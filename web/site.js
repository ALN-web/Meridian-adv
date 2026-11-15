// Shared behaviour: operator links, reveal on scroll, nav that adapts to dark sections.
(() => {
  const base = new URLSearchParams(location.search).get("app") ||
    (location.hostname ? `${location.protocol}//${location.hostname}:8510` : "http://localhost:8510");
  document.querySelectorAll("[data-app]").forEach(a => { a.href = base.replace(/\/$/, "") + a.dataset.app; });

  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: 0.12 });
  document.querySelectorAll(".reveal").forEach(el => io.observe(el));

  const nav = document.querySelector("nav.top");
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
