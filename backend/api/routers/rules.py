"""Rules router: CRUD + rule tree (flows) endpoints."""
from __future__ import annotations

from collections import defaultdict
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.api.schemas.rules import (
    FlowResponse,
    RuleCreateRequest,
    RulePatchRequest,
    RuleResponse,
    RuleTreeResponse,
)
from backend.services.rule_service import RuleService

router = APIRouter(prefix="/rules", tags=["rules"])


def _to_schema(rule) -> RuleResponse:
    return RuleResponse(
        id=rule.id,
        name=rule.name,
        description=rule.description,
        trigger_patterns=rule.trigger_patterns or [],
        response_template=rule.response_template,
        variables=rule.variables or {},
        priority=rule.priority,
        is_active=rule.is_active,
        flow_id=rule.flow_id,
        step_key=rule.step_key,
        required_step=rule.required_step,
        next_steps=rule.next_steps,
        conditions=rule.conditions,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("", response_model=List[RuleResponse])
async def list_rules(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    svc = RuleService(session)
    rules = await svc.list_all(active_only=active_only)
    return [_to_schema(r) for r in rules]


@router.get("/flows", response_model=RuleTreeResponse)
async def list_rule_tree(
    active_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    """Return rules grouped into flows + standalone, suitable for tree rendering."""
    svc = RuleService(session)
    rules = await svc.list_all(active_only=active_only)

    flows: dict[str, list] = defaultdict(list)
    standalone = []

    for rule in rules:
        if rule.flow_id:
            flows[rule.flow_id].append(_to_schema(rule))
        else:
            standalone.append(_to_schema(rule))

    return RuleTreeResponse(
        standalone_rules=standalone,
        flows=[
            FlowResponse(flow_id=fid, rules=sorted(frules, key=lambda r: r.priority, reverse=True))
            for fid, frules in flows.items()
        ],
    )


@router.post("", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    svc = RuleService(session)
    rule = await svc.create(
        name=body.name,
        description=body.description,
        trigger_patterns=body.trigger_patterns,
        response_template=body.response_template,
        variables=body.variables,
        priority=body.priority,
        is_active=body.is_active,
        flow_id=body.flow_id,
        step_key=body.step_key,
        required_step=body.required_step,
        next_steps=body.next_steps,
        conditions=body.conditions,
    )
    return _to_schema(rule)


@router.get("/{rule_id}", response_model=RuleResponse)
async def get_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    from backend.orchestrator.rules.repository import RuleRepository
    repo = RuleRepository(session)
    rule = await repo.get_by_id(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _to_schema(rule)


@router.patch("/{rule_id}", response_model=RuleResponse)
async def patch_rule(
    rule_id: UUID,
    body: RulePatchRequest,
    session: AsyncSession = Depends(get_session),
):
    svc = RuleService(session)
    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=422, detail="No fields to update")
    rule = await svc.update(rule_id, update_data)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return _to_schema(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = RuleService(session)
    deleted = await svc.delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
