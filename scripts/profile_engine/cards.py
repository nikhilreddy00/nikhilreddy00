"""The three Agent OS cards: agent trace, latent space map, training run."""

from __future__ import annotations

import datetime as dt
import math

from .latent import Cluster, Point
from .metrics import Metrics
from .svg import CATEGORICAL, PALETTES, document, esc, text, text_width

W = 880
REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}.l{opacity:1}}"


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


# --------------------------------------------------------------------------
# A. Agent trace (hero)
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
    body = [
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>',
        f'<circle cx="22" cy="21" r="6" fill="{p["dot_red"]}"/><circle cx="42" cy="21" r="6" fill="{p["dot_yellow"]}"/>'
        f'<circle cx="62" cy="21" r="6" fill="{p["dot_green"]}"/>',
        text(W / 2, 25.5, f"{m.login}@agent: ~/profile", p["muted"], 12, anchor="middle"),
        f'<line x1="0" x2="{W}" y1="41.5" y2="41.5" stroke="{p["line"]}"/>',
    ]
    y = top
    for i, segs in enumerate(lines):
        spans = []
        for color, s in segs:
            fill = color[5:] if color.startswith("lang:") else p[color]
            spans.append(f'<tspan fill="{fill}">{esc(s)}</tspan>')
        body.append(f'<text class="l" style="animation-delay:{0.12 + i * 0.22:.2f}s" x="24" y="{y}" '
                    f'font-size="{size}" xml:space="preserve">{"".join(spans)}</text>')
        y += lh
    last_w = sum(len(s) for _, s in lines[-1]) * size * 0.602
    body.append(f'<rect class="cur" x="{24 + last_w + 4:.1f}" y="{y - lh - 12}" width="8" height="15" fill="{p["fg"]}"/>')
    style = (".l{opacity:0;animation:in .35s ease-out forwards}"
             "@keyframes in{to{opacity:1}}"
             f".cur{{opacity:0;animation:in .1s {0.12 + len(lines) * 0.22:.2f}s forwards,blink 1.1s {0.12 + len(lines) * 0.22:.2f}s steps(1) infinite}}"
             "@keyframes blink{50%{opacity:0}}" + REDUCED)
    return document(W, height, "".join(body), f"{m.login} agent trace: latest repos and activity", style)


# --------------------------------------------------------------------------
# B. Latent space map
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
        body.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{color_of[j]}" fill-opacity="0.09" '
                    f'stroke="{color_of[j]}" stroke-opacity="0.25" stroke-dasharray="3 4"/>')
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

    # Points, newest drawn last so they sit on top.
    marks, labels, radius = [], [], {}
    for pt in sorted(points, key=lambda q: -rank[q.repo.name]):
        x, y = X(pt.x), Y(pt.y)
        k = rank[pt.repo.name]
        r = radius[pt.repo.name] = 3.5 + 4.5 * (1 - k / max(n - 1, 1))
        col = color_of[pt.cluster]
        if k == 0:
            marks.append(f'<circle class="glow" cx="{x:.1f}" cy="{y:.1f}" r="{r + 7:.1f}" fill="{col}" fill-opacity="0.35"/>')
        marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{col}" stroke="{p["bg"]}" stroke-width="1.5"/>')
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
            labels.append(text(x + dx, y + dy, name, p["fg"], 11, anchor=anchor))
            break

    body += marks + labels
    body.append(text(24, H - 22, "TF-IDF → LSA → k-means (k picked by silhouette) → PCA", p["faint"], 11))
    body.append(text(W - 24, H - 22, f"recomputed {m.generated_at:%Y-%m-%d}", p["faint"], 11, anchor="end"))
    style = ".glow{animation:pulse 2.4s ease-in-out infinite}@keyframes pulse{50%{fill-opacity:.08}}" + REDUCED
    return document(W, H, "".join(body), "Map of public repositories clustered by topic", style)


# --------------------------------------------------------------------------
# D. Training run (stats strip)
# --------------------------------------------------------------------------

def _nice_max(v: float) -> int:
    if v <= 4:
        return 4
    mag = 10 ** math.floor(math.log10(v))
    for step in (1, 2, 2.5, 5, 10):
        if step * mag >= v:
            return int(math.ceil(step * mag))
    return int(v)


def training_run(m: Metrics, mode: str) -> str:
    p = PALETTES[mode]
    H = 360
    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>']

    # Header
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
        body.append(f'<path d="M{X(0):.1f},{cy1} {pts} L{X(len(counts) - 1):.1f},{cy1} Z" fill="{p["teal"]}" fill-opacity="0.18"/>')
        ema, smooth = counts[0], []
        for c in counts:
            ema = 0.85 * ema + 0.15 * c
            smooth.append(ema)
        line = " ".join(f"{'M' if i == 0 else 'L'}{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(smooth))
        body.append(f'<path d="{line}" fill="none" stroke="{p["teal"]}" stroke-width="2.2" stroke-linejoin="round"/>')
        body.append(f'<circle cx="{X(len(counts) - 1):.1f}" cy="{Y(smooth[-1]):.1f}" r="3.5" fill="{p["teal"]}"/>')
        # Month ticks
        for i, (d, _) in enumerate(m.days):
            if d.day == 1:
                body.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{cy1}" y2="{cy1 + 4}" stroke="{p["faint"]}"/>')
                body.append(text(X(i), cy1 + 16, d.strftime("%b"), p["faint"], 10, anchor="middle"))
        # Checkpoints: public repos created inside the window
        first = m.days[0][0]
        shown = m.checkpoints[-3:]
        for cp in m.checkpoints:
            i = (cp.created.date() - first).days
            if not 0 <= i < len(counts):
                continue
            x = X(i)
            body.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{cy0}" y2="{cy1}" stroke="{p["purple"]}" stroke-dasharray="2 3" stroke-opacity="0.8"/>')
            body.append(f'<path d="M{x:.1f},{cy0 - 5} l5,5 l-5,5 l-5,-5 Z" fill="{p["purple"]}"/>')
        for k, cp in enumerate(reversed(shown)):
            i = (cp.created.date() - first).days
            if 0 <= i < len(counts):
                label = cp.name if len(cp.name) <= 22 else cp.name[:21] + "…"
                anchor = "end" if X(i) > cx1 - 120 else "start"
                body.append(text(X(i) + (-8 if anchor == "end" else 8), cy0 + 12 + k * 14, label, p["purple"], 10, anchor=anchor))

    # Language mix
    lx0, lx1 = 610, W - 28
    body.append(text(lx0, 62, "language mix · bytes of code", p["muted"], 11))
    for k, (name, color, share) in enumerate(m.languages[:6]):
        y = 84 + k * 22
        body.append(text(lx0, y, name, p["fg"], 11))
        body.append(text(lx1, y, _pct(share), p["muted"], 11, anchor="end"))
        body.append(f'<rect x="{lx0}" y="{y + 4}" width="{lx1 - lx0}" height="5" rx="2.5" fill="{p["grid"]}"/>')
        body.append(f'<rect x="{lx0}" y="{y + 4}" width="{max(3, (lx1 - lx0) * share):.1f}" height="5" rx="2.5" fill="{color}"/>')
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
        body.append(text(tx + 12, 304, value, p["fg"], 24, 700))
        body.append(text(tx + 12, 324, sub, subcol, 10.5))
        tx += tw + gap

    style = ".glow{animation:pulse 2s ease-in-out infinite}@keyframes pulse{50%{opacity:.35}}" + REDUCED
    return document(W, H, "".join(body), f"{m.login} activity dashboard", style)
