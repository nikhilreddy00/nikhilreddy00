"""Data file for the interactive site (site/data.json).

Same privacy rule as the cards: public repositories by name, private work
only as anonymous totals.
"""

from __future__ import annotations

import json

from .latent import Cluster, Point
from .metrics import Metrics


def build(m: Metrics, points: list[Point], clusters: list[Cluster], config: dict) -> str:
    commits = {name: c for name, _, c in m.repo_commits}
    featured = {n.lower() for n in config["projects"].get("featured", [])}
    pos = {pt.repo.name: pt for pt in points}

    repos = []
    for r in m.public_repos:
        pt = pos.get(r.name)
        repos.append({
            "name": r.name,
            "description": r.description,
            "url": r.url,
            "language": r.language,
            "color": r.language_color,
            "stars": r.stars,
            "created": r.created.date().isoformat(),
            "pushed": r.pushed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "topics": r.topics,
            "archived": r.archived,
            "featured": r.name.lower() in featured,
            "commits_12mo": commits.get(r.name, 0),
            "cluster": pt.cluster if pt else None,
            "x": round(pt.x, 4) if pt else None,
            "y": round(pt.y, 4) if pt else None,
        })

    data = {
        "generated_at": m.generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "login": m.login,
        "timezone": config.get("timezone", "America/New_York"),
        "identity": config["identity"],
        "experience": config.get("experience", []),
        "stack": config.get("stack", {}),
        "education": config.get("education", []),
        "totals": {
            "lifetime_contributions": m.lifetime_contributions,
            "repos_created_this_year": m.repos_created_this_year,
            "private_unattributed": m.restricted_contributions,
            "private_commits": m.private_commits,
        },
        "calendar": [[d.isoformat(), c] for d, c in m.year],
        "languages": [{"name": n, "color": c, "share": round(s, 4)} for n, c, s in m.languages],
        "languages_excluded": m.languages_excluded,
        "clusters": [{"id": j, "label": c.label, "terms": c.terms[:8]} for j, c in enumerate(clusters)],
        "repos": repos,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
