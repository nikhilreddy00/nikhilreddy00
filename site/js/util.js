// Small DOM and formatting helpers shared by every view.

export const $ = (sel, root = document) => root.querySelector(sel);

// h("div", {class: "x", onclick}, "text", child) — strings become text nodes, never HTML.
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// Links built from data only ever use web or mail schemes (defence in depth beside the CSP).
export function safeUrl(url) {
  try {
    const u = new URL(String(url), location.href);
    return ["https:", "http:", "mailto:"].includes(u.protocol) ? u.href : "#";
  } catch (e) { return "#"; }
}

export const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const clusterColor = (id) => cssVar(`--s${(id % 8) + 1}`);

export const parseDay = (s) => new Date(s + "T00:00:00Z");
export const dayKey = (d) => d.toISOString().slice(0, 10);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const fmtDay = (d) => `${WEEKDAYS[d.getUTCDay()]} ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
export const fmtDate = (d) => `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
export const fmtShort = (d) => `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
export const fmtNum = (n) => Number(n).toLocaleString("en-US");

export function ago(date, now = Date.now()) {
  const s = Math.max(0, Math.round((now - new Date(date).getTime()) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const hr = Math.round(m / 60);
  if (hr < 24) return `${hr} h ago`;
  const d = Math.round(hr / 24);
  if (d < 30) return `${d} day${d === 1 ? "" : "s"} ago`;
  const mo = Math.round(d / 30);
  if (mo < 12) return `${mo} mo ago`;
  return `${Math.round(mo / 12)} yr ago`;
}

// Shared tooltip: rows of [label, value, color?]; content built with textContent only.
const tip = () => document.getElementById("tooltip");
export function showTip(evt, title, rows = []) {
  const el = tip();
  el.replaceChildren();
  if (title) el.append(h("div", {}, h("b", {}, title)));
  for (const [label, value, color] of rows) {
    el.append(h("div", {}, color ? h("i", { class: "k", style: { background: color } }) : null,
      value != null ? h("b", {}, String(value)) : null, value != null ? " " : null, label));
  }
  el.hidden = false;
  const pad = 14, r = el.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
  el.style.left = `${Math.max(8, x)}px`;
  el.style.top = `${Math.max(8, y)}px`;
}
export const hideTip = () => { tip().hidden = true; };

// Tiny event bus so views can talk (e.g. terminal → map focus).
const bus = new EventTarget();
export const on = (type, fn) => bus.addEventListener(type, (e) => fn(e.detail));
export const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));

export function levenshtein(a, b) {
  const dp = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 1; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      dp[i][j] = Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return dp[a.length][b.length];
}

// Contribution stats over a slice of [dateString, count] pairs.
export function sliceStats(days) {
  let total = 0, active = 0, run = 0, longest = 0, best = null;
  for (const [d, c] of days) {
    total += c;
    if (c) { active++; run++; longest = Math.max(longest, run); } else run = 0;
    if (!best || c > best[1]) best = [d, c];
  }
  return { total, active, longest, best, days: days.length };
}
