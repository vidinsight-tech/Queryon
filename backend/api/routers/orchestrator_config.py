"""Orchestrator config router: GET + PUT the active configuration."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.api.schemas.orchestrator import OrchestratorConfigSchema
from backend.infra.database.models.tool_config import OrchestratorConfigModel
from backend.orchestrator.types import OrchestratorConfig

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


def _build_system_prompt(config: OrchestratorConfig) -> Optional[str]:
    """Build an auto-generated system prompt from bot identity + enabled modes.

    Returns None when there is no persona content at all.
    """
    parts = []

    base = f"You are {config.bot_name}."
    if config.character_system_prompt:
        base += f"\n\n{config.character_system_prompt.strip()}"
    parts.append(base)

    if config.appointment_fields:
        field_list = "\n".join(
            f"- {f.get('label', f.get('key', ''))}: {f.get('question', '')}"
            for f in config.appointment_fields
        )
        parts.append(
            f"## Randevu Alma\n"
            f"Kullanıcı randevu almak istediğinde aşağıdaki bilgileri sırayla sor:\n{field_list}\n"
            f"Tüm zorunlu bilgiler toplandığında kullanıcıya özet göster ve onay iste."
        )

    if config.order_mode_enabled and config.order_fields:
        field_list = "\n".join(
            f"- {f.get('label', f.get('key', ''))}: {f.get('question', '')}"
            for f in config.order_fields
        )
        parts.append(
            f"## Sipariş Alma\n"
            f"Kullanıcı sipariş vermek istediğinde aşağıdaki bilgileri sırayla sor:\n{field_list}\n"
            f"Tüm zorunlu bilgiler toplandığında kullanıcıya özet göster ve onay iste."
        )

    if config.restrictions and config.restrictions.strip():
        parts.append(
            f"## Kısıtlamalar\n"
            f"Aşağıdaki konuları KESINLIKLE konuşma ve bu konularda yardımcı olmayı reddet:\n"
            f"{config.restrictions.strip()}"
        )

    # Only return a prompt when there's actual content
    if not config.character_system_prompt and not config.appointment_fields and not (
        config.order_mode_enabled and config.order_fields
    ) and not config.restrictions:
        return None

    return "\n\n".join(parts)


async def _load_config(session: AsyncSession) -> OrchestratorConfig:
    result = await session.execute(
        select(OrchestratorConfigModel).where(OrchestratorConfigModel.id == 1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return OrchestratorConfig()
    return OrchestratorConfig.from_dict(row.config_json)


async def _save_config(session: AsyncSession, config: OrchestratorConfig) -> None:
    result = await session.execute(
        select(OrchestratorConfigModel).where(OrchestratorConfigModel.id == 1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        session.add(OrchestratorConfigModel(id=1, config_json=config.to_dict()))
    else:
        row.config_json = config.to_dict()
    await session.flush()


def _to_schema(config: OrchestratorConfig) -> OrchestratorConfigSchema:
    d = config.to_dict()
    return OrchestratorConfigSchema(**d)


@router.get("/preview-prompt")
async def preview_system_prompt(session: AsyncSession = Depends(get_session)):
    """Return the fully rendered system prompt the bot will use (read-only)."""
    config = await _load_config(session)
    prompt = _build_system_prompt(config)
    if prompt is None:
        prompt = ""
    return {"system_prompt": prompt}


@router.get("/config", response_model=OrchestratorConfigSchema)
async def get_config(session: AsyncSession = Depends(get_session)):
    config = await _load_config(session)
    return _to_schema(config)


@router.put("/config", response_model=OrchestratorConfigSchema)
async def update_config(
    body: OrchestratorConfigSchema,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # Build from dict to apply OrchestratorConfig defaults/validation
    config = OrchestratorConfig.from_dict(body.model_dump())

    # Auto-build character_system_prompt when not explicitly set but modes are active
    # (If body provided an explicit character_system_prompt, from_dict already captured it)
    generated_prompt = _build_system_prompt(config)
    if generated_prompt and not config.character_system_prompt:
        config.character_system_prompt = generated_prompt

    await _save_config(session, config)

    # Hot-reload the running orchestrator so changes apply immediately
    orchestrator = getattr(getattr(request, "app", None), "state", None)
    if orchestrator is not None:
        orchestrator = getattr(orchestrator, "orchestrator", None)
    if orchestrator is not None:
        # Update config fields on the running orchestrator
        orchestrator._config = config
        system_prompt = _build_system_prompt(config) or config.character_system_prompt
        orchestrator.reload_character(system_prompt)

    return _to_schema(config)
