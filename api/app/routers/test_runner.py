"""Test runner endpoints — run pytest and store results (no auth required)."""

import os
import re
import subprocess
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(tags=["test_runner"])

# Project root is 3 levels up from this file: routers/ -> app/ -> api/ -> project
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

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
# Matches: tests/test_foo.py::TestClass::test_name PASSED
# or:      tests/test_foo.py::test_name PASSED
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


@router.post("/health/tests/run")
def run_tests(db: Session = Depends(get_db)):
    """Run the full pytest suite and store results in the DB."""
    started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()

    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-v", "--tb=line", "--no-header"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=PROJECT_ROOT,
        )
    except subprocess.TimeoutExpired:
        # Record a failed run on timeout
        db.execute(
            text("""
                INSERT INTO test_runs (run_type, triggered_by, started_at, finished_at, status, duration_ms)
                VALUES ('unit', 'api', :started, :finished, 'error', :dur)
            """),
            {
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

    # Insert the run record
    row = db.execute(
        text("""
            INSERT INTO test_runs
                (run_type, triggered_by, started_at, finished_at, status,
                 total, passed, failed, errors, skipped, duration_ms)
            VALUES
                ('unit', 'api', :started, :finished, :status,
                 :total, :passed, :failed, :errors, :skipped, :dur)
            RETURNING id
        """),
        {
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
        # --tb=line produces lines like: FAILED tests/test_foo.py::test_bar - AssertionError: ...
        for line in proc.stdout.splitlines():
            if line.startswith("FAILED "):
                parts = line.split(" - ", 1)
                if len(parts) == 2:
                    test_path = parts[0].replace("FAILED ", "").strip()
                    # test_path looks like tests/test_foo.py::test_bar
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

    return {
        "run_id": run_id,
        "status": run_status,
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "duration_ms": elapsed_ms,
    }


@router.get("/health/tests/latest")
def get_latest_run(db: Session = Depends(get_db)):
    """Return the most recent test run with results grouped by category."""
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

    # Group by category
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
def get_run_history(db: Session = Depends(get_db)):
    """Return the last 20 test runs (summary only, no individual results)."""
    rows = db.execute(
        text("""
            SELECT id, run_type, status, started_at, total, passed, failed,
                   errors, skipped, duration_ms
            FROM test_runs
            ORDER BY id DESC
            LIMIT 20
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
