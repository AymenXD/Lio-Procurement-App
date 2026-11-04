# Current plan

Reviewed **2026-11-04**. Start with [the overview](README.md). This replaces the duplicated proposal; the [original plan](archive/original-plan.md) is preserved.

## Begin here

**Finish evaluating the extraction changes before starting another feature.** The three main features and the approval bonus already have implementations. The remaining uncertainty is extraction quality, not how many features to add.

Use the five supplied quotes and their [expected values](../backend/tests/fixtures/quotes_expected.json). Compare a known baseline with one change at a time. Keep a change only when the evidence supports it.

## Implementation status

| Area | Merged baseline | Current work or remaining limit |
| --- | --- | --- |
| PDF extraction | pypdf text extraction; null handling; structured AI response; timeouts; missing-field and arithmetic warnings | Row-kind filtering and category-then-group classification are under evaluation. Newly reported single runs score 23 → 22 → 24/30 across variants, with fewer prompt tokens. Confirm the final variant and repeat the comparison. No OCR or vision fallback. |
| Catalog | Embedding suggestions, category filter, unit display, separate prefilled request, stored article link and enforced catalog price | Semantic similarity can suggest a non-equivalent product. No currency or pack-size validation. |
| Booking | Tenant settings; rule preview; enforcement on create/update; audit entry | Confirm the “small software” threshold and the value-share rule for mixed requests. |
| Approval | Server totals; Acme's below-$2,000 policy; approval source; reapproval after material edits | USD and gross-total assumptions; extraction warnings do not prevent auto-approval. |
| CI | Local workflow added for backend tests, frontend types and build | Not pushed or remotely verified at review time. See [verification](verification.md). |

“Implemented” describes code, not perfect model accuracy or production readiness.

## Next actions, in order

1. **Settle extraction optimisation.** Preserve the [reported classification results](extraction-eval.md), then record the revision or diff, model, prompt variant, per-quote results, token usage and timings for the final choice. Compare row labels and hierarchical classification independently where possible. The 24/30 run uses a different baseline from the older 25–26/30 result; it does not establish an overall accuracy gain.
2. **Review the incomplete row-label UI if retaining that experiment.** Its backend returns excluded priced rows as `skippedLines`, but the inspected frontend does not show them. Either complete a review path or remove the unused contract with the experiment. Source variants were being switched during this review; check the active files before editing.
3. **Verify the final checkout.** Run the offline checks after code changes settle, then the five-quote live evaluation separately. Test one catalog suggestion, each Acme rule, and approval on both sides of $2,000. Use a disposable database for migration rollback checks.
4. **Prepare one final PR against main.** Explain the problem, behaviour, evidence, assumptions and remaining limitations. The integration branch is `feat/acme-customer-requests`; the user tests, merges and authorises any push.

## Decisions to state explicitly

| Decision | Current behaviour | Why it needs to be explicit |
| --- | --- | --- |
| What is a “small” software subscription? | Line subtotal below $2,000, before tax | The customer specified $2,000 for approval, not necessarily for this booking rule. |
| How should a mixed request be booked? | The winning rule must match at least 50% of line value; ties use rule order | A small cable-tie line can therefore leave the request in another group. Confirm this interpretation of the non-negotiable rules. |
| Which total controls approval? | Sum of rounded line totals plus tax | Gross total was chosen; the brief does not settle net versus gross. |
| Which currency? | Catalog is seeded in USD; requests have no currency | No currency guard or conversion exists for the approval threshold or price comparisons. |
| What is a negotiated alternative? | A similar catalog article, possibly from another supplier | Similarity does not guarantee an interchangeable product or a lower price. Selection opens a separate request. |
| What happens to an inconsistent quote? | Show a warning; save uses submitted lines and tax | The warning does not block auto-approval. A mathematically consistent total can still come from incorrectly extracted lines. |

## Deferred unless evidence makes it necessary

- OCR/vision fallback for missing image-only fields and ambiguous table layout.
- Reliable currency and pack-size handling.
- Exact identifier/lexical matching before embeddings, and stronger equivalence checks.
- Cache invalidation when article text changes without a change in article count.
- Persisted line kinds, tenant-owned taxonomy, vector database, and a combined PDF/extraction endpoint.

These are options, not an additional checklist to finish the assignment. The [original plan](archive/original-plan.md) proposed some of them; the implementation took a smaller scope.
