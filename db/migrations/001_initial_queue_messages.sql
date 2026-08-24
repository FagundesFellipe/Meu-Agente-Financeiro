-- Extensões
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Controle de migrações
CREATE TABLE IF NOT EXISTS migrations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fila de mensagens para procesamento assíncrono
CREATE TABLE IF NOT EXISTS message_queue(
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id                TEXT,
    phone_number              TEXT NOT NULL,
    to_number                 TEXT,                           -- Número destinatário (opcional)
    channel                   TEXT NOT NULL CHECK (channel IN ('telegram', 'whatsapp')), -- Canal de origem
    agent_id                  TEXT NOT NULL,                  -- Agente que vai processar
    thread_id                 TEXT NOT NULL,                  -- ID do thread: phone:agent_id
    incoming_message          TEXT NOT NULL,                  -- Texto da mensagem (pode ser concatenado via debounce)
    media_url                 TEXT,                           -- URL de mídia anexada
    media_type                TEXT,                           -- MIME type da mídia
    status                    TEXT NOT NULL DEFAULT 'queued', -- queued | processing | done | failed
    process_after             TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Debounce: só processar após este timestamp
    attempts                  INTEGER NOT NULL DEFAULT 0,     -- Tentativas de processamento
    max_attempts              INTEGER NOT NULL DEFAULT 3,     -- Máximo de tentativas
    lease_until               TIMESTAMPTZ,                    -- Lock: worker tem até este momento para processar
    response                  TEXT,                           -- Resposta do agente (preenchida no done)
    error                     TEXT,                           -- Erro (preenchido no failed)
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at              TIMESTAMPTZ,                     -- Quando foi processada
    normalized_input          TEXT,
    media_processing_status   TEXT,
    media_processing_error    TEXT
);


-- Busca mensagens prontas para processar, ordenadas por criação.
CREATE INDEX idx_queue_polling
    ON message_queue (process_after, created_at)
    WHERE status = 'queued';

-- Índice para buscar mensagens de um telefone+agente+canal (debounce e admin)
CREATE INDEX idx_queue_phone_agent
    ON message_queue (phone_number, agent_id, channel, status);

-- Índice para ordenação cronológica (admin)
CREATE INDEX idx_queue_created
    ON message_queue (created_at DESC);    

-- Tabela de conversas: agrega dados de cada par telefone+agente.
CREATE TABLE conversations (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID,                                       -- Usuário proprietário (opcional até o onboarding)
    phone_number      TEXT NOT NULL,
    agent_id          TEXT NOT NULL,
    thread_id         TEXT NOT NULL,
    last_message      TEXT NOT NULL,
    last_message_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_count     INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Sem usuário associado, cada canal/telefone possui apenas uma conversa por
-- agente. Quando houver usuário, a conversa passa a ser isolada também por ele.
CREATE UNIQUE INDEX uq_conversations_anonymous_phone_agent
    ON conversations (phone_number, agent_id)
    WHERE user_id IS NULL;

CREATE UNIQUE INDEX uq_conversations_user_phone_agent
    ON conversations (user_id, phone_number, agent_id)
    WHERE user_id IS NOT NULL;
