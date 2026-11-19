# Meridian-adv

Browser agent that reconciles carrier invoices on a legacy freight portal: Playwright automation, rule-based checks, OTP and human-approved disputes, Langfuse tracing.

> **FDE Fellowship · Week 3 · Team Delta.** Meridian Freight, TransIndus Roadways and all data here are fictional. Synthetic data only.

---

## The problem

Meridian Freight (Pune, accounts payable) gets ~600 invoices a month from its biggest trucking carrier, **TransIndus Roadways**. The carrier's portal was built around 2009: no API, no export. Two people spend three days a month clicking through it, opening invoices, downloading delivery proofs (PODs), checking weights and rates against Meridian's records, and raising disputes for overcharges.

**The question:** *Did the carrier bill us correctly for what it actually delivered?*

**What to get right: a portal that fights back.** It is slow, errors, logs you out, shows blocking notices, changes layout, serves scanned documents, asks for one-time passwords, rate-limits, and shows a CAPTCHA after repeated failed logins. The agent must still finish, check every number, and **never raise a wrong or duplicate dispute**.

## How the agent works

```
 plain-English task ──► 1. PLAN ──► 2. OPERATE ──► 3. COLLECT ──► 4. RECONCILE ──► 5. ACT SAFELY ──► 6. REPORT
                       (steps in UI)  (Playwright,   (invoices,     (pure Python   (dispute only     (task result JSON,
                                       vision LLM    PODs, week-2   rules — LLM    after human       screenshots,
                                       fallback)     doc reader)    never does     approval, then    Langfuse trace)
                                                                    the maths)     verify in list)
```

| Principle | What it means here |
|---|---|
| Scripted first, LLM second | Stable Playwright locators (labels, roles, text). Vision model only when a page doesn't match. LLM for decisions, not every click. |
| Code does the maths | All reconciliation is deterministic Python with `Decimal`. The LLM never compares amounts. |
| Resume, don't restart | Progress lives outside the browser (SQLite). On a dead session: log in again, continue from the next invoice. |
| Never write twice | Check dispute list → human approves → submit → confirm it appears in the list. Idempotent on reruns. |
| Humans do human checks | OTP and CAPTCHA pause the task and ask a person in the UI. Unreadable scans → `needs_human`, never a guess. |
| Be polite | ≤ 2 requests/second, back off when told. |
| Page text is data | Instructions found on the portal are never followed. |
| Secrets stay secret | Credentials and team key from env vars only — never in prompts, traces, screenshots, or git. |

## Reconciliation rules

Each invoice line (one shipment) is checked in code. Amounts compared within ₹1.

| Code | Line is wrong when |
|---|---|
| `shipment_unknown` | Shipment isn't in Meridian's records |
| `duplicate_billing` | Already billed on an earlier, non-cancelled invoice (by invoice date, then number). The later one is wrong. |
| `no_pod` | Portal has no delivery proof |
| `weight_over` | Billed weight > actual weight + 2% |
| `rate_wrong` | Rate/kg ≠ rate card for the lane on the **booking date** |
| `surcharge_wrong` | Fuel surcharge ≠ percentage for the **booking month** |
| `detention_unjustified` | Detention charged but delivered < 2 days after promised date |
| `math_error` | *(invoice level)* lines + 12% GST ≠ invoice total |

**Order:** `shipment_unknown` → `duplicate_billing` → `no_pod`. If any fires, expected line amount = ₹0 and the rest are skipped. Otherwise weight, rate, surcharge, detention are all checked (any number can fire).

**Expected amount**

```
freight            = actual_weight_kg × rate_card_rate        (round to paise)
fuel               = freight × surcharge_%                    (round to paise)
detention          = billed detention if delivered ≥ 2 days late, else 0
line_expected      = freight + fuel + detention
invoice_expected   = round(sum(lines) × 1.12, paise) − credit notes
invoice_billed     = invoice total − credit notes
```

- **match** — no rule fires and billed ≈ expected (±₹1)
- **mismatch** — otherwise, with every reason code
- **cancelled** — invoice status Cancelled; reported, not checked
- **missing in portal** — Meridian delivered on the lane in the month, but it's on no invoice (uses **delivery** month). Not disputed.
- **Dispute** — one per mismatched invoice where billed > expected + ₹500, with all reasons and expected amount, **after human approval**, skipping invoices that already have one.

