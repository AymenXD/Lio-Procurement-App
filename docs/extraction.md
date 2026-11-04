# PDF extraction

[Documentation index](README.md) · Reviewed 2026-11-04

## What the customer is experiencing

An upload can fail, fields can be empty, or an apparently successful extraction can contain the wrong vendor or amounts. These are different problems and need different checks.

For example, the Greenmantle quote `QT-4120-Cust-14918.pdf` contains an alternative priced at $430 that should not be ordered. Earlier runs included it and sometimes read a heading as a second item. The correct ordered lines are $715.26, $622.00 and $215.00; with $133.88 tax, the total is $1,686.14. A valid JSON response can still get these facts wrong.

## Library versus AI

A PDF library is already used: [pypdf](../backend/app/services/pdf.py) extracts the text locally. It does not decide which company is the seller, whether a row is an alternative, or which commodity group applies. Those interpretation tasks are sent to AI.

The current flow is **PDF → plain text → AI → validation → user review**. AI is used for interpretation on every extraction, not only when the text is short. There is no OCR or image fallback. More extracted text does not necessarily mean the table relationships or image-only tax ID survived.

A library-first structured parser with AI fallback is a possible future design. It would need a reliable completeness check and support for the different vendor layouts; it has not been implemented here.

## Implemented in the merged baseline

1. `POST /pdf/parse` checks MIME type, the 10 MB limit and the PDF signature, then extracts each page's text.
2. `POST /extraction` sends that text to OpenAI with instructions to treat the document as data, using a Pydantic response schema.
3. Nullable AI values are converted to the form's empty defaults rather than crashing the upload.
4. A shared client has a 60-second timeout and one SDK retry. Timeout, rate-limit, refusal and other errors become readable messages.
5. Missing fields and arithmetic inconsistencies are returned for review. A vendor name equal to the customer name is flagged.
6. Tenant booking rules override the proposed commodity group. They are checked again when saving.

Structured output constrains the response shape, not factual correctness. The vendor/customer equality check does not catch two different names being swapped.

## Uncommitted experiments observed during review

- **Row kinds:** the model labels rows; the backend counts only `item`, `shipping` and `fee`. Non-counted rows with a non-zero price are returned as `skippedLines`. The inspected frontend does not display that field or offer an “add back” action.
- **Two-step classification:** extraction selects one category, then a separate call selects a group within it. Matching booking rules skip the second call. See [commodity classification](commodity-classification.md).
- These changes were under evaluation, not in the merged baseline. Source variants changed during this review. Earlier row-kind experiments reduced the five-quote score; new classification results report fewer prompt tokens and 24/30 on one combined variant. See [evaluation](extraction-eval.md) for the distinct baselines and limits of that evidence.

## Remaining limits

- Plain text loses layout. A heading and a priced row may be associated incorrectly.
- An image-only tax ID cannot be recovered from plain text.
- Reconciliation detects inconsistent amounts, but cannot prove the vendor or every row is correct. A fee incorrectly folded into tax may still balance.
- Warnings do not block submission or auto-approval. Saving recomputes totals from the reviewed lines and tax, not from the printed quote total.
- There is no combined PDF-and-extraction endpoint, automatic self-correction, vision fallback or persisted line-kind column.

The rejected self-correction and layout experiments are recorded in [the evaluation history](extraction-eval.md).

## Code and evidence

| Concern | Source |
| --- | --- |
| Upload validation and local text extraction | [router](../backend/app/routers/pdf.py), [PDF service](../backend/app/services/pdf.py) |
| AI interpretation and missing-field checks | [extraction service](../backend/app/services/extraction.py), [schemas](../backend/app/schemas/extraction.py) |
| Shared AI client | [ai.py](../backend/app/services/ai.py) |
| Arithmetic warnings | [reconciliation.py](../backend/app/services/reconciliation.py) |
| Unit tests | [extraction tests](../backend/tests/test_extraction.py), [reconciliation tests](../backend/tests/test_reconciliation.py) |
| Five-quote answer key | [quotes_expected.json](../backend/tests/fixtures/quotes_expected.json) |

See [verification](verification.md) for offline checks and [extraction evaluation](extraction-eval.md) for the separate live API run.
