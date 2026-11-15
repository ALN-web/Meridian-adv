"""Look of the operator screen: a bento-style command hub in the Meridian home page colours
(white, paper, ink, one yellow accent; Manrope + IBM Plex Mono).

The 3D is a studio-lit Three.js scene: a ribbed 40 ft container in Meridian yellow on a road
trailer, with soft shadows and a callout pinned to the container door. The same scene, framed
smaller, heads every other page."""
from __future__ import annotations

import html

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root { --white:#ffffff; --paper:#f5f5f3; --canvas:#efeeea; --line:#e6e6e2; --ink:#0e0e0e; --ink2:#44443f; --muted:#8a8a84;
  --yellow:#f5c400; --yellow-ink:#1a1500; --yellow-soft:#fff6cc; --pass:#2fbf71; --bad:#e5484d; --r:14px; --R:22px;
  --card-shadow: 0 1px 2px rgba(14,14,14,.04), 0 14px 34px -22px rgba(14,14,14,.28); }

.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp td, .stApp th,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, [data-testid="stMarkdownContainer"] { font-family: Manrope, system-ui, sans-serif; }
.stApp code, .mono, .num { font-family: "IBM Plex Mono", monospace !important; }
.stApp h3 { font-size: 1.1rem; font-weight: 650; letter-spacing: -.015em; }

/* canvas: warm studio grey, the frame the cards sit in */
.stApp { background: radial-gradient(1200px 600px at 30% -10%, #ffffff 0%, rgba(255,255,255,0) 60%), var(--canvas); }
.block-container { padding-top: 5.2rem; padding-bottom: 4rem; max-width: 1320px; }

/* top bar (st.navigation position=top) */
header[data-testid="stHeader"] { background: rgba(255,255,255,.86); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--line); height: 64px; }
header[data-testid="stHeader"] img { height: 22px !important; max-width: none; }
header[data-testid="stHeader"] a, header[data-testid="stHeader"] button, header[data-testid="stHeader"] span { font-weight: 600; }
[data-testid="stTopNavLink"], [data-testid="stTopNavSection"] { border-radius: 999px !important; }
[data-testid="stTopNavLink"]:hover { background: var(--paper) !important; }
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stTopNavLink"].active { background: var(--ink) !important; }
[data-testid="stTopNavLink"][aria-current="page"] *, [data-testid="stTopNavLink"].active * { color: var(--white) !important; }
[data-testid="stTopNavLink"][aria-current="page"] [data-testid="stIconMaterial"] { color: var(--yellow) !important; }
[data-testid="stSidebar"] { background: var(--white); border-right: 1px solid var(--line); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: var(--ink); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: var(--white) !important; }

/* cards */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stForm"], [data-testid="stExpander"] details {
  background: var(--white); border: 1px solid rgba(14,14,14,.06) !important; border-radius: var(--R); box-shadow: var(--card-shadow); }
[data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid var(--line); border-radius: var(--r); overflow: hidden; background: var(--white); }
iframe { border-radius: var(--R); }
.stIFrame, [data-testid="stIFrame"], [data-testid="stCustomComponentV1"] { border-radius: var(--R); box-shadow: var(--card-shadow); }

/* inputs */
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-baseweb="base-input"] {
  border-radius: var(--r) !important; border-color: var(--line) !important; background: var(--white) !important; }
[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="input"], [data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="textarea"],
[data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="select"] > div, [data-testid="stVerticalBlockBorderWrapper"] [data-baseweb="base-input"] {
  background: var(--paper) !important; border-color: var(--paper) !important; }
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within, [data-baseweb="select"] > div:focus-within {
  border-color: var(--ink) !important; box-shadow: none !important; }

/* buttons: home page pills */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, .stLinkButton a {
  border-radius: 999px; min-height: 40px; padding: 0 18px; font-weight: 600; font-size: 14px; background: var(--white);
  border: 1px solid var(--line); color: var(--ink); box-shadow: none; transition: transform .2s, border-color .2s; }
.stButton button:hover, .stDownloadButton button:hover, .stFormSubmitButton button:hover, .stLinkButton a:hover {
  transform: translateY(-1px); border-color: var(--ink); color: var(--ink); }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"],
.stButton button[data-testid="stBaseButton-primary"], .stFormSubmitButton button[data-testid="stBaseButton-primaryFormSubmit"] {
  background: var(--ink); color: var(--white); border-color: var(--ink); }
