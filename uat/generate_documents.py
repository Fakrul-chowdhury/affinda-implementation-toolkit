"""Generate the synthetic UAT document set + ground truth.

Three layouts Wattlebird Freight (fictional) receives:
  A  domestic   - Wattlebird's own road BOL template (AU dates, kg, B-double trailers)
  B  vics       - a US-standard "VICS" straight BOL used by an importing shipper (lbs, checkboxes)
  C  ocean      - an ocean BOL for container cartage from the port (multi-container, packages in words)
Plus "_scan" variants: rasterised, rotated, blurred and JPEG-compressed like a driver's phone photo.

Everything is seeded, so re-running produces identical files. All companies are fictional.

    python -m uat.generate_documents
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
DOCS = HERE / "documents"
TRUTH = HERE / "ground_truth"

SHIPPERS = [
    ("BLUEGUM PANTRY CO.", "14 Tanner Street", "Botany NSW 2019"),
    ("SALTBUSH HARDWARE PTY LTD", "88 Foundry Road", "Seven Hills NSW 2147"),
    ("IRONBARK BUILDING SUPPLIES", "3 Quarry Lane", "Dandenong VIC 3175"),
    ("CORAL BAY BEVERAGES", "220 Brickworks Drive", "Yatala QLD 4207"),
    ("MALLEE GRAIN TRADERS", "9 Silo Crescent", "Kewdale WA 6105"),
    ("RIVERBEND FURNITURE", "41 Mill Street", "Wingfield SA 5013"),
    ("KOOKABURRA KITCHENWARE", "17 Enterprise Way", "Laverton North VIC 3026"),
]
CONSIGNEES = [
    ("HARBOURSIDE RETAIL GROUP", "5 Pier Street", "Newcastle NSW 2300"),
    ("INLAND RURAL SUPPLIES", "120 Sturt Highway", "Wagga Wagga NSW 2650"),
    ("NORTHGATE DISTRIBUTION CENTRE", "66 Logistics Boulevard", "Townsville QLD 4810"),
    ("SOUTHERLY HOME STORES", "2 Esplanade", "Geelong VIC 3220"),
    ("RED GUM CO-OPERATIVE", "31 Railway Parade", "Mildura VIC 3500"),
    ("TIDEWATER CATERING", "77 Marina Drive", "Cairns QLD 4870"),
]
GOODS = [
    ("CTN", "Canned tomatoes 24 x 400g", 14.2), ("CTN", "Stainless cookware sets", 9.8),
    ("PLT", "Bagged cement 40 x 20kg", 820.0), ("PLT", "Bottled sparkling water", 640.0),
    ("CTN", "Flat-pack bookshelves", 31.5), ("BAG", "Malting barley 25kg", 25.4),
    ("CTN", "Garden hose reels", 6.3), ("PLT", "Ceramic floor tiles", 910.0),
    ("CTN", "Dry pet food 15kg", 15.6), ("DRM", "Food-grade canola oil 200L", 188.0),
]
INSTRUCTIONS = [
    "Call consignee 30 minutes before arrival.", "Tail-lift required at delivery.",
    "Do not double stack.", "Deliver between 7AM and 3PM weekdays only.",
    "Keep dry. Fragile - handle with care.", "", "",
]

ONES = "ZERO ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE TEN ELEVEN TWELVE THIRTEEN FOURTEEN FIFTEEN " \
       "SIXTEEN SEVENTEEN EIGHTEEN NINETEEN".split()
TENS = "_ _ TWENTY THIRTY FORTY FIFTY SIXTY SEVENTY EIGHTY NINETY".split()


def in_words(n):
    """Number to words, the way it appears in 'total packages in words' boxes."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return ONES[n // 100] + " HUNDRED" + ("" if rest == 0 else " AND " + in_words(rest))
    rest = n % 1000
    return in_words(n // 1000) + " THOUSAND" + ("" if rest == 0 else (" AND " if rest < 100 else " ") + in_words(rest))


def _box(c, x, y, w, h, title=None, size=7):
    c.rect(x, y, w, h)
    if title:
        c.setFont("Helvetica-Bold", size)
        c.drawString(x + 4, y + h - 10, title)


def _lines(c, x, y, lines, size=9, leading=11, font="Helvetica"):
    c.setFont(font, size)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * leading, line)


