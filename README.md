# 💸 Meu Assistente Financeiro

> Um assistente financeiro conversacional para registrar e consultar gastos com a mesma naturalidade de uma conversa no WhatsApp ou no Telegram.

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Orquestra%C3%A7%C3%A3o-1C3C3C)

## ✨ Por que este projeto existe?

Controlar gastos costuma falhar não por falta de vontade, mas por **atrito**: abrir uma planilha ou aplicativo, preencher valor, categoria, data e meio de pagamento para cada compra. Com o tempo, esse ritual é abandonado e sobra apenas a visão do total no banco ou na fatura.

Este projeto existe para tornar o registro financeiro pessoal **mais fácil do que não registrar**. A pessoa só descreve o que aconteceu — por texto ou áudio — e o agente transforma a conversa em dados estruturados, confirmando o que foi salvo e respondendo perguntas sobre os próprios gastos.

O objetivo do MVP é que a pessoa consiga registrar ao menos 85% dos gastos durante 30 dias, sem precisar aprender comandos, formulários ou nomes internos de categorias.

## 🎯 O que o agente faz hoje

| Capacidade | Como funciona | Exemplo de mensagem |
| --- | --- | --- |
| 📝 Registrar gastos | Extrai descrição, valor, data, categoria e meio de pagamento; valida e grava o gasto. | `Gastei 35 reais no almoço` |
| ➕ Registrar vários gastos | Separa os itens de uma mesma mensagem e salva os que estão claros. | `Paguei 120 de internet e 45 de combustível` |
| ❓ Pedir esclarecimento | Mantém itens ambíguos como pendência em vez de gravar uma informação incerta. | `Gastei no mercado` → pergunta o valor |
| 📆 Lidar com parcelas | Expande uma compra parcelada em lançamentos mensais, com valores em centavos calculados de forma determinística. | `Comprei uma cadeira de 600 em 3x` |
| 🔁 Cadastrar gastos fixos | Cria regras mensais, como assinaturas e contas recorrentes. | `Netflix, 55 reais, todo dia 10` |
| 📊 Consultar gastos | Consulta totais, listas, categorias, comparações e gastos fixos no PostgreSQL. | `Quanto gastei com alimentação esta semana?` |
| 🎙️ Processar áudio | Baixa o áudio do canal, transcreve-o e usa a transcrição como mensagem do agente. | áudio: “gastei vinte reais no café” |

Exemplos de perguntas que a camada de relatórios suporta:

- `Quanto gastei hoje?`
- `Mostre meus últimos gastos deste mês.`
- `Qual categoria consumiu mais dinheiro no mês passado?`
- `Quanto gastei no cartão de crédito esta semana?`
- `Compare esta semana com a semana passada.`
- `Quais gastos fixos eu tenho cadastrados?`

### 🛡️ Como o agente protege a qualidade dos dados

O modelo de linguagem interpreta o texto, mas **não calcula totais nem escreve SQL livremente**. O Python e o PostgreSQL validam valores com `Decimal`, resolvem datas e categorias, calculam agregações e aplicam filtros por usuário. A fila também evita duplicações e preserva a ordem de processamento de cada conversa.

Quando uma mensagem traz itens claros e outro incompleto, o agente salva os claros e pergunta somente pelo que falta. Por exemplo, em `paguei 40 no almoço e comprei roupa`, o almoço pode ser confirmado e a roupa fica pendente de valor.

### 🚧 Limites atuais

- Criação, edição e exclusão de categorias pelo chat ainda não estão disponíveis.
- Correção de gastos pelo chat ainda não está disponível na implementação atual.
- Imagens, documentos e vídeos recebidos são recusados; o suporte de mídia atual é para **áudio**.
- Não há integração bancária, leitura de extrato/fatura, orçamento, investimentos ou interface web de finanças neste MVP.

## 🧭 Visão da arquitetura

```text
WhatsApp (Twilio) ou Telegram
            │
            ▼
     FastAPI recebe o webhook
     e valida sua autenticidade
            │
            ▼
  PostgreSQL: fila de mensagens
            │
            ▼
 Worker: processa uma conversa por vez
            │
            ▼
 LangGraph + OpenRouter
            │
            ▼
 PostgreSQL: gastos, categorias,
 recorrências, auditoria e estado
            │
            ▼
 Resposta enviada ao canal
```