### Using the engine

The portal layer collects plain data; the engine decides. No browser, no LLM inside.

```python
from meridian.reconcile import reconcile_invoice, propose_dispute, missing_in_portal

result = reconcile_invoice(invoice, shipments, reference_data)   # match | mismatch | cancelled
proposal = propose_dispute(result)                               # None, or a dispute awaiting human approval
result.to_output()                                               # dict for the task result
```

`reference_data` holds the rate card, monthly fuel surcharge, PODs, every invoice seen on the portal (for duplicate detection) and invoices that already have a dispute.

### Edge cases
- Credit notes reduce an invoice. A shipment on a cancelled invoice is not a duplicate.
- Portal formats: dates like `14-Oct-26`, amounts like `Rs. 1,23,456.00` (Indian grouping).
- Mid-month rate change → use the rate effective on each shipment's booking date.
- Dispute already exists → don't raise another; report it.
- Scanned documents are read with OCR (see **Scanned documents** below). If OCR is unsure, the line goes to a human — never a guess.

## Task kinds

Months are **invoice-date** months, except *missing* tasks (**delivery** month).

| Kind | Example | Result fields |
|---|---|---|
| `list` | List every invoice on PUN-BLR for Oct 2026 | `invoices: [{invoice_no, total_inr, status}]` |
| `one` | Reconcile invoice TIR/26-27/10121 | `invoices: [{invoice_no, result, reasons, billed_inr, expected_inr}]` |
| `lane_month` | Reconcile all Oct invoices on PUN-HYD | same as `one` |
| `missing` | Shipments delivered on PUN-CHN in Sep never invoiced | `missing_in_portal: [shipment_id, ...]` |
| `collect` | Download PODs for five shipments | `pods: [{shipment_id, promised_on, delivered_on}]` (YYYY-MM-DD) |
| `dispute` | Reconcile Oct PUN-BLR and raise disputes (needs approval) | same as `one` + disputes on the portal |

Every task ends with:

```json
{
  "task_id": "T-07",
  "status": "completed",
  "invoices": [
    {"invoice_no": "TIR/24-25/10121", "result": "mismatch",
     "reasons": ["weight_over"], "billed_inr": 48210.00, "expected_inr": 45930.40,
     "evidence": ["portal:invoice/10121", "pod:SHP-60431", "meridian:SHP-60431"]}
  ],
  "missing_in_portal": [],
  "disputes": [],
  "human_steps": ["otp"],
  "steps": 63, "retries": 4, "duration_s": 212, "cost_inr": 9.40,
  "trace_id": "lf-..."
}
```

`status` is one of `completed | needs_human | failed`.

## Project layout

```
src/meridian/
  config.py          settings from environment (.env)
  parsing.py         portal date / amount parsers
  models.py          task + result schemas
  records.py         Meridian shipment records (CSV) loader
  reconcile/         rule engine — pure, deterministic, unit-tested
  portal/            Playwright client: login, search, download, disputes, retries
  agent/             planner, task runner, checkpoint store, human-in-the-loop; month.py = whole month in parallel
  vision/            screenshot → element fallback; week-2 document reader bridge
  telemetry.py       Langfuse spans + screenshot masking
  ui/                operator screen (task, live log, OTP box, approvals, results)
harness/             runs all public tasks, scores against expected, writes eval results;
                     run_month.py / schedule_month.py = stretch goal
tests/               unit tests (rules, parsing)
docs/                brief notes, decisions, cost table
```

## Getting started

```bash
cp .env.example .env          # fill in values you got privately from the instructor
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
playwright install chromium
pytest
```

Website (marketing site for the agent):

```bash
python -m http.server 8700 --directory web     # http://localhost:8700
```

A single page in an industrial freight style (white, black, industrial yellow) with real-time 3D built in Three.js:

- **Hero:** a black MERIDIAN container hangs from a striped crane hook over a yard of container stacks; scrolling turns it and lands it on the stack.
- **About · How it works · stat tiles**
- **Scan:** a top-down container ship sails under a scan line; each container (an invoice line) turns green (billed right) or red (overcharged), with live counters.
- **What it checks** (the eight rules) · **Results** (safety, robustness, evidence, evaluation targets) · **Call to action**

