"""Turn the raw API snapshot into the numbers the cards and README show.

Private repositories only ever feed aggregate numbers (contribution counts,
language bytes, repo counts). Their names and descriptions are dropped here
and never reach the rendering code.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class Repo:
    name: str
    description: str
    url: str
    language: str | None
    language_color: str | None
    stars: int
    created: dt.datetime
    pushed: dt.datetime
    archived: bool
    topics: list[str]
    readme: str


@dataclass
class Metrics:
    login: str
    generated_at: dt.datetime
    public_repos: list[Repo]           # newest push first, exclusions applied
    featured: list[Repo]
    recent: list[Repo]
    languages: list[tuple[str, str, float]]   # (name, color, share 0..1)
    days: list[tuple[dt.date, int]]           # last 90 days, oldest first
    contributions_30d: int
    contributions_prev_30d: int
    active_days_90d: int
    current_streak: int
    last_active: dt.date | None
    longest_streak_year: int
    lifetime_contributions: int
    repos_created_this_year: int
    includes_private: bool
    languages_excluded: list[str]
    checkpoints: list[Repo] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return any(c for _, c in self.days[-7:])


def _ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def _streaks(counts: list[int]) -> tuple[int, int]:
    """Current streak (today may still be empty) and longest streak."""
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


def compute(snapshot: dict, config: dict) -> Metrics:
    now = _ts(snapshot["fetched_at"])
    excluded = {n.lower() for n in config["projects"].get("exclude", [])}
    featured_names = [n.lower() for n in config["projects"].get("featured", [])]
    lang_exclude = set(config["languages"].get("exclude", []))

    owned = [r for r in snapshot["repos"] if r["name"].lower() not in excluded]

    public = []
    for r in owned:
        if r["isPrivate"]:
            continue
        lang = r.get("primaryLanguage") or {}
        public.append(Repo(
            name=r["name"],
            description=(r.get("description") or "").strip(),
            url=r["url"],
            language=lang.get("name"),
            language_color=lang.get("color"),
            stars=r["stargazerCount"],
            created=_ts(r["createdAt"]),
            pushed=_ts(r["pushedAt"]),
            archived=r["isArchived"],
            topics=r.get("topics", []),
            readme=r.get("readme", ""),
        ))
    public.sort(key=lambda r: r.pushed, reverse=True)

    by_name = {r.name.lower(): r for r in public}
    featured = [by_name[n] for n in featured_names if n in by_name]
    recent = [r for r in public if r.name.lower() not in featured_names and not r.archived]
    recent = recent[: config["projects"].get("recent_count", 5)]

    sizes: dict[str, list] = {}
    for r in owned:
        for l in r["languages"]:
            if l["name"] in lang_exclude:
                continue
            entry = sizes.setdefault(l["name"], [l["color"] or "#8b949e", 0])
            entry[1] += l["size"]
    total = sum(v[1] for v in sizes.values()) or 1
    ranked = sorted(sizes.items(), key=lambda kv: kv[1][1], reverse=True)
    top_n = config["languages"].get("top", 5)
    languages = [(n, c, s / total) for n, (c, s) in ranked[:top_n]]
    rest = sum(s for _, (_, s) in ranked[top_n:])
    if rest:
        languages.append(("Other", "#8b949e", rest / total))

    cal = [(dt.date.fromisoformat(d["date"]), d["count"]) for d in snapshot["calendar"]]
    cal.sort()
    counts = [c for _, c in cal]
    last90 = cal[-90:]
    current, longest = _streaks(counts)

    window_start = dt.datetime.combine(last90[0][0], dt.time(), tzinfo=dt.timezone.utc)
    checkpoints = sorted((r for r in public if r.created >= window_start), key=lambda r: r.created)

    return Metrics(
        login=snapshot["login"],
        generated_at=now,
        public_repos=public,
        featured=featured,
        recent=recent,
        languages=languages,
        days=last90,
        contributions_30d=sum(counts[-30:]),
        contributions_prev_30d=sum(counts[-60:-30]),
        active_days_90d=sum(1 for c in counts[-90:] if c),
        current_streak=current,
        last_active=next((d for d, c in reversed(cal) if c), None),
        longest_streak_year=longest,
        lifetime_contributions=snapshot["lifetime_contributions"],
        repos_created_this_year=sum(1 for r in owned if _ts(r["createdAt"]).year == now.year),
        includes_private=any(r["isPrivate"] for r in snapshot["repos"]) or snapshot.get("restricted_contributions", 0) > 0,
        languages_excluded=sorted(lang_exclude),
        checkpoints=checkpoints,
    )
