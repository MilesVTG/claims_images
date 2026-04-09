"""Test runner endpoints — run pytest and store results (no auth required)."""

import os
import re
import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["test_runner"])


# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def _find_project_root():
    """Find project root by looking for pytest.ini."""
    # Container path
    if os.path.isfile("/project/pytest.ini"):
        return "/project"
    # Local dev: walk up from this file
    d = os.path.abspath(os.path.dirname(__file__))
    for _ in range(5):
        d = os.path.dirname(d)
        if os.path.isfile(os.path.join(d, "pytest.ini")):
            return d
    return os.getcwd()


PROJECT_ROOT = _find_project_root()


# ---------------------------------------------------------------------------
# Test file mapping by type
# ---------------------------------------------------------------------------

TEST_FILES_BY_TYPE = {
    "unit": [
        "tests/test_api_health.py",
        "tests/test_api_auth.py",
        "tests/test_api_prompts.py",
        "tests/test_api_claims.py",
        "tests/test_api_dashboard.py",
        "tests/test_api_config_deps.py",
        "tests/test_worker_services.py",
    ],
    "integration": [
        "tests/test_pipeline_e2e.py",
    ],
    "psychometrics": [
        "tests/test_golden_regression.py",
    ],
}

# Category mapping: filename stem -> display category
CATEGORY_MAP = {
    "test_api_health": "api_health",
    "test_api_auth": "api_auth",
    "test_api_prompts": "api_prompts",
    "test_api_claims": "api_claims",
    "test_api_dashboard": "api_dashboard",
    "test_api_config_deps": "api_config",
    "test_worker_services": "worker_services",
    "test_golden_regression": "golden_regression",
    "test_pipeline_e2e": "pipeline_e2e",
}

# Regex to parse pytest -v output lines
_RESULT_RE = re.compile(
    r"^(tests/\S+\.py)::(\S+)\s+(PASSED|FAILED|ERROR|SKIPPED)"
)


def _derive_category(test_file: str) -> str:
    """Derive category from test filename."""
    basename = os.path.basename(test_file).replace(".py", "")
    return CATEGORY_MAP.get(basename, basename)


def _parse_pytest_output(stdout: str) -> list[dict]:
    """Parse pytest -v stdout into a list of result dicts."""
    results = []
    for line in stdout.splitlines():
        m = _RESULT_RE.match(line.strip())
        if m:
            test_file, test_name, status = m.groups()
            results.append({
                "test_file": test_file,
                "test_name": test_name,
                "category": _derive_category(test_file),
                "status": status.lower(),
            })
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/health/tests/run")
def run_tests(
    run_type: str = Query(default="unit", regex="^(unit|integration|psychometrics)$"),
    db: Session = Depends(get_db),
):
    """Run pytest for a specific test type and store results in the DB."""
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    # Select test files for this run type
    test_files = TEST_FILES_BY_TYPE.get(run_type, [])
    if not test_files:
        return {"run_id": None, "status": "error", "detail": f"Unknown run type: {run_type}"}

    # Only include files that actually exist in the project
    existing_files = [f for f in test_files if os.path.isfile(os.path.join(PROJECT_ROOT, f))]
    if not existing_files:
        return {"run_id": None, "status": "error", "detail": "No test files found in container"}

    cmd = ["python3", "-m", "pytest"] + existing_files + ["-v", "--tb=line", "--no-header"]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        db.execute(
            text("""
                INSERT INTO test_runs (run_type, triggered_by, started_at, finished_at, status, duration_ms)
                VALUES (:rtype, 'dashboard', :started, :finished, 'error', :dur)
            """),
            {
                "rtype": run_type,
                "started": started_at.isoformat(),
                "finished": datetime.now(timezone.utc).isoformat(),
                "dur": int((time.monotonic() - t0) * 1000),
            },
        )
        db.commit()
        return {"run_id": None, "status": "error", "detail": "pytest timed out after 120s"}

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    finished_at = datetime.now(timezone.utc)

    # Parse individual test results
    results = _parse_pytest_output(proc.stdout)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    run_status = "passed" if failed == 0 and errors == 0 else "failed"

    # If 0 results, capture stderr for debugging
    debug_info = None
    if total == 0:
        debug_info = (proc.stderr or "")[:2000] + "\n---STDOUT---\n" + (proc.stdout or "")[:2000]

    # Insert the run record
    row = db.execute(
        text("""
            INSERT INTO test_runs
                (run_type, triggered_by, started_at, finished_at, status,
                 total, passed, failed, errors, skipped, duration_ms)
            VALUES
                (:rtype, 'dashboard', :started, :finished, :status,
                 :total, :passed, :failed, :errors, :skipped, :dur)
            RETURNING id
        """),
        {
            "rtype": run_type,
            "started": started_at.isoformat(),
            "finished": finished_at.isoformat(),
            "status": run_status,
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "dur": elapsed_ms,
        },
    ).fetchone()
    run_id = row[0]

    # Parse error messages from the tb=line output for failed tests
    error_lines = {}
    if failed > 0 or errors > 0:
        for line in proc.stdout.splitlines():
            if line.startswith("FAILED "):
                parts = line.split(" - ", 1)
                if len(parts) == 2:
                    test_path = parts[0].replace("FAILED ", "").strip()
                    name_part = test_path.split("::", 1)[-1] if "::" in test_path else test_path
                    error_lines[name_part] = parts[1].strip()

    # Insert individual results
    for r in results:
        db.execute(
            text("""
                INSERT INTO test_results (run_id, test_name, test_file, category, status, error_message)
                VALUES (:run_id, :name, :file, :cat, :status, :err)
            """),
            {
                "run_id": run_id,
                "name": r["test_name"],
                "file": r["test_file"],
                "cat": r["category"],
                "status": r["status"],
                "err": error_lines.get(r["test_name"]),
            },
        )

    db.commit()

    response = {
        "run_id": run_id,
        "run_type": run_type,
        "status": run_status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "duration_ms": elapsed_ms,
    }
    if debug_info:
        response["debug"] = debug_info

    return response


