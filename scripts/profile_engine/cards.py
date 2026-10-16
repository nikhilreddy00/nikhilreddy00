"""The Agent OS cards: agent trace, latent space map, training run, training history.

GitHub shows README images as plain <img>, so these SVGs can't react to the
mouse. Motion is pure CSS: the trace retypes itself on a loop, the map
drifts, the dashboard draws its curve and counts its numbers up. Everything
also has a complete still frame for prefers-reduced-motion.
"""

from __future__ import annotations

import datetime as dt
import math
import re

from .latent import Cluster, Point
from .metrics import Metrics
from .svg import CATEGORICAL, PALETTES, document, esc, text, text_width

W = 880


def _short_date(d: dt.datetime) -> str:
    return d.strftime("%b %d")


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%" if x >= 0.01 else "<1%"


def _streak_segments(m: Metrics) -> list[tuple[str, str]]:
    if m.current_streak:
        return [("green", str(m.current_streak)), ("fg", "-day streak")]
    if m.last_active:
        return [("fg", "last active "), ("green", m.last_active.strftime("%b %d"))]
    return [("muted", "no recent activity")]


def _pc(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------
# A. Agent trace (hero) — retypes itself every cycle
# --------------------------------------------------------------------------

def agent_trace(m: Metrics, identity: dict, mode: str) -> str:
    p = PALETTES[mode]
    tool, arrow = ("blue", "⚙ tool    "), ("muted", "  ↳ ")
    lines: list[list[tuple[str, str]]] = [
        [("muted", "$ "), ("fg", "nikhil-agent run profile.sync --every 1h")],
        [("purple", "● plan    "), ("muted", "read GitHub → summarize → render this page")],
        [tool, ("fg", "whoami()")],
        [arrow, ("fg", identity["name"]), ("muted", " · "), ("teal", identity["headline"]),
         ("muted", " · "), ("fg", f'{identity["current_role"]} @ {identity["current_org"]}')],
        [tool, ("fg", 'github.repos(sort="pushed", limit=3)')],
    ]
    for r in m.public_repos[:3]:
        lang = {"Jupyter Notebook": "Notebook"}.get(r.language, r.language) or "—"
        lines.append([arrow, ("fg", f"{r.name[:26]:<27}"), ("lang:" + (r.language_color or p["muted"]), "● "),
                      ("muted", f"{lang[:12]:<13}"), ("muted", f"★{r.stars:<3} pushed {_short_date(r.pushed)}")])
    active_30 = sum(1 for _, c in m.days[-30:] if c)
    lines += [
        [tool, ("fg", 'github.activity(window="30d")')],
        [arrow, ("green", f"{m.contributions_30d:,}"), ("fg", " contributions · "), ("green", str(active_30)),
         ("fg", " active days · ")] + _streak_segments(m),
        [tool, ("fg", 'github.languages(by="bytes")')],
        [arrow, ("fg", " · ".join(f"{n} {_pct(s)}" for n, _, s in m.languages[:3] if n != "Other") or "—")],
        [("green", "✓ done    "), ("muted", f"updated {m.generated_at:%Y-%m-%d %H:%M} UTC · next check within the hour")],
    ]

    size, lh, top = 13.5, 23, 64
    height = top + lh * len(lines) + 10
    # Timeline: a tool call "thinks" briefly before its result line lands.
    starts, t = [], 0.4
    for segs in lines:
        starts.append(t)
        t += 0.55 if segs[0] is tool else 0.22
    cycle = t + 9.0  # hold the finished trace, then clear and retype

    body = [
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>',
        f'<circle cx="22" cy="21" r="6" fill="{p["dot_red"]}"/><circle cx="42" cy="21" r="6" fill="{p["dot_yellow"]}"/>'
        f'<circle cx="62" cy="21" r="6" fill="{p["dot_green"]}"/>',
        text(W / 2, 25.5, f"{m.login}@agent: ~/profile", p["muted"], 12, anchor="middle"),
        f'<line x1="0" x2="{W}" y1="41.5" y2="41.5" stroke="{p["line"]}"/>',
    ]
    keyframes = []
    y = top
    for i, segs in enumerate(lines):
        a = starts[i] / cycle * 100
        b = (starts[i] + 0.18) / cycle * 100
        keyframes.append(f"@keyframes t{i}{{0%,{_pc(a)}%{{opacity:0}}{_pc(b)}%,97%{{opacity:1}}100%{{opacity:0}}}}")
        spans = []
        for color, s in segs:
            fill = color[5:] if color.startswith("lang:") else p[color]
            spans.append(f'<tspan fill="{fill}">{esc(s)}</tspan>')
        body.append(f'<text class="l" style="animation-name:t{i}" x="24" y="{y}" '
                    f'font-size="{size}" xml:space="preserve">{"".join(spans)}</text>')
        y += lh
    last_w = sum(len(s) for _, s in lines[-1]) * size * 0.602
    body.append(f'<g class="l" style="animation-name:t{len(lines) - 1}">'
                f'<rect class="cur" x="{24 + last_w + 4:.1f}" y="{y - lh - 12}" width="8" height="15" fill="{p["fg"]}"/></g>')
    style = (f".l{{opacity:0;animation-duration:{cycle:.2f}s;animation-timing-function:linear;animation-iteration-count:infinite}}"
             ".cur{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
             + "".join(keyframes)
             + "@media (prefers-reduced-motion: reduce){.l,.cur{animation:none!important;opacity:1}}")
    return document(W, height, "".join(body), f"{m.login} agent trace: latest repos and activity", style)


# --------------------------------------------------------------------------
# B. Latent space map — points drift, regions breathe
# --------------------------------------------------------------------------

def _overlaps(box, boxes, pad=3):
    x0, y0, x1, y1 = box
    return any(not (x1 + pad < a or x0 - pad > c or y1 + pad < b or y0 - pad > d) for a, b, c, d in boxes)


def latent_map(points: list[Point], clusters: list[Cluster], m: Metrics, mode: str) -> str:
    p = PALETTES[mode]
    H = 470
    left, right, top, bottom = 70, W - 70, 96, H - 64
    X = lambda v: left + v * (right - left)
    Y = lambda v: top + (1 - v) * (bottom - top)

    rank = {pt.repo.name: i for i, pt in enumerate(sorted(points, key=lambda q: q.repo.pushed, reverse=True))}
    n = len(points)
    color_of = {j: p[CATEGORICAL[j % len(CATEGORICAL)]] for j in range(len(clusters))}

    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{p["bg"]}" stroke="{p["line"]}"/>',
            text(24, 32, "latent space", p["fg"], 15, 700),
            text(24 + text_width("latent space ", 15), 32,
                 f"{n} public repos, embedded from READMEs + topics, {len(clusters)} clusters", p["muted"], 12),
            text(W - 24, 32, "● newest", p["muted"], 12, anchor="end")]
    boxes = []

    # Soft cluster regions and their labels.
    for j, c in enumerate(clusters):
        pts = [pt for pt in points if pt.cluster == j]
        if not pts:
            continue
        xs, ys = [X(pt.x) for pt in pts], [Y(pt.y) for pt in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        rx = max(max(abs(x - cx) for x in xs) + 34, 46)
        ry = max(max(abs(y - cy) for y in ys) + 28, 34)
        body.append(f'<ellipse class="br" style="animation-delay:-{j * 1.3:.1f}s" cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" '
                    f'fill="{color_of[j]}" fill-opacity="0.09" stroke="{color_of[j]}" stroke-opacity="0.25" stroke-dasharray="3 4"/>')
        label = c.label
        lw = text_width(label, 12)
        ly = max(cy - ry - 8, top - 22)
        lx = min(max(cx, left - 40 + lw / 2), right + 40 - lw / 2)
        box = (lx - lw / 2, ly - 11, lx + lw / 2, ly + 3)
        for _ in range(8):
            if not _overlaps(box, boxes):
                break
            ly -= 14
            box = (lx - lw / 2, ly - 11, lx + lw / 2, ly + 3)
        boxes.append(box)
        body.append(text(lx, ly, label, color_of[j], 12, 700, anchor="middle"))

    # Each point and its label share a drift animation so they move together.
    def drift(name: str) -> str:
        k = sum(map(ord, name))
        return f'class="d{k % 4}" style="animation-delay:-{(k % 37) / 4:.2f}s"'

    marks, labels, radius = [], [], {}
    for pt in sorted(points, key=lambda q: -rank[q.repo.name]):
        x, y = X(pt.x), Y(pt.y)
        k = rank[pt.repo.name]
        r = radius[pt.repo.name] = 3.5 + 4.5 * (1 - k / max(n - 1, 1))
        col = color_of[pt.cluster]
        glow = (f'<circle class="glow" cx="{x:.1f}" cy="{y:.1f}" r="{r + 7:.1f}" fill="{col}" fill-opacity="0.35"/>'
                if k == 0 else "")
        marks.append(f'<g {drift(pt.repo.name)}>{glow}<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{col}" '
                     f'stroke="{p["bg"]}" stroke-width="1.5"/></g>')
        boxes.append((x - r, y - r, x + r, y + r))

    for pt in sorted(points, key=lambda q: rank[q.repo.name])[:14]:
        x, y = X(pt.x), Y(pt.y)
        name = pt.repo.name if len(pt.repo.name) <= 28 else pt.repo.name[:27] + "…"
        tw, gap = text_width(name, 11), radius[pt.repo.name] + 5
        for dx, dy, anchor in ((gap, 4, "start"), (-gap, 4, "end"), (0, -gap - 2, "middle"), (0, gap + 9, "middle")):
            x0 = x + dx if anchor == "start" else x + dx - tw if anchor == "end" else x - tw / 2
            box = (x0, y + dy - 9, x0 + tw, y + dy + 2)
            if x0 < 8 or x0 + tw > W - 8 or _overlaps(box, boxes, 2):
                continue
            boxes.append(box)
            labels.append(f'<g {drift(pt.repo.name)}>{text(x + dx, y + dy, name, p["fg"], 11, anchor=anchor)}</g>')
            break

    body += marks + labels
    body.append(text(24, H - 22, "TF-IDF → LSA → k-means (k picked by silhouette) → PCA", p["faint"], 11))
    body.append(text(W - 24, H - 22, f"recomputed {m.generated_at:%Y-%m-%d}", p["faint"], 11, anchor="end"))
    orbits = [((2, -3), (-1, -5), (-3, -2)), ((-3, 2), (-5, -1), (-2, 3)),
              ((3, 2), (1, 4), (-2, 1)), ((-2, -3), (2, -4), (3, -1))]
    style = "".join(
        f"@keyframes d{i}{{0%,100%{{transform:translate(0,0)}}"
        + "".join(f"{q}%{{transform:translate({a}px,{b}px)}}" for q, (a, b) in zip((25, 50, 75), o)) + "}"
        f".d{i}{{animation:d{i} {8 + i * 1.7:.1f}s ease-in-out infinite}}"
        for i, o in enumerate(orbits)
    )
    style += (".br{transform-box:fill-box;transform-origin:center;animation:br 9s ease-in-out infinite}"
              "@keyframes br{50%{transform:scale(1.035)}}"
              ".glow{animation:pulse 2.4s ease-in-out infinite}@keyframes pulse{50%{fill-opacity:.08}}"
              "@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
    return document(W, H, "".join(body), "Map of public repositories clustered by topic", style)


# --------------------------------------------------------------------------
# D. Training run — curve draws itself, numbers count up
# --------------------------------------------------------------------------

def _nice_max(v: float) -> int:
    if v <= 4:
        return 4
    mag = 10 ** math.floor(math.log10(v))
    for step in (1, 2, 2.5, 5, 10):
        if step * mag >= v:
            return int(math.ceil(step * mag))
    return int(v)


COUNT_FRAMES = 12
COUNT_DUR, COUNT_DELAY = 1.6, 0.5


def _count_up_style() -> str:
    css = []
    for k in range(COUNT_FRAMES):
        a = k / COUNT_FRAMES * 100
        b = (k + 1) / COUNT_FRAMES * 100
        if k < COUNT_FRAMES - 1:
            css.append(f"@keyframes c{k}{{0%,{_pc(a)}%{{opacity:0}}{_pc(a + .01)}%,{_pc(b)}%{{opacity:1}}{_pc(b + .01)}%,100%{{opacity:0}}}}")
        else:
            css.append(f"@keyframes c{k}{{0%,{_pc(a)}%{{opacity:0}}{_pc(a + .01)}%,100%{{opacity:1}}}}")
        css.append(f".c{k}{{animation:c{k} {COUNT_DUR}s linear {COUNT_DELAY}s both}}")
    return ".cf{opacity:0}" + "".join(css)


def _count_up(x: float, y: float, value: str, fill: str, size: int) -> str:
    """Stack of frames that tick from 0 to the value; non-numeric values just fade in."""
    match = re.fullmatch(r"([\d,]+)(.*)", value)
    if not match:
        return f'<g class="c{COUNT_FRAMES - 1}">{text(x, y, value, fill, size, 700)}</g>'
    target, suffix = int(match.group(1).replace(",", "")), match.group(2)
    out = []
    for k in range(COUNT_FRAMES):
        t = (k + 1) / COUNT_FRAMES
        v = round(target * (1 - (1 - t) ** 3))   # ease-out
        cls = f"c{k}" + ("" if k == COUNT_FRAMES - 1 else " cf")
        out.append(f'<g class="{cls}">{text(x, y, f"{v:,}{suffix}", fill, size, 700)}</g>')
    return "".join(out)


def training_run(m: Metrics, mode: str) -> str:
    p = PALETTES[mode]
    H = 360
    draw = 2.2  # seconds for the curve to draw
    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>']

    body.append(text(24, 34, f"run: {m.login}/career", p["fg"], 15, 700))
    body.append(text(24 + text_width(f"run: {m.login}/career  ", 15), 34,
                     f"step {m.lifetime_contributions:,}  (lifetime contributions)", p["muted"], 12))
    status, scol = ("running", p["green"]) if m.running else ("idle", p["muted"])
    body.append(f'<circle class="{"glow" if m.running else ""}" cx="{W - 24 - text_width(status, 12) - 14:.1f}" cy="30" r="5" fill="{scol}"/>')
    body.append(text(W - 24, 34, status, scol, 12, 600, anchor="end"))

    # Activity curve
    cx0, cx1, cy0, cy1 = 52, 560, 78, 208
    counts = [c for _, c in m.days]
    ymax = _nice_max(max(counts) if counts else 1)
    X = lambda i: cx0 + i * (cx1 - cx0) / max(len(counts) - 1, 1)
    Y = lambda v: cy1 - v / ymax * (cy1 - cy0)
    body.append(text(cx0 - 28, 62, "contributions / day · last 90 days · smoothed line = EMA", p["muted"], 11))
    for v in (0, ymax // 2, ymax):
        body.append(f'<line x1="{cx0}" x2="{cx1}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{p["grid"]}"/>')
        body.append(text(cx0 - 8, Y(v) + 4, str(v), p["faint"], 10, anchor="end"))
    if counts:
        pts = " ".join(f"L{X(i):.1f},{Y(c):.1f}" for i, c in enumerate(counts))
        body.append(f'<path class="area" d="M{X(0):.1f},{cy1} {pts} L{X(len(counts) - 1):.1f},{cy1} Z" fill="{p["teal"]}" fill-opacity="0.18"/>')
        ema, smooth = counts[0], []
        for c in counts:
            ema = 0.85 * ema + 0.15 * c
            smooth.append(ema)
        line = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(smooth))
        body.append(f'<path class="curve" pathLength="1" d="{line}" fill="none" stroke="{p["teal"]}" stroke-width="2.2" stroke-linejoin="round"/>')
        body.append(f'<circle class="pop" style="animation-delay:{draw:.2f}s" cx="{X(len(counts) - 1):.1f}" cy="{Y(smooth[-1]):.1f}" r="3.5" fill="{p["teal"]}"/>')
        for i, (d, _) in enumerate(m.days):
            if d.day == 1:
                body.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{cy1}" y2="{cy1 + 4}" stroke="{p["faint"]}"/>')
                body.append(text(X(i), cy1 + 16, d.strftime("%b"), p["faint"], 10, anchor="middle"))
        # Checkpoints pop in as the curve reaches them.
        first = m.days[0][0]
        shown = {cp.name for cp in m.checkpoints[-3:]}
        k = 0
        for cp in reversed(m.checkpoints):
            i = (cp.created.date() - first).days
            if not 0 <= i < len(counts):
                continue
            x = X(i)
            delay = 0.3 + draw * i / len(counts)
            mark = (f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{cy0}" y2="{cy1}" stroke="{p["purple"]}" stroke-dasharray="2 3" stroke-opacity="0.8"/>'
                    f'<path d="M{x:.1f},{cy0 - 5} l5,5 l-5,5 l-5,-5 Z" fill="{p["purple"]}"/>')
            if cp.name in shown:
                label = cp.name if len(cp.name) <= 22 else cp.name[:21] + "…"
                anchor = "end" if x > cx1 - 120 else "start"
                mark += text(x + (-8 if anchor == "end" else 8), cy0 + 12 + k * 14, label, p["purple"], 10, anchor=anchor)
                k += 1
            body.append(f'<g class="pop" style="animation-delay:{delay:.2f}s">{mark}</g>')

    # Language mix: bars grow in.
    lx0, lx1 = 610, W - 28
    body.append(text(lx0, 62, "language mix · bytes of code", p["muted"], 11))
    for k, (name, color, share) in enumerate(m.languages[:6]):
        y = 84 + k * 22
        body.append(text(lx0, y, name, p["fg"], 11))
        body.append(text(lx1, y, _pct(share), p["muted"], 11, anchor="end"))
        body.append(f'<rect x="{lx0}" y="{y + 4}" width="{lx1 - lx0}" height="5" rx="2.5" fill="{p["grid"]}"/>')
        body.append(f'<rect class="grow" style="animation-delay:{0.2 + k * 0.12:.2f}s" x="{lx0}" y="{y + 4}" '
                    f'width="{max(3, (lx1 - lx0) * share):.1f}" height="5" rx="2.5" fill="{color}"/>')
    if m.languages_excluded:
        names = ", ".join("notebooks" if n == "Jupyter Notebook" else n for n in m.languages_excluded)
        body.append(text(lx0, 84 + min(len(m.languages), 6) * 22 + 2, f"excludes {names}", p["faint"], 10))

    # Stat tiles
    delta = m.contributions_30d - m.contributions_prev_30d
    if m.contributions_prev_30d:
        dtxt = f"{delta / m.contributions_prev_30d:+.0%} vs prior 30d"
    else:
        dtxt = "first active month" if m.contributions_30d else "quiet month"
    dcol = p["green"] if delta > 0 else p["red"] if delta < 0 else p["muted"]
    tiles = [
        ("contributions · 30d", f"{m.contributions_30d:,}", dtxt, dcol),
        ("current streak", f"{m.current_streak} day{'s' if m.current_streak != 1 else ''}", f"longest (1y): {m.longest_streak_year}", p["muted"])
        if m.current_streak or not m.last_active else
        ("last active", m.last_active.strftime("%b %d"), f"longest streak (1y): {m.longest_streak_year}", p["muted"]),
        ("active days · 90d", f"{m.active_days_90d}/90", f"{m.active_days_90d / 90:.0%} of days", p["muted"]),
        (f"repos created · {m.generated_at.year}", str(m.repos_created_this_year), "public + private", p["muted"]),
        ("lifetime contributions", f"{m.lifetime_contributions:,}", "all years on GitHub", p["muted"]),
    ]
    gap, tx = 12, 24
    tw = (W - 48 - gap * (len(tiles) - 1)) / len(tiles)
    for label, value, sub, subcol in tiles:
        body.append(f'<rect x="{tx:.1f}" y="250" width="{tw:.1f}" height="86" rx="8" fill="{p["bg"]}" stroke="{p["line"]}"/>')
        body.append(text(tx + 12, 272, label, p["muted"], 10.5))
        body.append(_count_up(tx + 12, 304, value, p["fg"], 24))
        body.append(text(tx + 12, 324, sub, subcol, 10.5))
        tx += tw + gap

    style = (f".curve{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw {draw}s ease-out .3s forwards}}"
             "@keyframes draw{to{stroke-dashoffset:0}}"
             ".area{opacity:0;animation:fade 1.2s ease-out 1.2s forwards}@keyframes fade{to{opacity:1}}"
             ".pop{opacity:0;animation:fade .4s ease-out forwards}"
             ".grow{transform-box:fill-box;transform-origin:left;transform:scaleX(0);animation:grow .9s ease-out forwards}"
             "@keyframes grow{to{transform:scaleX(1)}}"
             ".glow{animation:pulse 2s ease-in-out infinite}@keyframes pulse{50%{opacity:.35}}"
             + _count_up_style()
             + "@media (prefers-reduced-motion: reduce){*{animation:none!important}"
               ".curve{stroke-dashoffset:0}.area,.pop{opacity:1}.grow{transform:none}"
               f".c{COUNT_FRAMES - 1}{{opacity:1}}}}")
    return document(W, H, "".join(body), f"{m.login} activity dashboard", style)


# --------------------------------------------------------------------------
# E. Training history — 12-month drill-down
# --------------------------------------------------------------------------

def training_history(m: Metrics, mode: str) -> str:
    p = PALETTES[mode]
    H = 200
    year = m.year
    total = sum(c for _, c in year)
    active = sum(1 for _, c in year if c)

    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>',
            text(24, 34, "training history", p["fg"], 15, 700),
            text(24 + text_width("training history  ", 15), 34,
                 f"{total:,} contributions · {active} active days · last 12 months", p["muted"], 12)]

    # Calendar heatmap: weeks as columns, Monday on top.
    cell, gap, gx, gy = 10, 2.5, 52, 72
    nonzero = sorted(c for _, c in year if c)
    q = [nonzero[int(len(nonzero) * f)] for f in (0.25, 0.5, 0.75)] if nonzero else [1, 2, 3]
    level = lambda c: 0 if not c else 1 + sum(c > t for t in q)
    opacity = [0, 0.3, 0.5, 0.75, 1.0]
    first = year[0][0] if year else dt.date.today()
    offset = first.weekday()
    weeks = (offset + len(year) + 6) // 7
    for i, (d, c) in enumerate(year):
        col, row = (offset + i) // 7, d.weekday()
        x, y = gx + col * (cell + gap), gy + row * (cell + gap)
        lv = level(c)
        fill = p["grid"] if lv == 0 else p["teal"]
        op = "" if lv == 0 else f' fill-opacity="{opacity[lv]}"'
        body.append(f'<rect class="wave" style="animation-delay:{col * 0.025:.3f}s" x="{x:.1f}" y="{y:.1f}" width="{cell}" height="{cell}" rx="2" fill="{fill}"{op}/>')
        if d.day == 1:
            body.append(text(x, gy - 8, d.strftime("%b"), p["faint"], 10))
    for row, name in ((0, "Mon"), (2, "Wed"), (4, "Fri"), (6, "Sun")):
        body.append(text(gx - 8, gy + row * (cell + gap) + 9, name, p["faint"], 9.5, anchor="end"))
    grid_right = gx + weeks * (cell + gap)
    ly = gy + 7 * (cell + gap) + 18
    body.append(text(gx, ly, "less", p["faint"], 10))
    for lv in range(5):
        fill = p["grid"] if lv == 0 else p["teal"]
        op = "" if lv == 0 else f' fill-opacity="{opacity[lv]}"'
        body.append(f'<rect x="{gx + 30 + lv * 14}" y="{ly - 9}" width="10" height="10" rx="2" fill="{fill}"{op}/>')
    body.append(text(gx + 30 + 5 * 14 + 4, ly, "more", p["faint"], 10))

    # Weekday profile: when the work happens.
    wx0 = max(grid_right + 36, 720)
    body.append(text(wx0, 62, "by weekday", p["muted"], 11))
    by_day = [0] * 7
    for d, c in year:
        by_day[d.weekday()] += c
    peak = max(by_day) or 1
    for row, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        y = gy + row * (cell + gap)
        bw = (W - 28 - wx0 - 34) * by_day[row] / peak
        body.append(text(wx0, y + 9, name, p["faint"], 9.5))
        body.append(f'<rect class="grow" style="animation-delay:{0.4 + row * 0.08:.2f}s" x="{wx0 + 30}" y="{y + 1}" '
                    f'width="{max(bw, 2):.1f}" height="{cell - 2}" rx="2" fill="{p["purple"]}" fill-opacity="0.8"/>')
    busiest = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][by_day.index(peak)]
    body.append(text(wx0, ly, f"busiest: {busiest}" if total else "no activity yet", p["faint"], 10))

    style = (".wave{opacity:0;animation:fade .5s ease-out forwards}@keyframes fade{to{opacity:1}}"
             ".grow{transform-box:fill-box;transform-origin:left;transform:scaleX(0);animation:grow .8s ease-out forwards}"
             "@keyframes grow{to{transform:scaleX(1)}}"
             "@media (prefers-reduced-motion: reduce){*{animation:none!important}.wave{opacity:1}.grow{transform:none}}")
    return document(W, H, "".join(body), f"{m.login} contributions over the last 12 months", style)
