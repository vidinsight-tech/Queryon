# Queryon — Configuration & Behaviour Reference

This document is the single source of truth for **what happens under what conditions** in the
Queryon orchestrator. It covers intent routing, fallback policies, tools, flow rules, and the
full environment-variable / config-field mapping.

---

## 1. Intent Routing — Decision Flow

Every user message goes through the following steps **in order**. The first step that produces a
result short-circuits the rest.

```
User message
    │
    ▼
[Step 0] Flow-aware rule match ─────────────────────────────────────────────────┐
    │  Only when the user is inside an active multi-step flow.                  │
    │  The engine tries flow rules for the current step first.                  │  → RULE answer
    │                                                                            │
    ▼                                                                            │
[Step 1] rules_first keyword match ─────────────────────────────────────────────┤
    │  If config.rules_first = true, pattern-match all active standalone rules. │  → RULE answer
    │  No LLM call. Fast (<1 ms).                                               │
    │                                                                            │
    ▼                                                                            │
[Step 2] Three-layer classification ─────────────────────────────────────────────┘
    │
    ├─► Layer 1: PreClassifier  — keyword / regex, no LLM  (~0 ms)
    │       If confidence ≥ 0.9 → accepted immediately.
    │
    ├─► Layer 2: EmbeddingClassifier — cosine similarity against intent prototypes
    │       If confidence ≥ config.embedding_confidence_threshold → accepted.
    │       (Skipped if no embedding model is configured.)
    │
    └─► Layer 3: LLM Classifier — full prompt, optional conversation history
            Result is cached for exact-match repeated queries
            (cache bypassed when conversation_history is present).
    │
    ▼
[Step 3] Confidence gate  [policy: min_confidence + low_confidence_strategy]
    │  If confidence < min_confidence:
    │    • low_confidence_strategy = "fallback"  → use default_intent, continue
    │    • low_confidence_strategy = "ask_user"  → return needs_clarification response
    │
    ▼
[Step 3b] enabled_intents gate  [policy: enabled_intents + default_intent]
    │  If classified intent is NOT in enabled_intents → use default_intent, continue.
    │
    ▼
[Step 4] Dispatch to handler  [policy: when_rag_unavailable / default_intent]
    │  If intent = RAG and RAG handler is not registered (Qdrant unreachable at startup):
    │    • when_rag_unavailable = "direct"    → route to DirectHandler silently
    │    • when_rag_unavailable = "ask_user"  → return service-unavailable response
    │  Else if intent has no handler → use default_intent → fallback to DIRECT.
    │
    ▼
[Step 5] RAG empty fallback  [policy: fallback_to_direct]
    │  If intent = RAG and handler returned no answer:
    │    • fallback_to_direct = true  → re-run with DirectHandler, mark fallback_used=true
    │    • fallback_to_direct = false → return empty/no-answer response
    │
    ▼
Result returned to caller
```

### Handler summary

| Intent  | Handler         | Requires                          |
|---------|-----------------|-----------------------------------|
| `rag`   | RAGHandler      | Qdrant + embedding model          |
| `direct`| DirectHandler   | LLM only                          |
| `rule`  | RuleHandler     | At least one active rule          |
| `tool`  | ToolHandler     | LLM + ≥1 enabled tool in registry |

---

## 2. Fallback Policies — Four Scenarios

| # | Scenario | Config fields | Values |
|---|----------|---------------|--------|
| 1 | Confidence below threshold | `min_confidence` + `low_confidence_strategy` | `"fallback"` → use `default_intent`; `"ask_user"` → clarification prompt |
| 2 | Intent disabled by admin | `enabled_intents` + `default_intent` | Always falls back to `default_intent` |
| 3 | RAG service unreachable | `when_rag_unavailable` | `"direct"` (default) or `"ask_user"` |
| 4 | RAG returned no documents | `fallback_to_direct` | `true` (default) → DirectHandler; `false` → empty response |

**`default_intent`** is the shared fallback for scenarios 1 and 2. It does **not** affect
scenarios 3 and 4 (those have dedicated fields).

Every fallback decision is logged with the config field name that triggered it, e.g.:
```
Orchestrator: confidence=0.42 < min_confidence=0.70, low_confidence_strategy=fallback → default_intent=rag
Orchestrator: RAG handler unavailable, when_rag_unavailable=direct → routing to direct
Orchestrator: RAG returned no answer, fallback_to_direct=True → direct
```

