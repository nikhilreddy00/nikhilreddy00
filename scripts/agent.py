"""GitHub side of the profile agent.

    python scripts/agent.py respond   # run by the `issues: opened` workflow
    python scripts/agent.py sessions  # rebuild the README session log only

Reads ISSUE_NUMBER / ISSUE_TITLE / ISSUE_AUTHOR / GITHUB_TOKEN / GITHUB_REPOSITORY
from the environment (never interpolated into shell), replies, labels, closes
and locks the issue, then rewrites the README's live:agent section.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from profile_engine import agent  # noqa: E402
from profile_engine.readme import replace_section  # noqa: E402

LABEL = "agent"
DECLINED = "agent-declined"
MAX_PAGES = 10           # 1,000 issues; beyond that, fail closed rather than open
DAILY_LIMIT = 5          # runs per visitor per 24 h
HOURLY_CAP = 30          # runs per hour across everyone (stops floods from many accounts)
MIN_ACCOUNT_DAYS = 14    # brand-new accounts are the usual spam source

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "nikhilreddy00/nikhilreddy00")


def api(method: str, path: str, body: dict | None = None, ok=(200, 201, 204)) -> dict | list | None:
    req = urllib.request.Request(
        f"https://api.github.com{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "profile-agent"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        if e.code in ok:
            return None
        raise RuntimeError(f"{method} {path} -> {e.code}: {e.read()[:300]!r}") from None


def agent_issues() -> tuple[list[dict], bool]:
    """Answered (agent-labelled) issues, newest first, and whether the list was cut off."""
    out = []
    for page in range(1, MAX_PAGES + 1):
        batch = api("GET", f"/repos/{REPO}/issues?labels={LABEL}&state=all&sort=created&direction=desc&per_page=100&page={page}")
        out += [{"number": i["number"], "title": i["title"], "user": i["user"]["login"], "created_at": i["created_at"]}
                for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            return out, False
    return out, True


def readme_excerpt(repo: str, limit: int = 18) -> list[str]:
    try:
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{REPO.split('/')[0]}/{repo}/HEAD/README.md", timeout=15) as r:
            md = r.read().decode("utf-8", "replace")
    except Exception:
        return []
    md = re.sub(r"<!--.*?-->|<[^>]+>|```.*?```", "", md, flags=re.S)
    lines = []
    for line in md.splitlines():
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).replace("**", "").replace("`", "").rstrip()
        if re.match(r"^\s*(\[!\[|---+\s*$)", line):
            continue
        if line.strip() or (lines and lines[-1].strip()):
            lines.append(line[:110])
    return lines[:limit] + (["…"] if len(lines) > limit else [])


def update_readme(just_answered: dict | None = None) -> None:
    data = json.loads((ROOT / "site" / "data.json").read_text())
    issues, truncated = agent_issues()
    # The label filter can lag a few seconds behind the label we just added.
    if just_answered and all(i["number"] != just_answered["number"] for i in issues):
        issues.insert(0, just_answered)
    total = None
    if truncated:
        res = api("GET", f"/search/issues?q=repo:{REPO}+label:{LABEL}+is:issue&per_page=1")
        total = res.get("total_count") if res else None
    section = agent.sessions_section(issues, data, REPO, blocked=blocked_users(), total=total, truncated=truncated)
    path = ROOT / "README.md"
    path.write_text(replace_section(path.read_text(), "agent", section))


class WindowTooLarge(Exception):
    """More issues in the window than we page through: treat as over the limit."""


def agent_issues_since(hours: int, creator: str | None = None) -> list[dict]:
    """Issues opened in the window that count toward a limit, answered or not.

    Counting in-flight issues (not just labelled ones) closes the race where a
    burst of parallel runs each saw only the history from before the burst.
    - With `creator`, every issue by that person counts, whatever its title now
      says, so renaming an issue can't reset a quota.
    - Without it (the global cap), issues already declined don't count, so
      throwaway accounts can't use up the cap for everyone else.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    since = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    who = f"&creator={creator}" if creator else ""
    out = []
    for page in range(1, MAX_PAGES + 1):
        batch = api("GET", f"/repos/{REPO}/issues?state=all&since={since}{who}&per_page=100&page={page}")
        for i in batch:
            created = dt.datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))
            if "pull_request" in i or created < cutoff:
                continue
            if not creator:
                if not agent.TITLE.match(i["title"] or ""):
                    continue
                if any(l.get("name") == DECLINED for l in i.get("labels", [])):
                    continue
            out.append({"number": i["number"], "user": i["user"]["login"]})
        if len(batch) < 100:
            return out
    raise WindowTooLarge()


