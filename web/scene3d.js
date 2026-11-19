import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

window.__meridian3d = true;  // site.js shows the still picture if this never runs

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const isPhone = () => innerWidth < 680 || innerWidth <= innerHeight;
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const range = (p, a, b) => clamp((p - a) / (b - a));
const smooth = t => t * t * (3 - 2 * t);
const lerp = (a, b, t) => a + (b - a) * t;

function makeRenderer(canvas, clear) {
  let r;
  try { r = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" }); }
  catch (e) { document.documentElement.classList.add("nogl"); return null; }
  r.setClearColor(clear, 1);
  r.outputColorSpace = THREE.SRGBColorSpace;
  r.toneMapping = THREE.ACESFilmicToneMapping;
  r.toneMappingExposure = 1.0;
  return r;
}
function canvasTex(w, h, draw) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const ctx = c.getContext("2d"); draw(ctx, w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8;
  return { tex: t, ctx };
}
// corrugated container side: vertical ribs over a base colour
function ribs(color, dark = 0.22, light = 0.12) {
  return canvasTex(1024, 256, (ctx, w, h) => {
    ctx.fillStyle = color; ctx.fillRect(0, 0, w, h);
    for (let x = 0; x < w; x += 22) {
      const g = ctx.createLinearGradient(x, 0, x + 22, 0);
      g.addColorStop(0, `rgba(255,255,255,${light})`); g.addColorStop(.45, `rgba(0,0,0,${dark})`); g.addColorStop(1, `rgba(255,255,255,${light * .6})`);
      ctx.fillStyle = g; ctx.fillRect(x, 0, 22, h);
    }
    ctx.fillStyle = `rgba(0,0,0,${dark * .9})`; ctx.fillRect(0, 0, w, 10); ctx.fillRect(0, h - 10, w, 10);
  }).tex;
}
const L = 6.06, H = 2.59, W = 2.44;  // 20-foot container (metres)
function container(color, opts = {}) {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ map: ribs(color, opts.dark ?? 0.22, opts.light ?? 0.12), roughness: 0.55, metalness: 0.25 });
  const box = new THREE.Mesh(new RoundedBoxGeometry(L, H, W, 2, 0.05), mat);
  box.castShadow = true; box.receiveShadow = true; g.add(box);
  const cast = new THREE.MeshStandardMaterial({ color: 0x1b1b1a, roughness: 0.6, metalness: 0.4 });
  for (const x of [-L / 2 + 0.08, L / 2 - 0.08]) for (const y of [-H / 2 + 0.08, H / 2 - 0.08]) for (const z of [-W / 2 + 0.08, W / 2 - 0.08]) {
    const c = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.16, 0.18), cast); c.position.set(x, y, z); g.add(c);
  }
  const bar = new THREE.MeshStandardMaterial({ color: 0x2a2a28, roughness: 0.4, metalness: 0.7 });
  for (const z of [-0.75, -0.25, 0.25, 0.75]) { const b = new THREE.Mesh(new THREE.BoxGeometry(0.05, H - 0.3, 0.05), bar); b.position.set(L / 2 + 0.02, 0, z); g.add(b); }
  return g;
}

