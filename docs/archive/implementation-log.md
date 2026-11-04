# Archived implementation log

Archived on 2026-11-04. Entries describe the code and test results at the time they were written. Some experiments were reverted, and older "in progress" labels are stale. Counts and model scores are historical observations, not verification of today's checkout. Start with [the documentation index](../README.md) for current behaviour.

---

# Issues log

What we fixed, why it was broken, and how we know the fix works.
Scores come from the extraction eval (`extraction-eval.md`).

---

# Issue 1: PDF extraction isn't reliable

> Acme: *"Fields come out incorrect or empty, and sometimes the upload errors out completely."*

**Eval score: 11 → 26 / 30** (5 quotes × 6 checks).

## 1.1 A missing value crashed the whole upload
- **Problem:** 2 of 5 quotes failed completely.
- **Cause:** these quotes print no readable tax ID, so the AI correctly returned `null`. Our schema only accepted text, so it rejected the whole result.
- **Fix:** `null` values are dropped before validation, so the field falls back to empty (`""` or `0`) and is shown to the user as a *missing field*.
- **Where:** `schemas/extraction.py` (`_drop_nulls`).
- **Result:** no more crashes. **11 → 20 / 30.**
- **Trade-off:** a price the AI can't read shows as `0`, not "missing". The alternative (all fields nullable end to end) would also touch the frontend.

## 1.2 The AI didn't understand quotes
- **Problem:** the vendor was the *customer* on 4 of 5 quotes. Alternative items were counted as lines, so Hollis's total came out as 4,020 instead of 2,042.15. Shipping and fees were dropped.
- **Cause:** the prompt was vague.
  - It defined the vendor as "Company name".
  - It said "extract ALL line items".
  - It never defined the total.
  - It contained example values the model could copy.
- **Fix:** we rewrote the prompt around **concepts, not labels**, so it works on layouts we've never seen.
  - **Vendor** = the company that issued the quote and sells. The AI also names the recipient, and if the two are the same, our code flags the vendor.
  - **Lines:** a line counts only if its amount is part of the quote's total. Headings, alternatives, subtotals, spec bullets and upsells are skipped. Shipping and fees are lines; tax has its own field.
  - **Total** = the grand total printed on the quote.
  - **Safety:** the document text is wrapped in `<document>` tags and treated as data. No example values.
- **Where:** `services/extraction.py` (prompt, `_same_company`), `schemas/extraction.py` (`customer_name`, `tax_amount`).
- **Result:** vendor 1→3, lines 1→4, total 4→5. **20 → 26 / 30.**
- **Lesson learned:**
  - We first placed the document *after* the 25k-token commodity list, so OpenAI could cache the prompt. The eval showed classification collapsing (commodity 5/5 → 0/5).
  - An experiment proved the reorder was the cause, so we moved the document back. **Accuracy beats cost.**

## 1.3 Free-form AI replies could break the upload
- **Problem:** the AI's reply was free text that we parsed by hand. Broken JSON, a missing key or a price like `"$1,409.06"` failed the upload.
- **Cause:** nothing enforced the reply's shape. The prompt only *asked* for JSON.
- **Fix:** **OpenAI Structured Outputs.** We pass a Pydantic model (`QuoteExtraction`), and OpenAI guarantees the reply matches it: every key present, numbers as numbers. Temperature is now 0 (was 0.3), and a refusal returns a clean error.
- **Where:** `schemas/extraction.py` (`QuoteExtraction`), `services/extraction.py`.
- **Result:** same accuracy (**25–26 / 30**), but a malformed reply can no longer crash an upload, and runs vary by only 1 point.
- **Trade-off:** amounts are still `float`; `Decimal` comes with server-side totals (Bonus).

## 1.4 Wrong numbers passed silently
- **Problem:** when the AI got a number wrong, nobody noticed. Greenmantle's lines added up to 2,831.40 while the quote says 1,686.14, and the form showed no hint.
- **Cause:** nothing compared the extracted numbers with each other.
- **Fix:** small pure functions (no AI) check two things, using exact `Decimal` money and a 1-cent tolerance for rounding:
  - each line: quantity × unit price = line total
  - all lines + tax = the grand total

  A mismatch becomes a **warning** in the form's yellow box ("⚠️ Please check: …"). It never fails the upload; the user decides.
