"""Turn an Affinda document result into a flat, predictable list of fields.

Each Affinda field carries both `raw` (the text as it appears on the page) and
`parsed` (Affinda's normalised value, e.g. a float or ISO date). We keep both:
comparing them is how the validation layer catches normalisation problems such as
"4,425.00 KG 1,880.50 KG" being parsed as 4425001880.5.
"""
from dataclasses import dataclass, field
from typing import Any, List, Optional

# Field order and labels for display. Slugs match the Affinda document type schema.
FIELDS = [
    ("billOfLadingNumber", "BOL number"),
    ("date", "Date"),
    ("sidNumber", "SID number"),
    ("proNumber", "Pro number"),
    ("shipper", "Shipper"),
    ("origin", "Origin"),
    ("consignee", "Consignee"),
    ("destination", "Destination"),
    ("carrier", "Carrier"),
    ("trailerNumber", "Trailer / container no."),
    ("sealNumber", "Seal number"),
    ("grossWeight", "Gross weight"),
    ("quantity", "Quantity (packages)"),
    ("descriptionOfGoods", "Description of goods"),
    ("freightTerms", "Freight terms"),
    ("specialInstructions", "Special instructions"),
]
LABELS = dict(FIELDS)


@dataclass
class Value:
    raw: Optional[str]
    parsed: Any
    confidence: Optional[float] = None       # per-field model confidence (often null in Affinda Extract)
    text_confidence: Optional[float] = None  # OCR / text-layer confidence
    page: Optional[int] = None


@dataclass
class ExtractedField:
    key: str
    label: str
    values: List[Value] = field(default_factory=list)  # repeating fields have several
    multiple: bool = False  # True when Affinda returned a list (field configured as repeating)

    @property
    def is_list(self):
        return self.multiple

    @property
    def found(self):
        return any(v.raw not in (None, "") or v.parsed not in (None, "") for v in self.values)

    @property
    def value(self):
        """Best display/compare value: parsed when Affinda managed to normalise it, else raw."""
        out = [v.parsed if v.parsed not in (None, "") else v.raw for v in self.values]
        out = [o for o in out if o not in (None, "")]
        if self.is_list:
            return out
        return out[0] if out else None

    @property
    def raw(self):
        raws = [v.raw for v in self.values if v.raw]
        return " | ".join(raws) if raws else None

    @property
    def confidence(self):
        scores = [v.confidence if v.confidence is not None else v.text_confidence for v in self.values]
        scores = [s for s in scores if s is not None]
        return min(scores) if scores else None


def _to_value(item):
    if item is None:
        return None
    if not isinstance(item, dict):  # some plans/fields return bare values
        return Value(raw=str(item), parsed=item)
    raw = item.get("raw")
    return Value(
        raw=raw.strip() if isinstance(raw, str) else raw,
        parsed=item.get("parsed"),
        confidence=item.get("confidence"),
        text_confidence=item.get("textExtractionConfidence"),
        page=item.get("pageIndex"),
    )


def normalise(result):
    """Affinda result (dict) -> dict of slug -> ExtractedField, in display order."""
    data = (result or {}).get("data") or {}
    out = {}
    for key, label in FIELDS:
        raw_field = data.get(key)
        items = raw_field if isinstance(raw_field, list) else [raw_field]
        values = [v for v in (_to_value(i) for i in items) if v is not None]
        out[key] = ExtractedField(key=key, label=label, values=values,
                                  multiple=isinstance(raw_field, list) or key == "descriptionOfGoods")
    return out


def document_info(result):
    meta = (result or {}).get("meta") or {}
    return {
        "identifier": meta.get("identifier"),
        "file_name": meta.get("fileName"),
        "ocr_confidence": meta.get("ocrConfidence"),
        # isOcrd came back False even for JPEG phone photos in testing; ocrConfidence is only
        # populated when OCR actually ran, so use that to detect scans.
        "scanned": meta.get("ocrConfidence") is not None,
        "mock": bool(meta.get("mock")),
    }
