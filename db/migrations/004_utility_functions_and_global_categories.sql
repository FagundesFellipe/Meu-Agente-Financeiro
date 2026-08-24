-- ============================================================================
-- Funções utilitárias, índices de performance e inserção das categorias globais
-- padrão compartilhadas entre todos os usuários.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. clamp_recurrence_day: ajusta o dia de recorrência para o último dia
--    válido do mês alvo. Exemplo: dia 31 em fevereiro vira 28 (ou 29 em ano
--    bissexto); dia 31 em abril vira 30.
--    Deve ser chamada pela aplicação ao gerar gastos automáticos a partir de
--    um recurring_expense.recurrence_day.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION clamp_recurrence_day(p_day INT, p_month_date DATE)
RETURNS INT AS $$
DECLARE
    last_day INT;
BEGIN
    last_day := EXTRACT(DAY FROM (date_trunc('month', p_month_date) + INTERVAL '1 month' - INTERVAL '1 day'))::INT;
    RETURN LEAST(p_day, last_day);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ----------------------------------------------------------------------------
-- 2. Índice para acelerar as políticas de RLS que filtram por user_id na fila
--    de mensagens. Sem este índice, todas as queries de polling do worker
--    fariam sequential scan na message_queue.
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_message_queue_user_id
    ON message_queue (user_id)
    WHERE user_id IS NOT NULL;

-- Também para conversations (já habilitada com RLS em 003)
CREATE INDEX IF NOT EXISTS idx_conversations_user_id
    ON conversations (user_id);