@router.get("/health/tests/latest")
def get_latest_run(
    run_type: str = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
):
    """Return the most recent test run with results grouped by category."""
    if run_type:
        run_row = db.execute(
            text("SELECT * FROM test_runs WHERE run_type = :rtype ORDER BY id DESC LIMIT 1"),
            {"rtype": run_type},
        ).fetchone()
    else:
        run_row = db.execute(
            text("SELECT * FROM test_runs ORDER BY id DESC LIMIT 1")
        ).fetchone()

    if not run_row:
        return {"run": None, "results_by_category": {}}

    run_cols = run_row._mapping
    run_id = run_cols["id"]

    results = db.execute(
        text("SELECT * FROM test_results WHERE run_id = :rid ORDER BY category, test_name"),
        {"rid": run_id},
    ).fetchall()

    by_category = {}
    for r in results:
        rm = r._mapping
        cat = rm["category"] or "unknown"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            "test_name": rm["test_name"],
            "test_file": rm["test_file"],
            "status": rm["status"],
            "duration_ms": rm["duration_ms"],
            "error_message": rm["error_message"],
        })

    return {
        "run": {
            "id": run_cols["id"],
            "run_type": run_cols["run_type"],
            "status": run_cols["status"],
            "started_at": run_cols["started_at"],
            "finished_at": run_cols["finished_at"],
            "total": run_cols["total"],
            "passed": run_cols["passed"],
            "failed": run_cols["failed"],
            "errors": run_cols["errors"],
            "skipped": run_cols["skipped"],
            "duration_ms": run_cols["duration_ms"],
        },
        "results_by_category": by_category,
    }


@router.get("/health/tests/history")
def get_run_history(
    run_type: str = Query(default=None, alias="type"),
    db: Session = Depends(get_db),
):
    """Return the last 20 test runs (summary only)."""
    if run_type:
        rows = db.execute(
            text("""
                SELECT id, run_type, status, started_at, total, passed, failed,
                       errors, skipped, duration_ms
                FROM test_runs WHERE run_type = :rtype
                ORDER BY id DESC LIMIT 20
            """),
            {"rtype": run_type},
        ).fetchall()
    else:
        rows = db.execute(
            text("""
                SELECT id, run_type, status, started_at, total, passed, failed,
                       errors, skipped, duration_ms
                FROM test_runs ORDER BY id DESC LIMIT 20
            """)
        ).fetchall()

    return [
        {
            "id": r._mapping["id"],
            "run_type": r._mapping["run_type"],
            "status": r._mapping["status"],
            "started_at": r._mapping["started_at"],
            "total": r._mapping["total"],
            "passed": r._mapping["passed"],
            "failed": r._mapping["failed"],
            "errors": r._mapping["errors"],
            "skipped": r._mapping["skipped"],
            "duration_ms": r._mapping["duration_ms"],
        }
        for r in rows
    ]
