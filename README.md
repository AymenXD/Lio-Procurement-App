# Lio Procurement App

Create procurement requests from supplier quotes, review AI-extracted fields,
compare negotiated catalog prices, and apply Acme's booking and approval rules.

- **Frontend:** Next.js 15, React 19, Tailwind CSS 4
- **Backend:** FastAPI, SQLAlchemy, Alembic, JWT authentication
- **Database:** PostgreSQL 16

## Documentation

Start with [the documentation overview](docs/README.md), then read
[the current plan](docs/current-plan.md) and [architecture](docs/architecture.md).
Feature explanations, evaluation results and the demo checklist are linked there.

## Quick start with Docker

Start Docker Desktop (or Docker Engine with Compose v2), then run from this folder:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

On macOS/Linux, use `cp .env.example .env` for the copy step. Copy the template
only on first setup; retain your existing configuration on later runs.

An OpenAI API key is optional for starting the app and creating requests manually.
Add it to `.env` to enable AI extraction/classification and catalog suggestions.
PDF-to-text parsing itself uses a local library.

| Service | Address |
| --- | --- |
| App | http://localhost:3200 |
| API | http://localhost:7200 |
| Interactive API docs | http://localhost:7200/docs |

The backend applies migrations, seeds missing reference/demo data, and starts
the API. Data persists in the `postgres_data` volume. Seeding preserves existing
rule/policy settings and fills missing defaults or blank demo departments.

## Demo accounts

All demo accounts use password `demo1234`.

| Acme account | Role | Capability |
| --- | --- | --- |
| `requester@acme.com` | requester | Create and track requests |
| `buyer@acme.com` | buyer | Also approve or reject requests |
| `admin@acme.com` | admin | Also manage members and organisation settings |

Acme requests with a server-calculated total **strictly below $2,000, including
tax**, are auto-approved by default. Requests at or above the threshold wait
for a buyer or admin. Other tenants default to auto-approval disabled.

Walmart, Schaeffler, Siemens and BMW each have an `admin@<company>.com` account
for checking tenant isolation. Only Acme has the seeded supplier/article catalog.

## What is implemented

- PDF text extraction followed by structured AI interpretation, with missing-field
  and arithmetic warnings. Employees still need to review the results.
- Catalog suggestions showing supplier, negotiated price and unit. Selecting
  one opens a separate prefilled request; the server enforces its catalog price.
- Acme booking rules for cable ties, toner and small software subscriptions,
  enforced on request creation and update.
- Server-calculated totals, automatic approval and reapproval after material edits.

The seeded “small software” rule uses a subtotal below $2,000 and the rule matcher
uses a 50% line-value share for mixed requests. These are implementation assumptions.
Requests have no currency field; the approval threshold assumes USD. Extraction
warnings do not block auto-approval.

## Development without app containers

Docker is the reference setup. For host development, use Python 3.12 and Node 22.
The following commands use PowerShell, starting from this folder:

```powershell
docker compose up -d db
Copy-Item .env backend/.env
Set-Location backend
py -3.12 -m venv .venv
./.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 7200
```

The copied configuration uses localhost for PostgreSQL and allows the frontend
at port 3200. In another terminal, starting from this folder:

```powershell
Set-Location frontend
npm ci
npm run dev
```

## Tests and CI

Install backend development dependencies with `python -m pip install -e ".[dev]"`
from `backend/`, then run:

```powershell
$env:OPENAI_API_KEY = ""
$env:DATABASE_URL = "sqlite://"
python -m pytest -q
```

From `frontend/`:

```powershell
npm ci
npx tsc --noEmit
npm run build
```

[GitHub Actions](.github/workflows/ci.yml) runs these checks on every push and
pull request with Python 3.12 and Node 22. Backend tests use SQLite and mocked
AI calls; no database service or OpenAI secret is required. The frontend build
needs network access to fetch its Google-hosted fonts. CI does not deploy or
run the manual live-quote evaluation.

## Layout

```text
backend/              FastAPI routers, services, models, schemas and Alembic migrations
frontend/             Next.js pages, components and typed API client
.github/workflows/    CI workflow
docker-compose.yml    Local services
.env.example          Configuration template without secrets
```
