# Database migrations and seed data

[Documentation index](README.md) · Reviewed 2026-11-04

The current migration head is **0008**. Docker startup runs `alembic upgrade head`, then `python -m app.seed`, then starts the API.

## Schema changes

Revisions 0001–0006 are the supplied schema history: core tables, organisation settings, roles/approval, activity/documents, articles and tenant-scoped master data. The assignment added:

| Revision | Table | Change |
| --- | --- | --- |
| [0007](../backend/alembic/versions/0007_order_line_catalog_link.py) | `order_lines` | Nullable `article_id` FK with index and `ON DELETE SET NULL`; nullable `quoted_unit_price NUMERIC(12,2)` |
| [0008](../backend/alembic/versions/0008_request_tax_and_approval_source.py) | `procurement_requests` | Nullable `tax_amount NUMERIC(12,2)`; nullable `approval_source` restricted to `auto`, `manual` or null |

0007 leaves existing non-catalog lines valid. Deleting an article removes the link, preserving the saved order line and price.

0008 backfills already approved or rejected requests to `manual`. Pending requests remain unset. Old tax values remain null; application calculations treat missing tax as zero.

Both revisions have downgrade functions that remove their added columns and constraints. A rollback discards those values, so verify downgrade/upgrade cycles on a **disposable database**, not the working demo database.

## Check the running database

From the repository root:

```bash
docker compose exec backend alembic current
docker compose exec backend alembic heads
```

The first reports what the running database has applied; the second reports the head present in that container's code. With the current image and migrations applied, both should identify 0008. Reading this document does not establish the state of a running container.

## Seed changes, not migrations

[seed.py](../backend/app/seed.py) inserts missing reference/demo records and adds:

- Shared commodity group 2001, Office Supplies, under Office & Administration.
- Acme's booking rules if the `booking_rules` setting is absent.
- Acme's enabled below-$2,000 policy if `auto_approval` is absent.
- Demo profile departments when blank; the department column already existed.

An explicit empty rule list or a disabled policy is preserved. Seeding is repeatable, but “never updates anything” would be inaccurate: missing settings and blank demo departments can be filled.

There is no migration for tenant-owned commodity groups, request currency, stored row kinds or a vector index. Those appeared in earlier plans but are not in the schema.

The previous implementation notes report PostgreSQL upgrade/downgrade/upgrade checks for 0007 and 0008. They are historical evidence; [the current CI](verification.md) runs SQLite API tests and does not exercise Alembic against PostgreSQL.
