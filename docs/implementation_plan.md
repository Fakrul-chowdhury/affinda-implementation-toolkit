# Implementation plan: Wattlebird Freight, Bill of Lading automation

> Wattlebird Freight is a fictional customer. This is the plan I'd run as Implementation & Support Specialist; the live
> tracker is `tracker/wattlebird_project.yaml` (shown on the app's Implementation page).

## 1. The customer and the problem

Wattlebird is a mid-size Australian road carrier. Its operations team keys about **400 Bills of Lading a week** into the TMS
by hand, from three sources:

| Source | Share | What makes it hard |
|---|---|---|
| Wattlebird's own road BOL | ~55% | B-doubles: two trailers and two seals per document |
| Importers' VICS straight BOLs | ~25% | US format, weights in lbs, tick-box freight terms |
| Ocean BOLs for container cartage | ~20% | Several containers per BOL, totals spread across lines or only written in words |

About 15% arrive as **phone photos** taken by drivers.

**Goal:** extracted data goes straight into the TMS when it's safe, and to a review queue when it isn't, with
**zero wrong documents auto-approved**. Success is measured as straight-through rate × accuracy, not accuracy alone.

## 2. Timeline (7 weeks, 7 gates)

| Gate | Week | Exit criteria (summary) | Customer must provide |
|---|---|---|---|
| G1 Kick-off & discovery | 1 | Stakeholders, 50 sample docs per format, volumes | Samples, SME time |
| G2 Requirements sign-off | 2 | 16 fields defined, rules v1 agreed, UAT criteria agreed | Signed requirements |
| G3 Solution design | 3 | Document type design, integration approach (API + webhook → TMS) | IT contact |
| G4 Build check-in | 4 | Affinda configured, validation built, test integration works | TMS test environment |
| G5 UAT | 5–6 | ≥ 95% field accuracy, 0 auto-approved errors, every format ≥ 90%, findings signed | Reviewer for sign-off |
| G6 Go-live | 7 | Runbook, review-queue training, rollback plan, go/no-go | Go/no-go decision |
| G7 Hypercare | 7–9 | Daily checks in week 1, < 3 tickets/week by week 2, handover to support | Feedback channel |

**Gates are enforced.** UAT doesn't start without signed requirements, because otherwise "correct" is undefined and UAT
turns into an argument. Go-live doesn't happen on unmet UAT criteria without a written, signed exception
(for example, "ocean BOLs go live routed 100% to review").

## 3. Solution design

- **Affinda document type** "Bill of Lading" with 16 fields (+ `weightUnit` after UAT round 1). Trailer and seal fields
  are repeating. Descriptions say what each field is *not* as well as what it is (see `config_tuning.md`).
- **Validation layer** (`rules/wattlebird.yaml`): rules live in YAML, owned jointly with Wattlebird Ops, and can be changed
  without a code deploy. Severity decides routing: `error` → FAIL (fix before export), `warning` → REVIEW, none → PASS.
- **Integration:** the TMS integration listens for Affinda webhooks rather than polling. PASS documents post to the TMS
  automatically. REVIEW/FAIL documents land in a review queue with the reasons attached.
- **Units:** weights are stored in kg. LB documents are converted in the integration (pending decision D3).

## 4. UAT approach

- **Test set** covers every format and every known edge case: B-doubles, multi-container BOLs, totals in words, tick
  boxes, phone photos, plus the real sample documents. Ground truth is written down *before* the run.
- **Metrics:** field accuracy, documents fully correct, the share of errors caught by validation, false alarms, and the go-live
  gate metric: **documents auto-approved with an error**.
- **Holdout:** some documents are never used for tuning, so the final numbers aren't flattering.
- **Re-scoring is free:** responses are saved, so rule changes are re-scored without spending credits
  (`python -m uat.run_uat --rescore baseline --label ...`).

## 5. Go-live & hypercare

- **Go-live runbook:** production workspace and keys, review-queue training (30 minutes, with real flagged examples), rollback
  = switch the TMS back to manual entry (no data loss, because Affinda keeps the documents).
- **Hypercare, week 1:** daily 15-minute check of the exceptions queue: what was flagged, false-alarm rate, and anything wrong
  that passed. **Week 2:** twice weekly. Tickets tagged in the support queue (`support/`) feed a known-issues list.
- **Exit:** straight-through rate and accuracy stable for a week, < 3 tickets/week, and a known-issues list handed to
  standard support.

## 6. Communication

- Weekly status email generated from the tracker (Implementation page → "Weekly status update"). It's honest about
  RAG status, names any decision needed from the customer, and gives dates.
- **When something goes wrong:** say so early, with impact, cause, workaround and next update time, for example
  "3 documents would have passed with wrong data. Here's the rule that now catches them, and here's what it costs in
  review volume."

## 7. Risks (live list in the tracker)

| Risk | Mitigation |
|---|---|
| Ocean BOL accuracy below 90% | Tuning, then route ocean BOLs to review if needed |
| lbs vs kg | `weightUnit` field + conversion (decision D3) |
| Phone photos misread | Freight terms from scans always reviewed. Ask shippers for PDFs |
| Rules tuned on the test set | Holdout run before sign-off |
