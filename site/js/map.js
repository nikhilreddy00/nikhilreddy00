// Latent space: a force layout anchored to each repo's embedding position.
// Drag a bubble and a spring pulls it back to where its meaning puts it
// (or "pin where dropped" keeps it). Zoom, pan, hover, click for details.

import { $, h, ago, clusterColor, emit, hideTip, on, safeUrl, showTip } from "./util.js";

export function createMap(data) {
  const svgEl = $("#map-svg"), drawer = $("#map-drawer"), legendEl = $("#map-legend");
  const search = $("#map-search"), pinBox = $("#map-pin");
  const svg = d3.select(svgEl);
  const root = svg.append("g");
  const gHull = root.append("g"), gNode = root.append("g"), gLabel = root.append("g");

  const repos = data.repos.filter((r) => r.cluster != null);
  const newest = [...repos].sort((a, b) => b.pushed.localeCompare(a.pushed));
  const rank = new Map(newest.map((r, i) => [r.name, i]));
  // ex/ey: the embedding position (0..1); x/y belong to the simulation.
  const nodes = repos.map((r) => ({ ...r, ex: r.x, ey: r.y, x: undefined, y: undefined,
    r: 7 + 9 * (1 - rank.get(r.name) / Math.max(1, repos.length - 1)) + Math.min(6, r.stars * 2) }));
  const hidden = new Set();
  let W = 0, H = 0, query = "", selected = null, hoverCluster = null;

  // Where each cluster has been dragged to (px). Bubbles anchor to their
  // embedding position plus their cluster's offset, so a moved cluster stays put.
  const offset = new Map();
  const shift = (id) => offset.get(id) || { dx: 0, dy: 0 };
  const anchor = (n) => ({ x: 70 + n.ex * (W - 140) + shift(n.cluster).dx, y: 60 + (1 - n.ey) * (H - 120) + shift(n.cluster).dy });

  const sim = d3.forceSimulation(nodes)
    .force("x", d3.forceX((n) => anchor(n).x).strength(0.09))
    .force("y", d3.forceY((n) => anchor(n).y).strength(0.09))
    .force("collide", d3.forceCollide((n) => n.r + 4).iterations(2))
    .alphaDecay(0.03)
    .on("tick", ticked);

  const zoom = d3.zoom().scaleExtent([0.5, 4]).on("zoom", (e) => root.attr("transform", e.transform));
  svg.call(zoom).on("dblclick.zoom", null);

  // Nodes
  const node = gNode.selectAll("g").data(nodes, (d) => d.name).join("g")
    .attr("class", "node").attr("tabindex", 0).attr("role", "button")
    .attr("aria-label", (d) => `${d.name}: ${d.description || "no description"}`);
  node.append("circle").attr("class", "hit").attr("r", (d) => Math.max(12, d.r + 6)).attr("fill", "transparent");
  node.append("circle").attr("class", "ring");
  node.append("circle").attr("class", "dot").attr("r", (d) => d.r);
  const label = gLabel.selectAll("text").data(nodes, (d) => d.name).join("text").attr("class", "node-label").text((d) => d.name);

  node.call(d3.drag()
    .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.25).restart(); d.fx = d.x; d.fy = d.y; hideTip(); })
    .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); if (!pinBox.checked) { d.fx = null; d.fy = null; } }));
  node.on("pointerenter", (e, d) => { hoverCluster = d.cluster; style(); tooltip(e, d); })
    .on("pointermove", (e, d) => tooltip(e, d))
    .on("pointerleave", () => { hoverCluster = null; style(); hideTip(); })
    .on("click", (e, d) => { if (e.defaultPrevented) return; select(d); })
    .on("keydown", (e, d) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(d); } });

  function tooltip(e, d) {
    const cl = data.clusters.find((c) => c.id === d.cluster);
    showTip(e, d.name, [
      [d.description ? (d.description.length > 120 ? d.description.slice(0, 119) + "…" : d.description) : "no description"],
      [d.language || "—", null, d.color || null],
      [`pushed ${ago(d.pushed)}`, d.stars ? `★${d.stars}` : null],
      [cl ? cl.label : "", null, clusterColor(d.cluster)],
    ]);
  }

  // Cluster hulls: padded convex hull around each cluster's bubbles.
  const hullLine = d3.line().curve(d3.curveCatmullRomClosed.alpha(0.6));
  function hullPoints(c) {
    const pts = [];
    for (const n of nodes) {
      if (n.cluster !== c.id) continue;
      const pad = n.r + 16;
      for (let k = 0; k < 10; k++) pts.push([n.x + pad * Math.cos((k / 10) * 2 * Math.PI), n.y + pad * Math.sin((k / 10) * 2 * Math.PI)]);
    }
    return pts.length ? d3.polygonHull(pts) : null;
  }
  const hull = gHull.selectAll("path").data(data.clusters, (c) => c.id).join("path").attr("class", "hull");
  const hullLabel = gLabel.selectAll("text.hull-label").data(data.clusters, (c) => c.id).join("text")
    .attr("class", "hull-label").attr("text-anchor", "middle").text((c) => c.label);

  // Drag a whole cluster by its shaded area or its name.
  const clusterDrag = d3.drag()
    .on("start", (e) => { if (!e.active) sim.alphaTarget(0.2).restart(); hideTip(); })
    .on("drag", (e, c) => {
      const o = shift(c.id);
      offset.set(c.id, { dx: o.dx + e.dx, dy: o.dy + e.dy });
      for (const n of nodes) {
        if (n.cluster !== c.id) continue;
        n.x += e.dx; n.y += e.dy;
        if (n.fx != null) { n.fx += e.dx; n.fy += e.dy; }
      }
      ticked();
    })
    .on("end", (e) => { if (!e.active) sim.alphaTarget(0); });
  hull.call(clusterDrag).style("cursor", "move");
  hullLabel.call(clusterDrag).style("cursor", "move");
  const clusterTip = (e, c) => showTip(e, c.label, [[`${nodes.filter((n) => n.cluster === c.id).length} repos · drag to move the cluster`], [c.terms.slice(0, 5).join(" · ")]]);
  for (const sel of [hull, hullLabel]) {
    sel.on("pointerenter", (e, c) => { hoverCluster = c.id; style(); clusterTip(e, c); })
      .on("pointermove", clusterTip)
      .on("pointerleave", () => { hoverCluster = null; style(); hideTip(); });
  }

  function ticked() {
    node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    label.attr("x", (d) => d.x + d.r + 5).attr("y", (d) => d.y + 4);
    hull.attr("d", (c) => { const p = hullPoints(c); return p ? hullLine(p) : null; });
    hullLabel.each(function (c) {
      const members = nodes.filter((n) => n.cluster === c.id);
      if (!members.length) return;
      const top = d3.min(members, (n) => n.y - n.r) - 24;
      d3.select(this).attr("x", d3.mean(members, (n) => n.x)).attr("y", top);
    });
  }

  // Visual state: hidden clusters, search matches, hover and selection.
  function matches(d) {
    if (!query) return true;
    return [d.name, d.description, ...(d.topics || [])].join(" ").toLowerCase().includes(query);
  }
  function style() {
    const dim = (d) => hidden.has(d.cluster) || !matches(d) || (hoverCluster != null && d.cluster !== hoverCluster);
    node.attr("opacity", (d) => (hidden.has(d.cluster) ? 0.08 : dim(d) ? 0.25 : 1))
      .attr("pointer-events", (d) => (hidden.has(d.cluster) ? "none" : null));
    node.select(".dot").style("fill", (d) => clusterColor(d.cluster)).style("stroke", "var(--panel)").style("stroke-width", 2);
    node.select(".ring").attr("r", (d) => d.r + 5).style("fill", "none")
      .style("stroke", (d) => (selected === d.name ? "var(--fg)" : rank.get(d.name) === 0 ? clusterColor(d.cluster) : "none"))
      .attr("stroke-width", (d) => (selected === d.name ? 2 : 1.5)).attr("stroke-dasharray", (d) => (selected === d.name ? null : "3 3"));
    const showLabel = (d) => !hidden.has(d.cluster) && (rank.get(d.name) < 10 || selected === d.name || (query && matches(d)) || hoverCluster === d.cluster);
    label.attr("opacity", (d) => (showLabel(d) ? (dim(d) ? 0.35 : 1) : 0));
    hull.attr("fill", (c) => clusterColor(c.id)).attr("fill-opacity", (c) => (hidden.has(c.id) ? 0 : hoverCluster === c.id ? 0.16 : 0.08))
      .attr("stroke", (c) => clusterColor(c.id)).attr("stroke-opacity", (c) => (hidden.has(c.id) ? 0 : 0.45)).attr("stroke-dasharray", "4 4");
    hullLabel.attr("opacity", (c) => (hidden.has(c.id) ? 0 : 1));
  }

  // Legend doubles as cluster filter (identity is never color alone: names + hull labels).
  function buildLegend() {
    legendEl.replaceChildren(...data.clusters.map((c) => {
      const count = nodes.filter((n) => n.cluster === c.id).length;
      return h("button", {
        type: "button", "aria-pressed": hidden.has(c.id) ? "false" : "true", title: c.terms.slice(0, 5).join(" · "),
        onclick: () => { hidden.has(c.id) ? hidden.delete(c.id) : hidden.add(c.id); buildLegend(); style(); },
        onpointerenter: () => { hoverCluster = c.id; style(); }, onpointerleave: () => { hoverCluster = null; style(); },
      }, h("i", { style: { background: clusterColor(c.id) } }), `${c.label} ${count}`);
    }));
  }

  function select(d) {
    selected = d?.name || null;
    style();
    if (!d) { drawer.hidden = true; return; }
    const cl = data.clusters.find((c) => c.id === d.cluster);
    drawer.replaceChildren(
      h("button", { class: "btn close", type: "button", "aria-label": "Close details", onclick: () => select(null) }, "×"),
      h("h4", {}, d.name),
      h("div", { class: "meta" }, h("span", {}, d.language || "—"), h("span", {}, `★ ${d.stars}`), h("span", {}, `pushed ${ago(d.pushed)}`),
        d.commits_12mo ? h("span", {}, `${d.commits_12mo} commits / 12 mo`) : null),
      h("p", {}, d.description || "No description."),
      d.topics?.length ? h("div", { class: "tags" }, ...d.topics.map((t) => h("span", {}, `#${t}`))) : null,
      cl ? h("div", { class: "meta" }, h("span", {}, `cluster: ${cl.label}`), h("span", {}, cl.terms.slice(0, 4).join(" · "))) : null,
      h("div", { class: "row" },
        h("a", { class: "btn", href: safeUrl(d.url), target: "_blank", rel: "noopener" }, "Open on GitHub ↗"),
        h("button", { class: "btn", type: "button", onclick: () => { location.hash = "#terminal"; emit("terminal-run", `cat ${d.name}`); } }, "Read README")),
    );
    drawer.hidden = false;
  }

  search.addEventListener("input", () => { query = search.value.trim().toLowerCase(); style(); });
  $("#map-reset").addEventListener("click", reset);
  svg.on("click", (e) => { if (e.target === svgEl) select(null); });

  function reset() {
    hidden.clear(); offset.clear(); query = ""; search.value = ""; pinBox.checked = false;
    for (const n of nodes) { n.fx = null; n.fy = null; }
    buildLegend(); select(null);
    svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
    sim.alpha(0.8).restart();
  }

  function resize() {
    const r = svgEl.getBoundingClientRect();
    if (!r.width) return;
    const first = W === 0;
    W = r.width; H = r.height;
    svg.attr("viewBox", `0 0 ${W} ${H}`);
    if (first) for (const n of nodes) { const a = anchor(n); n.x = a.x + (Math.random() - 0.5) * 40; n.y = a.y + (Math.random() - 0.5) * 40; }
    sim.force("x").x((n) => anchor(n).x);
    sim.force("y").y((n) => anchor(n).y);
    sim.alpha(first ? 1 : 0.5).restart();
  }

  on("focus-repo", (name) => {
    const d = nodes.find((n) => n.name === name);
    if (!d) return;
    hidden.delete(d.cluster); buildLegend(); select(d);
    const t = d3.zoomIdentity.translate(W / 2, H / 2).scale(1.8).translate(-d.x, -d.y);
    svg.transition().duration(600).call(zoom.transform, t);
  });
  on("theme-changed", () => { buildLegend(); style(); });

  buildLegend();
  style();
  new ResizeObserver(resize).observe(svgEl);
  return { show: () => { resize(); sim.alpha(0.3).restart(); } };
}
