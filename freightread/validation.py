"""Customer-configurable validation rules for extracted Bill of Lading data.

Rules live in YAML (rules/<customer>.yaml), not code, because every customer's
rules differ: one carrier always has a Pro number, another never does. An
implementation specialist should be able to change a rule without a deploy.

Each finding has a severity:
  error   - the value is wrong or missing and must be fixed before export
  warning - plausible but suspicious; a human should glance at it
Document status:
  PASS    - no findings, safe for straight-through processing
  REVIEW  - warnings only
  FAIL    - at least one error
"""
import re
from dataclasses import dataclass
from datetime import date, datetime

import yaml

from .normalize import LABELS


@dataclass
class Finding:
    field: str
    rule: str
    severity: str  # "error" | "warning"
    message: str


def load_rules(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _as_date(value):
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _as_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(re.sub(r"[^\d.\-]", "", str(value)))
    except ValueError:
        return None


def iso6346_check_digit(code10):
    """Check digit for a shipping container number (ISO 6346), e.g. CSQU305438 -> 3."""
    values, v = {}, 10
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        if v % 11 == 0:  # values that are multiples of 11 are skipped
            v += 1
        values[ch] = v
        v += 1
    total = sum((values[c] if c.isalpha() else int(c)) * 2 ** i for i, c in enumerate(code10.upper()))
    return total % 11 % 10


def _fmt(num):
    return f"{num:,.2f}".rstrip("0").rstrip(".")


NUMBER_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _check_field(key, fld, rule, today, doc):
    """Yield findings for one field against its rule block."""
    label = LABELS.get(key, key)
    sev = rule.get("severity", "error")

    if not fld.found:
        if rule.get("required"):
            yield Finding(key, "required", sev, f"{label} is missing.")
        return

    value, raw = fld.value, fld.raw or ""

    # Affinda read text but couldn't normalise it (e.g. a quantity written in words).
    if rule.get("type") in ("number", "date") and any(v.raw and v.parsed in (None, "") for v in fld.values):
        yield Finding(key, "parse_failed", "error",
                      f"{label}: text '{raw}' was found but could not be converted to a {rule['type']}.")
        return

    if rule.get("type") == "number":
        num = _as_number(value)
        if num is None:
            yield Finding(key, "number", "error", f"{label} '{value}' is not a number.")
            return
        # Several numbers in the raw text usually means separate values were merged.
        tokens = NUMBER_TOKEN.findall(raw)
        if len(tokens) > 1:
            yield Finding(key, "multiple_numbers_in_raw", "error",
                          f"{label}: source text '{raw}' holds {len(tokens)} numbers but one value ({_fmt(num)}) was "
                          f"returned - likely merged. Expected a single total.")
        if "min" in rule and num < rule["min"]:
            yield Finding(key, "min", sev, f"{label} {_fmt(num)} is below the minimum of {rule['min']}.")
        if "max" in rule and num > rule["max"]:
            yield Finding(key, "max", sev, f"{label} {_fmt(num)} is above the plausible maximum of {rule['max']:,}.")
        if rule.get("integer") and num != int(num):
            yield Finding(key, "integer", sev, f"{label} {_fmt(num)} should be a whole number.")

    if rule.get("type") == "date":
        d = _as_date(value)
        if d is None:
            yield Finding(key, "date", "error", f"{label} '{value}' is not a recognisable date.")
        else:
            if rule.get("not_future") and d > today:
                yield Finding(key, "not_future", sev, f"{label} {d} is in the future.")
            if "max_age_days" in rule and (today - d).days > rule["max_age_days"]:
                yield Finding(key, "max_age_days", rule.get("age_severity", "warning"),
                              f"{label} {d} is more than {rule['max_age_days']} days old - stale or wrong document?")

    if "pattern" in rule:
        values = value if isinstance(value, list) else [value]
        for v in values:
            if not re.fullmatch(rule["pattern"], str(v).strip(), flags=re.IGNORECASE):
                yield Finding(key, "pattern", sev,
                              f"{label} '{v}' doesn't match the expected format ({rule.get('pattern_hint', rule['pattern'])}).")

    if "allowed_values" in rule:
        canonical = normalise_choice(value, rule)
        if canonical is None:
            yield Finding(key, "allowed_values", sev,
                          f"{label} '{value}' is not one of: {', '.join(rule['allowed_values'])}.")

    if "token_pattern" in rule and not fld.multiple:
        # e.g. two container numbers squeezed into one single-value field
        tokens = re.findall(rule["token_pattern"], raw, flags=re.IGNORECASE)
        if len(tokens) > rule.get("max_tokens", 1):
            yield Finding(key, "multiple_values", rule.get("multi_severity", "warning"),
                          f"{label} contains {len(tokens)} values ({', '.join(tokens)}) in one field. "
                          f"Configure it as a repeating field or confirm with the customer which one is needed.")

    if "min_items" in rule and isinstance(value, list) and len(value) < rule["min_items"]:
        yield Finding(key, "min_items", sev, f"{label}: expected at least {rule['min_items']} item(s).")

    if "max_length" in rule and len(str(value)) > rule["max_length"]:
        yield Finding(key, "max_length", rule.get("length_severity", "warning"),
                      f"{label} is {len(str(value))} characters - it may have absorbed neighbouring text "
                      f"(limit {rule['max_length']}).")

    if "boilerplate" in rule:
        # standard printed clauses that sometimes get read as the field's value
        text = str(value).upper()
        if any(phrase.upper() in text for phrase in rule["boilerplate"]):
            yield Finding(key, "boilerplate", rule.get("boilerplate_severity", "warning"),
                          f"{label} looks like standard printed terms, not a real instruction: '{value}'.")

    if rule.get("check_digit") == "iso6346":
        for token in re.findall(r"\b[A-Z]{4}\d{6}-?\d\b", raw.upper()):
            digits = token.replace("-", "")
            if iso6346_check_digit(digits[:10]) != int(digits[10]):
                yield Finding(key, "check_digit", "error",
                              f"{label} {token} fails the ISO 6346 check digit - likely a misread character.")

    if rule.get("review_if_scanned") and doc.get("scanned"):
        yield Finding(key, "review_if_scanned", "warning",
                      f"{label} came from a scanned/photographed page - {rule.get('scan_reason', 'confirm it visually')}.")

    conf = fld.confidence
    if conf is not None and "min_confidence" in rule and conf < rule["min_confidence"]:
        yield Finding(key, "low_confidence", "warning",
                      f"{label} confidence {conf:.2f} is below {rule['min_confidence']}.")


def normalise_choice(value, rule):
    """Map a free-text value onto the customer's allowed list using synonyms. None if no match."""
    if value is None:
        return None
    text = str(value).strip().lower()
    for allowed in rule["allowed_values"]:
        if text == allowed.lower():
            return allowed
    for allowed, synonyms in (rule.get("synonyms") or {}).items():
        if any(text == s.lower() for s in synonyms):
            return allowed
    return None


def _cross_field(fields, cross_rules):
    for rule in cross_rules or []:
        if rule["type"] == "review_if_multiple":
            # e.g. several containers on one BOL: totals are often taken from one line only
            src = fields[rule["field"]]
            n = len(re.findall(rule["token_pattern"], src.raw or "", flags=re.IGNORECASE))
            if n > 1:
                for target in rule["review"]:
                    if fields[target].found:
                        yield Finding(target, "multi_line_total", "warning",
                                      f"{LABELS[target]}: document has {n} {rule.get('noun', 'lines')} - confirm "
                                      f"{fields[target].value} is the total, not a single line.")
            continue
        if rule["type"] == "different":
            a, b = (fields[k] for k in rule["fields"])
            if a.found and b.found and str(a.value).strip().lower() == str(b.value).strip().lower():
                yield Finding(rule["fields"][1], "different", rule.get("severity", "warning"),
                              f"{LABELS[rule['fields'][0]]} and {LABELS[rule['fields'][1]]} are identical "
                              f"('{a.value}') - probably the wrong block was read.")


def validate(fields, rules, today=None, doc=None):
    """Validate normalised fields. Returns (status, findings, per-field status dict).

    doc: document-level facts from normalize.document_info(), e.g. {"scanned": True}.
    """
    today = today or date.today()
    doc = doc or {}
    findings = []
    for key, rule in (rules.get("fields") or {}).items():
        if key in fields:
            findings.extend(_check_field(key, fields[key], rule, today, doc))
    findings.extend(_cross_field(fields, rules.get("cross_field")))

    per_field = {k: "ok" if f.found else "empty" for k, f in fields.items()}
    for f in findings:
        if f.severity == "error" or per_field.get(f.field) != "error":
            per_field[f.field] = f.severity

    if any(f.severity == "error" for f in findings):
        status = "FAIL"
    elif findings:
        status = "REVIEW"
    else:
        status = "PASS"
    return status, findings, per_field
