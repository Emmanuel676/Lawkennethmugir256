# Onboarding walkthrough: importing lender data (synthetic sample packs)

> **Everything in this walkthrough is SYNTHETIC.** The four lenders are fictional and end in "(Demo)".
> Borrower codes were made from invented phone numbers with a fake salt. Every message ends in
> "(SYNTHETIC)". The numbers below come from running the real importer and the real risk score on the
> sample packs (`python -m src.evaluate_sample_pack`, Phase 9B rules). They are not field results.

This shows a team member how lender data comes in, one lender at a time, and how borrowers who use
several lenders appear only once their lenders' files are combined. About 10 minutes.

## Before you start (once)

```powershell
cd $HOME\projects\lending-monitor
.\dev.ps1 -SamplePack          # writes sample_pack\ (about 15 seconds; git-ignored, never committed)
.\dev.ps1                      # starts the dashboard on this computer only, NOT in presentation mode
```

Presentation mode (`.\dev.ps1 -Present`) switches the Data page off, so do **not** use it here. The browser
opens at http://localhost:8501.

The packs are in `sample_pack\<scenario>\lender_A` ... `lender_D` (one folder per lender) and
`all_lenders` (everything at once). **Never upload `sample_pack\_answer_keys`**: it is the answer key used
only by tests and evaluation.

## Steps (scenario: baseline)

### 1. Import lender A as a new dataset

Open **Data**, then the **Import** tab.

1. **What do you want to do?** Create a new dataset.
2. **Dataset name:** `SYNTHETIC sample baseline`. **Where the data came from:** `synthetic sample pack`.
3. **File type:** Five CSV files. Upload the five files in `sample_pack\baseline\lender_A`.
4. **As-of date:** 2026-10-01. This is the suggested date; keep it.
5. Leave redaction on and tick the permission box. The pack has no personal data, but the habit matters.
6. Press **Validate**.
   - **Point out:** "No errors found", with 0 warnings and no notes.
   - The counts row shows 1 lender, 244 borrowers, 666 loans, 20,144 transactions and 1,291 messages.
   - Repayments are daily, so there are many transactions.
7. Press **Import**. Then switch to the new dataset in the sidebar.

**What the screen shows.** The red banner reads **"REAL DATA - SYNTHETIC sample baseline. Confidential."**
This is expected: the importer marks every imported dataset as real, because it cannot know otherwise.
That is why the dataset name says SYNTHETIC. Say it out loud.

On the Data page's **Data health** tab: **"Borrowers who appear at two or more lenders: 0 of 244"**. With one
lender, there is nothing to match yet.

### 2. Add lender B: matches appear

On the **Import** tab, choose **Add to an existing real dataset**, then **Add to:** `synthetic-sample-baseline`.
Upload `sample_pack\baseline\lender_B`, Validate, then Import.

- The import message says **85 borrower code(s) were already in the dataset and kept**.
- **Data health:** **85 of 387** borrowers appear at two or more lenders.
- **Point out:** the same person has the same code at lender A and lender B, because both used the same salt.
  No phone number was shared, and nobody else could have seen this overlap.
- Overview: 0 high, 7 medium and 380 low.

### 3. Add lender C

Do the same with `sample_pack\baseline\lender_C`.

- **104 codes** were already known.
- **Data health:** **149 of 498** borrowers at two or more lenders.
- The per-lender table lists the three lenders, each with "Can be ranked: yes".
- Overview: **1 high, 36 medium and 461 low**.
- Lenders page:

  | Rank | Lender | Labelled abusive |
  |---|---|---|
  | 1 | Bright Day Loans | 14% |
  | 2 | Riverstone Credit | 5% |
  | 3 | Mango Tree Daily Cash | 0.6% |

### 4. Data health

Open **Data**, then **Data health**. The table has one row per lender, showing loans, messages, borrowers, the
date range and the share of loans with transactions.

- **Point out:** if the "two or more lenders" number stayed at 0 after lender B, the lenders did not use the
  same borrower codes. That is the first thing to check with real data.

### 5. The overlap view

Open **Borrowers**. In the sidebar set **Minimum open lenders** to 2: 83 borrowers match. Open the top borrower
(score 60.4, high band).

- **Point out the score breakdown:** 2 open lenders, debt about 1.9 times monthly income, and 3 new loans
  taken within 2 days of clearing a loan from another lender.
- **Be honest about it:** no borrower in the baseline pack was generated as a cycler. This borrower really
  cleared one lender within days of a loan from another, which looks exactly like borrowing to repay in this
  data. That is the known limit described below, and the reason a person must read the file.
- **Point out "Loans across all lenders" and the loan timeline:** loans from different lenders overlap in time.
- **Say:** "A score prompts a person to look. It is not a verdict."

### 6. Export the follow-up list

Open **Export**. Keep **Bands to include** at high and medium: **"37 borrowers will be exported."** Press
**Download flagged borrowers (CSV)**. The first line of the file is the `#` notice.

### 6b. Repayments: who is not paying (Phase 10)

Open **Repayments** (still with lenders A, B and C imported).