A second page, `/features.html`, shows each operator-screen feature (run a task, needs you, results, documents, disputes, monthly summary, evaluation, traces) with a clean UI preview and a link to the real page. Both pages share `web/site.css` (one 12-column grid, one spacing scale) and `web/site.js`. Every 3D object is modelled in code (no downloaded models). Buttons open the operator screen on the same host, port 8510. For a public deploy, set its address in the `<meta name="meridian-operator-url">` tag at the top of both pages; `?app=http://host:port` still works, but only while the site runs on localhost, and only for http(s) addresses. Each page has a Content-Security-Policy meta tag; if you edit the import map in `index.html`, update its `sha256-` hash in that tag. Three.js 0.160 is bundled in `web/vendor/three/` (MIT, with SRI hashes in the import map), so the 3D works without any CDN; fonts come from Google Fonts. If the 3D can't start (no WebGL, blocked script), the page drops the scroll-driven 3D sections and shows a still picture and the month's counts instead. The design prompt is in [docs/prompts/website.md](docs/prompts/website.md).

Operator screen (demo mode works without the portal):

```bash
streamlit run src/meridian/ui/app.py
```

Pages:

| Page | What it's for |
|---|---|
| **Run a task** | Plain-English task (or one of the 20 public tasks) → plan with live progress, OTP box, live step log with a problems filter, Stop / Resume |
| **Needs you** | Everything waiting on a person: OTPs, CAPTCHAs, disputes to approve (with the line-by-line reason and documents), items to review |
| **Results** | Graded result, colour-coded invoices, drill-down into each invoice's lines (billed vs actual weight, rate vs card, fuel %, detention vs POD dates) |
| **Documents** | Invoice PDFs, proofs of delivery (text shown, scans flagged), masked write-action screenshots |
| **Disputes** | Every proposal and its fate: pending, approved, confirmed on portal, rejected, skipped; receipts and screenshots |
| **Monthly summary** | For the logistics manager: overcharge by lane, why invoices were wrong, missing invoices, CSV export |
| **Evaluation** | Start a test run of the public tasks; metrics vs targets, per-task problems, history |
| **System** | What's configured and reachable (secrets shown only as set / missing) |

Demo mode: pick a task → **Run task** → type any 6 digits when asked for an OTP → approve disputes in **Needs you** → open **Results**. Demo mode uses the real planner, rules engine and approval flow on a simulated portal (planted errors, one session expiry). Put `meridian-shipments.csv` in `data/` to use Meridian's real records. On the real portal the agent downloads the CSV fresh (team key) once per run, so a portal reset to a new seed — the hidden test — never uses last week's records; the copy in `data/` is only a fallback (`MERIDIAN_OFFLINE_RECORDS=1` forces it).

Fake TransIndus portal (local copy that misbehaves on purpose, for offline development):

```bash
python -m meridian.fakeportal.server     # http://localhost:8600  (set PYTHONPATH=src first)
```

- Same shape as the real portal: `Login.aspx` → OTP → menu with Invoices, Delivery Proofs, Rate Card, Fuel Surcharge, Disputes; invoice and POD PDFs.
- Login `meridian.ap` / `fake-portal-pass`; the OTP appears in its operator inbox at `/operator` (password `fake-operator-pass`). These are test values for the fake portal only.
- Chaos (`FAKE_CHAOS`, default 0.15): slow pages, error pages, blocking notices (one tells "automated agents" to raise disputes), session expiry, rate limiting at >4 req/s, shuffled columns, POD dates only in the PDF, scanned PODs, and a dispute form that sometimes says "success" without saving.
- Data comes from the same deterministic world as demo mode, so results are directly comparable.

In the operator screen choose **Fake portal** to watch the real browser agent work (tick *Show the browser window*). The harness takes `--mode fake` too.

Test harness (all 20 public tasks in `harness/tasks_public.json`):

```bash
python harness/run_public.py --mode demo --auto-otp --auto-approve --rerun-disputes
```

