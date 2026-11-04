# Start here

Reviewed against the code on **2026-11-04**. This is the entry point for the assignment documentation.

## The assignment in one minute

Acme needs employees to turn supplier quotes into purchase requests, use negotiated catalog prices where appropriate, and book purchases to the correct commodity group. The optional fourth feature lets small requests skip buyer approval.

The application already has users, organisations and roles. We are extending that system.

| Customer need | Implementation status | Explanation |
| --- | --- | --- |
| Reliable PDF extraction | Error handling, structured output and number warnings are implemented. Some quotes still extract incorrectly; optimisation is in progress. | [Extraction](extraction.md) |
| Use negotiated prices | Suggestions and server-enforced catalog prices are implemented. Candidates may come from another supplier and need human review. | [Catalog suggestions](catalog-suggestions.md) |
| Acme's booking rules | Implemented in API and UI. “Small software” and mixed-request handling still depend on stated assumptions. | [Booking rules](booking-rules.md) |
| Optional auto-approval | Implemented for totals strictly below $2,000 including tax. The request model has no currency field. | [Auto-approval](auto-approval.md) |

## Read in this order

1. [Current plan](current-plan.md): completed work, remaining decisions and the next task.
2. [Architecture](architecture.md): components, communication flow and database relationships.
3. The relevant feature explanation in the table above.
4. [Verification](verification.md): repeatable checks, demo scenarios and dated evidence.
5. [App README](../README.md): setup and demo accounts.

For specific questions:

| Document | What it answers |
| --- | --- |
| [Commodity classification](commodity-classification.md) | How categories contain groups, and the two-step optimisation |
| [Migrations](migrations.md) | Schema changes, current migration head and seed behaviour |
| [Extraction evaluation](extraction-eval.md) | Five-quote scoring and historical/recent experiment results |

## Current code versus experiments

The merged baseline at review time was HEAD `2f17391`, on `fix/optimization`. The original four feature branches had been merged into `feat/acme-customer-requests`.

Row-kind extraction and category-then-group classification were being evaluated as uncommitted work; source variants changed during this review. New classification measurements are preserved in [the evaluation notes](extraction-eval.md). A change being present locally does not establish an accuracy improvement. The CI workflow was also local at review time.

## History and delivery

The [original plan](archive/original-plan.md) and [implementation log](archive/implementation-log.md) preserve the reasoning and earlier results. They are archives, not current specifications.

These documents now live inside the repository, with links that work without the surrounding workspace. The current ignore rules allow this directory to be committed; the old root `PLAN.md` remains ignored. The notes are not published merely by being organised here. The assignment's final hand-off is still one PR description.