- **Say first:** "This is a follow-up prompt, not a verdict or a credit score."
- **Tiles** (shares of 1,887 loans): **On time 46.1%**, **Late within grace 4.3%**, **Late beyond grace 24.0%**,
  **Not paying 7.2%**, **Unknown (no link) 0.0%**, **Owed, unpaid loans UGX 54.1M** (hover for the exact amount,
  UGX 54,065,300). The caption adds 304 current, 15 in grace and 29 overdue but still paying.
- **Status mix per lender:**

  | Lender | On time | Late beyond grace |
  |---|---|---|
  | Mango Tree Daily Cash | 48% | 21% |
  | Riverstone Credit | 48% | 23% |
  | Bright Day Loans | 42% | 28% |

  All three have 50 or more loans, so none is marked "too small to compare".
- **Follow-up list:** **"124 borrowers in the follow-up list."** (97 not paying, 27 overdue but paying)
  - The first rows are borrowers not paying at all three lenders, 179 days past due.
  - Their risk band and open lenders come from the cross-lender score.
  - **Point out:** codes only, no names; it is a work list, not a ranking of borrowers.
- Press **Download the follow-up list (CSV)**. The first line of the file is the `#` notice with the words
  "follow-up prompt, not a verdict or a credit score".
- **Point out the "Known limits" at the bottom:**
  - it needs loan links on repayments
  - lenders differ on grace rules
  - a status is not proof of wrongdoing
  - the defaults come from one lender

### 7. Optional: lender D, the small lender

Add `sample_pack\baseline\lender_D`. It has 39 messages. On the Lenders page it appears under
**"Too few messages to rank"**, with 18% labelled abusive and a 95% interval of 9% to 33%. It has some
abusive messages but too few to compare fairly. Data health now shows 150 of 500.

### Afterwards

Delete the dataset on the **Datasets** tab (type its name). The demo is not affected.

## Expected results per scenario (synthetic)

Each scenario's `all_lenders` folder was imported with the real importer (as-of 2026-10-01), its messages were
labelled with the saved local classifier, and it was scored with the real risk score. The answer key was used
only to count the last two columns. "Flagged" means the medium or high band. Rebuild these numbers with
`python -m src.evaluate_sample_pack`.

| Scenario | Borrowers | Loans | Messages | High / medium / low | Cycling events (borrowers with one) | 2+ lenders | Abusive share (model / true) | Answer-key cyclers flagged | Answer-key bad payers flagged |
|---|---:|---:|---:|---|---|---:|---|---|---|
| baseline | 500 | 1,901 | 3,795 | 1 / 38 / 461 | 84 (53) | 30% | 6.7% / 10.8% | none in scenario | 19 of 97 |
| high_overlap | 400 | 2,437 | 4,843 | 5 / 74 / 321 | 212 (135) | 90% | 6.1% / 9.6% | none in scenario | 32 of 66 |
| cycling | 500 | 2,200 | 3,488 | 0 / 94 / 406 | 458 (113) | 38% | 6.0% / 9.6% | 60 of 60 | 12 of 74 |
| repayment_mix | 600 | 2,407 | 4,696 | 2 / 44 / 554 | 105 (70) | 30% | 5.3% / 8.8% | none in scenario | 26 of 99 |
| clean_control | 300 | 842 | 1,633 | 0 / 3 / 297 | 0 (0) | 0% | 0.0% / 0.0% | none in scenario | 3 of 51 |

Each import of `all_lenders` took 2 to 15 seconds on this laptop. The cycling scenario's 38% at 2+ lenders is
30% of ordinary borrowers plus the 60 cyclers, who all use several lenders.

**Payer groups** (40/42/18 applied per borrower in every scenario; cyclers excluded):

| Scenario | On time | Late but cleared | Not paid in full |
|---|---:|---:|---:|
| baseline | 41% | 39% | 19% |
| high_overlap | 41% | 42% | 16% |
| cycling | 44% | 39% | 17% |
| repayment_mix | 44% | 40% | 16% |
| clean_control | 37% | 46% | 17% |

**How to read it:**

- **clean_control has no high-band borrowers and no cycling events.** With one lender each, the cycling rule
  correctly finds nothing, even though every borrower repays daily and re-borrows within 0 to 14 days.
- **Every defined cycler is caught** (cycling scenario: 60 of 60). Each one pays the old loan off on the day the
  loan from another lender arrives.
- **Some multi-lender borrowers still get cycling events.** In baseline, 53 of the 150 multi-lender borrowers
  have one, and 6 of them are lifted to medium by the cycling rule. In 84 to 94% of these cases the borrower
  really cleared one lender within 2 days of a loan at another lender. In the rest, the loan's true last
  repayment had no `linked_loan_id`, so an earlier linked repayment was taken as the clearing one. See the
  known limits below.

  | Scenario | Multi-lender borrowers with a cycling event | Lifted to medium by the cycling rule |
  |---|---|---|
  | baseline | 53 of 150 | 6 |
  | high_overlap | 135 of 360 | 9 |
  | cycling (excluding cyclers) | 53 of 132 | 4 |
  | repayment_mix | 70 of 180 | 5 |