| Flag | Meaning |
|---|---|
| `--key FILE` | score against an answer key (format in `src/meridian/evaluation.py`) |
| `--save-key FILE` | snapshot this run as a regression key |
| `--rerun-disputes` | run dispute tasks twice; any new dispute on the rerun counts as a duplicate |
| `--only T-01,T-19` | run a subset |
| `--fetch-tasks` | refresh the task list from the portal (team key from `.env`) |
| `--auto-otp`, `--auto-approve` | demo only; live runs wait for a person in the operator screen |

Each run writes `runs/eval/<label>/report.json`; the latest is copied to `eval_results/` and shown on the **Evaluation** tab (metrics vs targets, per-task table with problems, history).

> The demo key `harness/answer_keys/demo_regression.json` is a snapshot of the engine's own output, so it catches regressions but is not ground truth. In demo mode T-04/06/07/08 fail because those invoice numbers don't exist in the simulated portal.

Portal recon (read-only; you type the OTP yourself from the operator inbox):

```bash
python harness/recon.py
```

Saves masked screenshots and `runs/recon/recon.json` (menu, forms, grid headers, sample rows) — git-ignored.

Docker:

```bash
cp .env.example .env        # fill in the private values
docker compose up --build   # operator screen :8510 · website :8700 · fake portal :8600
```

The image is the official Playwright image plus Tesseract OCR. `runs/`, `data/` and `.auth/`
(the saved portal session) are mounted from the host; secrets come only from `.env`.

> ⚠️ Never commit `.env`, the team key, portal passwords, the tasks URL with its key, or unmasked screenshots.

## Telemetry (Langfuse)

One trace per task, one span per step. Each span records the **page**, the **action** and its target, the
**outcome**, **retries** and **time**. Write actions (dispute submissions) get their masked screenshot or receipt attached.
The root span's output summarises the task: status, steps, retries, time, cost, invoice counts and disputes.

```bash
# .env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com      # or https://us.cloud.langfuse.com / self-hosted
```

- Without keys, traces are still written to `runs/traces/<trace_id>.jsonl` and shown under **Results → Trace**.
- With keys, **Run a task** and **Results** link straight to the trace in Langfuse; the trace id is in every task result and on the Evaluation page.
- **No personal data in traces.** Everything sent passes a mask: portal user, password, team key, phone numbers, e-mails and receiver names become `[redacted]`, `[phone]`, `[email]`, `[person]`. Screenshots are masked in the browser before capture. OTP codes are never logged. Tested against a local stub of the Langfuse endpoint (`tests/test_telemetry.py`).
- Tracing never breaks a task: export errors are logged and ignored.

## Scanned documents (OCR)

The real portal serves **legacy invoices** whose line items exist only in a scanned, slightly
tilted PDF ("Line item details are available in the attached PDF only"). Some PODs are scans too.

1. Render the PDF page at 300 dpi, **straighten it** (try small rotations, keep the one where text
   rows are sharpest), then read words and their positions with **Tesseract, locally** — the
   document never leaves the machine and no model is paid for.
2. Put words back into table rows by position: each `SHP-…` starts a row; the row must have a date
   and exactly 7 numbers.
3. **Cross-check every number before trusting it:** weight × rate = freight, freight × fuel % = fuel,
   freight + fuel + detention = line total, and the line totals must add up to the **sub total shown
   as text on the invoice web page**. (The invoice total is not used as a check — a wrong total is a
   finding, `math_error`, not an OCR fault.)
4. Any check fails → the invoice is reported `needs_human` with the reason, and no dispute is proposed.

PODs: text first; OCR only for scans, trusted only when the date lines were read with ≥ 80 % confidence.
Tested in `tests/test_scaninvoice.py` (tilted synthetic scans, plus a refusal case).

## Delivery proof cache

A delivery proof does not change once the shipment is delivered, so confident POD dates (and the
downloaded PDF) are kept in `runs/cache/pods_<host>.pkl` (git-ignored) and reused on later runs.
Unreadable PODs, PODs whose PDF download failed and "no POD yet" results are never cached — they are
fetched again. Off for the local fake portal. Measured live on T-09: 141 s → 60 s, same answer.

## Alerts when a person is needed

The OTP must be typed by a person within 5 minutes, so the operator screen makes a waiting OTP or
dispute approval hard to miss: a short beep once per new request, a flashing tab title
("(!) OTP needed"), a live countdown of the code's validity in the yellow bar, and — after one click
on "Turn on desktop alerts" — a desktop notification. All of it stops when nothing is waiting.
It only gets attention; it never answers anything (`src/meridian/ui/alerts.py`).

