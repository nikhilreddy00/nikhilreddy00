"""Profile agent: answers commands that visitors run by opening an issue
titled `agent: <command>`.

Only allowlisted commands run, and anything displayed publicly (the README
session log) is the normalized command, never the raw issue title.
"""

from __future__ import annotations

import datetime as dt
import random
import re
import urllib.parse

SITE = "https://nikhilreddy00.github.io/nikhilreddy00/"
TITLE = re.compile(r"^\s*agent\s*:\s*(.*)$", re.I)
SAFE_LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")  # GitHub's username rules
SPARK = "▁▂▃▄▅▆▇█"

# command -> (description, example)
COMMANDS = {
    "whoami": ("who Nikhil is", "whoami"),
    "ls": ("list projects, newest first", "ls"),
    "cat": ("summary of one project", "cat praxis"),
    "stats": ("activity over 30, 90 or 365 days", "stats 90"),
    "langs": ("language mix", "langs"),
    "clusters": ("topic clusters from the latent space", "clusters"),
    "stack": ("tools and technologies", "stack"),
    "experience": ("work history", "experience"),
    "contact": ("how to reach Nikhil", "contact"),
    "random": ("a random project", "random"),
    "neofetch": ("one-screen summary", "neofetch"),
    "help": ("this list", "help"),
}
ALIASES = {"projects": "ls", "ll": "ls", "dir": "ls", "about": "whoami", "info": "neofetch",
           "skills": "stack", "work": "experience", "jobs": "experience", "hire": "contact",
           "email": "contact", "man": "help", "?": "help", "languages": "langs"}


def parse(title: str, data: dict) -> tuple[str, list[str]] | None:
    """Return (command, args) for an agent issue title, or None if it isn't one.
    Unknown commands come back as ("unknown", [])."""
    m = TITLE.match(title or "")
    if not m:
        return None
    words = m.group(1).strip().lstrip("$>").split()
    if not words:
        return "help", []
    head = words[0].lower()
    if head == "sudo":
        return ("sudo", []) if "hire" in " ".join(words).lower() else ("unknown", [])
    name = ALIASES.get(head, head)
    if name not in COMMANDS:
        return "unknown", []
    args = words[1:2]
    if name == "cat":
        repo = _find_repo(args[0] if args else "", data)
        return ("cat", [repo["name"]]) if repo else ("cat", [])
    if name == "stats":
        return "stats", [args[0]] if args and args[0] in ("30", "90", "365") else ["90"]
    return name, []


def display(cmd: str, args: list[str]) -> str:
    """Normalized command for public display."""
    if cmd == "sudo":
        return "sudo hire nikhil"
    if cmd == "unknown":
        return "(unknown command)"
    return " ".join([cmd, *args])


def run_link(repo_slug: str, command: str) -> str:
    q = urllib.parse.urlencode({
        "title": f"agent: {command}",
        "body": "Click **Create** / **Submit new issue** to run this command. "
                "My profile agent replies here in about 30 seconds, then closes the issue.\n\n"
                "_Only the command in the title is read. Your run is listed on my profile with your username._",
    }, quote_via=urllib.parse.quote)
    return f"https://github.com/{repo_slug}/issues/new?{q}"


def _find_repo(name: str, data: dict) -> dict | None:
    key = name.lower().strip("/")
    if not key:
        return None
    repos = data["repos"]
    exact = [r for r in repos if r["name"].lower() == key]
    if exact:
        return exact[0]
    pre = [r for r in repos if r["name"].lower().startswith(key)]
    return pre[0] if len(pre) == 1 else None


def _ago(iso: str, now: dt.datetime) -> str:
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (now - t).days
    if days < 1:
        return "today"
    if days < 30:
        return f"{days} day{'s' if days != 1 else ''} ago"
    months = days // 30
    return f"{months} mo ago" if months < 12 else f"{days // 365} yr ago"


def _block(lines: list[str]) -> str:
    return "```console\n" + "\n".join(lines) + "\n```"


