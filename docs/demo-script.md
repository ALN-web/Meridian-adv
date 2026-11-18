# Demo script — 8 minutes

Team Delta · Meridian Freight × TransIndus Roadways · Browser agent for accounts payable.

## Before you start (5 minutes earlier)

- Start: operator screen `python -m streamlit run src/meridian/ui/app.py --server.port=8510`, website
  `python -m http.server 8700 --directory web` (or `docker compose up`).
- Open the TransIndus portal once in a normal browser so the Render server is awake (first load ~60 s).
- Have the OTP inbox open **on your own screen** (the agent never opens it).
- Open in tabs: website `:8700`, operator hub `:8510`, Langfuse project, GitHub repo.
- Insurance: the 16 Nov live runs are already in the run list (all 20 tasks, 6 real disputes) —
  if the portal is slow or down, show those instead of a new run.
- Do **not** clear `runs/cache/` or `.auth/` before the demo: the invoice cache makes the live run
  take ~1 minute instead of ~10, and the saved session may skip the OTP.

## 0:00 – 1:00 · The problem (website)

Open `http://localhost:8700`.

> "Meridian gets about 600 invoices a month from TransIndus. The carrier's portal is from 2009 —
> no API, no export. Two people spend three days a month opening each invoice, checking it
> against Meridian's own shipment records, and raising disputes. Mistakes cost money."

Scroll to the scan section: each container is an invoice line, red = overcharged.

> "Our agent does that clicking for them — and it is built so it can never raise a wrong or duplicate dispute."

## 1:00 – 2:00 · The operator hub

Click **Open operator screen**. Point at: 3D hub with live figures, lanes from Pune, invoice board,
agent panel on the right.

> "Everything here is real results. The board: ink cells billed right, yellow overcharged."

## 2:00 – 4:30 · Live run on the real portal

In the agent panel: mode **Real portal**, task `Reconcile invoice TIR/26-27/10196.` → **Run**.

Narrate while it runs (plan card + log below the hub):
1. **Login → OTP.** The run pauses; the yellow bar says it needs you. Type the code from *your* inbox.
   > "The agent is not allowed to read the OTP. A person does human checks."
   If no OTP is asked: "It reused the login session from earlier — same as a person staying logged in."
2. **Notice popup** dismissed by its button — "and it never follows text written on the page".
3. **Invoice list, page 2 of 5** — "the portal has no search, so it pages through like a person".
4. **Invoice list → cached** — "It must know every invoice once, to catch a shipment billed twice.
   It remembers what it read, and re-reads an invoice only if the portal shows a new total or status."
5. **Legacy invoice** (show in **Results → run T-20 → Invoice detail → TIR/26-27/10170**, a scan-only
   invoice: 5 lines read by OCR, all sums checked — and it became real dispute DSP-5008):
   "Some invoices have no lines on the page — only a tilted scan. We straighten it, OCR it locally,
   and check every number: weight × rate = freight, the lines must add up to the sub total.
   If one check fails, it goes to a human — never a guess."

## 4:30 – 5:30 · Result and evidence

Open **Results** for the run. Drill into an invoice line: billed vs expected, the rule codes
(e.g. `weight_over`, `rate_wrong`), and the evidence (portal page, POD, Meridian record).

> "The maths is plain Python with Decimal. No AI model ever compares amounts."

## 5:30 – 6:30 · Safe dispute

Open **Disputes**: the 6 real disputes filed on the TransIndus portal on 16 Nov, each approved by
a person and confirmed in the portal's own list (DSP-5001 … DSP-5008). Practice-portal disputes are
hidden behind a switch. To show the approval step itself, run a dispute task in **Demo** mode and
approve it in **Needs you** — do not file a new real dispute on stage.

> "Before submitting, it checks the dispute list. After submitting, it does not trust the success
> message — it confirms the dispute is in the list. Re-running the task raises nothing new."

Show **Disputes** page: submitted → confirmed, with masked before/after screenshots.

## 6:30 – 7:30 · Proof it works

- **Langfuse**: open the run's trace — one span per step, page, outcome, retries, time; screenshots masked.
- **Evaluation** page, run `live-final`: all 20 public tasks completed on the real portal, 0 wrong
  and 0 duplicate disputes, ~2 minutes and ₹0 per task. Task success and accuracy say n/a until the
  answer key is out — "we score the saved results the moment it is published, no re-run needed"
- **Stretch (+10 %), 20 s**: **Monthly summary** → "Whole-month runs" table, and open
  `runs/month/2026-10/summary.md`. "Every lane of a month in 4 browser contexts under one 2 req/s limit
  and one OTP — 1.4× faster than one at a time with identical answers, read-only, scheduled for day 2
  of each month, with this summary for the logistics manager."
  (Run `python harness/run_month.py --mode live --month 2026-10 --workers 4` beforehand so it is a real-portal run.)

## 7:30 – 8:00 · Close

> "Scripted first, code does the maths, humans do the human checks, resume instead of restart,
> never write twice. Questions?"

## Likely questions

| Question | Short answer |
|---|---|
| Why not let an LLM read the pages? | Cost, speed and correctness. Stable locators first; numbers checked in code. |
| What if the portal changes layout? | Columns are found by header meaning, not position; pages are classified before acting. |
| What if OCR is wrong? | Every scanned row must pass arithmetic checks and add up to the page's sub total, or it goes to a human. |
| What did the real portal throw at you? | Paging outside the grid, renamed columns, scan-only invoices, a notice popup, OTP expiry, error pages instead of PDFs — each one fixed and tested. |
| What if it crashes mid-run? | Progress is in SQLite; **Resume** continues from the next invoice. |
| How do you avoid duplicate disputes? | Check the dispute list before, confirm in the list after, and skip invoices already disputed. |
| Doesn't parallel break the 2 requests/second rule? | No: all contexts share one limiter, so the total stays ≤ 2/s (the report shows the achieved rate). It's faster because the portal is slow, not because we push harder. |
| Four contexts, four OTPs? | One. Contexts share the saved session; after a logout the first one logs in again and the others adopt its session. |
| Where are the secrets? | Only in `.env` / environment; masked out of traces and screenshots; never in git. |
