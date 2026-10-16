"""Regenerate the live profile: fetch GitHub data, render cards, patch README.

    GITHUB_TOKEN=... python scripts/build_profile.py              # live data
    python scripts/build_profile.py --snapshot data.json          # offline render
    python scripts/build_profile.py --save-snapshot data.json     # keep raw data for debugging

Outputs are only rewritten when something other than the clock changed, so
the hourly job commits when your activity actually moves.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from profile_engine import cards, latent, metrics, readme  # noqa: E402
from profile_engine.github import fetch  # noqa: E402

ASSETS = ROOT / "assets"
FINGERPRINT = ASSETS / ".fingerprint"


def render(m: metrics.Metrics, config: dict) -> tuple[dict[str, str], dict[str, str]]:
    """Return (asset files, README live sections)."""
    points, clusters = latent.embed(m.public_repos, config["latent_space"]["labels"])
    files = {}
    for mode in ("dark", "light"):
        files[f"agent-trace-{mode}.svg"] = cards.agent_trace(m, config["identity"], mode)
        files[f"latent-space-{mode}.svg"] = cards.latent_map(points, clusters, m, mode)
        files[f"training-run-{mode}.svg"] = cards.training_run(m, mode)
        files[f"training-history-{mode}.svg"] = cards.training_history(m, mode)
    return files, readme.sections(m, points, clusters)


def fingerprint(m: metrics.Metrics, config: dict) -> str:
    """Hash of the outputs with the clock pinned to midnight, so hour-only changes don't count."""
    day = m.generated_at.replace(hour=0, minute=0, second=0, microsecond=0)
    files, live = render(dataclasses.replace(m, generated_at=day), config)
    blob = "".join(v for _, v in sorted(files.items())) + "".join(v for _, v in sorted(live.items()))
    return hashlib.sha256(blob.encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, help="render from a saved snapshot instead of the API")
    ap.add_argument("--save-snapshot", type=Path, help="write the fetched raw data here")
    ap.add_argument("--force", action="store_true", help="rewrite outputs even if nothing changed")
    args = ap.parse_args()

    config = tomllib.loads((ROOT / "profile.toml").read_text())

    if args.snapshot:
        snapshot = json.loads(args.snapshot.read_text())
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("Set GITHUB_TOKEN (or pass --snapshot).")
        snapshot = fetch(token, config["login"], dt.datetime.now(dt.timezone.utc),
                         repo_token=os.environ.get("PROFILE_TOKEN") or None)
        if args.save_snapshot:
            args.save_snapshot.write_text(json.dumps(snapshot, indent=1))

    m = metrics.compute(snapshot, config)
    print(f"{len(m.public_repos)} public repos · {m.contributions_30d} contributions in 30d · "
          f"streak {m.current_streak} · private data {'included' if m.includes_private else 'not visible'}")

    fp = fingerprint(m, config)
    if not args.force and FINGERPRINT.exists() and FINGERPRINT.read_text().strip() == fp:
        print("No change since last render; leaving files untouched.")
        return 0

    ASSETS.mkdir(exist_ok=True)
    files, live = render(m, config)
    for name, svg in files.items():
        (ASSETS / name).write_text(svg)
    readme_path = ROOT / "README.md"
    readme_path.write_text(readme.update(readme_path.read_text(), m, live))
    FINGERPRINT.write_text(fp + "\n")
    print("Profile updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
