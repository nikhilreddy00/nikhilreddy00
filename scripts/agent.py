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
DAILY_LIMIT = 5

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


def update_readme() -> None:
    data = json.loads((ROOT / "site" / "data.json").read_text())
    path = ROOT / "README.md"
    path.write_text(replace_section(path.read_text(), "agent", agent.sessions_section(agent_issues(), data, REPO)))


def respond() -> None:
    number = int(os.environ["ISSUE_NUMBER"])
    title = os.environ.get("ISSUE_TITLE", "")
    user = os.environ["ISSUE_AUTHOR"]
    data = json.loads((ROOT / "site" / "data.json").read_text())

    parsed = agent.parse(title, data)
    if parsed is None:
        print("Not an agent issue; nothing to do.")
        return
    cmd, args = parsed

    # Fair use: a few runs per visitor per day keeps the log readable.
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    recent = [i for i in agent_issues() if i["user"].lower() == user.lower()
              and dt.datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")) > since]

    api("POST", f"/repos/{REPO}/labels", {"name": LABEL, "color": "39c5bb", "description": "Profile agent runs"}, ok=(422,))
    if len(recent) >= DAILY_LIMIT and user.lower() != REPO.split("/")[0].lower():
        reply = (f"You've run {DAILY_LIMIT} commands in the last 24 hours, which is the daily limit here. "
                 f"The [interactive terminal]({agent.SITE}#terminal) has no limit. Try it there.")
        api("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": reply})
        api("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "not_planned"})
        api("PUT", f"/repos/{REPO}/issues/{number}/lock", {"lock_reason": "resolved"}, ok=(204,))
        print(f"Rate-limited @{user}")
        return

    excerpt = readme_excerpt(args[0]) if cmd == "cat" and args else None
    reply = agent.respond(cmd, args, data, user, REPO, excerpt)
    api("POST", f"/repos/{REPO}/issues/{number}/comments", {"body": reply})
    api("POST", f"/repos/{REPO}/issues/{number}/labels", {"labels": [LABEL]})
    api("PATCH", f"/repos/{REPO}/issues/{number}", {"state": "closed", "state_reason": "completed"})
    api("PUT", f"/repos/{REPO}/issues/{number}/lock", {"lock_reason": "resolved"}, ok=(204,))
    print(f"Answered #{number}: @{user} ran `{agent.display(cmd, args)}`")
    update_readme()


if __name__ == "__main__":
    try:
        {"respond": respond, "sessions": update_readme}[sys.argv[1] if len(sys.argv) > 1 else "respond"]()
    except Exception as exc:
        # Surface the reason as a workflow annotation (visible in the Actions UI and API).
        print(f"::error title=Profile agent failed::{type(exc).__name__}: {str(exc)[:500]}")
        raise