- **Where:** new `services/reconciliation.py`, the `warnings` field in `schemas/extraction.py`, the call in `services/extraction.py`, and the display in `new-request/page.tsx`.
- **Result:**
  - On the real quotes, **only Greenmantle (the wrong one) gets a warning**; the 4 correct quotes get none.
  - Bonus: the total check also catches the known limit of 1.1. An unreadable price shows as 0, so the lines no longer add up.
  - The eval score is unchanged, because warnings aren't scored.
- **Trade-off:** some real quotes don't add up on purpose (lump sums, per-pack prices), which is why it's a warning, not an error.

## 1.5 Uploads could hang or show technical errors
- **Problem:**
  - A slow AI call could hang for up to 10 minutes (the SDK default timeout).
  - Raw technical errors reached the user (e.g. `1 validation error for…`).
  - The PDF check trusted the browser, so a renamed non-PDF file got through.
- **Fix:**
  - **One shared OpenAI client** with a **60 s timeout** and **1 automatic retry** on rate limits, server and connection errors. These are built-in SDK options, so no new code or library.
  - **Readable errors:** timeout → "The AI took too long…", rate limit → "The AI service is busy…", anything else → "Extraction failed…". Only the error *type* goes to the server log, because messages can echo extracted values.
  - **Logging** of duration, tokens and outcome for every AI call. Never the document text or the key.
  - **PDF signature check:** the file must start with `%PDF-`.