def _check(c, x, y, label, ticked):
    c.rect(x, y, 8, 8)
    if ticked:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 1.3, y + 1, "X")
    c.setFont("Helvetica", 8)
    c.drawString(x + 12, y + 1, label)


def _items(rng, n, unit_scale=1.0):
    picks = rng.sample(GOODS, n)
    items = []
    for pkg, desc, unit_w in picks:
        qty = rng.randint(1, 18) if pkg in ("PLT", "DRM") else rng.randint(10, 160)
        items.append({"pkg": pkg, "qty": qty, "desc": desc, "weight": round(qty * unit_w * unit_scale, 1)})
    return items


# --------------------------------------------------------------------------- layout A
def layout_domestic(path, rng, d, scenario):
    s, cn = rng.choice(SHIPPERS), rng.choice(CONSIGNEES)
    items = _items(rng, rng.randint(1, 3))
    terms = "Collect" if "collect" in scenario else "Prepaid"
    trailers = [f"TRL-{rng.randint(1000, 9999)}" for _ in range(2 if "bdouble" in scenario else 1)]
    seals = [f"SL{rng.randint(100000, 999999)}" for _ in trailers]
    bol = f"WBF{rng.randint(100000, 999999)}"
    pro = f"{rng.randint(4000000, 4999999)}"
    instr = rng.choice(INSTRUCTIONS)

    c = canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    c.setFont("Helvetica-Bold", 18)
    c.drawString(36, H - 50, "WATTLEBIRD FREIGHT")
    c.setFont("Helvetica", 8)
    c.drawString(36, H - 62, "Road Transport  |  ABN 00 000 000 000 (demo)  |  Fictional company for testing")
    c.setFont("Helvetica-Bold", 13)
    c.drawRightString(W - 36, H - 50, "BILL OF LADING")
    _lines(c, W - 210, H - 68, [f"BOL No: {bol}", f"Date: {d.strftime('%d/%m/%Y')}", f"Con Note (Pro) No: {pro}"], size=9)

    top = H - 110
    _box(c, 36, top - 90, 255, 90, "SHIPPER (PICK UP FROM)")
    _lines(c, 42, top - 24, [s[0], s[1], s[2]])
    _box(c, 304, top - 90, 255, 90, "CONSIGNEE (DELIVER TO)")
    _lines(c, 310, top - 24, [cn[0], cn[1], cn[2]])

    y = top - 150
    _box(c, 36, y, 523, 50, "TRANSPORT DETAILS")
    _lines(c, 42, y + 26, [f"Origin: {s[2].rsplit(' ', 2)[0]}", f"Destination: {cn[2].rsplit(' ', 2)[0]}"], size=8.5)
    _lines(c, 220, y + 26, [f"Trailer No: {' / '.join(trailers)}", f"Seal No: {' / '.join(seals)}"], size=8.5)
    _lines(c, 420, y + 26, ["Carrier: Wattlebird Freight", "Vehicle: B-DOUBLE" if len(trailers) > 1 else "Vehicle: SEMI"], size=8.5)

    # goods table
    y -= 20
    c.setFont("Helvetica-Bold", 8)
    for x, h in ((42, "QTY"), (80, "TYPE"), (120, "DESCRIPTION OF GOODS"), (470, "WEIGHT (KG)")):
        c.drawString(x, y, h)
    c.line(36, y - 4, 559, y - 4)
    for i, it in enumerate(items):
        yy = y - 18 - i * 15
        _lines(c, 42, yy, [str(it["qty"])], size=9)
        _lines(c, 80, yy, [it["pkg"]], size=9)
        _lines(c, 120, yy, [it["desc"]], size=9)
        _lines(c, 470, yy, [f"{it['weight']:,.1f}"], size=9)
    total_qty = sum(i["qty"] for i in items)
    total_w = round(sum(i["weight"] for i in items), 1)
    yy = y - 30 - len(items) * 15
    c.line(36, yy + 10, 559, yy + 10)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(42, yy - 2, f"{total_qty}")
    c.drawString(120, yy - 2, "TOTALS")
    c.drawString(470, yy - 2, f"{total_w:,.1f}")

    y = yy - 70
    _box(c, 36, y, 255, 50, "FREIGHT CHARGES")
    _check(c, 44, y + 18, "Prepaid", terms == "Prepaid")
    _check(c, 120, y + 18, "Collect", terms == "Collect")
    _check(c, 190, y + 18, "Third Party", False)
    _box(c, 304, y, 255, 50, "SPECIAL INSTRUCTIONS")
    _lines(c, 310, y + 24, [instr], size=8.5)
    _lines(c, 36, y - 40, ["Received in apparent good order and condition. Shipper signature: ____________________",
                            "Driver signature: ____________________    Date: ____________"], size=8)
    c.save()

    return {
        "billOfLadingNumber": bol, "date": d.isoformat(), "sidNumber": None, "proNumber": pro,
        "shipper": s[0], "origin": s[2].rsplit(" ", 2)[0], "consignee": cn[0], "destination": cn[2].rsplit(" ", 2)[0],
        "carrier": "Wattlebird Freight", "trailerNumber": trailers, "sealNumber": seals,
        "grossWeight": total_w, "quantity": total_qty, "descriptionOfGoods": [i["desc"] for i in items],
        "freightTerms": terms, "specialInstructions": instr or None,
    }


