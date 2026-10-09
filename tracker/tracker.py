"""Implementation tracker: gate status (RAG), overdue tasks and a customer status update.

    python -m tracker.tracker                 # print this week's status update
    python -m tracker.tracker --today 2026-10-20

RAG rules (deliberately simple and explainable to a customer):
  green  - gate done, or on track
  amber  - due within 3 days with open tasks, or acceptance criteria currently not met
  red    - past due and not done, or a task is overdue
"""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(path=HERE / "wattlebird_project.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _d(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def uat_check(gate):
    """Compare the gate's acceptance criteria with the latest UAT summary."""
    label = gate.get("uat_results")
    if not label:
        return None
    path = ROOT / "uat" / "results" / label / "summary.json"
    if not path.exists():
        return {"available": False, "label": label}
    s = json.loads(path.read_text(encoding="utf-8"))
    acc = gate.get("acceptance", {})
    checks = [
        ("Field accuracy", s["field_accuracy"], f">= {acc['field_accuracy_min']:.0%}",
         s["field_accuracy"] >= acc["field_accuracy_min"], f"{s['field_accuracy']:.1%}"),
        ("Docs auto-approved with an error", s["passed_with_errors"], f"<= {acc['passed_with_errors_max']}",
         s["passed_with_errors"] <= acc["passed_with_errors_max"], str(s["passed_with_errors"])),
    ]
    for layout, value in s["per_layout"].items():
        checks.append((f"Accuracy: {layout} layout", value, f">= {acc['per_layout_min']:.0%}",
                       value >= acc["per_layout_min"], f"{value:.0%}"))
    return {"available": True, "label": label, "summary": s,
            "checks": [{"name": n, "target": t, "met": m, "actual": a} for n, _, t, m, a in checks],
            "all_met": all(c[3] for c in checks), "real": s.get("is_real_affinda_result", False)}


def gate_status(gate, today):
    due = _d(gate["due"])
    tasks = gate.get("tasks", [])
    overdue = [t for t in tasks if t.get("status") != "done" and t.get("due") and _d(t["due"]) < today]
    uat = uat_check(gate)
    reasons = []
    if gate["status"] == "done":
        rag = "green"
    elif gate["status"] == "not_started" and due >= today and not overdue:
        rag = "none"  # future gate: no RAG until it starts
    elif due < today:
        rag, reasons = "red", [f"gate was due {due}"]
    elif overdue:
        rag, reasons = "red", [f"{len(overdue)} task(s) overdue"]
    else:
        rag = "green"
        if gate["status"] == "in_progress" and due - today <= timedelta(days=3) and any(t.get("status") != "done" for t in tasks):
            rag, reasons = "amber", [f"due in {(due - today).days} days with open tasks"]
        if uat and uat.get("available") and not uat["all_met"]:
            rag = "amber"
            reasons.append("UAT acceptance criteria not yet met: "
                           + ", ".join(c["name"] for c in uat["checks"] if not c["met"]))
    return {**gate, "rag": rag, "reasons": reasons, "overdue_tasks": overdue, "uat": uat,
            "open_tasks": [t for t in tasks if t.get("status") != "done"]}


def project_status(project, today=None):
    today = today or date.today()
    gates = [gate_status(g, today) for g in project["gates"]]
    rags = [g["rag"] for g in gates]
    overall = "red" if "red" in rags else "amber" if "amber" in rags else "green"
    current = next((g for g in gates if g["status"] != "done"), None)
    done = sum(g["status"] == "done" for g in gates)
    return {"project": project, "today": today, "gates": gates, "overall": overall, "current": current,
            "progress": done / len(gates), "days_to_go_live": (_d(project["target_go_live"]) - today).days,
            "open_risks": [r for r in project.get("risks", []) if r["status"] != "closed"],
            "decisions_needed": [d for d in project.get("decisions", []) if d["status"] == "needed"]}


def status_update(st):
    """Plain-text weekly status update for the customer (email/Slack-ready)."""
    p, cur = st["project"], st["current"]
    lines = [
        f"Subject: {p['project']} - weekly status ({st['today']:%d %b %Y}) - {st['overall'].upper()}",
        "",
        f"Hi team,",
        "",
        f"Overall status: {st['overall'].upper()}. {st['days_to_go_live']} days to target go-live "
        f"({_d(p['target_go_live']):%d %b}). {sum(g['status'] == 'done' for g in st['gates'])} of {len(st['gates'])} gates complete.",
    ]
    if cur:
        lines += ["", f"Current stage: {cur['id']} {cur['name']} (due {_d(cur['due']):%d %b}) - {cur['rag'].upper()}"]
        for r in cur["reasons"]:
            lines.append(f"  - {r}")
        uat = cur.get("uat")
        if uat and uat.get("available"):
            lines += ["", f"UAT results ({'live Affinda run' if uat['real'] else 'SIMULATED'}, {uat['summary']['documents']} documents):"]
            for c in uat["checks"]:
                lines.append(f"  [{'x' if c['met'] else ' '}] {c['name']}: {c['actual']} (target {c['target']})")
        done = [t for t in cur.get("tasks", []) if t.get("status") == "done"]
        if done:
            lines += ["", "Done this period:"] + [f"  - {t['task']}" for t in done]
        if cur["open_tasks"]:
            lines += ["", "Next steps:"]
            lines += [f"  - {t['task']} ({t['owner']}{', due ' + format(_d(t['due']), '%d %b') if t.get('due') else ''})"
                      for t in cur["open_tasks"]]
    if st["decisions_needed"]:
        lines += ["", "Decisions needed from you:"]
        lines += [f"  - {d['id']}: {d['decision']} (by {_d(d['date']):%d %b})" for d in st["decisions_needed"]]
    risks = [r for r in st["open_risks"] if r["status"] == "open"]
    if risks:
        lines += ["", "Top risks:"]
        lines += [f"  - {r['id']} ({r['impact']} impact): {r['risk']}. Mitigation: {r['mitigation']}" for r in risks[:3]]
    lines += ["", "Happy to walk through any of this on our Thursday call.", "", f"{p['affinda_lead']}, Affinda"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", type=date.fromisoformat, default=date(2026, 10, 9))
    args = ap.parse_args()
    print(status_update(project_status(load(), args.today)))


if __name__ == "__main__":
    main()