- **Where:** `services/extraction.py` (`_client`, `_log_call`, error messages), `routers/pdf.py`, `main.py` (one `logging.basicConfig` line, so the app's INFO logs show in `docker compose logs`).
- **Result:**
  - All 23 tests pass (new: timeout → clean message, unexpected errors don't leak details, fake PDF rejected).
  - Eval 25 / 30 (within the usual 25–26).
  - Measured: ~25,000 prompt tokens and 2–7 s per extraction.
- **Not done (on purpose):** merging `/pdf/parse` and `/extraction` into one endpoint, since it changes the API for little gain.
- **Found, outside scope:** the request attachment upload (`routers/requests.py`) has the same browser-only file type check. It goes in the PR's security findings.

### The OpenAI client settings, explained
`OpenAI(api_key=..., timeout=60, max_retries=1)` in `_client()`, decorated with `@cache`:
- **Shared (`@cache`):** the client is created once and reused, instead of a new connection setup on every upload.
- **`timeout=60`:** stop waiting after 60 s. The default is 10 minutes, and a normal call takes 2–7 s.
- **`max_retries=1`:** temporary errors (429 overloaded, 5xx hiccup, dropped connection) are retried once by the SDK itself. Only once, so the worst-case wait stays short.
- No new library or retry loop: these are standard `openai` options.

### Logging: what we log and how to read it
- **Before:** the app never configured Python logging, so our own log lines were invisible. Only uvicorn's request lines (`"POST /extraction" 200 OK`) appeared.
- **Now:**
  - One line in `main.py`: `logging.basicConfig(level=logging.INFO)`.
  - Each AI call logs one line:
    ```
    INFO app.services.extraction: AI extraction outcome=ok duration_ms=2180 prompt_tokens=24882 completion_tokens=153
    ```
  - `outcome` is `ok`, `refused`, `timeout`, `rate_limited` or `error:<ErrorType>`.
- **Never logged:** document text, prompts, extracted values, the API key.
- **How to watch:** `docker compose logs -f backend`, then upload a quote.

## 1.6 The upload form didn't guide the user
- **Problems → fixes** (all in `new-request/page.tsx`, no new components or libraries):
  - **No size check in the browser** → files over 10 MB are refused instantly, before uploading.
  - **Re-selecting the same file did nothing after an error** → the file input is reset after every attempt.
  - **Missing fields were only listed in one sentence** → each flagged field gets a red border and "Not found or unclear on the quote". It clears as soon as the user edits that field. This uses the existing `Input` `error` prop.
  - **A broken file was still attached** → the file is kept only once `/pdf/parse` accepts it as a valid PDF.
  - **Submit could be clicked twice (duplicate requests)** → the button is disabled while saving ("Creating…").
  - **Requestor Name was always empty**, because the requestor isn't on the vendor's quote → it's prefilled from the logged-in user's profile (`api.auth.me()` → `full_name`), only if still empty, and stays editable.
  - **Department was flagged on almost every quote** (quotes rarely print it), and an admin can make it *required*, which blocks submission. Fix: **profile department first, the quote's as fallback**, highlighted only if both are empty.
    - Why the profile wins: the department belongs to the person ordering; a quote's "Attn:" line is just where the vendor sent it.
    - Frontend: `new-request/page.tsx`, plus the missing `department` field on the `Profile` type in `types/database.ts` (the backend already sent it).
    - Demo data: `seed.py` gives `requester@acme.com` the department "Facilities". It's idempotent and also fills existing databases. Other accounts stay empty, so the demo shows both cases.
- **Decisions:**
  - **Attachment differs from PLAN.md** ("attach only after successful extraction"). If only the AI step fails, the PDF stays attached, because the user fills the form by hand and the quote is still the right source document. Only invalid PDFs are dropped.
  - **Number warnings stay in the yellow box**, not next to each field (that would mean matching messages to fields: more code, little gain).
  - The highlight clears when the field is *edited*, not when it's non-empty. That way a vendor flagged as "same as customer" (filled but wrong) stays highlighted until the user touches it.
- **Verified:** type check and build pass; app rebuilt. Manual test steps:
  - a file over 10 MB
  - the same file twice after an error
  - Hartwell → Tax ID highlighted
  - double-click Create Request

## Tried and rejected
- **Layout text mode** (pypdf `extraction_mode="layout"`), meant to keep the on-page reading order. It fixed the Hollis vendor but broke Apple's (side-by-side address columns got merged). There was no net gain (24–25 / 30), so we **reverted** and kept the simpler code.

## Still open
- **Vendor on Verdeform and Hollis:** the customer is still picked.
- **Greenmantle lines:** the alternative item (430.00) is included. The user is now **warned** (1.4).
- **Verdeform tax ID** (`QT-OF2312380-Cust-57692.pdf`): confirmed **not in the text layer** (plain or layout); it's printed only inside the page image.
  - **Not done:** 1 optional field on 1 quote, and the user already sees it highlighted.
  - **With more time:** a vision fallback. If key fields are missing after text extraction, send the PDF to OpenAI as a file input (text + page images) for just those fields. No new library, but a second, pricier call, so only when needed.

---

# Issue 2: Negotiated prices aren't used

> Acme: *"When someone creates a request, suggest the matching articles we already have on catalog."*

Full explanation of the feature, how it works and its trade-offs: **`catalog-suggestions.md`**.

## 2.1 Matching endpoint (in progress)
- **Problem:** the catalog (1,920 articles with negotiated prices) was only a list. Search was substring-only, so "MacBook Air" found nothing, and the request form never looked at the catalog.
- **Done:**
  - `POST /articles/suggestions`, matching by meaning (OpenAI embeddings, catalog cached in memory, org-scoped).
  - The shared OpenAI client moved to `services/ai.py`.
  - 6 new tests; all 29 pass.
- **Finding:** embeddings alone can't separate good from bad matches. MacBook → laptop scores 0.42, while acrylic logo → desk organizer scores 0.57. Same articles from several suppliers also show up as duplicates.
- **Experiment: category filter.** Only articles whose supplier is in the request's commodity category, each description once (cheapest supplier), minimum 0.40 and within 0.10 of the best. Result: **9 of 11 lines right** (was ~4). The 2 misses have no real match in the catalog. Details in `catalog-suggestions.md`.
- **Implemented: the category filter.**
  - `POST /articles/suggestions` takes an optional `commodity_group_id`.
  - Only articles whose supplier is in that group's category are compared.
  - Each description is kept once (cheapest supplier) by `cheapest_per_description`.
  - A match must be ≥ 0.40 and within 0.10 of the line's best.
  - No extra AI call. The real data reproduces the experiment (9 of 11 lines right).
- **Verified:** 9 matching tests (category filter, dedupe, both thresholds, cache, no key, API failure); all 32 pass. Backend rebuilt.
- **The 2 misses, checked:** the catalog has no grinding machine and no acrylic logo, so the nearest item is shown anyway.
- **Price sanity check (implemented):** suggestions priced more than 10× away from the quoted price are hidden (`price_is_plausible`; 2 new tests, all 34 pass).
  - Result: **10 of 11 lines right**. The grinding machine is fixed.
  - The acrylic logo now gets the moss panel with company logo: plausible price, related, but not a true replacement. No extra rule for one line; the UI wording covers it.
- **Note for the UI (2.2):** the price difference is only meaningful when the units match (moss panel *per piece* vs moss wall *per sq ft*), so the UI must show both units.

## 2.2 Show suggestions in the request form
- **What the user sees:** under each order line with a match, a box "💡 Similar catalog item with a negotiated price. Check it fits." It shows description · supplier · price / unit, and:
  - green "$X cheaper per unit than quoted", or grey "$X more"
  - "Different unit (per sq ft vs per piece), so not comparable" when units differ ("piece" = "pieces")
- **When it loads:**
  - automatically after a PDF is extracted
  - when the commodity group changes (the filter depends on it)
  - with a **"Check catalog prices"** button, for typed or edited lines (no reload on every keystroke)

  Adding or removing a line clears the suggestions, because their positions would no longer match.
- **"Start request with this article ↗":** opens a **new tab** with a request prefilled with the catalog supplier, description, negotiated price, unit, quantity and commodity group. The current request stays with the quoted vendor, because the negotiated price belongs to another supplier.
- **Where:**
  - `lib/api/index.ts` (`articles.suggest`, `ArticleSuggestion`)
  - new `components/CatalogSuggestions.tsx` (display + `sameUnit`)
  - `new-request/page.tsx` (state, loading, button, prefill from URL)
- **Verified:**
  - type check and build pass; app rebuilt
  - over HTTP as `requester@acme.com`: MacBook → Business laptop 13" (Delmar Systems, $1,438, $28.94 more); shipping → nothing; the prefill URL loads
- **Trade-offs:** suggestions don't update while typing (button); the new-tab flow means two separate requests; the unit check is basic ("pcs" ≠ "pieces").

## 2.2b Polish: unit synonyms and a friendlier suggestion box
- **Problem 1:** "Different unit (per piece vs per ea.)". The unit check only lowercased and stripped a trailing "s", so "ea." ≠ "piece".
  - **Fix:** a small synonym table in `sameUnit()` maps each variant to one unit:
    - piece = ea, each, pc(s), unit(s), item(s)
    - sq ft = sqft, ft², square feet
    - also lin ft, license (seat), month, year, hour, day
  - Unknown units still show "not directly comparable", the safe default.
- **Problem 2:** the suggestion box was a plain text list with link-style buttons.
  - **Fix (UI only):**
    - The best match is shown first; the others sit behind "+ N more options".
    - A green pill "Save $X / unit · $Y on this line" (difference × line quantity), or a grey "$X more / unit".
    - The price is prominent; the supplier is secondary text.
    - A real "Start request ↗" button.
    - A ✕ to hide the box for that line (it comes back on the next "Check catalog prices").
- **Where:** `components/CatalogSuggestions.tsx`; `new-request/page.tsx` passes the line quantity.
- **Verified:** type check and build pass; frontend rebuilt.
- **Trade-off:** the synonym table is hand-written. A unit it doesn't know is reported as "not comparable" rather than guessed.

## 2.3 Record catalog usage (link order lines to articles)
- **Problem:** nothing recorded that a line used a catalog article, so Acme couldn't measure negotiated-price usage or savings. And any price typed in the browser could be called "negotiated".
- **Fix:**
  - **Migration `0007`:** `order_lines.article_id` (nullable FK to `articles`, `ON DELETE SET NULL`, indexed) and `quoted_unit_price` (the price on the original quote). It has a working `downgrade()`.
  - **The server trusts the catalog, not the browser:** on create *and* update, a line with `articleId` must belong to the caller's organisation (otherwise **404**). It gets its **unit price and unit from the catalog**, and its total is recalculated (`Decimal`). This is `_build_order_lines` in `routers/requests.py`.
  - **Activity log:** "Line 1 uses catalog article HAR-00172 at the negotiated $44.59 / sq ft (quoted $52.00)". On edit, only newly linked articles are logged.
  - **Frontend:**
    - "Start request ↗" passes the article id and the quoted price.
    - A catalog line's price and unit are read-only ("Negotiated catalog price").
    - The request edit page keeps the link when it re-saves lines.
- **Where:**
  - `alembic/versions/0007_order_line_catalog_link.py`
  - `models/procurement_request.py`, `schemas/requests.py`, `routers/requests.py`
  - `new-request/page.tsx`, `requests/[id]/page.tsx`, `lib/api/index.ts`, `types/database.ts`
- **Verified:**
  - 2 new tests: a faked browser price is replaced by the catalog price, and another tenant's article returns 404. All 36 pass.
  - Migration upgrade → downgrade → upgrade on Postgres.
  - End to end on the running app: the browser sent $1.00 / "x", the server stored $44.59 / sq ft with total 614.45 and the activity entry. The test request was deleted afterwards.
- **Trade-offs:**
  - Only catalog lines get a server-computed price. Other lines still trust the browser until the Bonus (server-side totals).
  - The request detail page doesn't show a "catalog article" badge yet.

---

# Finding: Greenmantle quote (QT-4120) shows "Lines + tax = 2,831.40, but the quote total is 1,686.14"
- **Checked:** the number check is **correct**. The extraction is wrong for this quote:
  - **Moss Art Panel came back as qty 2 × 715.26.** In the PDF text, item 1 is a heading with the same name as item 2, and the AI merged them.
  - **The "vertical logo" alternative (430.00) was kept.** Its "(Alt.)" marker is printed on the line *below* it.
  - The tax (133.88) and the total (1,686.14) were extracted correctly.
- **So the warning is a true positive:** the check caught a real extraction error.
- **Proposed fix: self-correction.** It was tried and reverted, since it showed no measured gain (see "Tried and reverted: extraction self-correction" below). The warning remains the safety net.

---

# Issue 3: The categorisation doesn't match how Acme books things

> Acme: *"Cable ties → Electrical Engineering, printer toner → IT Hardware, small software subscriptions → Office Supplies. Non-negotiable."*

Full explanation, examples and trade-offs: `booking-rules.md`.

- **Problem:**
  - The AI picks freely among 2,000 groups, and the user can pick anything. Toner naturally lands in "Toner Cartridges".
  - "Office Supplies" didn't exist.
  - Saving organisation settings replaced the whole object, so any stored rules would have been wiped.
- **Fix:** booking rules as **tenant configuration**, enforced by the **server**.
  - **Rules** live in the organisation's settings (`booking_rules`: name, keywords, target group, optional max total). Only admins can change them, in Organization › Settings › **Booking Rules** (add, edit, delete).
  - **Saving settings merges** instead of replacing, and unknown target groups are rejected (422).
  - **The rule engine** (`services/booking_rules.py`, pure functions):
    - whole-word, case-insensitive keyword match (plurals allowed)
    - the rule whose matching lines carry the most value wins; ties go to the first rule listed
    - a rule with `max_total` applies only below that request total
    - a rule decides only if its lines are **≥ 50% of the request value** (`MIN_VALUE_SHARE`), so $20 of cable ties don't re-book a $5,000 moss wall
  - **Enforced on create and update:** the rule overrides the browser's group, and the total comes from the stored lines. Activity entry: "Booked to Hardware by the rule 'Printer toner' (was Toner Cartridges)".
  - **Also applied:** in the extraction (`appliedRule`), and in a preview endpoint (`POST /requests/booking-rule-preview`) used while typing lines.
  - **Form:** the commodity field is locked with "🔒 Booked to Hardware by the rule “Printer toner”". A **searchable commodity picker** replaces the 2,000-option dropdown, in the request form, the edit page and the rule form.
  - **Seed:**
    - the global group **2001 "Office & Administration › Office Supplies"** (in the category Acme meant, under the name they used)
    - Acme's 3 rules, seeded **only if Acme has none yet**, so admin edits survive restarts
- **Decisions and assumptions:**
  - **"Small" = request total below $2,000,** Acme's own limit for "doesn't need approval". It's editable per rule.
  - **Starting keywords:**
    - cable tie / zip tie → Electrical Engineering (11)
    - toner → Hardware (29)
    - subscription / saas / software license → Office Supplies (2001), below $2,000
  - **Office Supplies is a global group:** the taxonomy was missing it, and only the *rule* is Acme-specific.
  - **Users can't override a rule.** Changing a rule applies to new and edited requests, not past ones.
  - Keyword matching is simple: "toner" would also match "skin toner".
- **Where:**
  - backend: `schemas/organizations.py`, `routers/organizations.py`, `services/booking_rules.py` (new), `routers/requests.py`, `services/extraction.py`, `routers/extraction.py`, `schemas/extraction.py`, `schemas/requests.py`, `seed.py`
  - frontend: `components/BookingRulesCard.tsx` (new), `components/CommodityGroupPicker.tsx` (new), `organization/page.tsx`, `new-request/page.tsx`, `requests/[id]/page.tsx`, `lib/api/index.ts`
- **Verified:**
  - 6 rule-engine tests and 3 API tests (override on create and update, preview, other tenants unaffected, settings merge, unknown group 422). All 45 pass.
  - The app is rebuilt, and the seed added the group and the rules to the existing database.
  - End to end:
    - cable ties → Electrical Engineering
    - a $960 Slack subscription → Office Supplies
    - a $24,000 Salesforce subscription → no rule
    - Walmart → no rule
    - toner saved as "Toner Cartridges" → stored as Hardware, with the activity entry

    The test request was deleted afterwards.

## 3.1 Polish: a friendlier Booking Rules card
- **Problem:** the card was a plain table: keywords typed as a comma list, a bare number field for the limit, a browser popup to delete, the edit form at the bottom, and no way to try a rule.
- **Fix (only `components/BookingRulesCard.tsx`; no backend change, no new library):**
  - each rule reads like a sentence: "If a line mentions [toner] / Book it to **Hardware** · IT Hardware", with an "Only under $2,000" pill
  - keywords are chips (Enter or comma adds one, × removes it)
  - the limit is a checkbox, "Only for small requests", that reveals a $ field
  - a live summary shows what the rule will do before saving
  - edit opens in place, and delete asks inline ("Delete this rule? Delete / Keep")
  - a **"Test your rules"** box: type an item and an optional total to see where it would be booked. It uses the existing preview endpoint and the saved rules.
  - a friendly empty state
  - the "+ Add rule" button no longer wraps onto two lines
  - a "How matching works" note was tried and removed at the user's request (the card should stay short)
- **Wording:** no "→" in user-facing texts, on the user's request. The badge and the activity entry now read "Booked to X by the rule 'Y'" (`new-request/page.tsx`, `routers/requests.py`).
- **Testing with the 5 quotes:** none of them mention toner, cable ties or software (checked by searching their text), so no rule fires on them. That proves no false positives. To see a rule fire on a real quote, add a temporary rule (e.g. `macbook` → Software) and upload the MacBook quote.
- **Verified:** all 45 tests pass, and the frontend builds with the type check after the rebuild.

# Bonus: buyers approve every request

Full explanation, examples and trade-offs: `auto-approval.md`.

> Acme: *"Anything below $2,000 shouldn't need approval at all."*

- **Problem:**
  - Every request waited for a buyer, even a $50 one.
  - **The total came from the browser** and was stored as sent (the edit page had a free "Total Cost" field), so a limit on it would be easy to cheat.
  - **Tax wasn't stored,** so the total meant different things: Hollis is $1,880 before tax and $2,042.15 with it.
  - **Editing an approved request kept it approved,** so an approved $1,500 request could become $50,000.
- **Fix:**
  - **The server computes the money:** line = quantity × unit price, total = lines + tax (`services/totals.py`, `Decimal`). Browser totals are ignored, and negative prices or tax are refused.
  - **The policy is a setting:** `auto_approval = {enabled, below_amount}`, off by default, on for Acme at $2,000 through the seed. Admins edit it in Organization › Settings.
  - **On create:** under the limit means approved, with `approval_source = auto`, no approver, and a log entry.
  - **On edit:** a vendor, tax ID, lines or tax change sends an approved request back to pending (logged), then the auto check runs again. Title, department and requestor edits keep the approval.
  - **Buyer decisions** are marked `approval_source = manual`.
  - **Migration 0008:** `tax_amount` and `approval_source`, with older decided requests backfilled to `manual`.
  - **UI:**
    - a Tax field, with a read-only "Order lines + Tax = Total"
    - a hint in the form ("✓ Under $2,000: this request will be approved automatically")
    - an "Auto-approved" badge in the list, on the detail page and on Approvals
    - an Auto-approval settings card
    - an amber note when editing an approved request
- **Also fixed:** activity entries from one save shared Postgres's transaction timestamp, so their order was random. Each entry is now stamped when it's written.
- **Decisions:**
  - **Strictly "under":** $2,000.00 exactly needs a buyer.
  - **Gross total, including tax.**
  - **No currency check:** requests have no currency, and all of Acme's data is in USD.
  - **Simplified from PLAN.md:** no "line kind" column, because shipping and fees are already normal lines.
- **Trade-offs:**
  - The total is only as honest as the lines; the quote PDF and the activity log allow an audit.
  - Order splitting isn't detected.
  - The server's rounding can differ by a cent from a printed line.
  - Older requests may be sent back to pending once on their first edit.
- **Where:**
  - backend: `services/totals.py` (new), `services/approval_policy.py` (new), `schemas/organizations.py`, `schemas/requests.py`, `models/procurement_request.py`, `routers/requests.py`, `alembic/versions/0008_request_tax_and_approval_source.py` (new), `seed.py`
  - frontend: `components/AutoApprovalCard.tsx` (new), `organization/page.tsx`, `new-request/page.tsx`, `requests/[id]/page.tsx`, `requests/page.tsx`, `approvals/page.tsx`, `lib/api/index.ts`, `types/database.ts`
- **Verified:**
  - **Tests:** 5 unit tests and 6 API tests: $1,999.99 auto-approved with no approver, $2,000 pending, browser total ignored, negative price refused, Walmart unaffected, re-approval after a price change but not after a title change, re-check after an edit. 2 existing tests adjusted (the default settings shape; the activity test raised above $2,000 so a buyer still decides). **All 56 pass.**
  - **Migration 0008:** upgrade, downgrade and upgrade on Postgres, with the backfill checked.
  - **Running app:**
    - Apple ($1,534.59) is auto-approved, with "Auto-approved…" logged after "Request created"
    - Hollis ($2,042.15) stays pending

    The test requests were deleted afterwards.
  - Frontend build and type check pass after the rebuild.

# Tried and reverted: extraction self-correction (branch `fix/optimization`)
Follows the QT-4120 finding above.

- **Idea:** when our own checks find a problem, ask the AI once more in the same conversation with its answer and the exact problem. The problems are numbers that don't add up, or vendor = customer. The second answer is kept **only if it has fewer problems**, otherwise the first one and its warning stay.
- **Code:** `services/extraction.py` (`_problems`, `_self_correct`, `RETRY_PROMPT`), plus 5 tests with a fake AI: fixed on retry, not better so kept, retry error so kept, no retry when fine, vendor corrected. All 61 pass.
- **Measured on the real quotes (eval: 25 before; 26 and 25 after):**
  - **QT-4120:** the retry removed the $430 alternative but kept the heading as qty 2. Still wrong, so rejected (2 of 2 runs).
  - **Hollis and Bloomcraft:** the AI swaps vendor and customer, so vendor = customer is never detected and no retry happens.
  - **Apple:** sometimes the $4 eWaste fee is folded into the tax (121.53 + 4 = 125.53). Lines + tax then still match the total, so no check can see the error.
- **Tried and reverted:** telling the AI the size of the gap. It invented two lines to close it, and the guard rejected them.
- **Takeaway:** the guard works, since a worse answer is never used, but gpt-4o-mini can't fix QT-4120 from the text alone.
- **Decision: reverted.** There was no measured gain on the 5 quotes, so it isn't worth an extra AI call and more code. The code is back to the merged version, and the 56 tests pass. The number warning stays the safety net: it tells the user QT-4120 doesn't add up.
- **Options not tried** (for the PR's "with more time"):
  - a stronger model only for the retry (gpt-4o, about $0.03 per retry)
  - reading the PDF as an image (vision), so headings and "(Alt.)" markers keep their layout
  - a tenant setting with the buyer's own company names, to catch a vendor/customer swap

# Experiment: row labels (Idea 1, branch `fix/optimization`)
- **Idea:** the AI labels every row of the price table (item, shipping, fee, alternative, optional, subtotal, heading, then tax), and **our code** counts only item, shipping and fee. Priced rows left out would be shown to the user ("add back").
- **Code (experimental):** `RowKind` and `kind` on `QuoteLine`, `SkippedLineData`, `ExtractionResponse.skipped_lines` in `schemas/extraction.py`; `COUNTED_KINDS` and `_split_rows` plus the prompt's orderLines section in `services/extraction.py`. 1 new test, 57 pass.
- **Measured (eval, 25 before):**
  - 19 and 19 with the first labels: tax rows were counted as lines everywhere, and commodity fell on 3 quotes
  - 22 with a "tax" label: tax was fixed, but commodity still fell on 3 quotes
- **Why it doesn't fix QT-4120:** the AI labels the *heading* "Alternative: vertical logo" as the alternative and the priced row under it as an item. In plain text, "(Alt.)" is on a separate line from the row it marks. The qty error comes and goes between runs.
- **Takeaway:** labels don't bring back the lost table layout, which is the root cause. They also changed the commodity classification.