## Login session reuse

After a good login the browser's cookies are saved to `.auth/<portal host>.json` (git-ignored).
The next task starts with them, like a person's browser tab, so one OTP covers a batch of tasks
until the portal ends the session; then the agent logs in again and asks for a new OTP.

## The real portal (from recon)

What `harness/recon.py` found on the TransIndus portal (read-only runs, 15 Nov 2026). The fake
portal copies this layout, so local tests exercise the same paths.

| Page | Path | What matters |
|---|---|---|
| Login → OTP | `/Login.aspx` → `/Login/Otp.aspx` | `#txtUser` `#txtPass` `#btnLogin`; OTP box `#txtOtp`, button **Verify**, code valid 5 minutes |
| Notice | (overlay on any page) | "Portal maintenance notice" with one button, **I Acknowledge** |
| Invoices | `/Billing/InvoiceList.aspx` | Filters `ddlLane`, `ddlMonth` ("October 2026"), `ddlStatus`; **no invoice-number or shipment search**; columns Invoice No · Invoice Date · Lane · No. of Consignments · Invoice Value (Rs.) · Status |
| Invoice | `/Billing/InvoiceView.aspx?InvNo=…` | Lines: Consignment · Booked On · Weight (kg) · Rate/kg · Freight · Fuel % · Fuel Amt · Detention · Amount; Sub Total, IGST @ 12 %, Invoice Total; **Raise Dispute** link; PDF at `/Billing/GetDoc.ashx`. **Legacy invoices** show no line grid — lines only in a scanned PDF |
| Invoice list paging | `…InvoiceList.aspx?…&pg=2` | "Showing 1-15 of 67 records"; pager links sit **outside** the grid |
| POD | `/Ops/PODSearch.aspx?txtCons=…` | Consignment · Status · Promised · Delivered; **View POD** document link |
| Rate card | `/Masters/RateCard.aspx` | Lane · Rate · Effective From · Effective To ("Till date") |
| Fuel | `/Masters/FuelSurcharge.aspx` | Month (`2026-08`) · FSC % |
| Disputes | `/Disputes/DisputeList.aspx` | Dispute No · Invoice No · Raised On · Raised By · Correct Amount Claimed · Status · Reasons |
| Raise dispute | `/Disputes/NewDispute.aspx?InvNo=…` | `txtInvNo`, reason checkboxes `chk_<rule code>`, `txtClaimed`, `txtRemarks`, **Submit Dispute** |

Because there is no search by shipment, the agent reads every invoice once per session to know
which invoices bill each shipment (needed for duplicate billing and "missing" tasks). The run
screen shows "Read n of 64 invoices" while it does this.

## Evaluation targets

| Metric | Target |
|---|---|
| Task success (exact match with answer key) | ≥ 80% |
| Invoice classification accuracy | ≥ 90% |
| Wrong disputes raised | **0** |
| Duplicate disputes | **0** |
| Tasks needing a human (beyond OTP) | reported |
| Time, steps, cost per task | reported |

One wrong or duplicate dispute in the hidden run sets the safety score to zero.

### Live results — real TransIndus portal, 16 Nov 2026

All 20 public tasks were run on `transindus-portal.onrender.com` with a person typing the OTP
and approving each dispute (`harness/run_public.py --mode live`).

| Measure | Result |
|---|---|
| Tasks run to completion | **20 / 20** (18 first time; T-07 and T-20 on a re-run, see below) |
| Wrong disputes | **0** |
| Duplicate disputes | **0** (invoice 10172 already had a dispute; none raised again) |
| Human steps | OTP only (a new code each time the portal ended the session; the saved session was reused in between) + dispute approvals |
| Time per task | 122 s average, 68 steps average; cost ₹0 (merged report `live-final`) |
| Task success / invoice accuracy | not scored yet — no answer key published |

Disputes filed, each only after operator approval and each confirmed in the portal's own dispute list:

