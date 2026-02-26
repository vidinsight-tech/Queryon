"""Orchestrator: top-level router that classifies intent and dispatches to the
correct handler (RAG, Direct LLM, Rule, or Tool).

Classification uses a three-layer cascade:
  Layer 1  PreClassifier     — keyword/pattern matching     (<1 ms, no LLM)
  Layer 2  EmbeddingClassifier — cosine similarity prototypes (~5 ms, no LLM)
  Layer 3  LLMClassifier     — full LLM classification      (~500 ms)
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional
from uuid import UUID

from backend.orchestrator.classifiers.cache import ClassificationCache
from backend.orchestrator.types import ConversationTurn
from backend.orchestrator.classifiers.pre_classifier import PreClassifier
from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.handlers.character_handler import CharacterHandler
from backend.orchestrator.handlers.direct_handler import DirectHandler
from backend.orchestrator.handlers.rag_handler import RAGHandler
from backend.orchestrator.handlers.rule_handler import RuleHandler
from backend.orchestrator.handlers.tool_handler import ToolHandler, ToolRegistry
from backend.orchestrator.rules.engine import FlowContext
from backend.orchestrator.types import (
    ClassificationResult,
    IntentType,
    LowConfidenceStrategy,
    OrchestratorConfig,
    OrchestratorMetrics,
    OrchestratorResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from backend.clients.llm.base import BaseLLMClient
    from backend.orchestrator.classifiers.embedding_classifier import EmbeddingClassifier
    from backend.orchestrator.classifiers.llm_classifier import LLMClassifier
    from backend.orchestrator.rules.engine import RuleEngine, RuleMatchResult
    from backend.rag.embedder import Embedder
    from backend.services.rag_service import RAGService

logger = logging.getLogger(__name__)

# Words that signal the user wants to correct a previously collected field.
# When present in the query, already-filled fields become overwritable.
_CORRECTION_SIGNALS: FrozenSet[str] = frozenset(
    {"düzelt", "değiştir", "aslında", "hayır", "yanlış"}
)

# Words that trigger proactive appointment-mode activation on first user message.
_APPT_TRIGGER_WORDS: FrozenSet[str] = frozenset({
    "randevu", "rezervasyon", "appointment", "booking",
    "randevu almak", "randevu istiyorum",
    "düğün", "nişan", "kına", "söz", "davetli",
    "makyaj", "hazırlık", "gelin",
})

_CONFIRMATION_WORDS: FrozenSet[str] = frozenset({
    "evet", "tamam", "onayla", "onaylıyorum", "olur", "kabul",
    "doğru", "uygun", "tamamdır", "ok", "yes",
})


def _match_option(candidate: str, allowed: List[str]) -> Optional[str]:
    """Match *candidate* to one of *allowed* options (exact → case-insensitive → substring)."""
    cand = candidate.strip()
    if not cand:
        return None
    if cand in allowed:
        return cand
    low = cand.lower()
    for a in allowed:
        if a.lower() == low:
            return a
    for a in allowed:
        if low in a.lower() or a.lower() in low:
            return a
    return None


class Orchestrator:
    """Central entry-point that takes a user query, classifies intent,
    dispatches to the matching handler, and applies fallback logic.

    All heavy components are injected — the orchestrator itself is stateless
    between calls (aside from the classification cache).
    """

    def __init__(
        self,
        llm: "BaseLLMClient",
        config: OrchestratorConfig,
        *,
        rag_service: Optional["RAGService"] = None,
        rule_engine: Optional["RuleEngine"] = None,
        embedder: Optional["Embedder"] = None,
        tool_registry: Optional[ToolRegistry] = None,
        session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ) -> None:
        self._llm = llm
        self._config = config
        self._session_factory = session_factory

        timeout = config.llm_timeout_seconds
        self._handlers: Dict[IntentType, BaseHandler] = {
            IntentType.DIRECT: DirectHandler(llm, timeout_seconds=timeout),
        }
        if rag_service is not None:
            self._handlers[IntentType.RAG] = RAGHandler(rag_service)
        if rule_engine is not None:
            self._handlers[IntentType.RULE] = RuleHandler(
                rule_engine, llm, timeout_seconds=timeout
            )
            self._rule_engine = rule_engine
        else:
            self._rule_engine = None
        self._handlers[IntentType.TOOL] = ToolHandler(tool_registry, llm, timeout_seconds=timeout)

        if config.character_system_prompt:
            self._handlers[IntentType.CHARACTER] = CharacterHandler(
                llm,
                config.character_system_prompt,
                timeout_seconds=timeout,
                appointment_fields=config.appointment_fields or [],
                order_fields=config.order_fields if config.order_mode_enabled else [],
            )
            logger.info("Orchestrator: character mode enabled")

        self._pre_classifier: Optional[PreClassifier] = None
        self._embedding_classifier: Optional["EmbeddingClassifier"] = None
        self._llm_classifier: Optional["LLMClassifier"] = None
        self._cache = ClassificationCache()
        self._embedder = embedder

        self._build_classifiers()

    def _build_classifiers(self) -> None:
        rule_keywords: set[str] = set()
        if self._rule_engine is not None:
            rule_keywords = self._rule_engine.keywords

        self._pre_classifier = PreClassifier(rule_keywords)

        from backend.orchestrator.classifiers.llm_classifier import LLMClassifier
        self._llm_classifier = LLMClassifier(self._llm, self._config)

    async def initialize(self) -> None:
        """Build embedding prototypes.  Call once after construction."""
        if self._embedder is not None:
            from backend.orchestrator.classifiers.embedding_classifier import EmbeddingClassifier
            self._embedding_classifier = EmbeddingClassifier(self._embedder)
            await self._embedding_classifier.build_prototypes()
            logger.info("Orchestrator: embedding classifier initialised")

    async def process(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        last_intent: Optional[IntentType] = None,
        flow_ctx: Optional[FlowContext] = None,
        mode_context: Optional[str] = None,
        active_mode: Optional[str] = None,
        appt_collected: Optional[Dict[str, Any]] = None,
        order_collected: Optional[Dict[str, Any]] = None,
        reschedule_collected: Optional[Dict[str, Any]] = None,
        appt_availability_slots: Optional[Dict[str, List[str]]] = None,
        reschedule_availability_slots: Optional[Dict[str, List[str]]] = None,
    ) -> OrchestratorResult:
        """Full orchestration cycle: classify → handle → fallback → return.

        conversation_history: recent turns [{"role":"user"|"assistant","content":"..."}]
        for context-aware classification. last_intent: previous reply's intent (helps follow-ups).
        flow_ctx: multi-step flow state — when active, flow-bound rules are evaluated first.
        """
        t_start = time.monotonic()
        llm_calls = 0

        # ── Character mode: FAQ rules → LLM character ─────────────────────────
        # When a character system prompt is configured, skip the rigid flow engine
        # entirely.  The LLM handles natural language via full conversation history.
        # Only standalone FAQ rules (address, hours, prices) are checked for speed.
        if IntentType.CHARACTER in self._handlers:
            # Skip FAQ matching when the user is inside an active
            # appointment/order/reschedule flow — their answer is meant for the
            # current field, not as a standalone FAQ question.
            _in_active_flow = bool(active_mode in ("appointment", "order", "reschedule"))
            if self._rule_engine is not None and not _in_active_flow:
                faq_match = self._rule_engine.match_faq(query)
                if faq_match is not None:
                    return self._build_rule_result(
                        query, faq_match, t_start, layer="character_faq",
                    )
            t_handler = time.monotonic()
            char_result = await self._handlers[IntentType.CHARACTER].handle(
                query,
                conversation_history=conversation_history,
                mode_context=mode_context,
                active_mode=active_mode,
                appt_collected=appt_collected,
                order_collected=order_collected,
                reschedule_collected=reschedule_collected,
                appt_availability_slots=appt_availability_slots or {},
                reschedule_availability_slots=reschedule_availability_slots or {},
            )
            handler_ms = (time.monotonic() - t_handler) * 1000
            elapsed = (time.monotonic() - t_start) * 1000
            char_result.classification = ClassificationResult(
                intent=IntentType.CHARACTER,
                confidence=1.0,
                classifier_layer="character",
            )
            char_result.metrics = OrchestratorMetrics(
                handler_ms=handler_ms,
                total_ms=elapsed,
                llm_calls_count=1,
                classifier_layer="character",
            )
            logger.info(
                "Orchestrator: character mode → %.0fms", elapsed,
            )
            return char_result

        # ── Step 0: flow-aware rule match (always checked when flow is active) ──
        # match() already tries standalone rules last, so Step 1 is skipped to
        # avoid a redundant second match call with the same arguments.
        if flow_ctx and flow_ctx.active and self._rule_engine is not None:
            from backend.orchestrator.rules.engine import RuleMatchResult
            rule_match = self._rule_engine.match(query, flow_ctx=flow_ctx)
            if rule_match is not None:
                return self._build_rule_result(
                    query, rule_match, t_start, layer="flow_rule",
                )

        # ── Step 1: rules_first — keyword-only rule match (no LLM) ──
        # Skipped when flow was active (Step 0 already covered standalone rules).
        elif self._config.rules_first and self._rule_engine is not None:
            rule_match = self._rule_engine.match(query, flow_ctx=flow_ctx)
            if rule_match is not None:
                return self._build_rule_result(
                    query, rule_match, t_start, layer="rules_first",
                )

        # ── Step 2: three-layer classification ──
        t_classify = time.monotonic()
        classification = await self._classify(
            query,
            conversation_history=conversation_history,
            last_intent=last_intent,
            flow_ctx=flow_ctx,
        )
        classify_ms = (time.monotonic() - t_classify) * 1000
        if classification.classifier_layer == "llm":
            llm_calls += 1

        # ── Step 3: confidence check  [policy: min_confidence + low_confidence_strategy] ──
        if classification.confidence < self._config.min_confidence:
            if self._config.low_confidence_strategy == LowConfidenceStrategy.ASK_USER:
                logger.info(
                    "Orchestrator: confidence=%.2f < min_confidence=%.2f, "
                    "low_confidence_strategy=ask_user → needs_clarification",
                    classification.confidence, self._config.min_confidence,
                )
                elapsed = (time.monotonic() - t_start) * 1000
                return OrchestratorResult(
                    query=query,
                    intent=classification.intent,
                    needs_clarification=True,
                    answer="Tam olarak anlayamadım. Lütfen sorunuzu biraz daha açar mısınız?",
                    classification=classification,
                    metrics=OrchestratorMetrics(
                        classification_ms=classify_ms,
                        total_ms=elapsed,
                        llm_calls_count=llm_calls,
                        classifier_layer=classification.classifier_layer,
                    ),
                )
            logger.info(
                "Orchestrator: confidence=%.2f < min_confidence=%.2f, "
                "low_confidence_strategy=fallback → default_intent=%s",
                classification.confidence, self._config.min_confidence,
                self._config.default_intent.value,
            )
            classification.intent = self._config.default_intent

        # ── Step 3b: enforce enabled_intents  [policy: enabled_intents + default_intent] ──
        if classification.intent not in self._config.enabled_intents:
            logger.info(
                "Orchestrator: intent=%s not in enabled_intents → default_intent=%s",
                classification.intent.value,
                self._config.default_intent.value,
            )
            classification.intent = self._config.default_intent

        # ── Step 4: dispatch to handler  [policy: when_rag_unavailable / default_intent] ──
        intent = classification.intent

        if intent == IntentType.RAG and IntentType.RAG not in self._handlers:
            # Scenario 3: RAG service was not configured at startup (Qdrant unreachable)
            if self._config.when_rag_unavailable == "ask_user":
                logger.info(
                    "Orchestrator: RAG handler unavailable, "
                    "when_rag_unavailable=ask_user → needs_clarification",
                )
                elapsed = (time.monotonic() - t_start) * 1000
                return OrchestratorResult(
                    query=query,
                    intent=IntentType.RAG,
                    needs_clarification=True,
                    answer="Arama servisine şu an ulaşılamıyor. Lütfen daha sonra tekrar deneyin.",
                    classification=classification,
                    metrics=OrchestratorMetrics(
                        classification_ms=classify_ms,
                        total_ms=elapsed,
                        llm_calls_count=llm_calls,
                        classifier_layer=classification.classifier_layer,
                    ),
                )
            logger.info(
                "Orchestrator: RAG handler unavailable, "
                "when_rag_unavailable=direct → routing to direct",
            )
            intent = IntentType.DIRECT
        elif intent not in self._handlers:
            logger.info(
                "Orchestrator: no handler for intent=%s → default_intent=%s",
                intent.value, self._config.default_intent.value,
            )
            intent = self._config.default_intent

        handler = self._handlers.get(intent) or self._handlers[IntentType.DIRECT]

        t_handler = time.monotonic()
        result = await handler.handle(
            query, conversation_history=conversation_history,
        )
        handler_ms = (time.monotonic() - t_handler) * 1000
        if intent in (IntentType.RAG, IntentType.DIRECT):
            llm_calls += 1

        # ── Step 5: fallback  [policy: fallback_to_direct] ──
        fallback_used = False

        fallback_from: Optional[str] = None

        # 5a: RULE returned empty answer (LLM hallucinated a rule intent but no rule matched)
        if (
            intent == IntentType.RULE
            and not result.answer
            and IntentType.DIRECT in self._handlers
        ):
            logger.info(
                "Orchestrator: RULE handler returned no answer → fallback to direct",
            )
            t_fb = time.monotonic()
            result = await self._handlers[IntentType.DIRECT].handle(
                query, conversation_history=conversation_history,
            )
            handler_ms += (time.monotonic() - t_fb) * 1000
            fallback_used = True
            fallback_from = IntentType.RULE.value
            llm_calls += 1
            result.intent = IntentType.DIRECT

        # 5b: RAG returned empty answer → fallback_to_direct
        elif (
            intent == IntentType.RAG
            and not result.answer
            and self._config.fallback_to_direct
            and IntentType.DIRECT in self._handlers
        ):
            logger.info(
                "Orchestrator: RAG returned no answer, fallback_to_direct=True → direct",
            )
            t_fb = time.monotonic()
            result = await self._handlers[IntentType.DIRECT].handle(
                query, conversation_history=conversation_history,
            )
            handler_ms += (time.monotonic() - t_fb) * 1000
            fallback_used = True
            fallback_from = IntentType.RAG.value
            llm_calls += 1
            result.intent = IntentType.DIRECT  # so last_intent reflects actual reply source

        # ── Step 6: assemble metrics ──
        elapsed = (time.monotonic() - t_start) * 1000
        result.classification = classification
        result.fallback_used = fallback_used
        result.fallback_from_intent = fallback_from
        result.metrics = OrchestratorMetrics(
            classification_ms=classify_ms,
            handler_ms=handler_ms,
            total_ms=elapsed,
            llm_calls_count=llm_calls,
            fallback_used=fallback_used,
            classifier_layer=classification.classifier_layer,
        )
        logger.info(
            "Orchestrator: intent=%s confidence=%.2f layer=%s total=%.0fms fallback=%s",
            result.intent.value,
            classification.confidence,
            classification.classifier_layer,
            elapsed,
            fallback_used,
        )
        return result

    # ── Conversation-tracked processing ──────────────────────────

    async def start_conversation(
        self,
        *,
        platform: str = "cli",
        channel_id: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_meta: Optional[Dict[str, Any]] = None,
        llm_id: Optional[UUID] = None,
        embedding_id: Optional[UUID] = None,
    ) -> UUID:
        """Create a new tracked conversation and return its ID.

        Requires ``session_factory`` to be set at construction time.
        """
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            conv = await svc.start_conversation(
                platform=platform,
                channel_id=channel_id,
                contact_phone=contact_phone,
                contact_email=contact_email,
                contact_name=contact_name,
                contact_meta=contact_meta,
                llm_id=llm_id,
                embedding_id=embedding_id,
            )
            await session.commit()
            return conv.id

    async def end_conversation(self, conversation_id: UUID) -> bool:
        """Close a tracked conversation."""
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            ok = await svc.close_conversation(conversation_id)
            await session.commit()
            return ok

    async def process_with_tracking(
        self,
        query: str,
        conversation_id: UUID,
    ) -> OrchestratorResult:
        """Full orchestration cycle with automatic DB persistence.

        1. Load conversation history + flow_state from DB
        2. Derive ``last_intent`` from the most recent assistant message
        3. Call ``process()`` with flow context
        4. Record user + assistant messages (with events) to DB
        5. Persist updated flow_state
        6. Return the ``OrchestratorResult``
        """
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        max_turns = max(0, self._config.max_conversation_turns)

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)

            conversation_history = await svc.get_history_as_turns(
                conversation_id, max_turns=max_turns,
            )

            last_intent = await self._get_last_intent(svc, conversation_id)

            flow_state_raw = await svc.get_flow_state(conversation_id)
            flow_ctx = FlowContext.from_dict(flow_state_raw)

            # Compute mode context for progressive questioning (character mode only)
            mode_context: Optional[str] = None
            active_mode: Optional[str] = None
            appt_collected: Optional[Dict[str, Any]] = None
            order_collected: Optional[Dict[str, Any]] = None
            reschedule_collected: Optional[Dict[str, Any]] = None
            appt_availability_slots: Dict[str, List[str]] = {}
            reschedule_availability_slots: Dict[str, List[str]] = {}
            if IntentType.CHARACTER in self._handlers:
                from backend.orchestrator.mode_engine import compute_mode_context, get_next_field

                config_dict = self._config.to_dict()
                if flow_state_raw is None:
                    flow_state_raw = {}
                appt_state = flow_state_raw.get("appointment") or {}
                # Shallow-copy each field dict so _inject_availability_options can
                # safely mutate field["options"] without contaminating shared config.
                appt_fields = [dict(f) for f in (self._config.appointment_fields or [])]
                config_dict["appointment_fields"] = appt_fields

                # Proactively activate appointment mode when the user's first
                # message signals intent even though flow_state is still empty.
                if (
                    appt_fields
                    and not flow_state_raw.get("active_mode")
                    and not appt_state.get("saved")
                    and any(w in query.lower() for w in _APPT_TRIGGER_WORDS)
                ):
                    flow_state_raw["active_mode"] = "appointment"
                    flow_state_raw.setdefault("appointment", {})
                    appt_state = flow_state_raw["appointment"]
                    await svc.update_flow_state(conversation_id, flow_state_raw)

                # Dynamically inject available time slots into event_time field
                await self._inject_availability_options(
                    session, appt_fields, appt_state,
                )

                # Collect injected availability slots so the character handler can use them
                appt_availability_slots: Dict[str, List[str]] = {}
                for _f in appt_fields:
                    if _f.get("options"):
                        appt_availability_slots[_f["key"]] = list(_f["options"])

                active_mode, mode_context = compute_mode_context(
                    config_dict, flow_state_raw,
                )
                appt_collected = dict(appt_state) if appt_state else None
                order_collected = dict(flow_state_raw.get("order") or {}) if flow_state_raw else None

                # For reschedule mode, inject availability into event_time options
                reschedule_state_now = flow_state_raw.get("reschedule") or {}
                # Include appt_number in reschedule_collected for flow section display
                reschedule_collected = dict(reschedule_state_now.get("updates") or {})
                if reschedule_state_now.get("appt_number"):
                    reschedule_collected["appt_number"] = reschedule_state_now["appt_number"]

                reschedule_availability_slots: Dict[str, List[str]] = {}
                if active_mode == "reschedule":
                    from backend.orchestrator.handlers.character_handler import _RESCHEDULE_FIELDS
                    rs_fields_copy = [dict(f) for f in _RESCHEDULE_FIELDS]
                    await self._inject_reschedule_availability(
                        session, rs_fields_copy, reschedule_state_now,
                    )
                    for _rf in rs_fields_copy:
                        if _rf.get("options"):
                            reschedule_availability_slots[_rf["key"]] = list(_rf["options"])

            await svc.record_user_message(conversation_id, query)
            await session.commit()

        result = await self.process(
            query,
            conversation_history=conversation_history if conversation_history else None,
            last_intent=last_intent,
            flow_ctx=flow_ctx,
            mode_context=mode_context,
            active_mode=active_mode,
            appt_collected=appt_collected,
            order_collected=order_collected,
            reschedule_collected=reschedule_collected,
            appt_availability_slots=appt_availability_slots,
            reschedule_availability_slots=reschedule_availability_slots,
        )

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)

            # record_assistant_message is deferred to just before session.commit()
            # so that CHARACTER-mode appointment confirmation can inject the RND
            # reference number into result.answer before it is persisted.

            # Only update the flow state when a flow rule explicitly fired.
            # Standalone rules that match inside an active flow will have no
            # "next_flow_context" key in metadata — we leave the flow state
            # unchanged so the user can continue their flow after an FAQ answer.
            if result.intent == IntentType.RULE and "next_flow_context" in (result.metadata or {}):
                next_flow_dict = result.metadata.get("next_flow_context")
                new_flow_ctx = FlowContext.from_dict(next_flow_dict) if next_flow_dict else None
                await svc.update_flow_state(
                    conversation_id,
                    new_flow_ctx.to_dict() if new_flow_ctx and new_flow_ctx.active else None,
                )

            # Character mode: merge appointment/order updates into flow_state and
            # create DB records when the user confirms.
            elif result.intent == IntentType.CHARACTER:
                metadata = result.metadata or {}
                appt_update = metadata.get("appointment_update")
                order_update = metadata.get("order_update")

                # Auto-inject confirmation when the LLM omits <extract> tags
                # but the user clearly confirmed and all fields are collected.
                from backend.orchestrator.mode_engine import (
                    is_complete as _appt_is_complete,
                    all_fields_handled as _appt_all_handled,
                    field_is_visible as _fv,
                )
                _appt_fields_cfg = self._config.appointment_fields or []

                if (
                    not appt_update
                    and active_mode == "appointment"
                    and any(w in query.lower().split() for w in _CONFIRMATION_WORDS)
                ):
                    _ac_state = (await svc.get_flow_state(conversation_id) or {}).get("appointment") or {}
                    if (
                        not _ac_state.get("saved")
                        and not _ac_state.get("confirmed")
                        and _appt_is_complete(_appt_fields_cfg, _ac_state)
                        and _appt_all_handled(_appt_fields_cfg, _ac_state)
                    ):
                        appt_update = {"confirmed": True}
                        metadata["appointment_update"] = appt_update
                        logger.info(
                            "Orchestrator: auto-injected confirmation (LLM omitted extract tags) "
                            "for conversation %s", conversation_id,
                        )

                if appt_update or order_update:
                    # Single DB read shared by both blocks; appointment block
                    # updates raw_state in-memory so the order block sees it.
                    raw_state = await svc.get_flow_state(conversation_id) or {}
                    _is_correction = any(sig in query.lower() for sig in _CORRECTION_SIGNALS)

                if appt_update:
                    current_appt: Dict[str, Any] = dict(raw_state.get("appointment") or {})
                    _required_appt_keys = {
                        f["key"] for f in (self._config.appointment_fields or [])
                        if f.get("required")
                    }
                    current_appt = self._merge_flow_fields(
                        current_appt, appt_update, _is_correction, _required_appt_keys,
                    )
                    if not current_appt.get("saved"):
                        raw_state["active_mode"] = "appointment"
                    else:
                        raw_state.pop("active_mode", None)
                    new_state = {**raw_state, "appointment": current_appt}
                    await svc.update_flow_state(conversation_id, new_state)
                    raw_state = new_state  # keep in-memory state current for order block

                    _wants_create = (
                        current_appt.get("confirmed")
                        and not current_appt.get("saved")
                    )

                    # If confirmed but fields are missing, attempt to rescue
                    # values from the LLM response text before giving up.
                    if _wants_create and not _appt_is_complete(_appt_fields_cfg, current_appt):
                        _rescued = self._rescue_missing_fields(
                            current_appt, _appt_fields_cfg, result.answer or "",
                            conversation_history,
                        )
                        if _rescued:
                            current_appt = self._merge_flow_fields(
                                current_appt, _rescued, False, _required_appt_keys,
                            )
                            logger.info(
                                "Orchestrator: rescued missing fields from response: %s",
                                list(_rescued.keys()),
                            )

                    if _wants_create and _appt_is_complete(_appt_fields_cfg, current_appt):
                        current_appt, raw_state = await self._finalize_appointment(
                            session, svc, conversation_id,
                            current_appt, raw_state, result,
                        )
                    elif _wants_create:
                        # Still incomplete — log missing fields, clear confirmed flag,
                        # and ask the user for the remaining data. IMPORTANT: since no
                        # appointment was created, we must override any LLM text that
                        # claims success (e.g. "Randevunuz başarıyla oluşturuldu").
                        _field_map = {f["key"]: f for f in _appt_fields_cfg}
                        _missing = [
                            f["key"] for f in _appt_fields_cfg
                            if f.get("required")
                            and _fv(f, current_appt)
                            and not current_appt.get(f["key"])
                        ]
                        logger.warning(
                            "Orchestrator: premature appointment confirmation rejected "
                            "(missing required fields: %s) for conversation %s  "
                            "flow_state_keys=%s",
                            _missing, conversation_id,
                            list(current_appt.keys()),
                        )
                        current_appt.pop("confirmed", None)
                        new_state = {**raw_state, "appointment": current_appt}
                        await svc.update_flow_state(conversation_id, new_state)
                        raw_state = new_state

                        if _missing:
                            _labels = [_field_map[k].get("label", k) for k in _missing if k in _field_map]
                            _q = _field_map[_missing[0]].get("question", "") if _missing else ""
                            _base = (
                                "Henüz randevunuzu oluşturamadım çünkü bazı zorunlu "
                                "bilgiler eksik."
                            )
                            _suffix = (
                                f"\n\nRandevuyu tamamlamak için şu bilgi(ler) eksik: "
                                f"**{', '.join(_labels)}**.\n{_q}"
                            )
                            result.answer = _base + _suffix

                appt_cancel = metadata.get("appointment_cancel")
                if appt_cancel:
                    appt_number = appt_cancel.get("appt_number", "")
                    from backend.services.appointment_service import AppointmentService
                    _, outcome = await AppointmentService(session).cancel_by_number(
                        appt_number, conversation_id
                    )
                    logger.info(
                        "Appointment cancel: %s → %s (conv=%s)",
                        appt_number, outcome, conversation_id,
                    )
                    # Kullanıcıya yanlış / geçersiz RND ve diğer durumları açıkça bildir.
                    if outcome == "not_found":
                        result.answer = (
                            f"Bu randevu numarasını bulamadım: **{appt_number}**. "
                            "Lütfen numarayı kontrol edip tekrar dener misiniz?"
                        )
                    elif outcome == "unauthorized":
                        result.answer = (
                            "Bu randevu başka bir oturum veya kanal üzerinden oluşturulmuş. "
                            "Sadece kendi randevularınızı iptal edebilirsiniz."
                        )
                    elif outcome == "already_cancelled":
                        # DB'de zaten iptal edildi; kullanıcıya durumu yumuşakça anlat.
                        result.answer = (
                            f"**{appt_number}** numaralı randevu zaten iptal edilmiş görünüyor. "
                            "Yeni bir randevu oluşturmak isterseniz size yardımcı olabilirim."
                        )

                # ── Reschedule flow ─────────────────────────────────────────
                rs_intent = metadata.get("appointment_reschedule_intent")
                if rs_intent:
                    _rs_raw = await svc.get_flow_state(conversation_id) or {}
                    existing_rs = _rs_raw.get("reschedule") or {}
                    if existing_rs.get("appt_number") != rs_intent["appt_number"]:
                        # Fresh reschedule request — initialize state
                        await svc.update_flow_state(conversation_id, {
                            **_rs_raw,
                            "reschedule": {
                                "appt_number": rs_intent["appt_number"],
                                "updates": {},
                                "saved": False,
                            },
                        })

                rs_update = metadata.get("reschedule_update")
                if rs_update:
                    _rs_state = await svc.get_flow_state(conversation_id) or {}
                    _rs = _rs_state.get("reschedule") or {}
                    if _rs and not _rs.get("saved"):
                        _rs = dict(_rs)
                        _updates = {
                            **(_rs.get("updates") or {}),
                            **{k: v for k, v in rs_update.items() if k != "confirmed"},
                        }
                        _rs["updates"] = _updates
                        if rs_update.get("confirmed"):
                            _rs["confirmed"] = True
                        _rs_state = {**_rs_state, "reschedule": _rs}
                        await svc.update_flow_state(conversation_id, _rs_state)

                        if _rs.get("confirmed") and not _rs.get("saved") and _updates:
                            from backend.services.appointment_service import AppointmentService
                            from backend.infra.database.repositories import CalendarBlockRepository as _CBRepo
                            _updated_appt, _outcome = await AppointmentService(session).reschedule_by_number(
                                _rs["appt_number"], conversation_id, _updates
                            )
                            if _outcome == "ok" and _updated_appt is not None:
                                await _CBRepo(session).delete_by_appointment_id(_updated_appt.id)
                                _merged_dict: Dict[str, Any] = {
                                    k: getattr(_updated_appt, k, None)
                                    for k in ("artist", "event_date", "event_time", "service")
                                }
                                _merged_dict.update(_updates)
                                _block_ok = await Orchestrator._create_calendar_block_for_appointment(
                                    session, _updated_appt, _merged_dict,
                                )
                                _rs["saved"] = True
                                await svc.update_flow_state(
                                    conversation_id, {**_rs_state, "reschedule": _rs}
                                )
                                if not _block_ok:
                                    logger.warning(
                                        "Orchestrator: reschedule block creation blocked by conflict for %s",
                                        _rs["appt_number"],
                                    )
                                # Outbound webhook on reschedule
                                from backend.services.appointment_webhook_service import dispatch as _wh2
                                asyncio.create_task(_wh2(
                                    "appointment.updated", _updated_appt,
                                    self._config.appointment_webhook_url,
                                    self._config.appointment_webhook_secret,
                                ))
                            else:
                                # RND var ama DB tarafında işlem yapılamadı → kullanıcıya net mesaj dön.
                                if _outcome == "not_found":
                                    result.answer = (
                                        f"Bu randevu numarasını bulamadım: **{_rs['appt_number']}**. "
                                        "Lütfen numarayı kontrol edip tekrar dener misiniz?"
                                    )
                                elif _outcome == "unauthorized":
                                    result.answer = (
                                        "Bu randevu başka bir oturum veya kanal üzerinden oluşturulmuş. "
                                        "Sadece kendi randevularınızı değiştirebilirsiniz."
                                    )
                                elif _outcome == "already_cancelled":
                                    result.answer = (
                                        f"**{_rs['appt_number']}** numaralı randevu zaten iptal edilmiş. "
                                        "İptal edilmiş bir randevunun saatini değiştiremiyorum."
                                    )
                            logger.info(
                                "Appointment reschedule: %s → %s (conv=%s)",
                                _rs["appt_number"], _outcome, conversation_id,
                            )

                if order_update:
                    current_order: Dict[str, Any] = dict(raw_state.get("order") or {})
                    _required_order_keys = {
                        f["key"] for f in (self._config.order_fields or [])
                        if f.get("required")
                    }
                    current_order = self._merge_flow_fields(
                        current_order, order_update, _is_correction, _required_order_keys,
                    )
                    if not current_order.get("saved"):
                        raw_state["active_mode"] = "order"
                    else:
                        raw_state.pop("active_mode", None)
                    new_state2 = {**raw_state, "order": current_order}
                    await svc.update_flow_state(conversation_id, new_state2)

                    if current_order.get("confirmed") and not current_order.get("saved"):
                        from backend.services.order_service import OrderService
                        order = await OrderService(session).create_from_flow_state(
                            conversation_id,
                            current_order,
                            self._config.order_fields,
                        )
                        current_order["saved"] = True
                        current_order["order_id"] = str(order.id)
                        await svc.update_flow_state(
                            conversation_id,
                            {**new_state2, "order": current_order},
                        )

            # Record the assistant message now — after potential result.answer
            # modifications (e.g. RND injection for appointment confirmations).
            await svc.record_assistant_message(conversation_id, result)
            await session.commit()

        return result

    async def _finalize_appointment(
        self,
        session,
        svc,
        conversation_id: UUID,
        current_appt: Dict[str, Any],
        raw_state: Dict[str, Any],
        result: OrchestratorResult,
    ) -> tuple:
        """Create the appointment record, calendar block, and webhook.

        Returns the updated ``(current_appt, raw_state)`` tuple.
        """
        from backend.services.appointment_service import AppointmentService
        from backend.services.appointment_webhook_service import dispatch as _wh_dispatch

        appt = await AppointmentService(session).create_from_flow_state(
            conversation_id,
            current_appt,
            self._config.appointment_fields,
        )
        current_appt["saved"] = True
        current_appt["appointment_id"] = str(appt.id)
        if appt.appt_number:
            current_appt["appt_number"] = appt.appt_number
            _rnd_suffix = (
                f"\n\nRandevu numaranız: **{appt.appt_number}**\n"
                "İptal veya değişiklik için bu numarayı kullanabilirsiniz."
            )
            if result.answer:
                result.answer = result.answer.rstrip() + _rnd_suffix
            else:
                result.answer = _rnd_suffix.lstrip()

        try:
            await self._create_calendar_block_for_appointment(
                session, appt, current_appt,
            )
        except Exception as exc:
            logger.warning(
                "Orchestrator: calendar block creation failed for %s "
                "(appointment is saved): %s",
                appt.appt_number, exc,
            )

        asyncio.create_task(_wh_dispatch(
            "appointment.created", appt,
            self._config.appointment_webhook_url,
            self._config.appointment_webhook_secret,
        ))

        raw_state = {**raw_state, "appointment": current_appt}
        await svc.update_flow_state(conversation_id, raw_state)
        return current_appt, raw_state

    @staticmethod
    def _merge_flow_fields(
        current: Dict[str, Any],
        updates: Dict[str, Any],
        is_correction: bool,
        required_keys: set,
    ) -> Dict[str, Any]:
        """Merge ``updates`` into ``current`` flow-state dict.

        Rules:
        - Skip ``None`` values.
        - Skip empty/null strings (``"null"``, ``"none"``, ``""``).
        - Skip ``__skip__`` sentinel for required fields.
        - ``"confirmed"`` is always written.
        - Other fields: only fill empty slots unless ``is_correction`` is True.

        Returns a new dict (``current`` is not mutated).
        """
        merged = dict(current)
        for k, v in updates.items():
            if v is None:
                continue
            if isinstance(v, str) and v.strip().lower() in ("null", "none", ""):
                continue
            if v == "__skip__" and k in required_keys:
                continue
            if k == "confirmed":
                merged[k] = v
            elif not merged.get(k) or is_correction:
                merged[k] = v
        return merged

    @staticmethod
    def _rescue_missing_fields(
        current: Dict[str, Any],
        fields_config: List[Dict[str, Any]],
        response_text: str,
        conversation_history: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Extract missing required field values from the LLM response text and
        conversation history when the LLM forgot to include them in <extract>.

        Scans the response text (which often contains a summary table with
        "Label : Value" lines) and falls back to option-matching against the
        full conversation history.
        """
        import re as _re
        from backend.orchestrator.mode_engine import field_is_visible

        rescued: Dict[str, Any] = {}

        for f in fields_config:
            key = f["key"]
            if not f.get("required"):
                continue
            if not field_is_visible(f, current):
                continue
            if current.get(key):
                continue

            label = f.get("label", key)
            opts = f.get("options")

            # Strategy 1: parse "Label : Value" or "Label: Value" from response
            pattern = _re.compile(
                _re.escape(label) + r"\s*[:：]\s*(.+)",
                _re.IGNORECASE,
            )
            match = pattern.search(response_text)
            if match:
                candidate = match.group(1).strip().rstrip("•*\n")
                if opts:
                    allowed = [str(o).strip() for o in opts if o is not None]
                    normalised = _match_option(candidate, allowed)
                    if normalised:
                        rescued[key] = normalised
                        continue
                else:
                    validation = f.get("validation")
                    if validation:
                        from backend.orchestrator.handlers.character_handler import CharacterHandler
                        ok, norm = CharacterHandler._validate_field_value(candidate, validation)
                        if ok:
                            rescued[key] = norm or candidate
                            continue
                    else:
                        if candidate:
                            rescued[key] = candidate
                            continue

            # Strategy 2: scan conversation history for option matches
            if opts and conversation_history:
                allowed = [str(o).strip() for o in opts if o is not None]
                for msg in reversed(conversation_history):
                    content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
                    normalised = _match_option(content.strip(), allowed)
                    if normalised:
                        rescued[key] = normalised
                        break

        return rescued

    @staticmethod
    async def _inject_availability_options(
        session,
        appt_fields: List[Dict[str, Any]],
        appt_state: Dict[str, Any],
    ) -> None:
        """When next field is event_time and artist+event_date are known,
        fetch live availability and set the field's options dynamically."""
        from backend.orchestrator.mode_engine import get_next_field

        next_f = get_next_field(appt_fields, appt_state)
        if not next_f or next_f.get("key") != "event_time":
            return

        artist = appt_state.get("artist")
        event_date_str = appt_state.get("event_date")
        service = appt_state.get("service")
        if not artist or not event_date_str:
            return

        event_date = _parse_date_str(event_date_str)
        if event_date is None:
            return

        try:
            from backend.services.availability_service import AvailabilityService
            av_svc = AvailabilityService(session)
            slots = await av_svc.get_slots_by_resource_name(
                artist, event_date, service_name=service,
            )
            if slots:
                next_f["options"] = slots
                logger.info(
                    "Orchestrator: injected %d availability slots for %s on %s",
                    len(slots), artist, event_date,
                )
        except Exception as exc:
            logger.warning("Orchestrator: could not fetch availability: %s", exc)

    @staticmethod
    async def _inject_reschedule_availability(
        session,
        rs_fields: List[Dict[str, Any]],
        rs_state: Dict[str, Any],
    ) -> None:
        """When the reschedule next step is event_time and artist+event_date are known,
        fetch live availability and populate event_time options in rs_fields."""
        updates = rs_state.get("updates") or {}
        artist = updates.get("artist") or rs_state.get("artist")
        event_date_str = updates.get("event_date")
        if not artist or not event_date_str:
            return

        # Only inject if event_time hasn't been collected yet
        if updates.get("event_time"):
            return

        event_date = _parse_date_str(event_date_str)
        if event_date is None:
            return

        try:
            from backend.services.availability_service import AvailabilityService
            av_svc = AvailabilityService(session)
            slots = await av_svc.get_slots_by_resource_name(artist, event_date)
            if slots:
                for f in rs_fields:
                    if f.get("key") == "event_time":
                        f["options"] = slots
                        break
                logger.info(
                    "Orchestrator: injected %d reschedule slots for %s on %s",
                    len(slots), artist, event_date,
                )
        except Exception as exc:
            logger.warning("Orchestrator: could not fetch reschedule availability: %s", exc)

    @staticmethod
    async def _create_calendar_block_for_appointment(
        session,
        appointment,
        appt_dict: Dict[str, Any],
    ) -> bool:
        """If the appointment has artist + event_date + event_time, create a CalendarBlock
        and optionally a Google Calendar event."""
        import datetime as _dt

        artist = appt_dict.get("artist") or getattr(appointment, "artist", None)
        event_date_str = appt_dict.get("event_date") or getattr(appointment, "event_date", None)
        event_time_str = appt_dict.get("event_time") or getattr(appointment, "event_time", None)
        if not artist or not event_date_str or not event_time_str:
            return True

        try:
            from backend.infra.database.repositories import CalendarResourceRepository, CalendarBlockRepository

            cal_repo = CalendarResourceRepository(session)
            resources = await cal_repo.list_by_resource_name(artist)
            if not resources:
                return True
            resource = resources[0]

            event_date = _parse_date_str(event_date_str)
            if event_date is None:
                return True

            try:
                start_time = _dt.datetime.strptime(event_time_str.strip(), "%H:%M").time()
            except ValueError:
                return True

            service = appt_dict.get("service") or getattr(appointment, "service", None)
            durations = resource.service_durations or {}
            if service and service in durations:
                duration = int(durations[service])
            else:
                duration = int(durations.get("default", 60))
            end_dt = _dt.datetime.combine(event_date, start_time) + _dt.timedelta(minutes=duration)

            block_repo = CalendarBlockRepository(session)

            # Hard conflict guard: block creation if slot overlaps an existing block
            try:
                from sqlalchemy import select as _select
                from backend.infra.database.models.calendar_block import CalendarBlock as _CB
                _overlap_q = _select(_CB).where(
                    _CB.calendar_resource_id == resource.id,
                    _CB.date == event_date,
                    _CB.start_time < end_dt.time(),
                    _CB.end_time > start_time,
                )
                _overlap_result = await session.execute(_overlap_q)
                _overlaps = list(_overlap_result.scalars().all())
                if _overlaps:
                    logger.warning(
                        "Orchestrator: double-booking BLOCKED for resource %s on %s %s-%s "
                        "(conflicts with %d existing block(s))",
                        resource.id, event_date, start_time, end_dt.time(), len(_overlaps),
                    )
                    return False
            except Exception as _exc:
                logger.warning("Orchestrator: could not check for double-booking: %s", _exc)

            await block_repo.create({
                "calendar_resource_id": resource.id,
                "date": event_date,
                "start_time": start_time,
                "end_time": end_dt.time(),
                "block_type": "booked",
                "appointment_id": appointment.id,
                "label": f"{getattr(appointment, 'contact_name', '') or ''} {service or ''}".strip() or None,
            })
            logger.info(
                "Orchestrator: created CalendarBlock for appointment %s on %s %s-%s",
                appointment.id, event_date, start_time, end_dt.time(),
            )

            # If the resource has Google Calendar, also create a real event
            if resource.calendar_type == "google":
                await Orchestrator._create_google_calendar_event(
                    session, resource, appointment, appt_dict,
                    event_date, start_time, end_dt, duration,
                )
            return True
        except Exception as exc:
            logger.warning("Orchestrator: could not create CalendarBlock: %s", exc)
            return True

    @staticmethod
    async def _create_google_calendar_event(
        session,
        resource,
        appointment,
        appt_dict: Dict[str, Any],
        event_date,
        start_time,
        end_dt,
        duration_minutes: int,
    ) -> None:
        """Create a Google Calendar event for the confirmed appointment."""
        import asyncio
        import datetime as _dt

        creds_json = resource.credentials
        if not creds_json:
            from sqlalchemy import select
            from backend.infra.database.models.tool_config import ToolConfig
            result = await session.execute(
                select(ToolConfig).where(ToolConfig.name == "check_calendar_availability")
            )
            row = result.scalar_one_or_none()
            creds_json = row.credentials if row and row.credentials else None

        if not creds_json:
            logger.debug("Orchestrator: no Google credentials for resource %s, skipping event creation", resource.name)
            return

        cal_id = resource.calendar_id or "primary"
        tz_name = resource.timezone or "Europe/Istanbul"

        try:
            from backend.tools.builtin.google_calendar import _build_service
        except ImportError:
            logger.debug("Google Calendar packages not installed")
            return

        try:
            service_name = appt_dict.get("service") or ""
            contact = getattr(appointment, "contact_name", "") or ""
            phone = getattr(appointment, "contact_phone", "") or ""

            start_dt = _dt.datetime.combine(event_date, start_time)
            end_datetime = start_dt + _dt.timedelta(minutes=duration_minutes)

            event_body = {
                "summary": f"{service_name} - {contact}".strip(" -"),
                "description": f"Randevu\nMüşteri: {contact}\nTelefon: {phone}\nHizmet: {service_name}",
                "start": {"dateTime": start_dt.isoformat(), "timeZone": tz_name},
                "end": {"dateTime": end_datetime.isoformat(), "timeZone": tz_name},
            }

            gcal_service = _build_service(creds_json)

            def _sync_insert():
                return gcal_service.events().insert(calendarId=cal_id, body=event_body).execute()

            result = await asyncio.get_event_loop().run_in_executor(None, _sync_insert)
            logger.info(
                "Orchestrator: created Google Calendar event %s for appointment %s",
                result.get("id"), appointment.id,
            )
            # Persist the Google event ID in appointment.extra_fields for later cleanup
            event_id = result.get("id")
            if event_id:
                try:
                    from backend.infra.database.repositories.appointment import AppointmentRepository
                    appt_repo = AppointmentRepository(session)
                    existing = await appt_repo.get_by_id(appointment.id)
                    if existing:
                        extra = dict(existing.extra_fields or {})
                        extra["_google_event_id"] = event_id
                        await appt_repo.update(appointment.id, {"extra_fields": extra})
                        appt_dict["_google_event_id"] = event_id
                        logger.info(
                            "Orchestrator: stored Google event ID %s on appointment %s",
                            event_id, appointment.id,
                        )
                except Exception as _exc:
                    logger.warning("Orchestrator: could not persist Google event ID: %s", _exc)
        except Exception as exc:
            logger.warning("Orchestrator: Google Calendar event creation failed: %s", exc)

    async def get_conversation_history(
        self,
        conversation_id: UUID,
        last_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve persisted messages for a conversation."""
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            conv = await svc.get_conversation(
                conversation_id, last_n_messages=last_n,
            )
            if conv is None:
                return []
            return [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "intent": m.intent,
                    "confidence": m.confidence,
                    "classifier_layer": m.classifier_layer,
                    "rule_matched": m.rule_matched,
                    "fallback_used": m.fallback_used,
                    "total_ms": m.total_ms,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in conv.messages
            ]

    @staticmethod
    def _build_rule_result(
        query: str,
        rule_match: "RuleMatchResult",
        t_start: float,
        *,
        layer: str = "rules_first",
    ) -> OrchestratorResult:
        elapsed = (time.monotonic() - t_start) * 1000
        flow_meta: Dict[str, Any] = {}
        if rule_match.rule.is_flow_rule:
            # Always include the key for flow rules so process_with_tracking can
            # distinguish "flow rule fired (key present, value may be None = flow ended)"
            # from "standalone rule fired within a flow (key absent = preserve flow state)".
            flow_meta["next_flow_context"] = (
                rule_match.next_flow_context.to_dict()
                if rule_match.next_flow_context and rule_match.next_flow_context.active
                else None
            )
        elif rule_match.next_flow_context is not None:
            flow_meta["next_flow_context"] = rule_match.next_flow_context.to_dict()
        logger.info(
            "Orchestrator: %s matched → '%s' (%.0f ms)",
            layer, rule_match.rule.name, elapsed,
        )
        return OrchestratorResult(
            query=query,
            intent=IntentType.RULE,
            answer=rule_match.rendered_answer,
            rule_matched=rule_match.rule.name,
            classification=ClassificationResult(
                intent=IntentType.RULE,
                confidence=1.0,
                classifier_layer=layer,
            ),
            metrics=OrchestratorMetrics(
                total_ms=elapsed,
                classifier_layer=layer,
            ),
            metadata=flow_meta if flow_meta else {},
        )

    def reload_llm(self, llm_client: "BaseLLMClient") -> None:
        """Hot-swap the LLM client across all handlers and the classifier.

        Called when a user adds or activates an LLM via the API so that the
        running orchestrator picks it up without a restart.
        """
        self._llm = llm_client
        for handler in self._handlers.values():
            if hasattr(handler, "_llm"):
                handler._llm = llm_client  # type: ignore[attr-defined]
        from backend.orchestrator.classifiers.llm_classifier import LLMClassifier
        self._llm_classifier = LLMClassifier(llm_client, self._config)
        self._cache = ClassificationCache()  # clear stale classifications
        logger.info("Orchestrator: LLM hot-reloaded to provider=%s", llm_client.provider)

    def reload_character(self, system_prompt: Optional[str]) -> None:
        """Hot-swap the character system prompt.  Pass None to disable character mode."""
        if system_prompt:
            self._handlers[IntentType.CHARACTER] = CharacterHandler(
                self._llm,
                system_prompt,
                timeout_seconds=self._config.llm_timeout_seconds,
                appointment_fields=self._config.appointment_fields or [],
                order_fields=self._config.order_fields if self._config.order_mode_enabled else [],
            )
            self._config.character_system_prompt = system_prompt
            logger.info("Orchestrator: character prompt updated")
        else:
            self._handlers.pop(IntentType.CHARACTER, None)
            self._config.character_system_prompt = None
            logger.info("Orchestrator: character mode disabled")

    def reload_rag(self, rag_service) -> None:
        """Hot-swap the RAG service. Pass None to disable RAG routing."""
        if rag_service is not None:
            from backend.orchestrator.handlers.rag_handler import RAGHandler
            self._handlers[IntentType.RAG] = RAGHandler(rag_service)
            logger.info("Orchestrator: RAG service hot-reloaded")
        else:
            self._handlers.pop(IntentType.RAG, None)
            logger.info("Orchestrator: RAG service removed")

    def _require_session_factory(self) -> None:
        if self._session_factory is None:
            raise RuntimeError(
                "Orchestrator: session_factory is required for conversation tracking. "
                "Pass session_factory when constructing the Orchestrator."
            )

    @staticmethod
    async def _get_last_intent(
        svc: Any,
        conversation_id: UUID,
    ) -> Optional[IntentType]:
        """Read the intent of the most recent assistant message from the DB."""
        intent_str = await svc.get_last_assistant_intent(conversation_id)
        if not intent_str:
            return None
        try:
            return IntentType(intent_str)
        except ValueError:
            return None

    # ── private ──

    async def _classify(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        last_intent: Optional[IntentType] = None,
        flow_ctx: Optional[FlowContext] = None,
    ) -> ClassificationResult:
        """Run the three-layer classification cascade."""

        # Layer 1: PreClassifier (keyword)
        if self._pre_classifier is not None:
            pre = self._pre_classifier.try_classify(query)
            if pre is not None and pre.confidence >= 0.9:
                return pre

        # Layer 2: EmbeddingClassifier
        if self._embedding_classifier is not None and self._embedding_classifier.ready:
            emb = await self._embedding_classifier.classify(query)
            if emb.confidence >= self._config.embedding_confidence_threshold:
                return emb

        # Layer 3: cache → LLM (skip cache when context is present)
        if not conversation_history:
            cached = self._cache.get(query)
            if cached is not None:
                return cached

        if self._llm_classifier is not None:
            max_turns = max(0, self._config.max_conversation_turns)
            history = (
                conversation_history[-max_turns * 2 :]
                if conversation_history and max_turns > 0
                else None
            )
            rule_descs = self._get_rule_descriptions()
            tool_descs = self._get_tool_descriptions()
            result = await self._llm_classifier.classify(
                query,
                rule_descriptions=rule_descs,
                tool_descriptions=tool_descs,
                conversation_history=history,
                last_intent=last_intent,
                flow_ctx=flow_ctx,
            )
            if not conversation_history:
                self._cache.put(query, result)
            return result

        return ClassificationResult(
            intent=self._config.default_intent,
            confidence=0.5,
            reasoning="no classifier available",
        )

    def _get_rule_descriptions(self) -> List[str]:
        if self._rule_engine is None:
            return []
        result = []
        for r in self._rule_engine.rules:
            if not r.is_active:
                continue
            desc = f"{r.name}: {r.description}"
            # Include up to 5 trigger patterns so the LLM knows what words fire this rule
            if r.trigger_patterns:
                shown = r.trigger_patterns[:5]
                desc += f" [triggers: {', '.join(shown)}]"
            # Mark flow rules so the LLM knows they are stateful steps, not standalone FAQ
            if r.is_flow_rule:
                step_info = f"flow={r.flow_id}"
                if r.step_key:
                    step_info += f", step={r.step_key}"
                desc += f" [{step_info}]"
            result.append(desc)
        return result

    def _get_tool_descriptions(self) -> List[str]:
        tool_handler = self._handlers.get(IntentType.TOOL)
        if isinstance(tool_handler, ToolHandler) and tool_handler._registry is not None:
            return tool_handler._registry.get_descriptions()
        return []


def _parse_date_str(date_str: str) -> Optional[_dt.date]:
    """Best-effort date parser for Turkish/ISO date strings."""
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    _TR_MONTHS = {
        "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
        "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
    }
    parts = date_str.lower().split()
    if len(parts) == 3:
        try:
            day = int(parts[0])
            month = _TR_MONTHS.get(parts[1])
            year = int(parts[2])
            if month:
                return _dt.date(year, month, day)
        except (ValueError, TypeError):
            pass
    return None
