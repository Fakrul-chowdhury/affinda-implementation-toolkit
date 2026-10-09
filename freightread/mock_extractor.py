"""Offline extractor so the app, UAT runner and tests work without spending Affinda credits.

Order of preference for a known UAT document:
  1. "recorded"  - a real Affinda response saved by a previous live UAT run (uat/recordings/)
  2. "simulated" - built from ground truth with the failure patterns seen in live runs injected

Every response is tagged meta.mock / meta.source so reports can never pass simulated
numbers off as real Affinda accuracy.
"""
import json
import re
from pathlib import Path

from .config import ROOT

UAT = ROOT / "uat"


def _manifest():
    path = UAT / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def find_doc_id(file_name):
    """Match an uploaded filename to a UAT document id (e.g. 'A01_domestic.pdf' -> 'A01')."""
    name = Path(file_name).name
    for row in _manifest():
        if Path(row["file"]).name == name:
            return row["doc_id"]
    m = re.match(r"^([A-Z]\d{2}S?)_", name)
    return m.group(1) if m else None


_SAME = object()


def _field(raw, parsed=_SAME):
    return {"raw": raw, "parsed": raw if parsed is _SAME else parsed, "confidence": None,
            "textExtractionConfidence": 1.0, "pageIndex": 0}


def simulate(truth, layout):
    """Ground truth -> Affinda-shaped response, with the error patterns observed live."""
    data = {}
    for key, value in truth.items():
        if key.startswith("_"):
            continue
        if value in (None, [], ""):
            data[key] = [] if key == "descriptionOfGoods" else None
        elif key == "descriptionOfGoods":
            data[key] = [_field(v) for v in value]
        elif key in ("trailerNumber", "sealNumber"):
            data[key] = _field(" ".join(value))           # single-value field swallows several IDs
        elif key == "grossWeight" and layout == "ocean":
            # per-container weights with no printed total: values get concatenated
            half = f"{value / 2:,.2f}"
            data[key] = _field(f"{half} KG {half} KG", float((half + half).replace(",", "").replace(".", "", 1)))
        elif key == "quantity" and layout == "ocean":
            data[key] = _field(truth.get("_quantity_words", "IN WORDS"), None)            # quantity only printed in words
        else:
            data[key] = _field(str(value), value)
    return data


def extract(file_path, file_name=None):
    file_name = file_name or Path(file_path).name
    doc_id = find_doc_id(file_name)
    if not doc_id:
        raise LookupError(
            f"Mock mode only knows the UAT documents in uat/documents (got '{file_name}'). "
            "Set EXTRACTOR_MODE=live in .env to extract any document with Affinda.")

    recording = UAT / "recordings" / f"{doc_id}.json"
    if recording.exists():
        result = json.loads(recording.read_text(encoding="utf-8"))
        result.setdefault("meta", {}).update({"mock": True, "source": "recorded"})
        return result

    truth = json.loads((UAT / "ground_truth" / f"{doc_id}.json").read_text(encoding="utf-8"))
    layout = next((r["layout"] for r in _manifest() if r["doc_id"] == doc_id), "")
    return {"data": simulate(truth, layout),
            "meta": {"identifier": f"mock-{doc_id}", "fileName": file_name, "ready": True,
                     "mock": True, "source": "simulated"}}