def respond(cmd: str, args: list[str], data: dict, user: str, repo_slug: str,
            readme_lines: list[str] | None = None, now: dt.datetime | None = None) -> str:
    """Markdown reply for one command."""
    now = now or dt.datetime.now(dt.timezone.utc)
    ident = data["identity"]
    repos = sorted(data["repos"], key=lambda r: r["pushed"], reverse=True)
    prompt = f"{user}@nikhil:~$ {display(cmd, args)}"
    body: list[str] = []
    extra = ""

    if cmd == "help":
        w = max(len(c) for c in COMMANDS) + 2
        body = [f"{c.ljust(w)}{d}" for c, (d, _) in COMMANDS.items()]
    elif cmd == "whoami":
        body = [f"{ident['name']} · {ident['headline']} · {ident['current_role']} @ {ident['current_org']}", "", ident["summary"]]
    elif cmd == "ls":
        w = min(32, max(len(r["name"]) for r in repos) + 2)
        body = [f"{r['name'][:30].ljust(w)}{(r['language'] or '—')[:16].ljust(18)}{('★' + str(r['stars'])) if r['stars'] else '':<5}pushed {_ago(r['pushed'], now)}"
                for r in repos if not r.get("archived")]
        body.append(f"\n{len(body)} public repositories")
    elif cmd == "cat":
        if not args:
            body = ["cat: no such project. Try `ls` to see them all."]
        else:
            r = _find_repo(args[0], data)
            cl = next((c for c in data["clusters"] if c["id"] == r["cluster"]), None)
            body = [f"{r['name']} · {r['language'] or '—'} · ★{r['stars']} · pushed {_ago(r['pushed'], now)}" + (f" · {cl['label']}" if cl else ""),
                    "", r["description"] or "(no description)"]
            if r.get("topics"):
                body += ["", " ".join(f"#{t}" for t in r["topics"])]
            if readme_lines:
                body += ["", "── README " + "─" * 38, *readme_lines]
            extra = f"\n\n→ [Open {r['name']} on GitHub]({r['url']})"
    elif cmd == "stats":
        n = int(args[0])
        days = data["calendar"][-n:]
        total = sum(c for _, c in days)
        active = sum(1 for _, c in days if c)
        longest = run = 0
        for _, c in days:
            run = run + 1 if c else 0
            longest = max(longest, run)
        best = max(days, key=lambda d: d[1]) if days else None
        weeks = [sum(c for _, c in days[max(0, i - 7):i]) for i in range(len(days), 0, -7)][::-1]
        peak = max(weeks + [1])
        body = [f"last {n} days (data as of {data['generated_at'][:16].replace('T', ' ')} UTC)",
                f"{'contributions':<18}{total}", f"{'active days':<18}{active} / {len(days)}",
                f"{'longest streak':<18}{longest} day{'s' if longest != 1 else ''}"]
        if best and best[1]:
            body.append(f"{'busiest day':<18}{best[0]} ({best[1]})")
        body.append(f"{'per week':<18}" + "".join(SPARK[min(7, int(w / peak * 7.99))] if w else "·" for w in weeks))
    elif cmd == "langs":
        for l in data["languages"]:
            k = max(1, round(l["share"] * 30))
            body.append(f"{l['name']:<14}{'█' * k}{'░' * (30 - k)} {l['share'] * 100:.0f}%")
        if data.get("languages_excluded"):
            body.append(f"excludes {', '.join(data['languages_excluded'])}")
    elif cmd == "clusters":
        for c in data["clusters"]:
            members = [r["name"] for r in repos if r["cluster"] == c["id"]]
            body += [f"{c['label']} ({len(members)})", f"  terms: {' · '.join(c['terms'][:5])}", f"  repos: {', '.join(members)}", ""]
        extra = f"\n\n→ [Drag these clusters around on the live map]({SITE}#map)"
    elif cmd == "stack":
        body = [f"{k + ':':<12}{v}" for k, v in data["stack"].items()]
    elif cmd == "experience":
        for x in data["experience"]:
            body.append(f"{x['when']:<22}{x['role']} · {x['org']}")
            body += [f"{'':<22}– {n}" for n in x["notes"]]
    elif cmd in ("contact", "sudo"):
        if cmd == "sudo":
            body = ["[sudo] access granted.", ""]
        body += [f"{'linkedin':<10}{ident['linkedin']}", f"{'email':<10}{ident['email']}", f"{'github':<10}https://github.com/{data['login']}"]
    elif cmd == "random":
        pool = [r for r in repos if r["description"] and not r.get("archived")]
        r = random.Random(f"{user}{now:%Y%m%d%H%M}").choice(pool)
        return respond("cat", [r["name"]], data, user, repo_slug, None, now).replace(f"$ cat {r['name']}", "$ random", 1)
    elif cmd == "neofetch":
        total = sum(c for _, c in data["calendar"])
        body = [f"{data['login']}@agent", "─" * 24,
                f"{'role':<10}{ident['headline']} · {ident['current_role']} @ {ident['current_org']}",
                f"{'repos':<10}{len(repos)} public",
                f"{'activity':<10}{total} contributions in 12 months",
                f"{'langs':<10}{', '.join(l['name'] for l in data['languages'][:3])}",
                f"{'site':<10}{SITE}"]
    else:
        body = ["command not found. Only these commands run here:", "", ", ".join(COMMANDS)]

    nxt = [c for c in ("whoami", "ls", "stats 90", "cat praxis", "clusters", "contact") if c != display(cmd, args)][:4]
    links = " · ".join(f"[`{c}`]({run_link(repo_slug, c)})" for c in nxt)
    return (f"{_block([prompt, *body])}{extra}\n\n"
            f"<sub>🤖 Answered by Nikhil's profile agent (a GitHub Action) and closed automatically. "
            f"Run another: {links} · or type freely in the [interactive terminal]({SITE}#terminal).</sub>")


def sessions_section(issues: list[dict], data: dict, repo_slug: str, limit: int = 6) -> str:
    """README block: totals plus the latest runs, newest first."""
    runs = []
    for it in issues:
        parsed = parse(it["title"], data)
        if parsed is None or not SAFE_LOGIN.fullmatch(it["user"] or ""):
            continue
        runs.append((it["user"], display(*parsed), it["created_at"]))
    if not runs:
        return "_No runs yet. Be the first: click a command above._"
    visitors = len({u.lower() for u, _, _ in runs})
    out = [f"**{len(runs):,} command{'s' if len(runs) != 1 else ''}** run by **{visitors:,} visitor{'s' if visitors != 1 else ''}** so far. Latest:", "",
           "| Visitor | Ran | When (UTC) |", "| :-- | :-- | :-- |"]
    for user, shown, at in runs[:limit]:
        out.append(f"| [@{user}](https://github.com/{user}) | `{shown}` | {at[:16].replace('T', ' ')} |")
    return "\n".join(out)
