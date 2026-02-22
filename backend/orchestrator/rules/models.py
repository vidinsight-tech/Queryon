"""OrchestratorRule ORM model — user-defined rules stored in PostgreSQL."""
from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class OrchestratorRule(Base, TimestampMixin):
    """A deterministic rule that can override LLM-based classification.

    When a user message matches one of the ``trigger_patterns``, the
    orchestrator returns the rendered ``response_template`` immediately
    without calling the LLM or RAG pipeline.

    **Multi-step flows:** Rules with ``flow_id`` and ``step_key`` participate
    in stateful conversational flows.  ``required_step`` gates the rule so it
    only fires when the user is at a specific step.  ``next_steps`` maps user
    choices to the next step key, enabling branching dialogues.
    """

    __tablename__ = "orchestrator_rules"

    id: Mapped[uuid.UUID] = _uuid_pk()

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    """Human-readable description; also fed to the LLM classifier so it
    understands when this rule should fire."""

    trigger_patterns: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}",
    )
    """Keyword or regex patterns.  Plain strings do substring matching;
    patterns prefixed with ``r:`` are evaluated as regular expressions."""

    response_template: Mapped[str] = mapped_column(Text, nullable=False)
    """Answer template with ``{variable}`` placeholders filled from *variables*."""

    variables: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    """Key-value pairs substituted into *response_template*."""

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Higher priority rules are checked first."""

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Multi-step flow fields ────────────────────────────────────

    flow_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    """Identifies which flow this rule belongs to.  NULL = standalone rule."""

    step_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    """This rule's step name within the flow (e.g. 'start', 'danismanlik')."""

    required_step: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    """The step the user must be at for this rule to fire.
    NULL = entry point (no prerequisite)."""

    next_steps: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    """Maps user choices to the next step_key.
    Example: ``{"A": "danismanlik", "B": "egitim", "C": "destek"}``.
    NULL = flow ends after this rule."""

    @property
    def is_flow_rule(self) -> bool:
        return self.flow_id is not None

    def __repr__(self) -> str:
        flow = f", flow={self.flow_id}/{self.step_key}" if self.flow_id else ""
        return (
            f"OrchestratorRule(id={self.id!r}, name={self.name!r}, "
            f"priority={self.priority}, active={self.is_active}{flow})"
        )
