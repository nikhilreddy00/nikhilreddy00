"""Shared SVG building blocks: palettes, text helpers, document wrapper.

Cards are rendered twice, once per palette, and the README picks the right
file with <picture> + prefers-color-scheme. GitHub serves README images as
plain <img>, so no scripts or web fonts: system monospace stacks only.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
CHAR_W = 0.602  # average advance of the monospace stack, in ems

_CLASSIC = {
    "dark": {
        "bg": "#0d1117", "panel": "#161b22", "line": "#30363d", "grid": "#21262d",
        "fg": "#e6edf3", "muted": "#8b949e", "faint": "#6e7681",
        "teal": "#39c5bb", "blue": "#58a6ff", "purple": "#bc8cff", "green": "#3fb950",
        "orange": "#f0883e", "pink": "#f778ba", "yellow": "#e3b341", "red": "#f85149",
        "dot_red": "#ff5f57", "dot_yellow": "#febc2e", "dot_green": "#28c840",
        # Categorical slots, validated for colour-vision deficiency on this surface.
        "c1": "#3987e5", "c2": "#d95926", "c3": "#199e70", "c4": "#c98500",
        "c5": "#d55181", "c6": "#008300", "c7": "#9085e9", "c8": "#e66767",
    },
    "light": {
        "bg": "#ffffff", "panel": "#f6f8fa", "line": "#d0d7de", "grid": "#eaeef2",
        "fg": "#1f2328", "muted": "#59636e", "faint": "#818b98",
        "teal": "#0b7a75", "blue": "#0969da", "purple": "#8250df", "green": "#1a7f37",
        "orange": "#bc4c00", "pink": "#bf3989", "yellow": "#9a6700", "red": "#cf222e",
        "dot_red": "#ff5f57", "dot_yellow": "#febc2e", "dot_green": "#28c840",
        "c1": "#2a78d6", "c2": "#eb6834", "c3": "#1baf7a", "c4": "#eda100",
        "c5": "#e87ba4", "c6": "#008300", "c7": "#6250d6", "c8": "#e34948",
    },
}


# Per-card hues for themes that give each card its own colour identity.
CARD_HUE = {"trace": "indigo", "latent": "violet", "run": "teal", "history": "teal",
            "career": "emerald", "stack": "amber"}
_HUES = {
    "light": {"indigo": "#4f5bd5", "violet": "#8250df", "teal": "#0b8f87", "emerald": "#1a7f37", "amber": "#c27803"},
    "dark": {"indigo": "#7c8cff", "violet": "#b392f0", "teal": "#39c5bb", "emerald": "#3fb950", "amber": "#e3b341"},
}


def _theme(base: dict, **over) -> dict:
    return {mode: {**base[mode], "is_dark": mode == "dark", **over.get(mode, {})} for mode in ("dark", "light")}


# Surfaces and text change per theme; data colours stay the validated set.
THEMES = {
    "classic": _theme(_CLASSIC, dark={"frame": "flat"}, light={"frame": "flat"}),
    "aurora": _theme(
        _CLASSIC,
        dark={"frame": "aurora", "panel": "#11161f", "bg": "#0d1117", "hues": _HUES["dark"]},
        light={"frame": "aurora", "panel": "#ffffff", "bg": "#ffffff", "line": "#dfe4ec", "grid": "#edf0f5",
               "hues": _HUES["light"]},
    ),
    "blueprint": _theme(
        _CLASSIC,
        dark={"frame": "blueprint", "panel": "#0c1a33", "bg": "#0a1529", "line": "#23406e", "grid": "#16305a",
              "fg": "#e2ecff", "muted": "#9db3d9", "faint": "#7189b5", "gridline": "#132a4f"},
        light={"frame": "blueprint", "panel": "#f2f7ff", "bg": "#ffffff", "line": "#c6d6f0", "grid": "#dfe9f8",
               "fg": "#0f2547", "muted": "#4b5f80", "faint": "#6f82a3", "gridline": "#d5e2f6"},
    ),
    "mesh": _theme(
        _CLASSIC,
        dark={"frame": "mesh", "panel": "#100e1c", "bg": "#0d0b17", "line": "#2e2a45", "grid": "#1d1a30",
              "blobs": ["#7c3aed", "#db2777", "#0ea5e9"], "blob_opacity": 0.22},
        light={"frame": "mesh", "panel": "#ffffff", "bg": "#ffffff", "line": "#e4dff2", "grid": "#f0edf8",
               "blobs": ["#a78bfa", "#f472b6", "#38bdf8"], "blob_opacity": 0.3},
    ),
}

# Active palettes (cards read PALETTES[mode]); switch with set_theme().
PALETTES = {mode: dict(v) for mode, v in THEMES["classic"].items()}


def set_theme(name: str) -> None:
    theme = THEMES.get(name, THEMES["classic"])
    for mode in ("dark", "light"):
        PALETTES[mode].clear()
        PALETTES[mode].update(theme[mode])


def frame(p: dict, w: float, h: float, key: str, rx: int = 12) -> str:
    """Card background for the active theme: flat, aurora (per-card hue wash and
    accent bar), blueprint (engineering grid paper) or mesh (soft colour blobs)."""
    kind = p.get("frame", "flat")
    edge = f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{p["line"]}"/>'
    clip = (f'<clipPath id="fr-{key}"><rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}"/></clipPath>')
    base = f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="{p["panel"]}"/>'
    if kind == "aurora":
        hue = p["hues"][CARD_HUE.get(key, "teal")]
        a0 = 0.20 if p.get("is_dark") else 0.19
        return (f'<defs>{clip}<linearGradient id="au-{key}" x1="0" y1="0" x2="1" y2="1">'
                f'<stop offset="0" stop-color="{hue}" stop-opacity="{a0}"/>'
                f'<stop offset="0.55" stop-color="{hue}" stop-opacity="0.05"/>'
                f'<stop offset="1" stop-color="{hue}" stop-opacity="0"/></linearGradient></defs>'
                f'{base}<rect width="{w}" height="{h}" fill="url(#au-{key})" clip-path="url(#fr-{key})"/>'
                f'<rect width="{w}" height="4" fill="{hue}" clip-path="url(#fr-{key})"/>'
                f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{hue}" stroke-opacity="0.35"/>')
    if kind == "blueprint":
        return (f'<defs>{clip}<pattern id="bp-{key}" width="20" height="20" patternUnits="userSpaceOnUse">'
                f'<path d="M20 0H0V20" fill="none" stroke="{p["gridline"]}" stroke-width="1"/></pattern></defs>'
                f'{base}<rect width="{w}" height="{h}" fill="url(#bp-{key})" clip-path="url(#fr-{key})"/>{edge}')
    if kind == "mesh":
        b, op = p["blobs"], p["blob_opacity"]
        spots = [(0.08, 0.1, 0.55), (0.92, 0.2, 0.5), (0.6, 1.05, 0.6)]
        grads = "".join(
            f'<radialGradient id="ms{i}-{key}" cx="{cx}" cy="{cy}" r="{r}">'
            f'<stop offset="0" stop-color="{b[i]}" stop-opacity="{op}"/><stop offset="1" stop-color="{b[i]}" stop-opacity="0"/></radialGradient>'
            for i, (cx, cy, r) in enumerate(spots))
        layers = "".join(f'<rect width="{w}" height="{h}" fill="url(#ms{i}-{key})" clip-path="url(#fr-{key})"/>' for i in range(3))
        return f'<defs>{clip}{grads}</defs>{base}{layers}{edge}'
    return f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="{p["panel"]}" stroke="{p["line"]}"/>'


CATEGORICAL = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]


def esc(s) -> str:
    return escape(str(s), {'"': "&quot;"})


def text_width(s: str, size: float) -> float:
    return len(s) * size * CHAR_W


def text(x, y, s, fill, size=12, weight=400, anchor="start", cls="", extra="") -> str:
    c = f' class="{cls}"' if cls else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    w = f' font-weight="{weight}"' if weight != 400 else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}"{w}{a}{c}{extra}>{esc(s)}</text>'


def document(width: int, height: int, body: str, title: str, style: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}" font-family="{MONO}">'
        f"<title>{esc(title)}</title>"
        f"<style>{style}</style>{body}</svg>\n"
    )
