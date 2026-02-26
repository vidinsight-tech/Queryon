"""Queryon FastAPI application — entry point.

Start with:
    uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

LLM client is resolved in order: (1) env OPENAI_API_KEY or GEMINI_API_KEY,
(2) first active LLM from DB (llms table), (3) no-op client with a friendly message.
So no API key is required at startup; user can configure LLM via API/UI (llms table).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.infra.database.engine import (
    build_engine,
    build_session_factory,
    close_engine,
    ensure_database_exists,
    init_db,
)

logger = logging.getLogger(__name__)


def _build_llm_client_from_env():
    """Build a LLM client from environment variables. Returns None if no key set."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if openai_key:
        from backend.clients.llm.providers.openai import OpenAILLMClient
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        logger.info("API: using OpenAI LLM from env (%s)", model)
        return OpenAILLMClient(model=model, api_key=openai_key)
    if gemini_key:
        from backend.clients.llm.providers.gemini import GeminiLLMClient
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
        logger.info("API: using Gemini LLM from env (%s)", model)
        return GeminiLLMClient(model=model, api_key=gemini_key)
    return None


async def _get_llm_client_from_db(session_factory):
    """Build LLM client from first active LLM in DB. Returns None if none configured."""
    from backend.infra.database.repositories import LLMRepository
    from backend.services.llm_service import LLMService

    async with session_factory() as session:
        repo = LLMRepository(session)
        llms = await repo.list_all(active_only=True, limit=1)
        if not llms:
            return None
        llm = llms[0]
        try:
            client = await LLMService(session).get_client(llm.id)
            if client is not None:
                logger.info("API: using LLM from DB (%s, %s)", llm.provider, llm.name)
            return client
        except Exception as exc:
            logger.warning("API: could not build LLM from DB (%s): %s", llm.id, exc)
            return None


