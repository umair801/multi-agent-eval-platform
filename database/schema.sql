-- ============================================================
-- AgAI_31: Multi-Agent Eval Platform — Database Schema
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. CONVERSATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_conversations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          TEXT NOT NULL UNIQUE,
    user_message        TEXT NOT NULL,
    intent              TEXT,
    outcome             TEXT,
    turn_count          INTEGER DEFAULT 0,
    total_cost_usd      NUMERIC(10, 6) DEFAULT 0,
    total_latency_ms    INTEGER DEFAULT 0,
    total_tokens_in     INTEGER DEFAULT 0,
    total_tokens_out    INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 2. TRACE STEPS
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_trace_steps (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID REFERENCES evals_conversations(id) ON DELETE CASCADE,
    turn_id             INTEGER NOT NULL,
    agent_name          TEXT NOT NULL,
    step_type           TEXT NOT NULL,
    prompt_text         TEXT,
    model_response      TEXT,
    tool_name           TEXT,
    tool_input          JSONB,
    tool_output         JSONB,
    latency_ms          INTEGER,
    token_count_input   INTEGER,
    token_count_output  INTEGER,
    cost_usd            NUMERIC(10, 6),
    error               TEXT,
    timestamp           TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 3. TOOL CALLS (Gateway log)
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_tool_calls (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id     UUID REFERENCES evals_conversations(id) ON DELETE CASCADE,
    tool_name           TEXT NOT NULL,
    tool_input          JSONB NOT NULL,
    tool_output         JSONB,
    risk_level          TEXT NOT NULL,
    status              TEXT NOT NULL,
    approved_by         TEXT,
    rejection_reason    TEXT,
    latency_ms          INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ
);

-- ============================================================
-- 4. HUMAN APPROVAL QUEUE
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_approval_queue (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_call_id        UUID REFERENCES evals_tool_calls(id) ON DELETE CASCADE,
    conversation_id     UUID REFERENCES evals_conversations(id) ON DELETE CASCADE,
    tool_name           TEXT NOT NULL,
    tool_input          JSONB NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    reviewed_by         TEXT,
    rejection_reason    TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at         TIMESTAMPTZ
);

-- ============================================================
-- 5. PROMPT VERSIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_prompt_versions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version_id          TEXT NOT NULL UNIQUE,
    agent_name          TEXT NOT NULL,
    prompt_text         TEXT NOT NULL,
    model               TEXT NOT NULL,
    is_baseline         BOOLEAN DEFAULT FALSE,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 6. EVAL RESULTS
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_eval_results (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id         UUID REFERENCES evals_conversations(id) ON DELETE CASCADE,
    prompt_version_id       TEXT,
    model                   TEXT,
    task_success            NUMERIC(4, 3),
    grounding_accuracy      NUMERIC(4, 3),
    tool_correctness        NUMERIC(4, 3),
    policy_compliance       NUMERIC(4, 3),
    escalation_correctness  NUMERIC(4, 3),
    avg_latency_ms          INTEGER,
    total_cost_usd          NUMERIC(10, 6),
    flagged_for_review      BOOLEAN DEFAULT FALSE,
    failure_category        TEXT,
    eval_notes              TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 7. OFFLINE EVAL RUNS
-- ============================================================
CREATE TABLE IF NOT EXISTS evals_eval_runs (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id                  TEXT NOT NULL UNIQUE,
    prompt_version_id       TEXT,
    model                   TEXT,
    total_cases             INTEGER,
    passed                  INTEGER,
    failed                  INTEGER,
    task_success_rate       NUMERIC(4, 3),
    grounding_accuracy_avg  NUMERIC(4, 3),
    tool_correctness_avg    NUMERIC(4, 3),
    policy_compliance_avg   NUMERIC(4, 3),
    escalation_accuracy_avg NUMERIC(4, 3),
    avg_latency_ms          INTEGER,
    total_cost_usd          NUMERIC(10, 6),
    report_json             JSONB,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_evals_trace_steps_conversation_id ON evals_trace_steps(conversation_id);
CREATE INDEX IF NOT EXISTS idx_evals_tool_calls_conversation_id ON evals_tool_calls(conversation_id);
CREATE INDEX IF NOT EXISTS idx_evals_approval_queue_status ON evals_approval_queue(status);
CREATE INDEX IF NOT EXISTS idx_evals_eval_results_conversation_id ON evals_eval_results(conversation_id);
CREATE INDEX IF NOT EXISTS idx_evals_conversations_intent ON evals_conversations(intent);
CREATE INDEX IF NOT EXISTS idx_evals_conversations_outcome ON evals_conversations(outcome);