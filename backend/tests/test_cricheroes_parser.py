"""Parser tests using markup mirroring the live CricHeroes match cards.

The class names below copy the real hashed CSS-module format
(``styles-module-scss-module__<hash>__<name>``) so the tests fail if the parser
ever starts depending on the volatile hash segment.
"""

from app.services.cricheroes.parser import (
    parse_matches_from_html,
    parse_matches_from_pages,
    parse_teams_from_html,
    parse_tournament_name_from_html,
)

P = "styles-module-scss-module__vScwrW__"
B = "styles-module-scss-module__ul8UIq__"


def _card(
    key: str,
    team_a: str,
    team_b: str,
    round_label: str,
    result: str,
    badge: str = "past",
    meta: str = "Tembekar Farm, Pune, 01-Feb-26, 8 Ov.,",
) -> str:
    return f"""
    <div class="{P}matchContainer {P}design4">
      <a href="/scorecard/{key}/mtpl-season-4/{team_a}-vs-{team_b}/summary">
        <div class="{P}matchCard {P}design4">
          <div class="{P}matchInfo ">
            <div><p> {meta} </p><div class="{P}round">{round_label}</div></div>
            <div class="{P}right"><span class="{B}badgeWrapper {B}past">{badge}</span></div>
          </div>
          <div class="{P}scoreWrapper">
            <div class="{P}teamWrapper">
              <div class="{P}teamName "><span class="{P}teamNameText">{team_a}</span></div>
              <div class="{P}oversWrapper"><span>(8.0)</span></div>
            </div>
            <div class="{P}teamWrapper">
              <div class="{P}teamName {P}active"><span class="{P}teamNameText">{team_b}</span></div>
              <div class="{P}oversWrapper"><span>(7.3)</span></div>
            </div>
          </div>
          <div class="{P}bottomInfo {P}design4"><span>{result}</span></div>
        </div>
      </a>
    </div>
    """


def _page(*cards: str, teams: list[str] | None = None) -> str:
    ld = ""
    if teams:
        performers = ",".join(f'{{"@type":"SportsTeam","name":"{t}"}}' for t in teams)
        ld = (
            '<script type="application/ld+json">'
            f'{{"@type":"SportsEvent","performer":[{performers}]}}'
            "</script>"
        )
    return f"<html><body>{ld}{''.join(cards)}</body></html>"


def test_parses_completed_match_fields():
    html = _page(
        _card(
            "22163275",
            "Markup Ultimate Warriors",
            "DC Strikers",
            "Final",
            "<b>DC Strikers</b> won by <b>8 wickets</b>",
        )
    )
    (m,) = parse_matches_from_html(html)

    assert m["cricheroes_match_key"] == "22163275"
    assert m["team_a_name"] == "Markup Ultimate Warriors"
    assert m["team_b_name"] == "DC Strikers"
    assert m["winner_name"] == "DC Strikers"
    assert m["status"] == "completed"
    assert m["stage"] == "final"
    assert m["stage_label"] == "Final"
    assert m["venue"] == "Tembekar Farm, Pune"
    assert m["overs"] == 8.0
    # 01-Feb-26 19:00 IST == 13:30 UTC
    assert m["start_time"].isoformat() == "2026-02-01T13:30:00+00:00"


def test_super_over_tie_resolves_a_winner():
    html = _page(
        _card(
            "22084006",
            "Markup Ultimate Warriors",
            "Surpluss Yoddha",
            "League Matches",
            "Match Tied ( Surpluss Yoddha won the super over)",
        )
    )
    (m,) = parse_matches_from_html(html)

    assert m["winner_name"] == "Surpluss Yoddha"
    assert m["status"] == "completed"


def test_abandoned_match_has_no_winner():
    html = _page(
        _card("999", "AB Mavericks", "Akizer XI", "League Matches", "Match abandoned due to rain")
    )
    (m,) = parse_matches_from_html(html)

    assert m["status"] == "no_result"
    assert m["winner_name"] is None


def test_upcoming_match_without_result():
    html = _page(
        _card(
            "1000",
            "AB Mavericks",
            "Akizer XI",
            "League Matches",
            "",
            badge="upcoming",
            meta="Tembekar Farm, Pune, 05-Feb-26, 09:30 AM, 8 Ov.,",
        )
    )
    (m,) = parse_matches_from_html(html)

    assert m["status"] == "upcoming"
    assert m["winner_name"] is None
    assert m["start_time"].isoformat() == "2026-02-05T04:00:00+00:00"


def test_stage_label_maps_to_stage_enum_values():
    html = _page(
        _card("1", "A Team", "B Team", "Quarter Final", "<b>B Team</b> won by 4 runs"),
        _card("2", "C Team", "D Team", "Semi Final", "<b>D Team</b> won by 4 runs"),
        _card("3", "E Team", "F Team", "Third Position", "<b>F Team</b> won by 4 runs"),
        _card("4", "G Team", "H Team", "League Matches", "<b>H Team</b> won by 4 runs"),
    )
    stages = {m["stage_label"]: m["stage"] for m in parse_matches_from_html(html)}

    assert stages == {
        "Quarter Final": "eliminator",
        "Semi Final": "qualifier",
        "Third Position": "eliminator",
        "League Matches": "league",
    }


def test_teams_come_from_json_ld():
    html = _page(teams=["AB Mavericks", "Akizer XI", "UM Warriors"])
    assert parse_teams_from_html(html) == ["AB Mavericks", "Akizer XI", "UM Warriors"]


def test_tournament_name_comes_from_json_ld():
    html = """
    <script type="application/ld+json">
      {"@type":"SportsEvent","name":"Big Bash League Season 5"}
    </script>
    """
    assert parse_tournament_name_from_html(html) == "Big Bash League Season 5"


def test_pages_are_merged_and_deduplicated():
    card = _card("22163275", "A Team", "B Team", "Final", "<b>B Team</b> won by 4 runs")
    other = _card("22163999", "C Team", "D Team", "Semi Final", "<b>D Team</b> won by 4 runs")

    merged = parse_matches_from_pages([_page(card), _page(card, other)])

    assert {m["cricheroes_match_key"] for m in merged} == {"22163275", "22163999"}


def test_empty_html_is_safe():
    assert parse_matches_from_html("") == []
    assert parse_teams_from_html("") == []
