# Archived original plan

Archived on 2026-11-04. This preserves the original proposal, including designs that were simplified, deferred or never implemented. It is historical context, not a description of the current system. Use [the current plan](../current-plan.md) instead.

---

# Acme Corp: Issues and Solutions

We extend the provided `lio-procurement-app` (FastAPI + SQLAlchemy/Alembic + Next.js, Postgres) for the customer **Acme Corp**. We work through one issue at a time. Each issue has five parts:
- **What happens today:** the symptom and the evidence.
- **Root causes:** why it happens.
- **Solution:** what we change and why.
- **Where:** the files involved.
- **How we verify it.**

Useful context for every issue:
- **Commodity groups:** a global taxonomy of 2,000 groups. Ids 1–50 are the classic list; the rest are generated variants such as "Toner Cartridges — Bulk".
- **Master data:** only Acme has it, namely 120 suppliers and 1,920 catalog articles with negotiated USD prices.
- **Tenant settings:** stored in `organizations.settings` (JSONB) and validated by `OrganizationSettings`.
- **Test data:** the five customer quotes live in `../quotes/`.

---

## Issue 1: PDF extraction isn't reliable

> "Fields come out incorrect or empty, and sometimes the upload errors out completely."

### What happens today
- **The flow:**
  1. The browser sends the PDF to `POST /pdf/parse`, which extracts the text with pypdf's plain mode.
  2. The browser sends that text to `POST /extraction`.
  3. **One** gpt-4o-mini call extracts the fields **and** picks a commodity group out of all 2,000.
- **We reproduced it on the running app:** `/pdf/parse` succeeds for all five quotes (every one has a text layer, none is encrypted, and the `.Pdf` extension is fine). **So the failures happen in the AI step.**
- **Measured baseline: 11 / 30** on the eval below. 2 of the 5 quotes crash, the vendor is wrong on the other 3, alternatives are counted as lines, and shipping and fees are dropped. Results per step are in `docs/extraction-eval.md`.

### Root causes
**"The upload errors out completely"**
1. **The output schema rejects `null` and formatted values.** `vat_id`, `department` and `unit` are typed `str`, and prices and amounts are typed `float`. A missing tax ID (`null`), `"$1,409.06"` or `"U.P."` fails validation, and the whole extraction returns `success: false` with raw exception text. **Every one of the five quotes has such a trap.**
2. **The JSON is free-form and nothing enforces a schema** (temperature 0.3, markdown fences stripped by hand). Descriptions containing quotes (`"askLio"`, `13"`) can break the JSON.
3. **All 2,000 commodity groups are pasted into every prompt.** That's roughly 25k tokens: slow, costly, and the output is capped at 4,000 tokens.

**"Fields come out wrong or empty"**

4. **Plain text extraction scrambles the reading order.** Hollis's labels end up separated from their values, Apple's configuration bullets come before the header, and Hartwell's customer appears at the end.
5. **Some facts exist only in images.** Verdeform's legal name and EIN are in a background image, so text extraction can never see them.
6. **The prompt doesn't know how quotes are structured.**
   - It doesn't recognise heading rows, "Alternative" positions, discounts, or shipping, fees and tax as distinct from items.
   - "Total" is undefined, and quotes may print net or gross.
   - Its example tax ID `12-3456789` invites hallucination.
   - "Department" is mapped to "Customer/Bill To", so the buyer company ends up there.
7. **Nothing checks the numbers.** Quantity × unit price vs line total and the sum of the lines vs the total are never compared, so wrong numbers pass silently.
8. **Frontend gaps:**
   - Only the browser-reported file type is checked, with no size check.
   - Re-selecting the same file after an error does nothing.
   - Missing fields appear as one sentence, with no per-field highlighting.
   - Raw backend errors are shown to the user.
   - The PDF is attached even when extraction failed.