/* ================================================================== HERO */
function initHero() {
  const canvas = document.getElementById("hero3d");
  const renderer = makeRenderer(canvas, 0xffffff);
  if (renderer) {
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 400);
    scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d8d2, 1.25));
    const sun = new THREE.DirectionalLight(0xffffff, 2.3); sun.position.set(10, 24, 16); sun.castShadow = true;
    sun.shadow.mapSize.setScalar(isPhone() ? 1024 : 2048); Object.assign(sun.shadow.camera, { left: -20, right: 20, top: 20, bottom: -20, near: 1, far: 80 });
    sun.shadow.bias = -0.0005; scene.add(sun);
    const fill = new THREE.DirectionalLight(0xfff3d6, 0.6); fill.position.set(-14, 6, 10); scene.add(fill);

    // the stack below (bleeds off the bottom of the hero)
    const YEL = "#f2c200", WHT = "#e7e7e3", BLK = "#1a1a19";
    const stack = new THREE.Group(); scene.add(stack);
    const DY = -1.9;   // whole yard sits lower so the copy stays clear
    const S = [
      [YEL, -6.6, -6.4 + DY, -1.6, 0.05], [YEL, 0.6, -6.4 + DY, -0.6, 0], [BLK, 7.0, -6.4 + DY, -1.4, -0.03],
      [WHT, -3.4, -3.81 + DY, -2.6, 0.02], [YEL, 4.6, -3.81 + DY, -3.0, 0], [WHT, -9.8, -3.81 + DY, -3.2, 0.04],
      [BLK, -1.0, -6.4 + DY, -4.4, 0], [YEL, 10.8, -3.81 + DY, -3.6, 0], [WHT, 6.8, -6.4 + DY, -5.8, 0],
    ];
    for (const [col, x, y, z, ry] of S) {
      const c = container(col, col === BLK ? { dark: 0.35, light: 0.08 } : {});
      c.position.set(x, y, z); c.rotation.y = ry; stack.add(c);
    }
    const landY = -6.4 + DY + H; // on top of the middle yellow container

    // the load: hook block + slings + branded container
    const load = new THREE.Group(); scene.add(load);
    const hero = container("#151514", { dark: 0.4, light: 0.07 });
    load.add(hero);
    const decal = canvasTex(1024, 300, (ctx, w, h) => {
      ctx.clearRect(0, 0, w, h);
      ctx.save(); ctx.translate(720, 150); ctx.transform(1, 0, -0.36, 1, 0, 0);
      ctx.fillStyle = "#f5c400"; ctx.fillRect(0, -70, 34, 140); ctx.fillStyle = "#ffffff"; ctx.fillRect(48, -70, 34, 140);
      ctx.restore();
      ctx.fillStyle = "#ffffff"; ctx.font = "800 122px Manrope, sans-serif"; ctx.textBaseline = "middle"; ctx.fillText("MERIDIAN", 0 + 40, 150);
    });
    const d1 = new THREE.Mesh(new THREE.PlaneGeometry(4.9, 1.43), new THREE.MeshStandardMaterial({ map: decal.tex, transparent: true, roughness: 0.6 }));
    d1.position.set(-0.2, 0.05, W / 2 + 0.012); hero.add(d1);
    const d2 = d1.clone(); d2.rotation.y = Math.PI; d2.position.z = -W / 2 - 0.012; hero.add(d2);
    const codeT = canvasTex(512, 96, (ctx) => { ctx.fillStyle = "rgba(255,255,255,.75)"; ctx.font = "500 40px 'IBM Plex Mono', monospace"; ctx.fillText("MRDU 204871 · 22G1", 8, 60); });
    const code = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 0.36), new THREE.MeshBasicMaterial({ map: codeT.tex, transparent: true }));
    code.position.set(-1.9, 1.0, W / 2 + 0.013); hero.add(code);

    const HOOK_Y = H / 2 + 3.2;
    const stripes = canvasTex(256, 256, (ctx, w, h) => {
      ctx.fillStyle = "#f5c400"; ctx.fillRect(0, 0, w, h); ctx.fillStyle = "#121212";
      for (let i = -h; i < w; i += 56) { ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i + 28, 0); ctx.lineTo(i + 28 + h, h); ctx.lineTo(i + h, h); ctx.closePath(); ctx.fill(); }
    }).tex;
    const block = new THREE.Mesh(new RoundedBoxGeometry(1.15, 1.5, 0.75, 3, 0.12), new THREE.MeshStandardMaterial({ map: stripes, roughness: 0.5, metalness: 0.2 }));
    block.position.y = HOOK_Y + 0.6; block.castShadow = true; load.add(block);
    const steel = new THREE.MeshStandardMaterial({ color: 0x5b5b57, roughness: 0.35, metalness: 0.85 });
    const sheave = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.82, 24), steel); sheave.rotation.x = Math.PI / 2; sheave.position.y = HOOK_Y + 1.45; load.add(sheave);
    const hook = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.11, 12, 32, Math.PI * 1.45), new THREE.MeshStandardMaterial({ color: 0x1c1c1b, roughness: 0.4, metalness: 0.7 }));
    hook.position.y = HOOK_Y - 0.45; hook.rotation.z = Math.PI * 0.95; hook.castShadow = true; load.add(hook);
    const cable = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 60, 8), steel); cable.position.y = HOOK_Y + 1.45 + 30; load.add(cable);
    const cable2 = cable.clone(); cable2.position.x = 0.28; load.add(cable2);
    const slingMat = new THREE.MeshStandardMaterial({ color: 0x3a3a37, roughness: 0.5, metalness: 0.6 });
    const top = new THREE.Vector3(0, HOOK_Y - 0.6, 0);
    for (const [x, z] of [[-L / 2 + 0.2, -W / 2 + 0.2], [-L / 2 + 0.2, W / 2 - 0.2], [L / 2 - 0.2, -W / 2 + 0.2], [L / 2 - 0.2, W / 2 - 0.2]]) {
      const end = new THREE.Vector3(x, H / 2 + 0.05, z);
      const len = top.distanceTo(end);
      const s = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, len, 6), slingMat);
      s.position.copy(top).add(end).multiplyScalar(0.5);
      s.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), top.clone().sub(end).normalize());
      load.add(s);
    }

    function resize() {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      renderer.setPixelRatio(Math.min(devicePixelRatio, isPhone() ? 1.5 : 2));
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.fov = isPhone() ? 40 : 28;
      camera.updateProjectionMatrix();
    }
    addEventListener("resize", resize); resize();

    const heroEl = document.querySelector(".hero");
    const loadPct = document.getElementById("loadPct");
    const fades = [...document.querySelectorAll(".hero-fade")];
    const pos = new THREE.Vector3(), tgt = new THREE.Vector3(), cp = new THREE.Vector3(), ct = new THREE.Vector3();
    let visible = true, hpS = 0;
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(heroEl);
    const clock = new THREE.Clock();
    const camAt = (hp) => {
      const phone = isPhone();
      const t = smooth(hp);
      pos.set(lerp(phone ? 2 : 4.5, phone ? 1 : 2.6, t), lerp(phone ? 2 : 2.6, -1.4, t), lerp(phone ? 40 : 31, phone ? 32 : 24, t));
      tgt.set(lerp(phone ? 0.6 : -2.2, phone ? 0.4 : -1.4, t), lerp(phone ? 4.2 : -0.9, phone ? -2.4 : -4.9, t), 0);
    };
    camAt(0); cp.copy(pos); ct.copy(tgt);
    function frame() {
      requestAnimationFrame(frame);
      if (!visible) return;
      const t = clock.getElapsedTime();
      const rect = heroEl.getBoundingClientRect();
      const hp = clamp(-rect.top / Math.max(1, rect.height - innerHeight));
      hpS += (hp - hpS) * (REDUCED ? 1 : 0.12);
      const lower = smooth(range(hpS, 0.12, 0.86));
      const yStart = isPhone() ? 0.2 : 0.8;
      load.position.set(lerp(1.6, 0.6, lower), lerp(yStart, landY, lower), -0.6);
      load.rotation.y = lerp(-0.62, 0.0, smooth(range(hpS, 0, 0.75))) + (REDUCED ? 0 : Math.sin(t * 0.35) * 0.04 * (1 - lower));
      const sway = REDUCED ? 0 : (1 - lower) * 0.035;
      load.rotation.z = Math.sin(t * 0.8) * sway; load.rotation.x = Math.sin(t * 0.55 + 1) * sway * 0.6;
      loadPct.textContent = Math.round(lower * 100) + "%";
      const fade = smooth(range(hpS, 0.42, 0.7));
      fades.forEach(el => { el.style.opacity = 1 - fade; el.style.transform = `translateY(${-fade * 40}px)`; el.style.pointerEvents = fade > 0.5 ? "none" : ""; });
      camAt(hpS);
      cp.lerp(pos, REDUCED ? 1 : 0.08); ct.lerp(tgt, REDUCED ? 1 : 0.08);
      camera.position.copy(cp); camera.lookAt(ct);
      renderer.render(scene, camera);
    }
    document.fonts && document.fonts.ready.then(() => {
      const c = decal.ctx; c.clearRect(0, 0, 1024, 300);
      c.save(); c.translate(720, 150); c.transform(1, 0, -0.36, 1, 0, 0);
      c.fillStyle = "#f5c400"; c.fillRect(0, -70, 34, 140); c.fillStyle = "#ffffff"; c.fillRect(48, -70, 34, 140); c.restore();
      c.fillStyle = "#ffffff"; c.font = "800 122px Manrope, sans-serif"; c.textBaseline = "middle"; c.fillText("MERIDIAN", 40, 150);
      decal.tex.needsUpdate = true;
    });
    requestAnimationFrame(frame);
  }
}

