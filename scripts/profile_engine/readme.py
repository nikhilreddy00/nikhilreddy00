"""Rewrite the auto-updated sections of README.md between <!--live:NAME:start/end--> markers."""

from __future__ import annotations

import re

from .metrics import Metrics, Repo


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def _describe(r: Repo, limit: int = 100) -> str:
    d = r.description or "—"
    if len(d) <= limit:
        return d
    cut = d[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-·")
    return cut + "…"


def recent_table(m: Metrics) -> str:
    rows = ["| Project | What it does | Language | Last push |", "| :-- | :-- | :-- | :-- |"]
    for r in m.recent:
        stars = f" ★{r.stars}" if r.stars else ""
        rows.append(f"| [**{_cell(r.name)}**]({r.url}){stars} | {_cell(_describe(r))} | "
                    f"{_cell(r.language or '—')} | {r.pushed:%b %d, %Y} |")
    return "\n".join(rows)


def replace_section(readme: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!--live:{name}:start-->)(.*?)(<!--live:{name}:end-->)", re.S)
    if not pattern.search(readme):
        raise ValueError(f"README is missing the live:{name} markers")
    inline = "\n" not in content
    body = content if inline else f"\n{content}\n"
    return pattern.sub(lambda mt: mt.group(1) + body + mt.group(3), readme)


def update(readme: str, m: Metrics) -> str:
    readme = replace_section(readme, "recent", recent_table(m))
    readme = replace_section(readme, "updated", f"{m.generated_at:%Y-%m-%d %H:%M} UTC")
    return readme
