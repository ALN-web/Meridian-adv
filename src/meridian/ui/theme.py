"""Look of the operator screen: the website's design language (ink, paper, one yellow accent,
Manrope + IBM Plex Mono) as a SaaS console, and a 3D page header in the same style as the
website's hero (a container stack with a box being lowered onto it, Three.js)."""
from __future__ import annotations

import html

INK, PAPER, LINE, YELLOW = "#0e0e0e", "#f4f4f1", "#e3e3de", "#f5c400"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root { --ink:#0e0e0e; --ink2:#44443f; --muted:#8a8a84; --paper:#f4f4f1; --line:#e3e3de; --card:#ffffff;
  --yellow:#f5c400; --yellow-ink:#1a1500; --side:#0e0e0e; --side2:#171716; --side-line:#262624; --side-text:#b9b9b3;
  --lift: 0 1px 0 rgba(14,14,14,.04), 0 1px 2px rgba(14,14,14,.06), 0 8px 24px -12px rgba(14,14,14,.18);
  --lift-hi: 0 1px 0 rgba(14,14,14,.04), 0 2px 4px rgba(14,14,14,.06), 0 22px 40px -18px rgba(14,14,14,.32); }

/* type */
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp td, .stApp th,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, [data-testid="stMarkdownContainer"] { font-family: Manrope, system-ui, sans-serif; }
.stApp code, .mono { font-family: "IBM Plex Mono", monospace !important; }
.stApp h1 { font-size: 2.1rem; font-weight: 600; letter-spacing: -.03em; }
.stApp h2, .stApp h3 { font-weight: 650; letter-spacing: -.02em; }
.stApp h3 { font-size: 1.08rem; padding-top: .9rem; }

/* canvas: paper with a faint dot grid, like a drafting table */
.stApp { background-color: var(--paper);
  background-image: radial-gradient(rgba(14,14,14,.07) 1px, transparent 1px); background-size: 22px 22px; }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1240px; }

