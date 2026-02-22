# Orchestrator & Conversation Tracking — Bağlantılar ve Akış

## Genel mimari

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLI (rag_cli) / API                                                         │
│  - orchestrator_chat() → orch.start_conversation() / process_with_tracking()  │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Orchestrator                                                                │
│  - start_conversation() → ConversationService (session_factory)              │
│  - process_with_tracking(query, conv_id)                                     │
│  - end_conversation(conv_id)                                                 │
│  - process(query, conversation_history, last_intent)  [core, DB-agnostic]    │
└───────────────────────────────────────┬─────────────────────────────────────┘
                    │                                     │
                    │ session_factory                     │ process()
                    ▼                                     ▼
┌──────────────────────────────┐    ┌──────────────────────────────────────────┐
│  ConversationService        │    │  Classification → Handler dispatch        │
│  - start_conversation()      │    │  - PreClassifier / Embedding / LLM        │
│  - record_user_message()     │    │  - RAGHandler / DirectHandler / Rule / Tool│
│  - record_assistant_message()│    │  - conversation_history handler'lara geçer│
│  - get_history_as_turns()    │    └──────────────────────────────────────────┘
│  - get_last_assistant_intent()│
│  - close_conversation()      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  Repositories (ConversationRepository, MessageRepository, MessageEventRepo) │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  DB Models: conversations, messages, message_events                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

## process_with_tracking akışı (adım adım)

1. **History yükle**  
   `ConversationService.get_history_as_turns(conv_id, max_turns)` → `[{role, content}, ...]`

2. **Son intent**  
   `_get_last_intent(svc, conv_id)` → son asistan mesajının `intent` değeri (DB’den).

3. **User mesajını kaydet**  
   `svc.record_user_message(conv_id, query)` → commit.

4. **Orkestrasyon**  
   `process(query, conversation_history=..., last_intent=...)`  
   → classify → handler.handle(query, conversation_history=...) → fallback gerekirse Direct.

5. **Asistan mesajını kaydet**  
   Yeni session: `svc.record_assistant_message(conv_id, result)` → events + commit.

6. **Sonuç dön**  
   `OrchestratorResult` çağırana döner.

## Bağlantı kontrol listesi

| Kaynak | Hedef | Bağlantı |
|--------|--------|----------|
| CLI | OrchestratorService.build(session_factory=sf) | ✓ |
| CLI | orch.start_conversation() → conv_id, orch.process_with_tracking(q, conv_id), orch.end_conversation(conv_id) | ✓ |
| Orchestrator | ConversationService (lazy import, session_factory() ile session) | ✓ |
| ConversationService | ConversationRepository, MessageRepository, MessageEventRepository | ✓ |
| Orchestrator._get_last_intent | ConversationService.get_last_assistant_intent() | ✓ |
| process() | handler.handle(query, conversation_history=...) | ✓ |
| record_assistant_message | OrchestratorResult → Message + MessageEvent | ✓ |
| init_db() | Tüm modeller (engine'de import backend.infra.database.models) → conversations, messages, message_events | ✓ |
| Migration 002 | conversations, messages, message_events tabloları (opsiyonel; init_db yeterli) | ✓ |

## Kurulum

- **Veritabanı:** CLI veya API başlarken `init_db()` çağrılmalı. `backend.infra.database.engine` tüm model modülünü import ettiği için `create_all()` conversations, messages, message_events tablolarını da oluşturur.
- **Session factory:** Orchestrator ile tracking kullanmak için `OrchestratorService.build(..., session_factory=sf)` ile `sf` mutlaka verilmelidir.

## Dosya referansları

- **Orchestrator:** `backend/orchestrator/orchestrator.py`
- **ConversationService:** `backend/services/conversation_service.py`
- **Repositories:** `backend/infra/database/repositories/conversation.py`
- **Models:** `backend/infra/database/models/conversation.py`
- **CLI sohbet:** `backend/scripts/rag_cli.py` → `orchestrator_chat()`
- **Migration:** `backend/infra/database/migrations/002_conversations.sql`
