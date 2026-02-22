-- 002_conversations.sql
-- Conversation, Message, MessageEvent tables for tracking chat sessions.
-- Run after 001_orchestrator_rules.sql.

BEGIN;

-- ──────────────────────────────────────────────
-- conversations
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform        VARCHAR(32)  NOT NULL DEFAULT 'cli',
    channel_id      VARCHAR(255),
    contact_phone   VARCHAR(32),
    contact_email   VARCHAR(255),
    contact_name    VARCHAR(255),
    contact_meta    JSONB,
    status          VARCHAR(16)  NOT NULL DEFAULT 'active',
    llm_id          UUID,
    embedding_id    UUID,
    message_count   INTEGER      NOT NULL DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_conversations_platform        ON conversations (platform);
CREATE INDEX IF NOT EXISTS ix_conversations_status          ON conversations (status);
CREATE INDEX IF NOT EXISTS ix_conversations_channel_id      ON conversations (channel_id);
CREATE INDEX IF NOT EXISTS ix_conversations_contact_phone   ON conversations (contact_phone);
CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at ON conversations (last_message_at);

-- ──────────────────────────────────────────────
-- messages
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID         NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role                VARCHAR(16)  NOT NULL,
    content             TEXT         NOT NULL DEFAULT '',
    intent              VARCHAR(32),
    confidence          DOUBLE PRECISION,
    classifier_layer    VARCHAR(32),
    rule_matched        VARCHAR(255),
    fallback_used       BOOLEAN      NOT NULL DEFAULT FALSE,
    needs_clarification BOOLEAN      NOT NULL DEFAULT FALSE,
    total_ms            DOUBLE PRECISION,
    llm_calls_count     INTEGER      NOT NULL DEFAULT 0,
    sources             JSONB,
    extra_metadata      JSONB,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_id ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS ix_messages_role            ON messages (role);
CREATE INDEX IF NOT EXISTS ix_messages_created_at      ON messages (created_at);

-- ──────────────────────────────────────────────
-- message_events
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS message_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id  UUID         NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    event_type  VARCHAR(64)  NOT NULL,
    data        JSONB,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_message_events_message_id ON message_events (message_id);
CREATE INDEX IF NOT EXISTS ix_message_events_event_type ON message_events (event_type);

COMMIT;
