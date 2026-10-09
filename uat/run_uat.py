"""UAT runner: extract every document in the manifest, score against ground truth, report.

    python -m uat.run_uat --label baseline              # uses EXTRACTOR_MODE from .env
    python -m uat.run_uat --label baseline --mode mock  # offline, replays recordings
    python -m uat.run_uat --label baseline --only A01,R02
    python -m uat.run_uat --rescore baseline            # re-score saved responses (e.g. after a rules change), 0 credits

Outputs go to uat/results/<label>/ : report.html, summary.json, documents.csv, fields.csv, responses/.
Live runs also refresh uat/recordings/, which mock mode replays.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from freightread import affinda_client, config, mock_extractor
from freightread.compare import score_document
from freightread.normalize import LABELS, document_info, normalise
from freightread.validation import load_rules, validate

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
RECORDINGS = HERE / "recordings"
ERRORS = {"wrong", "missed", "spurious"}
UAT_DATE = date(2026, 10, 9)  # fixed "today" so date rules give the same answer on every re-run


def load_manifest(only=None):
    rows = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    if only:
        wanted = set(only.split(","))
        rows = [r for r in rows if r["doc_id"] in wanted]
    return rows


def document_path(row):
    # real samples live in /samples at the repo root, generated ones in uat/documents
    return config.ROOT / row["file"] if row["file"].startswith("samples/") else HERE / "documents" / row["file"]


def get_response(row, mode, label):
    path = document_path(row)
    if mode == "live":
        result = affinda_client.sanitise(affinda_client.extract(path, custom_identifier=f"uat-{label}-{row['doc_id']}"))
        result["meta"]["source"] = "live"
        RECORDINGS.mkdir(exist_ok=True)
        (RECORDINGS / f"{row['doc_id']}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        return result
    return mock_extractor.extract(path)


def evaluate(row, result, rules):
    truth = json.loads((HERE / "ground_truth" / f"{row['doc_id']}.json").read_text(encoding="utf-8"))
    fields = normalise(result)
    status, findings, _ = validate(fields, rules, today=UAT_DATE, doc=document_info(result))
    scored = score_document(fields, truth)
    flagged = defaultdict(list)
    for f in findings:
        flagged[f.field].append(f)
    for s in scored:
        s["flagged"] = bool(flagged.get(s["field"]))
        s["findings"] = " / ".join(f.message for f in flagged.get(s["field"], []))
    return {
        **row,
        "source": (result.get("meta") or {}).get("source", "live"),
        "status": status,
        "fields": scored,
        "findings": [f.__dict__ for f in findings],
        "errors": sum(s["outcome"] in ERRORS for s in scored),
        "notes": truth.get("_notes", ""),
    }


def summarise(docs, label, mode, credits, rules_name=""):
    all_fields = [f for d in docs for f in d["fields"]]
    scored = [f for f in all_fields if f["outcome"] != "empty_ok"]
    errs = [f for f in all_fields if f["outcome"] in ERRORS]
    correct_ok = [f for f in all_fields if f["outcome"] in ("correct", "empty_ok")]

    per_field = {}
    for key in LABELS:
        rows = [f for f in scored if f["field"] == key]
        c = Counter(f["outcome"] for f in rows)
        per_field[key] = {"label": LABELS[key], "n": len(rows), **c,
                          "accuracy": round(c["correct"] / len(rows), 3) if rows else None}

    per_layout = {}
    for layout in sorted({d["layout"] for d in docs}):
        fs = [f for d in docs if d["layout"] == layout for f in d["fields"] if f["outcome"] != "empty_ok"]
        per_layout[layout] = round(sum(f["outcome"] == "correct" for f in fs) / len(fs), 3) if fs else None

    pass_docs = [d for d in docs if d["status"] == "PASS"]
    sources = Counter(d["source"] for d in docs)
    return {
        "label": label,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "rules": rules_name,
        "sources": dict(sources),
        "is_real_affinda_result": set(sources) <= {"live", "recorded"},
        "documents": len(docs),
        "credits_used": credits,
        "field_accuracy": round(sum(f["outcome"] == "correct" for f in scored) / len(scored), 3) if scored else None,
        "fields_scored": len(scored),
        "fields_wrong": len(errs),
        "docs_fully_correct": sum(d["errors"] == 0 for d in docs),
        "status_counts": dict(Counter(d["status"] for d in docs)),
        # Of the extraction errors, how many did the validation rules flag for a human?
        "errors_caught_by_validation": sum(f["flagged"] for f in errs),
        "error_catch_rate": round(sum(f["flagged"] for f in errs) / len(errs), 3) if errs else None,
        # Flags raised on fields that were actually right (noise for the reviewer).
        "false_alarms": sum(f["flagged"] for f in correct_ok),
        # The number that matters for go-live: documents validation would auto-approve that contain an error.
        "passed_with_errors": sum(d["errors"] > 0 for d in pass_docs),
        "per_field": per_field,
        "per_layout": per_layout,
    }


def write_outputs(out, docs, summary):
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(out / "documents.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "file", "layout", "scenario", "source", "validation_status", "field_errors"])
        for d in docs:
            w.writerow([d["doc_id"], d["file"], d["layout"], d["scenario"], d["source"], d["status"], d["errors"]])
    with open(out / "fields.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "field", "outcome", "expected", "actual", "raw", "flagged_by_validation", "note", "findings"])
        for d in docs:
            for r in d["fields"]:
                w.writerow([d["doc_id"], r["field"], r["outcome"], json.dumps(r["expected"]), json.dumps(r["actual"]),
                            r["raw"], r["flagged"], r["note"], r["findings"]])
    env = Environment(loader=FileSystemLoader(HERE), autoescape=True)
    html = env.get_template("report_template.html").render(s=summary, docs=docs, labels=LABELS)
    (out / "report.html").write_text(html, encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="latest")
    ap.add_argument("--mode", choices=["live", "mock"], default=config.EXTRACTOR_MODE)
    ap.add_argument("--only", help="comma-separated doc ids")
    ap.add_argument("--rescore", metavar="LABEL", help="re-score saved responses of a previous run; no API calls")
    ap.add_argument("--rules", default=str(config.RULES_FILE), help="validation rules YAML")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    rules = load_rules(args.rules)
    manifest = load_manifest(args.only)

    # --rescore SRC [--label OUT]: score SRC's saved responses (e.g. with new rules), write the report to OUT.
    label = args.label if (args.label != "latest" or not args.rescore) else args.rescore
    src = RESULTS / (args.rescore or label)
    out = RESULTS / label
    resp_dir = src / "responses"
    ledger = src / "credits.json"  # credits per live batch, so partial re-runs add up
    batches = json.loads(ledger.read_text(encoding="utf-8")) if ledger.exists() else []

    if args.rescore:
        mode = json.loads((src / "summary.json").read_text(encoding="utf-8"))["mode"]
    else:
        mode = args.mode
        org = before = None
        if mode == "live":
            print(f"LIVE run: {len(manifest)} documents will be sent to Affinda and use credits.")
            org = _organisation()
            before = affinda_client.credits_used(org)

        def fetch(row):
            try:
                return row["doc_id"], get_response(row, mode, label)
            except Exception as e:  # keep going; one bad document shouldn't sink the run
                print(f"  ! {row['doc_id']}: {e}", file=sys.stderr)
                return row["doc_id"], None

        with ThreadPoolExecutor(max_workers=args.workers if mode == "live" else 1) as pool:
            fetched = {k: v for k, v in pool.map(fetch, manifest) if v is not None}
        resp_dir.mkdir(parents=True, exist_ok=True)
        for doc_id, res in fetched.items():
            (resp_dir / f"{doc_id}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        if mode == "live":
            batches.append({"at": datetime.now().isoformat(timespec="seconds"), "documents": sorted(fetched),
                            "credits": affinda_client.credits_used(org) - before})
            ledger.write_text(json.dumps(batches, indent=1), encoding="utf-8")

    # Score every saved response under this label, so batches run with --only merge into one report.
    manifest = [r for r in load_manifest() if (resp_dir / f"{r['doc_id']}.json").exists()]
    responses = {r["doc_id"]: json.loads((resp_dir / f"{r['doc_id']}.json").read_text(encoding="utf-8"))
                 for r in manifest}
    credits = sum(b["credits"] for b in batches) if mode == "live" else 0

    docs = [evaluate(r, responses[r["doc_id"]], rules) for r in manifest]
    summary = summarise(docs, label, mode, credits, Path(args.rules).name)
    write_outputs(out, docs, summary)

    print(f"\n{label}: {summary['documents']} docs | field accuracy {summary['field_accuracy']:.1%} | "
          f"fully correct docs {summary['docs_fully_correct']}/{summary['documents']} | "
          f"validation caught {summary['errors_caught_by_validation']}/{summary['fields_wrong']} errors | "
          f"passed-with-errors {summary['passed_with_errors']} | credits {summary['credits_used']} | sources {summary['sources']}")
    print(f"Report: {RESULTS / label / 'report.html'}")


def _organisation():
    import requests
    r = requests.get(f"{config.AFFINDA_BASE_URL}/workspaces/{config.AFFINDA_WORKSPACE_ID}",
                     headers=affinda_client._headers(), timeout=30)
    affinda_client._raise_for_status(r)
    return r.json()["organization"]["identifier"]


if __name__ == "__main__":
    main()
