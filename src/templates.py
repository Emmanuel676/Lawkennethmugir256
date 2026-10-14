"""Message templates used by the synthetic data generator.

Every message is built from one of these templates. They are written for this
prototype and describe no real company or person. Placeholders:

    {amount}    amount owed, with thousands separators
    {lender}    short brand name of the (fictional) lender
    {due_date}  due date such as "12 Sep"
    {days_text} how long overdue AT THE TIME THE MESSAGE WAS SENT, worded correctly ("1 day", "5 days")
    {fee}       the late fee actually charged on that loan

The four classes follow PRD section 9.2:

    normal               neutral reminder
    firm_pressure        insistent but lawful (includes a few deliberately hard borderline cases)
    threat               threatens harm or action the lender cannot lawfully take (includes veiled threats)
    shaming_third_party  exposes the debt to other people, or contacts the borrower's contacts.
                         Despite the name it also covers shaming sent straight to the borrower,
                         because the PRD class is "shaming or third-party contact".

HELD-OUT PHRASINGS
Each list below has a matching *_HOLDOUT list written in a different style.
Messages built from a holdout template are never used for development or
training. Only they can become the test set (see generate_data.py). That way a
classifier is tested on wording it has never seen, instead of being rewarded for
memorising the templates. Even so, all of this text is synthetic, so accuracy
measured on it will be higher than on real messages.

Please have someone who knows local lending conduct rules review these
definitions before the demo (PRD section 9.2).
"""

from __future__ import annotations

# --- Normal: friendly reminders sent shortly before a payment is due -------------------
NORMAL_PRE_DUE = [
    "Dear customer, your {lender} loan of UGX {amount} is due on {due_date}. Please pay on time to avoid late fees. Thank you.",
    "Reminder from {lender}: UGX {amount} is due on {due_date}. You can pay through mobile money. Thank you for choosing us.",
    "Hello, this is a friendly reminder that your payment of UGX {amount} falls due on {due_date}.",
    "{lender}: Your repayment of UGX {amount} is due on {due_date}. Ignore this message if you have already paid.",
    "Good morning. Just a reminder that your loan balance of UGX {amount} is due on {due_date}. Contact our help line if you need assistance.",
    "Your loan with {lender} is due soon. Amount: UGX {amount}. Pay before {due_date} to keep your account in good standing.",
    "Hi, a gentle reminder of your upcoming payment of UGX {amount}. Thanks for being a valued customer.",
]
NORMAL_PRE_DUE_HOLDOUT = [
    "Hello from {lender}. We would like to remind you that UGX {amount} will be collected on {due_date}. Please make sure your mobile money wallet has enough balance.",
    "{lender} notice: repayment date approaching. Amount UGX {amount}, date {due_date}. Thank you for banking with us.",
    "Dear valued client, kindly note your loan instalment of UGX {amount} matures on {due_date}. Reply HELP for assistance.",
]

# --- Normal: polite messages sent after a payment has been missed -----------------------
NORMAL_POST_DUE = [
    "Dear customer, we noticed your payment of UGX {amount} was due on {due_date}. If you have a problem, please call us so we can discuss options.",
    "Hello, your payment of UGX {amount} appears to be late. If you have already paid, please ignore this message. If not, kindly pay at your earliest convenience.",
    "Good afternoon. We have not yet received your payment of UGX {amount}. Please let us know if you need more time.",
    "Hi, a polite reminder that your balance of UGX {amount} from {due_date} is still open. Thank you.",
]
NORMAL_POST_DUE_HOLDOUT = [
    "Hello, our records show a pending balance of UGX {amount} that was due on {due_date}. Kindly clear it when you can, or call our office to talk about it.",
    "Dear client, we kindly request that you settle UGX {amount}. If you are facing difficulty, please reach out and we will try to help.",
]

# --- Firm pressure: insistent but lawful ------------------------------------------------
# Two messages mention contacting a reference person or sharing a repayment record.
# They are deliberate hard cases: they mention contacts without shaming anyone.
FIRM_PRESSURE = [
    "Your loan of UGX {amount} is {days_text} overdue. Please pay today to avoid further late fees.",
    "{lender}: Payment of UGX {amount} is overdue. Late fees of UGX {fee} apply. Pay now to stop them growing.",
    "This is a second notice. Your account is overdue by {days_text}. Please settle UGX {amount} immediately.",
    "Your account has been listed as overdue. Late payment may affect your future borrowing limit with {lender}. Pay UGX {amount} today.",
    "We have not received your payment of UGX {amount}. Please pay today or call us to agree a repayment plan.",
    "Final reminder: UGX {amount} is {days_text} late. Failure to pay may lead to the loan being referred to our recovery team.",
    "As stated in your loan agreement, we may contact the reference person you provided if we cannot reach you. Please pay UGX {amount} to avoid this.",
    "Your payment is {days_text} overdue. Please do not ignore this message. Pay UGX {amount} today.",
    "Reminder: interest and fees continue to apply until UGX {amount} is paid in full.",
    "We have tried to reach you several times. Please call us today about your overdue balance of UGX {amount}.",
    "Please note that we may share your repayment record with credit reference agencies if UGX {amount} stays unpaid.",
]
FIRM_PRESSURE_HOLDOUT = [
    "Your repayment of UGX {amount} is {days_text} behind. Clear it today so that extra charges do not pile up on your account.",
    "{lender} notice of default: UGX {amount} remains unpaid after {days_text}. Contact us immediately to arrange payment.",
    "Please treat this as urgent. Your balance of UGX {amount} must be settled today, otherwise your credit record with us will be marked as delinquent.",
]

