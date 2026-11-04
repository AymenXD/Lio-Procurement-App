# Catalog suggestions and negotiated prices

[Documentation index](README.md) · Implemented; reviewed 2026-11-04

## What this solves

The quote contains the supplier's offered price. Acme may already have a negotiated catalog price for an equivalent item. The quote is not necessarily “wrong”, and the catalog price is not necessarily lower.

Suggestions search Acme's catalog across suppliers, so a candidate can come from the quoted vendor or another vendor. A negotiated price belongs to that specific catalog article and supplier.

For example, a quoted item at $50 from supplier A and a similar catalog item at $40 from supplier B are **two purchasing options**. The employee must check equivalence, units and quantity before choosing B.

## What the employee sees

The new-request form loads suggestions after extraction and when the commodity group changes. “Check catalog prices” refreshes them after manual entry or edits.

Each suggestion shows the article, supplier, price and unit. Recognised unit synonyms allow a savings comparison; unknown or different units are labelled as not directly comparable. The best suggestion is shown first, with additional options expandable.

“Start request ↗” opens a **separate, prefilled request in a new tab** with that article's supplier, description, price, unit and a copied quantity. This is the implemented action for any suggestion, including one from the same supplier. The employee reviews it and submits it; it does not silently replace a line in the original quote.

## How matching works

`POST /articles/suggestions` calls [catalog_matching.py](../backend/app/services/catalog_matching.py):

1. Read articles belonging to the caller's organisation.
2. If a commodity group is supplied, restrict candidates to suppliers whose category matches that group's category.
3. Keep the cheapest article for each identical description.
4. Compare description embeddings using `text-embedding-3-small` with 256 dimensions.
5. Return up to three candidates with similarity at least 0.40 and within 0.10 of the best candidate.
6. Drop those whose unit price is more than 10 times above or below the quoted unit price.

This is a heuristic search, not proof that products are interchangeable. If no API key is configured or the embedding call fails, the form receives no suggestions and remains usable.

Catalog vectors are cached in memory by organisation and article count. Restarting the backend or changing the count rebuilds them; editing descriptions without changing the count does not.

## What the server enforces

A selected article is stored on the order line as `article_id`, with optional `quoted_unit_price` for comparison. On both create and update, [the request router](../backend/app/routers/requests.py):

- Verifies that the article belongs to the caller's organisation; an inaccessible article returns 404.
- Loads the catalog's unit price and unit, replacing browser-supplied values.
- Recalculates the line total using Decimal arithmetic.
- Records catalog use in request activity.

The request edit page preserves these links. See [migration 0007](migrations.md).

## Limits and choices

- The UI starts a separate request; there is no same-vendor “apply to this line” action.
- Requests have a free-text vendor, not a supplier FK. The API validates article ownership and price, but does not enforce a single matching supplier for every linked line.
- A similar description or plausible price does not prove equivalence. Historical testing still suggested a moss panel with a logo for an acrylic logo.
- Unit synonyms do not handle pack sizes or unit conversion. The copied quantity needs review if the units differ.
- Requests have no currency field, so currency equality is not validated for savings.
- Identical-description deduplication does not compare specifications, currency or pack size.
- Shipping and fee descriptions can also be searched. There is no persisted row-kind filter for catalog matching.
- There is no exact article-number/lexical matching stage, persistent embedding table or vector database.

The historical “10 of 11 lines right” observation was a small manual sample, not a general accuracy guarantee. Its context is in [the implementation log](archive/implementation-log.md).

## Code and checks

[Matching service](../backend/app/services/catalog_matching.py) · [matching tests](../backend/tests/test_catalog_matching.py) · [suggestion UI](../frontend/src/components/CatalogSuggestions.tsx) · [new-request form](../frontend/src/app/dashboard/new-request/page.tsx)

The API tests in [test_smoke.py](../backend/tests/test_smoke.py) cover catalog price enforcement and cross-tenant article rejection. See [verification](verification.md) for the demo checklist.
