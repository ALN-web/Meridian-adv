# Feature inventory

Every feature the brief asks for (Meridian company page + Browser Agent project rules + team rules),
with status. ✅ done · 🟡 partial · ❌ not started · ⭐ stretch.

## 1. Agent core

| # | Feature | Source in brief | Status |
|---|---|---|---|
| 1.1 | Plain-English task → plan, plan visible in UI | Approach: Plan | ✅ rule-based planner (LLM fallback ❌) |
| 1.2 | Six task kinds: list, one, lane_month, missing, collect, dispute | Public tasks | ✅ |
| 1.3 | Task result JSON in the graded format | Task result | ✅ |
| 1.4 | Reconciliation rules in code, LLM never does arithmetic | Reconcile | ✅ |
| 1.5 | Edge cases: credit notes, cancelled, Indian amounts, `14-Oct-26`, mid-month rate, existing dispute, unreadable scan → human | Edge cases | ✅ |
| 1.6 | Meridian records from CSV (local or fetched with team key) | The portal | ✅ |

## 2. Browser operation

| # | Feature | Source | Status |
|---|---|---|---|
| 2.1 | Playwright navigation, waits, downloads; stable locators | Operate | ✅ fake and real portal (login, OTP, notice, paging, invoices, legacy scans) |
| 2.2 | Vision-model fallback when a page doesn't match | Operate | ❌ |
| 2.3 | LLM for decisions, scripted clicks | Operate | 🟡 no LLM used yet |
| 2.4 | Download every invoice PDF and POD | Collect | ✅ |
| 2.5 | Scanned PODs and legacy (scan-only) invoices read with OCR | Collect | ✅ local Tesseract + deskew + arithmetic cross-checks; unsure → human |

## 3. Robustness ("a portal that fights back")

| # | Feature | Status |
|---|---|---|
| 3.1 | Timeout + retry with backoff on every step; done vs failed | ✅ |
| 3.2 | Resume, don't restart (checkpoints outside the browser) | ✅ |
| 3.3 | Re-login on session expiry | ✅ |
| 3.4 | Blocking notices cleared without obeying their text | ✅ |
| 3.5 | ≤ 2 requests/s, back off when told | ✅ |
| 3.6 | Layout changes (column order / header wording) | ✅ |
| 3.7 | Page text is data, never instructions | ✅ |

## 4. Safety

| # | Feature | Status |
|---|---|---|
| 4.1 | Dispute = only write; human approves in UI | ✅ |
| 4.2 | Check dispute list before submit; confirm in list after (success message is not proof) | ✅ |
| 4.3 | Never a duplicate dispute (also on re-run) | ✅ |
| 4.4 | OTP and CAPTCHA → pause and ask a human; never open the OTP inbox | ✅ |
| 4.5 | Credentials only from env; never in prompts, traces, screenshots, git | ✅ |
| 4.6 | Screenshot of every write action, personal data masked | ✅ |

## 5. Operator screen (frontend)

| # | Feature | Who | Status |
|---|---|---|---|
| 5.1 | Start a task in plain English, examples incl. the 20 public tasks | AP executive | ✅ |
| 5.2 | Plan with live progress | AP executive | ✅ |
| 5.3 | Live step log (filter errors/retries) | AP executive | ✅ |
| 5.4 | OTP box; CAPTCHA "done" button | AP executive | ✅ |
| 5.5 | Disputes waiting for approval (approve / reject) | AP executive | ✅ |
| 5.6 | Results with evidence; drill into an invoice's lines (billed vs expected per line, why) | AP executive | ✅ |
| 5.7 | Downloaded proofs and invoice PDFs viewable | Demo script | ✅ |
| 5.8 | Write-action screenshots (dispute before/after submit) | Demo script | ✅ |
| 5.9 | Items needing a human (unreadable proofs, missing rates) | AP executive | ✅ |
| 5.10 | Stop a run; resume a failed run from its checkpoint | Operator | ✅ |
| 5.11 | Evaluation page: metrics vs targets, per-task table, history | Graders | ✅ |
| 5.12 | Run the public test set from the UI | Graders | ✅ |
| 5.13 | Monthly summary for the logistics manager (overcharges by lane/reason, disputes, amount at stake) | Logistics manager | ✅ |
| 5.14 | System status: portal reachable, credentials/LLM/Langfuse configured (never values) | Operator | ✅ |
| 5.15 | Link to the Langfuse trace per run | Demo script | ✅ |

## 6. Testing & evaluation

| # | Feature | Status |
|---|---|---|
| 6.1 | Run all 20 public tasks from a script, unattended except OTP | ✅ |
| 6.2 | Results stored per run, shown on an evaluation page | ✅ |
| 6.3 | Metrics: task success ≥ 80 %, invoice accuracy ≥ 90 %, 0 wrong / 0 duplicate disputes, human steps, time/steps/cost | ✅ (needs real answer key) |
| 6.4 | Fake portal for offline testing with failures | ✅ |

## 7. Telemetry

| # | Feature | Status |
|---|---|---|
| 7.1 | One Langfuse trace per task, one span per step (page, action, outcome, retries, time) | ✅ (+ local copy) |
| 7.2 | Screenshots attached for write actions, login/password/names/phones masked | ✅ |

## 8. Hand-in

| # | Feature | Status |
|---|---|---|
| 8.1 | `docker compose up` starts everything | 🟡 agent + website + fake portal + Tesseract; not run here (no Docker on this PC) |
| 8.2 | README: run, models + data terms, cost table, every threshold | ✅ |
| 8.3 | Test set, harness, latest results in repo | ✅ |
| 8.4 | 8-minute demo script rehearsed | 🟡 written ([demo-script.md](demo-script.md)); rehearsal pending |

## 9. Stretch (+10 %)

| # | Feature | Status |
|---|---|---|
| 9.1 | Whole month, every lane, parallel browser contexts within the rate limit | ❌ |
| 9.2 | Scheduled monthly run with a summary for the logistics manager | ❌ (summary page in 5.13) |

## Biggest open risk

The hidden test (30 %) runs on the real portal. Public tasks are being run there one by one; each new portal trap found (paging outside the grid, scan-only legacy invoices) is fixed and covered by a test.