# --------------------------------------------------------------------------- layout B
US_SHIPPERS = [("PRAIRIE HOLLOW TOOLWORKS INC.", "410 Commerce Pkwy, Tulsa, OK 74107"),
               ("CEDAR FORGE APPLIANCES LLC", "9 Harbor Point Rd, Savannah, GA 31401"),
               ("BLUE MESA OUTDOOR GEAR", "2200 Canyon Dr, Phoenix, AZ 85034")]
US_CARRIERS = ["Lone Pine Express Inc", "Prairie Line Trucking LLC", "Silver Creek Haulers"]


def layout_vics(path, rng, d, scenario):
    s, cn = rng.choice(US_SHIPPERS), rng.choice(CONSIGNEES)
    carrier = rng.choice(US_CARRIERS)
    items = _items(rng, rng.randint(2, 3), unit_scale=2.2046)  # lbs
    terms = "Third Party" if "thirdparty" in scenario else rng.choice(["Prepaid", "Collect"])
    bol = f"{d.year}-{rng.randint(10000, 99999)}"
    sid = f"SID-{rng.randint(100000, 999999)}"
    pro = None if "nopro" in scenario else f"{rng.randint(100000, 999999)}"
    trailer, seal = f"{rng.randint(1000, 9999)}", f"{rng.randint(10000, 99999)}"
    instr = rng.choice(INSTRUCTIONS) or "Notify consignee on arrival at port."
    dest = cn[2].rsplit(" ", 2)[0]

    c = canvas.Canvas(str(path), pagesize=LETTER)
    W, H = LETTER
    c.setFont("Helvetica-Bold", 20)
    c.drawString(36, H - 50, "Bill of Lading")
    c.setFont("Helvetica", 7)
    c.drawString(36, H - 62, "Straight Bill of Lading - Short Form - Not Negotiable")
    _box(c, 330, H - 72, 246, 36)
    _lines(c, 336, H - 50, [f"Date: {d.strftime('%B %d, %Y')}", f"Bill of Lading Number: {bol}"], size=9)

    _box(c, 36, H - 160, 290, 80, "SHIP FROM")
    _lines(c, 42, H - 104, [s[0].title(), s[1], f"SID#: {sid}"], size=8.5)
    _box(c, 36, H - 250, 290, 84, "SHIP TO")
    _lines(c, 42, H - 194, [cn[0].title(), f"{cn[1]}, {cn[2]}", "Australia (via Port of Brisbane)"], size=8.5)

    _box(c, 330, H - 160, 246, 80, "CARRIER")
    lines = [f"Carrier Name: {carrier}", f"Trailer Number: {trailer}", f"Seal Number(s): {seal}", "SCAC: DEMO"]
    if pro:
        lines.append(f"Pro Number: {pro}")
    _lines(c, 336, H - 104, lines, size=8.5, leading=10)
    _box(c, 330, H - 250, 246, 84, "FREIGHT CHARGE TERMS (prepaid unless marked otherwise)")
    _check(c, 338, H - 205, "Prepaid", terms == "Prepaid")
    _check(c, 408, H - 205, "Collect", terms == "Collect")
    _check(c, 478, H - 205, "3rd Party", terms == "Third Party")

    _box(c, 36, H - 300, 540, 44, "SPECIAL INSTRUCTIONS")
    _lines(c, 42, H - 284, [instr], size=8.5)

    y = H - 330
    c.setFont("Helvetica-Bold", 8)
    for x, h in ((42, "HANDLING UNIT QTY"), (140, "TYPE"), (180, "WEIGHT (LBS)"), (260, "COMMODITY DESCRIPTION")):
        c.drawString(x, y, h)
    c.line(36, y - 4, 576, y - 4)
    for i, it in enumerate(items):
        yy = y - 18 - i * 15
        _lines(c, 42, yy, [str(it["qty"])], size=9)
        _lines(c, 140, yy, [it["pkg"]], size=9)
        _lines(c, 180, yy, [f"{it['weight']:,.0f}"], size=9)
        _lines(c, 260, yy, [it["desc"]], size=9)
    total_qty = sum(i["qty"] for i in items)
    total_w = round(sum(round(i["weight"]) for i in items))
    yy = y - 30 - len(items) * 15
    c.line(36, yy + 10, 576, yy + 10)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(42, yy - 2, str(total_qty))
    c.drawString(180, yy - 2, f"{total_w:,}")
    c.drawString(260, yy - 2, "GRAND TOTAL")
    _lines(c, 36, yy - 50, ["RECEIVED, subject to individually determined rates or contracts agreed in writing between",
                             "the carrier and shipper. Shipper Signature: ________________  Carrier Signature: ________________"], size=7)
    c.save()

    return {
        "billOfLadingNumber": bol, "date": d.isoformat(), "sidNumber": sid, "proNumber": pro,
        "shipper": s[0], "origin": s[1].split(", ", 1)[1], "consignee": cn[0], "destination": dest,
        "carrier": carrier, "trailerNumber": [trailer], "sealNumber": [seal],
        "grossWeight": total_w, "quantity": total_qty, "descriptionOfGoods": [i["desc"] for i in items],
        "freightTerms": terms, "specialInstructions": instr, "_notes": "weights printed in LBS",
    }


