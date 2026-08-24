from datetime import datetime

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    points_balance: int
    starting_balance: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamResponse(BaseModel):
    id: int
    name: str
    short_name: str
    logo_url: str | None = None

    model_config = {"from_attributes": True}


class MatchPoolResponse(BaseModel):
    team_id: int
    team: TeamResponse
    total_wager: int
    bidder_count: int


class MatchSummary(BaseModel):
    id: int
    stage: str
    stage_label: str | None = None
    status: str
    venue: str | None
    start_time: datetime
    bid_deadline: datetime
    multiplier: int
    team_a: TeamResponse
    team_b: TeamResponse
    winner_team: TeamResponse | None = None
    result_raw: str | None = None


class MatchDetail(MatchSummary):
    pools: list[MatchPoolResponse] = []
    user_bid_count: int = 0
    user_bids: list["BidResponse"] = []


class BidResponse(BaseModel):
    id: int
    match_id: int
    team_id: int
    amount: int
    created_at: datetime
    team: TeamResponse | None = None

    model_config = {"from_attributes": True}


class PlaceBidRequest(BaseModel):
    match_id: int
    team_id: int
    amount: int = Field(gt=0)


class BidValidationHint(BaseModel):
    min_amount: int
    max_bids: int
    current_bids: int
    allowed_team_b_range: tuple[int, int] | None = None
    message: str | None = None


class QuizQuestionResponse(BaseModel):
    id: int
    match_id: int
    text: str
    options: dict
    points: int
    locks_at: datetime
    user_answer: str | None = None

    model_config = {"from_attributes": True}


class QuizAnswerRequest(BaseModel):
    question_id: int
    chosen_option: str


class SeasonBetRequest(BaseModel):
    category: str
    pick: str


class SeasonBetResponse(BaseModel):
    id: int
    category: str
    pick: str
    locked_cap: int
    placed_at: datetime
    result: str
    payout: int
    current_cap: int | None = None

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    id: int
    type: str
    delta: int
    balance_after: int
    description: str | None
    created_at: datetime
    match_id: int | None = None

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    display_name: str
    points_balance: int
    win_rate: float
    current_streak: int
    best_streak: int
    badge_count: int


class ProfileStats(BaseModel):
    user: UserResponse
    win_rate: float
    wins: int
    losses: int
    net_profit: int
    current_streak: int
    best_streak: int
    badges: list[dict]
    streak_milestones: list[dict]


class MatchResultResponse(BaseModel):
    match: MatchSummary
    profit_pool: int
    user_payout: int | None = None
    user_net: int | None = None


class SyncRunResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime | None
    status: str
    matches_seen: int
    matches_updated: int
    error: str | None = None

    model_config = {"from_attributes": True}


class AdminMatchOverride(BaseModel):
    status: str | None = None
    winner_team_id: int | None = None
    result_raw: str | None = None


class ImportMatch(BaseModel):
    cricheroes_match_key: str
    team_a_name: str
    team_b_name: str
    start_time: datetime
    status: str = "upcoming"
    winner_name: str | None = None
    venue: str | None = None
    result_raw: str | None = None
    stage: str = "league"
    stage_label: str | None = None


class ImportRequest(BaseModel):
    """Fixtures scraped by a trusted client (see scripts/push_sync.py)."""

    cricheroes_id: int | None = Field(
        default=None,
        description="Rejected unless it matches the active tournament",
    )
    teams: list[str] = Field(default_factory=list)
    matches: list[ImportMatch]


class TournamentPreviewRequest(BaseModel):
    ref: str = Field(description="CricHeroes tournament ID or canonical URL")


class TournamentActivateRequest(BaseModel):
    ref: str
    confirm_reset: bool = False


class TournamentResponse(BaseModel):
    id: int
    cricheroes_id: int
    slug: str
    base_url: str
    display_name: str | None
    status: str
    team_count: int
    match_count: int
    activated_at: datetime | None
    activated_by_user_id: int | None
    archived_at: datetime | None
    archived_by_user_id: int | None
    last_sync_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TournamentPreviewResponse(BaseModel):
    cricheroes_id: int
    slug: str
    base_url: str
    display_name: str
    teams: list[str]
    match_count: int
    status_counts: dict[str, int]
    biddable_count: int
    earliest_start: datetime | None
    latest_start: datetime | None


class TournamentActivateResponse(BaseModel):
    tournament: TournamentResponse
    sync_status: str
    matches_seen: int
    matches_updated: int


class QuizCreateRequest(BaseModel):
    match_id: int
    text: str
    options: dict
    correct_option: str | None = None
    points: int = 100