---

## 3. Tools

### When a tool is called

A tool is called when the orchestrator routes to `IntentType.TOOL`. This happens when:
1. The LLM classifier decides the query requires a tool (date/time lookup, HTTP call, RAG search,
   calendar check).
2. `tool` is in `enabled_intents`.
3. At least one tool is registered **and enabled** in the registry.

### Enabled / disabled at runtime

Each tool has an `enabled` flag stored in the `tool_configs` database table.

- **GET /api/v1/tools** — list all tools with their current `enabled` state.
- **PATCH /api/v1/tools/{name}** — toggle `enabled` or update `description`. The change takes
  effect immediately (live registry updated in memory; no restart needed).

Disabled tools are **excluded from the schema sent to the LLM**, so the model cannot select them.
If all tools are disabled, `ToolHandler` returns a "not configured" message without calling the LLM.

### Built-in tools

| Tool name                    | Always on | Requires                        |
|------------------------------|-----------|---------------------------------|
| `get_current_time`           | ✓         | —                               |
| `get_current_date`           | ✓         | —                               |
| `http_request`               | ✓         | —                               |
| `search_knowledge_base`      | If Qdrant available | `QDRANT_URL` + embedding key |
| `check_calendar_availability`| If credentials stored | Google service-account JSON via `POST /api/v1/tools/google-calendar/oauth` |

### Tool execution flow

```
ToolHandler.handle(query)
    │
    ├─ get_schema_for_llm()  — only enabled tools
    │
    ├─ llm.function_call(query, schemas)
    │       OpenAI: native tools= parameter
    │       Gemini: prompt-based JSON extraction
    │
    ├─ tool_def.handler(**arguments)  — actual function called
    │
    └─ llm.complete(synthesis_prompt)  — natural-language answer from tool result
```

---

## 4. Rule Engine

### Standalone rules

A rule fires when:
1. `is_active = true`
2. `flow_id` is NULL (standalone, not part of a flow)
3. A trigger pattern matches the user's query
4. All **conditions** (if any) pass

Rules are checked in descending `priority` order. The first match wins.

#### Trigger patterns

| Pattern format | Example | Match behaviour |
|----------------|---------|-----------------|
| Plain string   | `"fiyat"` | Substring match (case-insensitive) |
| `r:` prefix    | `r:^(fiyat\|ücret)` | Full regex (case-insensitive) |
| `*` wildcard   | `"*"` | Always matches (catch-all) |

#### Conditions (optional)

Conditions narrow **when** a rule fires even if patterns match.

```json
{
  "time_window": {
    "start": "09:00",
    "end":   "17:00",
    "timezone": "Europe/Istanbul"
  },
  "platforms": ["web", "whatsapp"]
}
```

| Key | Type | Behaviour |
|-----|------|-----------|
| `time_window` | object | Rule fires only when local time is within `[start, end]`. Overnight ranges (e.g. 22:00–06:00) are supported. Malformed values fail open (rule still fires). |
| `platforms` | string[] | Rule fires only when the request's `platform` is in the list. If no platform is provided by the caller, this condition is skipped. |

To set conditions: `PATCH /api/v1/rules/{id}` with `{ "conditions": { … } }`.

### Flow rules

A **flow** is a sequence of rules linked by `flow_id`. Each rule in the flow represents one step.

| Field | Type | Meaning |
|-------|------|---------|
| `flow_id` | string | Groups rules into the same flow. |
| `step_key` | string | This rule's name within the flow (e.g. `"start"`, `"confirm"`). |
| `required_step` | string \| null | The step the user must currently be at for this rule to fire. `null` = flow entry point (no prerequisite). |
| `next_steps` | object \| null | Maps user reply choices to the next `step_key`. `null` = flow ends here. |

#### `next_steps` example

```json
{
  "A": "danismanlik",
  "B": "egitim",
  "C": "destek",
  "*": "destek"
}
```

- Keys `"A"`, `"B"`, `"C"` — matched against the user's reply (case-insensitive, whole-word for ≤2 chars).
- Key `"*"` — wildcard catch-all used when no other choice matches.

#### Flow execution sequence

```
User enters "randevu" (entry trigger)
    └─ matches flow entry rule (required_step = null, flow_id = "randevu_flow")
       → response rendered, FlowContext set to step_key of this rule

Next message from user
    └─ Step 0: engine looks for flow rules where
               flow_id = active flow AND required_step = current_step
       → if next_steps present: user's reply is matched against choices
         → transitions to target step_key
       → if no flow rule matches: falls through to standalone rules

Flow ends when matched rule has next_steps = null
```

