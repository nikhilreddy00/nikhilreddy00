"""Hand-curated story cards, drawn from profile.toml (not from GitHub data):

- career_graph: experience and education as `git log --graph`. Jobs are
  commits on main, degrees are branches that merge back in, and resume
  metrics are green diff chips under each commit.
- stack_pipeline: the toolbox laid out as the stages data flows through.
"""

from __future__ import annotations

import hashlib

from .svg import PALETTES, document, esc, text, text_width

W = 880
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month(ym: str) -> str:
    y, m = ym.split("-")
    return f"{MONTHS[int(m) - 1]} {y}"


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:7]


def _pill(x: float, y: float, label: str, color: str, size: float = 10.5) -> tuple[str, float]:
    w = text_width(label, size) + 12
    svg = (f'<rect x="{x:.1f}" y="{y - 12:.1f}" width="{w:.1f}" height="17" rx="8.5" fill="{color}" fill-opacity="0.12" '
           f'stroke="{color}" stroke-opacity="0.55"/>' + text(x + 6, y, label, color, size, 600))
    return svg, w


def career_graph(config: dict, mode: str) -> str:
    p = PALETTES[mode]
    main_c, edu_c = p["teal"], p["purple"]
    x0, x1, tx = 34, 58, 92  # lane x positions, text start

    rows = []  # (sort_key, kind, payload)
    for e in config.get("experience", []):
        rows.append((e["start"], "job", e))
    first = "9999-99"
    for ed in config.get("education", []):
        if "start" not in ed:
            continue
        rows.append((ed["start"], "edu-start", ed))
        rows.append((ed["end"], "edu-merge", ed))
        first = min(first, ed["start"])
    first = min([first] + [e["start"] for e in config.get("experience", [])])
    rows.append(("0000-00", "init", {"start": first}))
    rows.sort(key=lambda r: (r[0], r[1] != "edu-merge"), reverse=True)

    # Layout: y per row, extra height for impact chips (wrapped).
    y, lay = 74, []
    for key, kind, d in rows:
        chips = d.get("impact", []) if kind == "job" else []
        lines, cur = [], 0.0
        for c in chips:
            w = text_width(f"+ {c}", 10.5) + 14
            if not lines or cur + w > W - tx - 24:
                lines.append([])
                cur = 0.0
            lines[-1].append((c, w))
            cur += w + 6
        h = 34 + len(lines) * 23
        lay.append({"y": y, "kind": kind, "d": d, "chips": lines, "h": h})
        y += h
    H = y + 6

    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>',
            text(24, 32, "career.git", p["fg"], 15, 700),
            text(24 + text_width("career.git  ", 15), 32, "git log --graph --oneline --decorate", p["muted"], 12),
            text(W - 24, 32, "main     education", p["faint"], 11, anchor="end"),
            f'<circle cx="{W - 24 - text_width("main     education", 11) - 9:.1f}" cy="28" r="4" fill="{main_c}"/>',
            f'<circle cx="{W - 24 - text_width("education", 11) - 9:.1f}" cy="28" r="4" fill="{edu_c}"/>']

    # Lines first (drawn under the nodes).
    ys = [r["y"] for r in lay]
    lines = [f'<path class="ln" pathLength="1" d="M{x0},{ys[0]} V{ys[-1]}" stroke="{main_c}" stroke-width="2.5" fill="none"/>']
    for i, r in enumerate(lay):
        if r["kind"] != "edu-merge":
            continue
        j = next(k for k in range(i + 1, len(lay)) if lay[k]["kind"] == "edu-start" and lay[k]["d"] is r["d"])
        ym, ys_, yb = r["y"], lay[j]["y"], lay[j + 1]["y"] if j + 1 < len(lay) else lay[j]["y"] + 30
        d = (f"M{x0},{ym} C{x0},{ym + 14} {x1},{ym + 6} {x1},{ym + 22} V{ys_} "
             f"C{x1},{ys_ + 16} {x0},{yb - 18} {x0},{yb}")
        lines.append(f'<path class="ln" pathLength="1" d="{d}" stroke="{edu_c}" stroke-width="2.5" fill="none"/>')
    body += lines

    for i, r in enumerate(lay):
        kind, d, yy = r["kind"], r["d"], r["y"]
        delay = 0.25 + i * 0.22
        g = [f'<g class="row" style="animation-delay:{delay:.2f}s">']
        cx = x1 if kind == "edu-start" else x0
        color = edu_c if kind == "edu-start" else main_c
        if kind == "edu-merge":
            g.append(f'<circle cx="{cx}" cy="{yy}" r="6.5" fill="{p["panel"]}" stroke="{main_c}" stroke-width="2.5"/>')
        else:
            g.append(f'<circle cx="{cx}" cy="{yy}" r="6" fill="{color}" stroke="{p["panel"]}" stroke-width="2"/>')

        if kind == "job":
            sha, title, sub, when = _sha(d["role"] + d["org"]), d["role"], f" @ {d['org']}", d["when"]
        elif kind == "edu-start":
            sha, title, sub, when = _sha(d["degree"]), d["degree"], f" · {d['school']}", _month(d["start"])
        elif kind == "edu-merge":
            sha, title, sub, when = _sha("merge" + d["degree"]), f"Merge branch '{d['branch']}'", "  graduated", _month(d["end"])
        else:
            sha, title, sub, when = _sha("init"), "git init", "  hello, world", d["start"][:4]

        x = tx
        g.append(text(x, yy + 4, sha, p["faint"], 12))
        x += text_width(sha + " ", 12) + 4
        if i == 0:
            pill, w = _pill(x, yy + 4, "HEAD → main", main_c)
            g.append(pill)
            x += w + 8
        if kind == "edu-start":
            pill, w = _pill(x, yy + 4, d["branch"], edu_c)
            g.append(pill)
            x += w + 8
        g.append(f'<text x="{x:.1f}" y="{yy + 4:.1f}" font-size="13" xml:space="preserve">'
                 f'<tspan fill="{p["fg"]}" font-weight="700">{esc(title)}</tspan><tspan fill="{p["muted"]}">{esc(sub)}</tspan></text>')
        g.append(text(W - 24, yy + 4, when, p["faint"], 11.5, anchor="end"))

        cy = yy + 26
        for line in r["chips"]:
            cxp = tx
            for label, w in line:
                g.append(f'<rect x="{cxp:.1f}" y="{cy - 12:.1f}" width="{w:.1f}" height="18" rx="4" fill="{p["green"]}" fill-opacity="0.12" '
                         f'stroke="{p["green"]}" stroke-opacity="0.35"/>')
                g.append(text(cxp + 7, cy + 1, f"+ {label}", p["green"], 10.5, 600))
                cxp += w + 6
            cy += 23
        g.append("</g>")
        body += g

    total = 0.25 + len(lay) * 0.22
    style = (".row{opacity:0;animation:in .45s ease-out forwards}@keyframes in{to{opacity:1}}"
             f".ln{{stroke-dasharray:1;stroke-dashoffset:1;animation:draw {total:.2f}s ease-out .1s forwards}}"
             "@keyframes draw{to{stroke-dashoffset:0}}"
             "@media (prefers-reduced-motion: reduce){*{animation:none!important}.row{opacity:1}.ln{stroke-dashoffset:0}}")
    return document(W, H, "".join(body), "Career as a git log: roles as commits on main, degrees as merged branches", style)


