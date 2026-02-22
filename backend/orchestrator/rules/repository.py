"""Repository for OrchestratorRule CRUD operations."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select

from backend.infra.database.repositories.base import BaseRepository
from backend.orchestrator.rules.models import OrchestratorRule


class RuleRepository(BaseRepository[OrchestratorRule]):
    model = OrchestratorRule

    async def list_active(self, *, limit: int = 200) -> List[OrchestratorRule]:
        stmt = (
            select(OrchestratorRule)
            .where(OrchestratorRule.is_active.is_(True))
            .order_by(OrchestratorRule.priority.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self, *, active_only: bool = True, limit: int = 200) -> List[OrchestratorRule]:
        stmt = select(OrchestratorRule)
        if active_only:
            stmt = stmt.where(OrchestratorRule.is_active.is_(True))
        stmt = stmt.order_by(OrchestratorRule.priority.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_rule(
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
    ) -> OrchestratorRule:
        data: Dict[str, Any] = {
            "name": name,
            "description": description,
            "trigger_patterns": trigger_patterns,
            "response_template": response_template,
            "variables": variables,
            "priority": priority,
            "is_active": is_active,
        }
        if flow_id is not None:
            data["flow_id"] = flow_id
        if step_key is not None:
            data["step_key"] = step_key
        if required_step is not None:
            data["required_step"] = required_step
        if next_steps is not None:
            data["next_steps"] = next_steps
        return await self.create(data)

    async def list_by_flow(
        self, flow_id: str, *, active_only: bool = True,
    ) -> List[OrchestratorRule]:
        stmt = (
            select(OrchestratorRule)
            .where(OrchestratorRule.flow_id == flow_id)
        )
        if active_only:
            stmt = stmt.where(OrchestratorRule.is_active.is_(True))
        stmt = stmt.order_by(OrchestratorRule.priority.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_rule(self, rule_id: UUID) -> bool:
        return await self.delete(rule_id)

    async def update_rule(self, rule_id: UUID, data: Dict[str, Any]) -> Optional[OrchestratorRule]:
        return await self.update(rule_id, data)
