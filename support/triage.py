"""Rule-based ticket triage: category, issue signature, priority and a suggested first reply.

Rules over ML on purpose: they're transparent, a support lead can edit them in minutes, and with
~150 tickets there isn't enough data to train anything trustworthy. Accuracy against hand labels
is measured in support/insights.py, so we know when the rules need work.
"""
import re

# (issue signature, category, regex over subject+body). First match wins, so specific before generic.
SIGNATURES = [
    ("ui_bug", "bug", r"spins|not loading|greyed out|disabled"),
    ("credits_out", "billing_credits", r"out of credits|production is down|all documents failing|refuses uploads"),
    ("webhook_missing", "integration_api", r"webhook|resthook|callback"),
    ("api_401", "integration_api", r"\b401\b|unauthori[sz]ed|authentication error"),
    ("duplicate_docs", "integration_api", r"duplicate|twice"),
    ("polling_timeout", "integration_api", r"time[sd]? out|timeout|polling|ready=false|stuck processing"),
    ("credits_per_page", "billing_credits", r"credits? (for|usage)|used \d+ credits|usage .*calculated|charged"),
    ("merged_weight", "extraction_accuracy", r"weight.*(crazy|billion|stuck together|wrong|doesn.t match|incorrect)|(incorrect|wrong) (total )?weight"),
    ("quantity_words", "extraction_accuracy", r"in words|quantity (comes back )?(blank|empty)|packages.*null|package count"),
    ("checkbox_scan", "extraction_accuracy", r"tick ?box|prepaid|collect was ticked"),
    ("multi_page_lines", "extraction_accuracy", r"page 2|second page|2 of 3"),
    ("id_confusion", "extraction_accuracy", r"sid (field|number)|po number|po#"),
    ("boilerplate_instructions", "extraction_accuracy", r"disclaimer|printed terms"),
    ("ocr_typo", "extraction_accuracy", r"typo|misspelt|letter or two wrong"),
    ("feature_repeating", "feature_request", r"more than one value|multiple trailer|two trailers"),
    ("feature_units", "feature_request", r"convert.*(lbs|kg)|lbs to kg"),
    ("feature_confidence", "feature_request", r"confidence"),
    ("howto_add_field", "how_to", r"add (a |an )?(new |extra )?field|capture an extra field|weight unit"),
    ("howto_email_ingest", "how_to", r"email(ed)? (in|upload)|emailed in"),
    ("howto_export", "how_to", r"export|download|spreadsheet|csv|excel"),
    ("howto_validation", "how_to", r"validation (rules|checks)|flag .* doesn.t look right"),
    ("access", "account_access", r"log ?in|password|access|new user|team member"),
    ("general_accuracy", "extraction_accuracy", r"wrong value|incorrect|extract(ed|ion)?.*wrong|accuracy"),
]
COMPILED = [(sig, cat, re.compile(rx, re.IGNORECASE)) for sig, cat, rx in SIGNATURES]

URGENT = re.compile(r"urgent|production|down|blocked|all (documents|requests)|nothing has processed", re.I)
MONEY = re.compile(r"billed|invoic|billing|wrong party|rejected a load", re.I)

DEFAULT_PRIORITY = {"billing_credits": "P3", "integration_api": "P3", "extraction_accuracy": "P3",
                    "bug": "P3", "account_access": "P3", "how_to": "P4", "feature_request": "P4"}

REPLIES = {
    "merged_weight": "Thanks - this is a known pattern on multi-line BOLs where weights are printed per line with no "
                     "total. Validation flags these for review; we're tuning the field so it returns the document total. "
                     "Could you share 2-3 example document IDs?",
    "quantity_words": "Thanks - the package total on these documents is only printed in words, which the number field "
                      "can't parse yet. These are routed to review; a fix to the field definition is in progress.",
    "checkbox_scan": "Thanks for flagging - tick boxes on phone photos are the hardest case. As of the latest rules, "
                     "freight terms from scanned documents always go to review. Where possible, ask shippers for PDFs.",
    "credits_out": "Looking at this now. Can you confirm the error message from the API? I'm checking your "
                   "organisation's credit balance and will update you within 30 minutes.",
    "webhook_missing": "Looking at this now. Can you send the subscription ID and the time of the last event received? "
                       "I'll check delivery attempts on our side.",
    "api_401": "After rotating a key, every service using the old key gets 401. Please check each environment "
               "variable/secret has the new key; keys can't be viewed again after creation.",
    "credits_per_page": "Credits are charged per page, so a 2-page document uses 2 credits. Happy to review your usage "
                        "if the numbers still don't line up.",
    "howto_export": "You can export confirmed documents from the workspace document list, or pull them via the API. "
                    "Here's the help article: <link>.",
}


def triage(subject, body, tier=""):
    text = f"{subject}\n{body}"
    signature, category = "other", "other"
    for sig, cat, rx in COMPILED:
        if rx.search(text):
            signature, category = sig, cat
            break
    if URGENT.search(text):
        priority = "P1"
    elif MONEY.search(text) or (category == "extraction_accuracy" and signature in ("merged_weight", "checkbox_scan")):
        priority = "P2"
    elif signature == "api_401":
        priority = "P2"
    else:
        priority = DEFAULT_PRIORITY.get(category, "P3")
    if tier == "Enterprise" and priority == "P4" and category not in ("how_to", "feature_request"):
        priority = "P3"
    return {"category": category, "signature": signature, "priority": priority,
            "suggested_reply": REPLIES.get(signature, "")}