- **Bad payers are flagged far more often when they also use other lenders.** Arrears at a single lender adds
  at most 20 of the 100 points.
- **The model finds less abuse than there is** (about 6% against 10% true). The packs use new wording,
  including Luganda-style mixed phrases that the demo-trained classifier has never seen. This is expected.
  Use the Review page with real data.

## Known limits of the cycling signal

- **Clearing one lender from your own money looks the same as borrowing to repay.** A borrower who really
  clears one lender within 2 days of taking a loan at another lender is indistinguishable from borrowing to
  repay in these columns. The rule counts an event only when the repayment clears the old loan (the loan is
  repaid and this is its last linked repayment, because `lending.db` stores no amount due) and the new loan is
  from another lender. A person must read the file.
- **Cycling cannot be detected without `linked_loan_id`.** Without it, nobody can tell which loan a repayment
  paid. If only the true last repayment lacks the link, an earlier linked repayment is taken as the clearing one.

## Repayments page per scenario (synthetic)

The share of loans in each status, after importing `all_lenders`:

| Scenario | Loans | On time | Late within grace | Late beyond grace | Not paying | Overdue but paying | In grace | Current | Unknown | Follow-up borrowers |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline | 1,901 | 45.9% | 4.3% | 24.2% | 7.2% | 1.5% | 0.8% | 16.1% | 0.0% | 124 |
| high_overlap | 2,437 | 42.4% | 5.8% | 27.7% | 5.9% | 1.5% | 0.7% | 16.0% | 0.0% | 100 |
| cycling | 2,200 | 53.2% | 3.8% | 21.0% | 4.5% | 1.4% | 0.6% | 15.5% | 0.0% | 104 |
| repayment_mix | 2,407 | 45.2% | 4.9% | 27.1% | 6.0% | 1.6% | 0.5% | 14.7% | 0.0% | 137 |
| clean_control | 842 | 39.8% | 7.1% | 30.6% | 6.1% | 1.8% | 0.7% | 13.9% | 0.0% | 66 |

**Against the answer key** (evaluation only; the page never reads it):

- **Per borrower:** the page's worst status agrees with how each borrower was generated (on time / late but
  cleared / not paid in full) for 100% of the borrowers it can decide, in all five scenarios. At most one
  borrower per scenario is "too early" (its only late loan is still current).
- **Per loan:** 99.3 to 99.8% agree. Every miss is a late loan read as on time, because its last repayment had
  no `linked_loan_id`.
- **Treat this as a consistency check, not accuracy.** The packs were built from the same rules as the page; a
  non-payer, for example, always stops early and never pays again. Real data will disagree more.

## Sequential import check (baseline, lender by lender)

| After | Borrowers | Codes already known | Borrowers at 2+ lenders | Expected from the answer key |
|---|---:|---:|---:|---:|
| lender A | 244 | 0 | 0 | 0 |
| lender B | 387 | 85 | 85 | 85 |
| lender C | 498 | 104 | 149 | 149 |
| lender D | 500 | 3 | 150 | 150 |

Every match the answer key expects is found, and nothing else.

## Repayments without a loan link (realism setting f)

`sample_pack.repayment.link_share` sets the share of repayments that carry `linked_loan_id` (default 85%).
These results are from the cycling scenario:

| Repayments with a link | Cyclers with a cycling event | Cyclers flagged |
|---|---|---|
| 100% | 60 of 60 | 60 of 60 |
| 85% (default) | 60 of 60 | 60 of 60 |
| 50% | 60 of 60 | 60 of 60 |
| 0% | **0 of 60** | **0 of 60** |

Losing some links costs little here, because each cycler refinances several times. Losing all of them removes
the cycling signal completely. Ask lenders whether their repayment records name the loan.

## What the packs contain (settings in the `sample_pack` section of config.yaml)

- **Lenders and loans.** Four "(Demo)" lenders: A clean, B borderline, C abusive and D small and abusive.
  Loans are UGX 50,000 to 2,000,000 (typical 150,000) over 30 days, at 20% flat interest. Repayments are
  daily. There are 3 days of grace, then a 20% charge on the unpaid balance once, at day 33. Re-borrowing
  follows 90% of clearings, after 0 to 14 days. Every borrower keeps one payer behaviour (`payer_scope: borrower`).
- **(a)** Abusive lenders sometimes start pressure 1 to 3 days before the due date, and some reminders go out
  between 00:00 and 04:59.
- **(b)** Messages after part payments quote what is still owed.
- **(c)** About 40% of overdue messages quote a rounded amount or the original amount, not the exact balance.
- **(d)** About half of the late-but-cleared loans still received overdue messages.
- **(e)** The small lender D has 19 to 44 messages (under 50) and at least 3 abusive ones; clean_control has
  no abuse.
- **(f)** Covered in the section above.
- **Language.** About a third of messages use Luganda-style mixed phrasing. It was not written by a speaker:
  have it checked before showing it outside the team.