def rank(issues: list[dict], number: int) -> int:
    """1-based position of this issue among the window's issues, oldest first."""
    numbers = sorted({i["number"] for i in issues} | {number})
    return numbers.index(number) + 1


def decline(number: int, reason: str, public_note: str | None = None) -> None:
    """Close and lock without running anything or logging the visitor.

    Most declines are silent so spam doesn't turn into a stream of public bot
    comments; the `agent-declined` label keeps them out of the global count.
    """
    api("POST", f"/repos/{REPO}/labels", {"name": DECLINED, "color": "8b949e", "description": "Profile agent: not run"}, ok=(422,))
    api("POST", f"/repos/{REPO}/issues/{number}/labels", {"labels": [DECLINED]})
    if public_note:
        api("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": public_note})
    api("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "not_planned"})
    api("PUT", f"/repos/{REPO}/issues/{number}/lock", {"lock_reason": "resolved"}, ok=(204,))
    print(f"Declined #{number}: {reason}")


def blocked_users() -> set[str]:
    try:
        import tomllib
        cfg = tomllib.loads((ROOT / "profile.toml").read_text())
        return {u.lower() for u in cfg.get("agent", {}).get("blocked_users", [])}
    except Exception:
        return set()


def respond() -> None:
    number = int(os.environ["ISSUE_NUMBER"])
    title = os.environ.get("ISSUE_TITLE", "")[:200]
    user = os.environ["ISSUE_AUTHOR"]
    user_type = os.environ.get("ISSUE_AUTHOR_TYPE", "User")
    owner = REPO.split("/")[0].lower()
    data = json.loads((ROOT / "site" / "data.json").read_text())

    parsed = agent.parse(title, data)
    if parsed is None:
        print("Not an agent issue; nothing to do.")
        return
    cmd, args = parsed
    later = f"Thanks for stopping by. The [interactive terminal]({agent.SITE}#terminal) works for everyone."

    # Guards, cheapest first. None of them run anything the visitor wrote.
    if user_type != "User" or not agent.SAFE_LOGIN.fullmatch(user):
        return decline(number, f"non-user author {user!r}")
    if user.lower() in blocked_users():
        return decline(number, "blocked user")
    if user.lower() != owner:
        profile = api("GET", f"/users/{user}")
        created = dt.datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00"))
        if dt.datetime.now(dt.timezone.utc) - created < dt.timedelta(days=MIN_ACCOUNT_DAYS):
            return decline(number, "account too new")

        # Deterministic under bursts: every parallel run ranks the same issue list
        # by issue number, so exactly the first N in each window get answered.
        try:
            daily = rank(agent_issues_since(24, creator=user), number)
            hourly = rank(agent_issues_since(1), number)
        except WindowTooLarge:
            return decline(number, "window too large (fail closed)")
        if daily > DAILY_LIMIT:
            # One friendly note on the first run over the limit; silent after that.
            note = f"You've run {DAILY_LIMIT} commands in the last 24 hours, the daily limit here. {later}"
            return decline(number, "daily limit", note if daily == DAILY_LIMIT + 1 else None)
        if hourly > HOURLY_CAP:
            return decline(number, "hourly cap", f"The agent is busy right now. {later}")

    api("POST", f"/repos/{REPO}/labels", {"name": LABEL, "color": "39c5bb", "description": "Profile agent runs"}, ok=(422,))

    excerpt = readme_excerpt(args[0]) if cmd == "cat" and args else None
    reply = agent.respond(cmd, args, data, user, REPO, excerpt)
    api("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": reply})
    api("POST", f"/repos/{REPO}/issues/{number}/labels", {"labels": [LABEL]})
    api("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "completed"})
    api("PUT", f"/repos/{REPO}/issues/{number}/lock", {"lock_reason": "resolved"}, ok=(204,))
    print(f"Answered #{number}: @{user} ran `{agent.display(cmd, args)}`")
    created = os.environ.get("ISSUE_CREATED_AT") or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    update_readme({"number": number, "title": title, "user": user, "created_at": created})


if __name__ == "__main__":
    try:
        {"respond": respond, "sessions": lambda: update_readme()}[sys.argv[1] if len(sys.argv) > 1 else "respond"]()
    except Exception as exc:
        # Surface the reason as a workflow annotation (visible in the Actions UI and API).
        print(f"::error title=Profile agent failed::{type(exc).__name__}: {str(exc)[:500]}")
        raise
