-- ============================================================================
-- RF-017/RF-019: índices de relatórios e registro de consultas não suportadas.
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_expense_user_occurred_at
    ON expense (user_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_expense_user_category_occurred_at
    ON expense (user_id, category_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS unsupported_report_query (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES "user"(id),
    raw_question         TEXT NOT NULL,
    intent               TEXT NOT NULL,
    normalized_question  TEXT NOT NULL,
    reason               TEXT,
    source_message_id    UUID REFERENCES message_queue(id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE unsupported_report_query ENABLE ROW LEVEL SECURITY;

CREATE POLICY unsupported_report_query_isolation_policy
    ON unsupported_report_query
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

CREATE INDEX IF NOT EXISTS idx_unsupported_report_query_created_at
    ON unsupported_report_query (created_at DESC);
