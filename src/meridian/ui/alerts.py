"""Make a waiting OTP or dispute approval impossible to miss.

The agent may never read the OTP, so a person has to type it — fast, because a code is valid for
5 minutes. When something is waiting, the operator screen beeps once per new request, shows a
desktop notification (if the operator allowed them), flashes the tab title and counts down the
OTP's validity in the yellow bar. Everything stops as soon as nothing is waiting.

Nothing here answers anything: it only gets a person's attention.
"""
from __future__ import annotations

import json
import time

OTP_VALID_S = 300  # the portal's OTP is valid for 5 minutes from when it is sent


def items(pending_human: list[dict], pending_disputes: list[dict]) -> list[dict]:
    """What is waiting, as plain data for the page script."""
    out = [{"id": r["id"], "kind": r["kind"], "created": r["created"]} for r in pending_human]
    out += [{"id": d["id"], "kind": "approval", "created": d["created"]} for d in pending_disputes]
    return out


def otp_seconds_left(pending_human: list[dict], now: float | None = None) -> int | None:
    """Seconds left on the newest waiting OTP, or None when no OTP is waiting."""
    otps = [r["created"] for r in pending_human if r["kind"] == "otp"]
    if not otps:
        return None
    return max(0, int(OTP_VALID_S - ((now or time.time()) - max(otps))))


def title_for(waiting: list[dict]) -> str:
    kinds = {w["kind"] for w in waiting}
    if "otp" in kinds:
        return "(!) OTP needed · Meridian"
    if "approval" in kinds:
        return "(!) Approval needed · Meridian"
    return "(!) Needs you · Meridian"


def script(waiting: list[dict], otp_deadline: float | None) -> str:
    """HTML for a zero-height component. It acts on the operator screen's own window (same origin)."""
    data = json.dumps({"items": waiting, "title": title_for(waiting) if waiting else "",
                       "deadline": otp_deadline})
    return f"""<script>
(function () {{
  const W = window.parent, D = W.document, S = {data};
  const A = W.__meridianAlert = W.__meridianAlert || {{ seen: {{}}, timer: null, tick: null, base: null }};
  // timers live on the operator window, so a later check can always stop them
  W.clearInterval(A.timer); W.clearInterval(A.tick);
  if (A.base === null || !D.title.startsWith("(!)")) A.base = D.title;

  if (!S.items.length) {{ D.title = A.base; A.active = false; return; }}
  A.active = true;

  // 1. flash the tab title until answered
  let on = false;
  A.timer = W.setInterval(() => {{ on = !on; D.title = on ? S.title : A.base; }}, 1000);

  // 2. every second (the bar may render after this script): OTP countdown + alerts link
  const show = () => {{
    const el = D.getElementById("otp-countdown");
    if (el && S.deadline) {{
      const s = Math.max(0, Math.round(S.deadline - Date.now() / 1000));
      el.textContent = s > 0 ? `code valid for ${{Math.floor(s / 60)}}:${{String(s % 60).padStart(2, "0")}}`
                             : "code may have expired: use the newest one";
    }}
    // 3. "turn on desktop alerts": the browser only asks for permission after a click
    const link = D.getElementById("alert-enable"), N = W.Notification;
    if (link) {{
      if (!N || N.permission !== "default") link.style.display = "none";
      else if (!link.onclick) link.onclick = (e) => {{ e.preventDefault(); N.requestPermission().then(show); }};
    }}
  }};
  show(); A.tick = W.setInterval(show, 1000);

  // 4. once per new request: beep + desktop notification
  const fresh = S.items.filter(i => !A.seen[i.id]);
  fresh.forEach(i => A.seen[i.id] = true);
  if (!fresh.length) return;
  A.beeps = (A.beeps || 0) + 1;
  try {{
    const ctx = A.ctx = A.ctx || new (W.AudioContext || W.webkitAudioContext)();
    [0, 0.25].forEach(t => {{
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = 880; g.gain.value = 0.15;
      o.connect(g); g.connect(ctx.destination);
      o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.15);
    }});
  }} catch (e) {{}}
  try {{
    if (W.Notification && W.Notification.permission === "granted") {{
      const otp = fresh.some(i => i.kind === "otp");
      const n = new W.Notification(otp ? "Meridian needs the OTP" : "Meridian needs your approval", {{
        body: otp ? "Type the newest code from your inbox. It is valid for 5 minutes."
                  : "A dispute is waiting for your approval.",
        tag: "meridian-" + fresh[0].id, requireInteraction: otp }});
      n.onclick = () => {{ W.focus(); n.close(); }};
    }}
  }} catch (e) {{}}
}})();
</script>"""
