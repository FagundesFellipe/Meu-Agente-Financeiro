-- ============================================================================
-- Materialização de gastos recorrentes em lançamentos (Stack 2).
--
-- Acrescenta a chave de unicidade que torna a duplicação de um lançamento
-- gerado fisicamente impossível. A proteção vive aqui, e não no código Python,
-- porque o catch-up roda a cada mensagem do usuário e pode executar
-- concorrentemente em workers distintos: uma checagem "consultar, depois
-- inserir" na aplicação tem janela de corrida entre as duas operações.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Período de competência do lançamento gerado.
--    Coluna explícita em vez de derivar de occurred_at: PostgreSQL não aceita
--    índice único sobre date_trunc('month', occurred_at), porque a função não
--    é IMMUTABLE para TIMESTAMPTZ.
-- ----------------------------------------------------------------------------
ALTER TABLE expense ADD COLUMN IF NOT EXISTS recurrence_period DATE;

COMMENT ON COLUMN expense.recurrence_period IS
    'Primeiro dia do mês de competência, quando o lançamento veio de uma regra recorrente. NULL para gasto pontual.';

-- ----------------------------------------------------------------------------
-- 2. Uma regra gera no máximo um lançamento por mês de competência.
-- ----------------------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_expense_recurring_period
    ON expense (recurring_expense_id, recurrence_period)
    WHERE recurring_expense_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Coerência do par: ou o lançamento veio de uma regra e tem competência,
--    ou é um gasto pontual e não tem nenhum dos dois.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_recurrence_period_pairing'
    ) THEN
        ALTER TABLE expense ADD CONSTRAINT chk_recurrence_period_pairing CHECK (
            (recurring_expense_id IS NULL AND recurrence_period IS NULL)
            OR (recurring_expense_id IS NOT NULL AND recurrence_period IS NOT NULL)
        );
    END IF;
END;
$$;

-- ----------------------------------------------------------------------------
-- 4. Apoio ao catch-up: ler as regras ativas de um usuário a cada mensagem.
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_recurring_expense_active
    ON recurring_expense (user_id) WHERE is_active;