# --- Threat: sent to the borrower, including several veiled threats ---------------------
THREAT = [
    "Pay UGX {amount} today or we will make you regret it.",
    "We know where you live and work. Pay UGX {amount} now or we will come to you.",
    "If you do not pay in 24 hours you will be arrested. Pay UGX {amount} now.",
    "You are a thief. Pay UGX {amount} or face the police and jail.",
    "Do not test us. Pay UGX {amount} today or we will take your phone and your property.",
    "Last warning. We will make your life very difficult until UGX {amount} is paid.",
    "It would be unfortunate if something happened to you or your family over UGX {amount}. Pay today.",
    "We are sending people to your home tonight. Be ready with UGX {amount}.",
    "Pay UGX {amount} or we will make sure you lose your job.",
    "Your family will suffer if you keep ignoring us. Settle UGX {amount} now.",
]
THREAT_HOLDOUT = [
    "We are tired of waiting. Bring UGX {amount} today or you will see what happens next.",
    "Our agents have your home address. Pay UGX {amount} before tonight or they will pay you a visit.",
    "Failure to clear UGX {amount} will land you in a police cell. This is your last chance.",
]

# --- Shaming: sent to someone other than the borrower (a person in their contacts) ------
SHAMING_THIRD_PARTY = [
    "Hello, a person in your contacts has taken a loan from {lender} and refuses to pay UGX {amount}. They listed you as a reference. Please tell them to pay today.",
    "Dear contact, your friend is a defaulter. They owe {lender} UGX {amount} and have been avoiding us. Please ask them to pay.",
    "Your colleague owes UGX {amount} and is not answering. If they do not pay, we will keep contacting everyone in their phone.",
    "Attention: someone you know is a loan defaulter at {lender}. Tell them to pay UGX {amount} or we will inform their workplace.",
    "We are contacting you because you are in the contact list of a borrower who owes UGX {amount}. They are dodging payment. Please help us.",
    "Your relative has a debt of UGX {amount} with {lender} and is ignoring our calls. Everyone should know they are not honest.",
    "This person has stolen money from {lender}. If you are their friend, tell them to pay UGX {amount} today.",
    "Hello, we are informing you that the owner of your contact has not paid UGX {amount}. We will continue messaging you until they pay.",
    "Your neighbour owes {lender} UGX {amount}. Please tell them we are looking for them.",
    "Dear family member, the person who listed you as a guarantor has defaulted on UGX {amount}. You will be held responsible if they do not pay.",
]
SHAMING_THIRD_PARTY_HOLDOUT = [
    "Good day. You have been given as an emergency contact by a client of {lender} who owes UGX {amount}. They are hiding from us. Please convince them to pay.",
    "Warning to the family and friends of a debtor: this person took money from {lender} and has not repaid UGX {amount}. They are known as a cheat.",
    "We have been told you are close to a borrower who owes UGX {amount} to {lender}. Tell them their name will be circulated to everyone they know.",
]

# --- Shaming: sent straight to the borrower (threatening to expose the debt) ------------
SHAMING_DIRECT = [
    "Everyone in your contact list will know you are a defaulter if you do not pay UGX {amount} today.",
    "We will tell your boss and your family that you do not pay your debts. Pay UGX {amount} now.",
    "Your photo will be shared with all your contacts as a debtor unless UGX {amount} is paid.",
    "Do you want your friends to see that you owe {lender} UGX {amount}? Pay today.",
    "We will post your name as a defaulter if UGX {amount} is not paid by tonight.",
]
SHAMING_DIRECT_HOLDOUT = [
    "Pay UGX {amount} today or your colleagues will receive a message about your debt with {lender}.",
    "Your name and loan details will be sent to everyone on your phone if UGX {amount} is not cleared by tonight.",
]

# Pool name -> (development templates, held-out templates).
# The pool name is stored with every message in the ground-truth database, so a
# message's template can always be traced.
TEMPLATE_POOLS = {
    "normal_pre": (NORMAL_PRE_DUE, NORMAL_PRE_DUE_HOLDOUT),
    "normal_post": (NORMAL_POST_DUE, NORMAL_POST_DUE_HOLDOUT),
    "firm": (FIRM_PRESSURE, FIRM_PRESSURE_HOLDOUT),
    "threat": (THREAT, THREAT_HOLDOUT),
    "shaming_third": (SHAMING_THIRD_PARTY, SHAMING_THIRD_PARTY_HOLDOUT),
    "shaming_direct": (SHAMING_DIRECT, SHAMING_DIRECT_HOLDOUT),
}
