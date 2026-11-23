"""Users, projects, source files, functions, settings, activity log (tables 1-4, 18, 19)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Entity, fk, in_list

PROJECT_STATUSES = ("active", "archived")
FUNCTION_KINDS = ("function", "async_function", "method", "async_method")


class User(Entity):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("is_local_user = 1 OR password_hash IS NOT NULL", name="local_or_password"),
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))  # never plain text
    display_name: Mapped[Optional[str]] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    is_local_user: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class Project(Entity):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_projects_user_id_slug"),
        UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),
        CheckConstraint(in_list("status", PROJECT_STATUSES), name="status_valid"),
    )
    user_id: Mapped[int] = fk("users.id", "CASCADE")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")

    user: Mapped[User] = relationship(back_populates="projects")
    source_files: Mapped[list["SourceFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True)


class SourceFile(Entity):
    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("project_id", "rel_path", name="uq_source_files_project_id_rel_path"),
        CheckConstraint("size_bytes >= 0 AND line_count >= 0", name="non_negative"),
    )
    project_id: Mapped[int] = fk("projects.id", "CASCADE")
    rel_path: Mapped[str] = mapped_column(String(500), nullable=False)       # path inside the project
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # path under storage/
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_test_file: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    project: Mapped[Project] = relationship(back_populates="source_files")
    functions: Mapped[list["Function"]] = relationship(
        back_populates="source_file", cascade="all, delete-orphan", passive_deletes=True)


class Function(Entity):
    __tablename__ = "functions"
    __table_args__ = (
        UniqueConstraint("source_file_id", "qualified_name", "lineno",
                         name="uq_functions_source_file_id_qualified_name_lineno"),
        CheckConstraint(in_list("kind", FUNCTION_KINDS), name="kind_valid"),
        CheckConstraint("lineno >= 1 AND cyclomatic_complexity >= 1 AND branch_count >= 0",
                        name="metrics_valid"),
    )
    source_file_id: Mapped[int] = fk("source_files.id", "CASCADE")
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    qualified_name: Mapped[str] = mapped_column(String(300), nullable=False)
    class_name: Mapped[Optional[str]] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="function")
    lineno: Mapped[int] = mapped_column(Integer, nullable=False)
    end_lineno: Mapped[Optional[int]] = mapped_column(Integer)
    parameters: Mapped[Optional[Any]] = mapped_column(JSON)
    return_annotation: Mapped[Optional[str]] = mapped_column(String(300))
    cyclomatic_complexity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    branch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source_file: Mapped[SourceFile] = relationship(back_populates="functions")


class UserSettings(Entity):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("default_timeout_seconds > 0 AND default_max_iterations > 0", name="positive"),
        CheckConstraint("default_coverage_target BETWEEN 0 AND 100", name="target_pct"),
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="dark", server_default="dark")
    default_timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    default_max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    default_coverage_target: Mapped[float] = mapped_column(Float, nullable=False, default=90.0)
    ollama_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    ollama_base_url: Mapped[str] = mapped_column(String(255), nullable=False, default="http://127.0.0.1:11434")
    ollama_model: Mapped[Optional[str]] = mapped_column(String(100))
    extra: Mapped[Optional[Any]] = mapped_column(JSON)


class ActivityLog(Entity):
    """Audit trail. Rows survive user/project deletion (SET NULL) on purpose."""
    __tablename__ = "activity_logs"
    user_id: Mapped[Optional[int]] = fk("users.id", "SET NULL", nullable=True)
    project_id: Mapped[Optional[int]] = fk("projects.id", "SET NULL", nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    details: Mapped[Optional[Any]] = mapped_column(JSON)