# --------------------------------------------------------------------------- layout C
OCEAN_CARRIERS = ["ZEPHYR OCEAN LINES", "SOUTHERN MERIDIAN SHIPPING"]
PORTS = [("NINGBO, CHINA", "PORT BOTANY, SYDNEY"), ("BUSAN, KOREA", "PORT OF MELBOURNE"),
         ("LAEM CHABANG, THAILAND", "PORT OF BRISBANE")]


def layout_ocean(path, rng, d, scenario):
    s, cn = rng.choice(SHIPPERS), rng.choice(CONSIGNEES)
    carrier = rng.choice(OCEAN_CARRIERS)
    pol, pod = rng.choice(PORTS)
    n_cont = 2 if "multi" in scenario else 1
    conts = []
    for _ in range(n_cont):
        items = _items(rng, rng.randint(1, 2))
        conts.append({"no": f"{rng.choice(['ZOLU', 'SMSU', 'TGHU'])}{rng.randint(100000, 999999)}-{rng.randint(0, 9)}",
                      "seal": f"{rng.randint(100000, 999999)}", "items": items})
    bol = f"{carrier[:2]}{rng.randint(10**11, 10**12 - 1)}"
    terms = rng.choice(["Prepaid", "Collect"])
    total_qty = sum(i["qty"] for ct in conts for i in ct["items"])
    total_w = round(sum(i["weight"] for ct in conts for i in ct["items"]), 2)

    c = canvas.Canvas(str(path), pagesize=A4)
    W, H = A4
    c.setFont("Helvetica-Bold", 15)
    c.drawString(36, H - 48, carrier)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(36, H - 64, "BILL OF LADING: PORT TO PORT")
    _lines(c, 360, H - 48, [f"BOL NO: {bol}", f"DATE OF ISSUE: {d.strftime('%d-%b-%Y').upper()}"], size=9, font="Helvetica-Bold")

    _box(c, 36, H - 170, 260, 92, "SHIPPER:")
    _lines(c, 42, H - 104, [s[0], s[1].upper(), "C/O EXPORT AGENT", pol], size=8.5)
    _box(c, 300, H - 170, 259, 92, "CONSIGNEE:")
    _lines(c, 306, H - 104, [cn[0], cn[1].upper(), cn[2].upper(), "AUSTRALIA"], size=8.5)
    _box(c, 36, H - 215, 523, 40, "")
    _lines(c, 42, H - 188, [f"PORT OF LOADING: {pol}", f"PORT OF DISCHARGE: {pod}"], size=8.5)
    _lines(c, 300, H - 188, [f"VESSEL: {rng.choice(['MV CORAL TIDE', 'MV SOUTHERN STAR'])}", f"VOYAGE NO: {rng.randint(100, 999)}S"], size=8.5)

    y = H - 240
    c.setFont("Helvetica-Bold", 7.5)
    for x, h in ((42, "MARKS & NUMBERS"), (160, "# PKGS"), (210, "DESCRIPTION OF GOODS"), (470, "GROSS WEIGHT (KGS)")):
        c.drawString(x, y, h)
    c.line(36, y - 4, 559, y - 4)
    yy = y - 18
    for ct in conts:
        cont_qty = sum(i["qty"] for i in ct["items"])
        cont_w = sum(i["weight"] for i in ct["items"])
        _lines(c, 42, yy, ["40' CONTAINER NO:", ct["no"], f"SEAL NO: {ct['seal']}"], size=8)
        _lines(c, 160, yy, [str(cont_qty)], size=8.5)
        _lines(c, 210, yy, [f"{i['qty']} {i['pkg']}S {i['desc'].upper()}" for i in ct["items"]], size=8)
        _lines(c, 470, yy, [f"{cont_w:,.2f} KG"], size=8.5)
        yy -= 50
    c.line(36, yy + 20, 559, yy + 20)
    _box(c, 36, yy - 20, 523, 30, "")
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(42, yy - 9, "TOTAL NO. OF PKGS IN WORDS:")
    c.drawString(300, yy - 9, in_words(total_qty))
    _box(c, 36, yy - 70, 523, 46, "")
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(42, yy - 45, "OCEAN FREIGHT")
    c.drawString(200, yy - 35, "PREPAID")
    c.drawString(330, yy - 35, "COLLECT")
    c.drawString(200 if terms == "Prepaid" else 330, yy - 55, f"AUD ${rng.randint(18, 60) * 100:,}")
    c.line(190, yy - 70, 190, yy - 24)
    c.line(320, yy - 70, 320, yy - 24)
    c.line(450, yy - 70, 450, yy - 24)
    c.drawString(458, yy - 45, "ORIGINALS: 3")
    _lines(c, 36, yy - 95, ["CARRIER HAS NOT VERIFIED PARTICULARS FURNISHED BY MERCHANT.",
                            f"CARRIER: {carrier} - SIGNATURE / DATE: ______________________"], size=7.5)
    c.save()

    return {
        "billOfLadingNumber": bol, "date": d.isoformat(), "sidNumber": None, "proNumber": None,
        "shipper": s[0], "origin": pol, "consignee": cn[0], "destination": pod,
        "carrier": carrier, "trailerNumber": [ct["no"] for ct in conts], "sealNumber": [ct["seal"] for ct in conts],
        "grossWeight": total_w, "quantity": total_qty,
        "descriptionOfGoods": [i["desc"] for ct in conts for i in ct["items"]],
        "freightTerms": terms, "specialInstructions": None,
        "_notes": "total packages only printed in words; weights printed per container, no total",
    }


