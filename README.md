# OpsBridge

OpsBridge is an event-driven remediation control plane for the Cognition Devin take-home. It turns a scoped GitHub issue in a Superset fork into a managed Devin session, then reports task status, PR output, and lightweight effectiveness metrics.

## Workflow

```text
Simulated GitHub issue event
        -> OpsBridge task ledger
        -> Devin API session
        -> Superset remediation PR or blocker
        -> Dashboard/reporting
```

The MVP defaults to dry-run mode so the event pipeline can be tested without spending Devin credits.

## Configuration

Copy `.env.example` to `.env` and fill in the Devin values:

```env
DEVIN_ORG_ID=your_org_id
DEVIN_API_KEY=your_service_user_key
DEVIN_ENABLE_REAL_CALLS=false
DEVIN_MAX_ACU_LIMIT=2
SUPERSET_REPO_URL=https://github.com/lukecode0/superset
DEFAULT_ISSUE_NUMBER=3
```

Keep `DEVIN_ENABLE_REAL_CALLS=false` until you are ready to create a real Devin session. Start with `DEVIN_MAX_ACU_LIMIT=2` for a capped live run.

## Run Locally

```bash
pip install -e .
uvicorn app.main:app --reload
```

Open:

```text
http://localhost:8000/dashboard
```

## Run With Docker

```bash
docker compose up --build
```

Open:

```text
http://localhost:8000/dashboard
```

Stop the container with `Ctrl+C`, or from another terminal:

```bash
docker compose down
```

## Simulate an Event

Dry run, no Devin credits spent:

```bash
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"issue_number": 3}'
```

Real Devin session:

1. Set `DEVIN_ENABLE_REAL_CALLS=true` in `.env`.
2. Restart the app.
3. Trigger:

```bash
curl -X POST http://localhost:8000/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"issue_number": 3, "dry_run": false}'
```

Refresh a Devin session status:

```bash
curl -X POST http://localhost:8000/api/tasks/1/sync
```

Send a follow-up message to a waiting Devin session:

```bash
curl -X POST http://localhost:8000/api/tasks/1/message \
  -H "Content-Type: application/json" \
  -d '{"message": "GitHub access has been granted. Please continue and open a PR. Do not merge it or close the issue."}'
```

## Reset Demo State

Local Python run:

```bash
rm -f opsbridge.db
```

Docker run:

```bash
docker compose down -v
```

## Observability

OpsBridge stores every task in SQLite and reports:

- active/completed/failed task counts
- issue and trigger source
- Devin session URL
- PR URL when reported by Devin
- requested ACU limit
- consumed ACUs when reported by Devin
- errors or blockers

This answers the engineering-leader question: "Is the automation producing useful remediation output, and at what cost/reliability?"

## Selected Superset Issues

- https://github.com/lukecode0/superset/issues/3
- https://github.com/lukecode0/superset/issues/2
- https://github.com/lukecode0/superset/issues/1

## Demo Output

- Devin session: https://app.devin.ai/sessions/5c4d18266d2549969152e80f270ea0aa
- Remediation PR: https://github.com/lukecode0/superset/pull/4
