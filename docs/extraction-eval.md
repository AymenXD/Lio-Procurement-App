# Extraction evaluation

[Documentation index](README.md) · Reviewed 2026-11-04

This manual evaluation scores extraction against Acme's five supplied quotes. It measures model behaviour; passing unit tests does not establish extraction accuracy. The results below are reported development runs, not runs performed as part of the documentation cleanup.

## Run separately from CI

Start with a migrated, seeded application database and a configured OpenAI key. From the workspace root:

```bash
cd lio-procurement-app
docker compose run --rm -v ./backend:/app -v ../quotes:/quotes:ro backend \
  python -m scripts.eval_extraction /quotes
```

- **Answer key:** [quotes_expected.json](../backend/tests/fixtures/quotes_expected.json), recorded as checked by hand against the PDFs.
- **Script:** [eval_extraction.py](../backend/scripts/eval_extraction.py). It uses the current local backend files and makes real, billable OpenAI calls; it is not part of pytest or CI.

The script prints failed extracted values as well as the score; review that output before sharing it. It calls the extraction service without an organisation ID, so it does not evaluate Acme's tenant booking rules, browser uploads, catalog selection or saved-request approval.

## Scoring and limits

**6 checks per quote (5 quotes = 30 points):**

| Check | Passes when |
|---|---|
| OK | extraction didn't fail |
| Vendor | name matches (case and punctuation ignored) |
| Tax ID | digits match |
| Lines | the line amounts equal the expected list (any order, ±$0.01). Shipping and fees count; alternatives and headings must not appear. |
| Total | the grand total matches |
| Commodity | the group is the expected one |

The tax value in the fixture is not independently scored. The line check compares totals, not descriptions, quantities or units independently. A score of 26/30 is 26 successful field-level checks on this small set, not a production accuracy estimate.

## Historical baseline results

| Check | Baseline | 1.1 no crash on `null` | 1.2 new prompt | 1.3 strict schema |
|---|---|---|---|---|
| OK | 3 | 5 | 5 | 5 |
| Vendor | 0 | 1 | 3 | 3 |
| Tax ID | 3 | 4 | 4 | 4 |
| Lines | 0 | 1 | 4 | 4 |
| Total | 2 | 4 | 5 | 5 |
| Commodity | 3 | 5 | 5 | 5 |
| **Score** | **11** | **20** | **26** | **25–26** |

The strict-schema column shows a representative 26-point result; repeated runs also scored 25. These earlier notes do not contain a complete revision/model/run record.

## Two-step commodity classification

These runs came after the row-label work, which is why the "before" score here is 23 rather than 25–26. The design and trade-offs are in [commodity-classification.md](commodity-classification.md).

| | Before: one call, 2,000 groups | A1: bare category names | A2: categories + 8 examples (current) |
|---|---|---|---|
| Prompt tokens per upload | ~25k | ~2.6–3.2k | ~3.3–3.9k |
| Commodity | 3 | 2 | 4 |
| **Score** | **23** | **22** | **24** |

The eval script now prints each AI call's outcome, duration and token usage, plus the chosen category and group.

These are single reported runs of different prompt variants. The 23-point comparison baseline already includes row-label work, so 24/30 is not an improvement over the earlier 25–26/30 baseline. Prompt-token counts do not by themselves establish total billed cost or end-to-end latency. See [classification](commodity-classification.md) for per-call measurements and remaining misses.

## Historical experiments

Reverted experiments and row-label work are listed separately from the merged feature baseline. “Present in the working tree” is not the same as “validated improvement”; files were being switched during evaluation while these docs were reviewed.

| Experiment | Score | What we learned |
|---|---|---|
| Document placed after the commodity list (for caching) | 21–23 | Classification collapsed (commodity 0–2/5), so we moved the document back |
| Old prompt with its example values removed | 20 | Commodity still 5/5, so the old score wasn't the model copying an example |
| Layout text mode | 24–25 | No net gain: fixed Hollis's vendor, broke Apple's. Reverted. |
| Self-correction: one retry with the problems found (gpt-4o-mini). **Reverted.** | 25–26 (before: 25) | QT-4120: the retry dropped the $430 alternative but kept the heading as "qty 2", so it was still wrong and correctly rejected (2 of 2 runs). Hollis and Bloomcraft: the AI *swapped* vendor and customer, so the vendor = customer check never triggered. |
| Self-correction plus a "the lines are $X too high" hint | QT-4120 only | Worse: the AI invented two lines (115.34, 18.54) to close the gap. The "fewer problems" rule rejected it. Hint reverted. |
| Row labels (Idea 1): the AI labels every row (item, shipping, fee, alternative, optional, subtotal, heading) and our code counts item, shipping and fee | 19, 19 | Tax rows were listed as lines on every quote ("list every row" beat "tax is not a row"). Commodity fell to Promotional Materials on the 3 moss quotes. QT-4120's qty was right (715.26), but $430 was still counted. |
| Row labels plus a "tax" label | 22 | Tax rows are left out. On QT-4120 the AI labelled the *heading* "Alternative: vertical logo" as the alternative and the priced $430 row as an item, because "(Alt.)" sits on a different text line. The qty bug came back on this run (1,430.52). Commodity is still wrong on the 3 moss quotes. |

## Record the next run

Record the date, commit plus uncommitted changes, model, variant, per-quote results and failed values. Include token usage, timings and call counts when comparing classification approaches. Keep the answer key stable unless inspecting the PDF justifies a correction; record any such change separately.

Compare one change at a time on the same five PDFs, and repeat promising results to check consistency. The next priorities are in [the current plan](current-plan.md); offline checks are in [verification](verification.md).
