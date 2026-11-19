// Shared behaviour: operator links, phone menu, reveal on scroll, nav that adapts to dark sections.
(() => {
  // Where the operator screen lives.
  // 1. <meta name="meridian-operator-url" content="https://ops.example.com"> (set this for a public deploy)
  // 2. ?app=http://host:port, only honoured while the site itself runs on localhost (dev convenience)
  // 3. Fallback: same host as this page, port 8510 (docker compose layout)
  // Every candidate must be an absolute http(s) URL; anything else (javascript:, data:, //evil) is ignored.
  const LOCAL = ["localhost", "127.0.0.1", "[::1]"];
  const safeBase = (value) => {
    if (!value) return null;
    try {
      const u = new URL(value);
      if (u.protocol !== "http:" && u.protocol !== "https:") return null;
      return u.origin + u.pathname.replace(/\/$/, "");
    } catch { return null; }
  };
  const meta = document.querySelector('meta[name="meridian-operator-url"]');
  const fromMeta = safeBase(meta && meta.content.trim());
  const fromQuery = LOCAL.includes(location.hostname) ? safeBase(new URLSearchParams(location.search).get("app")) : null;
  const fallback = location.hostname ? `${location.protocol === "https:" ? "https:" : "http:"}//${location.hostname}:8510` : "http://localhost:8510";
  const base = fromQuery || fromMeta || fallback;
  document.querySelectorAll("[data-app]").forEach(a => {
    const path = a.dataset.app.startsWith("/") ? a.dataset.app : "/" + a.dataset.app;
    a.href = base + path;
  });

  // Phone menu
  const nav = document.querySelector("nav.top");
  const menuBtn = nav && nav.querySelector(".menu-btn");
  if (menuBtn) {
    const setOpen = (open) => {
      nav.classList.toggle("open", open);
      menuBtn.setAttribute("aria-expanded", String(open));
      menuBtn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    };
    menuBtn.addEventListener("click", () => setOpen(!nav.classList.contains("open")));
    nav.querySelectorAll(".links a").forEach(a => a.addEventListener("click", () => setOpen(false)));
    addEventListener("keydown", e => { if (e.key === "Escape" && nav.classList.contains("open")) { setOpen(false); menuBtn.focus(); } });
  }

  // 3D is decoration. If the scene script never starts (blocked network, old browser, no WebGL),
  // drop the scroll-driven 3D sections and show the still picture and the month's real counts.
  if (document.getElementById("hero3d")) {
    const no3d = () => {
      if (window.__meridian3d && !document.documentElement.classList.contains("nogl")) return;
      document.documentElement.classList.add("nogl");
      [["cLines", "1,180"], ["cPass", "1,032"], ["cBad", "148"]].forEach(([id, v]) => {
        const el = document.getElementById(id); if (el) el.textContent = v;
      });
    };
    addEventListener("error", e => { if (e.target && /scene3d\.js$/.test(e.target.src || "")) no3d(); }, true);
    addEventListener("load", () => setTimeout(no3d, 2500));
  }

  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.12 });
  document.querySelectorAll(".reveal").forEach(el => io.observe(el));

  if (!nav) return;
  const darks = [...document.querySelectorAll("section.dark, .ship, footer")];
  const onScroll = () => {
    const y = 34;
    nav.classList.toggle("on-dark", darks.some(d => { const r = d.getBoundingClientRect(); return r.top <= y && r.bottom > y; }));
    nav.classList.toggle("scrolled", scrollY > 8);
  };
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();
})();