---

## 5. Orchestrator Config — All Fields

Managed via **GET / PUT `/api/v1/orchestrator/config`**.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled_intents` | string[] | `["rag","direct","rule","tool"]` | Intents the orchestrator may route to. Classified intents outside this list fall back to `default_intent`. |
| `default_intent` | string | `"rag"` | Fallback intent for low-confidence (strategy=fallback) and disabled-intent scenarios. |
| `rules_first` | bool | `true` | Run keyword rule matching before classification. Fast, no LLM. |
| `fallback_to_direct` | bool | `true` | **Scenario 4** — if RAG returns no answer, re-run with DirectHandler. |
| `when_rag_unavailable` | `"direct"` \| `"ask_user"` | `"direct"` | **Scenario 3** — behaviour when Qdrant was unreachable at startup. |
| `min_confidence` | float [0,1] | `0.7` | Classification score below which the confidence gate triggers. |
| `low_confidence_strategy` | `"fallback"` \| `"ask_user"` | `"fallback"` | **Scenario 1** — what to do when confidence < `min_confidence`. |
| `embedding_confidence_threshold` | float [0,1] | `0.85` | Minimum score for the embedding classifier to short-circuit the LLM classifier. |
| `classification_prompt_override` | string \| null | `null` | Custom system prompt for the LLM classifier. `null` uses the built-in prompt. |
| `llm_timeout_seconds` | float \| null | `60.0` | Per-call LLM timeout. `null` = no timeout. Applies to classification, direct answers, and rule matching. |
| `max_conversation_turns` | int [0,100] | `10` | How many recent turns to include as context for classification. `0` = no history. |

---

## 6. Environment Variables

### Required

| Variable | Example | Used by |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@localhost/queryon` | SQLAlchemy engine |
| `OPENAI_API_KEY` | `sk-…` | OpenAI LLM + embeddings |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `AIza…` | Gemini LLM + embeddings (alternative to OpenAI) |

At least one LLM key is required. If both are set, OpenAI takes precedence.

### Optional — Qdrant (RAG)

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server address |
| `QDRANT_API_KEY` | — | API key for Qdrant Cloud |
| `QDRANT_TIMEOUT` | `30` | Request timeout in seconds |
| `QDRANT_VECTOR_SIZE` | `1536` | Must match the embedding model's output dimension ¹ |
| `QDRANT_COLLECTION_NAME` | `knowledge_base` | Collection used for document storage and search |
| `QDRANT_DISTANCE` | `Cosine` | Distance metric: `Cosine`, `Dot`, or `Euclid` |

¹ Common values: `1536` (OpenAI `text-embedding-3-small`), `3072` (`text-embedding-3-large`),
`768` (Gemini `text-embedding-004`).

### Optional — LLM model selection

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `gpt-4o-mini` (OpenAI) / `gemini-2.0-flash` (Gemini) | Model name passed to the provider |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model (ignored for Gemini) |

### Optional — Server

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated list of allowed CORS origins |

### Starting the API

```bash
# Development
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000

# With env vars inline
OPENAI_API_KEY=sk-… DATABASE_URL=postgresql+asyncpg://… uvicorn backend.api.main:app --reload
```

### Starting the frontend

```bash
cd frontend
# Set NEXT_PUBLIC_API_URL=http://localhost:8000 in frontend/.env.local
npm run dev   # → http://localhost:3000
```

---

## 7. Quick Recipes

**"Always use direct LLM, disable RAG"**
```json
{ "enabled_intents": ["direct","rule","tool"], "default_intent": "direct" }
```

**"Ask user to clarify when unsure"**
```json
{ "min_confidence": 0.75, "low_confidence_strategy": "ask_user" }
```

**"RAG unavailable → tell user instead of silently switching"**
```json
{ "when_rag_unavailable": "ask_user" }
```

**"Rules fire even outside business hours except this one"**
```json
PATCH /api/v1/rules/{id}
{ "conditions": { "time_window": { "start": "09:00", "end": "18:00", "timezone": "Europe/Istanbul" } } }
```

**"Disable HTTP tool without restarting"**
```
PATCH /api/v1/tools/http_request   { "enabled": false }
```
