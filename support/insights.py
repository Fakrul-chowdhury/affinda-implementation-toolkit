"""Support queue analytics: volumes, SLA, tagger accuracy and ranked product feedback.

    python -m support.insights        # prints a summary and writes support/insights.json
"""
import csv
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .generate_tickets import SLA_HOURS
from .triage import triage

HERE = Path(__file__).resolve().parent
SEVERITY = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}

# What each recurring issue means for the product, and the evidence behind it.
FEEDBACK = {
    "merged_weight": ("Number fields concatenate several values ('4,425.00 KG 1,880.50 KG' -> 4425001880.5)",
                      "Return null or a list when raw text holds several numbers, instead of joining digits; "
                      "expose a 'sum of lines' option for totals", "UAT R01, C02, C02S"),
    "checkbox_scan": ("Tick boxes misread on phone photos (Collect read as Prepaid)",
                      "Surface per-field confidence for checkbox-derived values so integrations can route them to review",
                      "UAT B01S"),
    "quantity_words": ("Totals printed only in words aren't parsed into number fields",
                       "Parse number words ('FIVE HUNDRED AND EIGHTY') during number normalisation", "UAT R01"),
    "multi_page_lines": ("Values on continuation pages are missed",
                         "Make single-value fields with several matches across pages visible as a warning", "UAT R01"),
    "credits_per_page": ("Customers are surprised that credits are per page",
                         "Show pages and credits per document in the UI and API response; add to onboarding guide",
                         "Live usage: 2-page sample used 2 credits"),
    "feature_confidence": ("Per-field confidence is null on Extract document types",
                           "Return a confidence signal (or document it clearly) so customers can tune auto-approval",
                           "Every live UAT response: confidence = null"),
    "feature_repeating": ("Single-value fields can't hold B-double trailers/seals",
                          "Suggest 'multiple' when the sample document has several matches during field setup",
                          "UAT A04, A05, R01"),
    "feature_units": ("Weights in lbs vs kg", "Unit capture/normalisation for weight fields", "UAT B01-B03 (lbs)"),
    "id_confusion": ("Identifier fields pick up neighbouring references (PO# as SID)",
                     "Prompt guidance in field setup to describe what a field is NOT", "UAT R01"),
    "webhook_missing": ("Webhook delivery visibility", "Delivery log + retry status in the UI", "Support tickets"),
    "polling_timeout": ("Integrations poll instead of using webhooks", "Promote webhooks in onboarding docs", "Support tickets"),
}


def load(path=HERE / "tickets.csv"):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.update({f"tag_{k}": v for k, v in triage(r["subject"], r["body"], r["tier"]).items()})
        # Final classification = what the ticket ends up tagged as after an agent confirms or fixes the
        # auto-tag. In this synthetic queue that's the hand label.
        r["final_category"], r["final_issue"] = r["true_category"], r["true_issue"]
        r["created"] = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M")
        r["first_response_hours"] = float(r["first_response_hours"])
        r["resolution_hours"] = float(r["resolution_hours"]) if r["resolution_hours"] else None
        r["sla_met"] = r["first_response_hours"] <= SLA_HOURS[r["true_priority"]]
    return rows


