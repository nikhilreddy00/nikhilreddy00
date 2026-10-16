"""Rewrite the auto-updated sections of README.md between <!--live:NAME:start/end--> markers."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # keep this module importable without numpy (the agent workflow)
    from .latent import Cluster, Point
    from .metrics import Metrics, Repo

BAR_WIDTH = 16


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def _describe(r: Repo, limit: int = 100) -> str:
    d = r.description or "—"
    if len(d) <= limit:
        return d
    cut = d[:limit].rsplit(" ", 1)[0].rstrip(" ,;:—-·")
    return cut + "…"


def _bar(value: int, peak: int) -> str:
    filled = round(BAR_WIDTH * value / peak) if peak else 0
    return "`" + "█" * filled + "░" * (BAR_WIDTH - filled) + "`"


def recent_table(m: Metrics) -> str:
    rows = ["| Project | What it does | Language | Last push |", "| :-- | :-- | :-- | :-- |"]
    for r in m.recent:
        stars = f" ★{r.stars}" if r.stars else ""
        rows.append(f"| [**{_cell(r.name)}**]({r.url}){stars} | {_cell(_describe(r))} | "
                    f"{_cell(r.language or '—')} | {r.pushed:%b %d, %Y} |")
    return "\n".join(rows)


def repo_commits_table(m: Metrics) -> str:
    rows = [(f"[{_cell(n)}]({u})", c) for n, u, c in m.repo_commits[:12]]
    if m.private_commits:
        plural = "s" if m.private_commit_repos != 1 else ""
        rows.append((f"*{m.private_commit_repos} private repo{plural} (combined)*", m.private_commits))
    if not rows:
        return "_No commits in the last 12 months yet._"
    rows.sort(key=lambda r: -r[1])
    peak = rows[0][1]
    total = sum(c for _, c in rows)
    out = ["| Repository | Commits · 12 mo | Share |", "| :-- | --: | :-- |"]
    out += [f"| {name} | {c:,} | {_bar(c, peak)} {c / total:.0%} |" for name, c in rows]
    if m.restricted_contributions:
        out += ["", f"<sub>Plus {m.restricted_contributions} private contributions that GitHub counts "
                    "but doesn't attribute to a repository.</sub>"]
    return "\n".join(out)


def clusters_table(points: list[Point], clusters: list[Cluster]) -> str:
    out = ["| Cluster | Repos | Strongest terms |", "| :-- | :-- | :-- |"]
    for j, c in enumerate(clusters):
        members = [pt.repo for pt in points if pt.cluster == j]
        if not members:
            continue
        names = ", ".join(f"[{_cell(r.name)}]({r.url})" for r in members[:6])
        if len(members) > 6:
            names += f" +{len(members) - 6} more"
        terms = " · ".join(f"`{t}`" for t in c.terms[:6]) or "—"
        out.append(f"| **{_cell(c.label)}** | {names} | {terms} |")
    return "\n".join(out)


def sections(m: Metrics, points: list[Point], clusters: list[Cluster]) -> dict[str, str]:
    return {
        "recent": recent_table(m),
        "repos": repo_commits_table(m),
        "clusters": clusters_table(points, clusters),
    }


def replace_section(readme: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!--live:{name}:start-->)(.*?)(<!--live:{name}:end-->)", re.S)
    if not pattern.search(readme):
        raise ValueError(f"README is missing the live:{name} markers")
    body = content if "\n" not in content else f"\n{content}\n"
    return pattern.sub(lambda mt: mt.group(1) + body + mt.group(3), readme)


def update(readme: str, m: Metrics, live: dict[str, str]) -> str:
    for name, content in live.items():
        readme = replace_section(readme, name, content)
    return replace_section(readme, "updated", f"{m.generated_at:%Y-%m-%d %H:%M} UTC")
