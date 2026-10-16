# FairLend Watch: 5-minute demo script

> **Every number below comes from the SYNTHETIC demo dataset** (seed 42, 5,000 made-up
> borrowers, 13 fictional lenders ending in "(Demo)"). The figures were re-read on 2026-10-16 (after the Phase 9B cycling rule)
> from `python -m src.evaluate_overlap`, `python -m src.evaluate_classifier`,
> `python -m src.evaluate_lenders` (all with `--dataset demo`), the Overview page and
> `config.yaml`. If the demo is rebuilt with other settings, re-read them before presenting.
> **All amounts are Ugandan shillings (UGX), whole shillings**, as on screen ("UGX 1,500,000").
> Say "shillings" or "UGX" when you read an amount out loud, never "dollars".

## Before you start (2 minutes, off stage)

```powershell
.\dev.ps1 -Preflight      # every line must say PASS
.\dev.ps1 -Present        # opens the dashboard with the demo only; real data cannot appear
```

- The sidebar shows the **Presentation mode** tag and no dataset switcher. If it doesn't, stop and restart with `-Present`.
- Open the **Guided Demo** page (first in the menu, under the Overview) in a second tab. It has the six cases and a button for each.
- The featured borrowers and lenders are chosen by fixed rules from computed scores and labels, never from answer labels. On the current demo they are B01767, B00030, B00550, B02339, Kestrel Instant Cash (Demo) and Redstone Loans (Demo).

## The script (5:00)

| Time | Click | Say |
|------|-------|-----|
| 0:00-0:40 | **Overview** | "FairLend Watch gives a regulator a view **across** lenders that no single lender has. Three things up front: **this data is synthetic**; **the accuracy numbers are optimistic** because the data was built to be separable; and **a person decides**. The tool only points at files worth reading. Of 5,000 made-up borrowers, 280 are in the high band and 863 in medium. 23% of the 26,780 collection messages were labelled abusive." |
| 0:40-1:25 | Guided Demo, step 1: **Open on the Borrowers page** | "Borrower B01767 scores 89 of 100. They have 5 open lenders and owe 3.1 times their monthly income. Each lender sees one loan; only the combined view shows the stack. Here is the breakdown: every point is explained, and the weights are in the config." |
| 1:25-2:05 | Step 2 | "B00030 scores only 28, but took 5 new loans within days of repaying others: borrowing to repay. A rule lifts repeated cycling to medium so a person looks. The page says the rule did it, not the score." |
| 2:05-2:40 | Step 3 | "B00550 has 5 open lenders but owes only 0.23 times monthly income: it scores 38.5 and stays in medium. The score is not just a lender count. Debt, arrears and cycling matter more." |
| 2:40-3:20 | Step 4 | "B02339 received 48 messages labelled abusive, 20 of them late at night and 14 sent to other people. Scroll down: you can read every message. The labels are a model's guesses; late night and third party are facts of the message." |
| 3:20-3:55 | Step 5 (Lenders page) | "Kestrel Instant Cash sent only 6 messages. That is too few to rank: its interval runs from 0% to 39%. A lender needs 50 messages before it is ranked, so a small lender can't top or escape the list by luck." |
| 3:55-4:35 | Step 6 (Lenders page) | "Redstone Loans ranks first: 45% of its 2,094 messages were labelled abusive, and even the low end of the 95% interval is 43%. We rank by that low end, so a lender only reaches the top on strong evidence. A rank means 'read these messages', not 'this lender broke the law'." |
| 4:35-5:00 | **About** | "What we have not proven: these are synthetic messages, so real accuracy will be lower. Real data would need legal clearance, redaction (built in), and people checking a sample of labels on the Review page before anyone relies on them. Questions?" |

## Optional: Repayments (45 seconds; after step 6, or when asked "who is not paying?")

Numbers read on 2026-10-16 from the Repayments page on the synthetic demo. The 5-minute script above is
unchanged; this adds 45 seconds.

