# Auto-approval

[Documentation index](README.md) · Optional feature implemented; reviewed 2026-11-04

## What “skip buyer approval” means

The role system still exists: requesters create requests; buyers and admins can approve or reject them. Auto-approval is an organisation policy that approves an eligible pending request immediately, without waiting for one of those people.

Acme is seeded with `auto_approval = {enabled: true, below_amount: 2000}`. Other tenants default to disabled. Admins can change the policy in Organisation → Settings.

| Server-calculated total | Acme's result |
| --- | --- |
| $1,999.99 | Auto-approved |
| $2,000.00 | Pending buyer/admin approval |
| $2,042.15 | Pending buyer/admin approval |

The comparison is strictly **below** the threshold.

## Which amount is compared?

[totals.py](../backend/app/services/totals.py) calculates:

```text
line total    = quantity × unit price, rounded half up to cents
request total = sum of line totals + tax
```

Catalog-linked lines first receive the server's catalog price. Shipping and fees are ordinary order lines. Missing tax counts as zero. Browser-supplied totals are ignored, and negative prices or tax are rejected.

The policy uses **gross total including tax**. This was an implementation decision. For example, Hollis's $1,880 subtotal plus $162.15 tax stays pending at $2,042.15.

Requests have **no currency field**. Seeded catalog data is USD, but the policy does not check or convert currency. The $2,000 rule therefore assumes USD input.

## What is saved and what happens on edits?

- Automatic approval sets `approval_status = approved`, `approval_source = auto`, a timestamp and no human approver. Activity records the policy decision.
- A buyer/admin decision records `approval_source = manual`.
- Editing an approved request's vendor, tax ID, order lines, tax or computed total resets its approval, then checks the policy again.
- Title, department and requestor-name changes keep the approval.
- An explicitly rejected request is not silently auto-approved on edit.
- Changing policy settings does not retroactively process all existing requests.

The purchase's workflow `status` and its `approval_status` are separate fields. See [migration 0008](migrations.md) for the added tax and approval-source columns.

## Limits

Recomputing money prevents a forged browser total from controlling approval; it does not prove that the submitted lines accurately describe the quote. Extraction warnings do not block this policy. A missed item, omitted tax or incorrectly labelled alternative can still affect the decision.

The implementation does not detect deliberate order splitting or validate the quote's currency. Old requests without stored tax may receive a different computed total on their first edit.

## Code and checks

[Approval policy](../backend/app/services/approval_policy.py) · [money calculations](../backend/app/services/totals.py) · [create/update enforcement](../backend/app/routers/requests.py) · [policy tests](../backend/tests/test_approval_policy.py) · [API tests](../backend/tests/test_smoke.py)

Check the threshold boundaries, another tenant with policy disabled, and a price edit that moves an approved request above $2,000. A title-only edit should keep approval. Historical Apple/Hollis API checks are recorded in [the implementation log](archive/implementation-log.md); they were not rerun during this documentation review.
