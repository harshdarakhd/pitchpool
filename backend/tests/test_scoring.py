import pytest

from app.services.bidding import validate_gap
from app.services.scoring import (
    STREAK_MILESTONES,
    compute_late_join_balance,
    effective_pick_team,
    non_bid_penalty,
    season_cap_for_date,
)
from app.db.models import MatchStage
from datetime import date


class FakeBid:
    def __init__(self, team_id: int, amount: int):
        self.team_id = team_id
        self.amount = amount


def test_validate_gap_pass():
    assert validate_gap(200, 100) is True
    assert validate_gap(200, 140) is True


def test_validate_gap_fail_equal():
    assert validate_gap(200, 200) is False


def test_validate_gap_fail_within_30():
    assert validate_gap(200, 180) is False


def test_effective_pick_single_team():
    bids = [FakeBid(1, 100), FakeBid(1, 200)]
    assert effective_pick_team(bids) == 1


def test_effective_pick_largest_wager():
    bids = [FakeBid(1, 100), FakeBid(2, 300)]
    assert effective_pick_team(bids) == 2


def test_late_join_penalty():
    assert compute_late_join_balance(0) == 5000
    assert compute_late_join_balance(10) == 4000
    assert compute_late_join_balance(100) == 500


def test_non_bid_penalty():
    assert non_bid_penalty(MatchStage.league, 1000) == 100
    assert non_bid_penalty(MatchStage.qualifier, 1000) == 300
    assert non_bid_penalty(MatchStage.final, 1000) == 1000


def test_streak_milestones():
    assert STREAK_MILESTONES[7] == 500
    assert STREAK_MILESTONES[25] == 5000


def test_season_cap_decay():
    cap_day1 = season_cap_for_date(date(2026, 4, 17))
    cap_mid = season_cap_for_date(date(2026, 5, 5))
    cap_end = season_cap_for_date(date(2026, 5, 24))
    assert cap_day1 == 5000
    assert cap_mid < cap_day1
    assert cap_end == 250
