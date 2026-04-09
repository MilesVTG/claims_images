# Handoff Notes — Claims Images

Notes for the next conversation. Read this before doing anything.

## TL;DR

Infrastructure is provisioned, all 3 services deployed to Cloud Run, DB seeded, 22/22 health checks pass. Blocked on dashboard browser access (Cloud Run IAM auth doesn't work with browsers). Next: fix dashboard access, redeploy worker, then build photo endpoints.

## What Happened Today

1. Full provision → deploy → seed → health check cycle working
2. Team audit found 13 issues in deploy.sh (7 critical) — all fixed
3. Seed runs as Cloud Run job inside VPC (laptop can't reach private Cloud SQL)
4. Replaced passlib with direct bcrypt (passlib unmaintained)
5. Schema.sql created — seed creates tables before inserting
6. Health check verifies seed data (login, claims, prompts)
7. All tickets assigned and synced to Jira POR-5152

## Blocker: Dashboard Browser Access

Cloud Run IAM auth (`--no-allow-unauthenticated`) requires an identity token in the Authorization header. Browsers don't send this — they just get 403. The `domain:vtg-services.net` binding is irrelevant because the browser never presents credentials.

**Try first (30 seconds):**
```bash
gcloud run services add-iam-policy-binding claims-dashboard \
  --region=us-central1 \
  --member=allAuthenticatedUsers \
  --role=roles/run.invoker
```
If org policy blocks this, use proxy for now:
```bash
gcloud run services proxy claims-dashboard --region=us-central1 --port=8080
# Then open http://localhost:8080
```

## What To Do Next (in order)

1. Fix dashboard browser access (see above)
2. Redeploy worker — still has old passlib code:
   ```bash
   ./scripts/deploy.sh worker
   ```
3. Update deploy.sh with correct dashboard auth approach
4. POR-5302 — `/api/photos` endpoints (upload, list, status, ask-question)
5. POR-5303 — Dashboard field mapping fixes
6. POR-5306 — E2E integration test
7. POR-5307 — Golden dataset regression

## Full Cycle (if needed)

```bash
./scripts/preflight.sh
./scripts/provision.sh
./scripts/deploy.sh --all --seed
./scripts/health_check.sh
```

## Tracking

- **Jira**: Epic POR-5152 — ALL tickets go here. Project POR.
- **DWB**: Project 5, prefix CI. API at localhost:8000. Use `X-Agent-ID: 1`.
- **Rule**: Every ticket goes in both DWB and Jira. Present as table: DWB # | JIRA # | JIRA SPRINT | TITLE | STATUS
- **Rule**: Real bugs get tickets before fixing. OK to ask if something warrants a ticket.
- **Rule**: Numbered lists (1. 2. 3.) with lettered sub-steps (a. b. c.) for all multi-item output.
- **Rule**: Action items / commands for Miles go at the bottom of the response.
- **Active sprint**: POR Sprint - Vladjic (ID 955), ends 2026-04-10
- **Miles Jira account ID**: 5c0e84cac22785142f681f78
- **dwb2jira CLI**: must run from ~/Dev/DWB_2_JIRA with its own .venv

## Known Gotchas

- Cloud SQL is PRIVATE IP only — no public IP, no local access
- Org policy blocks `allUsers` IAM on Cloud Run
- `dwb2jira` must run from `~/Dev/DWB_2_JIRA` or it reads the wrong `.env`
- Exchange password has special chars — must be single-quoted in `.env`
- GCP account is `mchick@vtg-services.net` (**.net** not .com)
- Worker still has old passlib code — needs redeploy before photo processing
- gcloud SDK on this machine doesn't support `--dockerfile` flag
- Python is `python3` on macOS (no `python` symlink)

## Script Colors

All scripts use: cyan banners, orange section headers, red errors, green pass.
