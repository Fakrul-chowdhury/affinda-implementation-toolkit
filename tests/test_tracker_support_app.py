from datetime import date

import pytest

from support.triage import triage
from tracker.tracker import load, project_status, status_update


def test_tracker_flags_unmet_uat_criteria_as_amber():
    st = project_status(load(), date(2026, 10, 9))
    g5 = next(g for g in st["gates"] if g["id"] == "G5")
    assert g5["rag"] == "amber"
    assert g5["uat"]["real"] is True  # acceptance numbers come from a live Affinda run


def test_tracker_goes_red_when_gate_overdue():
    st = project_status(load(), date(2026, 10, 20))
    assert next(g for g in st["gates"] if g["id"] == "G5")["rag"] == "red"
    assert st["overall"] == "red"


def test_status_update_mentions_decisions_and_risks():
    text = status_update(project_status(load(), date(2026, 10, 9)))
    assert "Decisions needed from you" in text and "D3" in text
    assert "Top risks" in text


@pytest.mark.parametrize("subject,body,category,priority", [
    ("URGENT", "All documents failing, production is down", "billing_credits", "P1"),
    ("401 Unauthorized after key rotation", "", "integration_api", "P2"),
    ("Export to CSV", "How do I export?", "how_to", "P4"),
    ("Freight terms wrong", "Collect was ticked but we billed the wrong party", "extraction_accuracy", "P2"),
])
def test_triage_examples(subject, body, category, priority):
    t = triage(subject, body)
    assert (t["category"], t["priority"]) == (category, priority)


def test_unknown_wording_falls_back_to_manual_triage():
    assert triage("Locked out", "Too many attempts")["category"] == "other"


@pytest.fixture
def client(monkeypatch):
    from freightread import config
    monkeypatch.setattr(config, "EXTRACTOR_MODE", "mock")  # never spend credits in tests
    import app
    return app.app.test_client()


@pytest.mark.parametrize("url", ["/", "/uat", "/tracker", "/support", "/uat/report/baseline"])
def test_pages_render(client, url):
    assert client.get(url).status_code == 200


def test_extract_uat_document_in_mock_mode(client):
    r = client.post("/", data={"doc_id": "R01"})
    assert r.status_code == 200 and b"FAIL" in r.data and b"recorded" in r.data


def test_api_rejects_bad_file_type(client):
    from io import BytesIO
    r = client.post("/api/extract", data={"file": (BytesIO(b"x"), "evil.exe")}, content_type="multipart/form-data")
    assert r.status_code == 400