/* sidebar: ink panel */
[data-testid="stSidebar"] { background: var(--side); border-right: 1px solid var(--side-line); }
[data-testid="stSidebar"] * { color: var(--side-text); }
[data-testid="stSidebarHeader"] { padding: 1.4rem 1.2rem .6rem; }
[data-testid="stSidebarHeader"] img { height: 26px !important; max-width: none; }
[data-testid="stNavSectionHeader"], [data-testid="stNavSectionHeader"] * { font-family: "IBM Plex Mono", monospace !important;
  font-size: .68rem !important; letter-spacing: .12em; text-transform: uppercase; color: #6d6d68 !important; font-weight: 500 !important; }
[data-testid="stSidebarNavLink"] { border-radius: 10px; padding: .42rem .7rem; margin: 1px 0; transition: background .15s; position: relative; }
[data-testid="stSidebarNavLink"]:hover { background: var(--side2); }
[data-testid="stSidebarNavLink"] span { font-weight: 500; font-size: .92rem; }
[data-testid="stSidebarNavLink"][aria-current="page"], [data-testid="stSidebarNavLink"].active,
[data-testid="stSidebarNavLink"][aria-selected="true"] { background: #1d1d1b; box-shadow: inset 0 0 0 1px #2c2c29; }
[data-testid="stSidebarNavLink"][aria-current="page"]::before { content: ""; position: absolute; left: -12px; top: 9px; bottom: 9px;
  width: 3px; border-radius: 3px; background: var(--yellow); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: #ffffff !important; font-weight: 600; }
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] { color: var(--yellow) !important; }
[data-testid="stSidebar"] [data-testid="stIconMaterial"] { color: #7a7a74; }
[data-testid="stSidebarNavSeparator"] { border-color: var(--side-line); }
[data-testid="stSidebar"] [data-testid="stAlert"] { background: rgba(245,196,0,.12); border: 1px solid rgba(245,196,0,.35); border-radius: 12px; }
[data-testid="stSidebar"] [data-testid="stAlert"] * { color: #f3dc7a !important; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a { background: var(--yellow); border-radius: 999px; padding: .35rem .9rem; }
[data-testid="stSidebar"] [data-testid="stPageLink"] a * { color: var(--yellow-ink) !important; font-weight: 700; }
.side-foot { margin-top: 1.2rem; padding: 12px 14px; border: 1px solid var(--side-line); border-radius: 12px; background: var(--side2); }
.side-foot b { display: block; color: #fff !important; font-size: .85rem; font-weight: 600; }
.side-foot span { font-family: "IBM Plex Mono", monospace; font-size: .7rem; color: #7a7a74 !important; }
.side-foot i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #2fbf71; margin-right: 6px;
  box-shadow: 0 0 0 3px rgba(47,191,113,.18); }

/* cards: white, layered shadow, a little depth on hover */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stForm"], div[data-testid="stVerticalBlock"].st-key-card {
  border-radius: 16px; }
div[data-testid="stLayoutWrapper"] > div[data-testid="stVerticalBlock"][class*="border"],
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stForm"], [data-testid="stExpander"] details {
  background: var(--card); border: 1px solid var(--line) !important; box-shadow: var(--lift); border-radius: 16px; }
[data-testid="stExpander"] details summary:hover { color: var(--ink); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border-radius: 12px; overflow: hidden; box-shadow: var(--lift);
  border: 1px solid var(--line); background: var(--card); }

/* inputs */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {
  border-radius: 12px !important; border-color: var(--line) !important; background: #fbfbf9 !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--ink) !important; box-shadow: 0 0 0 4px rgba(245,196,0,.28) !important; }

/* buttons */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a {
  border-radius: 999px; font-weight: 600; border: 1px solid var(--line); background: var(--card); box-shadow: var(--lift);
  transition: transform .15s ease, box-shadow .15s ease, background .15s; }
.stButton button:hover, .stDownloadButton button:hover, .stFormSubmitButton button:hover, .stLinkButton a:hover {
  transform: translateY(-1px); box-shadow: var(--lift-hi); border-color: #cfcfc9; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"], .stButton button[data-testid="stBaseButton-primary"],
.stFormSubmitButton button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: linear-gradient(180deg, #2a2a27 0%, #0e0e0e 100%); color: #fff; border: 1px solid #0e0e0e;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.14), 0 10px 22px -10px rgba(14,14,14,.6); }
.stButton button[kind="primary"] *, .stFormSubmitButton button[kind="primary"] * { color: #fff; }
[data-testid="stBaseButton-segmented_control"], [data-testid="stBaseButton-segmented_controlActive"] { border-radius: 10px !important; }
[data-testid="stBaseButton-segmented_controlActive"] { background: var(--ink) !important; color: #fff !important; border-color: var(--ink) !important; }
[data-testid="stBaseButton-segmented_controlActive"] * { color: #fff !important; }

/* tabs */
[data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); }
[data-baseweb="tab"] { font-weight: 600; }
[data-baseweb="tab-highlight"] { background: var(--ink); height: 2px; }

/* the 3D page header */
iframe[title="st.iframe"], .stIFrame, [data-testid="stIFrame"], [data-testid="stCustomComponentV1"] {
  border-radius: 20px; box-shadow: 0 30px 60px -30px rgba(14,14,14,.45), 0 1px 0 rgba(14,14,14,.05); }
.sub { color: var(--muted); margin: -.5rem 0 1.6rem; font-size: 1rem; }

/* small pieces used by every page */
.pill { display: inline-flex; align-items: center; gap: 6px; height: 24px; padding: 0 10px; border-radius: 999px; font-size: .76rem;
  font-weight: 650; margin: 0 4px 4px 0; white-space: nowrap; letter-spacing: .01em; }
.pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; opacity: .8; }
.p-ok { background: rgba(47,191,113,.13); color: #1d8a51; } .p-bad { background: rgba(229,72,77,.11); color: #c23338; }
.p-wait { background: rgba(245,196,0,.22); color: #6b5600; } .p-grey { background: #ebebe7; color: #44443f; }
.p-run { background: var(--ink); color: #fff; } .p-run::before { background: var(--yellow); animation: blink 1.2s infinite; }
@keyframes blink { 50% { opacity: .2; } }
.kpi { position: relative; background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px 18px 16px;
  height: 100%; box-shadow: var(--lift); transform: perspective(700px) translateZ(0);
  transition: transform .25s cubic-bezier(.2,.7,.2,1), box-shadow .25s; overflow: hidden; }
.kpi::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: linear-gradient(90deg, var(--yellow), rgba(245,196,0,0)); opacity: .9; }
.kpi:hover { transform: perspective(700px) rotateX(4deg) translateY(-3px); box-shadow: var(--lift-hi); }
.lbl { font-family: "IBM Plex Mono", monospace; font-size: .68rem; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.big { font-size: 1.5rem; font-weight: 700; letter-spacing: -.03em; white-space: nowrap; line-height: 1.35; color: var(--ink); }
.plan-row { padding: 6px 0; font-size: .92rem; display: flex; gap: 10px; align-items: center; color: var(--ink2); }
.plan-row b { width: 22px; height: 22px; border-radius: 7px; display: inline-grid; place-items: center; font-size: .7rem;
  background: #ebebe7; color: var(--muted); flex: none; font-family: "IBM Plex Mono", monospace; }
.plan-row.done b { background: var(--ink); color: #fff; }
.plan-row.now b { background: var(--yellow); color: var(--yellow-ink); box-shadow: 0 0 0 4px rgba(245,196,0,.25); }
.plan-row.now { color: var(--ink); font-weight: 650; }
.muted { color: var(--muted); font-size: .88rem; }
[data-testid="stProgress"] > div > div > div > div { background: linear-gradient(90deg, #0e0e0e, #44443f); }
[data-testid="stProgress"] > div > div > div { background: #e6e6e1; border-radius: 99px; }

@media (max-width: 640px) {
  .block-container { padding-left: 16px; padding-right: 16px; padding-top: 3.8rem; }
  .big { font-size: 1.2rem; }
}
@media (prefers-reduced-motion: reduce) { .kpi, .stButton button { transition: none; } .kpi:hover { transform: none; } }
</style>
"""

# Logo for st.logo (sits above the navigation in the ink sidebar).
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="168" height="28" viewBox="0 0 168 28">
<g transform="skewX(-20) translate(10 0)"><rect x="2" y="5" width="6" height="18" fill="#f5c400"/><rect x="11" y="5" width="6" height="18" fill="#ffffff"/></g>
<text x="32" y="20" font-family="Manrope, Segoe UI, Arial, sans-serif" font-size="15" font-weight="800" letter-spacing="1.2" fill="#ffffff">MERIDIAN</text>
</svg>"""

# Shown in the top bar when the sidebar is closed (on paper, so ink letters).
LOGO_ICON_SVG = LOGO_SVG.replace('fill="#ffffff"', 'fill="#0e0e0e"')

HERO_HEIGHT = 236

_HERO = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:transparent;overflow:hidden}
.card{position:relative;height:100%;border-radius:20px;overflow:hidden;color:#fff;font-family:Manrope,system-ui,sans-serif;
  background:radial-gradient(120% 140% at 85% 10%,#2a2a26 0%,#141413 45%,#0b0b0a 100%)}
.card::after{content:"";position:absolute;inset:0;border-radius:20px;box-shadow:inset 0 0 0 1px rgba(255,255,255,.07);pointer-events:none}
canvas{position:absolute;top:0;right:0;width:60%;height:100%}
.ui{position:absolute;inset:0;padding:26px 30px 22px;display:flex;flex-direction:column;justify-content:space-between;pointer-events:none}
.eyebrow{display:inline-flex;align-items:center;gap:8px;font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:#9a9a94}
.eyebrow::before{content:"";width:6px;height:6px;border-radius:50%;background:#f5c400;box-shadow:0 0 0 4px rgba(245,196,0,.18)}
h1{font-weight:600;font-size:38px;line-height:1.05;letter-spacing:-.035em;margin-top:10px}
p{margin-top:8px;color:#b9b9b3;font-size:15px;max-width:440px;line-height:1.45}
.stats{display:flex;gap:10px;flex-wrap:wrap}
.stat{min-width:116px;padding:9px 14px 10px;border-radius:12px;background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.09);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.stat b{display:block;font-size:20px;font-weight:700;letter-spacing:-.03em;line-height:1.15}
.stat span{font-family:"IBM Plex Mono",monospace;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#8a8a84}
.stat.y{background:#f5c400;border-color:#f5c400;color:#1a1500}.stat.y span{color:#5f4d00}
.nogl canvas{display:none}
@media (max-width:760px){
  canvas{width:100%;opacity:.3}
  .ui{padding:18px 18px 16px}
  h1{font-size:28px} p{font-size:13.5px}
  .stats{flex-wrap:nowrap;gap:6px}
  .stat{min-width:0;flex:1 1 0;padding:7px 9px}.stat b{font-size:16px}
  .stat span{font-size:9px;letter-spacing:.04em;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
}
</style></head><body>
<div class="card" id="card">
  <canvas id="c" aria-hidden="true"></canvas>
  <div class="ui">
    <div><span class="eyebrow">__EYEBROW__</span><h1>__TITLE__</h1>__SUB__</div>
    <div class="stats">__STATS__</div>
  </div>
</div>
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
const canvas = document.getElementById("c"), card = document.getElementById("card");
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); }
catch (e) { card.classList.add("nogl"); throw e; }
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 100);

scene.add(new THREE.HemisphereLight(0xffffff, 0x1a1a18, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(6, 10, 4); sun.castShadow = true; sun.shadow.mapSize.set(1024, 1024);
Object.assign(sun.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8 }); scene.add(sun);
const rim = new THREE.DirectionalLight(0xf5c400, 0.9); rim.position.set(-6, 3, -5); scene.add(rim);

const world = new THREE.Group(); scene.add(world);
const ground = new THREE.Mesh(new THREE.CircleGeometry(9, 64), new THREE.ShadowMaterial({ opacity: .45 }));
ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; world.add(ground);
const grid = new THREE.GridHelper(16, 32, 0x3a3a36, 0x242422); grid.position.y = .001;
grid.material.transparent = true; grid.material.opacity = .55; world.add(grid);

const W = 2.4, H = 1.0, D = 1.0, geo = new RoundedBoxGeometry(W, H, D, 3, .06);
const ribs = new THREE.BoxGeometry(.035, H * .78, D + .012);
const mat = c => new THREE.MeshStandardMaterial({ color: c, roughness: .55, metalness: .15 });
const PAL = { ink: mat(0x1f1f1d), graphite: mat(0x34342f), bone: mat(0xe9e9e3), yellow: mat(0xf5c400) };
const edge = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: .08 });
function box(m) {
  const g = new THREE.Group();
  const b = new THREE.Mesh(geo, m); b.castShadow = b.receiveShadow = true; g.add(b);
  for (let i = -5; i <= 5; i++) { const r = new THREE.Mesh(ribs, m); r.position.x = i * .2; r.castShadow = true; g.add(r); }
  g.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), edge));
  return g;
}
// stack: 3 rows deep x 2 across, 1-3 high
const layout = [[0,0,3,"ink","graphite","bone"],[0,1,2,"graphite","ink"],[1,0,2,"bone","ink"],[1,1,1,"ink"],[2,0,1,"graphite"],[2,1,2,"ink","bone"]];
for (const [r, c, h, ...cols] of layout)
  for (let k = 0; k < h; k++) { const b = box(PAL[cols[k]]); b.position.set(c * (W + .12) - (W + .12) / 2, H / 2 + k * (H + .02), r * (D + .14) - (D + .14)); world.add(b); }

// the yellow box on the crane hook, lowered onto row 1 / col 1 and lifted again
const hook = new THREE.Group(); world.add(hook);
const load = box(PAL.yellow); hook.add(load);
const cableMat = new THREE.LineBasicMaterial({ color: 0x9a9a94 });
const cable = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3(0, 9, 0)]), cableMat); hook.add(cable);
const target = new THREE.Vector3((W + .12) / 2, H / 2 + 1 * (H + .02), 0);

// scan plane sweeping the stack
const scan = new THREE.Mesh(new THREE.PlaneGeometry(.06, 4.2), new THREE.MeshBasicMaterial({ color: 0xf5c400, transparent: true, opacity: .55, blending: THREE.AdditiveBlending, depthWrite: false }));
scan.rotation.y = Math.PI / 2; scan.position.y = 1.6; world.add(scan);
const glow = new THREE.Mesh(new THREE.PlaneGeometry(.9, 4.2), new THREE.MeshBasicMaterial({ color: 0xf5c400, transparent: true, opacity: .08, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
scan.add(glow);

let mx = 0, my = 0;
addEventListener("pointermove", e => { mx = e.clientX / innerWidth - .5; my = e.clientY / innerHeight - .5; });
function size() {
  const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
}
addEventListener("resize", size); size();
const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
let visible = true;
new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(card);
function frame(ms) {
  const t = still ? 2.2 : ms / 1000;
  const a = .78 + Math.sin(t * .18) * .22 + mx * .25;
  camera.position.set(Math.sin(a) * 12.5, 6.4 - my * 1.2, Math.cos(a) * 12.5);
  camera.lookAt(0, 1.2, 0);
  // 7 s cycle: lower (0-3), rest (3-4), lift (4-6.2), wait
  const c = (t % 7);
  const k = c < 3 ? ease(c / 3) : c < 4 ? 1 : c < 6.2 ? 1 - ease((c - 4) / 2.2) : 0;
  hook.position.set(target.x, target.y + (1 - k) * 2.6, target.z);
  hook.rotation.y = (1 - k) * Math.sin(t * 1.3) * .08;
  scan.position.z = Math.sin(t * .9) * 2.2;
  scan.material.opacity = .35 + .25 * Math.sin(t * 3);
  renderer.render(scene, camera);
}
if (still) { frame(0); }
else renderer.setAnimationLoop(ms => { if (visible && !document.hidden) frame(ms); });
</script></body></html>"""


def hero_html(title: str, sub: str | None, eyebrow: str, stats: list[tuple[str, str, bool]]) -> str:
    """The 3D page header. ``stats`` is [(value, label, highlight)]."""
    e = html.escape
    stat_html = "".join(f"<div class='stat{' y' if hi else ''}'><b>{e(v)}</b><span>{e(lbl)}</span></div>" for v, lbl, hi in stats)
    return (_HERO.replace("__EYEBROW__", e(eyebrow)).replace("__TITLE__", e(title))
            .replace("__SUB__", f"<p>{e(sub)}</p>" if sub else "").replace("__STATS__", stat_html))