.stButton button[kind="primary"] *, .stFormSubmitButton button[kind="primary"] * { color: var(--white); }
.stButton button:disabled { opacity: .35; transform: none; }
[data-testid="stBaseButton-segmented_control"], [data-testid="stBaseButton-segmented_controlActive"] {
  border-radius: 999px !important; min-height: 34px; font-weight: 600; font-size: 13px; }
[data-testid="stBaseButton-segmented_controlActive"] { background: var(--ink) !important; border-color: var(--ink) !important; }
[data-testid="stBaseButton-segmented_controlActive"] * { color: var(--white) !important; }
[data-baseweb="tab-list"] { gap: 24px; border-bottom: 1px solid var(--line); }
[data-baseweb="tab"] { font-weight: 600; padding-left: 0; padding-right: 0; }
[data-baseweb="tab-highlight"] { background: var(--ink); height: 2px; }

/* waiting bar under the top nav */
.waitbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px; border-radius: 999px;
  background: var(--yellow); color: var(--yellow-ink); font-weight: 600; font-size: .9rem; margin-bottom: 14px; }
.waitbar a { color: var(--yellow-ink) !important; text-decoration: none; border: 1px solid var(--yellow-ink); border-radius: 999px; padding: 3px 12px; }

/* card heads used inside bento cards */
.chead { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.chead .t { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1rem; letter-spacing: -.01em; color: var(--ink); }
.chead .ic { width: 30px; height: 30px; border-radius: 9px; background: var(--paper); display: grid; place-items: center; }
.chead .ic svg { width: 16px; height: 16px; }
.chead .sub { font-size: .78rem; color: var(--muted); font-weight: 500; }
.tag { display: inline-flex; align-items: center; gap: 6px; height: 24px; padding: 0 10px; border-radius: 999px; font-size: .74rem;
  font-weight: 650; background: var(--yellow-soft); color: #6b5600; border: 1px solid rgba(245,196,0,.45); white-space: nowrap; }
.tag.k { background: var(--ink); color: var(--white); border-color: var(--ink); }

/* agent panel (the "copilot") */
.agent-top { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid var(--line); margin-bottom: 12px; }
.agent-id { display: flex; align-items: center; gap: 10px; }
.av { width: 34px; height: 34px; border-radius: 50%; background: var(--ink); display: grid; place-items: center; flex: none; }
.av i { display: inline-block; width: 4px; height: 13px; background: var(--yellow); transform: skewX(-20deg); margin: 0 1px; }
.av i + i { background: var(--white); }
.agent-id b { display: block; font-size: .95rem; color: var(--ink); }
.agent-id span { font-size: .75rem; color: var(--muted); }
.agent-id span::before { content: ""; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--pass); margin-right: 6px; vertical-align: 1px; }
.agent-id span.busy::before { background: var(--yellow); }
.daystamp { text-align: center; font-size: .72rem; color: var(--muted); margin: 6px 0 10px; }
.msg { max-width: 88%; padding: 10px 13px; border-radius: 14px; font-size: .88rem; line-height: 1.45; margin-bottom: 10px; color: var(--ink); }
.msg.me { margin-left: auto; background: var(--yellow-soft); border: 1px solid rgba(245,196,0,.4); border-bottom-right-radius: 4px; }
.msg.bot { background: var(--paper); border-bottom-left-radius: 4px; }
.msg.bot.bad { background: rgba(229,72,77,.08); color: #9f2a2e; }
.msg small { display: block; color: var(--muted); font-size: .72rem; margin-top: 3px; }
.cards2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 2px 0 10px; }
.mini { background: var(--white); border: 1px solid var(--line); border-radius: 12px; padding: 9px 11px; }
.mini .no { font-family: "IBM Plex Mono", monospace; font-size: .74rem; font-weight: 500; color: var(--ink); }
.mini .k { font-size: .7rem; color: var(--muted); }
.mini .v { display: flex; justify-content: space-between; align-items: baseline; margin-top: 6px; font-size: .78rem; font-weight: 700; }
.mini .bar { height: 3px; border-radius: 3px; background: var(--line); margin-top: 6px; overflow: hidden; }
.mini .bar i { display: block; height: 100%; background: var(--yellow); }
.mini.ok .bar i { background: var(--pass); } .mini.bad .v .r { color: #c23338; } .mini.ok .v .r { color: #1d8a51; }
.act-head { font-size: .75rem; color: var(--muted); margin: 8px 0 6px; }
.act { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 12px; border: 1px solid var(--line);
  border-radius: 12px; font-size: .86rem; font-weight: 600; margin-bottom: 6px; background: var(--white); color: var(--ink); }
.act.hot { border-color: var(--yellow); background: var(--yellow-soft); }
.act span { font-size: .74rem; color: var(--muted); font-weight: 500; }
.typing { display: inline-flex; gap: 4px; padding: 10px 13px; background: var(--paper); border-radius: 14px; margin-bottom: 10px; }
.typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: dot 1.2s infinite; }
.typing i:nth-child(2) { animation-delay: .2s; } .typing i:nth-child(3) { animation-delay: .4s; }
@keyframes dot { 0%, 80%, 100% { opacity: .25; } 40% { opacity: 1; } }

/* lane map + invoice board */
.lanes svg { width: 100%; height: auto; display: block; }
.stat4 { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.stat4 div { background: var(--paper); border-radius: 12px; padding: 8px 10px; }
.stat4 span { display: block; font-size: .7rem; color: var(--muted); }
.stat4 b { font-size: 1rem; font-weight: 700; letter-spacing: -.02em; color: var(--ink); }
.board { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 5px; margin: 4px 0 12px; }
.board i { aspect-ratio: 1.6; border-radius: 4px; background: var(--paper); border: 1px dashed #d9d9d4; display: block; }
.board i.ok { background: var(--ink); border: 0; } .board i.bad { background: var(--yellow); border: 0; }
.board i.cx { background: repeating-linear-gradient(45deg, #e6e6e2 0 3px, #f5f5f3 3px 6px); border: 0; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: .75rem; color: var(--ink2); }
.legend i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.alert { margin-top: 10px; padding: 9px 12px; border-radius: 12px; border: 1px solid rgba(245,196,0,.6); background: var(--yellow-soft); font-size: .82rem; }
.alert b { display: block; font-size: .85rem; color: var(--ink); }
.alert span { color: var(--ink2); }

/* status pills, KPIs and plan rows used on the inner pages */
.pill { display: inline-flex; align-items: center; height: 26px; padding: 0 11px; border-radius: 999px; font-size: .78rem;
  font-weight: 600; margin: 0 4px 4px 0; white-space: nowrap; }
.p-ok { background: rgba(47,191,113,.14); color: #1d8a51; } .p-bad { background: rgba(229,72,77,.12); color: #c23338; }
.p-wait { background: var(--yellow); color: var(--yellow-ink); } .p-grey { background: var(--paper); color: var(--ink2); }
.p-run { background: var(--ink); color: var(--white); }
.kpi { background: var(--white); border: 1px solid rgba(14,14,14,.06); border-radius: var(--r); padding: 14px 18px; height: 100%; box-shadow: var(--card-shadow); }
.lbl { font-size: .8rem; color: var(--muted); }
.big { font-size: 1.6rem; font-weight: 700; letter-spacing: -.03em; white-space: nowrap; line-height: 1.3; color: var(--ink); }
.label { display: inline-flex; align-items: center; gap: 8px; font-family: "IBM Plex Mono", monospace; font-size: 12px;
  letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.label::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--yellow); }
.sec-label { display: flex; margin: 1.6rem 0 .7rem; }
.plan-row { padding: 10px 0; font-size: .93rem; display: flex; gap: 12px; align-items: center; color: var(--ink2); border-top: 1px solid var(--line); }
.plan-row:first-child { border-top: 2px solid var(--ink); }
.plan-row b { font-family: "IBM Plex Mono", monospace; font-size: .75rem; font-weight: 500; color: var(--muted); width: 22px; flex: none; }
.plan-row.done { color: var(--muted); } .plan-row.done b { color: var(--pass); }
.plan-row.now { color: var(--ink); font-weight: 600; } .plan-row.now b { color: var(--ink); }
.plan-row.now::after { content: "Now"; margin-left: auto; font-size: .72rem; font-weight: 600; padding: 2px 10px;
  border-radius: 999px; background: var(--yellow); color: var(--yellow-ink); }
.muted { color: var(--muted); font-size: .88rem; }
[data-testid="stProgress"] > div > div > div > div { background: var(--ink); }
[data-testid="stProgress"] > div > div > div { background: var(--line); border-radius: 99px; }

@media (max-width: 640px) {
  .block-container { padding-left: 16px; padding-right: 16px; padding-top: 4.6rem; }
  .stat4 { grid-template-columns: 1fr 1fr; } .board { grid-template-columns: repeat(8, minmax(0, 1fr)); }
  .big { font-size: 1.25rem; }
}
</style>
"""

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="150" height="24" viewBox="0 0 150 24">
<g transform="skewX(-20) translate(8 0)"><rect x="2" y="3" width="6" height="18" fill="#f5c400"/><rect x="11" y="3" width="6" height="18" fill="#0e0e0e"/></g>
<text x="30" y="18" font-family="Manrope, Segoe UI, Arial, sans-serif" font-size="15" font-weight="800" letter-spacing="0.6" fill="#0e0e0e">MERIDIAN</text>
</svg>"""

ICON = {  # 24px stroke icons (inline SVG, currentColor)
    "box": '<path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 7v10l9 4 9-4V7"/><path d="M12 11v10"/>',
    "rupee": '<path d="M7 4h10M7 9h10M7 4c6 0 6 10 0 10l8 6"/>',
    "gavel": '<path d="M14 4l6 6M11 7l6 6M12.5 5.5l-4 4M17.5 10.5l-4 4M4 20l7-7"/>',
    "bell": '<path d="M6 16V11a6 6 0 1112 0v5l2 2H4l2-2z"/><path d="M10 20a2 2 0 004 0"/>',
    "route": '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h7a3 3 0 000-6H9a3 3 0 010-6h7"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "cube": '<path d="M12 2l9 5v10l-9 5-9-5V7z"/><path d="M12 22V12M21 7l-9 5-9-5"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 3-6.3"/><path d="M4 4v5h5"/>',
}


def icon(name: str, size: int = 16, color: str = "currentColor") -> str:
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' stroke='{color}' stroke-width='1.8' "
            f"stroke-linecap='round' stroke-linejoin='round'>{ICON[name]}</svg>")


# ---------------------------------------------------------------- 3D scene

_SCENE = r"""
<script type="importmap">{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
const CFG = __CFG__;
const canvas = document.getElementById("c"), card = document.getElementById("card");
let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); }
catch (e) { card.classList.add("nogl"); throw e; }
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
const camera = new THREE.PerspectiveCamera(CFG.fov, 1, 0.1, 100);

const key = new THREE.DirectionalLight(0xffffff, 2.4); key.position.set(5, 9, 6); key.castShadow = true;
key.shadow.mapSize.set(2048, 2048); key.shadow.radius = 6; key.shadow.bias = -0.0004;
Object.assign(key.shadow.camera, { left: -6, right: 6, top: 6, bottom: -6, near: 1, far: 30 }); scene.add(key);
scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d6cf, 0.6));

const M = (c, r = .55, m = .2) => new THREE.MeshStandardMaterial({ color: c, roughness: r, metalness: m });
const shade = (m, k) => { const c = m.color.clone().multiplyScalar(k); return M(c, m.roughness, m.metalness); };
function labelTex(lines, fg, bg) {
  const cv = document.createElement("canvas"); cv.width = 1024; cv.height = 256; const g = cv.getContext("2d");
  g.fillStyle = bg; g.fillRect(0, 0, 1024, 256); g.fillStyle = fg;
  g.font = "600 64px 'IBM Plex Mono', monospace"; g.fillText(lines[0], 36, 92);
  g.font = "500 40px 'IBM Plex Mono', monospace"; g.globalAlpha = .75; g.fillText(lines[1], 36, 160); g.globalAlpha = 1;
  if (lines[2]) { g.save(); g.translate(820, 60); g.transform(1, 0, -0.36, 1, 0, 0);
    g.fillStyle = "#0e0e0e"; g.fillRect(0, 0, 34, 120); g.fillRect(48, 0, 34, 120); g.restore(); }
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t;
}
function container(body, L, lines) {
  const g = new THREE.Group(), H = 1.32, W = 1.22, rail = shade(body, .62), dark = M(0x1c1c1a, .6, .4);
  const box = new THREE.Mesh(new RoundedBoxGeometry(L, H, W, 2, .025), body); box.castShadow = box.receiveShadow = true; g.add(box);
  const ribG = new THREE.BoxGeometry(.055, H * .84, .035), n = Math.floor((L - .5) / .135);
  const ribs = new THREE.InstancedMesh(ribG, body, n * 2), o = new THREE.Object3D();
  for (let i = 0; i < n; i++) for (const s of [-1, 1]) {
    o.position.set(-L / 2 + .3 + i * .135, 0, s * (W / 2 + .012)); o.updateMatrix(); ribs.setMatrixAt(i * 2 + (s > 0 ? 1 : 0), o.matrix); }
  ribs.castShadow = true; g.add(ribs);
  const roofR = new THREE.InstancedMesh(new THREE.BoxGeometry(.05, .02, W * .9), body, n);
  for (let i = 0; i < n; i++) { o.position.set(-L / 2 + .3 + i * .135, H / 2 + .006, 0); o.updateMatrix(); roofR.setMatrixAt(i, o.matrix); }
  g.add(roofR);
  for (const y of [-1, 1]) for (const s of [-1, 1]) {
    const r = new THREE.Mesh(new THREE.BoxGeometry(L, .08, .06), rail); r.position.set(0, y * (H / 2 - .04), s * (W / 2 + .02)); r.castShadow = true; g.add(r); }
  for (const x of [-1, 1]) for (const y of [-1, 1]) for (const z of [-1, 1]) {
    const c = new THREE.Mesh(new THREE.BoxGeometry(.16, .13, .16), dark); c.position.set(x * (L / 2 - .06), y * (H / 2 - .05), z * (W / 2 - .04)); g.add(c); }
  // door end: two leaves, four lock bars with handles
  const door = new THREE.Mesh(new THREE.BoxGeometry(.03, H * .88, W * .94), shade(body, .9)); door.position.x = L / 2 + .01; g.add(door);
  const seam = new THREE.Mesh(new THREE.BoxGeometry(.035, H * .86, .012), rail); seam.position.x = L / 2 + .02; g.add(seam);
  for (const z of [-.44, -.2, .2, .44]) {
    const bar = new THREE.Mesh(new THREE.CylinderGeometry(.017, .017, H * .92, 10), M(0xb9b9b3, .35, .85));
    bar.position.set(L / 2 + .05, 0, z); bar.castShadow = true; g.add(bar);
    const h = new THREE.Mesh(new THREE.BoxGeometry(.025, .03, .12), M(0x2a2a27, .4, .6)); h.position.set(L / 2 + .07, -.1, z + (z > 0 ? -.06 : .06)); g.add(h); }
  // printed marking on the long side
  const plate = new THREE.Mesh(new THREE.PlaneGeometry(1.7, .42), new THREE.MeshStandardMaterial({ map: labelTex(lines, "#1a1500", "rgba(0,0,0,0)"), transparent: true, roughness: .8 }));
  plate.position.set(L / 2 - 1.35, .28, W / 2 + .032); g.add(plate);
  g.userData = { H, W, L };
  return g;
}
function trailer(L) {
  const g = new THREE.Group(), steel = M(0x1d1d1b, .55, .55), tyre = M(0x141413, .9, 0), rim = M(0x9a9a94, .3, .85);
  const y0 = .82;
  for (const s of [-1, 1]) { const b = new THREE.Mesh(new THREE.BoxGeometry(L + .2, .2, .12), steel); b.position.set(0, y0, s * .36); b.castShadow = true; g.add(b); }
  for (let i = 0; i < 9; i++) { const c = new THREE.Mesh(new THREE.BoxGeometry(.08, .12, .86), steel); c.position.set(-L / 2 + .2 + i * (L - .4) / 8, y0 + .02, 0); c.castShadow = true; g.add(c); }
  const deck = new THREE.Mesh(new THREE.BoxGeometry(L + .2, .05, 1.26), steel); deck.position.y = y0 + .12; deck.castShadow = deck.receiveShadow = true; g.add(deck);
  const neck = new THREE.Mesh(new THREE.BoxGeometry(1.3, .26, 1.0), steel); neck.position.set(L / 2 - .5, y0 + .02, 0); g.add(neck);
  for (const s of [-1, 1]) {   // landing legs
    const leg = new THREE.Mesh(new THREE.BoxGeometry(.08, y0 - .05, .08), steel); leg.position.set(L / 2 - 1.6, (y0 - .05) / 2, s * .4); leg.castShadow = true; g.add(leg);
    const pad = new THREE.Mesh(new THREE.BoxGeometry(.22, .03, .2), steel); pad.position.set(L / 2 - 1.6, .015, s * .4); g.add(pad); }
  const R = .36, tg = new THREE.CylinderGeometry(R, R, .2, 36), rg = new THREE.CylinderGeometry(R * .55, R * .55, .21, 24), hub = new THREE.CylinderGeometry(.08, .08, .22, 12);
  for (const x of [-L / 2 + .55, -L / 2 + 1.35, -L / 2 + 2.15]) for (const s of [-1, 1]) for (const d of [0, 1]) {
    const z = s * (.42 + d * .22);
    const t = new THREE.Mesh(tg, tyre); t.rotation.x = Math.PI / 2; t.position.set(x, R, z); t.castShadow = true; g.add(t);
    if (d === 1) { const r = new THREE.Mesh(rg, rim); r.rotation.x = Math.PI / 2; r.position.set(x, R, z + s * .005); g.add(r);
      const h = new THREE.Mesh(hub, steel); h.rotation.x = Math.PI / 2; h.position.set(x, R, z + s * .01); g.add(h); } }
  for (const s of [-1, 1]) { const f = new THREE.Mesh(new THREE.BoxGeometry(2.1, .05, .5), steel); f.position.set(-L / 2 + 1.35, R * 2 + .06, s * .53); g.add(f); }
  const bump = new THREE.Mesh(new THREE.BoxGeometry(.08, .12, 1.3), steel); bump.position.set(-L / 2 - .1, .5, 0); g.add(bump);
  for (const s of [-1, 1]) { const l = new THREE.Mesh(new THREE.BoxGeometry(.04, .07, .16), new THREE.MeshStandardMaterial({ color: 0xe5484d, emissive: 0x7a1010 }));
    l.position.set(-L / 2 - .14, .5, s * .5); g.add(l); }
  g.userData = { top: y0 + .145 };
  return g;
}

const rig = new THREE.Group(); scene.add(rig);
const L = 6.0, tr = trailer(L); rig.add(tr);
const yellow = M(0xf2c200, .5, .25), boxY = container(yellow, L, ["MRDU 204871 2", "45G1  ·  40' HIGH CUBE", true]);
boxY.position.y = tr.userData.top + boxY.userData.H / 2; rig.add(boxY);
if (CFG.stack) {
  const grey = M(0xdcdbd5, .6, .2), boxG = container(grey, L, ["TRIU 559871 4", "22G1  ·  TRANSINDUS", false]);
  boxG.position.y = boxY.position.y + boxY.userData.H + .02; rig.add(boxG);
}
rig.position.x = .2;
const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({ opacity: .22 }));
floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);

const target = new THREE.Vector3(...CFG.target);
camera.position.set(...CFG.cam);
const controls = new OrbitControls(camera, canvas);
controls.target.copy(target); controls.enableDamping = true; controls.dampingFactor = .06;
controls.enableZoom = false; controls.enablePan = false; controls.minPolarAngle = .95; controls.maxPolarAngle = 1.42;
controls.autoRotate = !matchMedia("(prefers-reduced-motion: reduce)").matches; controls.autoRotateSpeed = CFG.spin;
controls.enabled = CFG.drag; controls.update();
const home = camera.position.clone();

// callout pinned to the container's door corner
const pin = document.getElementById("pin"), tag = document.getElementById("tag");
const anchor = new THREE.Vector3(L / 2 + .2, boxY.position.y - .1, boxY.userData.W / 2);
const v = new THREE.Vector3(), toCam = new THREE.Vector3(), normal = new THREE.Vector3(.7, 0, .7).normalize();
function placePin(w, h) {
  if (!pin) return;
  v.copy(anchor).project(camera); const x = (v.x + 1) / 2 * w, y = (1 - v.y) / 2 * h;
  toCam.copy(camera.position).sub(anchor).normalize();
  const show = toCam.dot(normal) > .05 && x > 40 && x < w - 40 && y > 70 && y < h - 110;
  pin.style.opacity = tag.style.opacity = show ? 1 : 0;
  const left = x > w - 230;  // near the right edge: put the label on the pin's left
  pin.style.transform = `translate(${x - 18}px, ${y - 18}px)`;
  tag.style.transform = `translate(${left ? x - 26 - tag.offsetWidth : x + 26}px, ${y - 30}px)`;
}
function size() {
  const w = canvas.clientWidth, h = canvas.clientHeight; if (!w || !h) return;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  rig.scale.setScalar(w < 700 ? .62 : 1);  // phones: smaller, sitting under the title
  camera.setViewOffset(w, h, (w < 700 ? 0 : CFG.shift) * w, 0, w, h); camera.updateProjectionMatrix();
}
addEventListener("resize", size); size();
const view3d = document.getElementById("view3d"), resetBtn = document.getElementById("reset");
if (view3d) view3d.onclick = () => { controls.autoRotate = !controls.autoRotate; view3d.classList.toggle("on", controls.autoRotate); };
if (resetBtn) resetBtn.onclick = () => { camera.position.copy(home); controls.target.copy(target); controls.update(); };
let visible = true; new IntersectionObserver(es => { visible = es[0].isIntersecting; }).observe(card);
renderer.setAnimationLoop(() => {
  if (!visible || document.hidden) return;
  controls.update(); renderer.render(scene, camera); placePin(canvas.clientWidth, canvas.clientHeight);
});
</script>"""

_BASE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;background:transparent;overflow:hidden;font-family:Manrope,system-ui,sans-serif;color:#0e0e0e}
.card{position:relative;height:100%;border-radius:22px;overflow:hidden;
  background:radial-gradient(90% 120% at 62% 30%,#ffffff 0%,#f4f3ef 45%,#e7e6e0 100%)}
canvas{position:absolute;inset:0;width:100%;height:100%;cursor:grab}
canvas:active{cursor:grabbing}
.nogl canvas{display:none}
.chip{display:inline-flex;align-items:center;gap:8px;height:30px;padding:0 12px;border-radius:999px;background:rgba(255,255,255,.78);
  border:1px solid rgba(14,14,14,.06);font-size:12px;font-weight:600;color:#44443f;backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
.chip i{width:7px;height:7px;border-radius:50%;background:#2fbf71;box-shadow:0 0 0 3px rgba(47,191,113,.18)}
.chip i.busy{background:#f5c400;box-shadow:0 0 0 3px rgba(245,196,0,.25)}
.label{display:inline-flex;align-items:center;gap:8px;font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8a8a84}
.label::before{content:"";width:6px;height:6px;border-radius:50%;background:#f5c400}
"""

_HUB = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>__BASE__
.ui{position:absolute;inset:0;pointer-events:none;padding:22px 24px}
.ui a,.ui button,.ui .pe{pointer-events:auto}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.btns{display:flex;gap:8px}
.btn{height:34px;padding:0 12px;border-radius:999px;border:1px solid rgba(14,14,14,.08);background:rgba(255,255,255,.85);
  display:inline-flex;align-items:center;gap:7px;font:600 12px Manrope,sans-serif;color:#0e0e0e;cursor:pointer;backdrop-filter:blur(8px)}
.btn.on{background:#0e0e0e;color:#fff;border-color:#0e0e0e}.btn.icon{width:34px;padding:0;justify-content:center}
.title{margin-top:22px;display:flex;align-items:center;gap:14px}
.mark{display:inline-flex;gap:5px;transform:skewX(-20deg)}.mark i{width:12px;height:46px;background:#f5c400}.mark i:last-child{background:#0e0e0e}
h1{font-weight:700;font-size:30px;line-height:1.02;letter-spacing:-.035em}
.lead{margin-top:10px;font-size:13px;color:#44443f;font-weight:500}
.lead b{font-weight:600;color:#0e0e0e}
.chips{position:absolute;left:16px;right:16px;bottom:16px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
.k{display:flex;gap:10px;align-items:center;padding:12px 14px;border-radius:16px;background:rgba(255,255,255,.72);
  border:1px solid rgba(255,255,255,.9);box-shadow:0 10px 24px -16px rgba(14,14,14,.35);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.k.hot{background:rgba(245,196,0,.92);border-color:#f5c400}
.k .ic{width:32px;height:32px;border-radius:10px;background:rgba(14,14,14,.05);display:grid;place-items:center;flex:none}
.k.hot .ic{background:rgba(26,21,0,.12)}
.k span{display:block;font-size:11px;color:#8a8a84;font-weight:500}.k.hot span{color:#5f4d00}
.k b{font-size:20px;font-weight:700;letter-spacing:-.03em;white-space:nowrap}.k small{font-size:11px;color:#8a8a84;font-weight:500;margin-left:5px}
#pin{position:absolute;left:0;top:0;width:36px;height:36px;border-radius:50%;background:#0e0e0e;color:#fff;display:grid;place-items:center;
  font:600 18px Manrope;box-shadow:0 0 0 6px rgba(255,255,255,.6);transition:opacity .3s;pointer-events:none}
#tag{position:absolute;left:0;top:0;padding:9px 12px;border-radius:12px;background:rgba(255,255,255,.88);border:1px solid rgba(14,14,14,.06);
  box-shadow:0 12px 28px -16px rgba(14,14,14,.4);backdrop-filter:blur(10px);transition:opacity .3s;pointer-events:none;white-space:nowrap}
#tag span{display:block;font-size:10px;color:#8a8a84}#tag b{font:600 14px "IBM Plex Mono",monospace;letter-spacing:.02em}
#tag small{display:block;font-size:11px;color:#44443f;margin-top:2px}
@media (max-width:700px){.chips{grid-template-columns:1fr 1fr;gap:8px}.k{padding:9px 10px}.k b{font-size:16px}
  h1{font-size:24px}.mark i{height:36px;width:9px}#tag,#pin{display:none}.btn.txt{display:none}}
</style></head><body>
<div class="card" id="card"><canvas id="c" aria-label="3D view of a Meridian container on a road trailer. Drag to turn it."></canvas>
<div id="pin">+</div><div id="tag"><span>Container ID</span><b>MRDU 204871-2</b><small>40 ft High Cube · Pune hub</small></div>
<div class="ui">
  <div class="top">
    <span class="chip pe"><i class="__BUSY__"></i>__STATUS__</span>
    <div class="btns"><button class="btn txt on" id="view3d">__CUBE__ 3D view</button><button class="btn icon" id="reset" aria-label="Reset view">__RESET__</button></div>
  </div>
  <div class="title"><span class="mark"><i></i><i></i></span><h1>Freight Audit<br>Command Hub</h1></div>
  <p class="lead">TransIndus Roadways · <b>Pune → 5 lanes</b> · 8 rules per line</p>
</div>
<div class="chips">__CHIPS__</div>
</div>__SCENE__</body></html>"""

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>__BASE__
.ui{position:absolute;inset:0;pointer-events:none;padding:22px 28px;display:flex;flex-direction:column;justify-content:center;gap:8px;
  background:linear-gradient(90deg,rgba(244,243,239,.96) 0%,rgba(244,243,239,.75) 38%,rgba(244,243,239,0) 62%)}
h1{font-weight:700;font-size:34px;line-height:1.05;letter-spacing:-.035em}
p{font-size:14px;color:#44443f;max-width:460px;line-height:1.45}
@media (max-width:700px){.ui{background:rgba(244,243,239,.82);padding:18px}h1{font-size:26px}p{font-size:13px}}
</style></head><body>
<div class="card" id="card"><canvas id="c" aria-hidden="true"></canvas>
<div class="ui"><span class="label">__LABEL__</span><h1>__TITLE__</h1>__SUB__</div></div>__SCENE__</body></html>"""

HUB_HEIGHT = 450
PAGE_HEIGHT = 178


def _scene(cfg: str) -> str:
    return _SCENE.replace("__CFG__", cfg)


def hub_html(chips: list[tuple[str, str, str, str, bool]], status: str, busy: bool) -> str:
    """chips: [(icon, label, value, small, highlight)]"""
    e = html.escape
    chip_html = "".join(
        f"<div class='k{' hot' if hot else ''}'><div class='ic'>{icon(ic, 16)}</div><div><span>{e(lbl)}</span>"
        f"<b>{e(val)}</b>{f'<small>{e(sm)}</small>' if sm else ''}</div></div>"
        for ic, lbl, val, sm, hot in chips)
    cfg = '{"fov":30,"cam":[10.6,4.6,11.6],"target":[0.2,1.75,0],"shift":-0.17,"spin":0.55,"drag":true,"stack":true}'
    return (_HUB.replace("__BASE__", _BASE_CSS).replace("__CHIPS__", chip_html).replace("__STATUS__", e(status))
            .replace("__BUSY__", "busy" if busy else "").replace("__CUBE__", icon("cube", 14))
            .replace("__RESET__", icon("reset", 14)).replace("__SCENE__", _scene(cfg)))


def page_html(label: str, title: str, sub: str | None) -> str:
    e = html.escape
    cfg = '{"fov":24,"cam":[6.4,2.6,6.8],"target":[0.2,1.25,0],"shift":-0.24,"spin":0.4,"drag":false,"stack":false}'
    return (_PAGE.replace("__BASE__", _BASE_CSS).replace("__LABEL__", e(label)).replace("__TITLE__", e(title))
            .replace("__SUB__", f"<p>{e(sub)}</p>" if sub else "").replace("__SCENE__", _scene(cfg)))
