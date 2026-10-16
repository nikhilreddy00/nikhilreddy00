// Entry point: load data.json, wire tabs (hash routing), theme, live status.

import { $, ago, emit, on } from "./util.js";
import { startLive, describe } from "./live.js";
import { createTerminal } from "./terminal.js";
import { createMap } from "./map.js";
import { createDashboard } from "./dashboard.js";

const VIEWS = ["terminal", "map", "dashboard"];

async function main() {
  let data;
  try {
    const res = await fetch("data.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    $("#term-out").textContent = `Couldn't load profile data (${e.message}). Try reloading the page.`;
    return;
  }

  $("#who-name").textContent = data.identity.name;
  $("#who-role").textContent = `${data.identity.headline} · ${data.identity.current_role} @ ${data.identity.current_org}`;

  const terminal = createTerminal(data);
  const map = createMap(data);
  const dash = createDashboard(data);
  let booted = false;

  function route() {
    const view = VIEWS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "terminal";
    document.body.dataset.view = view;
    for (const v of VIEWS) {
      $(`#view-${v}`).hidden = v !== view;
      $(`#tab-${v}`).setAttribute("aria-selected", String(v === view));
    }
    if (view === "map") map.show();
    if (view === "dashboard") dash.show(); else dash.hide();
    if (view === "terminal") {
      if (!booted) { booted = true; terminal.boot(); }
      terminal.focus();
    }
  }
  window.addEventListener("hashchange", route);
  route();
  on("terminal-run", (cmd) => setTimeout(() => terminal.run(cmd), 50));

  // Theme: auto (follows OS) unless the visitor picks one.
  const applyTheme = (t) => {
    if (t === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = t;
    try { t === "auto" ? localStorage.removeItem("theme") : localStorage.setItem("theme", t); } catch (e) { /* storage blocked */ }
    emit("theme-changed", t);
  };
  on("theme", applyTheme);
  $("#theme-toggle").addEventListener("click", () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(dark ? "light" : "dark");
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => emit("theme-changed"));

  // Header live status: newest push from the real-time feed, else from data.json.
  const status = $("#live-status");
  const fallback = [...data.repos].sort((a, b) => b.pushed.localeCompare(a.pushed))[0];
  let latest = fallback ? { at: fallback.pushed, repo: fallback.name } : null;
  const paint = (ok) => {
    status.classList.toggle("on", ok);
    status.querySelector("span").textContent = latest ? `last push ${ago(latest.at)} · ${latest.repo}` : "live";
    status.title = ok ? "Live: polling GitHub's public events every 60 s" : "Live feed unavailable; showing hourly data";
  };
  on("live", ({ events, ok }) => {
    const push = events.map(describe).find((e) => e && e.kind === "push");
    if (push && (!latest || push.at > latest.at)) latest = { at: push.at, repo: push.repo };
    paint(ok);
  });
  paint(false);
  setInterval(() => paint(status.classList.contains("on")), 30_000);
  startLive(data.login);
}

main();
