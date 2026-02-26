"""RuleService: CRUD operations for orchestrator rules."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

from backend.orchestrator.rules.repository import RuleRepository

if TYPE_CHECKING:
    from backend.orchestrator.rules.models import OrchestratorRule
    from sqlalchemy.ext.asyncio import AsyncSession


class RuleService:
    """Manage orchestrator rules in the database."""

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session
        self._repo = RuleRepository(session)

    async def create(
        self,
        name: str,
        description: str,
        trigger_patterns: List[str],
        response_template: str,
        variables: Dict[str, Any],
        *,
        priority: int = 0,
        is_active: bool = True,
        flow_id: Optional[str] = None,
        step_key: Optional[str] = None,
        required_step: Optional[str] = None,
        next_steps: Optional[Dict[str, Any]] = None,
        conditions: Optional[Dict[str, Any]] = None,
    ) -> "OrchestratorRule":
        return await self._repo.create_rule(
            name=name,
            description=description,
            trigger_patterns=trigger_patterns,
            response_template=response_template,
            variables=variables,
            priority=priority,
            is_active=is_active,
            flow_id=flow_id,
            step_key=step_key,
            required_step=required_step,
            next_steps=next_steps,
            conditions=conditions,
        )

    async def delete(self, rule_id: UUID) -> bool:
        return await self._repo.delete_rule(rule_id)

    async def list_all(self, *, active_only: bool = True, limit: int = 200) -> List["OrchestratorRule"]:
        return await self._repo.list_all(active_only=active_only, limit=limit)

    async def update(self, rule_id: UUID, data: Dict[str, Any]) -> Optional["OrchestratorRule"]:
        return await self._repo.update_rule(rule_id, data)
