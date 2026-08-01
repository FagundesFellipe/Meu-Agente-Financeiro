-- ============================================================================
-- Tabelas de domínio financeiro: usuário, canais, categorias, gastos,
-- gastos fixos, auditoria e rastreamento de custo de LLM.
-- ============================================================================

CREATE TABLE IF NOT EXISTS "user" (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number      TEXT NOT NULL UNIQUE,                        -- Número de telefone normalizado (canal primário: WhatsApp)
    name              TEXT,                                        -- Nome de exibição do usuário (coletado no onboarding)
    timezone          TEXT NOT NULL DEFAULT 'America/Sao_Paulo',   -- Fuso horário do usuário para interpretação de datas
    currency          TEXT NOT NULL DEFAULT 'BRL',                 -- Moeda padrão do usuário (ISO 4217)
    onboarding_status TEXT NOT NULL DEFAULT 'pending',             -- Estado do onboarding: pending | in_progress | completed
    deleted_at        TIMESTAMPTZ,                                 -- Soft delete para conformidade LGPD (NULL = conta ativa)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Vincula um usuário interno a um ou mais canais externos (WhatsApp, Telegram).
-- Permite que o mesmo usuário seja contatado por múltiplos canais.
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_channel (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES "user"(id),       -- Usuário interno proprietário do canal
    channel          TEXT NOT NULL,                                -- Canal de comunicação: whatsapp | telegram
    external_user_id TEXT NOT NULL,                                -- Identificador do usuário no canal externo (ex.: número WhatsApp, ID Telegram)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (channel, external_user_id)
);

-- ============================================================================
-- Categorias podem ser globais (user_id IS NULL) ou pessoais (user_id NOT NULL).
-- Categorias globais são inseridas pela migration e compartilhadas entre todos
-- os usuários. Categorias pessoais são criadas pelo próprio usuário e visíveis
-- apenas para ele.
-- Um mesmo normalized_name não pode existir duplicado no escopo global nem no
-- escopo de um mesmo usuário.
-- ============================================================================

CREATE TABLE IF NOT EXISTS category (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES "user"(id),                 -- NULL = categoria global/compartilhada; NOT NULL = categoria pessoal do usuário
    name            TEXT NOT NULL,                                 -- Nome original informado pelo usuário ou nome fixo da categoria padrão
    normalized_name TEXT NOT NULL,                                 -- Nome normalizado para deduplicação (lowercase, trim, sem acentos)
    description     TEXT,                                          -- Descrição auxiliar
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,                -- Se é uma categoria inserida pela migration (ex.: "Alimentação", "Transporte")
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,                 -- Se está ativa para uso em novos gastos
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Garante que não haja categorias globais duplicadas (ex.: duas "Alimentação")
CREATE UNIQUE INDEX uq_category_global
    ON category (normalized_name) WHERE user_id IS NULL;

-- Garante que um usuário não crie a mesma categoria duas vezes
CREATE UNIQUE INDEX uq_category_per_user
    ON category (user_id, normalized_name) WHERE user_id IS NOT NULL;

-- ============================================================================
-- Gastos fixos (despesas recorrentes). Representam uma regra de recorrência
-- mensal — o lançamento do gasto realizado pode ser gerado automaticamente no
-- dia configurado.
-- ============================================================================

CREATE TABLE IF NOT EXISTS recurring_expense (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES "user"(id),       -- Usuário proprietário do gasto fixo
    category_id     UUID NOT NULL REFERENCES category(id),     -- Categoria associada ao gasto fixo
    description     TEXT NOT NULL,                                -- Descrição do gasto fixo (ex.: "Internet", "Netflix")
    amount          NUMERIC(12,2) NOT NULL CHECK (amount > 0),                       -- Valor mensal esperado (sempre decimal, nunca float)
    payment_method  TEXT CHECK(payment_method IN ('pix', 'credit_card', 'debit_card', 'cash', 'not_informed')),                                         -- Meio de pagamento padrão: pix | credit_card | debit_card | cash | not_informed
    recurrence_day  INTEGER NOT NULL CHECK (recurrence_day BETWEEN 1 AND 31),                             -- Dia do mês em que o gasto ocorre (1 a 31)
    starts_at       DATE NOT NULL DEFAULT CURRENT_DATE,          -- Data de início da recorrência
    ends_at         DATE,                                         -- Data de término da recorrência (NULL = sem data fim)
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,               -- Se o gasto fixo está ativo (FALSE = cancelado/desativado)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Gastos realizados. Cada registro representa um gasto efetivo do usuário.
-- O valor é armazenado como NUMERIC (decimal fixo) — nunca float binário.
-- Correções são feitas via UPDATE in-place; o histórico de alterações fica
-- na tabela expense_audit_log.
-- ============================================================================

CREATE TABLE IF NOT EXISTS expense (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES "user"(id),           -- Usuário proprietário do gasto
    category_id          UUID NOT NULL REFERENCES category(id),         -- Categoria do gasto (obrigatória)
    source_message_id    UUID REFERENCES message_queue(id),              -- Referência à mensagem de origem (tabela message_queue em 001)
    recurring_expense_id UUID REFERENCES recurring_expense(id),         -- Gasto fixo de origem, se gerado automaticamente
    amount               NUMERIC(12,2) NOT NULL CHECK (amount > 0),                           -- Valor do gasto (precisão decimal, nunca float)
    description          TEXT NOT NULL,                                    -- Descrição normalizada (ex.: "Almoço", "Gasolina")
    original_description TEXT,                                             -- Texto original do usuário antes da normalização (para auditoria)
    payment_method       TEXT CHECK(payment_method IN ('pix', 'credit_card', 'debit_card', 'cash', 'not_informed')),                                             -- Meio de pagamento: pix | credit_card | debit_card | cash | not_informed
    occurred_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),                             -- Data e hora em que o gasto ocorreu (padrão: timestamp da mensagem)
    confidence           NUMERIC(5,4) DEFAULT NULL CHECK (confidence BETWEEN 0 AND 1),                       -- Nível de confiança da extração pelo LLM (0.0000 a 1.0000)
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Auditoria de alterações em gastos. Cada UPDATE ou correção gera um registro
-- com o estado anterior (before_data) e o novo estado (after_data).
-- ============================================================================

CREATE TABLE IF NOT EXISTS expense_audit_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    expense_id        UUID NOT NULL REFERENCES expense(id),     -- Gasto que foi alterado
    user_id           UUID NOT NULL REFERENCES "user"(id),      -- Usuário proprietário do gasto (desnormalizado para queries rápidas)
    action            TEXT NOT NULL CHECK (action IN ('created', 'updated',  'corrected')),                               -- Tipo da ação: created | updated | corrected
    before_data       JSONB,                                       -- Estado do gasto antes da alteração (NULL na criação)
    after_data        JSONB NOT NULL,                              -- Estado do gasto após a alteração
    source_message_id UUID REFERENCES message_queue(id),             -- Mensagem que originou esta ação (tabela message_queue em 001)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Rastreamento de custo de cada chamada a modelo de linguagem (OpenRouter).
-- Vinculado à mensagem que disparou o processamento.
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_usage (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES "user"(id),             -- Usuario proprietario do registro de custo
    message_id    UUID NOT NULL REFERENCES message_queue(id),      -- Referência à mensagem processada (tabela message_queue em 001)
    provider      TEXT NOT NULL,                                   -- Provedor do modelo (ex.: openai, anthropic, google)
    model         TEXT NOT NULL,                                   -- Nome do modelo utilizado (ex.: gpt-4o-mini, claude-3-haiku)
    input_tokens  INTEGER NOT NULL,                               -- Quantidade de tokens de entrada consumidos
    output_tokens INTEGER NOT NULL,                               -- Quantidade de tokens de saída gerados
    cost          NUMERIC(10,6) NOT NULL,                         -- Custo estimado da chamada em USD
    latency_ms    INTEGER NOT NULL,                               -- Latência da chamada ao modelo em milissegundos
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Adiciona user_id à fila de mensagens e conversas da migration 001 para
-- permitir particionamento por usuário (RF-022) e isolamento (RNF-004).
-- ============================================================================

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES "user"(id);

ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_user
        FOREIGN KEY (user_id) REFERENCES "user"(id);