### What correct extraction looks like (expected values; these become the eval fixtures)
| Quote | Vendor | Tax ID | Lines that must be extracted | Must **not** become lines | Net / charges / tax / **total** | Commodity |
|---|---|---|---|---|---|---|
| QT-4120 | Greenmantle Moss Studio, LLC | 85-3252405 | Moss Art Panel 1 × 715.26 (894.08 −20%); Logo horizontal 1 × 622.00 | heading row; "Alternative" vertical logo 430.00 | 1,337.26 / ship 215.00 / 133.88 / **1,686.14** | Office Equipment (15)? |
| QT-OF2312380 | Bloomcraft Interiors, Inc. (verdeform) | 27-1073640 (**image only**) | 13.78 sq ft × 52.00; 15.75 lin ft × 7.65; logo 1 × 350.00 | Moss Duo upsell, surcharge text | 1,187.05 / ship 113.85 / 112.20 / **1,413.10** | 15? |
| QuoteA0492_23 | Hollis Greenscapes | 94-1985704 (not Seller's Permit 333-571207) | moss panel 1,560.00; transport 320.00 | heading 1.; alternatives 1.1a / 1.1b ("U.P."); "Carried forward" | 1,880.00 / – / 162.15 / **2,042.15** | 15? |
| Apple MBA | Apple (no legal name printed) | 94-2404110 | MacBook Air 13" M2, 1 × 1,409.06 | 12 configuration bullets | 1,409.06 / eWaste fee 4.00 / 121.53 / **1,534.59** | Hardware (29) |
| Hartwell | Hartwell Industrial Tools, Inc. | none | grinding machine 15,000.00; delivery and installation 2,000.00 | — | 17,000.00 / – / 1,402.50 / **18,402.50** | Production Machinery (45) |

### Solution
1. **Measure first.** `backend/scripts/eval_extraction.py` runs the five quotes through the pipeline and compares the result field by field with the table above. Comparison rules:
   - tax IDs as digits only
   - names case-insensitively
   - money within ±0.01
   - lines in any order

   We run it on today's code (the baseline score) and after each change. It needs a real key and is a manual tool, not a CI test.
   - **The answer key is built by hand from the PDFs before any code changes**, so the code is never tuned to its own output.
   - **Five tuned documents show improvement, not production-wide accuracy.** The PR says so.
2. **Layout-preserving text first.** Switch pypdf to `extraction_mode="layout"`.
   - **Verified:** this already restores reading order and table rows on the two worst quotes, at zero extra cost.
   - Text stays the default input. The PDF-as-image path is only a fallback (step 6).
3. **Enforced output schema with typed rows.** Use OpenAI Structured Outputs bound to a Pydantic model at temperature 0, so the model can't return malformed JSON or wrong types.
   - Every optional field is nullable, so "absent" is valid and no longer a crash. This replaces the interim `_drop_nulls` fix.
   - Amounts are returned as decimal strings and parsed by our code into `Decimal`.
   - **The model labels every priced row** with a `kind`: `item`, `shipping`, `fee`, `discount`, `tax`, `alternative` or `subtotal`.
   - **Our code, not the model, decides what becomes an order line:**
     - `item`, `shipping`, `fee` and `discount` rows become lines; a discount is a negative line.
     - `tax` rows are summed into `tax_amount`.
     - `alternative` and `subtotal` rows are dropped, but returned as "excluded rows" so the reviewer can see them.
     - This rule is deterministic, unit-testable and auditable, and the model only has to classify rows.
4. **A quote-aware prompt:**
   - It describes how to label rows (above): heading rows without a price are ignored, and "Alternative", optional and carried-forward rows are labelled, not guessed away.
   - A discount printed in a separate column is applied to that line's unit price.
   - The vendor is the issuing company, never the recipient.
   - It contains no example values the model could copy.
   - The document text is clearly delimited and treated as data, not instructions.
5. **Classification split out of extraction.**
   - It runs as a second, small call: first pick one of the 22 categories, then a group within that category (about 90 options, restricted to that list).
   - This drops the 2,000-line list from the prompt and gives better choices.
   - Issue 3's booking rules apply on top.
6. **Deterministic reconciliation, then a vision fallback only when needed.**
   - **Checks, in `Decimal`, as small pure functions:**
     - quantity × unit price = line total
     - Σ lines + tax = grand total
   - A mismatch becomes a **warning** for the review form, never a failure.
   - **Vision fallback:** we call the model again with the **PDF itself as an OpenAI `file` input** (text plus page images) only when one of these holds:
     - the vendor, the tax ID, the lines or the grand total is missing
     - reconciliation fails
   - **Which result we keep:** the vision result if it reconciles; otherwise the text result, with its empty fields filled from the vision result.
   - **Cost:** easy quotes cost one call; hard ones cost two.
   - **Coverage:** this handles Verdeform, whose legal name and EIN exist only in an image. Hartwell prints no tax ID, so it pays the second call and still, correctly, gets none. We accept that cost.
7. **Partial results and a robust endpoint.**
   - **Never discard a useful extraction:**
     - A missing field (a tax ID, say) is returned empty and listed in `missing_fields` for the user to fill.
     - Extraction fails only when the PDF can't be read or the AI call itself fails.
   - A single `POST /extraction` takes the file, so text no longer makes a round trip through the browser.
   - It checks the `%PDF-` signature and the 10 MB limit.
   - The OpenAI client is created once, with a timeout and one retry on 429/5xx.
   - Errors are typed and readable; raw exception text never reaches the user.
   - Logs record durations, tokens and whether the fallback ran, but never document text or the key.
8. **Frontend:**
   - a size check
   - the file input resets after each attempt
   - per-field "missing" highlighting; a missing tax ID never blocks submission
   - warnings shown next to the fields they concern
   - excluded rows (alternatives, subtotals) listed collapsed under the lines
   - the PDF attached only after successful extraction
   - a disabled submit button while saving

### Where
- `backend/app/services/pdf.py`, `services/extraction.py`, a new `services/ai.py` (OpenAI wrapper), a new `services/reconciliation.py` (row kinds → lines, checks), `schemas/extraction.py`, `routers/extraction.py`, `routers/pdf.py`
- `backend/scripts/eval_extraction.py` with fixtures under `backend/tests/fixtures/`
- `frontend/src/app/dashboard/new-request/page.tsx`, `frontend/src/lib/api/index.ts`

### How we verify
- **Eval table:** the baseline score vs the new score per quote and field. It goes into the PR description.
- **pytest with OpenAI stubbed:**
  - `null` fields no longer crash
  - row kinds map correctly:
    - `alternative` and `subtotal` rows are excluded
    - `tax` goes to `tax_amount`
    - `discount` becomes a negative line
  - reconciliation warnings appear on a mismatch and not on the five answer-key totals
  - the vision fallback runs only when a key field is missing or reconciliation fails, and its result is merged as described
  - a missing tax ID returns a partial result, not a failure
  - a non-PDF file is rejected by its signature
  - the 2,000-group list is no longer in the prompt
- **Tests never see a real key.** A `conftest.py` clears `OPENAI_API_KEY`. Today `test_extraction_without_api_key` fails when pytest runs inside the backend container, because it inherits the key from `.env`.
- **Manual:** upload each quote in the UI as `requester@acme.com`.

---

## Issue 2: Negotiated prices aren't used

> "When someone creates a request, suggest the matching articles we already have on catalog."

### What happens today
- **The catalog exists, but only as a list.** Acme has 1,920 articles, each with a supplier, negotiated `unit_price`, `unit` and pack `quantity`. They are shown only in the Articles list.
- **Search is plain substring matching.** `GET /articles` checks `ILIKE %term%` against the description or article number, so a whole order-line description ("13" MacBook Air: Apple M2 Chip…") matches nothing.
- **The new-request form never consults the catalog**, and an order line has no link to an article.

### Root causes
1. **No matching step** between order lines and catalog articles.
2. **Matching has to work on meaning, not words.** "MacBook Air" should find "Business laptop 14" i5 / 16 GB…", although the two share no words.
3. **No record of catalog usage,** so negotiated-price compliance can't be measured.

### Solution
1. **Matching, cheapest signal first.** This runs only on `item` lines, never on shipping or fees.
   1. **Exact:** an article number printed in the line text is a certain match.
   2. **Lexical:** word overlap on normalised descriptions (lower-case, punctuation and units stripped). It's cheap, explainable, and works without a key.
   3. **Embeddings for synonyms:** "MacBook Air" vs "Business laptop 14" i5…" share no words.
      - OpenAI `text-embedding-3-small` vectors for Acme's articles are stored in a small table (`article_embeddings`).
      - They're created lazily on first use and refreshed when an article changes.
   - **Ranking:** the scores are combined, with a small boost when the supplier matches the quote's vendor and a cut-off so weak matches aren't shown. We keep the top 3 per line.
   - *More time:* a small LLM judge that confirms a match is truly substitutable (same spec, not just a similar name) and may abstain.
2. **Suggestion endpoint.** `POST /articles/suggestions {lines: [{description, unit_price, quantity}], vendor_name?}`. Per match it returns:
   - supplier, negotiated price, unit, pack quantity and currency
   - the **difference against the offered price**, compared per unit
   - `same_supplier`: whether the article's supplier is the quote's vendor
   - why it matched: exact, lexical or semantic
3. **UI: never silently replace the quote's supplier.** In the new-request form, each item line gets a "Catalog match" hint:
   - **Same supplier:** an **"Apply negotiated price"** button takes the description, unit price and unit from the article.
   - **Different supplier:** the hint shows "Cheaper with <supplier>: $X" and a **"Start separate request"** button that opens a new request prefilled with that article. The current request stays with the quoted vendor.
4. **The server trusts the catalog, not the client.** On create and update, a line with an `article_id`:
   - must belong to the caller's organisation; otherwise the server returns 404
   - gets its unit price, unit and currency from the catalog row, whatever the browser sent
5. **Audit.** A migration adds to `order_lines`:
   - `article_id` (nullable FK), the article the line uses
   - `quoted_description` and `quoted_unit_price`, the original values from the quote

   Together these keep both sides, so savings and catalog compliance can be measured. The activity log records each switch: "Line 2 → catalog article ABC-123 ($1,409.06 → $1,199.00)".

### Where
- `backend/app/services/catalog_matching.py` (new), `routers/articles.py`, `routers/requests.py`, `schemas/requests.py`, `models/procurement_request.py`, `models/article.py` (embedding table), `alembic/versions/0007_…`
- `frontend/src/app/dashboard/new-request/page.tsx`, a new `frontend/src/components/ArticleSuggestions.tsx`, `frontend/src/lib/api/index.ts`

### How we verify
- **pytest with embeddings stubbed:**
  - org scoping: another tenant's articles never appear, and a foreign `article_id` is rejected
  - an exact article number beats a lexical match, which beats a semantic one
  - the cut-off and the supplier boost
  - the per-unit price difference
  - the lexical-only fallback without a key
  - on create, the catalog's price overrides the client's, and `article_id` and the quoted values are saved
  - a different-supplier match never changes the request's vendor
- **Manual:** the Apple quote should suggest catalog business laptops with their negotiated prices, as "Start separate request" if the supplier isn't Apple.

---

## Issue 3: Commodity groups don't match Acme's booking

> "Cable ties → Electrical Engineering, printer toner → IT Hardware, small software subscriptions → Office Supplies. Non-negotiable."

### What happens today
- **The AI picks freely** among 2,000 groups (Issue 1). Nothing is tenant-specific, and the user can choose anything from a 2,000-option dropdown with no search.
- **The taxonomy doesn't line up with Acme's rules:**
  - "Electrical Engineering" exists (id 11).
  - "IT Hardware" is *Information Technology › Hardware* (id 29).
  - **"Office Supplies" doesn't exist.** The nearest category is *Office & Administration*.
  - "Toner Cartridges" (204 and its variants) is exactly where the system "keeps putting" toner.
- **Saving organisation settings replaces the whole settings object.** Any new rules stored there would be wiped by the existing "required fields" toggle.

### Root causes
1. Customer-specific accounting rules have no place in the product. Classification is purely generic.
2. A rule enforced only in the prompt or in the UI can be ignored, either by the model or by the user. "Non-negotiable" means the **server** has to enforce it.

### Solution
1. **Rules as tenant configuration.** `OrganizationSettings.booking_rules`, a list of entries like `{label, keywords[], commodity_group_id, max_total?}`. It's validated like the existing settings, and the settings PATCH is changed to **merge** instead of replacing the whole object.
2. **Acme's rules are seeded idempotently:**
   - `cable tie`, `zip tie` → 11 Electrical Engineering
   - `toner` → 29 IT Hardware
   - `subscription` + software terms, with a request total under a threshold → **Office Supplies**
3. **Office Supplies as an Acme-owned group.**
   - **The problem:** the customer named a group that doesn't exist. We don't quietly map it to Office Equipment or Software, and we don't add it to the global taxonomy, which every tenant sees.
   - **The change:**
     - A migration adds a nullable `organization_id` to `commodity_groups`; `null` means global.
     - The seed creates "Office & Administration › Office Supplies" for Acme only.
     - The commodity list and request validation accept global groups plus the caller's own; anything else returns 404.
   - The PR states this as an assumption.
4. **Deterministic rule engine.** A pure function `apply_booking_rules(lines, total, rules)` matches the keywords against the line descriptions.
   - If matching lines make up the largest share of the request value, the rule's group wins.
   - It runs **after** AI classification in the extraction response, so the user sees it, and again **on create and update** in the requests router, so it can't be bypassed.
   - **The rule that fired is recorded:** its label is returned as `appliedRule`, and the activity log records "Booked per Acme rule: …".
5. **UI.**
   - When a rule applied, the commodity field shows a locked "per Acme booking rule" badge.
   - A searchable commodity picker replaces the 2,000-option `<select>`.
   - Optionally, a simple rules card in Organization → Settings for admins.
6. *More time:* **propose new rules from corrections.** When users repeatedly change the AI's group from X to Y for similar descriptions, show admins a suggested rule to accept or ignore.

### Where
- `backend/app/services/booking_rules.py` (new), `schemas/organizations.py`, `routers/organizations.py`, `routers/requests.py`, `routers/commodity_groups.py`, `models/commodity_group.py`, `services/extraction.py`, `seed.py`, `alembic/versions/…` (org-owned groups)
- `frontend/src/app/dashboard/new-request/page.tsx`, `requests/[id]/page.tsx`, `organization/page.tsx`, a new searchable commodity picker component

### How we verify
- **pytest:**
  - each of the three rules applies
  - the threshold works for "small" subscriptions
  - mixed requests are decided by value share
  - **a user-chosen group is overridden on create and update**
  - another tenant is unaffected and can't see or use Acme's Office Supplies group
  - a settings PATCH no longer wipes the rules
  - the seed stays idempotent
- **Manual:** a request containing cable ties is always booked under Electrical Engineering, whatever the AI or the user picks.

---

## Bonus: buyers shouldn't approve everything

> "Anything below $2,000 shouldn't need approval at all." (optional)

### What happens today
- Every request starts `pending` and needs a buyer or admin to approve it.
- **`total_cost` and line totals come from the browser** as floats and are stored as sent. A threshold on them would be trivially bypassable.
- **Any member can edit a request after approval, and it stays approved.** An approved $1,500 request could be raised to $50,000.
- **Quotes define "total" differently.** Hollis is $1,880 net but $2,042.15 including tax, so it lands on either side of $2,000.

### Solution
1. **Server-computed totals from typed lines (prerequisite).**
   - Each order line gets a `kind`: `item`, `shipping`, `fee` or `discount`, carried over from Issue 1's row kinds. Discounts are negative.
   - The line total is quantity × unit price.
   - `total_cost` = the sum of the lines + `tax_amount`, a new column.
   - Everything is computed with `Decimal`; client-sent totals are ignored.
   - This matches what each quote prints as its total, and what Acme actually pays.
2. **Policy as tenant configuration, off by default.**
   - `OrganizationSettings.auto_approval = {enabled: false, below_amount: 2000, currency: "USD"}`.
   - It's enabled only for Acme, through the seed.
   - **The rule is stated explicitly:**
     - **Basis:** the gross total, including tax, shipping and fees.
     - **Currency:** it must equal the policy's currency, otherwise manual approval.
     - **Boundary:** strictly below the threshold, so $2,000.00 exactly needs a buyer.
3. **Approval source.** A new `approval_source` column holds `auto`, `manual` or null.
   - An automatic decision never has a human approver: `approved_by = null`.
   - The activity log records "Auto-approved by policy (< $2,000)".
4. **On create:** if the policy applies, the request becomes `approved` with `approval_source = auto`.
5. **On update:**
   - **Auto approval is re-evaluated after any financial edit** (lines, tax, currency). A request that now reaches $2,000 goes back to `pending`.
   - **Manual approval is invalidated by a material change:**
     - **Material:** vendor name, tax ID, line descriptions, quantities, prices, tax or currency. The request goes back to `pending`, which closes the existing loophole.
     - **Not material:** title or notes. The approval stays.
6. **UI:** an "Auto-approved" badge in the request list, the detail page and Approvals.

### Where
- `backend/app/services/approval_policy.py` (new), `services/totals.py` (new), `routers/requests.py`, `schemas/requests.py`, `schemas/organizations.py`, `models/procurement_request.py`, `alembic/versions/0008_…`, `seed.py`
- `frontend/src/app/dashboard/requests/*`, `approvals/page.tsx`, `new-request/page.tsx`, `lib/api/index.ts`

### How we verify
- **pytest:**
  - $1,999.99 is auto-approved with `approval_source = auto` and no approver
  - $2,000.00 and above stays pending
  - a request in another currency stays pending
  - a client-sent `totalCost` is ignored, and a discount line lowers the total
  - editing above the threshold goes back to pending
  - a manually approved request goes back to pending after a vendor or price change, but not after a title change
  - other tenants (policy off by default) are unchanged
- **Manual, with the quotes:**
  - Apple ($1,534.59) is auto-approved.
  - Hollis ($2,042.15) and Hartwell ($18,402.50) need a buyer.

---

## Hand-off: the PR description

The PR description is the only hand-off; there are no slides. It contains:
- **Per issue:** the problem, the change, and how it was verified.
- **The eval table:** baseline vs final, per quote and check, with a clear note that five tuned documents show improvement, not production-wide accuracy.
- **Screenshots:**
  - a quote extracted with its warnings
  - a catalog suggestion
  - a booking-rule badge
  - an auto-approved request
- **How to run and test:** `docker compose up --build`, pytest, the frontend build, and the eval command.
- **Assumptions:**
  - Office Supplies is Acme-owned.
  - The total is gross, and shipping and fees are lines.
  - The $2,000 boundary is strict and in USD.
  - "Small" subscriptions is defined by a threshold.
- **Limitations and next steps:**
  - an LLM judge for catalog matches
  - rule suggestions from user corrections
  - a larger eval set
- **Security findings outside scope.**
- **Data:**
  - The repository stays private: the fixtures name real vendors and tax IDs, and the quotes are customer documents.
  - Before anything is made public, sanitise the quotes and the answer key.