# --------------------------------------------------------------------------- scans
def make_scan(pdf_path, out_path, rng):
    """Rasterise page 1 and degrade it like a phone photo of a crumpled document."""
    import fitz  # PyMuPDF
    from PIL import Image, ImageFilter, ImageEnhance

    page = fitz.open(str(pdf_path))[0]
    pix = page.get_pixmap(dpi=120)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    img = img.rotate(rng.uniform(-3.5, 3.5), expand=True, fillcolor=(205, 200, 190))
    img = ImageEnhance.Contrast(img).enhance(0.75)
    img = ImageEnhance.Brightness(img).enhance(0.93)
    img = img.filter(ImageFilter.GaussianBlur(0.9))
    img.save(out_path, "JPEG", quality=38)


PLAN = [
    # (doc_id, layout, scenario tags, days before 2026-10-09)
    ("A01", "domestic", "clean", 3), ("A02", "domestic", "clean", 6), ("A03", "domestic", "collect", 2),
    ("A04", "domestic", "bdouble", 4), ("A05", "domestic", "bdouble collect", 9),
    ("B01", "vics", "clean lbs", 12), ("B02", "vics", "lbs thirdparty", 20), ("B03", "vics", "lbs nopro", 7),
    ("B04", "vics", "lbs", 15),
    ("C01", "ocean", "words", 25), ("C02", "ocean", "multi words", 31), ("C03", "ocean", "multi words", 18),
    ("C04", "ocean", "words", 40),
]
SCANS = ["A01", "A04", "B01", "C02"]
LAYOUTS = {"domestic": layout_domestic, "vics": layout_vics, "ocean": layout_ocean}

