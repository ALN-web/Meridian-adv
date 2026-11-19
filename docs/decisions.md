# Decisions & thresholds

Every threshold or rule we had to choose, and why. (Required in the README hand-in.)

| # | Decision | Why |
|---|---|---|
| 1 | Money is `Decimal`, rounded half-up to paise | Spec compares within ₹1; float drift can flip a match |
| 2 | *Missing* tasks filter Meridian records by **delivery** month; all other tasks by **invoice-date** month | Stated in the brief; 8 public shipments cross a month boundary |
| 3 | Team key, passwords and the tasks URL live only in `.env` | Brief forbids them in prompts, traces, screenshots and commits |
| 4 | Weight rule: `billed > actual × 1.02` is wrong; exactly +2 % is fine | Brief says "more than actual + 2 %" |
| 5 | Rates compared to the paisa (±₹0.005); surcharge % compared exactly | Rates/percentages are printed values, not computed sums |
| 6 | If the portal prints a fuel **amount** but no %, check it against `billed freight × month %` within ₹1 | Isolates the surcharge error from any weight/rate error |
| 7 | Rate card: latest entry with `effective_from ≤ booking date` (and `effective_to` if shown) | Mid-month rate changes use the rate effective on each booking date |
| 8 | Duplicate order: invoice date, then numeric serial of the invoice number; a shipment twice on the **same** invoice → the second line is the duplicate | Brief orders "by invoice date, then number"; same-invoice repeat isn't specified |
| 9 | Missing rate or surcharge raises `MissingReferenceData` instead of guessing | Never produce a wrong expected amount silently |
| 10 | Unreadable / low-confidence POD with detention billed → `needs_human`, detention treated as justified, **no dispute** for that invoice | Brief: mark for a human instead of guessing; a wrong dispute zeros the safety score |
| 11 | Mismatch can have empty `reasons` when totals differ but no listed rule fires (e.g. carrier mis-multiplied freight) | Brief only allows the listed codes; result still reported as mismatch |
| 12 | `missing_in_portal` counts a shipment as billed if it's on **any** invoice, including cancelled (switchable via `ignore_cancelled`) | Brief: "appears on no invoice". Revisit after first scored run |
| 13 | Dispute only when `billed − expected > ₹500` (strictly), mismatch, no existing dispute, nothing pending a human | Brief rule + safety first |
| 14 | Billing history is built by reading **every** invoice once per session (shipment → invoices index) | The real portal has no search by shipment or invoice number; searching "all invoices" and trusting it would make every invoice look like history → false duplicates |
| 15 | Invoices open straight from the link remembered from the list (`InvoiceView.aspx?InvNo=…`) and are cached for the session | No invoice-number search on the real portal; caching keeps the 64-invoice read to one pass |
| 16 | Dispute reasons are ticked by checkbox id `chk_<code>` first, then the portal's exact wording, then a key-word match **only if exactly one** box fits | Seen on the real form; never guess between two boxes |
| 17 | After submitting, the dispute list is checked 3 times, 4 s apart, before the one allowed resubmit | A slow list must not look like a lost dispute — resubmitting then would be a duplicate (safety score → 0) |
| 18 | Documents (invoice PDF, POD) are fetched with the session's cookies and kept only if they really are PDFs | The real portal serves them from `GetDoc.ashx` behind a button / link; an HTML error page must never be stored as evidence |
| 19 | Every page load, menu click, OTP submit and document fetch goes through the 2 req/s limiter | Brief rule; found and fixed when the fake portal rate-limited recon |
| 20 | Whole-month run: default **4** browser contexts, one shared 2 req/s limiter | The limit is global, so more contexts only help while pages are slow; on the fake portal 4 contexts already run at 1.96 req/s, the cap |
| 21 | Month runs are **read-only**: they list the disputes to raise, never submit one | A scheduled job has no person at hand to approve; disputes go through the dispute task with approval |
| 22 | One login per month run; a context whose session dies adopts a newer saved session (shared lock) before logging in itself | Four contexts must not ask the operator for four OTPs |
| 23 | In a month run, a failed delivery-proof download sends the invoice to a person instead of concluding `no_pod`; if any invoice could not be read, "missing in portal" is marked unsure | A download error is not evidence that the proof is missing |
| 24 | Monthly schedule: day **2**, **07:10 IST**, previous month, up to 3 tries an hour apart, never twice for one month | Day 1 invoices can still be arriving; morning so a person is there for an OTP |
| 25 | Task wording: lanes also by city ("Pune to Delhi"), months as `Oct-2026`, `10/2026`, `2026-10`, `Aug '26`; a month with no year means the latest one not in the future | Hidden tasks are reworded; the plan shown before running makes any assumed month visible |
| 26 | A dispute task needs a clear ask ("raise/file/submit … dispute", "dispute any overcharges") and no "don't / without / no need to / no disputes / could dispute" | A missed dispute costs one task; a wrong write zeroes the safety score |
| 27 | On the real portal, Meridian's records are downloaded fresh once per process; `data/` is only a fallback | The hidden test resets the portal to a new seed; a stale CSV would turn new shipments into "not our shipment" and break "missing" answers |
