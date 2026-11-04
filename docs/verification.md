# Verification and demo checklist

[Documentation index](README.md) · Evidence reviewed 2026-11-04

There are three separate checks: deterministic tests, live model evaluation, and a manual product demo. None substitutes for the others.

## Offline checks

Use Python 3.12 and Node 22, matching Docker and the [CI workflow](../.github/workflows/ci.yml). Install backend development dependencies as described in [the README](../README.md).

From `backend/`, in PowerShell:

```powershell
$env:OPENAI_API_KEY = ""
$env:DATABASE_URL = "sqlite://"
$env:JWT_SECRET = "local-test-secret"
python -m pytest -q
```

From `frontend/`:

```powershell
npm ci
npx tsc --noEmit
npm run build
```

Backend tests use SQLite and stub AI calls. They require no OpenAI secret. The frontend build uses Google-hosted fonts and needs network access for those assets.

CI runs the backend and frontend jobs on pushes and pull requests. It does not deploy, run live quote evaluations, test browser flows or exercise PostgreSQL migrations. The workflow must be committed and pushed before GitHub can run it.

## Evidence available at this review

| Check | Result | Scope |
| --- | --- | --- |
| Backend tests during the preceding CI task | 57 passed | Isolated Python 3.12 container, no real key; before subsequent classification changes |
| Frontend clean install, type check and production build | Passed | Isolated Node 22 container during the CI task |
| Workflow syntax via actionlint | Passed | Local CI file during the CI task |
| Remote GitHub Actions run | Not run | Workflow was still local |
| PostgreSQL migration upgrade/downgrade/upgrade | Reported in earlier implementation notes | Historical 0007/0008 checks; not repeated here |
| Five-quote model evaluation | Historical and newly reported experiment scores | See [evaluation](extraction-eval.md); these are separate from CI |

The documentation cleanup did not rerun application tests or make live AI calls. Do not use the 57-test snapshot as evidence that later extraction edits passed. Source files were changing during this review; test the final checkout after those changes settle.

## Manual demo after code settles

| Scenario | Expected behaviour to verify |
| --- | --- |
| Upload each of the five sample quotes | Extraction completes or explains failure; missing fields and inconsistent arithmetic are visible; compare actual fields with the answer key |
| Inspect a catalog suggestion | Supplier, price and unit are visible; “Start request” opens a separate prefilled request |
| Save a catalog-linked line with a tampered browser price | Server stores the catalog price and recalculates the total |
| Single-line cable ties or toner | Electrical Engineering or IT Hardware is enforced, including on edit |
| Software subscription below the limit; then exactly $2,000 before tax | Office Supplies rule applies only below the limit |
| Mixed request with a minor cable-tie line | Current 50% value-share policy is observable; explain it as an assumption |
| Gross total $1,999.99; then $2,000.00 | First auto-approved, second pending for Acme |
| Raise an approved request above $2,000 | Approval resets to pending and activity explains why |
| Change only an approved request's title | Approval is retained |
| Same scenarios under another tenant | Acme's rules and enabled policy do not leak across tenants |

Use explicit manual values to demonstrate approval boundaries; model output should not determine the test setup. For rollback verification, use a disposable PostgreSQL database as explained in [migrations](migrations.md).

## Final PR evidence

State what changed, what was actually tested on the submitted revision, the measured extraction results, and the known assumptions. The documentation directory is now eligible for Git, but its files still need to be committed and included in the PR before reviewers can follow links to them.