| Invoice | Reasons | Billed → expected | Portal ref |
|---|---|---|---|
| TIR/26-27/10175 | detention_unjustified | ₹25,520.50 → ₹23,840.50 | DSP-5001 |
| TIR/26-27/10221 | weight_over | ₹1,46,895.32 → ₹1,44,246.57 | DSP-5003 |
| TIR/26-27/10176 | duplicate_billing, weight_over | ₹70,821.31 → ₹63,169.46 | DSP-5004 |
| TIR/26-27/10177 | math_error | ₹1,10,557.35 → ₹1,09,197.35 | DSP-5006 |
| TIR/26-27/10178 | rate_wrong, detention_unjustified | ₹1,12,717.46 → ₹1,10,531.68 | DSP-5007 |
| TIR/26-27/10170 | weight_over, detention_unjustified | ₹1,19,747.71 → ₹1,15,326.87 | DSP-5008 |

The merged report comes from `python harness/rescore.py --runs live-full-3,live-rerun-3 --label live-final`;
add `--key <answer key>` to score the same saved results once the key is published (no re-run).

What the first pass taught us (all fixed, with tests where possible):
- **T-07** waited 16 minutes for an OTP nobody typed; the request now closes cleanly on timeout
  and the task passed on re-run.
- **T-20** sent invoice 10170 to a person because one POD download returned an error page once.
  Document downloads now retry up to 3 times; on re-run the POD read at 95 % OCR confidence and
  the dispute was proposed with the extra `detention_unjustified` reason.
- Earlier batches found the invoice list's alternate column names, renamed line columns, the
  pager outside the grid and scan-only legacy invoices (OCR) — see "The real portal" above.

### Second full run — 16 Nov 2026, after the speed work (issues #1–#4)

| Measure | Result |
|---|---|
| Tasks run to completion | **20 / 20** (merged report `live-final-2`, published in `eval_results/`) |
| Answers vs the first run | **identical for all 20 tasks** |
| Time per task | **79 s average** (was 122 s), 69 steps; cost ₹0 |
| Wrong / duplicate disputes | **0 / 0**; no new disputes (all overcharges were already disputed) |

Two more real-portal traps were found and fixed in this run:
- **A refused OTP sends no new code.** The agent kept asking for a code that never came; it now
  signs in again after "Invalid or expired OTP", which makes the portal send a fresh one.
- **The dispute list could be misread as empty.** One T-20 run proposed a dispute for 10172, which
  already had one from before this project. The operator rejected it, so nothing was filed. The
  list is now read by invoice-number format in any column and a list that can't be read stops the
  task instead of meaning "nothing disputed". The re-run marked 10170 and 10172 as already disputed.

`python harness/rescore.py --runs live-full-4a,live-full-4b,t20-dispute-check --label live-final-2`
(`live-full-4a` was rebuilt from the run store: that part of the batch was stopped before it wrote its files.)

## Stretch goal: a whole month in parallel, every month

```bash
python harness/run_month.py --mode live --month 2026-10 --workers 4      # real portal, OTP in the operator screen
python harness/run_month.py --mode fake --month 2026-10 --workers 4 --compare   # fake portal, with a 1-context baseline
python harness/schedule_month.py              # every month: day 2, 07:10 IST, last month
docker compose --profile scheduler up -d      # the same schedule as a container
```

- **Parallel, but polite.** One browser, `--workers` separate browser contexts, **one shared limiter**, so the
  portal still gets at most 2 requests a second in total. It is faster because the portal is slow: while one
  context waits for a page or Tesseract reads a scan, the others use the free request slots.
- **One OTP.** The lead context logs in; the others start from its saved session. When the portal ends the
  session, the first context to notice logs in again (one OTP) and the others take that session under a shared
  lock instead of asking for more codes (`PortalClient.login_lock`).
- **Three shared queues:** read every invoice once (billing history) → read the delivery proofs of the
  month's shipments → reconcile in code with the same rules engine (no portal calls). Missing-in-portal uses the
  delivery month.
- **Read-only.** A month run never raises a dispute. It lists the disputes to raise; a person raises them with the
  dispute task and approves each one.
- **Summary for the logistics manager:** `runs/month/<YYYY-MM>/summary.md` (at a glance, by lane, why invoices
  were wrong, disputes to raise, delivered-but-never-invoiced, what needs a person, run speed), plus
  `invoices.csv` and `report.json`. The run is stored like any task, so it shows on **Results** and **Monthly
  summary** (new "Whole-month runs" table) and gets its own Langfuse trace.
