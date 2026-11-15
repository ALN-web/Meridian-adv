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
