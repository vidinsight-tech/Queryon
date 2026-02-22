# Orchestrator Akış ve Bağlantı Doğrulama Raporu

## 1. CLI → Orchestrator Bağlantısı

| Adım | Kod | Doğru |
|------|-----|--------|
| Session factory | `main()` → `sf = build_session_factory(engine)` | ✓ |
| Orchestrator sohbet handler | `MAIN_HANDLERS["7"] = orchestrator_chat` | ✓ |
| orchestrator_chat | `OrchestratorService.build(..., session_factory=sf)` | ✓ |
| Konuşma başlatma | `conv_id = await orch.start_conversation(platform="cli", ...)` | ✓ |
| Her mesaj | `result = await orch.process_with_tracking(q, conv_id)` | ✓ |
| Konuşma bitiş | `await orch.end_conversation(conv_id)` | ✓ |

## 2. OrchestratorService.build() Bağlantıları

| Bağlantı | Kod | Doğru |
|----------|-----|--------|
| Kurallar DB'den | `RuleRepository(session).list_active()` | ✓ |
| RuleEngine | `RuleEngine(db_rules)` (kurallar varsa) | ✓ |
| Orchestrator oluşturma | `Orchestrator(llm, config, rag_service=..., rule_engine=..., session_factory=...)` | ✓ |
| initialize() | `await orch.initialize()` (embedding prototype'ları) | ✓ |

## 3. process_with_tracking() Akışı

| Sıra | İşlem | Bağlantı |
|------|--------|----------|
| 1 | Session aç | `async with self._session_factory() as session` | ✓ |
| 2 | ConversationService | `svc = ConversationService(session)` | ✓ |
| 3 | History | `conversation_history = await svc.get_history_as_turns(conversation_id, max_turns)` | ✓ |
| 4 | last_intent | `last_intent = await self._get_last_intent(svc, conversation_id)` | ✓ |
| 5 | flow_state | `flow_state_raw = await svc.get_flow_state(conversation_id)` | ✓ |
| 6 | FlowContext | `flow_ctx = FlowContext.from_dict(flow_state_raw)` | ✓ |
| 7 | User mesaj kaydet | `await svc.record_user_message(conversation_id, query)` + commit | ✓ |
| 8 | process() | `result = await self.process(query, conversation_history=..., last_intent=..., flow_ctx=flow_ctx)` | ✓ |
| 9 | next_flow_context | `next_flow_dict = result.metadata.get("next_flow_context")` | ✓ |
| 10 | Yeni session | `async with self._session_factory() as session` | ✓ |
| 11 | Assistant mesaj | `await svc.record_assistant_message(conversation_id, result)` | ✓ |
| 12 | flow_state güncelle | `if result.intent == IntentType.RULE: await svc.update_flow_state(..., new_flow_ctx.to_dict() or None)` | ✓ |
| 13 | Commit | `await session.commit()` | ✓ |

## 4. process() Karar Akışı

| Öncelik | Koşul | Sonuç |
|---------|--------|--------|
| 0 | `flow_ctx.active` ve `rule_engine` → `match(query, flow_ctx=flow_ctx)` | Eşleşirse: `_build_rule_result(..., layer="flow_rule")` |
| 1 | `config.rules_first` ve `rule_engine` → `match(query, flow_ctx=flow_ctx)` | Eşleşirse: `_build_rule_result(..., layer="rules_first")` |
| 2 | PreClassifier → EmbeddingClassifier → LLMClassifier | classification |
| 3 | confidence < min_confidence | ASK_USER veya default_intent |
| 4 | Handler dispatch (RAG/Direct/Rule/Tool) | handler.handle(query, conversation_history=...) |
| 5 | RAG boş ve fallback_to_direct | DirectHandler.handle() |
| 6 | result.classification, result.metrics set | return result |

## 5. Rule Engine → Orchestrator Bağlantısı

| Yol | next_flow_context nereye yazılır |
|-----|----------------------------------|
| flow_rule / rules_first | `_build_rule_result()` → `result.metadata["next_flow_context"] = rule_match.next_flow_context.to_dict()` |
| Classification → RuleHandler | `RuleHandler.handle()` → `return OrchestratorResult(..., metadata={"next_flow_context": match.next_flow_context.to_dict()})` |

Her iki yolda da `result.metadata["next_flow_context"]` process_with_tracking tarafından okunup flow_state olarak DB'ye yazılıyor.

## 6. ConversationService ↔ Repository

| Metod | Repository metodu | Doğru |
|-------|-------------------|--------|
| get_flow_state(conversation_id) | ConversationRepository.get_flow_state(conversation_id) | ✓ |
| update_flow_state(conversation_id, flow_state) | ConversationRepository.update_flow_state(...) | ✓ |
| get_history_as_turns | MessageRepository.get_recent() → role/content listesi | ✓ |
| get_last_assistant_intent | MessageRepository.get_recent() → son assistant intent | ✓ |
| record_user_message | MessageRepository.add_user_message + increment_message_count | ✓ |
| record_assistant_message | MessageRepository.add_assistant_message + events + increment_message_count | ✓ |

## 7. Veritabanı Tabloları (init_db)

| Tablo | Kaynak | Oluşturulma |
|-------|--------|-------------|
| conversations, messages, message_events | `backend.infra.database.models` (engine'de import) | init_db() → create_all() |
| orchestrator_rules | `backend.orchestrator.rules.models` (rag_cli.py satır 24'te import) | init_db() öncesi import edildiği için Base.metadata'da, create_all() ile |

CLI başlarken `rag_cli` import edilir → `backend.orchestrator.rules.models` import edilir → OrchestratorRule Base'e eklenir → main() içinde init_db() çağrılır → tüm tablolar oluşur.

## 8. Handler conversation_history Bağlantısı

| Handler | conversation_history kullanımı |
|---------|---------------------------------|
| BaseHandler | handle(..., conversation_history=...) imzası | ✓ |
| DirectHandler | _build_prompt(query, conversation_history) | ✓ |
| RAGHandler | _enrich_query(query, conversation_history) | ✓ |
| RuleHandler | match/match_with_llm (flow_ctx orchestrator'da kullanılıyor, handler'da yok) | ✓ |
| ToolHandler | Parametre var (kullanım opsiyonel) | ✓ |

Flow eşleşmesi orchestrator içinde (process adım 0 ve 1) yapıldığı için RuleHandler'a flow_ctx geçilmez; sadece classification yolunda RuleHandler çalışır.

## 9. Özet

- **CLI → Orchestrator → process_with_tracking → process → RuleEngine / Handlers** zinciri doğru.
- **flow_state** okuma/yazma (get_flow_state, update_flow_state) ve **next_flow_context** (metadata) bağlantısı doğru.
- **ConversationService** ve **ConversationRepository** metotları birbiriyle uyumlu.
- **init_db** ile **orchestrator_rules** tablosu, CLI'nin rules modelini import etmesi sayesinde oluşturuluyor.
- Tüm handler'lar **conversation_history** alıyor; Direct ve RAG bunu kullanıyor.

Son kontrol tarihi: 2026-02-22