def analyse(rows):
    weeks = sorted({r["created"].strftime("%G-W%V") for r in rows})
    by_week = {w: Counter(r["final_category"] for r in rows if r["created"].strftime("%G-W%V") == w) for w in weeks}

    def acc(subset, tag, truth):
        return round(sum(r[tag] == r[truth] for r in subset) / len(subset), 3) if subset else None

    def coverage(subset):
        return round(sum(r["tag_category"] != "other" for r in subset) / len(subset), 3) if subset else None

    def precision(subset):
        tagged = [r for r in subset if r["tag_category"] != "other"]
        return round(sum(r["tag_signature"] == r["true_issue"] for r in tagged) / len(tagged), 3) if tagged else None

    seen = [r for r in rows if r.get("phrasing") != "holdout"]
    unseen = [r for r in rows if r.get("phrasing") == "holdout"]
    misses = Counter((r["true_category"], r["tag_category"]) for r in rows if r["tag_category"] != r["true_category"])

    sla = {}
    for p in ("P1", "P2", "P3", "P4"):
        rs = [r for r in rows if r["true_priority"] == p]
        res = [r["resolution_hours"] for r in rs if r["resolution_hours"] is not None]
        sla[p] = {"tickets": len(rs), "sla_hours": SLA_HOURS[p],
                  "first_response_met": round(sum(r["sla_met"] for r in rs) / len(rs), 3) if rs else None,
                  "median_first_response_h": round(statistics.median(r["first_response_hours"] for r in rs), 1) if rs else None,
                  "median_resolution_h": round(statistics.median(res), 1) if res else None}

    cutoff = max(r["created"] for r in rows).strftime("%G-W%V")
    recent_weeks = set(weeks[-2:])
    issues = defaultdict(list)
    for r in rows:
        issues[r["final_issue"]].append(r)
    feedback = []
    for sig, rs in issues.items():
        if sig not in FEEDBACK:
            continue
        customers = {r["customer"] for r in rs}
        worst = max(SEVERITY[r["true_priority"]] for r in rs)
        recent = sum(r["created"].strftime("%G-W%V") in recent_weeks for r in rs)
        problem, ask, evidence = FEEDBACK[sig]
        feedback.append({"signature": sig, "tickets": len(rs), "customers": len(customers),
                         "customer_names": sorted(customers), "max_severity": worst, "recent_2w": recent,
                         # simple, explainable ranking: volume x reach x severity
                         "score": len(rs) * len(customers) * worst,
                         "problem": problem, "ask": ask, "evidence": evidence})
    feedback.sort(key=lambda f: -f["score"])

    deflectable = [r for r in rows if r["final_category"] == "how_to"]
    return {
        "tickets": len(rows), "weeks": weeks, "through_week": cutoff,
        "by_category": dict(Counter(r["final_category"] for r in rows).most_common()),
        "manual_triage_needed": sum(r["tag_category"] == "other" for r in rows),
        "by_customer": dict(Counter(r["customer"] for r in rows).most_common()),
        "by_week": {w: dict(c) for w, c in by_week.items()},
        "open": sum(r["status"] != "resolved" for r in rows),
        "tagger": {"seen": {"n": len(seen), "category": acc(seen, "tag_category", "true_category"),
                            "issue": acc(seen, "tag_signature", "true_issue"),
                            "priority": acc(seen, "tag_priority", "true_priority"),
                            "coverage": coverage(seen), "precision": precision(seen)},
                   "unseen": {"n": len(unseen), "category": acc(unseen, "tag_category", "true_category"),
                              "issue": acc(unseen, "tag_signature", "true_issue"),
                              "priority": acc(unseen, "tag_priority", "true_priority"),
                              "coverage": coverage(unseen), "precision": precision(unseen)},
                   "top_confusions": [{"true": t, "tagged": g, "n": n} for (t, g), n in misses.most_common(5)]},
        "sla": sla,
        "feedback": feedback,
        "deflection": {"how_to_tickets": len(deflectable), "share": round(len(deflectable) / len(rows), 3),
                       "top": Counter(r["final_issue"] for r in deflectable).most_common(4)},
    }


def main():
    a = analyse(load())
    (HERE / "insights.json").write_text(json.dumps(a, indent=2, default=str), encoding="utf-8")
    t = a["tagger"]
    print(f"{a['tickets']} tickets, {a['open']} open.")
    for k in ("seen", "unseen"):
        print(f"  Tagger on {k} phrasing (n={t[k]['n']}): category {t[k]['category']:.0%}, "
              f"issue {t[k]['issue']:.0%}, priority {t[k]['priority']:.0%} | coverage {t[k]['coverage']:.0%}, "
              f"precision when tagged {t[k]['precision']:.0%}")
    print("By category:", a["by_category"])
    for p, s in a["sla"].items():
        print(f"  {p}: {s['tickets']} tickets, first response within {s['sla_hours']}h: {s['first_response_met']:.0%}, "
              f"median resolution {s['median_resolution_h']}h")
    print("Top product feedback:")
    for f in a["feedback"][:6]:
        print(f"  [{f['score']:>3}] {f['signature']}: {f['tickets']} tickets / {f['customers']} customers - {f['problem']}")
    print("Tagger confusions:", a["tagger"]["top_confusions"])


if __name__ == "__main__":
    main()
