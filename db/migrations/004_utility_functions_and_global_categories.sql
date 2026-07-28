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

-- ----------------------------------------------------------------------------
-- 3. Categorias globais (user_id IS NULL) — visíveis para todos os usuários.
--    Cada categoria tem nome, nome normalizado (lowercase, sem acentos, trim)
--    e descrição com exemplos de uso.
-- ----------------------------------------------------------------------------
INSERT INTO category (name, normalized_name, description, is_default, is_active)
VALUES
    ('Alimentação',                'alimentacao',               'Supermercado, feira, padaria, restaurantes, cafés e delivery',                        TRUE, TRUE),
    ('Moradia',                    'moradia',                   'Aluguel, financiamento, condomínio, manutenção e reformas',                           TRUE, TRUE),
    ('Transporte',                 'transporte',                'Combustível, transporte público, aplicativos de corrida, estacionamento e manutenção do veículo', TRUE, TRUE),
    ('Contas e serviços essenciais', 'contas_e_servicos_essenciais', 'Energia, água, gás, telefone, internet e TV',                                      TRUE, TRUE),
    ('Saúde e bem-estar',          'saude_e_bem-estar',         'Plano de saúde, consultas, exames, farmácia, dentista e academia',                     TRUE, TRUE),
    ('Compras',                    'compras',                   'Roupas, eletrônicos, móveis, utensílios domésticos e comércio eletrônico',             TRUE, TRUE),
    ('Lazer e entretenimento',     'lazer_e_entretenimento',    'Cinema, eventos, jogos, hobbies, bares e serviços de streaming',                       TRUE, TRUE),
    ('Educação',                   'educacao',                  'Escola, faculdade, cursos, livros, mensalidades e materiais',                          TRUE, TRUE),
    ('Viagens',                    'viagens',                   'Passagens, hospedagem, turismo, aluguel de veículos e alimentação em viagem',           TRUE, TRUE),
    ('Dívidas e financiamentos',   'dividas_e_financiamentos',  'Empréstimos, financiamento de veículo, crédito pessoal e parcelamentos',               TRUE, TRUE),
    ('Poupança e investimentos',   'poupanca_e_investimentos',  'Reserva de emergência, previdência, renda fixa, fundos e ações',                       TRUE, TRUE),
    ('Seguros',                    'seguros',                   'Seguro residencial, automóvel, vida, viagem e saúde',                                   TRUE, TRUE),
    ('Cuidados pessoais',          'cuidados pessoais',         'Cabeleireiro, cosméticos, estética, higiene e vestuário pessoal',                       TRUE, TRUE),
    ('Impostos, taxas e tarifas',  'impostos, taxas e tarifas', 'IPTU, IPVA, Imposto de Renda, tarifas bancárias, juros e multas',                      TRUE, TRUE),
    ('Família e filhos',           'familia e filhos',          'Creche, babá, atividades infantis, mesada e despesas com dependentes',                  TRUE, TRUE)
ON CONFLICT (normalized_name) WHERE user_id IS NULL DO NOTHING;