/* ================================================================== SHIP (top-down) */
function initShip() {
  const canvas = document.getElementById("ship3d");
  const renderer = makeRenderer(canvas, 0x111110);
  if (renderer) {
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 500);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x333330, 1.1));
    const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.position.set(-20, 60, 30); scene.add(sun);

    // sea: subtle ripple lines
    const seaT = canvasTex(512, 512, (ctx, w, h) => {
      ctx.fillStyle = "#121211"; ctx.fillRect(0, 0, w, h);
      ctx.strokeStyle = "rgba(255,255,255,.035)"; ctx.lineWidth = 2;
      for (let i = 0; i < 70; i++) { const y = Math.random() * h, x = Math.random() * w; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 30 + Math.random() * 60, y); ctx.stroke(); }
    }).tex;
    seaT.wrapS = seaT.wrapT = THREE.RepeatWrapping; seaT.repeat.set(6, 6);
    const sea = new THREE.Mesh(new THREE.PlaneGeometry(400, 400), new THREE.MeshBasicMaterial({ map: seaT }));
    sea.rotation.x = -Math.PI / 2; scene.add(sea);

    const ship = new THREE.Group(); scene.add(ship);
    const LEN = 70, BEAM = 12.5;
    const shape = new THREE.Shape();
    shape.moveTo(-BEAM / 2, -LEN / 2); shape.lineTo(BEAM / 2, -LEN / 2); shape.lineTo(BEAM / 2, LEN / 2 - 9);
    shape.quadraticCurveTo(BEAM / 2, LEN / 2 - 2, 0, LEN / 2 + 1.5); shape.quadraticCurveTo(-BEAM / 2, LEN / 2 - 2, -BEAM / 2, LEN / 2 - 9); shape.closePath();
    const hull = new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: 1.6, bevelEnabled: true, bevelSize: 0.25, bevelThickness: 0.25, bevelSegments: 2 }),
      new THREE.MeshStandardMaterial({ color: 0x2b2b29, roughness: 0.7, metalness: 0.3 }));
    hull.rotation.x = -Math.PI / 2; ship.add(hull);
    const deck = new THREE.Mesh(new THREE.ShapeGeometry(shape), new THREE.MeshStandardMaterial({ color: 0x3a3a37, roughness: 0.9 }));
    deck.rotation.x = -Math.PI / 2; deck.position.y = 1.86; deck.scale.set(0.94, 0.97, 1); ship.add(deck);
    // bridge at the stern
    const bridge = new THREE.Mesh(new THREE.BoxGeometry(BEAM * 0.8, 2.6, 4.2), new THREE.MeshStandardMaterial({ color: 0xe9e9e6, roughness: 0.6 }));
    bridge.position.set(0, 3.2, LEN / 2 - 66.5 + 2.5); ship.add(bridge);
    const funnel = new THREE.Mesh(new THREE.BoxGeometry(2.2, 2.2, 2.2), new THREE.MeshStandardMaterial({ color: 0xf5c400, roughness: 0.5 }));
    funnel.position.set(0, 5.2, LEN / 2 - 66.5 + 1.5); ship.add(funnel);

    // containers: bays along the length, rows across the beam
    const BAYS = 16, ROWS = 5, N = BAYS * ROWS;
    const boxGeo = new THREE.BoxGeometry(2.1, 1, 3.4);
    const boxMat = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.2 });
    const boxes = new THREE.InstancedMesh(boxGeo, boxMat, N);
    ship.add(boxes);
    const BASE = [new THREE.Color(0xf2c200), new THREE.Color(0xe7e7e3), new THREE.Color(0x1d1d1c), new THREE.Color(0x8a8a85)];
    const PASS = new THREE.Color(0x2fbf71), BAD = new THREE.Color(0xe5484d);
    const data = [];
    const m4 = new THREE.Object3D();
    for (let b = 0; b < BAYS; b++) for (let r = 0; r < ROWS; r++) {
      const i = b * ROWS + r;
      const h = 0.8 + ((b * 5 + r * 3) % 3) * 0.35;
      const z = LEN / 2 - 13 - b * 3.6;
      const x = (r - (ROWS - 1) / 2) * 2.25;
      m4.position.set(x, 1.9 + h / 2, z); m4.scale.set(1, h, 1); m4.updateMatrix(); boxes.setMatrixAt(i, m4.matrix);
      const base = BASE[(b * 7 + r * 3) % 4];
      const bad = ((b * 13 + r * 5) % 9) === 0;
      data.push({ z, base, bad, done: false });
      boxes.setColorAt(i, base);
    }
    boxes.instanceColor.needsUpdate = true;

    // scan line fixed in the world; the ship sails under it
    const scanMat = new THREE.MeshBasicMaterial({ color: 0xf5c400, transparent: true, opacity: 0.9 });
    const scan = new THREE.Mesh(new THREE.PlaneGeometry(BEAM + 10, 0.22), scanMat); scan.rotation.x = -Math.PI / 2; scan.position.y = 5.0; scene.add(scan);
    const glowT = canvasTex(64, 256, (ctx, w, h) => { const g = ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "rgba(245,196,0,0)"); g.addColorStop(.5, "rgba(245,196,0,.35)"); g.addColorStop(1, "rgba(245,196,0,0)"); ctx.fillStyle = g; ctx.fillRect(0, 0, w, h); }).tex;
    const glow = new THREE.Mesh(new THREE.PlaneGeometry(BEAM + 10, 5), new THREE.MeshBasicMaterial({ map: glowT, transparent: true, depthWrite: false }));
    glow.rotation.x = -Math.PI / 2; glow.position.y = 4.95; scene.add(glow);

    function resize() {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      renderer.setPixelRatio(Math.min(devicePixelRatio, isPhone() ? 1.5 : 2));
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.updateProjectionMatrix();
    }
    addEventListener("resize", resize); resize();

    const shipEl = document.querySelector(".ship");
    const cLines = document.getElementById("cLines"), cPass = document.getElementById("cPass"), cBad = document.getElementById("cBad");
    let visible = false, spS = 0;
    new IntersectionObserver(([e]) => { visible = e.isIntersecting; }).observe(shipEl);
    const clock = new THREE.Clock();
    const tmp = new THREE.Color();
    function frame() {
      requestAnimationFrame(frame);
      if (!visible) return;
      const t = clock.getElapsedTime();
      const rect = shipEl.getBoundingClientRect();
      const sp = clamp(-rect.top / Math.max(1, rect.height - innerHeight));
      spS += (sp - spS) * (REDUCED ? 1 : 0.12);
      // ship sails "up" the screen (towards -z) as you scroll
      ship.position.z = lerp(-52, 44, spS);
      ship.position.x = isPhone() ? 0 : 6;
      ship.rotation.z = REDUCED ? 0 : Math.sin(t * 0.6) * 0.004;
      scan.position.x = glow.position.x = ship.position.x;
      seaT.offset.y = REDUCED ? 0 : -t * 0.01;
      let lines = 0, pass = 0, bad = 0;
      data.forEach((d, i) => {
        const worldZ = d.z + ship.position.z;
        const passed = worldZ > 0;               // has crossed the scan line (z = 0)
        const k = clamp(worldZ / 3);             // quick blend after crossing
        tmp.copy(d.base).lerp(d.bad ? BAD : PASS, passed ? smooth(k) : 0);
        boxes.setColorAt(i, tmp);
        if (passed) { lines++; d.bad ? bad++ : pass++; }
      });
      boxes.instanceColor.needsUpdate = true;
      const scale = 1180 / N;   // each box stands for a batch of lines this month
      cLines.textContent = Math.round(lines * scale).toLocaleString("en-IN");
      cPass.textContent = Math.round(pass * scale).toLocaleString("en-IN");
      cBad.textContent = Math.round(bad * scale).toLocaleString("en-IN");
      camera.position.set(isPhone() ? 0 : 0, isPhone() ? 88 : 66, isPhone() ? 22 : 18);
      camera.lookAt(isPhone() ? 0 : 0, 0, 0);
      renderer.render(scene, camera);
    }
    requestAnimationFrame(frame);
  }
}

/* ================================================================== START
   The 3D scenes are decoration: let the headline and copy paint first, then build the hero
   when the browser is idle, and only build the ship scene when it is about to scroll into view. */
const whenIdle = (fn) => ("requestIdleCallback" in window ? requestIdleCallback(fn, { timeout: 1200 }) : setTimeout(fn, 200));
const afterFirstPaint = (fn) => requestAnimationFrame(() => requestAnimationFrame(() => whenIdle(fn)));
afterFirstPaint(initHero);
{
  const shipEl = document.querySelector(".ship");
  if (shipEl) {
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); whenIdle(initShip); } }, { rootMargin: "100% 0px" });
    io.observe(shipEl);
  }
}
