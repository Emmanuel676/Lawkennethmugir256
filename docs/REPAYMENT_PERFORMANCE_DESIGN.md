# Proposal: a "Repayment performance" view (design only, not built)

Status: **proposal for discussion (Phase 9A, Part 4). No code exists for it.** All numbers mentioned come from
the synthetic sample packs.

## Purpose

The risk score shows over-indebtedness across lenders. It does not show how loans are being repaid. The field
visit to a daily-collection lender described repayment in four groups: on time, late but cleared, and not paid
in full, plus a grace period. A regulator would want to see this per lender, and to know who needs follow-up.

As everywhere in FairLend Watch, the view prompts a person to look. It is not a credit decision about a
borrower.

## What it shows

**1. Repayment status per loan, on the as-of date.**

| Status | Rule (grace_days = 3, not_paying_after_days = 14; both settings) |
|---|---|
| On time | Repaid on or before the due date |
| Late within grace | Repaid 1 to grace_days after the due date, or still owing at most grace_days past due |
| Late beyond grace | Repaid more than grace_days after the due date, or still owing beyond grace with a payment in the last not_paying_after_days |
| Not paying | Still owing past the due date, with no repayment in the last not_paying_after_days days |
| Current | Not yet due |

**2. Ageing buckets** (outstanding loans only). Amounts owed and loan counts in each bucket, per lender and in
total:

- current
- 1–3 days past due (grace)
- 4–30 days
- 31–60 days
- 61–90 days
- over 90 days

The bucket edges are a setting.

**3. Follow-up list.** Borrowers with a "not paying" loan, or a loan more than 30 days past due. Sorted by
amount owed, it shows:

- the lender, days past due and the last payment date
- the amount owed
- context from other lenders: open lenders, the risk band, and messages labelled abusive

It can be downloaded like the Export page, with the same `#` notice line.

**Layout:** a new page, **Repayments**, after Lenders. It would have:

- four tiles: share on time, late within grace, late beyond grace, not paying
- a stacked bar of ageing buckets per lender, with the bucket written on every bar, never shown by colour alone
- the follow-up table and its download

## Data needed (all already in the import format)

| Table | Columns | Used for |
|---|---|---|
| loans | loan_id, borrower_id, lender_id, amount_outstanding, issue_date, due_date, status | status, buckets, amounts |
| transactions | txn_date, amount, direction = out, counterparty_type = lender, linked_loan_id | the date a loan was cleared; the last payment date |
| borrowers | borrower_id | joining to the risk score |
| (computed) risk score, message labels | band, open_lenders, abusive_messages | follow-up context |

**Gaps to state on screen:**

- **When a loan was cleared** comes from its last linked repayment. Without `linked_loan_id` (15% of
  repayments in the sample packs; unknown in the field), a repaid loan can only be shown as "repaid, date
  unknown". The same goes for the last payment date.
- **There is no field for the amount due or the late charge.** "Behind schedule" for a daily loan, meaning paid
  less than the days elapsed, would need the interest rule. That would be a setting (20% flat at the visited
  lender), not data.
- **Only one as-of snapshot exists**, so no trend over time unless datasets are imported repeatedly.

## Settings (a new `repayment_performance` section)

`grace_days`, `not_paying_after_days`, `bucket_edges_days`, `follow_up_min_days_past_due`, and optionally
`expected_interest_flat` for the "behind schedule" idea.

## Effort estimate

About **3.5 to 4.5 days**:

| Task | Days |
|---|---|
| Pure functions in the style of dashboard_data, plus tests on hand-built loans with known answers | 1.5–2 |
| The page, the CSV export and headless page tests | 1 |
| Checks against the sample packs (repayment_mix shows the 40/42/18 split) | 0.5 |
| README, About page and docs | 0.5 |

## Risks

- **"Repaid" may hide when it was repaid.** Missing loan links blur on time against late (see the gaps).
- **Grace and "not paying" differ by lender.** One visited lender is a tiny sample; the defaults must stay
  settings and be confirmed per lender.
- **Status values in real files may be unreliable**, for example "active" on a loan long past due. The view
  should trust dates and balances over the status word, and say when they disagree.
- **The follow-up list is personal data.** Same rules as the rest: borrower codes only, the "REAL DATA"
  banner, and nothing leaves the computer.
- **It could be misread as a borrower credit score.** The wording must say it describes repayment events for
  a regulator, not anyone's creditworthiness.
- **Tuning on synthetic data.** The packs were built from the same assumptions, so they can check the code,
  not the thresholds.