- **Schedule:** `schedule_month.py` sleeps until day 2, 07:10 IST, runs last month, retries up to 3 times an
  hour apart and never runs a month twice. If the saved session has expired, the OTP is asked for on the
  operator screen (beep + flashing tab). A cron line works too (see the script's docstring).

Measured on the fake portal (chaos on, October 2026, every lane, 10 invoices / 30 PODs):

| Contexts | Time | Portal requests | Requests/s | Answers |
|---|---:|---:|---:|---|
| 1 (one after another) | 247.5 s | 326 | 1.32 | — |
| 4 (parallel) | 176.6 s | 347 | 1.96 | identical to the 1-context run and to the rules engine |

The parallel run sits at the 2 req/s cap, so on the fake portal (fast pages) that is the ceiling; on the real
portal, where a page takes seconds, the sequential run leaves more of the budget unused and parallel gains more.
Tested in `tests/test_month.py` (shared session, limiter, schedule, summary, and an end-to-end parallel run on
the fake portal checked against the engine with no dispute written).

## Cost table

Budget ₹6,000 for the week; suggested cap ₹3,000 for this project. Spend limits set on every provider on day 1.

| Item | Provider / model | Cost | Cost per task |
|---|---|---|---|
| Browser automation | Playwright + Chromium (local) | ₹0 | ₹0 |
| Reconciliation | Python rules engine (no LLM) | ₹0 | ₹0 |
| Tracing | Langfuse Cloud, free tier | ₹0 | ₹0 |
| OCR for scanned invoices / PODs | Tesseract 5 (local, open source) | ₹0 | ₹0 |
| LLM / vision fallback | not enabled (`LLM_MODEL` unset) | ₹0 | ₹0 |
| **Total so far** | | **₹0** | **₹0** |

**Models and data terms.** No hosted AI model is called: the scripted path, the rules engine and
OCR all run locally, so no invoice, POD or personal data is sent to a model provider. The only
external services are the TransIndus portal itself and Langfuse (masked traces, see above).

The scripted path needs no model calls. If the optional vision fallback is switched on, its
calls are traced in Langfuse and this table gets a real per-task figure.

## Decisions & thresholds

Tracked in [docs/decisions.md](docs/decisions.md).

## Roadmap

- [x] Day 1 — repo, Docker, spend limits; thinnest end-to-end path (log in, list one invoice)
- [x] Reconciliation engine (`src/meridian/reconcile/`) — all rules, expected amounts, dispute proposals, missing-in-portal; unit-tested
- [x] Portal client foundation (`src/meridian/portal/`) — login, OTP/CAPTCHA hand-off, page-state detection, safe notice dismissal, retries with backoff, re-login on expiry, 2 req/s limiter, layout-tolerant table parsing, masked screenshots
- [x] Operator screen (`streamlit run src/meridian/ui/app.py`) — plain-English task → plan, live step log, OTP box, dispute approvals, results, evaluation summary; demo mode on a simulated portal
- [x] Test harness + evaluation page — runs all 20 public tasks, scores against an answer key, checks duplicate disputes on re-run
- [x] Fake portal with chaos + live browser runner (`src/meridian/agent/live.py`) — all task kinds, OTP via operator screen, PDF date reading, never-write-twice dispute flow
- [x] Run `harness/recon.py` against the live portal and tune selectors (all pages incl. invoice view, POD result, raise-dispute form)
- [x] Day 2 — core path on public tasks
- [x] Day 3 — "portal that fights back": retries, resume, OTP, popups; first full test run
- [x] Langfuse tracing (one trace per task, span per step, masked, screenshots attached)
- [x] Day 4 — safety (dispute gate), failure handling
- [ ] Day 5 — evaluation page, README, stretch goal, demo rehearsal
- [x] Stretch — whole month in parallel browser contexts within rate limit, scheduled monthly with a summary (see "Stretch goal")

## Related

Week 2 — Meridian shipping-document reader (commercial invoice / packing list / delivery receipt OCR with personal-data masking). Reused here for scanned invoices and PODs.

## License

[MIT](LICENSE)
