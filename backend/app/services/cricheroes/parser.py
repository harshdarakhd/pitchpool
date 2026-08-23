"""Parse CricHeroes tournament HTML into normalized match dicts.

CricHeroes renders match cards server-side with hashed CSS-module class names
(e.g. ``styles-module-scss-module__vScwrW__matchCard``). The hash segment changes
between deploys, so every selector here matches on the stable *suffix* only.

Runs/wickets are painted into a ``<canvas>`` and are therefore not extractable;
the winner and margin come from the result line instead, which is all the
bidding engine needs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# CricHeroes round label -> internal stage enum value
STAGE_MAP: dict[str, str] = {
    "final": "final",
    "third position": "eliminator",
    "3rd position": "eliminator",
    "semi final": "qualifier",
    "semifinal": "qualifier",
    "quarter final": "eliminator",
    "quarterfinal": "eliminator",
    "eliminator": "eliminator",
    "qualifier": "qualifier",
    "league matches": "league",
    "league": "league",
    "group": "league",
    "super over": "league",
}

_DATE_RE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{2,4}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*(?:AM|PM)$", re.IGNORECASE)
_OVERS_RE = re.compile(r"^([\d.]+)\s*Ov\.?$", re.IGNORECASE)
_SCORECARD_RE = re.compile(r"/scorecard/(\d+)")
_WON_RE = re.compile(r"^(.*?)\s+won\s+by\s+(.+?)\s*$", re.IGNORECASE)
# "Match Tied ( Surpluss Yoddha won the super over)" -> the super-over side wins.
_SUPER_OVER_RE = re.compile(r"([A-Za-z0-9][^()]*?)\s+won\s+the\s+super\s+over", re.IGNORECASE)
_NO_RESULT_RE = re.compile(r"abandon|no result|cancel|wash(?:ed)?\s*out", re.IGNORECASE)


def _cls_endswith(suffix: str):
    """Match elements whose class list has an entry ending in ``suffix``."""

    def _pred(value: Any) -> bool:
        if not value:
            return False
        classes = value if isinstance(value, list) else str(value).split()
        return any(c.endswith(suffix) for c in classes)

    return _pred


def _find(node: Tag, suffix: str, name: str | None = None) -> Tag | None:
    return node.find(name, class_=_cls_endswith(suffix))


def _find_all(node: Tag, suffix: str, name: str | None = None) -> list[Tag]:
    return node.find_all(name, class_=_cls_endswith(suffix))


def _text(node: Tag | None) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def _parse_meta(meta: str) -> tuple[str | None, datetime | None, float | None]:
    """Split ``"Tembekar Farm, Pune, 01-Feb-26, 8 Ov.,"`` into venue/start/overs."""
    parts = [p.strip() for p in meta.split(",") if p.strip()]
    venue_parts: list[str] = []
    date_str: str | None = None
    time_str: str | None = None
    overs: float | None = None

    for part in parts:
        if _DATE_RE.match(part):
            date_str = part
            continue
        if _TIME_RE.match(part):
            time_str = part
            continue
        m = _OVERS_RE.match(part)
        if m:
            try:
                overs = float(m.group(1))
            except ValueError:
                pass
            continue
        if date_str is None:
            venue_parts.append(part)

    start: datetime | None = None
    if date_str:
        for fmt in ("%d-%b-%y", "%d-%b-%Y"):
            try:
                parsed = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                parsed = None
        else:
            parsed = None
        if parsed:
            if time_str:
                try:
                    t = datetime.strptime(time_str.upper().replace(" ", ""), "%I:%M%p").time()
                except ValueError:
                    t = time(19, 0)
            else:
                # Cards omit the time for completed matches; use a stable evening slot.
                t = time(19, 0)
            start = datetime.combine(parsed.date(), t, tzinfo=IST).astimezone(UTC)

    venue = ", ".join(venue_parts) or None
    return venue, start, overs


def _parse_card(card: Tag, index: int) -> dict[str, Any] | None:
    anchor = card.find("a", href=_SCORECARD_RE)
    href = anchor.get("href", "") if anchor else ""
    key_match = _SCORECARD_RE.search(href)

    team_nodes = _find_all(card, "teamNameText")
    teams = [_text(t) for t in team_nodes if _text(t)]
    if len(teams) < 2:
        return None
    team_a, team_b = teams[0], teams[1]

    if not key_match:
        # Fall back to a deterministic key so re-syncs stay idempotent.
        slug = re.sub(r"[^a-z0-9]+", "-", f"{team_a}-{team_b}".lower()).strip("-")
        cricheroes_key = f"slug:{slug}:{index}"
    else:
        cricheroes_key = key_match.group(1)

    meta = _text(_find(card, "matchInfo"))
    meta_p = _find(card, "matchInfo")
    if meta_p:
        p = meta_p.find("p")
        if p:
            meta = _text(p)
    venue, start, overs = _parse_meta(meta)

    round_label = _text(_find(card, "__round")) or _text(_find(card, "round"))
    stage = STAGE_MAP.get(round_label.strip().lower(), "league")

    badge = _text(_find(card, "badgeWrapper")).lower()
    result_raw = _text(_find(card, "bottomInfo")) or None

    winner_name: str | None = None
    status = "upcoming"

    def _match_team(candidate: str) -> str:
        candidate = candidate.strip()
        for name in (team_a, team_b):
            if candidate.lower() == name.lower():
                return name
        return candidate

    if result_raw and _NO_RESULT_RE.search(result_raw):
        status = "no_result"
    elif result_raw:
        super_over = _SUPER_OVER_RE.search(result_raw)
        won = _WON_RE.match(result_raw)
        if super_over:
            winner_name = _match_team(super_over.group(1))
            status = "completed"
        elif won:
            winner_name = _match_team(won.group(1))
            status = "completed"

    if status == "upcoming":
        if "past" in badge or "complet" in badge:
            status = "completed" if winner_name else "no_result"
        elif "live" in badge:
            status = "locked"

    # Overs are rendered per-innings; a card without a result but marked past is
    # still treated as finished so it never sits in the bidding queue forever.
    overs_val = overs

    return {
        "cricheroes_match_key": str(cricheroes_key),
        "team_a_name": team_a,
        "team_b_name": team_b,
        "winner_name": winner_name,
        "status": status,
        "venue": venue,
        "start_time": start,
        "result_raw": result_raw,
        "stage": stage,
        "stage_label": round_label or None,
        "overs": overs_val,
        "scorecard_url": href or None,
    }


def parse_teams_from_html(html: str) -> list[str]:
    """Pull the full team roster from the page's JSON-LD block."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    teams: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw or "SportsTeam" not in raw:
            continue
        for name in re.findall(r'"@type"\s*:\s*"SportsTeam"\s*,\s*"name"\s*:\s*"([^"]+)"', raw):
            if name not in teams:
                teams.append(name)
    return teams