def _build_rag_service(llm_client) -> Optional[object]:
    """Try to build a RAGService. Returns None if Qdrant, embedding key, or real LLM is unavailable."""
    if llm_client is None or getattr(llm_client, "provider", "") == "noop":
        return None
    openai_key = os.environ.get("OPENAI_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    try:
        from backend.config.qdrant import QdrantConfig
        from backend.infra.vectorstore.client import QdrantManager
        from backend.services.rag_service import RAGService

        qdrant_cfg = QdrantConfig.from_env()
        qdrant = QdrantManager(qdrant_cfg)

        if openai_key:
            from backend.clients.embedding.providers.openai import OpenAIEmbeddingClient
            emb_model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
            embed_client = OpenAIEmbeddingClient(model=emb_model, api_key=openai_key)
        elif gemini_key:
            from backend.clients.embedding.providers.gemini import GeminiEmbeddingClient
            embed_client = GeminiEmbeddingClient(api_key=gemini_key)
        else:
            return None

        rag_service = RAGService(qdrant, embed_client, llm_client, qdrant_config=qdrant_cfg)
        logger.info("API: RAGService initialised")
        return rag_service
    except Exception as exc:
        logger.warning("API: RAGService not available (%s) — RAG intent disabled", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────
    logging.basicConfig(level=logging.INFO)

    await ensure_database_exists()
    engine = build_engine()
    session_factory = build_session_factory(engine)
    await init_db()

    app.state.session_factory = session_factory

    llm_client = _build_llm_client_from_env() or await _get_llm_client_from_db(session_factory)
    if llm_client is None:
        from backend.clients.llm.providers.noop import NoOpLLMClient
        llm_client = NoOpLLMClient()
        logger.info("API: no LLM configured (env or DB) — using no-op; configure via LLM API or set OPENAI_API_KEY / GEMINI_API_KEY")
    app.state.llm_client = llm_client

    rag_service = _build_rag_service(llm_client)
    app.state.embed_client = None  # default; overwritten below if a DB RAG config is found

    # Try to restore RAG config from DB (overrides env-based rag_service if configured)
    try:
        from backend.infra.database.models.tool_config import RagConfigModel
        from backend.services.embedding_model_service import EmbeddingModelService
        from backend.services.llm_service import LLMService
        from sqlalchemy import select as sa_select

        async with session_factory() as session:
            result = await session.execute(sa_select(RagConfigModel).where(RagConfigModel.id == 1))
            rag_cfg = result.scalar_one_or_none()
            if rag_cfg and rag_cfg.embedding_model_id:
                embed_client = await EmbeddingModelService(session).get_client(rag_cfg.embedding_model_id)
                if embed_client and llm_client and getattr(llm_client, "provider", "") != "noop":
                    from backend.config.qdrant import QdrantConfig
                    from backend.infra.vectorstore.client import QdrantManager
                    from backend.services.rag_service import RAGService

                    qdrant_cfg = QdrantConfig.from_env()
                    qdrant = QdrantManager(qdrant_cfg)
                    if rag_cfg.llm_id:
                        rag_llm = await LLMService(session).get_client(rag_cfg.llm_id)
                        rag_llm = rag_llm or llm_client
                    else:
                        rag_llm = llm_client
                    rag_service = RAGService(qdrant, embed_client, rag_llm, qdrant_config=qdrant_cfg)
                    app.state.embed_client = embed_client
                    logger.info("API: RAG service restored from DB config")
    except Exception as exc:
        logger.warning("API: could not restore RAG from DB config: %s", exc)

    app.state.rag_service = rag_service

    # Build tool registry
    from backend.tools.registry_builder import build_tool_registry
    async with session_factory() as session:
        tool_registry = await build_tool_registry(
            rag_service=rag_service, session=session
        )
    app.state.tool_registry = tool_registry
    logger.info("API: tool registry built with tools: %s", tool_registry.names)

    # Build orchestrator (shared across requests for rule engine + classifiers)
    from backend.infra.database.models.tool_config import OrchestratorConfigModel
    from backend.orchestrator.types import OrchestratorConfig
    from backend.services.orchestrator_service import OrchestratorService
    from sqlalchemy import select

    async with session_factory() as session:
        result = await session.execute(
            select(OrchestratorConfigModel).where(OrchestratorConfigModel.id == 1)
        )
        cfg_row = result.scalar_one_or_none()
        orch_config = (
            OrchestratorConfig.from_dict(cfg_row.config_json)
            if cfg_row
            else OrchestratorConfig()
        )
        orchestrator = await OrchestratorService.build(
            session,
            llm_client,
            rag_service=rag_service,
            config=orch_config,
            tool_registry=tool_registry,
            session_factory=session_factory,
        )
    app.state.orchestrator = orchestrator
    logger.info("API: orchestrator ready")

    # Load channel configs from DB into app.state for low-latency webhook use
    import json as _json
    from backend.api.routers.channels import _TG_KEY, _WA_KEY
    from backend.infra.database.models.tool_config import ToolConfig as _TC

    channel_configs: dict = {}
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(_TC).where(_TC.name.in_([_TG_KEY, _WA_KEY]))
            )
            for row in result.scalars().all():
                try:
                    creds = _json.loads(row.credentials or "{}")
                    key = "telegram" if row.name == _TG_KEY else "whatsapp"
                    channel_configs[key] = creds
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("API: could not load channel configs from DB: %s", exc)
    app.state.channel_configs = channel_configs
    logger.info("API: channel configs loaded (%s)", list(channel_configs))

    yield

    # ── Shutdown ─────────────────────────────────────────────────
    await close_engine()
    logger.info("API: engine disposed")


app = FastAPI(
    title="Queryon Admin API",
    version="1.0.0",
    description="REST API for the Queryon RAG platform — rules, orchestrator config, tools, and chat.",
    lifespan=lifespan,
)

# Rate limiter — limit is configurable via CHAT_RATE_LIMIT env var (default 30/minute)
_chat_rate_limit = os.environ.get("CHAT_RATE_LIMIT", "30/minute")
limiter = Limiter(key_func=get_remote_address, default_limits=[_chat_rate_limit])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — allow the Next.js dev server and any configured origin
_allowed_origins = os.environ.get(
    "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Optional API key authentication ──────────────────────────────
# Set ADMIN_API_KEY env var to protect all /api/v1/* endpoints.
# Requests must then include the header:  X-Api-Key: <value>
# If ADMIN_API_KEY is not set the check is skipped (dev/open mode).
_ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "").strip() or None


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    if _ADMIN_API_KEY and request.url.path.startswith("/api/v1"):
        provided = (
            request.headers.get("X-Api-Key")
            or request.headers.get("x-api-key")
        )
        if provided != _ADMIN_API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized — set X-Api-Key header"},
            )
    return await call_next(request)


# ── Routers ───────────────────────────────────────────────────────
from backend.api.routers import appointments, calendars, channels, chat, dashboard, documents, embeddings, google_oauth, llms, orchestrator_config, orders, rag, rules, tools, webhooks  # noqa: E402

app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")
app.include_router(orchestrator_config.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")
app.include_router(llms.router, prefix="/api/v1")
app.include_router(calendars.router, prefix="/api/v1")
app.include_router(google_oauth.router, prefix="/api/v1")
app.include_router(embeddings.router, prefix="/api/v1")
app.include_router(rag.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(appointments.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(channels.router, prefix="/api/v1")
app.include_router(webhooks.router)  # No /api/v1/ prefix — intentionally public


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
