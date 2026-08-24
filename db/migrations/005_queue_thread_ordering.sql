-- Garante que o polling encontre rapidamente a primeira mensagem ainda ativa
-- de cada conversa. A seleção em shared.queue usa este índice para impedir que
-- dois workers reivindiquem mensagens do mesmo thread_id em paralelo.
ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS claim_token UUID;

CREATE INDEX IF NOT EXISTS idx_message_queue_thread_ordering
    ON message_queue (thread_id, created_at, id)
    WHERE status IN ('queued', 'processing');
