"""Shared SVG building blocks: palettes, text helpers, document wrapper.

Cards are rendered twice, once per palette, and the README picks the right
file with <picture> + prefers-color-scheme. GitHub serves README images as
plain <img>, so no scripts or web fonts: system monospace stacks only.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
CHAR_W = 0.602  # average advance of the monospace stack, in ems

PALETTES = {
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
