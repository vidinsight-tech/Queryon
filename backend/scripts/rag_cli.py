#!/usr/bin/env python3
"""
Queryon RAG CLI – LLM/Embedding/Dosya yönetimi ve RAG sohbet.

Kullanım:
  python -m backend.scripts.rag_cli

Gerekli env: DATABASE_URL, QDRANT_URL
LLM/Embedding eklerken: OPENAI_API_KEY veya GEMINI_API_KEY / GOOGLE_API_KEY
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional
from uuid import UUID

# Provider'ları registry'ye kaydet
import backend.clients.llm.providers  # noqa: F401
import backend.clients.embedding.providers  # noqa: F401
import backend.orchestrator.rules.models  # noqa: F401  — Base'e kaydet (init_db'den önce)

from backend.config import load_postgres_config, load_qdrant_config
from backend.core.logger import LoggerConfig, configure, get_logger
from backend.infra.database.engine import build_engine, build_session_factory, ensure_database_exists, init_db
from backend.infra.vectorstore.client import get_qdrant_manager
from backend.orchestrator.types import LowConfidenceStrategy, OrchestratorConfig
from backend.services import (
    EmbeddingService,
    FileService,
    LLMService,
    OrchestratorService,
    RAGService,
    RuleService,
)

RAG_CONFIG_PATH = Path.home() / ".queryon-rag.json"
ORCHESTRATOR_CONFIG_PATH = Path.home() / ".queryon-orchestrator.json"

# Test edilebilirlik: input/print fonksiyonları değiştirilebilir
_input_fn = input
_print_fn = print
_default_input_fn = input
_default_print_fn = print


def _set_io(input_fn=None, print_fn=None) -> None:
    """Test için I/O enjekte et. None = değiştirme."""
    global _input_fn, _print_fn
    if input_fn is not None:
        _input_fn = input_fn
    if print_fn is not None:
        _print_fn = print_fn


def _reset_io() -> None:
    """I/O'yu varsayılana (gerçek input/print) döndür."""
    global _input_fn, _print_fn
    _input_fn = _default_input_fn
    _print_fn = _default_print_fn


def _input(prompt: str, default: str = "") -> str:
    s = _input_fn(prompt).strip()
    return s if s else default


def _input_uuid(prompt: str) -> Optional[UUID]:
    s = _input_fn(prompt).strip()
    if not s:
        return None
    try:
        return UUID(s)
    except ValueError:
        _print_fn("  Geçersiz UUID.")
        return None


