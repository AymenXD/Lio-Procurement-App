# Commodity categories and groups

[Documentation index](README.md) · Reviewed 2026-11-04

A **category contains multiple commodity groups**. The request stores one group ID; its broader category comes from that group's row.

For example, the seeded taxonomy includes:

```text
Facility Management                 ← category
├── Electrical Engineering (11)     ← commodity group
├── Office Equipment (15)
└── other groups

Information Technology
├── IT Hardware (29)
└── other groups

Office & Administration
└── Office Supplies (2001)
```

The database has one `commodity_groups` table with `id`, `category` and `name`. There is no categories table or arbitrary-depth tree. The taxonomy is shared across tenants; Acme's rules, rather than its group definitions, are tenant-specific.

## Why change classification?

The merged extraction flow supplies all roughly 2,000 groups to one AI call. That makes the prompt large and mixes document interpretation with a long classification task.

The uncommitted implementation in [extraction.py](../backend/app/services/extraction.py) and [classification.py](../backend/app/services/classification.py) does this:

1. Read the distinct category names from the database.
2. Ask the extraction model to return the purchase details and **one of those roughly 22 category names**. Each category is listed with up to 8 of its group names as examples (variants reduced to their base name), e.g. `Production (e.g. Warehouse and Operational Equipment, Production Machinery, …)`. It chooses using the document's meaning; this remains a model prediction.
3. Apply the organisation's deterministic booking rules. If one supplies a valid group, use it and skip step 4.
4. Otherwise, send only the chosen category's groups, along with the extracted title, vendor and item descriptions, to a second AI call.
5. Accept a group only if its ID belongs to that offered category. Derive its name from the database.

For a laptop, the first call should select Information Technology; the second then chooses among its groups, including IT Hardware. For printer toner, Acme's booking rule directly selects IT Hardware, regardless of the model's proposed category.

## Failure behaviour

An unknown or missing category produces no candidate groups and no second call. A failed second call or an out-of-category ID leaves the commodity group missing so the user can choose it. The rest of the extracted fields are retained.

Category and group values are checked by application logic; the response schemas do not dynamically enumerate all allowed category names or group IDs. If the model copies the bracketed examples along with the category name, they are stripped before the lookup.

Each call logs its outcome, duration and token usage (`AI extraction …`, `AI classification …`), and the chosen category and group ID are logged too, so a wrong pick can be traced to the step that made it.

## Measured results

These are single runs of [the five-quote eval](extraction-eval.md) with gpt-4o-mini at temperature 0, measured 2026-11-04. Token counts are per upload.

| | Before: one call, 2,000 groups | A1: bare category names | **A2: categories + 8 examples (current)** |
| --- | --- | --- | --- |
| Prompt tokens, call 1 | 24,592–25,176 | 1,602–2,186 | 2,290–2,874 |
| Prompt tokens, call 2 | — | 955–1,084 | 955–1,084 |
| **Prompt tokens, total** | **~25k** | **~2.6–3.2k** | **~3.3–3.9k (about −85%)** |
| Duration, call 1 | 2.4–11.5 s | 2.7–4.9 s | 2.6–6.0 s |
| Duration, call 2 | — | 0.6–0.75 s | 0.6–0.9 s |
| Commodity correct | 3/5 | 2/5 | **4/5** |
| Eval score | 23/30 | 22/30 | **24/30** |

- **A1 → A2:** with bare names, the grinding machine went to *Facility Management*, because "Production" alone doesn't say "machinery", and the second call then correctly returned no group. Listing a few groups per category fixed this for about 700 tokens. The examples come from the data, not from the eval quotes.
- **Remaining miss (Apple MacBook):** the model picks a "Business Laptop" group (96 or a variant such as 1086) while the answer key expects 29. Both are in Information Technology, and the more specific group is defensible. The prompt was not tuned to this quote.
- Vendor/customer swaps, QT-4120's alternative row and Apple's eWaste fee are extraction misses, unchanged by this work.
- The smaller candidate lists reduce prompt size by construction; the exact token count depends on the document and selected category. The accuracy figures come from single runs and are indicative only; for example, Bloomcraft's group was null in the A1 run and correct in A2. These results were reported by the ongoing implementation work and were not rerun during the documentation review.

## Options considered

| Option | How | Why not chosen |
| --- | --- | --- |
| **A. Category, then group (chosen)** | Call 1 picks one of 22 categories; call 2 picks among that category's ~90 groups | — |
| B. Embedding shortlist | Embed the 2,000 groups once, embed the item lines, and send the top ~30 groups to the AI | Near-identical variant names could crowd the shortlist with one base product. This option adds embedding calls, a cache/index lifecycle and re-embedding when groups change; it does not inherently require a separate vector database. These are design concerns, not measured results for this option. |
| C. Prompt caching | Keep the 2,000 groups as a stable prefix and let OpenAI's prefix cache discount them | Already tried: putting the document after the list collapsed commodity accuracy to 0–2/5 ([evaluation](extraction-eval.md)). Caching also only discounts tokens; the prompt doesn't get shorter or faster on a cold cache. |
| D. No AI classification | The user always picks the group | This is the field users find hardest to fill in, so it is the most useful one to suggest. |

## Trade-offs

**Gains**

- About 85% fewer prompt tokens in the reported sample. Total billed cost also depends on output tokens and caching, so the same percentage cost reduction has not been established. Call 2 sees only the selected category's groups.
- Call 1 extracts fields and chooses a category; call 2 classifies a short summary. Commodity checks improved from 3/5 to 4/5 in these single runs; repeat the comparison before claiming a general accuracy gain.
- When a booking rule matches, only one AI call is made.
- Each step can be observed and tested separately: logs per call, and unit tests that check what each call sees.

**Costs**

- **A wrong category is not recoverable.** Call 2 never sees groups outside the chosen category. The result is either "missing" (safe) or the nearest wrong group in that category (less safe). The category examples reduce this risk but don't remove it.
- **An extra round trip** of about 0.6–0.9 s in the reported runs when no rule matches. The sampled call durations were below the old worst case; this is not a latency guarantee.
- **Two failure points.** Call 2 can time out or be rate-limited on its own. By design this only leaves the group empty; it never fails the upload.
- **No enum in the schema.** The category is checked in code, so the response schema stays static and easy to fake in tests. A misspelled category becomes "missing" instead of being prevented.
- **Less context in call 2.** It sees the title, vendor and item descriptions, not the document. That is enough for the eval quotes, but a quote listing only SKUs would classify worse.

## Possible follow-ups (not implemented)

- **Runner-up category:** call 1 also returns a second-choice category, and call 2 is offered both categories' groups (~180). This hedges the wrong-category risk for about 1k tokens.
- **Category enum:** build the schema per request with `Literal[...]` over the categories, so the API itself guarantees a valid name.
- **Learn from corrections:** record the group a user picks over a suggestion; frequent corrections become booking rules, which skip call 2 entirely.

See [the current plan](current-plan.md) and [evaluation](extraction-eval.md) for the remaining validation.
