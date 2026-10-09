# UAT findings memo: Wattlebird Freight, Bill of Lading extraction

**To:** Wattlebird Operations Manager (customer sponsor) · Affinda Customer Success Lead
**From:** Implementation & Support Specialist
**Date:** 9 October 2026 · **Gate:** G5 User acceptance testing · **Status:** AMBER

> Wattlebird Freight is a fictional customer created for this demo. All numbers below come from **live Affinda API runs**
> (13 documents, 14 credits) unless marked otherwise. Raw responses are in `uat/recordings/`, and the full report is
> `uat/results/baseline/report.html`.

## 1. Summary

| | Rules v1 (as agreed) | Rules v2 (after this UAT) | Target |
|---|---|---|---|
| Field accuracy (194 fields) | 93.3% | 93.3% | ≥ 95% |
| Documents 100% correct | 7 / 13 | 7 / 13 | n/a |
| Extraction errors flagged by validation | 8 / 13 | 11 / 13 | as high as possible |
| **Documents auto-approved while containing an error** | **3** | **0** | **0** |
| Straight-through (PASS) documents | 7 | 4 | maximise, safely |
| Ocean BOL field accuracy | 80% | 80% | ≥ 90% |

**Bottom line:** extraction is strong on Wattlebird's own BOLs (98%) and on VICS BOLs (99%), but weak on ocean BOLs (80%),
where totals are spread across container lines. The v1 validation rules would have let 3 documents with wrong data
straight into the TMS. With the v2 rules, no wrong document passes, but straight-through processing falls from 7 to 4 documents.
The next step is field-description tuning in Affinda, to raise accuracy and win back straight-through volume.

**Recommendation:** don't sign off UAT yet. Apply the configuration changes in `docs/config_tuning.md`, re-test the same 13
documents, and then run the 6 holdout documents that have never been used for tuning. If ocean BOLs are still below 90%,
go live with ocean BOLs always routed to review (see risk R1).

## 2. What went wrong, and what we did about it

| # | Finding (document) | Impact | Caught by v1? | Fix |
|---|---|---|---|---|
| F1 | **Gross weight digits merged.** Two container weights `4,425.00 KG 1,880.50 KG` came back as `4425001880.5` (R01, C02, C02S) | Bad weight into TMS. Plausibility rule catches it, but the load is blocked | Yes | Field description: "total, never join numbers". Product feedback P1 |
| F2 | **Totals taken from one line.** Package count `153` returned where the document total is 166, written only in words (C02) | Silent under-count | **No** | v2 rule `review_if_multiple`: multi-container documents get totals reviewed |
| F3 | **Quantity written in words not parsed** (`FIVE HUNDRED AND EIGHTY`, R01) | Empty quantity | Yes | Field description: convert words to digits |
| F4 | **Tick box misread on a phone photo.** Collect read as Prepaid (B01S) | Wrong party billed | **No** | v2 rule `review_if_scanned` on freight terms. Ask shippers for PDFs |
| F5 | **Printed disclaimer returned as a special instruction** (C01) | Noise for drivers | **No** | v2 `boilerplate` rule + field description |
| F6 | **Multiple trailers/seals squeezed into one value** (A04, A05, C02, R01) | TMS expects one value per field | Warned | Make the fields repeating (`config_tuning.md`) |
| F7 | **Third container on page 2 missed** (R01) | Incomplete container list | Warned (multi-value) | Field description: include continuation pages |
| F8 | **PO number returned as SID** (R01, which has no SID) | Wrong reference | No | Field description: "only when labelled SID" |
| F9 | **OCR letter error.** `Laverton Nonh` for Laverton North (A01S photo) | Minor address typo | No (the document went to review anyway, for F4) | Optional: validate suburbs against a reference list (Affinda data source) |

The two errors v2 still doesn't flag at field level are F8 and F9. Both sit on documents that v2 routes to review or
fail for other reasons, so neither would reach the TMS unseen. The reviewer still has to check the whole document, not only
the flagged fields, so the review-queue training must cover this.

