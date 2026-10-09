"""Thin client for the Affinda v3 documents API.

Affinda processes asynchronously: we upload with wait=false, then poll the document
until meta.ready (or meta.failed) is set. Checking the ready flag matters - the old
FreightRead returned as soon as *any* data appeared, which could be a partial result.
"""
import time

import requests

from . import config


class AffindaError(Exception):
    """An error worth showing to a user (bad key, out of credits, timeout...)."""


def _headers():
    if not config.AFFINDA_API_KEY:
        raise AffindaError("AFFINDA_API_KEY is not set. Add it to .env or switch EXTRACTOR_MODE to mock.")
    return {"Authorization": f"Bearer {config.AFFINDA_API_KEY}", "Accept": "application/json"}


def _raise_for_status(response):
    if response.status_code in (200, 201):
        return
    body = response.text[:500]
    if response.status_code == 401:
        raise AffindaError("Affinda rejected the API key (401). Create a new key under Settings > API Keys.")
    if response.status_code in (402, 403) or "credit" in body.lower():
        raise AffindaError(f"Affinda refused the request ({response.status_code}) - usually no credits left. {body}")
    raise AffindaError(f"Affinda API error {response.status_code}: {body}")


def extract(file_path, file_name=None, custom_identifier=None, timeout_s=180, poll_every_s=3):
    """Upload one document and return the full Affinda result once processing is finished."""
    file_name = file_name or str(file_path).replace("\\", "/").rsplit("/", 1)[-1]
    data = {"workspace": config.AFFINDA_WORKSPACE_ID, "wait": "false"}
    if config.AFFINDA_DOCUMENT_TYPE_ID:
        # Skips classification: we already know every upload is a Bill of Lading.
        data["documentType"] = config.AFFINDA_DOCUMENT_TYPE_ID
    if custom_identifier:
        data["customIdentifier"] = custom_identifier

    with open(file_path, "rb") as f:
        response = requests.post(
            f"{config.AFFINDA_BASE_URL}/documents",
            headers=_headers(),
            files={"file": (file_name, f, "application/octet-stream")},
            data=data,
            timeout=60,
        )
    _raise_for_status(response)
    doc_id = (response.json().get("meta") or {}).get("identifier")
    if not doc_id:
        raise AffindaError(f"No document identifier in Affinda response: {response.text[:300]}")

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(poll_every_s)
        poll = requests.get(f"{config.AFFINDA_BASE_URL}/documents/{doc_id}", headers=_headers(), timeout=30)
        _raise_for_status(poll)
        result = poll.json()
        meta = result.get("meta") or {}
        if meta.get("failed"):
            raise AffindaError(f"Affinda failed to process {file_name}: {meta.get('errorCode')} {meta.get('errorDetail')}")
        if meta.get("ready"):
            return result
    raise AffindaError(f"Timed out after {timeout_s}s waiting for {file_name} (document {doc_id}).")


def credits_used(organization):
    """Total credits the organisation has used in the last year (from /v3/usage)."""
    r = requests.get(f"{config.AFFINDA_BASE_URL}/usage", headers=_headers(),
                     params={"organization": organization}, timeout=30)
    _raise_for_status(r)
    return r.json().get("total")


def sanitise(result):
    """Strip short-lived signed URLs and review links before a response is saved to disk or git."""
    meta = dict(result.get("meta") or {})
    for key in ("pages", "reviewUrl", "file", "pdf", "html", "createdBy", "confirmedBy",
                "rejectedBy", "archivedBy", "sourceEmail", "sourceEmailAddress"):
        meta.pop(key, None)
    clean = dict(result)
    clean["meta"] = meta
    return clean
