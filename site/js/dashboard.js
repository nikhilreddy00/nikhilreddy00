// Dashboard: one date range + brush selection scopes every chart, tile and
// table below it (Power BI-style cross-filtering). Language clicks filter
// the project table. Every mark has a hover tooltip.

import { $, h, ago, cssVar, fmtDay, fmtNum, fmtShort, hideTip, on, parseDay, safeUrl, showTip, sliceStats } from "./util.js";
import { describe, getEvents } from "./live.js";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function createDashboard(data) {
  const cal = data.calendar; // [[YYYY-MM-DD, count]] oldest → newest, 365 days
  const state = { days: 90, brush: null, alpha: 0.15, lang: null, sort: { key: "pushed", dir: -1 } };
  let visible = false;

  // ---- controls ------------------------------------------------------------
  const rangeEl = $("#dash-range");
  rangeEl.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-days]");
    if (!b) return;
    state.days = +b.dataset.days; state.brush = null; render();
  });
  const alphaEl = $("#dash-alpha"), alphaOut = $("#dash-alpha-out");
  alphaEl.addEventListener("input", () => { state.alpha = +alphaEl.value; alphaOut.value = alphaEl.value; drawDaily(); });

  // ---- data slices -----------------------------------------------------------
  const rangeDays = () => cal.slice(-state.days);
  function windowDays() {
    const r = rangeDays();
    if (!state.brush) return r;
    return r.filter(([d]) => d >= state.brush[0] && d <= state.brush[1]);
  }
  function previousWindow(len, endKey) {
    const i = cal.findIndex(([d]) => d === endKey);
    const start = Math.max(0, i - len - len + 1);
    return cal.slice(start, Math.max(0, i - len + 1));
  }

  // ---- render all ------------------------------------------------------------
  function render() {
    for (const b of rangeEl.querySelectorAll("button")) b.setAttribute("aria-pressed", String(+b.dataset.days === state.days));
    renderFilters(); drawKpis(); drawDaily(); drawWeekday(); drawHeatmap(); drawLangs(); drawTable(); drawFeed();
    $("#dash-asof").textContent = `data as of ${ago(data.generated_at)}`;
  }

  function renderFilters() {
    const chips = [];
    if (state.brush) chips.push(chip(`${fmtShort(parseDay(state.brush[0]))} – ${fmtShort(parseDay(state.brush[1]))}`, () => { state.brush = null; render(); }));
    if (state.lang) chips.push(chip(`language: ${state.lang}`, () => { state.lang = null; render(); }));
    $("#dash-filters").replaceChildren(...chips);
  }
  const chip = (text, clear) => h("span", { class: "filter" }, text, h("button", { type: "button", "aria-label": `Clear ${text}`, onclick: clear }, "×"));

  // ---- KPI tiles ---------------------------------------------------------------
  function drawKpis() {
    const w = windowDays(), s = sliceStats(w);
    const prev = w.length ? sliceStats(previousWindow(w.length, w[w.length - 1][0])) : null;
    let delta = "", cls = "";
    if (prev && prev.days === w.length) {
      if (prev.total) { const d = (s.total - prev.total) / prev.total; delta = `${d >= 0 ? "+" : ""}${Math.round(d * 100)}% vs previous ${w.length} days`; cls = d > 0 ? "up" : d < 0 ? "down" : ""; }
      else delta = s.total ? `up from 0 in previous ${w.length} days` : `same as previous ${w.length} days`;
    }
    const tiles = [
      ["contributions", fmtNum(s.total), delta, cls],
      ["active days", `${s.active}/${s.days}`, `${s.days ? Math.round((s.active / s.days) * 100) : 0}% of days`],
      ["longest streak", `${s.longest} day${s.longest === 1 ? "" : "s"}`, "in this window"],
      ["per active day", s.active ? (s.total / s.active).toFixed(1) : "0", "contributions on days with any"],
      ["busiest day", s.best && s.best[1] ? fmtShort(parseDay(s.best[0])) : "—", s.best && s.best[1] ? `${s.best[1]} contributions` : "no activity"],
    ];
    $("#dash-kpis").replaceChildren(...tiles.map(([label, value, sub, c]) =>
      h("div", { class: "kpi" }, h("span", { class: "label" }, label), h("span", { class: "value" }, value), h("span", { class: `sub ${c || ""}` }, sub || " "))));
  }

  // ---- daily bars + EMA + crosshair + brush ------------------------------------
  function drawDaily() {
    const el = $("#chart-daily");
    const days = rangeDays().map(([d, c]) => ({ d, date: parseDay(d), c }));
    const W = el.clientWidth || 600, H = 230, m = { t: 26, r: 10, b: 24, l: 34 };
    let ema = days.length ? days[0].c : 0;
    for (const p of days) { ema = (1 - state.alpha) * ema + state.alpha * p.c; p.ema = ema; }
    const x = d3.scaleTime().domain([days[0].date, d3.utcDay.offset(days[days.length - 1].date, 1)]).range([m.l, W - m.r]);
    const y = d3.scaleLinear().domain([0, Math.max(4, d3.max(days, (p) => p.c))]).nice().range([H - m.b, m.t]);
    const bw = Math.max(1, (W - m.l - m.r) / days.length - (days.length > 120 ? 0.5 : 2));

    const svg = d3.create("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("height", H);
    svg.append("g").attr("class", "gridline").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(y).ticks(4).tickSize(-(W - m.l - m.r)).tickFormat(""));
    svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickSizeOuter(0));
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
      .call(d3.axisBottom(x).ticks(W < 500 ? 4 : 7).tickSizeOuter(0).tickFormat(d3.utcFormat(state.days > 90 ? "%b" : "%b %d")));
    const inBrush = (p) => !state.brush || (p.d >= state.brush[0] && p.d <= state.brush[1]);
    svg.append("g").selectAll("rect").data(days.filter((p) => p.c > 0)).join("rect")
      .attr("x", (p) => x(p.date) + 0.5).attr("width", bw).attr("y", (p) => y(p.c)).attr("height", (p) => y(0) - y(p.c))
      .attr("rx", Math.min(2, bw / 2)).style("fill", "var(--s1)").style("fill-opacity", (p) => (inBrush(p) ? 0.8 : 0.25));
    svg.append("path").datum(days)
      .attr("d", d3.line().x((p) => x(p.date) + bw / 2).y((p) => y(p.ema)).curve(d3.curveMonotoneX))
      .style("fill", "none").style("stroke", "var(--s2)").style("stroke-width", 2);
    // Legend (two series → legend; the title names the measure).
    const lg = svg.append("g").attr("transform", `translate(${m.l},12)`).attr("class", "axis");
    lg.append("rect").attr("width", 10).attr("height", 10).attr("y", -8).attr("rx", 2).style("fill", "var(--s1)");
    lg.append("text").attr("x", 15).text("daily");
    lg.append("line").attr("x1", 64).attr("x2", 80).attr("y1", -3).attr("y2", -3).style("stroke", "var(--s2)").style("stroke-width", 2);
    lg.append("text").attr("x", 85).text(`EMA α=${state.alpha.toFixed(2)}`);

    const cross = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).style("stroke", "var(--muted)").style("stroke-dasharray", "3 3").attr("opacity", 0);
    const brush = d3.brushX().extent([[m.l, m.t], [W - m.r, H - m.b]])
      .on("end", (e) => {
        if (!e.sourceEvent) return;
        if (!e.selection) { if (state.brush) { state.brush = null; render(); } return; }
        const [a, b] = e.selection.map((px) => x.invert(px));
        const lo = d3.utcDay.floor(a), hi = d3.utcDay.offset(d3.utcDay.ceil(b), -1);
        if (hi < lo) return;
        state.brush = [lo.toISOString().slice(0, 10), hi.toISOString().slice(0, 10)];
        render();
      });
    const gb = svg.append("g").attr("class", "brush").call(brush);
    if (state.brush) gb.call(brush.move, [x(parseDay(state.brush[0])), x(d3.utcDay.offset(parseDay(state.brush[1]), 1))]);
    gb.on("pointermove.tip", (e) => {
      const [px] = d3.pointer(e, svg.node());
      const t = x.invert(px), i = Math.max(0, Math.min(days.length - 1, d3.utcDay.count(days[0].date, t)));
      const p = days[i];
      cross.attr("x1", x(p.date) + bw / 2).attr("x2", x(p.date) + bw / 2).attr("opacity", 1);
      showTip(e, fmtDay(p.date), [["contributions", p.c, cssVar("--s1")], ["EMA", p.ema.toFixed(2), cssVar("--s2")]]);
    }).on("pointerleave.tip", () => { cross.attr("opacity", 0); hideTip(); });
    el.replaceChildren(svg.node());
  }

  // ---- weekday profile ---------------------------------------------------------
  function drawWeekday() {
    const el = $("#chart-weekday");
    const sums = Array(7).fill(0), counts = Array(7).fill(0);
    for (const [d, c] of windowDays()) { const wd = (parseDay(d).getUTCDay() + 6) % 7; sums[wd] += c; counts[wd]++; }
    const W = el.clientWidth || 300, H = 230, m = { t: 8, r: 34, b: 8, l: 38 };
    const y = d3.scaleBand().domain(WEEKDAYS).range([m.t, H - m.b]).padding(0.28);
    const x = d3.scaleLinear().domain([0, Math.max(1, d3.max(sums))]).range([m.l, W - m.r]);
    const svg = d3.create("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("height", H);
    svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).tickSize(0)).select(".domain").remove();
    const g = svg.append("g").selectAll("g").data(WEEKDAYS).join("g");
    g.append("rect").attr("x", m.l).attr("y", (d) => y(d) - 3).attr("width", W - m.r - m.l).attr("height", y.bandwidth() + 6).style("fill", "transparent");
    g.append("rect").attr("x", m.l).attr("y", (d) => y(d)).attr("height", y.bandwidth()).attr("rx", 4)
      .attr("width", (d, i) => Math.max(sums[i] ? 3 : 0, x(sums[i]) - m.l)).style("fill", "var(--s1)");
    g.append("text").attr("class", "axis").attr("x", (d, i) => x(sums[i]) + 6).attr("y", (d) => y(d) + y.bandwidth() / 2 + 4)
      .text((d, i) => sums[i]).style("font", "11px var(--mono)").style("fill", "var(--muted)");
    g.on("pointermove", (e, d) => { const i = WEEKDAYS.indexOf(d); showTip(e, d, [["contributions", sums[i], cssVar("--s1")], [`across ${counts[i]} ${d}s`]]); })
      .on("pointerleave", hideTip);
    el.replaceChildren(svg.node());
  }

  // ---- 12-month heatmap (click a week to select it) ------------------------------
  function drawHeatmap() {
    const el = $("#chart-heatmap");
    const W = el.clientWidth || 700;
    const first = parseDay(cal[0][0]), offset = (first.getUTCDay() + 6) % 7;
    const weeks = Math.ceil((offset + cal.length) / 7);
    const m = { t: 18, l: 30 }, gap = 2;
    const cell = Math.max(6, Math.min(14, Math.floor((W - m.l) / weeks) - gap));
    const H = m.t + 7 * (cell + gap) + 4;
    const needW = m.l + weeks * (cell + gap);
    const nz = cal.map(([, c]) => c).filter(Boolean).sort((a, b) => a - b);
    const q = nz.length ? [0.25, 0.5, 0.75].map((f) => nz[Math.floor(nz.length * f)]) : [1, 2, 3];
    const level = (c) => (c ? 1 + q.filter((t) => c > t).length : 0);
    const win = new Set(windowDays().map(([d]) => d));
    const svg = d3.create("svg").attr("viewBox", `0 0 ${Math.max(W, needW)} ${H}`).attr("width", Math.max(W, needW)).attr("height", H);
    const cells = svg.append("g").selectAll("rect").data(cal).join("rect")
      .attr("x", (_, i) => m.l + Math.floor((offset + i) / 7) * (cell + gap))
      .attr("y", ([d]) => m.t + ((parseDay(d).getUTCDay() + 6) % 7) * (cell + gap))
      .attr("width", cell).attr("height", cell).attr("rx", 2)
      .style("fill", ([, c]) => (level(c) ? `var(--q${level(c)})` : "var(--grid)"))
      .style("opacity", ([d]) => (win.has(d) ? 1 : 0.28)).style("cursor", "pointer");
    cells.on("pointermove", (e, [d, c]) => showTip(e, fmtDay(parseDay(d)), [["contributions", c]]))
      .on("pointerleave", hideTip)
      .on("click", (e, [d]) => {
        const day = parseDay(d), wd = (day.getUTCDay() + 6) % 7;
        const lo = d3.utcDay.offset(day, -wd), hi = d3.utcDay.offset(lo, 6);
        state.days = 365;
        state.brush = [lo.toISOString().slice(0, 10), hi.toISOString().slice(0, 10) > cal[cal.length - 1][0] ? cal[cal.length - 1][0] : hi.toISOString().slice(0, 10)];
        render();
      });
    cal.forEach(([d], i) => {
      const day = parseDay(d);
      if (day.getUTCDate() === 1) svg.append("text").attr("class", "axis").attr("x", m.l + Math.floor((offset + i) / 7) * (cell + gap)).attr("y", 11)
        .text(d3.utcFormat("%b")(day)).style("font", "10.5px var(--mono)").style("fill", "var(--faint)");
    });
    ["Mon", "Wed", "Fri"].forEach((t, k) => svg.append("text").attr("x", 0).attr("y", m.t + (k * 2) * (cell + gap) + cell - 1)
      .text(t).style("font", "10px var(--mono)").style("fill", "var(--faint)"));
    el.replaceChildren(svg.node());
    el.scrollLeft = el.scrollWidth; // narrow screens: open on the most recent weeks
  }

  // ---- language donut (click to filter projects) --------------------------------
  function drawLangs() {
    const el = $("#chart-langs");
    const langs = data.languages;
    const W = el.clientWidth || 300, size = Math.min(170, W * 0.45), R = size / 2;
    const svg = d3.create("svg").attr("viewBox", `0 0 ${W} ${Math.max(size, langs.length * 24 + 8)}`).attr("height", Math.max(size, langs.length * 24 + 8));
    const g = svg.append("g").attr("transform", `translate(${R},${R})`);
    const arcs = d3.pie().sort(null).value((l) => l.share).padAngle(0.02)(langs);
    const arc = d3.arc().innerRadius(R * 0.58).outerRadius(R).cornerRadius(3);
    const toggle = (name) => { if (name === "Other") return; state.lang = state.lang === name ? null : name; render(); };
    g.selectAll("path").data(arcs).join("path").attr("d", arc)
      .style("fill", (a) => a.data.color || "var(--faint)").style("stroke", "var(--panel)").style("stroke-width", 2)
      .style("opacity", (a) => (!state.lang || state.lang === a.data.name ? 1 : 0.3)).style("cursor", (a) => (a.data.name === "Other" ? "default" : "pointer"))
      .on("pointermove", (e, a) => showTip(e, a.data.name, [["of code", `${(a.data.share * 100).toFixed(1)}%`, a.data.color]]))
      .on("pointerleave", hideTip).on("click", (e, a) => toggle(a.data.name));
    g.append("text").attr("text-anchor", "middle").attr("y", 5).text(state.lang || `${langs.length} langs`)
      .style("font", "600 12px var(--mono)").style("fill", "var(--fg)");
    const lx = size + 16;
    const items = svg.append("g").selectAll("g").data(langs).join("g").attr("transform", (_, i) => `translate(${lx},${14 + i * 24})`)
      .style("cursor", (l) => (l.name === "Other" ? "default" : "pointer")).style("opacity", (l) => (!state.lang || state.lang === l.name ? 1 : 0.4))
      .on("click", (e, l) => toggle(l.name));
    items.append("rect").attr("y", -9).attr("width", 10).attr("height", 10).attr("rx", 2).style("fill", (l) => l.color || "var(--faint)");
    items.append("text").attr("x", 16).text((l) => l.name).style("font", "12px var(--mono)").style("fill", "var(--fg)");
    items.append("text").attr("x", W - lx - 4).attr("text-anchor", "end").text((l) => `${(l.share * 100).toFixed(l.share < 0.01 ? 1 : 0)}%`)
      .style("font", "12px var(--mono)").style("fill", "var(--muted)");
    el.replaceChildren(svg.node());
    if (data.languages_excluded?.length) el.append(h("p", { class: "muted", style: { font: "11px var(--mono)", margin: "6px 0 0" } }, `excludes ${data.languages_excluded.join(", ")}`));
  }

  // ---- project table (sortable, filtered by language) -----------------------------
  const COLS = [
    ["name", "Project"], ["cluster", "Cluster"], ["language", "Language"], ["stars", "★", true], ["commits_12mo", "Commits 12 mo", true], ["pushed", "Last push"],
  ];
  function drawTable() {
    const clusterName = (id) => data.clusters.find((c) => c.id === id)?.label || "—";
    let rows = data.repos.filter((r) => !state.lang || r.language === state.lang);
    const { key, dir } = state.sort;
    const val = (r) => (key === "cluster" ? clusterName(r.cluster) : r[key] ?? "");
    rows = [...rows].sort((a, b) => { const va = val(a), vb = val(b); return (typeof va === "number" ? va - vb : String(va).localeCompare(String(vb))) * dir; });
    $("#repo-count").textContent = `${rows.length} of ${data.repos.length}${state.lang ? ` · ${state.lang}` : ""} · click a header to sort`;
    const head = h("tr", {}, ...COLS.map(([k, label, num]) => h("th", {
      scope: "col", tabindex: 0, "aria-sort": key === k ? (dir > 0 ? "ascending" : "descending") : "none", style: num ? { textAlign: "right" } : null,
      onclick: () => sortBy(k), onkeydown: (e) => { if (e.key === "Enter") sortBy(k); },
    }, label)));
    const body = rows.map((r) => h("tr", {},
      h("td", {}, h("a", { href: safeUrl(r.url), target: "_blank", rel: "noopener" }, r.name), r.description ? h("div", { class: "desc" }, r.description.length > 110 ? r.description.slice(0, 109) + "…" : r.description) : null),
      h("td", {}, r.cluster != null ? h("span", { class: "dot", style: { background: `var(--s${(r.cluster % 8) + 1})` } }) : null, clusterName(r.cluster)),
      h("td", {}, h("span", { class: "dot", style: { background: r.color || "var(--faint)" } }), r.language || "—"),
      h("td", { class: "num" }, r.stars || ""),
      h("td", { class: "num" }, r.commits_12mo || ""),
      h("td", { title: r.pushed }, ago(r.pushed)),
    ));
    $("#repo-table").replaceChildren(h("thead", {}, head), h("tbody", {}, ...body));
  }
  function sortBy(k) {
    state.sort = state.sort.key === k ? { key: k, dir: -state.sort.dir } : { key: k, dir: ["name", "cluster", "language"].includes(k) ? 1 : -1 };
    drawTable();
  }

  // ---- live feed --------------------------------------------------------------------
  function drawFeed() {
    const items = getEvents().map(describe).filter(Boolean).slice(0, 25);
    const el = $("#live-feed");
    if (!items.length) { el.replaceChildren(h("li", {}, h("span", { class: "muted" }, "Waiting for GitHub… (the public events API allows 60 requests an hour per visitor)"))); return; }
    el.replaceChildren(...items.map((e) => h("li", { class: e.kind },
      h("span", {}, e.text), e.detail ? h("span", { class: "msg" }, e.detail) : null, h("time", { datetime: e.at, title: e.at }, ago(e.at)))));
  }

  on("live", () => { if (visible) drawFeed(); });
  on("theme-changed", () => { if (visible) render(); });
  setInterval(() => { if (visible) { drawFeed(); $("#dash-asof").textContent = `data as of ${ago(data.generated_at)}`; } }, 30_000);
  let rt;
  new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(() => { if (visible) render(); }, 120); }).observe($("#view-dashboard"));

  return { show() { visible = true; render(); }, hide() { visible = false; hideTip(); } };
}
