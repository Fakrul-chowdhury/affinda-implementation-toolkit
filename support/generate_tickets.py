"""Generate a synthetic support queue (8 weeks, ~150 tickets) for the support analytics demo.

The issues are modelled on what actually went wrong in the live UAT run (merged weights,
quantities in words, tick boxes on scans...) plus the everyday mix any document-AI support
queue sees (API keys, webhooks, credits, how-to questions). Customers are fictional.

Each ticket carries a hand-assigned `true_category`/`true_issue` so the automatic tagger in
support/triage.py can be *measured*, not just demoed.

    python -m support.generate_tickets
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

CUSTOMERS = {
    "Wattlebird Freight": {"tier": "Onboarding", "docs": "Bills of Lading", "from": datetime(2026, 9, 14)},
    "Bluewater Haulage": {"tier": "Enterprise", "docs": "Bills of Lading", "from": datetime(2026, 8, 17)},
    "Greenleaf Accounting Partners": {"tier": "Growth", "docs": "invoices", "from": datetime(2026, 8, 17)},
    "Pinnacle Claims Co": {"tier": "Enterprise", "docs": "claim forms", "from": datetime(2026, 8, 17)},
    "Copperline Mining Services": {"tier": "Growth", "docs": "delivery dockets", "from": datetime(2026, 8, 17)},
}
BOL_CUSTOMERS = ["Wattlebird Freight", "Bluewater Haulage"]

# issue key: (true_category, true_priority, weight, customers (None = any), [(subject, body), ...])
ISSUES = {
    "merged_weight": ("extraction_accuracy", "P2", 9, BOL_CUSTOMERS, [
        ("Gross weight is a crazy number", "On BOLs with more than one container the gross weight comes through as something like 4425001880.5. Looks like two weights stuck together."),
        ("Weight field wrong on multi-container docs", "Our TMS rejected a load because weight was 8 billion kg. The document lists 8,431.60 KG and 8,320.00 KG separately."),
        ("Incorrect total weight", "The extracted weight doesn't match the total on the bill of lading for multi-line shipments. Can you check?"),
    ]),
    "quantity_words": ("extraction_accuracy", "P3", 5, BOL_CUSTOMERS, [
        ("Quantity blank", "Quantity comes back empty when the total packages is written in words e.g. FIVE HUNDRED AND EIGHTY."),
        ("Package count missing on ocean BOLs", "The # of packages field is null on ocean bills. The doc only has the total in words."),
    ]),
    "checkbox_scan": ("extraction_accuracy", "P2", 6, BOL_CUSTOMERS, [
        ("Freight terms wrong on photographed BOLs", "Drivers send phone photos. Collect was ticked but the extraction says Prepaid. We billed the wrong party."),
        ("Prepaid/Collect mixed up", "Tick box for freight charges is being misread on scanned documents. This affects invoicing."),
    ]),
    "multi_page_lines": ("extraction_accuracy", "P3", 4, BOL_CUSTOMERS, [
        ("Items on page 2 missing", "Our BOL has an attached listing on page 2 with the third container. Container and seal numbers from page 2 are missing."),
        ("Not all containers captured", "Only 2 of 3 container numbers come through when the BOL continues onto a second page."),
    ]),
    "id_confusion": ("extraction_accuracy", "P3", 3, BOL_CUSTOMERS, [
        ("SID number is actually the PO number", "SID field is filled with the PO# from export references. Our BOLs don't have a SID."),
    ]),
    "boilerplate_instructions": ("extraction_accuracy", "P4", 3, BOL_CUSTOMERS, [
        ("Special instructions contain disclaimer", "Special instructions shows CARRIER HAS NOT VERIFIED PARTICULARS which is just printed terms, not an instruction for the driver."),
    ]),
    "ocr_typo": ("extraction_accuracy", "P4", 3, None, [
        ("Typos in extracted text from scans", "Suburb came through as 'Laverton Nonh' instead of Laverton North on a photographed document."),
        ("Misspelt names on scanned docs", "Scanned documents sometimes have a letter or two wrong in names and addresses."),
    ]),
    "general_accuracy": ("extraction_accuracy", "P3", 8, None, [
        ("Field extracted incorrectly", "One of our {docs} came through with the wrong value in a field. Document attached."),
        ("Wrong value extracted", "Extraction picked up the wrong number on a few {docs} this week. Examples attached."),
        ("Accuracy dropped on new template", "A supplier changed their {docs} layout and a couple of fields are now coming through wrong."),
    ]),
    "ui_bug": ("bug", "P3", 4, None, [
        ("Validation screen not loading", "The review screen spins forever for some {docs}. Tried Chrome and Edge."),
        ("Export button greyed out", "Can't export confirmed documents, the button is disabled."),
    ]),
    "credits_per_page": ("billing_credits", "P4", 4, None, [
        ("Charged 2 credits for one document", "Why did a single document use 2 credits? Usage page shows 2 for one upload."),
        ("Credit usage higher than expected", "We uploaded 100 {docs} but used 160 credits. How is usage calculated?"),
    ]),
    "credits_out": ("billing_credits", "P1", 3, None, [
        ("URGENT: API errors, all documents failing", "Every upload is failing since this morning. Production is down. Are we out of credits?"),
        ("Processing stopped", "Nothing has processed for 2 hours, the API refuses uploads. Please help urgently."),
    ]),
    "webhook_missing": ("integration_api", "P1", 4, None, [
        ("Webhook not firing", "Our webhook endpoint stopped receiving events for processed documents. Production integration is blocked."),
        ("No resthook callbacks", "Resthook subscription is active but we get no callbacks since yesterday."),
    ]),
    "api_401": ("integration_api", "P2", 4, None, [
        ("401 Unauthorized after key rotation", "We rotated our API key and now get 401 from the API."),
        ("Authentication error from API", "API returns 401 for all requests from our integration server."),
    ]),
    "polling_timeout": ("integration_api", "P3", 4, None, [
        ("Integration times out waiting for results", "Our integration polls for 60s and gives up on large PDFs. Is there a better way than polling?"),
        ("Document stuck processing", "Polling the document endpoint keeps returning ready=false for big files."),
    ]),
    "duplicate_docs": ("integration_api", "P3", 3, None, [
        ("Duplicate documents created", "When our upload retries after a timeout we end up with the same document twice in the workspace."),
    ]),
    "howto_add_field": ("how_to", "P4", 6, None, [
        ("How do I add a new field?", "We want to capture an extra field on our {docs}. How do we add it to the document type?"),
        ("Adding a weight unit field", "How can we add a field for the weight unit (kg vs lbs)?"),
    ]),
    "howto_email_ingest": ("how_to", "P4", 4, None, [
        ("Set up email upload", "Can documents be emailed in instead of uploaded? Where do I find the address?"),
    ]),
    "howto_export": ("how_to", "P4", 5, None, [
        ("Export to CSV", "How do I export extracted data to a spreadsheet?"),
        ("Download results", "Is there a way to download all confirmed {docs} as a CSV or Excel?"),
    ]),
    "howto_validation": ("how_to", "P4", 4, None, [
        ("How to set up validation checks", "Can we make the system flag {docs} where the total doesn't look right? Where are validation rules configured?"),
    ]),
    "feature_repeating": ("feature_request", "P4", 3, BOL_CUSTOMERS, [
        ("Multiple trailer numbers", "B-doubles have two trailers and two seals. Can the trailer and seal fields hold more than one value?"),
    ]),
    "feature_units": ("feature_request", "P4", 3, BOL_CUSTOMERS, [
        ("Convert lbs to kg", "Some of our shippers' BOLs are in lbs. Could the platform convert weights to kg automatically?"),
    ]),
    "feature_confidence": ("feature_request", "P4", 2, None, [
        ("Confidence scores are null", "The API returns confidence: null on every field. We'd like per-field confidence to decide what to review."),
    ]),
    "access": ("account_access", "P3", 5, None, [
        ("Can't log in", "One of our team can't log in, password reset email not arriving."),
        ("Add a new user", "How do I give a new team member access to our workspace?"),
    ]),
}

# Unseen phrasings: written AFTER the triage rules and never used to tune them, so tagger accuracy on
# these tickets is an honest estimate of how the rules cope with real customers' wording.
HOLDOUT = {
    "merged_weight": [("Load weight way off", "TMS says the consignment weighs 4 billion kilos. Pretty sure that's not right lol")],
    "quantity_words": [("No carton count", "Number of cartons isn't coming through on the port paperwork. It's spelled out on the doc.")],
    "checkbox_scan": [("Customer invoiced incorrectly", "We charged the shipper but the paperwork said receiver pays. It was a photo of the BOL.")],
    "multi_page_lines": [("Missing container", "Shipment had three boxes on the water but we only got two container IDs back.")],
    "general_accuracy": [("Data doesn't match document", "Several {docs} have values that don't match what's printed.")],
    "credits_out": [("Everything failing!!", "None of our docs have gone through today and ops is screaming. What's going on?")],
    "webhook_missing": [("Not getting notified", "Our system isn't being told when documents finish anymore.")],
    "api_401": [("Integration broke after security change", "IT replaced the key as part of a security review and now every call is rejected.")],
    "credits_per_page": [("Bill higher than expected", "Our usage this month is way more than the number of files we sent. Why?")],
    "howto_add_field": [("Capture container size", "Is it possible to also pick up the container size (20ft/40ft)? Where do I set that?")],
    "howto_export": [("Getting data into Excel", "What's the easiest way to get everything into Excel for our finance team?")],
    "access": [("Locked out", "I've been locked out of my account after too many attempts.")],
    "feature_units": [("Imperial weights", "Some shippers use pounds. We need everything in kilos for the TMS.")],
}

SLA_HOURS = {"P1": 1, "P2": 4, "P3": 8, "P4": 24}


def main(seed=7, n=150):
    rng = random.Random(seed)
    start, end = datetime(2026, 8, 17, 8), datetime(2026, 10, 9, 17)
    keys = list(ISSUES)
    weights = [ISSUES[k][2] for k in keys]
    rows = []
    while len(rows) < n:
        key = rng.choices(keys, weights)[0]
        category, priority, _, allowed, templates = ISSUES[key]
        # volume ramps up over the period (new customer onboarding in September)
        offset = (end - start).total_seconds() * (rng.random() ** 0.8)
        created = start + timedelta(seconds=offset)
        customer = rng.choice(allowed or list(CUSTOMERS))
        if created < CUSTOMERS[customer]["from"]:
            continue
        if created.weekday() >= 5:
            created -= timedelta(days=created.weekday() - 4)
        phrasing = "holdout" if key in HOLDOUT and rng.random() < 0.3 else "seen"
        subject, body = rng.choice(HOLDOUT[key] if phrasing == "holdout" else templates)
        body = body.format(docs=CUSTOMERS[customer]["docs"])
        sla = SLA_HOURS[priority]
        first_response_h = round(rng.lognormvariate(0, 0.9) * sla * 0.45, 2)
        resolve_h = round(first_response_h + rng.lognormvariate(1.2, 0.8) * (6 if priority in ("P1", "P2") else 14), 1)
        resolved = created + timedelta(hours=resolve_h)
        status = "resolved" if resolved < end else rng.choice(["open", "pending_customer"])
        rows.append({
            "ticket_id": "",
            "created_at": created.strftime("%Y-%m-%d %H:%M"),
            "customer": customer,
            "tier": CUSTOMERS[customer]["tier"],
            "channel": rng.choice(["email", "email", "portal", "chat"]),
            "subject": subject,
            "body": body,
            "status": status,
            "first_response_hours": first_response_h,
            "resolution_hours": resolve_h if status == "resolved" else "",
            "true_category": category,
            "true_issue": key,
            "true_priority": priority,
            "phrasing": phrasing,
        })
    rows.sort(key=lambda r: r["created_at"])
    for i, r in enumerate(rows, 1):
        r["ticket_id"] = f"SUP-{1000 + i}"
    with open(HERE / "tickets.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} tickets to support/tickets.csv")


if __name__ == "__main__":
    main()
