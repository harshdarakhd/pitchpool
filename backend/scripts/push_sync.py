"""Scrape CricHeroes locally and push fixtures to the deployed site.

CricHeroes serves a Cloudflare challenge to datacenter IPs, so Render cannot
scrape itself. Run this from a home/office connection.

  python scripts/push_sync.py
  python scripts/push_sync.py --loop --interval 600

`--loop` keeps watching: it syncs on a timer and immediately when you tap
**Sync from my PC** on the phone Admin page.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.cricheroes.client import fetch_all_match_tabs  # noqa: E402
from app.services.cricheroes.parser import (  # noqa: E402
    parse_matches_from_pages,
    parse_teams_from_html,
)
from app.services.tournaments import parse_tournament_ref  # noqa: E402


def _headers(secret: str) -> dict[str, str]:
    return {"X-Cron-Secret": secret}


async def pending_requested(client: httpx.AsyncClient, target: str, secret: str) -> bool:
    response = await client.get(
        f"{target}/internal/cron/pending-sync",
        headers=_headers(secret),
        timeout=30,
    )
    if response.status_code != 200:
        return False
    return bool(response.json().get("pending"))


async def scrape_and_push(*, ref: str, target: str, secret: str, dry_run: bool) -> int:
    cricheroes_id, _slug, base_url = parse_tournament_ref(ref)
    print(f"Scraping {base_url}")

    pages = await fetch_all_match_tabs(base_url)
    if not pages:
        print("Scrape returned nothing — Cloudflare blocked this machine too.", file=sys.stderr)
        return 1

    teams = parse_teams_from_html(pages[0])
    matches = [m for m in parse_matches_from_pages(pages) if m.get("start_time")]
    statuses: dict[str, int] = {}
    for m in matches:
        statuses[m["status"]] = statuses.get(m["status"], 0) + 1
    print(f"Found {len(teams)} teams and {len(matches)} dated matches: {statuses}")

    if not matches:
        print("Nothing to push.", file=sys.stderr)
        return 1

    payload = {
        "cricheroes_id": cricheroes_id,
        "teams": teams,
        "matches": [
            {
                "cricheroes_match_key": m["cricheroes_match_key"],
                "team_a_name": m["team_a_name"],
                "team_b_name": m["team_b_name"],
                "start_time": m["start_time"].isoformat(),
                "status": m["status"],
                "winner_name": m.get("winner_name"),
                "venue": m.get("venue"),
                "result_raw": m.get("result_raw"),
                "stage": m.get("stage", "league"),
                "stage_label": m.get("stage_label"),
            }
            for m in matches
        ],
    }

    if dry_run:
        print("Dry run — not sending.")
        return 0

    if not target or not secret:
        print("Set PITCHPOOL_URL and PITCHPOOL_CRON_SECRET (or --url/--secret).", file=sys.stderr)
        return 1

    print(f"Pushing to {target}/internal/cron/import")
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(1, 20):
            response = await client.post(
                f"{target}/internal/cron/import",
                json=payload,
                headers=_headers(secret),
            )
            if response.status_code != 409 or "already running" not in response.text:
                break
            print(f"  sync lock held, retrying in 60s (attempt {attempt})")
            await asyncio.sleep(60)

    if response.status_code != 200:
        print(f"Failed: HTTP {response.status_code} {response.text}", file=sys.stderr)
        return 1

    run = response.json()
    print(
        f"Import {run['status']}: {run['matches_seen']} seen, "
        f"{run['matches_updated']} written"
    )
    if run.get("error"):
        print(f"  error: {run['error']}", file=sys.stderr)
        return 1
    return 0


async def run_loop(*, ref: str, target: str, secret: str, interval: int) -> int:
    if not target or not secret:
        print("Set PITCHPOOL_URL and PITCHPOOL_CRON_SECRET (or --url/--secret).", file=sys.stderr)
        return 1

    print(f"Agent running. Timer every {interval}s; phone Admin tap syncs immediately.")
    await scrape_and_push(ref=ref, target=target, secret=secret, dry_run=False)
    elapsed = 0
    poll = 30
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            await asyncio.sleep(poll)
            elapsed += poll
            try:
                requested = await pending_requested(client, target, secret)
            except Exception as exc:
                print(f"  pending-sync check failed: {exc}", file=sys.stderr)
                requested = False
            if requested or elapsed >= interval:
                reason = "phone request" if requested else "timer"
                print(f"Starting sync ({reason})")
                await scrape_and_push(ref=ref, target=target, secret=secret, dry_run=False)
                elapsed = 0


async def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Push locally scraped fixtures to production.")
    parser.add_argument(
        "--ref",
        default=settings.cricheroes_base_url or str(settings.cricheroes_tournament_id),
        help="CricHeroes tournament URL or numeric ID",
    )
    parser.add_argument("--url", default="", help="deployed base URL (or PITCHPOOL_URL)")
    parser.add_argument("--secret", default="", help="CRON_SECRET (or PITCHPOOL_CRON_SECRET)")
    parser.add_argument("--dry-run", action="store_true", help="scrape and report, send nothing")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="stay running: timer plus phone Admin 'Sync from my PC'",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        help="seconds between automatic syncs in --loop (default 600)",
    )
    args = parser.parse_args()

    target = (args.url or os.environ.get("PITCHPOOL_URL", "")).rstrip("/")
    secret = args.secret or os.environ.get("PITCHPOOL_CRON_SECRET", "")

    if args.loop:
        return await run_loop(ref=args.ref, target=target, secret=secret, interval=max(60, args.interval))
    return await scrape_and_push(ref=args.ref, target=target, secret=secret, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
