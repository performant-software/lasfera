/*
 * Manuscript word cloud for the Manuscripts page.
 *
 * Each holding city's name is sized by how many manuscripts it holds and
 * placed so that cities keep their compass relation to one another
 * (Florence above Rome, Washington to the west of both, Tenri to the east).
 * Distances are compressed, not true. Clicking a name lists that city's
 * manuscripts by library below the cloud.
 *
 * Expects: d3 v7 loaded globally, a <script id="ms-cloud-data"> JSON block
 * (from manuscript/manuscript_cloud.py), and the markup in
 * templates/partials/manuscript_cloud.html.
 */
(function () {
  const root = document.querySelector(".ms-cloud");
  const dataEl = document.getElementById("ms-cloud-data");
  if (!root || !dataEl || !window.d3) return;

  const PLACES = JSON.parse(dataEl.textContent);
  if (!PLACES.length) return;

  const coll = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  PLACES.forEach((p, i) => {
    p.id = i;
    p.label = p.city;
    p.inst.sort((a, b) => b.mss.length - a.mss.length || coll.compare(a.name, b.name));
    p.inst.forEach((ins) => ins.mss.sort((a, b) => coll.compare(a[0], b[0])));
    p.count = p.inst.reduce((s, x) => s + x.mss.length, 0);
  });
  const located = PLACES.filter((p) => p.lat != null);
  // Size only by the cities on the cloud; the "not mapped" group isn't drawn
  const MAXC = Math.max(2, d3.max(located, (p) => p.count) || 0);
  let selected = located.slice().sort((a, b) => b.count - a.count)[0] || PLACES[0];

  const summary = root.querySelector(".ms-cloud__summary");
  if (summary) {
    const total = located.reduce((s, p) => s + p.count, 0);
    summary.textContent = `${total} manuscripts in ${located.length} cities. Select a city to list its manuscripts.`;
  }

  /* ---------- Layout ---------- */
  const stage = root.querySelector(".ms-cloud__stage");
  const frame = root.querySelector(".ms-cloud__frame");
  const svg = d3.select(root.querySelector("svg"));
  const gW = svg.append("g");
  const detEl = root.querySelector(".ms-cloud__detail");
  let W = 0, H = 0, words = [];

  const region = (p) =>
    p.country === "Italy" || p.country === "Vatican City" ? "it"
      : p.country === "USA" ? "na"
      : p.country === "Japan" ? "jp" : "eu";

  const ctx = document.createElement("canvas").getContext("2d");
  const FAMILY = '"Barlow Semi Condensed", "Arial Narrow", "Helvetica Neue", Arial, sans-serif';
  function measure(text, size) {
    ctx.font = `600 ${size}px ${FAMILY}`;
    const m = ctx.measureText(text);
    return {
      w: m.width,
      asc: m.actualBoundingBoxAscent || size * 0.72,
      desc: m.actualBoundingBoxDescent || size * 0.22,
    };
  }

  // Compress distance from Florence logarithmically, then blend with rank order
  // so the names spread across the frame instead of leaving an empty Atlantic.
  const LON0 = 11.3, LAT0 = 43.6, SC = 1.1, LON_GAP = 2.0, LAT_GAP = 1.4;
  const fx = (d) => Math.sign(d) * Math.log1p(Math.abs(d) / SC);
  function blend(vals) {
    const [a, b] = d3.extent(vals);
    const sorted = vals.slice().sort((x, y) => x - y);
    const n = Math.max(1, vals.length - 1);
    return vals.map((v) => {
      const lin = b > a ? (v - a) / (b - a) : 0.5;
      const lo = d3.bisectLeft(sorted, v), hi = d3.bisectRight(sorted, v);
      return 0.4 * lin + 0.6 * ((lo + (hi - lo - 1) / 2) / n);
    });
  }

  function tryLayout(maxF) {
    const minF = Math.max(W < 500 ? 10 : 12, maxF * 0.16);
    const pad = 2, placed = [];
    let viol = 0;
    const us = blend(located.map((p) => fx(p.lon - LON0)));
    const vs = blend(located.map((p) => -fx(p.lat - LAT0)));
    const mx = Math.min(70, W * 0.1), my = Math.min(28, H * 0.06);
    const list = located
      .map((p, i) => ({ p, tx: mx + us[i] * (W - 2 * mx), ty: my + vs[i] * (H - 2 * my) }))
      .sort((a, b) => b.p.count - a.p.count || coll.compare(a.p.label, b.p.label));

    for (let i = 0; i < list.length; i++) {
      const { p, tx, ty } = list[i];
      const size = minF + (maxF - minF) * Math.sqrt((p.count - 1) / (MAXC - 1));
      const m = measure(p.label, size);
      const vertical = p.count === 1 && !p.label.includes(" ") && p.label.length <= 7 && i % 3 === 1;
      const bw = (vertical ? m.asc + m.desc : m.w) + pad * 2;
      const bh = (vertical ? m.w : m.asc + m.desc) + pad * 2;
      let best = null;
      for (let s = 0; s < 9000; s++) {
        const th = s * 0.1, r = 1.2 * th;
        if (r > Math.max(W, H)) break;
        const cx = tx + r * Math.cos(th) * 1.6, cy = ty + r * Math.sin(th);
        const x = cx - bw / 2, y = cy - bh / 2;
        if (x < 4 || y < 4 || x + bw > W - 4 || y + bh > H - 4) continue;
        if (placed.some((q) => x < q.x + q.w && x + bw > q.x && y < q.y + q.h && y + bh > q.y)) continue;
        // Count compass-order slips against words already placed; never allow big ones.
        let v = 0, hard = false;
        for (const q of placed) {
          const dl = p.lon - q.p.lon, dt = p.lat - q.p.lat;
          const qx = q.x + q.w / 2, qy = q.y + q.h / 2;
          const bx = Math.abs(dl) > LON_GAP && Math.sign(cx - qx) !== Math.sign(dl);
          const by = Math.abs(dt) > LAT_GAP && Math.sign(qy - cy) !== Math.sign(dt);
          if (bx || by) {
            v++;
            if (Math.abs(dl) > 25 || (by && Math.abs(dt) > 6)) hard = true;
          }
        }
        if (hard) continue;
        if (!best || v < best.v) best = { x, y, v };
        if (v === 0) break;
      }
      if (!best) return null;
      viol += best.v;
      placed.push({ p, x: best.x, y: best.y, w: bw, h: bh, size, vertical, asc: m.asc, desc: m.desc });
    }
    placed.viol = viol;
    return placed;
  }

  async function computeLayout() {
    const rect = frame.getBoundingClientRect();
    W = rect.width; H = rect.height;
    if (W < 50 || H < 50) return;
    svg.attr("viewBox", `0 0 ${W} ${H}`);
    try { await document.fonts.load(`600 40px ${FAMILY}`); } catch (e) { /* use fallback */ }
    let maxF = Math.min(W / 5, H / 3), res = null;
    for (let k = 0; k < 50 && !res; k++) {
      const r = tryLayout(maxF);
      if (r && r.viol <= 2) res = r; else maxF *= 0.95;
    }
    if (!res) {
      maxF = Math.min(W / 5, H / 3);
      for (let k = 0; k < 50 && !res; k++) { res = tryLayout(maxF); if (!res) maxF *= 0.95; }
    }
    words = res || [];
  }

  function render() {
    const plural = (n) => `${n} manuscript${n > 1 ? "s" : ""}`;
    const g = gW.selectAll("g.ms-word").data(words, (d) => d.p.id).join((enter) => {
      const g = enter.append("g").attr("tabindex", 0).attr("role", "button");
      g.append("title"); g.append("rect").attr("class", "ms-word__hl").attr("rx", 4); g.append("text");
      g.on("click", (e, d) => select(d.p)).on("keydown", (e, d) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(d.p); }
      });
      return g;
    });
    g.attr("transform", (d) => `translate(${d.x + d.w / 2},${d.y + d.h / 2})${d.vertical ? " rotate(-90)" : ""}`)
      .attr("class", (d) => `ms-word ms-word--${region(d.p)}`)
      .classed("is-selected", (d) => d.p === selected)
      .attr("aria-label", (d) => `${d.p.label}: ${plural(d.p.count)}`);
    g.select("title").text((d) => `${d.p.label} · ${plural(d.p.count)}`);
    g.select("rect").each(function (d) {
      const w = d.vertical ? d.h : d.w, h = d.vertical ? d.w : d.h;
      d3.select(this).attr("x", -w / 2 - 3).attr("y", -h / 2 - 2).attr("width", w + 6).attr("height", h + 4);
    });
    g.select("text").attr("text-anchor", "middle").attr("y", (d) => (d.asc - d.desc) / 2)
      .style("font-size", (d) => d.size + "px").text((d) => d.p.label);
  }

  /* ---------- Detail list ---------- */
  function renderDetail() {
    const p = selected;
    const n = p.count, k = p.inst.length;
    detEl.innerHTML = `
      <p class="ms-cloud__eyebrow">${p.lat == null ? "Not on the cloud" : esc(p.country)}</p>
      <h5 class="ms-cloud__place">${esc(p.label)}</h5>
      <p class="ms-cloud__meta">${n} manuscript${n > 1 ? "s" : ""} · ${k} ${k > 1 ? "libraries" : "library"}</p>
      <div class="ms-cloud__libs">
      ${p.inst.map((ins) => `
        <section class="ms-cloud__lib">
          <h6>${esc(ins.name)}<span>${ins.mss.length}</span></h6>
          <ul>${ins.mss.map(([shelf, sig, url]) => `
            <li><a href="${esc(url)}"><span class="ms-cloud__sig">${esc(sig)}</span><span>${esc(shelf)}</span></a></li>`).join("")}
          </ul>
        </section>`).join("")}
      </div>
      ${PLACES.some((x) => x.lat == null) && p.lat != null
        ? `<button type="button" class="ms-cloud__unmapped">Show manuscripts with no mapped location</button>` : ""}`;
    const btn = detEl.querySelector(".ms-cloud__unmapped");
    if (btn) btn.addEventListener("click", () => select(PLACES.find((x) => x.lat == null)));
  }

  function select(p) {
    selected = p;
    renderDetail();
    render();
  }

  // Start from the current size so the observer's first callback doesn't
  // repeat the initial layout below
  const r0 = frame.getBoundingClientRect();
  let lastW = r0.width, lastH = r0.height;
  new ResizeObserver(() => {
    const r = frame.getBoundingClientRect();
    if (Math.abs(r.width - lastW) < 1 && Math.abs(r.height - lastH) < 1) return;
    lastW = r.width; lastH = r.height;
    computeLayout().then(render);
  }).observe(frame);

  renderDetail();
  computeLayout().then(() => {
    render();
    if (stage) stage.scrollLeft = (stage.scrollWidth - stage.clientWidth) / 2;
  });
})();
