-- Orchestrator rules table (PostgreSQL).
-- Run with: psql $DATABASE_URL -f 001_orchestrator_rules.sql
-- Or use init_db() in code (creates all tables including this one).

CREATE TABLE IF NOT EXISTS orchestrator_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    trigger_patterns TEXT[] NOT NULL DEFAULT '{}',
    response_template TEXT NOT NULL,
    variables JSONB NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_orchestrator_rules_priority
    ON orchestrator_rules (priority DESC);
CREATE INDEX IF NOT EXISTS ix_orchestrator_rules_is_active
    ON orchestrator_rules (is_active);

COMMENT ON TABLE orchestrator_rules IS 'User-defined rules for orchestrator (keyword/regex → fixed response)';
