# Onboarding walkthrough: importing lender data (synthetic sample packs)

> **Everything in this walkthrough is SYNTHETIC.** The four lenders are fictional and end in "(Demo)".
> Borrower codes were made from invented phone numbers with a fake salt. Every message ends in
> "(SYNTHETIC)". The numbers below come from running the real importer and the real risk score on the
> sample packs (`python -m src.evaluate_sample_pack`). They are not field results.

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
   - The counts row shows 1 lender, 292 borrowers, 724 loans, 21,902 transactions and 1,713 messages.
   - Repayments are daily, so there are many transactions.
7. Press **Import**. Then switch to the new dataset in the sidebar.

**What the screen shows.** The red banner reads **"REAL DATA - SYNTHETIC sample baseline. Confidential."**
This is expected: the importer marks every imported dataset as real, because it cannot know otherwise.
That is why the dataset name says SYNTHETIC. Say it out loud.

On the Data page's **Data health** tab: **"Borrowers who appear at two or more lenders: 0 of 292"**. With one
lender, there is nothing to match yet.

### 2. Add lender B: matches appear

On the **Import** tab, choose **Add to an existing real dataset**, then **Add to:** `synthetic-sample-baseline`.
Upload `sample_pack\baseline\lender_B`, Validate, then Import.

- The import message says **81 borrower code(s) were already in the dataset and kept**.
- **Data health:** **81 of 400** borrowers appear at two or more lenders.
- **Point out:** the same person has the same code at lender A and lender B, because both used the same salt.
  No phone number was shared, and nobody else could have seen this overlap.
- Overview: 3 high, 60 medium and 337 low.

### 3. Add lender C

Do the same with `sample_pack\baseline\lender_C`.

- **104 codes** were already known.
- **Data health:** **149 of 499** borrowers at two or more lenders.
- The per-lender table lists the three lenders, each with "Can be ranked: yes".
- Overview: **8 high, 97 medium and 394 low**.
- Lenders page:

  | Rank | Lender | Labelled abusive |
  |---|---|---|
  | 1 | Bright Day Loans | 17% |
  | 2 | Riverstone Credit | 6% |
  | 3 | Mango Tree Daily Cash | 0.7% |

### 4. Data health

Open **Data**, then **Data health**. The table has one row per lender, showing loans, messages, borrowers, the
date range and the share of loans with transactions.

- **Point out:** if the "two or more lenders" number stayed at 0 after lender B, the lenders did not use the
  same borrower codes. That is the first thing to check with real data.

### 5. The overlap view

Open **Borrowers**. In the sidebar set **Minimum open lenders** to 2: 98 borrowers match. Open the top borrower
(score 81.6, high band).

- **Point out the score breakdown:** 3 open lenders, debt about 2.1 times monthly income, and cycling events.
- **Point out "Loans across all lenders" and the loan timeline:** loans from three lenders overlap in time.
- **Say:** "A score prompts a person to look. It is not a verdict."

### 6. Export the follow-up list

Open **Export**. Keep **Bands to include** at high and medium: **"105 borrowers will be exported."** Press
**Download flagged borrowers (CSV)**. The first line of the file is the `#` notice.

### 7. Optional: lender D, the small lender

Add `sample_pack\baseline\lender_D`. It has 34 messages. On the Lenders page it appears under
**"Too few messages to rank"**, with 24% labelled abusive and a 95% interval of 12% to 40%. It has some
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
| baseline | 500 | 1,726 | 4,086 | 10 / 96 / 394 | 429 (113) | 30% | 7.1% / 10.7% | none in scenario | 74 of 271 |
| high_overlap | 400 | 2,187 | 5,356 | 21 / 236 / 143 | 1,074 (291) | 90% | 6.9% / 11.6% | none in scenario | 207 of 304 |
| cycling | 500 | 1,997 | 3,716 | 9 / 146 / 345 | 752 (153) | 38% | 7.3% / 11.3% | 60 of 60 | 67 of 234 |
| repayment_mix | 600 | 2,407 | 4,696 | 2 / 141 / 457 | 721 (145) | 30% | 5.3% / 8.8% | none in scenario | 27 of 99 |
| clean_control | 300 | 772 | 1,812 | 0 / 4 / 296 | 0 (0) | 0% | 0.0% / 0.0% | none in scenario | 4 of 137 |

Each import of `all_lenders` took 2 to 9 seconds on this laptop.

**How to read it:**

- **clean_control has no high-band borrowers and no cycling events.** With one lender each, the cycling rule
  correctly finds nothing, even though every borrower repays daily and re-borrows within 0 to 14 days.
- **Every defined cycler is caught** (cycling scenario: 60 of 60).
- **Cycling events also appear for ordinary multi-lender borrowers.** In baseline, 113 of the 150 multi-lender
  borrowers have a cycling event, and 19 of them are lifted to medium by the cycling rule. A borrower who
  repays lender A daily while taking a new loan at lender B looks like "borrowing to repay", because a daily
  repayment to A falls within 2 days of B's disbursement. The rule cannot yet tell refinancing apart from
  paying two lenders at once. This is a known limit, not a pack error.
- **Bad payers are flagged far more often when they also use other lenders.** Arrears at a single lender adds
  at most 20 of the 100 points.
- **The model finds less abuse than there is** (about 7% against 11% true). The packs use new wording,
  including Luganda-style mixed phrases that the demo-trained classifier has never seen. This is expected.
  Use the Review page with real data.
- **Bad payers in baseline, high_overlap and cycling** use `payer_scope: loan`: the 40/42/18 split is drawn
  for every loan, so long-standing borrowers often have one unpaid loan (54% of baseline borrowers).
  repayment_mix uses `payer_scope: borrower` (one behaviour per person), so the split shows directly:
  99 of 600 (17%) are non-payers.

## Sequential import check (baseline, lender by lender)

| After | Borrowers | Codes already known | Borrowers at 2+ lenders | Expected from the answer key |
|---|---:|---:|---:|---:|
| lender A | 292 | 0 | 0 | 0 |
| lender B | 400 | 81 | 81 | 81 |
| lender C | 499 | 104 | 149 | 149 |
| lender D | 500 | 4 | 150 | 150 |

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

Losing some links costs nothing, because cyclers make many daily repayments. Losing all of them removes the
cycling signal completely. Ask lenders whether their repayment records name the loan.

## What the packs contain (settings in the `sample_pack` section of config.yaml)

- **Lenders and loans.** Four "(Demo)" lenders: A clean, B borderline, C abusive and D small and abusive.
  Loans are UGX 50,000 to 2,000,000 (typical 150,000) over 30 days, at 20% flat interest. Repayments are
  daily. There are 3 days of grace, then a 20% charge on the unpaid balance once, at day 33. Re-borrowing
  follows 90% of clearings, after 0 to 14 days.
- **(a)** Abusive lenders sometimes start pressure 1 to 3 days before the due date, and some reminders go out
  between 00:00 and 04:59.
- **(b)** Messages after part payments quote what is still owed.
- **(c)** About 40% of overdue messages quote a rounded amount or the original amount, not the exact balance.
- **(d)** About half of the late-but-cleared loans still received overdue messages.
- **(e)** The small lender D has 23 to 39 messages (under 50) and at least 3 abusive ones; clean_control has
  no abuse.
- **(f)** Covered in the section above.
- **Language.** About a third of messages use Luganda-style mixed phrasing. It was not written by a speaker:
  have it checked before showing it outside the team.
