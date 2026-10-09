"""Score extracted fields against ground truth for UAT.

Different fields need different notions of "correct":
  identifiers (BOL, seal, trailer...)  exact after removing spaces/punctuation case
  numbers                              within 0.5%
  dates                                same calendar date
  choices (freight terms)              same canonical value after synonyms
  free text (names, places, notes)     every ground-truth word present in the extraction
                                       (so "BLUEGUM PANTRY CO. 14 TANNER ST" still counts for
                                       "BLUEGUM PANTRY CO." - the field asks for name and address)
  lists (goods lines)                  every expected line matched, no extras

Outcomes: correct | wrong | missed (expected a value, got none) |
          spurious (expected nothing, got a value) | empty_ok (both empty)
"""
import re
import unicodedata

from .validation import _as_date, _as_number

IDENTIFIER = {"billOfLadingNumber", "sidNumber", "proNumber"}
MULTI_ID = {"trailerNumber", "sealNumber"}
NUMBER = {"grossWeight", "quantity"}
DATE = {"date"}
CHOICE = {"freightTerms"}
LIST = {"descriptionOfGoods"}
# everything else is free text

TERMS_SYNONYMS = {"prepaid": ["pp", "ppd", "pre-paid", "freight prepaid"],
                  "collect": ["cc", "col", "freight collect"],
                  "third party": ["3rd party", "third-party", "3p"]}


def _plain(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", text)).strip().upper()
    return re.sub(r"(\d) (KG|G|L|ML|LB|LBS)\b", r"\1\2", text)  # "15 kg" == "15kg"


def _compact(text):
    return re.sub(r"[^A-Z0-9]", "", _plain(text))


def _words(text):
    return set(_plain(text).split())


def word_recall(expected, actual):
    exp = _words(expected)
    return len(exp & _words(actual)) / len(exp) if exp else 1.0


def _empty(v):
    return v is None or v == "" or v == []


def _id_tokens(value):
    """Split '555728 555111' or ['TRL-1', 'TRL-2'] into compact tokens."""
    items = value if isinstance(value, list) else re.split(r"[\s,/;|]+", str(value))
    return {_compact(i) for i in items if _compact(i)}


def _terms(value):
    t = _plain(value).lower()
    for canon, syns in TERMS_SYNONYMS.items():
        if t == canon or t in syns:
            return canon
    return t


def match(key, expected, actual):
    """Return (outcome, note)."""
    if _empty(expected) and _empty(actual):
        return "empty_ok", ""
    if _empty(actual):
        return "missed", ""
    if _empty(expected):
        return "spurious", f"got '{actual}' where the document has none"

    if key in IDENTIFIER:
        ok = _compact(expected) == _compact(actual)
    elif key in MULTI_ID:
        exp, act = _id_tokens(expected), _id_tokens(actual)
        ok = exp == act
        if not ok:
            return "wrong", f"expected {sorted(exp)}, got {sorted(act)}"
    elif key in NUMBER:
        a = _as_number(actual)
        ok = a is not None and abs(a - float(expected)) <= max(0.005 * abs(float(expected)), 0.01)
    elif key in DATE:
        ok = _as_date(actual) == _as_date(expected)
    elif key in CHOICE:
        ok = _terms(expected) == _terms(actual)
    elif key in LIST:
        act = actual if isinstance(actual, list) else [actual]
        unmatched = [e for e in expected if not any(word_recall(e, a) >= 0.75 for a in act)]
        ok = not unmatched and len(act) == len(expected)
        if not ok:
            return "wrong", f"{len(expected) - len(unmatched)}/{len(expected)} lines found, {len(act)} returned"
    else:
        ok = word_recall(expected, actual) >= 0.99

    return ("correct", "") if ok else ("wrong", f"expected '{expected}', got '{actual}'")


def score_document(fields, truth):
    """fields: normalised ExtractedField dict. Returns list of per-field result dicts."""
    rows = []
    for key, fld in fields.items():
        expected = truth.get(key)
        actual = fld.value
        outcome, note = match(key, expected, actual)
        rows.append({"field": key, "expected": expected, "actual": actual, "raw": fld.raw,
                     "outcome": outcome, "note": note})
    return rows
