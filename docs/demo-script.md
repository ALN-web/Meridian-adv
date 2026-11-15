# Demo script — 8 minutes

Team Delta · Meridian Freight × TransIndus Roadways · Browser agent for accounts payable.

## Before you start (5 minutes earlier)

- Start: operator screen `python -m streamlit run src/meridian/ui/app.py --server.port=8510`, website
  `python -m http.server 8700 --directory web` (or `docker compose up`).
- Open the TransIndus portal once in a normal browser so the Render server is awake (first load ~60 s).
- Have the OTP inbox open **on your own screen** (the agent never opens it).
- Open in tabs: website `:8700`, operator hub `:8510`, Langfuse project, GitHub repo.
- Optional insurance: a finished live run already in the run list, in case the portal is slow.

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
2. **Notice popup** dismissed by its button — "and it never follows text written on the page".
3. **Invoice list, page 2 of 5** — "the portal has no search, so it pages through like a person".
4. **Reads every invoice once** — needed to catch the same shipment billed twice.
5. **Legacy invoice**: "This one has no lines on the page — only a tilted scan. We straighten it,
   OCR it locally, and check every number: weight × rate = freight, the lines must add up to the
   sub total. If one check fails, it goes to a human — never a guess."

## 4:30 – 5:30 · Result and evidence

Open **Results** for the run. Drill into an invoice line: billed vs expected, the rule codes
(e.g. `weight_over`, `rate_wrong`), and the evidence (portal page, POD, Meridian record).

> "The maths is plain Python with Decimal. No AI model ever compares amounts."

## 5:30 – 6:30 · Safe dispute

Open **Needs you** → a proposed dispute with reasons and expected amount. Approve (only if the
team agreed to file one live; otherwise show a demo-mode one).

> "Before submitting, it checks the dispute list. After submitting, it does not trust the success
> message — it confirms the dispute is in the list. Re-running the task raises nothing new."

Show **Disputes** page: submitted → confirmed, with masked before/after screenshots.

## 6:30 – 7:30 · Proof it works

- **Langfuse**: open the run's trace — one span per step, page, outcome, retries, time; screenshots masked.
- **Evaluation** page: public test set, metrics against targets (task success ≥ 80 %,
  invoice accuracy ≥ 90 %, 0 wrong, 0 duplicate disputes), time / steps / cost per task (₹0 — no paid model).

## 7:30 – 8:00 · Close

> "Scripted first, code does the maths, humans do the human checks, resume instead of restart,
> never write twice. Questions?"

## Likely questions

| Question | Short answer |
|---|---|
| Why not let an LLM read the pages? | Cost, speed and correctness. Stable locators first; numbers checked in code. |
| What if the portal changes layout? | Columns are found by header meaning, not position; pages are classified before acting. |
| What if OCR is wrong? | Every scanned row must pass arithmetic checks and add up to the page's sub total, or it goes to a human. |
| What if it crashes mid-run? | Progress is in SQLite; **Resume** continues from the next invoice. |
| How do you avoid duplicate disputes? | Check the dispute list before, confirm in the list after, and skip invoices already disputed. |
| Where are the secrets? | Only in `.env` / environment; masked out of traces and screenshots; never in git. |
