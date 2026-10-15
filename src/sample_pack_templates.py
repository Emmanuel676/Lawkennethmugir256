"""Message templates for the Phase 9A sample lender packs. ALL SYNTHETIC.

Written for this prototype, separately from the demo's templates (src/templates.py), so the packs also show
how the demo-trained classifier copes with wording it has not seen. Placeholders: {amount} (UGX, with
thousands separators), {lender} (short brand name), {due_date} ("12 Sep") and {days_text} ("4 days").

The "mixed" lists use Luganda-style mixed phrasing (English with common Luganda words such as sasula = pay,
leero = today, ebbanja = debt, webale = thank you, ewaka = at home, mukwano gwo = your friend). They are
synthetic and were not written by a speaker: have a Luganda speaker check them before showing them outside
the team.
"""

from __future__ import annotations

TEMPLATES = {
    "normal": {
        "english": [
            "{lender}: your daily payment is due. Balance UGX {amount}, due date {due_date}. Thank you.",
            "Hello, a reminder from {lender} that UGX {amount} remains on your loan, due on {due_date}.",
            "Dear client, please keep up your daily repayments. Remaining balance UGX {amount}.",
            "{lender} thanks you for your payments. UGX {amount} is left to clear by {due_date}.",
        ],
        "mixed": [
            "Ssebo/Nnyabo, {lender} reminder: balance UGX {amount}, due {due_date}. Webale nnyo.",
            "Gyebale ko. Your loan balance with {lender} is UGX {amount}. Sasula by {due_date}. Webale.",
        ],
    },
    "firm_pressure": {
        "english": [
            "Your {lender} loan is {days_text} overdue. Pay UGX {amount} today to avoid the late charge.",
            "{lender}: UGX {amount} is overdue by {days_text}. A 20% late charge applies after the grace period.",
            "Your guarantor will be asked to help settle UGX {amount} if this account stays overdue, as agreed.",
            "Final notice from {lender}: clear UGX {amount} or the account goes to our recovery officer.",
        ],
        "mixed": [
            "Olina ebbanja lya UGX {amount} ku {lender}, {days_text} overdue. Sasula leero please.",
            "{lender}: account yo eri overdue {days_text}. Pay UGX {amount} leero to stop extra charges.",
        ],
    },
    "threat": {
        "english": [
            "Pay UGX {amount} today or our team comes to collect your things.",
            "We know your shop. Clear UGX {amount} before evening or you will regret it.",
            "Last chance. UGX {amount} today or we take the TV and the motorbike.",
            "Ignore us again and you will see what happens. Pay UGX {amount} now.",
        ],
        "mixed": [
            "Sasula UGX {amount} leero oba tujja kujja ewaka okutwala ebintu byo.",
            "Tukulabudde: UGX {amount} leero, otherwise abasajja baffe bajja ku dduuka lyo.",
        ],
    },
    "shaming_borrower": {
        "english": [
            "Pay UGX {amount} today or everyone in your phone will know you are a defaulter.",
            "We will put your photo in the market group as a thief unless UGX {amount} is paid.",
        ],
        "mixed": [
            "Bw'otosasula UGX {amount} leero, buli muntu mu contacts zo ajja kumanya nti oli defaulter.",
        ],
    },
    "shaming_third_party": {
        "english": [
            "Hello. You are the guarantor of a {lender} client who owes UGX {amount} and is hiding. Make them pay.",
            "Your friend owes {lender} UGX {amount} and refuses to pay. Everyone should know they are a cheat.",
            "This number belongs to a contact of a defaulter. They owe UGX {amount}. We will keep messaging you.",
        ],
        "mixed": [
            "Mukwano gwo alina ebbanja lya UGX {amount} ku {lender}. Mugambe asasule leero, ye mubbi.",
            "Ggwe guarantor wa client waffe. Alina okusasula UGX {amount}. Mugambe oba naawe tujja kukutuukirira.",
        ],
    },
}
