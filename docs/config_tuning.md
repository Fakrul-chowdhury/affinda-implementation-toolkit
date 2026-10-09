# Affinda configuration tuning (UAT round 2)

These are the changes to make in the Affinda dashboard, then how to re-test. Each change maps to a finding in
`findings_memo.md`. The Affinda API doesn't expose field definitions for Extract document types, so these are
done in the UI: **Workspace → Workflow → Bill of Lading → Configure → Fields**.

## 1. Field changes

| Field | Change | Fixes |
|---|---|---|
| `trailerNumber` | Make it a **repeating / multiple** field. Description below | F6, F7 |
| `sealNumber` | Make it a **repeating / multiple** field. Description below | F6, F7 |
| `grossWeight` | Replace description | F1 |
| `quantity` | Replace description | F2, F3 |
| `sidNumber` | Replace description | F8 |
| `specialInstructions` | Replace description | F5 |
| `freightTerms` | Replace description | F4 (helps on PDFs; scans still go to review) |
| `weightUnit` (new) | Add a text field (or an enumeration of KG / LB if available) | Decision D3 |

### Descriptions to paste

**trailerNumber**
> Each trailer number or shipping container number on the document, one value per trailer or container (for example
> TRL-1234 or ABCU1234567-8). Include containers listed on attached or continuation pages.

**sealNumber**
> Each seal number on the document, one value per seal. Include seals listed on attached or continuation pages.

**grossWeight**
> The TOTAL gross weight of the whole shipment as one number, without units. If weights are only printed per container
> or per line, add them together. Never join two numbers into one.

**quantity**
> The TOTAL number of packages or handling units for the whole shipment, as digits. If the total is only written in words
> (for example "FIVE HUNDRED AND EIGHTY"), convert it to digits (580). If only per-line counts are printed, add them up.

**sidNumber**
> The Shipper Identification Number, only when it is explicitly labelled SID or SID#. Leave empty if there is no SID label.
> Never use PO numbers, booking numbers or invoice numbers.

**specialInstructions**
> Handling or delivery instructions written for this specific shipment (for example "Tail-lift required"). Leave empty if
> there are none. Ignore standard printed terms and disclaimers such as "CARRIER HAS NOT VERIFIED PARTICULARS".

**freightTerms**
> Which freight charge term applies: Prepaid, Collect or Third Party. Use the box that is ticked or marked, or the column
> where the freight amount is written.

**weightUnit** (new)
> The unit the gross weight is printed in: KG or LB.

## 2. Optional: Affinda validation checks

The document type's **Validation** tab can hold checks inside Affinda itself, so people reviewing in the Affinda UI see the
same rules as FreightRead. Mirror these from `rules/wattlebird.yaml`:

- Gross weight between 1 and 45,000
- Quantity is a whole number of at least 1
- Freight terms is one of Prepaid / Collect / Third Party
- BOL number is present

## 3. Re-test (after saving the changes)

Set `EXTRACTOR_MODE=live` in `.env`, then:

```bash
# Same 13 documents as the baseline (~14 credits)
python -m uat.run_uat --label tuned --mode live --only A01,A04,A05,A01S,B01,B02,B03,B01S,C01,C02,C02S,R01,R02

# Holdout: 6 documents never used for tuning (~6 credits). This is the honest number.
python -m uat.run_uat --label holdout --mode live --only A02,A03,A04S,B04,C03,C04
```

Then set `EXTRACTOR_MODE=mock` again. The UAT page in the app shows all runs side by side. Update `uat_results:` for G5
in `tracker/wattlebird_project.yaml` to point at the new run, so the status report reflects it.

Expected effect (a hypothesis to test, not a promise): fewer multi-value warnings, correct trailer/seal lists, fewer weight
and quantity errors on ocean BOLs. If merged weights persist after the description change, that confirms the
product-side issue (memo §4, item 1) and the review rule stays essential.