def _load_rag_cfg() -> Dict[str, Any]:
    if not RAG_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(RAG_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_rag_cfg(data: Dict[str, Any]) -> None:
    existing = _load_rag_cfg()
    existing.update(data)
    RAG_CONFIG_PATH.write_text(json.dumps(existing, indent=2))
    _print_fn(f"  Kaydedildi → {RAG_CONFIG_PATH}")


def _load_orchestrator_cfg() -> Dict[str, Any]:
    if not ORCHESTRATOR_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(ORCHESTRATOR_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_orchestrator_cfg(data: Dict[str, Any]) -> None:
    existing = _load_orchestrator_cfg()
    existing.update(data)
    ORCHESTRATOR_CONFIG_PATH.write_text(json.dumps(existing, indent=2))
    _print_fn(f"  Kaydedildi → {ORCHESTRATOR_CONFIG_PATH}")


def _get_orchestrator_config() -> OrchestratorConfig:
    """Load orchestrator config from file or return defaults."""
    raw = _load_orchestrator_cfg()
    return OrchestratorConfig.from_dict(raw)


def _out(msg: str = "") -> None:
    _print_fn(msg)


# Menü genişliği (testlerde de aynı çıktı için sabit)
MENU_WIDTH = 44


def _show_menu(title: str, items: List[str]) -> str:
    """Görsel olarak düzenli, test edilebilir menü."""
    top = "╭" + "─" * (MENU_WIDTH - 2) + "╮"
    bot = "╰" + "─" * (MENU_WIDTH - 2) + "╯"
    sep = "├" + "─" * (MENU_WIDTH - 2) + "┤"
    _out()
    _out(top)
    _out("│ " + title.center(MENU_WIDTH - 4) + " │")
    _out(sep)
    for item in items:
        _out("│ " + item.ljust(MENU_WIDTH - 4) + " │")
    _out(bot)
    return _input_fn("  Seçim: ").strip()


# ─── LLM ─────────────────────────────────────────────────────────

async def llm_menu(sf, qdrant, qcfg) -> None:
    while True:
        choice = _show_menu("LLM Yönetimi", [
            "1) LLM ekle",
            "2) LLM sil",
            "3) LLM listele",
            "0) Geri",
        ])
        if choice == "0":
            return
        elif choice == "1":
            await _llm_add(sf)
        elif choice == "2":
            await _llm_delete(sf)
        elif choice == "3":
            await _llm_list(sf)
        else:
            _out("  Geçersiz seçim.")


async def _llm_add(sf) -> None:
    provider = _input("  Provider (openai | gemini): ").lower()
    if provider not in ("openai", "gemini"):
        _out("  Sadece openai veya gemini desteklenir.")
        return
    name = _input("  İsim: ")
    if not name:
        _out("  İsim gerekli.")
        return

    if provider == "openai":
        model = _input("  Model (gpt-4o-mini, gpt-4o, gpt-3.5-turbo) [gpt-4o-mini]: ") or "gpt-4o-mini"
    else:
        model = _input("  Model (gemini-2.0-flash, gemini-1.5-pro) [gemini-2.0-flash]: ") or "gemini-2.0-flash"

    api_key = _input("  API key (boş = env'den): ")
    config: Dict[str, Any] = {"model": model}
    if api_key:
        config["api_key"] = api_key

    if provider == "openai":
        base_url = _input("  Base URL (boş = varsayılan): ")
        if base_url:
            config["base_url"] = base_url
        temp = _input("  Temperature (0-2) [0]: ") or "0"
        config["temperature"] = float(temp)
        max_tok = _input("  Max tokens (boş = varsayılan): ")
        if max_tok:
            config["max_tokens"] = int(max_tok)

    async with sf() as session:
        svc = LLMService(session)
        llm = await svc.create(name=name, provider=provider, config=config)
        await session.commit()
    _out(f"  ✓ LLM eklendi: {llm.id}  [{llm.provider}] {config.get('model')}")


async def _llm_delete(sf) -> None:
    uid = _input_uuid("  Silinecek LLM UUID: ")
    if uid is None:
        return
    async with sf() as session:
        svc = LLMService(session)
        ok = await svc.delete(uid)
        await session.commit()
    _out("  Silindi." if ok else "  Kayıt bulunamadı.")


async def _llm_list(sf) -> None:
    async with sf() as session:
        svc = LLMService(session)
        items = await svc._repo.list_all(active_only=False, limit=100)
    if not items:
        _out("  Kayıtlı LLM yok.")
        return
    _out()
    for llm in items:
        m = (llm.config or {}).get("model", "-")
        _out(f"  {llm.id}  {llm.name}  provider={llm.provider}  model={m}")


# ─── Embedding ───────────────────────────────────────────────────

async def embedding_menu(sf, qdrant, qcfg) -> None:
    while True:
        choice = _show_menu("Embedding Yönetimi", [
            "1) Embedding ekle",
            "2) Embedding sil",
            "3) Embedding listele",
            "0) Geri",
        ])
        if choice == "0":
            return
        elif choice == "1":
            await _emb_add(sf)
        elif choice == "2":
            await _emb_delete(sf)
        elif choice == "3":
            await _emb_list(sf)
        else:
            _out("  Geçersiz seçim.")


async def _emb_add(sf) -> None:
    provider = _input("  Provider (openai | gemini): ").lower()
    if provider not in ("openai", "gemini"):
        _out("  Sadece openai veya gemini.")
        return
    name = _input("  İsim: ")
    if not name:
        _out("  İsim gerekli.")
        return
    if provider == "openai":
        model = _input("  Model (text-embedding-3-small | 3-large | ada-002) [text-embedding-3-small]: ") or "text-embedding-3-small"
    else:
        model = _input("  Model (text-embedding-004 | 005) [text-embedding-004]: ") or "text-embedding-004"
    api_key = _input("  API key (boş = env'den): ")
    config: Dict[str, Any] = {"model": model}
    if api_key:
        config["api_key"] = api_key
    if provider == "openai":
        base_url = _input("  Base URL (boş = varsayılan): ")
        if base_url:
            config["base_url"] = base_url

    async with sf() as session:
        svc = EmbeddingService(session)
        emb = await svc.create(name=name, provider=provider, config=config)
        await session.commit()
    _out(f"  ✓ Embedding eklendi: {emb.id}  [{emb.provider}] {model}")


async def _emb_delete(sf) -> None:
    uid = _input_uuid("  Silinecek Embedding UUID: ")
    if uid is None:
        return
    async with sf() as session:
        svc = EmbeddingService(session)
        ok = await svc.delete(uid)
        await session.commit()
    _out("  Silindi." if ok else "  Kayıt bulunamadı.")


async def _emb_list(sf) -> None:
    async with sf() as session:
        svc = EmbeddingService(session)
        items = await svc._repo.list_all(active_only=False, limit=100)
    if not items:
        _out("  Kayıtlı Embedding yok.")
        return
    _out()
    for emb in items:
        m = (emb.config or {}).get("model", "-")
        _out(f"  {emb.id}  {emb.name}  provider={emb.provider}  model={m}")


# ─── Dosya ───────────────────────────────────────────────────────

async def file_menu(sf, qdrant, qcfg) -> None:
    while True:
        choice = _show_menu("Dosya Yönetimi", [
            "1) Dosya embed (yükle)",
            "2) Dosya sil",
            "3) Dosya listele",
            "0) Geri",
        ])
        if choice == "0":
            return
        elif choice == "1":
            await _file_embed(sf, qdrant, qcfg)
        elif choice == "2":
            await _file_delete(sf, qdrant, qcfg)
        elif choice == "3":
            await _file_list(sf)
        else:
            _out("  Geçersiz seçim.")


async def _get_emb_client(sf, hint: str = "Embedding UUID"):
    """RAG config'ten veya kullanıcıdan embedding client al."""
    cfg = _load_rag_cfg()
    emb_id_str = cfg.get("embedding_id")
    if emb_id_str:
        _out(f"  (Kayıtlı embedding: {emb_id_str})")
        confirm = _input("  Bu embedding'i kullan? (E/h) [E]: ") or "E"
        if confirm.lower() in ("e", "evet", "y", "yes", ""):
            uid = UUID(emb_id_str)
        else:
            uid = _input_uuid(f"  {hint}: ")
    else:
        uid = _input_uuid(f"  {hint}: ")
    if uid is None:
        return None, None
    async with sf() as session:
        svc = EmbeddingService(session)
        client = await svc.get_client(uid)
    if client is None:
        _out("  Embedding bulunamadı.")
    return uid, client


async def _file_embed(sf, qdrant, qcfg) -> None:
    _, emb_client = await _get_emb_client(sf, "Embedding UUID (dosya bu model ile embed edilecek)")
    if emb_client is None:
        return
    path_str = _input("  Dosya yolu (PDF, DOCX, DOC, TXT): ")
    if not path_str:
        _out("  Dosya yolu gerekli.")
        return
    path = Path(path_str).expanduser()
    if not path.exists():
        _out("  Dosya bulunamadı.")
        return
    title = _input("  Başlık (boş = dosya adı): ") or None
    file_bytes = path.read_bytes()
    _out("  Embed ediliyor...")
    async with sf() as session:
        file_svc = FileService(session, qdrant, emb_client, qdrant_config=qcfg)
        result = await file_svc.upload(file_bytes, path.name, title=title)
    if result.success:
        _out(f"  ✓ Dosya eklendi: doc_id={result.document_id}  chunks={result.chunk_count}")
    else:
        _out(f"  ✗ Hata: {result.error}")


async def _file_delete(sf, qdrant, qcfg) -> None:
    doc_id = _input_uuid("  Silinecek doküman UUID: ")
    if doc_id is None:
        return
    _, emb_client = await _get_emb_client(sf, "Embedding UUID (vektör silmek için)")
    if emb_client is None:
        return
    async with sf() as session:
        file_svc = FileService(session, qdrant, emb_client, qdrant_config=qcfg)
        ok = await file_svc.delete_file(doc_id)
    _out("  Silindi." if ok else "  Doküman bulunamadı.")


async def _file_list(sf) -> None:
    from backend.infra.database.repositories.knowledge import KnowledgeDocumentRepository
    async with sf() as session:
        repo = KnowledgeDocumentRepository(session)
        docs = await repo.list_active(skip=0, limit=100)
    if not docs:
        _out("  Doküman yok.")
        return
    _out()
    for d in docs:
        _out(f"  {d.id}  \"{d.title}\"  file={d.file_name}  chunks={d.chunk_count}  model={d.embedding_model or '-'}")


# ─── RAG Konfigüre ──────────────────────────────────────────────

async def rag_configure_menu(sf, qdrant, qcfg) -> None:
    while True:
        cfg = _load_rag_cfg()
        items = [
            "1) Varsayılan Embedding ayarla",
            "2) Varsayılan LLM ayarla",
            "3) Mevcut ayarları göster",
            "0) Geri",
        ]
        if cfg.get("embedding_id"):
            items.insert(0, f"  [Embedding: {cfg['embedding_id']}]")
        if cfg.get("llm_id"):
            items.insert(0, f"  [LLM: {cfg['llm_id']}]")

        choice = _show_menu("RAG Konfigürasyon", items)
        if choice == "0":
            return
        elif choice == "1":
            await _rag_set_embedding(sf)
        elif choice == "2":
            await _rag_set_llm(sf)
        elif choice == "3":
            _rag_show_config()
        else:
            _out("  Geçersiz seçim.")


async def _rag_set_embedding(sf) -> None:
    await _emb_list(sf)
    uid = _input_uuid("  Kullanılacak Embedding UUID: ")
    if uid is None:
        return
    async with sf() as session:
        svc = EmbeddingService(session)
        client = await svc.get_client(uid)
    if client is None:
        _out("  Embedding bulunamadı veya provider geçersiz.")
        return
    _save_rag_cfg({"embedding_id": str(uid)})
    _out(f"  ✓ Embedding ayarlandı: {uid} ({client.model_name}, {client.dimension}d)")


async def _rag_set_llm(sf) -> None:
    await _llm_list(sf)
    uid = _input_uuid("  Kullanılacak LLM UUID: ")
    if uid is None:
        return
    async with sf() as session:
        svc = LLMService(session)
        client = await svc.get_client(uid)
    if client is None:
        _out("  LLM bulunamadı veya provider geçersiz.")
        return
    _save_rag_cfg({"llm_id": str(uid)})
    _out(f"  ✓ LLM ayarlandı: {uid} ({client.provider})")


def _rag_show_config() -> None:
    cfg = _load_rag_cfg()
    if not cfg:
        _out("  Henüz RAG konfigürasyonu yok.")
        return
    _out(f"\n  Embedding ID : {cfg.get('embedding_id', '-')}")
    _out(f"  LLM ID      : {cfg.get('llm_id', '-')}")


# ─── RAG Sohbet ──────────────────────────────────────────────────

async def rag_chat(sf, qdrant, qcfg) -> None:
    cfg = _load_rag_cfg()
    emb_id_str = cfg.get("embedding_id")
    llm_id_str = cfg.get("llm_id")

    if not emb_id_str:
        emb_id_str = _input("  Embedding UUID: ")
    if not llm_id_str:
        llm_id_str = _input("  LLM UUID: ")
    if not emb_id_str or not llm_id_str:
        _out("  RAG için Embedding ve LLM UUID gerekli.")
        _out("  Önce 'RAG Konfigüre' ile ayarlayın.")
        return

    try:
        emb_id = UUID(emb_id_str)
        llm_id = UUID(llm_id_str)
    except ValueError:
        _out("  Geçersiz UUID.")
        return

    async with sf() as session:
        emb_client = await EmbeddingService(session).get_client(emb_id)
        llm_client = await LLMService(session).get_client(llm_id)

    if emb_client is None:
        _out("  Embedding bulunamadı.")
        return
    if llm_client is None:
        _out("  LLM bulunamadı.")
        return

    _out(f"\n  Embedding: {emb_client.model_name} ({emb_client.dimension}d)")
    _out(f"  LLM      : {llm_client.provider}")
    rag = RAGService(qdrant, emb_client, llm_client, qdrant_config=qcfg)
    _out("\n  RAG Sohbet başlatıldı. Çıkmak için 'çık' veya 'exit' yazın.\n")

    while True:
        try:
            q = input("  Soru: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("çık", "exit", "quit", "q"):
            break
        try:
            result = await rag.ask(q)
        except Exception as exc:
            _out(f"  Hata: {exc}")
            continue
        if result.answer:
            _out(f"\n  Cevap: {result.answer}")
        else:
            _out("  Cevap üretilemedi.")
        if result.context and result.context.sources:
            _out(f"  ({len(result.context.sources)} kaynak kullanıldı)")
        _out()

    _out("  Sohbet sonlandı.\n")


# ─── Kural Yönetimi ──────────────────────────────────────────────

async def rule_menu(sf, qdrant, qcfg) -> None:
    while True:
        choice = _show_menu("Kural Yönetimi", [
            "1) Kural ekle",
            "2) Kural sil",
            "3) Kural listele",
            "0) Geri",
        ])
        if choice == "0":
            return
        elif choice == "1":
            await _rule_add(sf)
        elif choice == "2":
            await _rule_delete(sf)
        elif choice == "3":
            await _rule_list(sf)
        else:
            _out("  Geçersiz seçim.")


async def _rule_add(sf) -> None:
    name = _input("  Kural adı: ")
    if not name:
        _out("  Ad gerekli.")
        return
    description = _input("  Açıklama (LLM bu açıklamayı okuyacak): ")
    if not description:
        _out("  Açıklama gerekli.")
        return
    patterns_raw = _input("  Tetikleyiciler (virgülle ayırın): ")
    if not patterns_raw:
        _out("  En az bir tetikleyici gerekli.")
        return
    patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()]
    template = _input("  Cevap şablonu ({degisken} formatında): ")
    if not template:
        _out("  Şablon gerekli.")
        return
    vars_raw = _input("  Değişkenler (JSON, boş = yok): ") or "{}"
    try:
        variables = json.loads(vars_raw)
    except json.JSONDecodeError:
        _out("  Geçersiz JSON.")
        return
    priority_str = _input("  Öncelik (0-100) [0]: ") or "0"
    try:
        priority = int(priority_str)
    except ValueError:
        priority = 0

    flow_id: str | None = None
    step_key: str | None = None
    required_step: str | None = None
    next_steps: dict | None = None

    is_flow = _input("  Çok adımlı akış kuralı mı? (e/h) [h]: ").strip().lower()
    if is_flow == "e":
        flow_id = _input("    Flow ID (akış grubu adı): ").strip() or None
        if not flow_id:
            _out("    Flow ID gerekli.")
            return
        step_key = _input("    Step Key (bu adımın adı): ").strip() or None
        if not step_key:
            _out("    Step Key gerekli.")
            return
        required_step = _input("    Gerekli Adım (bu kural hangi adımdan sonra çalışır, boş=giriş noktası): ").strip() or None
        ns_raw = _input("    Sonraki Adımlar (JSON, örn: {\"A\":\"step_a\",\"B\":\"step_b\"}, boş=akış sonu): ").strip() or ""
        if ns_raw:
            try:
                next_steps = json.loads(ns_raw)
            except json.JSONDecodeError:
                _out("    Geçersiz JSON.")
                return

    async with sf() as session:
        svc = RuleService(session)
        rule = await svc.create(
            name=name,
            description=description,
            trigger_patterns=patterns,
            response_template=template,
            variables=variables,
            priority=priority,
            flow_id=flow_id,
            step_key=step_key,
            required_step=required_step,
            next_steps=next_steps,
        )
        await session.commit()
    flow_info = f"  flow={flow_id}/{step_key}" if flow_id else ""
    _out(f"  ✓ Kural eklendi: {rule.id}  \"{rule.name}\"  öncelik={priority}{flow_info}")


async def _rule_delete(sf) -> None:
    uid = _input_uuid("  Silinecek Kural UUID: ")
    if uid is None:
        return
    async with sf() as session:
        svc = RuleService(session)
        ok = await svc.delete(uid)
        await session.commit()
    _out("  Silindi." if ok else "  Kural bulunamadı.")


async def _rule_list(sf) -> None:
    async with sf() as session:
        svc = RuleService(session)
        items = await svc.list_all(active_only=False)
    if not items:
        _out("  Kayıtlı kural yok.")
        return
    _out()
    for r in items:
        pats = ", ".join(r.trigger_patterns or [])
        flow_info = ""
        if r.flow_id:
            flow_info = f"  flow={r.flow_id}/{r.step_key}"
            if r.required_step:
                flow_info += f"  gerekli_adım={r.required_step}"
            if r.next_steps:
                flow_info += f"  sonraki={json.dumps(r.next_steps, ensure_ascii=False)}"
        _out(f"  {r.id}  \"{r.name}\"  öncelik={r.priority}  aktif={r.is_active}{flow_info}")
        _out(f"    tetikleyiciler: {pats}")
        _out(f"    şablon: {r.response_template[:80]}")
        _out()


# ─── Orchestrator Sohbet ─────────────────────────────────────────

async def orchestrator_chat(sf, qdrant, qcfg) -> None:
    cfg = _load_rag_cfg()
    emb_id_str = cfg.get("embedding_id")
    llm_id_str = cfg.get("llm_id")

    if not emb_id_str:
        emb_id_str = _input("  Embedding UUID: ")
    if not llm_id_str:
        llm_id_str = _input("  LLM UUID: ")
    if not emb_id_str or not llm_id_str:
        _out("  Orchestrator için Embedding ve LLM UUID gerekli.")
        _out("  Önce 'RAG Konfigüre' ile ayarlayın.")
        return

    try:
        emb_id = UUID(emb_id_str)
        llm_id = UUID(llm_id_str)
    except ValueError:
        _out("  Geçersiz UUID.")
        return

    async with sf() as session:
        emb_client = await EmbeddingService(session).get_client(emb_id)
        llm_client = await LLMService(session).get_client(llm_id)

    if emb_client is None:
        _out("  Embedding bulunamadı.")
        return
    if llm_client is None:
        _out("  LLM bulunamadı.")
        return

    _out(f"\n  Embedding: {emb_client.model_name} ({emb_client.dimension}d)")
    _out(f"  LLM      : {llm_client.provider}")

    rag = RAGService(qdrant, emb_client, llm_client, qdrant_config=qcfg)

    from backend.rag.embedder import Embedder
    embedder = Embedder(emb_client)

    _out("  Orchestrator kuruluyor...")
    orch_cfg = _get_orchestrator_config()
    async with sf() as session:
        orch = await OrchestratorService.build(
            session,
            llm_client,
            rag_service=rag,
            embedder=embedder,
            config=orch_cfg,
            session_factory=sf,
        )

    _out("  ✓ Orchestrator hazır.")
    _out("  Orchestrator Sohbet başlatıldı. Çıkmak için 'çık' veya 'exit' yazın.\n")

    conv_id = await orch.start_conversation(
        platform="cli",
        llm_id=llm_id,
        embedding_id=emb_id,
    )
    _out(f"  Konuşma başlatıldı: {conv_id}\n")

    while True:
        try:
            q = input("  Soru: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in ("çık", "exit", "quit", "q"):
            break

        try:
            result = await orch.process_with_tracking(q, conv_id)
        except Exception as exc:
            _out(f"  Hata: {exc}")
            continue

        intent_label = result.intent.value.upper()
        layer = result.metrics.classifier_layer if result.metrics else "?"
        conf = f"{result.classification.confidence:.2f}" if result.classification else "?"
        total_ms = f"{result.metrics.total_ms:.0f}" if result.metrics else "?"

        _out(f"\n  [{intent_label}] (güven={conf}, katman={layer}, süre={total_ms}ms)")

        if result.rule_matched:
            _out(f"  Eşleşen kural: {result.rule_matched}")
        if result.fallback_used:
            _out("  (RAG bulamadı → LLM doğrudan cevapladı)")
        if result.needs_clarification:
            _out("  ⚠ Düşük güven — lütfen sorunuzu netleştirin.")

        if result.answer:
            _out(f"\n  Cevap: {result.answer}")
        else:
            _out("  Cevap üretilemedi.")

        if result.sources:
            _out(f"  ({len(result.sources)} kaynak kullanıldı)")
        _out()

    await orch.end_conversation(conv_id)
    _out("  Sohbet sonlandı ve kaydedildi.\n")


# ─── Orchestrator Konfigürasyon ──────────────────────────────────

async def orchestrator_configure_menu(sf, qdrant, qcfg) -> None:
    while True:
        cfg = _get_orchestrator_config()
        choice = _show_menu("Orchestrator Konfigürasyon", [
            "1) Mevcut ayarları göster",
            "2) Min güven eşiği (0-1)",
            "3) LLM zaman aşımı (saniye, 0=kapalı)",
            "4) Konuşma geçmişi turn sayısı",
            "5) Kurallar önce (E/h)",
            "6) RAG boşsa Direct fallback (E/h)",
            "7) Embedding güven eşiği (0-1)",
            "8) Düşük güvende strateji (fallback | ask_user)",
            "0) Geri",
        ])
        if choice == "0":
            return
        elif choice == "1":
            _out(f"\n  default_intent           : {cfg.default_intent.value}")
            _out(f"  rules_first              : {cfg.rules_first}")
            _out(f"  fallback_to_direct       : {cfg.fallback_to_direct}")
            _out(f"  min_confidence           : {cfg.min_confidence}")
            _out(f"  low_confidence_strategy  : {cfg.low_confidence_strategy.value}")
            _out(f"  embedding_confidence     : {cfg.embedding_confidence_threshold}")
            _out(f"  llm_timeout_seconds      : {cfg.llm_timeout_seconds}")
            _out(f"  max_conversation_turns   : {cfg.max_conversation_turns}")
            _out("")
        elif choice == "2":
            s = _input("  Min güven (0-1) [%.2f]: " % cfg.min_confidence) or str(cfg.min_confidence)
            try:
                v = float(s)
                if 0 <= v <= 1:
                    _save_orchestrator_cfg({"min_confidence": v})
                    _out("  Kaydedildi.")
                else:
                    _out("  Geçersiz aralık.")
            except ValueError:
                _out("  Geçersiz sayı.")
        elif choice == "3":
            s = _input("  Zaman aşımı (saniye, 0=kapalı) [%s]: " % (cfg.llm_timeout_seconds or "60")) or str(cfg.llm_timeout_seconds or 60)
            try:
                v = float(s)
                if v <= 0:
                    v = None
                _save_orchestrator_cfg({"llm_timeout_seconds": v})
                _out("  Kaydedildi.")
            except ValueError:
                _out("  Geçersiz sayı.")
        elif choice == "4":
            s = _input("  Konuşma geçmişi turn sayısı (0=kapalı) [%d]: " % cfg.max_conversation_turns) or str(cfg.max_conversation_turns)
            try:
                v = int(s)
                if v >= 0:
                    _save_orchestrator_cfg({"max_conversation_turns": v})
                    _out("  Kaydedildi.")
                else:
                    _out("  Negatif olamaz.")
            except ValueError:
                _out("  Geçersiz sayı.")
        elif choice == "5":
            s = _input("  Kurallar önce? (E/h) [%s]: " % ("E" if cfg.rules_first else "h")) or ("E" if cfg.rules_first else "h")
            _save_orchestrator_cfg({"rules_first": s.lower() in ("e", "evet", "y", "yes", "")})
            _out("  Kaydedildi.")
        elif choice == "6":
            s = _input("  RAG boşsa Direct fallback? (E/h) [%s]: " % ("E" if cfg.fallback_to_direct else "h")) or ("E" if cfg.fallback_to_direct else "h")
            _save_orchestrator_cfg({"fallback_to_direct": s.lower() in ("e", "evet", "y", "yes", "")})
            _out("  Kaydedildi.")
        elif choice == "7":
            s = _input("  Embedding güven eşiği (0-1) [%.2f]: " % cfg.embedding_confidence_threshold) or str(cfg.embedding_confidence_threshold)
            try:
                v = float(s)
                if 0 <= v <= 1:
                    _save_orchestrator_cfg({"embedding_confidence_threshold": v})
                    _out("  Kaydedildi.")
                else:
                    _out("  Geçersiz aralık.")
            except ValueError:
                _out("  Geçersiz sayı.")
        elif choice == "8":
            s = _input("  Düşük güvende: fallback | ask_user [%s]: " % cfg.low_confidence_strategy.value) or cfg.low_confidence_strategy.value
            if s.strip().lower() in ("fallback", "ask_user"):
                _save_orchestrator_cfg({"low_confidence_strategy": s.strip().lower()})
                _out("  Kaydedildi.")
            else:
                _out("  Sadece 'fallback' veya 'ask_user'.")
        else:
            _out("  Geçersiz seçim.")


# ─── Ana Menü ────────────────────────────────────────────────────

MAIN_ITEMS = [
    "1) LLM Yönetimi",
    "2) Embedding Yönetimi",
    "3) Dosya Yönetimi",
    "4) RAG Konfigürasyon",
    "5) RAG Sohbet",
    "6) Kural Yönetimi",
    "7) Orchestrator Sohbet",
    "8) Orchestrator Konfigürasyon",
    "0) Çıkış",
]

MAIN_HANDLERS: Dict[str, Any] = {
    "1": llm_menu,
    "2": embedding_menu,
    "3": file_menu,
    "4": rag_configure_menu,
    "5": rag_chat,
    "6": rule_menu,
    "7": orchestrator_chat,
    "8": orchestrator_configure_menu,
}


def _setup_logging() -> str:
    """Rotating file + console logging; log dir default = proje kökü/logs. Returns log file path."""
    config = LoggerConfig.from_env()
    log_dir_raw = (config.log_dir or "").strip()
    if not log_dir_raw:
        # Proje kökü: backend/scripts/rag_cli.py -> backend -> Queryon
        _project_root = Path(__file__).resolve().parent.parent.parent
        log_dir = _project_root / "logs"
        config = config.with_overrides(
            log_dir=str(log_dir),
            log_file_basename="queryon",
            root_name="backend",
        )
    else:
        log_dir = Path(log_dir_raw)
        config = config.with_overrides(
            log_file_basename=config.log_file_basename or "queryon",
            root_name=config.root_name or "backend",
        )
    log_dir_str = str(log_dir)
    try:
        os.makedirs(log_dir_str, exist_ok=True)
    except OSError as e:
        _print_fn(f"  Uyarı: Log klasörü oluşturulamadı: {log_dir_str} ({e})")
    configure(config)
    log_path = Path(log_dir_str) / f"{config.log_file_basename}.log"
    get_logger(__name__).info("CLI started; log file: %s", log_path)
    return str(log_path)


async def main() -> None:
    log_path = _setup_logging()
    _out(f"  Log dosyası: {log_path}")
    _out("")

    try:
        pg = load_postgres_config()
        qcfg = load_qdrant_config()
    except Exception as e:
        _out(f"Config hatası: {e}")
        _out("Gerekli env: DATABASE_URL, QDRANT_URL")
        sys.exit(1)

    _out("Veritabanı kontrol ediliyor...")
    await ensure_database_exists(pg)

    engine = build_engine(pg)
    sf = build_session_factory(engine)
    qdrant = get_qdrant_manager(qcfg)

    try:
        _out("Tablolar oluşturuluyor / kontrol ediliyor...")
        await init_db(pg)
        _out("Veritabanı hazır.")
    except Exception as e:
        _out(f"Veritabanı bağlantı hatası: {e}")
        _out("PostgreSQL çalıştığından ve DATABASE_URL doğru olduğundan emin olun.")
        sys.exit(1)

    _out("")
    _out("  ▸ Queryon CLI — LLM, Embedding, Dosya, RAG, Kurallar ve Orchestrator")
    _out("")

    while True:
        choice = _show_menu("Queryon RAG CLI", MAIN_ITEMS)
        if choice == "0":
            break
        handler = MAIN_HANDLERS.get(choice)
        if handler is None:
            _out("  Geçersiz seçim.")
            continue
        try:
            await handler(sf, qdrant, qcfg)
        except KeyboardInterrupt:
            _out("\n  İşlem iptal edildi.")
        except Exception as e:
            _out(f"  Hata: {e}")
            import traceback
            traceback.print_exc()

    _out("\nÇıkılıyor.")


if __name__ == "__main__":
    asyncio.run(main())
