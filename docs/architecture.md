# Architecture

[Documentation index](README.md) · Reviewed 2026-11-04

The application has a Next.js frontend, one FastAPI backend and PostgreSQL. Files in `backend/app/services/` are modules inside that backend, not separately deployed services. OpenAI is an external dependency for interpreting quote text and matching catalog descriptions.

## Components and communication

```mermaid
flowchart LR
    User[Employee or buyer] --> Browser[Browser: Next.js UI]
    Next[Next.js server: port 3200] -->|Pages and assets| Browser
    Browser -->|HTTP and bearer JWT| API[FastAPI: port 7200]
    API -->|SQLAlchemy| DB[(PostgreSQL: port 5432)]
    API -->|pypdf: local text extraction| PDF[PDF bytes]
    API -->|Structured extraction and classification| AI[OpenAI API]
    API -->|Catalog embeddings| AI
```

The browser calls FastAPI directly using [the typed API client](../frontend/src/lib/api/client.ts). `NEXT_PUBLIC_API_URL` is included in the frontend at build time. The JWT is stored in local storage under `lio_token`.

[Authentication dependencies](../backend/app/core/deps.py) resolve the user and their membership. Tenant-owned requests, suppliers and articles are scoped by organisation. Commodity groups are shared reference data. Memberships support multiple rows in the database, but the current dependency selects a user's first membership; there is no active-organisation selector.

| Layer | Location | Responsibility |
| --- | --- | --- |
| Pages and forms | [frontend/src/app](../frontend/src/app) | Upload, review, catalog suggestions, request tracking and approval UI |
| API endpoints | [backend/app/routers](../backend/app/routers) | Authentication, tenant scope, validation and saving |
| Business logic | [backend/app/services](../backend/app/services) | Extraction, matching, booking rules, totals and approval policy |
| API shapes | [backend/app/schemas](../backend/app/schemas) | Pydantic validation and response contracts |
| Persistence | [backend/app/models](../backend/app/models) | SQLAlchemy tables and relationships |
| Schema and demo data | [migrations](../backend/alembic/versions), [seed](../backend/app/seed.py) | Apply schema changes, then insert missing reference/demo data |

## From quote to request

```mermaid
sequenceDiagram
    participant U as Browser
    participant A as FastAPI
    participant O as OpenAI
    participant D as PostgreSQL

    U->>A: POST /pdf/parse (PDF)
    A->>A: Validate file and extract text with pypdf
    A-->>U: Plain text
    U->>A: POST /extraction (text)
    A->>D: Load taxonomy and tenant rules
    A->>O: Extract fields and classify purchase
    O-->>A: Structured fields
    Note over A,O: Working tree may make a second group-classification call
    A->>A: Apply booking rules and arithmetic checks
    A-->>U: Fields, missing fields and warnings
    U->>A: POST /articles/suggestions
    A->>D: Read tenant catalog
    A->>O: Embed descriptions (catalog vectors cached)
    A-->>U: Candidate articles and negotiated prices
    Note over U: Employee reviews and edits the form
    U->>A: POST /requests
    A->>A: Enforce catalog prices, booking rules, totals and approval policy
    A->>D: Save request, lines and activity
    A-->>U: Saved request
    U->>A: PUT /requests/{id}/document (original PDF)
    A->>D: Store attachment
```

The parse and extraction calls are separate. Parsing does not store the original PDF; attachment happens after request creation and is a separate operation. A manual request can bypass extraction.

The merged baseline sends all groups in one extraction call. The uncommitted optimisation selects a category first, then a group from that category, unless a booking rule supplies the group. See [classification](commodity-classification.md) for its exact scope.

## Database relationships

This diagram shows the main foreign keys. Request ownership links are nullable in the schema for legacy compatibility; API-created requests use the current membership. Users also have nullable approval/audit links, omitted here for readability.

```mermaid
erDiagram
    users ||--o| profiles : has
    users ||--o{ organization_members : joins
    organizations ||--o{ organization_members : contains
    organizations ||--o{ organization_invites : issues
    organizations |o--o{ procurement_requests : owns
    users ||--o{ procurement_requests : creates
    commodity_groups |o--o{ procurement_requests : classifies
    organizations ||--o{ suppliers : owns
    organizations ||--o{ articles : owns
    suppliers ||--o{ articles : supplies
    procurement_requests ||--o{ order_lines : contains
    articles |o--o{ order_lines : optionally_links
    procurement_requests ||--o{ request_activity : records
    procurement_requests ||--o| request_documents : attaches

    organizations {
        uuid id PK
        string name
        json settings
    }
    commodity_groups {
        int id PK
        string category
        string name
    }
    procurement_requests {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        string vendor_name
        int commodity_group_id FK
        decimal total_cost
        decimal tax_amount
        string approval_status
        string approval_source
    }
    order_lines {
        uuid id PK
        uuid request_id FK
        uuid article_id FK
        string position_description
        decimal unit_price
        decimal amount
        decimal total_price
        decimal quoted_unit_price
    }
    articles {
        uuid id PK
        uuid organization_id FK
        uuid supplier_id FK
        string description
        decimal unit_price
        string currency
        string unit
    }
```

Important details:

- A category is a **text field on commodity groups**, not a separate table. The seed has 2,000 generated groups plus Office Supplies (2001).
- A request stores a free-text `vendor_name`; it has **no supplier foreign key**. Catalog linkage exists on individual order lines.
- Articles have a currency; requests have **no currency field**.
- Original PDFs are stored as bytes in `request_documents`, with at most one document per request.
- Tenant configuration lives in `organizations.settings`: `required_fields`, `booking_rules` and `auto_approval`. Settings updates merge supplied top-level fields; this is not a general recursive merge.

## Roles and business decisions

A requester creates and tracks requests. A buyer can approve or reject. An admin can also manage organisation settings and members. These are the implemented roles; there is no separate “manager” role.

The server applies catalog prices before calculating line totals, enforces the organisation's booking rule, calculates the gross total, then checks auto-approval. UI hints do not replace those checks.

Runtime versions, startup and accounts are in the [app README](../README.md). Database changes are in [migrations](migrations.md). Model accuracy and policy assumptions are documented in the individual feature pages.