| Time | Click | Say |
|------|-------|-----|
| +0:00-0:15 | **Repayments** | "This page is a follow-up prompt, not a verdict or a credit score. Of 11,158 loans, 29% were repaid on time, 23% up to three days late, inside the grace period, and 12.5% are not being paid." |
| +0:15-0:35 | Scroll to **Follow-up list** | "885 borrowers have a loan that is not being paid or is overdue. The list shows codes, never names, with the lenders involved, days past due, the amount owed and the cross-lender risk band, and it downloads as CSV with the synthetic notice on the first line." |
| +0:35-0:45 | Point at **Known limits** | "It needs repayments linked to their loan, lenders differ on grace rules, and a status is not proof of wrongdoing. The demo repays each loan in one payment; the daily-repayment story is in the sample packs." |

## Three caveats to say out loud (always)

1. **The data is synthetic.** It describes no real people, loans, lenders or messages. The lenders are fictional.
2. **The accuracy is optimistic.** The generator built borrower types and lender styles to be separable. On real data both the score and the classifier will do worse, by an amount we have not measured yet.
3. **A human decides.** A flag or a rank tells a person where to look. It is never a finding, a verdict or a reason to act on its own.

## Hard questions and short, true answers

1. **Why not name the worst lenders publicly?**
   A rank is a model's estimate, built on labels that are guesses. Naming a lender needs a person to read the messages and a proper process with a right of reply. The tool helps decide whose files to open; it does not publish.

2. **What about borrowers in real distress?**
   The tool doesn't contact anyone and doesn't decide anything about a borrower. In a real deployment, flagged borrowers would go to people trained to help, under the regulator's own rules. The tool only shortens the search.

3. **How do you know the weights are right?**
   We don't. The weights (open lenders 25, debt-to-income 30, arrears 20, cycling 15, loan velocity 10) were set by judgement before looking at results, and were not tuned on the answers. On synthetic data the score gets 87.4% precision and 86.9% recall, but the data was built to be separable. Real use would need validation with case workers.

4. **What if lenders use different borrower IDs?**
   Then the cross-lender view disappears, because the same person looks like several people. Every lender must make codes from the same phone or ID number with the **same secret salt** (`src.make_borrower_codes`). The Data health tab shows how many borrowers appear at two or more lenders. If that is near zero, the codes don't match.

5. **What is the classifier's real accuracy?**
   Unknown on real messages. On the synthetic test set (400 messages from 16 held-out phrasings) macro-F1 is 0.93, but that is about 14 of 16 unseen phrasings handled, not "93% of messages". On a real dataset, the Review page measures it on a random sample a person has checked, with an interval.

6. **What are its weak spots?**
   On the test set, 15 of 100 shaming messages were read as threats. One phrasing ("your colleagues will receive a message about your debt") is wrong every time. 8 of 100 polite reminders were read as shaming. It was trained only on synthetic English text, so real Luganda or mixed-language messages and slang are untested.

7. **What about privacy and the law?**
   Real data needs legal clearance first, and the import refuses to run without a permission confirmation. Phone numbers, emails, national ID numbers and listed names are redacted before storage, and error messages never repeat a cell's value. Everything runs on one computer with no network. Real data must never be sent to a free cloud AI service.

8. **Can it detect names?**
   No. Names cannot be detected automatically. The import removes only names on a list you provide, and the Data page suggests frequent capitalised words for a person to check.

9. **Why should a small lender with a few awful messages not be at the top?**
   With 6 messages the true share could be anywhere from 0% to 39%. Ranking by the low end of the interval means a lender needs strong evidence to rank high. Lenders under 50 messages are shown separately, so they are not hidden.

10. **Couldn't the model just learn which lender sent a message?**
    Lender names are masked before training and prediction, so the model judges what a message says, not who sent it.

11. **What happens with a borrower who has lots of loans but is fine?**
    That is the "many lenders, little debt" case in the demo (B00550: 5 lenders, 0.23 times income). Many such borrowers stay below high. On synthetic data, about four in ten of the high-income look-alike borrowers still land in medium, and we say that openly on the About page.

12. **Who checks the checker?**
    Every number on screen traces back to a rule in `config.yaml` or a labelled sample. On real data, a person labels a random sample on the Review page, and the dashboard shows what share of labels a person has checked. The test suite (over 400 automatic checks) fails if the dashboard ever reads the answer labels.

## If something goes wrong on stage

- A page shows **"Something went wrong (error code FW-...)"**: say "that's the safety net", move to the next step, and look up the code in `data\logs\app.log` afterwards. The log holds the error type and code locations only, never data.
- The numbers differ from this script: the demo was rebuilt with other settings. Use the Guided Demo page's sentences, which are computed live.
