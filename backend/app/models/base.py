"""Declarative base, naming conventions, shared helpers.

All timestamps are stored as naive UTC. Every table has an integer primary key
plus indexed created_at / updated_at columns.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import DateTime, ForeignKey, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedColumn, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Entity(Base):
    """Abstract parent: surrogate PK + created_at/updated_at."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=func.current_timestamp(), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow,
        server_default=func.current_timestamp())


def fk(target: str, ondelete: str, *, nullable: bool = False) -> MappedColumn[Any]:
    """Indexed foreign key with an explicit ON DELETE rule (CASCADE/SET NULL/RESTRICT)."""
    assert ondelete in {"CASCADE", "SET NULL", "RESTRICT"}
    return mapped_column(Integer, ForeignKey(target, ondelete=ondelete), nullable=nullable, index=True)


def in_list(column: str, values: Iterable[str]) -> str:
    """SQL text for a CHECK ... IN (...) constraint."""
    return f"{column} IN ({', '.join(repr(v) for v in values)})"
