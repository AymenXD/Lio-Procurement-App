# Acme's booking rules

[Documentation index](README.md) · Implemented; reviewed 2026-11-04

## What this solves

AI may classify an item sensibly but differently from Acme's accounting convention. These tenant rules override the chosen group, including a group selected by the user.

| Acme request | Seeded keywords | Stored group | Limit |
| --- | --- | --- | --- |
| Cable ties → Electrical Engineering | cable tie, zip tie | 11 | None |
| Printer toner → IT Hardware | toner | 29 | None |
| Small software subscriptions → Office Supplies | subscription, saas, software license | 2001 | Line subtotal strictly below $2,000 |

The $2,000 definition of “small” is an implementation assumption. The customer explicitly gave that number for approval, not for the software booking rule.

Office Supplies is an extra **shared** commodity group under Office & Administration. The rules are specific to Acme; the group itself is not tenant-owned.

## How one request gets one group

[match_rule](../backend/app/services/booking_rules.py) examines order-line descriptions and values:

1. Match keywords case-insensitively at word boundaries, allowing a simple plural and spaces/hyphens between words.
2. Reject a rule with `max_total` when the sum of all line values is at or above its limit. This subtotal excludes tax.
3. Require the matching lines to represent at least 50% of the request's positive line subtotal.
4. Choose the rule with the largest matching line value. A tie uses the first listed rule.

The system has one commodity group per request, not one per line. The 50% policy is a design choice for mixed requests: $20 of cable ties in a $5,000 request will not force Electrical Engineering. Confirm that choice against Acme's “non-negotiable” requirement before presenting it as agreed behaviour.

The broad keyword “subscription” can also match a non-software subscription. The matcher is deterministic, not a semantic classifier.

## Where it is enforced

- Extraction applies the organisation's rules to the extracted lines.
- The request form calls `POST /requests/booking-rule-preview` while lines change, displays the rule label and locks the group when a rule applies.
- Create and update apply the rule again on the server using recalculated line values. UI changes cannot bypass a matching rule.
- Request activity records the applied rule.

Extraction uses the model's line values, while saving uses quantity × unit price. If those disagree, the final rule decision can change.

Admins can edit rules and try sample inputs in Organisation → Settings. Rules live in `organizations.settings.booking_rules`; updates validate the group IDs and preserve settings fields not supplied at the top level.

The seed adds Acme's rules only when the `booking_rules` key is absent. An administrator's edits, including an intentionally empty rule list, are preserved.

## Checks and code

Use a single-line cable-tie request, a toner request and a software subscription below $2,000. Then verify the software boundary at exactly $2,000 and a mixed request below the 50% share. Repeat a sample as another tenant to check that Acme's rules do not apply there.

None of the five sample PDFs triggers these three rules; that is useful sample coverage, not proof that false positives are impossible.

[Rule service](../backend/app/services/booking_rules.py) · [rule schemas](../backend/app/schemas/organizations.py) · [seed](../backend/app/seed.py) · [request enforcement](../backend/app/routers/requests.py) · [unit tests](../backend/tests/test_booking_rules.py) · [API tests](../backend/tests/test_smoke.py)
