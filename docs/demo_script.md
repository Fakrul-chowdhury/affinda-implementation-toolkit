# Demo script (about 5 minutes)

Set up before recording: `python app.py`, then open http://localhost:5000. Mock mode replays the recorded live Affinda
responses, so the demo costs no credits. Say that on camera.

| Time | Screen | What to say |
|---|---|---|
| 0:00 | README / app header | "I built this to show how I'd run an Affinda Extract implementation end to end: configure, test, track and support, using a fictional carrier, Wattlebird Freight." |
| 0:30 | Extract → **A01** | "A clean Wattlebird BOL. Sixteen fields, validation PASS, safe for straight-through processing into the TMS." |
| 1:00 | Extract → **R01** (real sample) | "A real ocean BOL. Affinda merged two container weights into 4.4 billion kg and couldn't parse a quantity written in words. Validation fails it, so it never reaches the TMS." Point at the raw vs parsed values. |
| 1:45 | Extract → **B01S** (phone photo) | "Here the Collect box was read as Prepaid from a photo. The first version of the rules let this through. I added a rule so freight terms from scans always get a human look, because that field drives billing." |
| 2:30 | **UAT** page | "Thirteen documents, live API, 14 credits. Accuracy is 93%, but the number I care about is documents auto-approved with an error: 3 with the original rules, 0 after. The cost is straight-through falling from 7 to 4. That's the trade-off I'd take to the customer." Open the full report and one document. |
| 3:15 | **Implementation** page | "The tracker reads the real UAT results, so the gate is amber: accuracy is below 95% and ocean BOLs are at 80%. The weekly status email is generated from the tracker, with a decision the customer owes us on lbs vs kg." |
| 4:00 | **Support** page | "A synthetic support queue modelled on the UAT issues. The keyword triage is 100% on wording it was built for and 16% on new wording, and I show both because the first number is meaningless. Unmatched tickets fall to a person rather than getting the wrong tag. The ranked product feedback links each item to real evidence from the live runs." |
| 4:40 | `docs/findings_memo.md` | "Everything is written up for the customer and for the product team, including two mistakes I made and caught." |

Tips: keep the browser at 100% zoom, close other tabs, and record at 1080p. If you show live mode, upload one document
only (1 credit per page).
