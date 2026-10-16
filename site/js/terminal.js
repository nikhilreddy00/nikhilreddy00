// The terminal: a small shell over the profile data, live GitHub events and
// repos' READMEs. Output is built from DOM nodes (textContent only).

import { $, h, ago, emit, fmtNum, fmtShort, levenshtein, parseDay, safeUrl, sliceStats } from "./util.js";
import { describe, poll } from "./live.js";

const SPARK = "▁▂▃▄▅▆▇█";
const pad = (s, n) => String(s).padEnd(n);

export function createTerminal(data) {
  const out = $("#term-out"), body = $("#term-body"), input = $("#term-input"), form = $("#term-form");
  const login = data.login;
  const repos = [...data.repos].sort((a, b) => b.pushed.localeCompare(a.pushed));
  const byName = new Map(repos.map((r) => [r.name.toLowerCase(), r]));
  const history = [];
  let hIdx = 0, busy = false;

  // ---- output primitives -------------------------------------------------
  const span = (cls, text) => h("span", { class: cls }, text);
  const link = (text, fn, title) => h("button", { class: "t-link", type: "button", onclick: fn, title }, text);
  const cmdLink = (text, cmd) => link(text, () => run(cmd), `run: ${cmd}`);
  const ext = (text, url) => h("a", { class: "t-link", href: safeUrl(url), target: "_blank", rel: "noopener" }, text);
  const scroll = () => { body.scrollTop = body.scrollHeight; };
  function print(...segs) {
    const ln = h("div", { class: "ln" }, ...segs.map((s) => (typeof s === "string" ? s : s)));
    out.append(ln);
    scroll();
    return ln;
  }
  const blank = () => print("");
  const err = (msg) => print(span("t-bad", msg));

  function resolveRepo(arg) {
    if (!arg) return { error: "usage: needs a repo name. Try `ls` to see them." };
    const key = arg.toLowerCase().replace(/\/$/, "");
    if (byName.has(key)) return { repo: byName.get(key) };
    const pre = repos.filter((r) => r.name.toLowerCase().startsWith(key));
    if (pre.length === 1) return { repo: pre[0] };
    const near = repos.map((r) => [r, levenshtein(key, r.name.toLowerCase())]).sort((a, b) => a[1] - b[1]);
    return { error: `no repo named "${arg}"`, suggest: (pre.length ? pre : near.slice(0, 3).map((x) => x[0])).slice(0, 3) };
  }
  function repoError(res, verb) {
    err(res.error);
    if (res.suggest?.length) print(span("t-mut", "did you mean: "), ...res.suggest.flatMap((r, i) => [i ? ", " : "", cmdLink(r.name, `${verb} ${r.name}`)]));
  }
  const repoLink = (r, width = 0) => {
    const el = cmdLink(r.name, `cat ${r.name}`);
    return width ? [el, " ".repeat(Math.max(1, width - r.name.length))] : [el];
  };
  const clusterOf = (r) => data.clusters.find((c) => c.id === r.cluster);

  // ---- commands ----------------------------------------------------------
  const commands = {
    help: { desc: "list commands", run() {
      print(span("t-b", "Commands"), span("t-mut", "  (tap any to run it)"));
      for (const [name, c] of Object.entries(commands)) {
        if (c.hidden) continue;
        print("  ", cmdLink(pad(name, 12), c.example || name), span("t-mut", c.desc));
      }
      print(span("t-faint", "  Tab completes · ↑/↓ history · Ctrl+L clears"));
    } },
    whoami: { desc: "who is Nikhil", run() {
      const id = data.identity;
      print(span("t-b t-acc", id.name), span("t-mut", " · "), span("t-cmd", id.headline), span("t-mut", " · "), `${id.current_role} @ ${id.current_org}`);
      print(span("t-mut", id.summary));
      print(span("t-faint", "next: "), cmdLink("experience", "experience"), "  ", cmdLink("ls", "ls"), "  ", cmdLink("stats", "stats"), "  ", cmdLink("contact", "contact"));
    } },
    ls: { desc: "list projects (ls -l for details, ls featured)", example: "ls", run(args) {
      const long = args.includes("-l") || args.includes("-la");
      let list = repos.filter((r) => !r.archived);
      if (args.includes("featured")) list = list.filter((r) => r.featured);
      const w = Math.min(30, Math.max(...list.map((r) => r.name.length)) + 2);
      for (const r of list) {
        print(...repoLink(r, w), span("t-mut", pad(r.language || "—", 18)), span("t-yel", pad(r.stars ? `★${r.stars}` : "", 5)), span("t-faint", `pushed ${ago(r.pushed)}`));
        if (long && r.description) print(" ".repeat(2), span("t-mut", r.description));
      }
      print(span("t-faint", `${list.length} repositories · tap a name to read its README`));
    } },
    cat: { desc: "read a project's README", example: "cat praxis", async run(args) {
      const res = resolveRepo(args[0]);
      if (!res.repo) return repoError(res, "cat");
      const r = res.repo, cl = clusterOf(r);
      print(span("t-b t-acc", r.name), span("t-mut", ` · ${r.language || "—"} · ★${r.stars} · pushed ${ago(r.pushed)}${cl ? ` · ${cl.label}` : ""}`));
      if (r.description) print(r.description);
      if (r.topics?.length) print(span("t-pur", r.topics.map((t) => `#${t}`).join(" ")));
      const loading = print(span("t-faint", "fetching README…"));
      try {
        const res2 = await fetch(`https://raw.githubusercontent.com/${login}/${r.name}/HEAD/README.md`);
        if (!res2.ok) throw new Error(res2.status === 404 ? "no README.md in this repo" : `HTTP ${res2.status}`);
        const lines = cleanReadme(await res2.text());
        loading.remove();
        print(span("t-faint", "─".repeat(48)));
        for (const l of lines.slice(0, 40)) print(/^#{1,6}\s/.test(l) ? span("t-b", l.replace(/^#+\s*/, "")) : l);
        if (lines.length > 40) print(span("t-faint", `… ${lines.length - 40} more lines`));
      } catch (e) {
        loading.replaceChildren(span("t-bad", `couldn't load README: ${e.message}`));
      }
      print(span("t-faint", "next: "), cmdLink(`open ${r.name}`, `open ${r.name}`), "  ", cmdLink(`map ${r.name}`, `map ${r.name}`));
    } },
    open: { desc: "open a repo, linkedin, github or email", example: "open praxis", run(args) {
      const t = (args[0] || "").toLowerCase();
      const id = data.identity;
      const go = (url, label) => { if (safeUrl(url) === "#") return err("blocked: not a web link"); window.open(safeUrl(url), "_blank", "noopener"); print(span("t-mut", "opening "), ext(label, url)); };
      if (t === "linkedin") return go(id.linkedin, "LinkedIn");
      if (t === "github") return go(`https://github.com/${login}`, `github.com/${login}`);
      if (t === "email" || t === "mail") return print(span("t-mut", "email: "), ext(id.email, `mailto:${id.email}`));
      const res = resolveRepo(args[0]);
      if (!res.repo) return repoError(res, "open");
      go(res.repo.url, res.repo.url.replace("https://", ""));
    } },
    grep: { desc: "search projects by text or topic", example: "grep rag", run(args) {
      const term = args.join(" ").trim();
      if (!term) return err("usage: grep <term>");
      const q = term.toLowerCase();
      const hits = repos.filter((r) => [r.name, r.description, ...(r.topics || []), clusterOf(r)?.label || ""].join(" ").toLowerCase().includes(q));
      if (!hits.length) return print(span("t-mut", `no matches for "${term}"`));
      const w = Math.min(30, Math.max(...hits.map((r) => r.name.length)) + 2);
      for (const r of hits) print(...repoLink(r, w), ...highlight(r.description || (r.topics || []).join(" "), q));
      print(span("t-faint", `${hits.length} match${hits.length === 1 ? "" : "es"}`));
    } },
    stats: { desc: "activity stats (stats 30 | 90 | 365)", example: "stats 90", run(args) {
      const n = [30, 90, 365].includes(+args[0]) ? +args[0] : 90;
      const days = data.calendar.slice(-n), s = sliceStats(days);
      print(span("t-b", `last ${n} days`), span("t-faint", `  (data as of ${ago(data.generated_at)})`));
      print(pad("contributions", 18), span("t-good t-b", fmtNum(s.total)));
      print(pad("active days", 18), span("t-good", `${s.active}`), span("t-mut", ` / ${s.days}`));
      print(pad("longest streak", 18), `${s.longest} day${s.longest === 1 ? "" : "s"}`);
      if (s.best?.[1]) print(pad("busiest day", 18), `${fmtShort(parseDay(s.best[0]))}`, span("t-mut", ` (${s.best[1]})`));
      const weeks = [];
      for (let i = days.length; i > 0; i -= 7) weeks.unshift(days.slice(Math.max(0, i - 7), i).reduce((a, [, c]) => a + c, 0));
      const peak = Math.max(1, ...weeks);
      print(pad("per week", 18), span("t-acc", weeks.map((w) => (w ? SPARK[Math.min(7, Math.floor((w / peak) * 7.99))] : "·")).join("")));
      print(span("t-faint", "more: "), cmdLink("dashboard", "dashboard"), "  ", cmdLink("langs", "langs"));
    } },
    langs: { desc: "language mix by bytes of code", run() {
      for (const l of data.languages) {
        const n = Math.max(1, Math.round(l.share * 30));
        print(pad(l.name, 14), span("t-acc", "█".repeat(n)), span("t-faint", "░".repeat(30 - n)), " ", `${(l.share * 100).toFixed(l.share < 0.01 ? 1 : 0)}%`);
      }
      if (data.languages_excluded?.length) print(span("t-faint", `excludes ${data.languages_excluded.join(", ")}`));
    } },
    clusters: { desc: "topic clusters from the latent space", example: "clusters", run(args) {
      const q = args.join(" ").toLowerCase();
      const list = q ? data.clusters.filter((c) => c.label.toLowerCase().includes(q)) : data.clusters;
      if (!list.length) return err(`no cluster matching "${args.join(" ")}"`);
      for (const c of list) {
        const members = repos.filter((r) => r.cluster === c.id);
        print(cmdLink(c.label, `clusters ${c.label}`), span("t-mut", `  ${members.length} repos · `), span("t-pur", c.terms.slice(0, 5).join(" · ")));
        if (q) for (const r of members) print("  ", ...repoLink(r));
      }
      if (!q) print(span("t-faint", "tap a cluster to list its repos, or "), cmdLink("map", "map"));
    } },
    log: { desc: "live GitHub activity (real time)", async run() {
      const loading = print(span("t-faint", "fetching live events from api.github.com…"));
      const events = (await poll()).map(describe).filter(Boolean).slice(0, 12);
      loading.remove();
      if (!events.length) return print(span("t-mut", "no recent public activity (or the GitHub API rate limit was hit; try again in a bit)"));
      for (const e of events) {
        print(span("t-faint", pad(ago(e.at), 13)), span(e.kind === "push" ? "t-acc" : "t-cmd", e.text));
        if (e.detail) print(" ".repeat(13), span("t-mut", e.detail));
      }
    } },
    experience: { desc: "work history", run() {
      for (const x of data.experience) {
        print(span("t-faint", pad(x.when, 22)), span("t-b", x.role), span("t-mut", ` · ${x.org}`));
        for (const n of x.notes) print(" ".repeat(22), span("t-mut", `– ${n}`));
      }
    } },
    stack: { desc: "tools and technologies", run() {
      for (const [k, v] of Object.entries(data.stack)) print(span("t-acc", pad(`${k}:`, 12)), v);
    } },
    education: { desc: "degrees", run() {
      for (const e of data.education) print(span("t-b", e.degree), span("t-mut", ` · ${e.school} · ${e.year}`));
    } },
    contact: { desc: "how to reach Nikhil", run() {
      const id = data.identity;
      print(pad("linkedin", 10), ext(id.linkedin.replace("https://www.", ""), id.linkedin));
      print(pad("email", 10), ext(id.email, `mailto:${id.email}`));
      print(pad("github", 10), ext(`github.com/${login}`, `https://github.com/${login}`));
    } },
    neofetch: { desc: "system summary", run() {
      const id = data.identity;
      const s = sliceStats(data.calendar);
      const langs = data.languages.slice(0, 3).map((l) => l.name).join(", ");
      const logo = ["   ▄▄▄▄▄▄▄   ", "  █ ▄▄▄▄▄ █  ", "  █ █>_ █ █  ", "  █ ▀▀▀▀▀ █  ", "   ▀▀▀▀▀▀▀   ", "             ", "             "];
      const rows = [
        [span("t-acc t-b", `${login}@agent`)],
        [span("t-faint", "─".repeat(22))],
        [span("t-acc", "role     "), `${id.headline} · ${id.current_role} @ ${id.current_org}`],
        [span("t-acc", "repos    "), `${repos.length} public`],
        [span("t-acc", "activity "), `${fmtNum(s.total)} contributions in 12 months`],
        [span("t-acc", "langs    "), langs],
        [span("t-acc", "uptime   "), `data refreshed ${ago(data.generated_at)}`],
      ];
      rows.forEach((r, i) => print(span("t-acc", logo[i] || " ".repeat(13)), "  ", ...r));
    } },
    map: { desc: "open the latent-space map (map <repo> to focus one)", example: "map", run(args) {
      location.hash = "#map";
      if (args[0]) {
        const res = resolveRepo(args[0]);
        if (!res.repo) return repoError(res, "map");
        setTimeout(() => emit("focus-repo", res.repo.name), 350);
      }
    } },
    dashboard: { desc: "open the dashboard", run() { location.hash = "#dashboard"; } },
    theme: { desc: "theme dark | light | auto", example: "theme light", run(args) {
      const t = args[0];
      if (!["dark", "light", "auto"].includes(t)) return err("usage: theme dark | light | auto");
      emit("theme", t);
      print(span("t-mut", `theme set to ${t}`));
    } },
    history: { desc: "commands you've run", run() { history.forEach((c, i) => print(span("t-faint", pad(i + 1, 4)), cmdLink(c, c))); } },
    clear: { desc: "clear the screen", run() { out.replaceChildren(); } },
    date: { hidden: true, run() { print(new Date().toString()); } },
    echo: { hidden: true, run(args) { print(args.join(" ")); } },
    pwd: { hidden: true, run() { print("/home/visitor"); } },
    uname: { hidden: true, run() { print("Agent OS 2026.10 (GitHub Pages) · data refreshed hourly · live feed every 60 s"); } },
    uptime: { hidden: true, run() { print(`data generated ${ago(data.generated_at)} · live events polling every 60 s`); } },
    sudo: { hidden: true, run(args) {
      if (args.join(" ").toLowerCase().includes("hire")) { print(span("t-good", "access granted.")); return commands.contact.run([]); }
      print(span("t-bad", "visitor is not in the sudoers file."), span("t-mut", " Try "), cmdLink("sudo hire nikhil", "sudo hire nikhil"));
    } },
    rm: { hidden: true, run() { print(span("t-bad", "rm: permission denied"), span("t-mut", " (this profile is read-only, but nice try)")); } },
    exit: { hidden: true, run() { print(span("t-mut", "there's no exit from a good profile. Try "), cmdLink("open linkedin", "open linkedin")); } },
    ll: { hidden: true, run() { return commands.ls.run(["-l"]); } },
  };
  commands.quit = commands.logout = commands.exit;
  commands.man = commands.help;

  function highlight(text, q) {
    const i = text.toLowerCase().indexOf(q);
    const short = text.length > 90 ? text.slice(0, 90) + "…" : text;
    if (i < 0 || i + q.length > short.length) return [span("t-mut", short)];
    return [span("t-mut", short.slice(0, i)), span("t-hl", short.slice(i, i + q.length)), span("t-mut", short.slice(i + q.length))];
  }

  // ---- input handling ----------------------------------------------------
  function tokenize(line) {
    return (line.match(/"[^"]*"|'[^']*'|\S+/g) || []).map((t) => t.replace(/^["']|["']$/g, ""));
  }

  async function run(line, { echo = true } = {}) {
    line = line.trim();
    if (echo) print(span("t-acc", "visitor@nikhil:~$ "), span("t-cmd", line));
    if (!line) return;
    history.push(line);
    hIdx = history.length;
    const [name, ...args] = tokenize(line);
    const cmd = commands[name.toLowerCase()];
    if (!cmd) {
      const best = Object.keys(commands).filter((k) => !commands[k].hidden)
        .map((k) => [k, levenshtein(name.toLowerCase(), k)]).sort((a, b) => a[1] - b[1])[0];
      print(span("t-bad", `command not found: ${name}`), span("t-mut", ". "),
        best && best[1] <= 2 ? [span("t-mut", "did you mean "), cmdLink(best[0], best[0]), span("t-mut", "? ")] : "",
        span("t-mut", "Type "), cmdLink("help", "help"), span("t-mut", "."));
      return;
    }
    busy = true;
    try { await cmd.run(args); } catch (e) { err(`error: ${e.message}`); }
    busy = false;
    blank();
    scroll();
  }

  function complete() {
    const v = input.value;
    const parts = v.split(/\s+/);
    let options;
    if (parts.length <= 1) options = Object.keys(commands).filter((k) => !commands[k].hidden);
    else if (["cat", "open", "map"].includes(parts[0])) options = [...repos.map((r) => r.name), ...(parts[0] === "open" ? ["linkedin", "github", "email"] : [])];
    else if (parts[0] === "clusters") options = data.clusters.map((c) => c.label);
    else if (parts[0] === "stats") options = ["30", "90", "365"];
    else if (parts[0] === "theme") options = ["dark", "light", "auto"];
    else return;
    const cur = parts[parts.length - 1].toLowerCase();
    const matches = options.filter((o) => o.toLowerCase().startsWith(cur));
    if (matches.length === 1) {
      parts[parts.length - 1] = matches[0];
      input.value = parts.join(" ") + " ";
    } else if (matches.length > 1) {
      print(span("t-acc", "visitor@nikhil:~$ "), span("t-cmd", v));
      print(span("t-mut", matches.join("   ")));
      let p = matches[0];
      for (const m of matches) while (!m.toLowerCase().startsWith(p.toLowerCase())) p = p.slice(0, -1);
      parts[parts.length - 1] = p;
      input.value = parts.join(" ");
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (busy) return;
    const v = input.value;
    input.value = "";
    run(v);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Tab") { e.preventDefault(); complete(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (hIdx > 0) input.value = history[--hIdx]; }
    else if (e.key === "ArrowDown") { e.preventDefault(); hIdx = Math.min(history.length, hIdx + 1); input.value = history[hIdx] || ""; }
    else if (e.key.toLowerCase() === "l" && e.ctrlKey) { e.preventDefault(); out.replaceChildren(); }
  });
  body.addEventListener("click", (e) => {
    if (e.target.closest("a, button") || getSelection().toString()) return;
    input.focus({ preventScroll: true });
  });

  // Suggested commands for touch and first-time visitors.
  const chips = ["whoami", "ls", "cat praxis", "stats 90", "log", "grep agent", "clusters", "experience", "neofetch", "contact", "help"];
  $("#term-chips").replaceChildren(...chips.map((c) => h("button", { class: "chip", type: "button", onclick: () => { if (!busy) run(c); } }, c)));

  // Boot: banner, then type `whoami` like a person would.
  async function boot() {
    print(span("t-acc t-b", "Agent OS"), span("t-mut", ` · ${data.identity.name}'s profile, live from GitHub`));
    print(span("t-mut", "Type a command or tap one below. "), cmdLink("help", "help"), span("t-mut", " lists everything."));
    blank();
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!reduce) {
      for (const ch of "whoami") { input.value += ch; await new Promise((r) => setTimeout(r, 90)); }
      await new Promise((r) => setTimeout(r, 250));
      input.value = "";
    }
    await run("whoami");
  }

  return { boot, run, focus: () => input.focus({ preventScroll: true }) };
}

// README → plain lines: drop HTML, images, badges and code fences' noise.
function cleanReadme(md) {
  const lines = md
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<[^>]+>/g, "")
    .split("\n")
    .map((l) => l.replace(/!\[[^\]]*\]\([^)]*\)/g, "").replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/\*\*|__|`/g, "").trimEnd())
    .filter((l) => !/^\s*(\[!\[|---+\s*$|```)/.test(l));
  const outl = [];
  for (const l of lines) if (l.trim() || (outl.length && outl[outl.length - 1].trim())) outl.push(l);
  return outl;
}
