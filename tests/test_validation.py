import json
from datetime import date
from pathlib import Path

import pytest

from freightread.normalize import document_info, normalise
from freightread.validation import iso6346_check_digit, load_rules, validate

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 10, 9)


def recorded(doc_id):
    return json.loads((ROOT / "uat" / "recordings" / f"{doc_id}.json").read_text(encoding="utf-8"))


def fake(**fields):
    """Affinda-shaped result with one value per field: fake(grossWeight=("1,240.00 KG", 1240.0))."""
    data = {}
    for key, value in fields.items():
        raw, parsed = value if isinstance(value, tuple) else (value, value)
        data[key] = {"raw": raw, "parsed": parsed}
    return {"data": data, "meta": {}}


@pytest.fixture(scope="module")
def rules():
    return load_rules(ROOT / "rules" / "wattlebird.yaml")


def run(result, rules):
    return validate(normalise(result), rules, today=TODAY, doc=document_info(result))


def rules_hit(findings, field):
    return {f.rule for f in findings if f.field == field}


def test_merged_weight_from_real_affinda_response_is_an_error(rules):
    # R01 is the real sample: Affinda parsed "4,425.00 KG 1,880.50 KG" as 4425001880.5
    status, findings, _ = run(recorded("R01"), rules)
    assert status == "FAIL"
    assert {"multiple_numbers_in_raw", "max"} <= rules_hit(findings, "grossWeight")


def test_quantity_in_words_is_a_parse_failure(rules):
    _, findings, _ = run(fake(quantity=("FIVE HUNDRED AND EIGHTY", None)), rules)
    assert rules_hit(findings, "quantity") == {"parse_failed"}


def test_clean_document_passes(rules):
    status, findings, _ = run(recorded("A01"), rules)
    assert status == "PASS", [f.message for f in findings]


def test_freight_terms_from_scan_needs_review(rules):
    # B01S: phone photo where Collect was read as Prepaid. v2 rules send it to a human.
    status, findings, _ = run(recorded("B01S"), rules)
    assert status == "REVIEW"
    assert "review_if_scanned" in rules_hit(findings, "freightTerms")


def test_same_freight_terms_from_pdf_is_not_flagged(rules):
    _, findings, _ = run(recorded("B01"), rules)
    assert not rules_hit(findings, "freightTerms")


def test_multi_container_totals_are_reviewed(rules):
    _, findings, _ = run(recorded("C02"), rules)
    assert "multi_line_total" in rules_hit(findings, "quantity")


def test_boilerplate_special_instruction_flagged(rules):
    _, findings, _ = run(recorded("C01"), rules)
    assert "boilerplate" in rules_hit(findings, "specialInstructions")


def test_freight_terms_synonyms_accepted(rules):
    _, findings, _ = run(fake(freightTerms="PPD"), rules)
    assert "allowed_values" not in rules_hit(findings, "freightTerms")
    _, findings, _ = run(fake(freightTerms="FOB"), rules)
    assert "allowed_values" in rules_hit(findings, "freightTerms")


def test_future_and_stale_dates(rules):
    _, findings, _ = run(fake(date="2026-12-01"), rules)
    assert "not_future" in rules_hit(findings, "date")
    _, findings, _ = run(fake(date="2021-08-10"), rules)
    stale = [f for f in findings if f.field == "date" and f.rule == "max_age_days"]
    assert stale and stale[0].severity == "warning"


def test_missing_required_field(rules):
    _, findings, _ = run(fake(), rules)
    assert "required" in rules_hit(findings, "billOfLadingNumber")


def test_shipper_equals_consignee_is_suspicious(rules):
    _, findings, _ = run(fake(shipper="ACME PTY LTD", consignee="Acme Pty Ltd"), rules)
    assert "different" in rules_hit(findings, "consignee")


def test_iso6346_check_digit():
    assert iso6346_check_digit("CSQU305438") == 3  # textbook example from the standard


def test_v1_rules_miss_what_v2_catches():
    v1 = load_rules(ROOT / "rules" / "wattlebird_v1.yaml")
    status, _, _ = run(recorded("B01S"), v1)
    assert status == "PASS"  # the gap the baseline UAT run exposed


def test_repeating_trailer_field_is_kept_whole_and_not_flagged(rules):
    # After tuning, trailerNumber is a repeating field: Affinda returns a list
    result = {"data": {"trailerNumber": [{"raw": "TRL-7336", "parsed": "TRL-7336"},
                                         {"raw": "TRL-3650", "parsed": "TRL-3650"}]}, "meta": {}}
    fields = normalise(result)
    assert fields["trailerNumber"].value == ["TRL-7336", "TRL-3650"]
    _, findings, _ = validate(fields, rules, today=TODAY)
    assert "multiple_values" not in rules_hit(findings, "trailerNumber")
