// Real-time layer: polls GitHub's public events API from the visitor's browser.
// Unauthenticated calls allow 60/hour per visitor; ETag revalidation (304)
// doesn't count against that, and polling pauses while the tab is hidden.

import { emit } from "./util.js";

const POLL_MS = 60_000;
let etag = null;
let events = [];
let login = "";
let timer = null;

export const getEvents = () => events;

export async function poll() {
  try {
    const res = await fetch(`https://api.github.com/users/${login}/events/public?per_page=40`, {
      headers: etag ? { "If-None-Match": etag, Accept: "application/vnd.github+json" } : { Accept: "application/vnd.github+json" },
    });
    if (res.status === 304) return events;
    if (!res.ok) throw new Error(`GitHub API ${res.status}`);
    etag = res.headers.get("ETag");
    events = await res.json();
    emit("live", { events, ok: true });
  } catch (err) {
    emit("live", { events, ok: false, error: String(err.message || err) });
  }
  return events;
}

export function startLive(user) {
  login = user;
  poll();
  const tick = () => { if (document.visibilityState === "visible") poll(); };
  timer = setInterval(tick, POLL_MS);
  document.addEventListener("visibilitychange", tick);
}

const short = (repo) => repo.replace(`${login}/`, "");

// Turn a raw event into {kind, text, repo, detail, at}. Unknown types are skipped.
export function describe(ev) {
  const repo = short(ev.repo?.name || "");
  const p = ev.payload || {};
  const at = ev.created_at;
  switch (ev.type) {
    case "PushEvent": {
      const branch = (p.ref || "").replace("refs/heads/", "");
      const n = p.size ?? p.commits?.length;
      const msg = p.commits?.[p.commits.length - 1]?.message?.split("\n")[0];
      return { kind: "push", repo, at, text: n ? `pushed ${n} commit${n === 1 ? "" : "s"} to ${repo}` : `pushed to ${repo}${branch ? ` (${branch})` : ""}`, detail: msg };
    }
    case "CreateEvent":
      return { kind: "create", repo, at, text: p.ref_type === "repository" ? `created repository ${repo}` : `created ${p.ref_type} ${p.ref || ""} in ${repo}` };
    case "PublicEvent": return { kind: "create", repo, at, text: `made ${repo} public` };
    case "WatchEvent": return { kind: "star", repo, at, text: `starred ${repo}` };
    case "ForkEvent": return { kind: "fork", repo, at, text: `forked ${repo}` };
    case "ReleaseEvent": return { kind: "release", repo, at, text: `released ${p.release?.tag_name || ""} of ${repo}` };
    case "PullRequestEvent": return { kind: "pr", repo, at, text: `${p.action} pull request #${p.number} in ${repo}`, detail: p.pull_request?.title };
    case "IssuesEvent": return { kind: "issue", repo, at, text: `${p.action} issue #${p.issue?.number} in ${repo}`, detail: p.issue?.title };
    case "IssueCommentEvent": return { kind: "issue", repo, at, text: `commented on #${p.issue?.number} in ${repo}` };
    case "DeleteEvent": return { kind: "delete", repo, at, text: `deleted ${p.ref_type} ${p.ref} in ${repo}` };
    default: return null;
  }
}
