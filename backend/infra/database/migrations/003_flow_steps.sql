-- Migration 003: Multi-step conversational flow support
-- Adds flow columns to orchestrator_rules and flow_state to conversations.

-- ── orchestrator_rules: flow fields ───────────────────────────────
ALTER TABLE orchestrator_rules
    ADD COLUMN IF NOT EXISTS flow_id      VARCHAR(64)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS step_key     VARCHAR(64)  DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS required_step VARCHAR(64) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS next_steps   JSONB        DEFAULT NULL;

CREATE INDEX IF NOT EXISTS ix_orchestrator_rules_flow_id
    ON orchestrator_rules (flow_id) WHERE flow_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_orchestrator_rules_flow_step
    ON orchestrator_rules (flow_id, required_step)
    WHERE flow_id IS NOT NULL;

-- ── conversations: flow state ─────────────────────────────────────
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS flow_state JSONB DEFAULT NULL;