## 3. Trade-offs the customer needs to understand

- **Safety vs straight-through rate.** v2 raises review volume. False alarms (flags on correct fields) rose from 9 to 15.
  The 6 new ones come from the totals-review rule firing on B-double road BOLs (A04, A05), which print a proper total row,
  and from the scanned-freight-terms rule on scans where the tick box was read correctly (A01S, C02S). The 9 carried over
  from v1 are multi-value trailer/seal warnings (fixed by making those fields repeating) and stale-date warnings on the two
  real samples, which are genuinely old documents. Candidate for v3: apply the totals-review rule to ocean containers
  only. It isn't done yet, because that would be tuning on the test set again. Validate it on the holdout first.
- **Tuning on the test set.** v2 was written after looking at these 13 documents, so its catch rate is optimistic.
  The 6 holdout documents (A02, A03, A04S, B04, C03, C04) have never been sent to Affinda or used for tuning. They are the honest check.
- **lbs vs kg (decision D3).** VICS BOL weights are printed in lbs, and the TMS expects kg. Extraction is correct (it returns
  the printed number), but the integration must either convert or store the unit. A `weightUnit` field is proposed.
- **ISO 6346 container check digit (decision D2).** A check-digit rule would have caught the OCR error in C02S
  (`TGHU970258-7`). But the real sample BOL's container numbers fail the check digit (they're illustrative numbers), so
  turning it on blind would raise false alarms. It's built (`check_digit: iso6346`) and switched off until Wattlebird confirms its
  documents carry genuine container numbers.

## 4. Product feedback (for Affinda's product team)

Observed directly in live responses, not inferred:

1. **Number fields concatenate several values** instead of returning null or a list (`4,425.00 KG 1,880.50 KG` → `4425001880.5`).
   This is the most dangerous failure seen, because the output looks like a valid number.
2. **Per-field `confidence` is `null`** on every field of this Extract document type (only `textExtractionConfidence` and
   page `ocrConfidence` are populated). Customers can't use confidence to tune auto-approval, so validation rules carry all the weight.
3. **`meta.isOcrd` is `false` for JPEG phone photos** even though `ocrConfidence` is populated. Integrations that branch on
   `isOcrd` will treat scans as digital PDFs. FreightRead uses `ocrConfidence` instead.
4. **Number words aren't parsed** in number fields (`FIVE HUNDRED AND EIGHTY` → `parsed: null`).
5. **Credits are per page:** a 2-page BOL used 2 credits. That's fine, but worth making visible in the UI and in onboarding,
   because customers budgeting "per document" will be surprised.

## 5. Mistakes I made along the way (and how I caught them)

- **Scorer bug.** My first scoring counted `15kg` vs `15 kg` as wrong, so the first report showed 91.2% instead of 93.3%. I fixed
  the scorer and didn't count it against Affinda.
- **A false encoding bug.** I briefly logged "Affinda returns `â€“` instead of an en dash". Before escalating I checked
  the codepoints: Affinda returns U+2013 correctly. My own script had read the UTF-8 file with the Windows default encoding.
  I removed it from the feedback list. Lesson: reproduce before escalating.
- **Container numbers.** My synthetic container numbers don't have valid check digits either, the same as the real sample. That's another
  reason the check-digit rule stays off.

## 6. Next steps

| Step | Owner | Due | Credits |
|---|---|---|---|
| Apply field-description changes + repeating fields (`config_tuning.md`) | Affinda | 12 Oct | 0 |
| Re-test the same 13 documents (`--label tuned`) | Affinda | 14 Oct | ~14 |
| Run the 6 holdout documents (`--label holdout`) | Affinda | 14 Oct | ~6 |
| Decide lbs/kg handling (D3) | Wattlebird | 13 Oct | n/a |
| UAT sign-off meeting | Wattlebird | 16 Oct | n/a |
