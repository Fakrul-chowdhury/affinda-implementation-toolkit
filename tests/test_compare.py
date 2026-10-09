from freightread.compare import match


def test_identifiers_ignore_case_and_punctuation():
    assert match("billOfLadingNumber", "2026-00471", "2026 00471")[0] == "correct"
    assert match("billOfLadingNumber", "2026-00471", "2026-00472")[0] == "wrong"


def test_multi_value_ids_compare_as_sets():
    assert match("trailerNumber", ["TRL-1", "TRL-2"], "TRL-1 / TRL-2")[0] == "correct"
    assert match("sealNumber", ["555728", "555111", "555423"], "555728 555111")[0] == "wrong"


def test_numbers_within_tolerance():
    assert match("grossWeight", 10165.5, "10,165.50 KG")[0] == "correct"
    assert match("grossWeight", 10165.5, 4425001880.5)[0] == "wrong"


def test_free_text_allows_extra_address_words():
    assert match("shipper", "BLUEGUM PANTRY CO.", "BLUEGUM PANTRY CO. 14 TANNER STREET")[0] == "correct"
    assert match("origin", "Laverton North", "Laverton Nonh")[0] == "wrong"


def test_units_spacing_is_not_an_error():
    assert match("descriptionOfGoods", ["Dry pet food 15kg"], ["Dry pet food 15 kg"])[0] == "correct"


def test_outcomes_for_empty_values():
    assert match("proNumber", None, None)[0] == "empty_ok"
    assert match("proNumber", "123", None)[0] == "missed"
    assert match("sidNumber", None, "10002345")[0] == "spurious"


def test_freight_terms_synonyms():
    assert match("freightTerms", "Prepaid", "PREPAID")[0] == "correct"
    assert match("freightTerms", "Third Party", "3rd Party")[0] == "correct"
    assert match("freightTerms", "Collect", "Prepaid")[0] == "wrong"
