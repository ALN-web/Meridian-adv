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

### Edge cases
- Credit notes reduce an invoice. A shipment on a cancelled invoice is not a duplicate.
- Portal formats: dates like `14-Oct-26`, amounts like `Rs. 1,23,456.00` (Indian grouping).
- Mid-month rate change → use the rate effective on each shipment's booking date.
- Dispute already exists → don't raise another; report it.
- Low-confidence scanned POD → flag for a human, don't guess.

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
  agent/             planner, task runner, checkpoint store, human-in-the-loop
  vision/            screenshot → element fallback; week-2 document reader bridge
  telemetry.py       Langfuse spans + screenshot masking
  ui/                operator screen (task, live log, OTP box, approvals, results)
harness/             runs all public tasks, scores against expected, writes eval results
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

Docker (target for hand-in):

```bash
docker compose up
```

> ⚠️ Never commit `.env`, the team key, portal passwords, the tasks URL with its key, or unmasked screenshots.

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

## Cost table

Budget ₹6,000 for the week; suggested cap ₹3,000 for this project. Spend limits set on every provider on day 1.

| Item | Provider / model | Cost | Cost per task |
|---|---|---|---|
| _TBD_ | | | |

## Decisions & thresholds

Tracked in [docs/decisions.md](docs/decisions.md).

## Roadmap

- [ ] Day 1 — repo, Docker, spend limits; thinnest end-to-end path (log in, list one invoice)
- [ ] Day 2 — reconciliation engine + core path on public tasks
- [ ] Day 3 — "portal that fights back": retries, resume, OTP, popups; first full test run
- [ ] Day 4 — safety (dispute gate), failure handling, Langfuse tracing
- [ ] Day 5 — evaluation page, README, stretch goal, demo rehearsal
- [ ] Stretch — whole month in parallel browser contexts within rate limit, scheduled monthly with a summary

## Related

Week 2 — Meridian shipping-document reader (commercial invoice / packing list / delivery receipt OCR with personal-data masking). Reused here for scanned invoices and PODs.

## License

[MIT](LICENSE)
