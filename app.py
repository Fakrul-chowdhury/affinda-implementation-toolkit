"""FreightRead web app: extraction + validation, UAT results, implementation tracker, support insights.

    python app.py          then open http://localhost:5000

EXTRACTOR_MODE in .env decides whether uploads go to Affinda ("live", uses credits) or are
replayed from recorded responses ("mock", free, UAT documents only).
"""
import json
import os
import tempfile
from datetime import date
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from freightread import affinda_client, config, mock_extractor
from freightread.normalize import document_info, normalise
from freightread.validation import load_rules, validate
from support.insights import analyse, load as load_tickets
from tracker.tracker import load as load_project, project_status, status_update

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
ALLOWED = {"pdf", "png", "jpg", "jpeg", "docx"}
UAT_DIR = config.ROOT / "uat"
DEMO_TODAY = date(2026, 10, 9)  # the demo project's "today"; see tracker/wattlebird_project.yaml


def _extract(path, file_name):
    if config.EXTRACTOR_MODE == "live":
        return affinda_client.sanitise(affinda_client.extract(path, file_name=file_name))
    return mock_extractor.extract(path, file_name=file_name)


def _process(path, file_name):
    result = _extract(path, file_name)
    fields = normalise(result)
    doc = document_info(result)
    status, findings, per_field = validate(fields, load_rules(config.RULES_FILE), doc=doc)
    by_field = {}
    for f in findings:
        by_field.setdefault(f.field, []).append(f)
    return {"file_name": file_name, "fields": fields, "doc": doc, "status": status, "findings": findings,
            "per_field": per_field, "by_field": by_field,
            "source": (result.get("meta") or {}).get("source", "live"), "raw": result.get("data")}


def _uat_docs():
    path = UAT_DIR / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@app.context_processor
def inject_mode():
    return {"mode": config.EXTRACTOR_MODE}


@app.route("/", methods=["GET", "POST"])
def extract_page():
    result, error = None, None
    doc_id = request.form.get("doc_id")
    if not doc_id and config.EXTRACTOR_MODE == "mock":
        doc_id = request.args.get("doc")  # /?doc=R01 link; mock only, so a plain GET can never spend credits
    if request.method == "POST" or doc_id:
        tmp = None
        try:
            if doc_id:  # one of the UAT documents
                row = next((r for r in _uat_docs() if r["doc_id"] == doc_id), None)
                if not row:
                    abort(404)
                path = config.ROOT / row["file"] if row["file"].startswith("samples/") else UAT_DIR / "documents" / row["file"]
                result = _process(path, Path(row["file"]).name)
            else:
                upload = request.files.get("file")
                if not upload or not upload.filename:
                    raise ValueError("Choose a file to upload.")
                name = secure_filename(upload.filename)
                if name.rsplit(".", 1)[-1].lower() not in ALLOWED:
                    raise ValueError("File type not supported. Use PDF, PNG, JPG or DOCX.")
                # unique temp file: two people uploading 'bol.pdf' at once can't collide
                fd, tmp = tempfile.mkstemp(suffix="_" + name)
                os.close(fd)
                upload.save(tmp)
                result = _process(tmp, name)
        except (affinda_client.AffindaError, LookupError, ValueError) as e:
            error = str(e)
        finally:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
    return render_template("extract.html", result=result, error=error, docs=_uat_docs())


@app.post("/api/extract")
def api_extract():
    """JSON endpoint for integrations: upload a file, get fields + validation back."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": "No file uploaded"}), 400
    name = secure_filename(upload.filename)
    if name.rsplit(".", 1)[-1].lower() not in ALLOWED:
        return jsonify({"error": "File type not supported"}), 400
    fd, tmp = tempfile.mkstemp(suffix="_" + name)
    os.close(fd)
    try:
        upload.save(tmp)
        r = _process(tmp, name)
    except (affinda_client.AffindaError, LookupError) as e:
        return jsonify({"error": str(e)}), 502
    finally:
        os.remove(tmp)
    return jsonify({
        "file": name, "status": r["status"], "source": r["source"],
        "fields": {k: {"value": f.value, "raw": f.raw, "check": r["per_field"].get(k)} for k, f in r["fields"].items()},
        "findings": [f.__dict__ for f in r["findings"]],
    })


def _uat_runs():
    runs = []
    for p in sorted((UAT_DIR / "results").glob("*/summary.json")):
        runs.append(json.loads(p.read_text(encoding="utf-8")))
    return runs


@app.get("/uat")
def uat_page():
    return render_template("uat.html", runs=_uat_runs())


@app.get("/uat/report/<label>")
def uat_report(label):
    folder = UAT_DIR / "results" / secure_filename(label)
    if not (folder / "report.html").exists():
        abort(404)
    return send_from_directory(folder, "report.html")


@app.get("/tracker")
def tracker_page():
    st = project_status(load_project(), DEMO_TODAY)
    return render_template("tracker.html", st=st, email=status_update(st))


@app.get("/support")
def support_page():
    a = analyse(load_tickets())
    categories = list(a["by_category"])
    peak = max(sum(c.values()) for c in a["by_week"].values())
    return render_template("support.html", a=a, categories=categories, peak=peak)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
