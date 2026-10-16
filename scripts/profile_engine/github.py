"""Thin GitHub GraphQL client that collects everything the profile renders."""

from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request

API = "https://api.github.com/graphql"
README_CHARS = 6000

REPOS_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    repositories(first: 50, after: $cursor, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name description url isPrivate isArchived createdAt pushedAt stargazerCount
        primaryLanguage { name color }
        repositoryTopics(first: 12) { nodes { topic { name } } }
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
        readme: object(expression: "HEAD:README.md") { ... on Blob { text } }
      }
    }
  }
}
"""

CALENDAR_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionYears
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

YEAR_TOTAL_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar { totalContributions }
    }
  }
}
"""


class GitHub:
    def __init__(self, token: str):
        self.token = token

    def query(self, query: str, **variables) -> dict:
        body = json.dumps({"query": query, "variables": variables}).encode()
        for attempt in range(4):
            req = urllib.request.Request(API, data=body, headers={
                "Authorization": f"bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "profile-engine",
            })
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.load(resp)
            except urllib.error.HTTPError as err:
                if err.code >= 500 and attempt < 3:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise
            if payload.get("errors"):
                raise RuntimeError(f"GraphQL error: {payload['errors']}")
            return payload["data"]
        raise RuntimeError("GitHub API kept failing")


def _iso(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(token: str, login: str, now: dt.datetime) -> dict:
    """Return a plain-JSON snapshot of the user's repos and contribution history."""
    gh = GitHub(token)

    repos, cursor = [], None
    while True:
        data = gh.query(REPOS_QUERY, login=login, cursor=cursor)["user"]
        page = data["repositories"]
        for node in page["nodes"]:
            readme = (node.pop("readme") or {}).get("text") or ""
            node["readme"] = readme[:README_CHARS]
            node["topics"] = [t["topic"]["name"] for t in node.pop("repositoryTopics")["nodes"]]
            node["languages"] = [
                {"name": e["node"]["name"], "color": e["node"]["color"], "size": e["size"]}
                for e in node["languages"]["edges"]
            ]
            repos.append(node)
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    start = (now - dt.timedelta(days=364)).replace(hour=0, minute=0, second=0, microsecond=0)
    coll = gh.query(CALENDAR_QUERY, login=login, **{"from": _iso(start), "to": _iso(now)})
    coll = coll["user"]["contributionsCollection"]
    days = [d for w in coll["contributionCalendar"]["weeks"] for d in w["contributionDays"]]

    lifetime = 0
    for year in coll["contributionYears"]:
        y0 = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        y1 = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now)
        res = gh.query(YEAR_TOTAL_QUERY, login=login, **{"from": _iso(y0), "to": _iso(y1)})
        lifetime += res["user"]["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    return {
        "login": login,
        "name": data.get("name"),
        "fetched_at": _iso(now),
        "repos": repos,
        "calendar": [{"date": d["date"], "count": d["contributionCount"]} for d in days],
        "lifetime_contributions": lifetime,
        "restricted_contributions": coll["restrictedContributionsCount"],
    }