O webhook responde rapidamente ao provedor; o trabalho mais lento acontece no worker. Isso evita que uma chamada do Telegram ou Twilio fique esperando a IA terminar.

## 🧱 Stack

| Camada | Tecnologias | Papel |
| --- | --- | --- |
| Linguagem e pacotes | Python 3.13, [uv](https://docs.astral.sh/uv/) | Ambiente e dependências |
| API | FastAPI, Uvicorn | Health check e webhooks |
| Orquestração | LangGraph, LangChain | Roteamento de intenções e memória da conversa |
| IA | OpenRouter, modelos compatíveis com OpenAI | Extração estruturada, relatórios e transcrição |
| Dados e fila | PostgreSQL 16, pgvector, psycopg | Dados financeiros, fila, locks e checkpoints |
| Canais | Telegram Bot API, Twilio WhatsApp | Entrada e saída de mensagens |
| Qualidade | Pytest, Ruff, Pyright | Testes, lint, formatação e tipos |
| Infraestrutura | Docker Compose, Docker | PostgreSQL local e execução em containers |

## ✅ Pré-requisitos

Antes de começar, instale:

- [Git](https://git-scm.com/downloads)
- [Python 3.13](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ou Docker Engine com o plugin Compose
- Uma conta no [OpenRouter](https://openrouter.ai/) com uma chave de API

Para receber mensagens reais, você também precisará de:

- Um bot do Telegram criado no BotFather; e/ou
- Uma conta Twilio com acesso ao WhatsApp Sandbox para testes;
- Uma URL pública HTTPS. Em desenvolvimento local, um túnel como Cloudflare Tunnel ou ngrok resolve essa necessidade.

> 🔐 Nunca envie o arquivo `.env`, tokens ou chaves para o Git. Use valores reais somente no seu ambiente local ou no gerenciador de segredos da infraestrutura.

## 🚀 Subir o projeto localmente

### 1. Clonar o repositório

```bash
git clone <URL_DO_SEU_REPOSITORIO>
cd "MEU ASSISTENTE FINANCEIRO"
```

### 2. Criar o arquivo de ambiente

Copie o modelo:

```bash
cp .env.example .env
```

Abra `.env` e use, no mínimo, esta configuração inicial. Os nomes do banco abaixo são intencionalmente iguais: eles evitam uma inconsistência entre o valor demonstrativo do `.env.example` e o Compose atual.

```dotenv
# Ambiente e banco
ENVIRONMENT=development
POSTGRES_DB=assistente_financeiro
POSTGRES_USER=postgres
POSTGRES_PASSWORD=troque-por-uma-senha-local-segura
DATABASE_URL=postgresql://postgres:troque-por-uma-senha-local-segura@localhost:5433/assistente_financeiro

# IA
OPENROUTER_API_KEY=sk-or-v1-sua-chave-aqui
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=google/gemini-2.5-flash-lite
OPENROUTER_MIDIA_MODEL=google/gemini-2.5-flash-lite

# Telegram — preencha ao configurar o canal
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_SECRET_TOKEN=

# WhatsApp/Twilio — comece em mock até configurar o Sandbox
TWILIO_OUTBOUND_MODE=mock
TWILIO_ACCOUNT_SID=
TWILIO_API_KEY_SID=
TWILIO_API_KEY_SECRET=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_WEBHOOK_URL=
```

> 💡 `TWILIO_AUTH_TOKEN` é usado para validar chamadas recebidas da Twilio. Já `TWILIO_API_KEY_SID` e `TWILIO_API_KEY_SECRET` são usados para enviar respostas. São credenciais com papéis diferentes.

### 3. Instalar as dependências Python

```bash
make setup
```

### 4. Iniciar o PostgreSQL

```bash
docker compose up -d db
docker compose ps
```

O banco fica exposto apenas em `127.0.0.1:5433`; a aplicação local usa esse endereço por meio de `DATABASE_URL`.

### 5. Aplicar as migrações e iniciar API + worker

Abra **dois terminais**, ambos na raiz do repositório.

No primeiro, execute a API. Na primeira inicialização ela também aplica migrações, sincroniza categorias globais e prepara os checkpoints do LangGraph:

```bash
make api
```

No segundo, execute o worker, responsável por consumir e responder mensagens:

```bash
make worker
```

Valide a API em um terceiro terminal:

```bash
curl http://localhost:8000/health
```

O resultado esperado é um JSON com `"status": "ok"`. Mantenha API e worker rodando para que o agente possa receber e responder mensagens.

## 🤖 Configurar e usar o Telegram

O Telegram é o caminho mais simples para validar o agente em desenvolvimento.

### 1. Criar o bot e os segredos

1. No Telegram, abra **@BotFather** e execute `/newbot`.
2. Escolha o nome e o `username` do bot.
3. Copie o token entregue pelo BotFather para `TELEGRAM_BOT_TOKEN` no `.env`.
4. Gere um segredo aleatório para validar os webhooks e salve-o em `TELEGRAM_WEBHOOK_SECRET_TOKEN`.

Exemplo para gerar o segredo:

```bash
openssl rand -hex 32
```

### 2. Expor a API local em HTTPS

O Telegram precisa alcançar a sua API por uma URL HTTPS pública. Com Cloudflare Tunnel, por exemplo:

```bash
cloudflared tunnel --url http://localhost:8000
```

Copie a URL HTTPS retornada, como `https://exemplo.trycloudflare.com`. Deixe o túnel aberto enquanto testa.

### 3. Registrar o webhook do Telegram

Com a API, worker e túnel em execução, substitua os valores no comando abaixo. O identificador `financial_agent` pode ser mantido como está; ele identifica a conversa internamente.

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -F "url=https://exemplo.trycloudflare.com/webhook/telegram?agent=financial_agent" \
  -F "secret_token=<TELEGRAM_WEBHOOK_SECRET_TOKEN>"
```

O Telegram enviará o valor de `secret_token` no header que esta API exige. Confira a resposta da API do Telegram: ela deve informar `"ok": true`.

### 4. Testar

Abra a conversa com o seu bot e envie:

```text
Gastei 35 reais no almoço
```

Você deve receber uma confirmação semelhante a:

```text
Anotado: almoço — R$ 35.00 (Restaurantes).
```

Depois, teste uma consulta:

```text
Quanto gastei hoje?
```

Para conferir a configuração do Telegram, use a documentação oficial do método [`setWebhook`](https://core.telegram.org/bots/api#setwebhook).

## 📱 Configurar e usar o WhatsApp com Twilio

Use este fluxo para desenvolvimento e testes. O [Twilio Sandbox for WhatsApp](https://www.twilio.com/docs/whatsapp/sandbox) exige que cada número de teste entre no sandbox e tem limitações próprias.

### 1. Preparar o Sandbox

1. Crie ou acesse sua conta Twilio.
2. Abra a página **Messaging** -> **Try it out** -> **Send a WhatsApp Message** no Console legado e ative o Sandbox.
3. No WhatsApp do seu celular, envie `join <código-do-sandbox>` para o número mostrado pela Twilio, ou use o QR code da tela.
4. Copie para o `.env`:
   - `TWILIO_ACCOUNT_SID`;
   - `TWILIO_API_KEY_SID` e `TWILIO_API_KEY_SECRET` de uma API Key;
   - `TWILIO_AUTH_TOKEN` da conta;
   - `TWILIO_FROM_NUMBER`, normalmente no formato `whatsapp:+14155238886` no Sandbox.
5. Altere `TWILIO_OUTBOUND_MODE=real`.

### 2. Criar uma URL pública e ajustar a assinatura

Com a API local em execução, crie ou reutilize o túnel HTTPS:

```bash
cloudflared tunnel --url http://localhost:8000
```

Defina somente a **base** pública em `TWILIO_WEBHOOK_URL`, sem caminho ou parâmetros:

```dotenv
TWILIO_WEBHOOK_URL=https://exemplo.trycloudflare.com
```

Isso é essencial: a API reconstrói essa URL para validar a assinatura `X-Twilio-Signature` enviada pela Twilio. Sem `TWILIO_AUTH_TOKEN` e uma assinatura válida, ela rejeita a chamada por segurança.

### 3. Configurar o webhook no Console Twilio

Em **Sandbox settings → Sandbox configuration**, preencha **When a Message Comes in** com o método **POST** e a URL:

```text
https://exemplo.trycloudflare.com/webhook/twilio?agent=financial_agent
```

Reinicie o worker depois de atualizar o `.env`:

```bash
make worker
```

### 4. Testar

No WhatsApp que entrou no Sandbox, envie para o número do Sandbox:

```text
Paguei 120 de internet e 45 de combustível
```

O agente deve responder com os lançamentos confirmados. Dentro da janela de atendimento iniciada pela mensagem do usuário, a Twilio permite respostas livres; fora dela, o WhatsApp exige templates aprovados para mensagens iniciadas pela empresa. Consulte a [documentação oficial da Twilio](https://www.twilio.com/docs/whatsapp/api#conversational-messaging-on-whatsapp) para as regras vigentes.

## 🐳 Executar API, worker e banco com Docker

O Compose reúne os três serviços:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api worker
```

Antes disso, confirme que `.env` possui `POSTGRES_DB=assistente_financeiro` e as credenciais necessárias. O Compose não publica a porta da API no host; ele foi preparado para ser atendido por um proxy reverso HTTPS, como Traefik. Para o primeiro teste local com Telegram ou Twilio, o fluxo com `make api`, `make worker` e um túnel é o mais direto.

## 🔍 Comandos úteis

| Comando | O que faz |
| --- | --- |
| `make setup` | Cria o ambiente virtual e instala dependências |
| `docker compose up -d db` | Inicia apenas o PostgreSQL local |
| `make migrations` | Aplica migrações pendentes |
| `make api` | Sobe a FastAPI em `http://localhost:8000` |
| `make worker` | Inicia o consumidor da fila |
| `make graph` | Imprime a representação Mermaid do grafo LangGraph |
| `make test` | Executa a suíte de testes |
| `make check` | Executa Ruff e Pyright sem alterar arquivos |
| `make prompt-manager-serve` | Inicia o gerenciador local de prompts na porta 5000 |

Caso o `uv` não consiga usar o cache padrão por permissão, defina um diretório gravável antes dos comandos:

```bash
export UV_CACHE_DIR=/tmp/meu-assistente-financeiro-uv-cache
```

## 🔐 Boas práticas de segurança

- Use senhas fortes fora do desenvolvimento local.
- Mantenha `TELEGRAM_WEBHOOK_SECRET_TOKEN`, `TWILIO_AUTH_TOKEN`, chaves Twilio e OpenRouter apenas no ambiente de execução.
- Use sempre HTTPS nos webhooks públicos.
- Não desligue a validação de assinatura da Twilio nem deixe o token secreto do Telegram vazio: os endpoints falham fechados quando essas credenciais não existem.
- Em produção, substitua o Sandbox da Twilio por um remetente WhatsApp aprovado e configure uma URL pública estável.

## 🧪 Desenvolvimento e qualidade

As migrações ficam em [`db/migrations`](db/migrations), e os testes que precisam de PostgreSQL são marcados como `db`. Para executar somente eles com o banco disponível:

```bash
uv run pytest -m db
```

Os prompts do agente são versionados em `src/financial_agent/agent/prompts/metadata.json`; não os fixe diretamente no código Python. O Prompt Manager permite administrar versões localmente.

## 📁 Estrutura do projeto

```text
src/
├── financial_agent/
│   ├── agent/        # Grafo LangGraph, agentes, regras e prompts
│   ├── server/       # FastAPI, health check e webhooks
│   └── worker/       # Consumo da fila, mídia e clientes dos canais
├── shared/           # Configuração, banco, fila e repositórios
└── prompts_manager/  # Interface de versionamento de prompts
db/
├── migrations/       # Esquema e evolução do PostgreSQL
└── migrate.py        # Aplicador de migrações
tests/                # Testes unitários, de integração e evals
```

## 🤝 Contribuição

Antes de abrir uma mudança, leia [`dev-workflow.md`](dev-workflow.md), mantenha o escopo pequeno e execute as verificações adequadas. Não inclua segredos nem alterações não relacionadas no mesmo commit.

---

Feito para reduzir o atrito entre **gastar**, **registrar** e **entender** para onde o dinheiro foi. ✨