STAGES = [("data", "ingest"), ("retrieval", "find"), ("models", "reason"),
          ("agents", "act"), ("evals", "verify"), ("ship", "serve")]


def stack_pipeline(config: dict, mode: str) -> str:
    p = PALETTES[mode]
    pipe = config.get("pipeline", {})
    stages = [(k, verb, pipe.get(k, [])) for k, verb in STAGES if pipe.get(k)]
    n = len(stages)
    gap, left = 14, 24
    cw = (W - 2 * left - gap * (n - 1)) / n
    rows = max(len(t) for _, _, t in stages)
    top, chip_h, chip_gap = 104, 24, 7
    H = top + rows * (chip_h + chip_gap) + 30
    cycle = 7.0

    body = [f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{p["panel"]}" stroke="{p["line"]}"/>',
            text(24, 32, "how I ship an AI system", p["fg"], 15, 700),
            text(24 + text_width("how I ship an AI system  ", 15), 32, "the stack, in the order data flows through it", p["muted"], 12)]

    # The bus: a line through every stage, with a signal travelling along it.
    bus_y = 58
    bx0, bx1 = left + cw / 2, left + (n - 1) * (cw + gap) + cw / 2
    body.append(f'<line x1="{bx0:.1f}" x2="{bx1:.1f}" y1="{bus_y}" y2="{bus_y}" stroke="{p["line"]}" stroke-width="2"/>')
    for i in range(n - 1):
        ax = left + i * (cw + gap) + cw / 2 + (cw + gap) / 2
        body.append(f'<path d="M{ax - 4:.1f},{bus_y - 4} l5,4 l-5,4" fill="none" stroke="{p["faint"]}" stroke-width="1.5"/>')
    body.append(f'<g class="sig"><circle cx="{bx0:.1f}" cy="{bus_y}" r="9" fill="{p["teal"]}" fill-opacity="0.25"/>'
                f'<circle cx="{bx0:.1f}" cy="{bus_y}" r="4.5" fill="{p["teal"]}"/></g>')

    for i, (key, verb, tools) in enumerate(stages):
        x = left + i * (cw + gap)
        mid = x + cw / 2
        delay = cycle * (i / max(n - 1, 1)) * 0.82
        body.append(f'<circle class="hit" style="animation-delay:{delay:.2f}s" cx="{mid:.1f}" cy="{bus_y}" r="7" '
                    f'fill="{p["panel"]}" stroke="{p["teal"]}" stroke-width="2"/>')
        body.append(text(mid, 84, f"{i + 1:02d} {key}", p["fg"], 12, 700, anchor="middle"))
        body.append(text(mid, 98, verb, p["faint"], 10.5, anchor="middle"))
        for k, tool in enumerate(tools):
            y = top + k * (chip_h + chip_gap)
            body.append(f'<g class="chip" style="animation-delay:{delay + 0.05 * k:.2f}s">'
                        f'<rect x="{x:.1f}" y="{y}" width="{cw:.1f}" height="{chip_h}" rx="6" fill="{p["bg"]}" stroke="{p["line"]}"/>'
                        + text(mid, y + 16, tool, p["fg"], 11, anchor="middle") + "</g>")

    style = (f".sig{{animation:travel {cycle}s cubic-bezier(.45,0,.55,1) infinite}}"
             f"@keyframes travel{{0%{{transform:translateX(0)}}82%,100%{{transform:translateX({bx1 - bx0:.1f}px)}}}}"
             f".hit{{animation:hit {cycle}s ease-out infinite}}"
             "@keyframes hit{0%,6%{fill:" + p["teal"] + "}14%,100%{fill:" + p["panel"] + "}}"
             f".chip rect{{animation:glow {cycle}s ease-out infinite;animation-delay:inherit}}"
             "@keyframes glow{0%,4%{stroke:" + p["teal"] + "}16%,100%{stroke:" + p["line"] + "}}"
             "@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
    return document(W, H, "".join(body), "Toolbox as a pipeline: data, retrieval, models, agents, evals, ship", style)
