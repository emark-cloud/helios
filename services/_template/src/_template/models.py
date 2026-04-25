"""Postgres schema v0. Shared across services.

Each service may add service-specific tables in its own models module that
also inherits from `Base`. Phase 0 ships the canonical event-sourced schema
that the Reputation Engine, Sentinel, and Helix all read.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from _template.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    passport_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    operator: Mapped[str] = mapped_column(String(42), index=True)
    declared_class: Mapped[str] = mapped_column(String(64), index=True)
    chain_id: Mapped[int] = mapped_column(Integer)
    stake_amount: Mapped[int] = mapped_column(Numeric(78, 0))
    fee_rate_bps: Mapped[int] = mapped_column(Integer)
    max_capacity: Mapped[int] = mapped_column(Numeric(78, 0))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Allocator(Base):
    __tablename__ = "allocators"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    operator: Mapped[str] = mapped_column(String(42), index=True)
    fee_rate_bps: Mapped[int] = mapped_column(Integer)
    stake_amount: Mapped[int] = mapped_column(Numeric(78, 0))
    is_reference_brand: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Allocation(Base):
    __tablename__ = "allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    allocator_id: Mapped[int] = mapped_column(ForeignKey("allocators.id"))
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    capital_deployed: Mapped[int] = mapped_column(Numeric(78, 0))
    high_water_mark: Mapped[int] = mapped_column(Numeric(78, 0))
    last_rebalance_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    defunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (Index("idx_trades_strategy_time", "strategy_id", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    allocator_id: Mapped[int] = mapped_column(ForeignKey("allocators.id"))
    chain_id: Mapped[int] = mapped_column(Integer)
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True)
    trade_hash: Mapped[str] = mapped_column(String(66))
    proof_hash: Mapped[str] = mapped_column(String(66))
    proof_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    asset_in: Mapped[str] = mapped_column(String(42))
    asset_out: Mapped[str] = mapped_column(String(42))
    amount_in: Mapped[int] = mapped_column(Numeric(78, 0))
    amount_out: Mapped[int] = mapped_column(Numeric(78, 0))
    direction: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NavSnapshot(Base):
    __tablename__ = "nav_snapshots"
    __table_args__ = (Index("idx_nav_strategy_time", "strategy_id", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    allocator_id: Mapped[int] = mapped_column(ForeignKey("allocators.id"))
    nav: Mapped[int] = mapped_column(Numeric(78, 0))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ReputationSnapshot(Base):
    __tablename__ = "reputation_snapshots"
    __table_args__ = (Index("idx_rep_actor_time", "actor", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor: Mapped[str] = mapped_column(String(42), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))  # "STRATEGY" | "ALLOCATOR"
    score: Mapped[int] = mapped_column(Integer)
    perf_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proof_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stake_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventLog(Base):
    """Generic event sink for the activity rail / Telegram bot / dashboard."""

    __tablename__ = "events"
    __table_args__ = (Index("idx_events_user_time", "user_address", "timestamp"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), index=True)
    user_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    strategy_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    allocator_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    chain_id: Mapped[int] = mapped_column(Integer)
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    payload: Mapped[str] = mapped_column(Text)  # JSON-encoded event-specific fields
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
