-- ============================================================================
-- Mecanismos transversais: atualizacao automatica de updated_at e isolamento
-- de dados por usuario (Row-Level Security).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Funcao generica para manter updated_at sincronizado
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 2. Triggers de updated_at
-- ----------------------------------------------------------------------------
CREATE TRIGGER trg_message_queue_updated_at
    BEFORE UPDATE ON message_queue
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_user_updated_at
    BEFORE UPDATE ON "user"
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_category_updated_at
    BEFORE UPDATE ON category
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_recurring_expense_updated_at
    BEFORE UPDATE ON recurring_expense
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_expense_updated_at
    BEFORE UPDATE ON expense
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ----------------------------------------------------------------------------
-- 3. Row-Level Security (RLS): isolamento de dados por usuario
-- ----------------------------------------------------------------------------
-- A aplicacao deve definir a variavel de sessao antes de executar queries:
--   SET LOCAL app.current_user_id = '<uuid-do-usuario>';
-- Quando a variavel nao esta definida, as politicas nao retornam linhas,
-- impedindo acesso acidental sem contexto de usuario.

-- Helper seguro para ler o user_id da sessao sem erro de conversao
CREATE OR REPLACE FUNCTION current_app_user_id()
RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_user_id', true), '')::UUID;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- 3.1 Habilita RLS nas tabelas
ALTER TABLE message_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;
ALTER TABLE category ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_expense ENABLE ROW LEVEL SECURITY;
ALTER TABLE expense ENABLE ROW LEVEL SECURITY;
ALTER TABLE expense_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_usage ENABLE ROW LEVEL SECURITY;

-- 3.2 Políticas baseadas em user_id

-- Usuario: cada um ve e pode alterar apenas seu proprio registro
CREATE POLICY user_isolation_policy ON "user"
    FOR ALL
    USING (id = current_app_user_id())
    WITH CHECK (id = current_app_user_id());

-- Fila de mensagens
CREATE POLICY message_queue_isolation_policy ON message_queue
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

-- Conversas
CREATE POLICY conversations_isolation_policy ON conversations
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

-- Categorias: pessoais isoladas; globais (user_id IS NULL) visiveis a todos
CREATE POLICY category_select_policy ON category
    FOR SELECT
    USING (user_id = current_app_user_id() OR user_id IS NULL);

CREATE POLICY category_modify_policy ON category
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

-- Gastos fixos
CREATE POLICY recurring_expense_isolation_policy ON recurring_expense
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

-- Gastos
CREATE POLICY expense_isolation_policy ON expense
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

-- Auditoria
CREATE POLICY expense_audit_log_isolation_policy ON expense_audit_log
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());

-- Rastreamento de custo
CREATE POLICY model_usage_isolation_policy ON model_usage
    FOR ALL
    USING (user_id = current_app_user_id())
    WITH CHECK (user_id = current_app_user_id());