# Hand-labelled ground truth for the two real sample documents from the original FreightRead repo.
REAL = {
    "R01": ("BillOfLading.pdf", "ocean (real sample, 2 pages)", {
        "billOfLadingNumber": "EG00055802323028", "date": "2021-08-10", "sidNumber": None, "proNumber": None,
        "shipper": "WILD HEALTH FOODS PTY LTD", "origin": "FREMANTLE",
        "consignee": "LAIHEE KUNG SUPERMARKET GROUP", "destination": "SINGAPORE", "carrier": "ZESTADO LOGISTICS",
        "trailerNumber": ["EXGU3024389-2", "EXGU3024111-5", "EXGU3024132-6"],
        "sealNumber": ["555728", "555111", "555423"], "grossWeight": 10165.5, "quantity": 580,
        "descriptionOfGoods": ["20 X 1KG BXS ORGANIC MUESLI PER CARTON", "25 CTRS OF 500G SUPERFOOD SHAKE PER CARTON",
                               "CRTNS WITH ASSORTED MIX OF PKTS OF BARS & BALLS"],
        "freightTerms": "Prepaid", "specialInstructions": "FREIGHT COUNTED BY SHIPPER. CUSTOM CHECK ON ARRIVAL.",
        "_notes": "3rd container only on page 2; total weight not printed (sum of 3 lines); date is the invoice date",
    }),
    "R02": ("Bill_of_Lading_final_sample.pdf", "vics (real sample)", {
        "billOfLadingNumber": "2026-00471", "date": "2026-04-09", "sidNumber": "2026-00471", "proNumber": "994421",
        "shipper": "Blue Ridge Auto Parts Co.", "origin": "Dallas, TX", "consignee": "Pacific Distribution Ltd.",
        "destination": "Los Angeles, CA", "carrier": "TransAmerica Trucking LLC", "trailerNumber": ["8842"],
        "sealNumber": ["44921"], "grossWeight": 1240.0, "quantity": 48,
        "descriptionOfGoods": ["Auto engine components", "Brake assembly units", "Suspension parts"],
        "freightTerms": "Prepaid", "specialInstructions": "Handle with care. Deliver between 8AM-4PM weekdays only.",
    }),
}


def main():
    DOCS.mkdir(exist_ok=True)
    TRUTH.mkdir(exist_ok=True)
    today = date(2026, 10, 9)
    manifest = []
    for doc_id, layout, scenario, age in PLAN:
        rng = random.Random(doc_id)  # per-document seed: adding a doc never changes the others
        path = DOCS / f"{doc_id}_{layout}.pdf"
        truth = LAYOUTS[layout](path, rng, today - timedelta(days=age), scenario)
        manifest.append({"doc_id": doc_id, "file": path.name, "layout": layout, "scenario": scenario, "source": "synthetic"})
        (TRUTH / f"{doc_id}.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
        if doc_id in SCANS:
            scan_id = f"{doc_id}S"
            scan_path = DOCS / f"{scan_id}_{layout}_scan.jpg"
            make_scan(path, scan_path, random.Random(scan_id))
            manifest.append({"doc_id": scan_id, "file": scan_path.name, "layout": layout,
                             "scenario": scenario + " phone-scan", "source": "synthetic"})
            (TRUTH / f"{scan_id}.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    samples = HERE.parent / "samples"
    for doc_id, (fname, layout, truth) in REAL.items():
        manifest.append({"doc_id": doc_id, "file": f"samples/{fname}", "layout": layout.split()[0],
                         "scenario": layout, "source": "real sample"})
        (TRUTH / f"{doc_id}.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
        assert (samples / fname).exists(), fname

    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} documents ({len(PLAN)} synthetic PDFs, {len(SCANS)} scans, {len(REAL)} real).")


if __name__ == "__main__":
    main()
