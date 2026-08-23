import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class MatchStage(str, enum.Enum):
    league = "league"
    qualifier = "qualifier"
    eliminator = "eliminator"
    final = "final"


class MatchStatus(str, enum.Enum):
    upcoming = "upcoming"
    locked = "locked"
    awaiting_result = "awaiting_result"
    completed = "completed"
    no_result = "no_result"


class TransactionType(str, enum.Enum):
    bid = "bid"
    payout = "payout"
    penalty = "penalty"
    quiz = "quiz"
    streak_bonus = "streak_bonus"
    season = "season"
    adjustment = "adjustment"
    refund = "refund"


class SeasonCategory(str, enum.Enum):
    winner = "winner"
    orange_cap = "orange_cap"
    purple_cap = "purple_cap"


class SeasonResult(str, enum.Enum):
    pending = "pending"
    won = "won"
    lost = "lost"


class TournamentStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cricheroes_id: Mapped[int] = mapped_column(Integer, index=True)
    slug: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500))
    display_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    status: Mapped[TournamentStatus] = mapped_column(
        Enum(TournamentStatus), default=TournamentStatus.active, index=True
    )
    team_count: Mapped[int] = mapped_column(Integer, default=0)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list["Team"]] = relationship(back_populates="tournament")
    matches: Mapped[list["Match"]] = relationship(back_populates="tournament")
    sync_runs: Mapped[list["SyncRun"]] = relationship(back_populates="tournament")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.user)
    points_balance: Mapped[int] = mapped_column(Integer, default=5000)
    starting_balance: Mapped[int] = mapped_column(Integer, default=5000)
    joined_match_index: Mapped[int] = mapped_column(Integer, default=0)
    refresh_token_jti: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bids: Mapped[list["Bid"]] = relationship(back_populates="user")
    streak: Mapped[Optional["Streak"]] = relationship(back_populates="user", uselist=False)
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("tournament_id", "name", name="uq_team_tournament_name"),
        UniqueConstraint("tournament_id", "short_name", name="uq_team_tournament_short_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    cricheroes_team_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(150))
    short_name: Mapped[str] = mapped_column(String(10))
    logo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    tournament: Mapped["Tournament"] = relationship(back_populates="teams")


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("tournament_id", "cricheroes_match_key", name="uq_match_tournament_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    cricheroes_match_key: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stage: Mapped[MatchStage] = mapped_column(Enum(MatchStage), default=MatchStage.league)
    # Verbatim CricHeroes round text ("Quarter Final", "Third Position", ...), which
    # is finer-grained than the stage enum used for bid limits.
    stage_label: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    team_a_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    team_b_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    venue: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bid_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[MatchStatus] = mapped_column(Enum(MatchStatus), default=MatchStatus.upcoming)
    winner_team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"), nullable=True)
    multiplier: Mapped[int] = mapped_column(Integer, default=1)
    result_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)

    tournament: Mapped["Tournament"] = relationship(back_populates="matches")
    team_a: Mapped["Team"] = relationship(foreign_keys=[team_a_id])
    team_b: Mapped["Team"] = relationship(foreign_keys=[team_b_id])
    winner_team: Mapped[Optional["Team"]] = relationship(foreign_keys=[winner_team_id])
    bids: Mapped[list["Bid"]] = relationship(back_populates="match")
    pools: Mapped[list["MatchPool"]] = relationship(back_populates="match")
    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(back_populates="match")


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    amount: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="bids")
    match: Mapped["Match"] = relationship(back_populates="bids")
    team: Mapped["Team"] = relationship()


class MatchPool(Base):
    __tablename__ = "match_pools"
    __table_args__ = (UniqueConstraint("match_id", "team_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    total_wager: Mapped[int] = mapped_column(Integer, default=0)
    bidder_count: Mapped[int] = mapped_column(Integer, default=0)

    match: Mapped["Match"] = relationship(back_populates="pools")
    team: Mapped["Team"] = relationship()


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[dict] = mapped_column(JSON)
    correct_option: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    points: Mapped[int] = mapped_column(Integer, default=100)
    locks_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    match: Mapped["Match"] = relationship(back_populates="quiz_questions")
    answers: Mapped[list["QuizAnswer"]] = relationship(back_populates="question")


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (UniqueConstraint("user_id", "question_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("quiz_questions.id"), index=True)
    chosen_option: Mapped[str] = mapped_column(String(10))
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    awarded_points: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    question: Mapped["QuizQuestion"] = relationship(back_populates="answers")


class SeasonBet(Base):
    __table_args__ = (UniqueConstraint("user_id", "category", "tournament_id"),)
    __tablename__ = "season_bets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    category: Mapped[SeasonCategory] = mapped_column(Enum(SeasonCategory))
    pick: Mapped[str] = mapped_column(String(200))
    locked_cap: Mapped[int] = mapped_column(Integer)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    result: Mapped[SeasonResult] = mapped_column(Enum(SeasonResult), default=SeasonResult.pending)
    payout: Mapped[int] = mapped_column(Integer, default=0)


class Streak(Base):
    __tablename__ = "streaks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    current: Mapped[int] = mapped_column(Integer, default=0)
    best: Mapped[int] = mapped_column(Integer, default=0)
    last_result_match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matches.id"), nullable=True)

    user: Mapped["User"] = relationship(back_populates="streak")


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    icon: Mapped[str] = mapped_column(String(20), default="🏅")


class UserBadge(Base):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id"))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    badge: Mapped["Badge"] = relationship()


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tournament_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tournaments.id"), nullable=True, index=True)
    match_id: Mapped[Optional[int]] = mapped_column(ForeignKey("matches.id"), nullable=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tournament_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tournaments.id"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    matches_seen: Mapped[int] = mapped_column(Integer, default=0)
    matches_updated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tournament: Mapped[Optional["Tournament"]] = relationship(back_populates="sync_runs")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
