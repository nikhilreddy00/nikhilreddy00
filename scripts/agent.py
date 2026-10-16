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


def agent_issues() -> list[dict]:
    """All agent-labelled issues, newest first."""
    out, page = [], 1
    while True:
        batch = api("GET", f"/repos/{REPO}/issues?labels={LABEL}&state=all&sort=created&direction=desc&per_page=100&page={page}")
        out += [{"number": i["number"], "title": i["title"], "user": i["user"]["login"], "created_at": i["created_at"]}
                for i in batch if "pull_request" not in i]
        if len(batch) < 100:
            return out
        page += 1


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
    issues = agent_issues()
    # The label filter can lag a few seconds behind the label we just added.
    if just_answered and all(i["number"] != just_answered["number"] for i in issues):
        issues.insert(0, just_answered)
    path = ROOT / "README.md"
    path.write_text(replace_section(path.read_text(), "agent", agent.sessions_section(issues, data, REPO)))


def decline(number: int, reason: str, public_note: str) -> None:
    """Close without running anything and without logging the visitor."""
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
        return decline(number, f"non-user author {user!r}", "This agent only answers people, not bots or apps.")
    if user.lower() in blocked_users():
        return decline(number, f"blocked user {user}", later)
    if user.lower() != owner:
        profile = api("GET", f"/users/{user}")
        created = dt.datetime.fromisoformat(profile["created_at"].replace("Z", "+00:00"))
        if dt.datetime.now(dt.timezone.utc) - created < dt.timedelta(days=MIN_ACCOUNT_DAYS):
            return decline(number, "account too new", f"This agent answers accounts older than {MIN_ACCOUNT_DAYS} days. {later}")

    now = dt.datetime.now(dt.timezone.utc)
    history = agent_issues()
    stamp = lambda i: dt.datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))
    if user.lower() != owner:
        mine = [i for i in history if i["user"].lower() == user.lower() and now - stamp(i) < dt.timedelta(days=1)]
        if len(mine) >= DAILY_LIMIT:
            return decline(number, "daily limit", f"You've run {DAILY_LIMIT} commands in the last 24 hours, the daily limit here. {later}")
        if sum(1 for i in history if now - stamp(i) < dt.timedelta(hours=1)) >= HOURLY_CAP:
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