def parse_tournament_name_from_html(html: str) -> str | None:
    """Read the canonical tournament name from CricHeroes JSON-LD metadata."""
    if not html:
        return None
    soup = BeautifulSoup(html, "lxml")
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("@type") == "SportsEvent"
                and isinstance(item.get("name"), str)
            ):
                return item["name"].strip() or None
    return None


def _team_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("name", "team_name", "teamName", "full_name", "fullName"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return ""


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts /= 1000.0
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return _coerce_datetime(int(text))
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _looks_like_api_match(item: dict[str, Any]) -> bool:
    keys = {str(k).lower() for k in item}
    has_id = bool(keys & {"id", "match_id", "matchid", "match_key"})
    has_teams = any("team" in k for k in keys)
    return has_id and has_teams


def _walk_api_matches(payload: Any, found: list[dict[str, Any]]) -> None:
    if isinstance(payload, list):
        if payload and isinstance(payload[0], dict) and _looks_like_api_match(payload[0]):
            found.extend(item for item in payload if isinstance(item, dict))
            return
        for item in payload:
            _walk_api_matches(item, found)
        return
    if isinstance(payload, dict):
        for value in payload.values():
            _walk_api_matches(value, found)


def _status_from_api(item: dict[str, Any], winner: str | None) -> str:
    raw = item.get("status") or item.get("match_status") or item.get("matchStatus") or ""
    text = str(raw).lower()
    if any(token in text for token in ("abandon", "no result", "cancel", "wash")):
        return "no_result"
    if any(token in text for token in ("complete", "past", "result")) or winner:
        return "completed"
    if any(token in text for token in ("live", "progress")):
        return "locked"
    numeric = item.get("status_id") or item.get("match_status_id")
    if numeric == 2:
        return "completed"
    if numeric == 1:
        return "locked"
    return "upcoming"


def parse_matches_from_api_payloads(payloads: list[Any]) -> list[dict[str, Any]]:
    """Normalize captured CricHeroes XHR JSON into the same dicts as HTML cards."""
    raw_matches: list[dict[str, Any]] = []
    for payload in payloads:
        _walk_api_matches(payload, raw_matches)

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_matches:
        match_id = item.get("id") or item.get("match_id") or item.get("matchId") or item.get("match_key")
        team_a = (
            _team_name(item.get("team_a"))
            or _team_name(item.get("teamA"))
            or _team_name(item.get("team_a_name"))
            or _team_name(item.get("teamAName"))
            or _team_name(item.get("team1"))
        )
        team_b = (
            _team_name(item.get("team_b"))
            or _team_name(item.get("teamB"))
            or _team_name(item.get("team_b_name"))
            or _team_name(item.get("teamBName"))
            or _team_name(item.get("team2"))
        )
        if not match_id or not team_a or not team_b:
            continue
        key = str(match_id)
        if key in seen:
            continue
        seen.add(key)
        winner = (
            _team_name(item.get("winner"))
            or _team_name(item.get("winner_team"))
            or _team_name(item.get("winning_team"))
            or None
        ) or None
        start = (
            _coerce_datetime(item.get("start_time"))
            or _coerce_datetime(item.get("startTime"))
            or _coerce_datetime(item.get("match_start_time"))
            or _coerce_datetime(item.get("datetime"))
            or _coerce_datetime(item.get("date"))
        )
        result_raw = item.get("result") or item.get("result_str") or item.get("resultString")
        matches.append(
            {
                "cricheroes_match_key": key,
                "team_a_name": team_a,
                "team_b_name": team_b,
                "winner_name": winner,
                "status": _status_from_api(item, winner),
                "venue": item.get("venue") or item.get("ground") or item.get("location"),
                "start_time": start,
                "result_raw": str(result_raw) if result_raw else None,
                "stage": "league",
                "stage_label": item.get("round") or item.get("round_name") or item.get("stage"),
                "overs": None,
                "scorecard_url": item.get("scorecard_url") or item.get("url"),
            }
        )
    logger.info("Parsed %d CricHeroes matches from captured API JSON", len(matches))
    return matches


def parse_matches_from_html(html: str) -> list[dict[str, Any]]:
    """Extract match data from a rendered CricHeroes tournament matches page."""
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_=_cls_endswith("matchContainer"))
    if not cards:
        cards = soup.find_all("div", class_=_cls_endswith("matchCard"))

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()

    for i, card in enumerate(cards):
        try:
            parsed = _parse_card(card, i)
        except Exception:
            logger.exception("Failed to parse CricHeroes match card %d", i)
            continue
        if not parsed:
            continue
        key = parsed["cricheroes_match_key"]
        if key in seen:
            continue
        seen.add(key)
        matches.append(parsed)

    captured = soup.find("script", id="pitchpool-captured-api")
    if captured and captured.string:
        try:
            payloads = json.loads(captured.string)
        except json.JSONDecodeError:
            payloads = []
        if isinstance(payloads, list):
            for item in parse_matches_from_api_payloads(payloads):
                key = item["cricheroes_match_key"]
                if key in seen:
                    continue
                seen.add(key)
                matches.append(item)

    logger.info("Parsed %d CricHeroes matches from %d cards", len(matches), len(cards))
    return matches


def parse_matches_from_pages(pages: list[str]) -> list[dict[str, Any]]:
    """Parse several tab documents, de-duplicating on the CricHeroes match id."""
    merged: dict[str, dict[str, Any]] = {}
    for page in pages:
        for item in parse_matches_from_html(page):
            merged.setdefault(item["cricheroes_match_key"], item)
    return list(merged.values())
