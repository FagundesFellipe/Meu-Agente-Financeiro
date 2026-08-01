# Prompts Manager

Interface web para gerenciamento de prompts LLM com versionamento semântico e armazenamento baseado em arquivos JSON.

## Visão Geral

O **Prompts Manager** é uma ferramenta de desenvolvimento local que fornece uma interface web (Flask) para criar, versionar, ativar e descontinuar prompts utilizados pelo assistente financeiro. Cada prompt é armazenado como um arquivo JSON versionado em um diretório dedicado, com um arquivo `metadata.json` central que rastreia qual versão está ativa para cada prompt.

**Canal:** Web (localhost)  
**Propósito:** Gerenciamento de prompts do agente LangGraph (MVP)  
**Usuário-alvo:** Desenvolvedores do assistente financeiro

## Estrutura do Módulo

```
src/prompts_manager/
├── config.py                          # Configuração centralizada via pydantic-settings
├── pyproject.toml                     # Dependências do módulo
├── README.md                          # Este arquivo
└── src/
    ├── __init__.py
    ├── main.py                        # Ponto de entrada (servidor Flask)
    ├── prompt_strore.py               # Camada de persistência (file-based JSON store)
    ├── versioning.py                  # Utilitários de versionamento semântico
    └── frontend/
        ├── __init__.py
        ├── app.py                     # Aplicação Flask (rotas, CSRF, validação)
        └── templates/
            ├── base.html              # Layout base com Tailwind CSS
            ├── index.html             # Página inicial — lista de prompts + formulário de criação
            └── prompt_detail.html     # Detalhes do prompt — histórico de versões + ações
```

## Arquitetura

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────────┐
│   Browser    │────▶│  Flask (app.py)  │────▶│  prompt_strore.py    │
│  (localhost) │◀────│  Rotas + CSRF    │◀────│  CRUD + versionamento│
└──────────────┘     └────────┬────────┘     └──────────┬───────────┘
                              │                         │
                              │    ┌──────────────┐     │
                              └───▶│  config.py   │     │
                                   │  (Settings)  │     │
                                   └──────┬───────┘     │
                                          │             │
                                   ┌──────┴───────┐     │
                                   │   .env file  │     │
                                   └──────────────┘     │
                                                         │
                              ┌──────────────────────────┴───┐
                              │  File System                 │
                              │  PROMPT_DIR/                 │
                              │  ├── metadata.json           │
                              │  ├── saudacao/               │
                              │  │   ├── v1.0.0.json         │
                              │  │   └── v1.0.1.json         │
                              │  └── classificador/          │
                              │      └── v1.0.0.json         │
                              └──────────────────────────────┘
```

### Separação de Responsabilidades

| Módulo | Responsabilidade |
|--------|-----------------|
| `config.py` | Configuração centralizada via variáveis de ambiente (pydantic-settings). Única fonte de verdade para portas, diretórios, chaves e flags. |
| `versioning.py` | Parsing, formatação e bump de versões semânticas (`v1.2.3`). Sem dependências externas. |
| `prompt_strore.py` | CRUD de prompts e versões. Operações de leitura/escrita em JSON com locking (`fcntl`) para segurança em concorrência. Sanitização de nomes contra path traversal. |
| `app.py` | Camada web — rotas Flask, validação de formulários, proteção CSRF, flash messages. NÃO contém lógica de negócio. |
| `main.py` | Bootstrap do servidor. Valida diretório de prompts, imprime diagnóstico, inicia Flask. |

## Dependências

```toml
# pyproject.toml
dependencies = [
    "flask>=3.0",            # Framework web
    "flask-wtf>=1.2",        # Proteção CSRF
    "pydantic-settings>=2.0", # Configuração tipada via .env
]
```

Instalar: `uv pip install -e "src/prompts_manager"`

## Configuração

Toda a configuração é gerenciada por `config.py` usando `pydantic_settings.BaseSettings`, que lê do arquivo `.env` e de variáveis de ambiente.

### Variáveis de Ambiente

| Variável | Tipo | Padrão | Descrição |
|----------|------|--------|-----------|
| `PROMPT_DIR` | `str` | `/src/financial_agent/agent/prompts` | Diretório raiz onde os prompts são armazenados |
| `PROMPT_MANAGER_PORT` | `int` | `5000` | Porta do servidor web |
| `FLASK_SECRET_KEY` | `str` | `prompt-manager-dev-key` | Chave de sessão Flask (***substituir em produção***) |
| `FLASK_DEBUG` | `bool` | `False` | Modo debug do Flask (console interativo) |

### Exemplo `.env`

```env
PROMPT_DIR=/caminho/para/prompts
PROMPT_MANAGER_PORT=5000
FLASK_SECRET_KEY=seu-segredo-aqui
FLASK_DEBUG=false
```

## Execução

```bash
# Iniciar o servidor
python -m src.prompts_manager.src.main

# Ou com debug ativado (desenvolvimento)
FLASK_DEBUG=true python -m src.prompts_manager.src.main
```

O servidor inicia em `http://127.0.0.1:5000` (bind local apenas).

## Rotas da Interface

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/` | Página inicial — lista de prompts cadastrados |
| `POST` | `/` | Criar novo prompt com versão inicial |
| `GET` | `/prompts/<name>` | Detalhes do prompt — histórico completo de versões |
| `POST` | `/prompts/<name>/versions` | Criar nova versão de um prompt existente |
| `POST` | `/prompts/<name>/versions/<version>/activate` | Ativar uma versão específica (deprecia a anterior) |
| `POST` | `/prompts/<name>/versions/<version>/deprecate` | Marcar versão como obsoleta (não pode ser a ativa) |

## Modelo de Dados

### Estrutura do Prompt (arquivo JSON por versão)

```json
{
  "prompt_name": "classificador_intencao",
  "prompt_version": "v1.2.0",
  "prompt_content": "Você é um classificador de intenções financeiras...",
  "llm_model": "gpt-4o-mini",
  "llm_temperature": 0.3,
  "llm_reasoning_effort": null,
  "owner": "usuario_feliz",
  "change_note": "Adicionada classificação de recorrência",
  "created_at": "2025-01-15T10:30:00+00:00",
  "status": "active"
}
```

### Estados de Versão

| Estado | Significado |
|--------|------------|
| `active` | Versão atualmente em uso pelo agente |
| `deprecated` | Versão substituída por uma mais recente |
| (sem status) | Versão criada mas nunca ativada |

### metadata.json

```json
{
  "active_versions": {
    "classificador_intencao": "v1.2.0",
    "saudacao": "v1.0.1"
  }
}
```

## Versionamento Semântico

O módulo `versioning.py` implementa versionamento semântico (`vMAJOR.MINOR.PATCH`):

| Incremento | Quando usar |
|------------|------------|
| `patch` | Correções de texto, ajustes de formatação, correções gramaticais |
| `minor` | Novas instruções, parâmetros adicionais, melhorias sem quebra |
| `major` | Reestruturação completa do prompt, mudança de comportamento fundamental |

A primeira versão de um prompt é sempre `v1.0.0`.

## Segurança

### Medidas Implementadas

| Camada | Proteção |
|--------|----------|
| **Path Traversal** | `get_prompt_dir()` valida nomes contra regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$` e verifica `resolve()` contra o diretório base |
| **CSRF** | `flask-wtf` CSRFProtect em todos os formulários POST com token por requisição |
| **Secret Key** | Configurável via `FLASK_SECRET_KEY` |
| **Debug Mode** | Controlado por `FLASK_DEBUG` (default: `False`) |
| **Race Condition** | `save_metadata()` usa `fcntl.flock(LOCK_EX)` para escrita atômica com lock exclusivo |
| **Tamanho de Conteúdo** | Limite de 100 KB (`MAX_PROMPT_SIZE`) por conteúdo de prompt, validado em bytes UTF-8 |
| **Bind Restrito** | Servidor escuta apenas em `127.0.0.1` — sem exposição à rede |
| **Validação de Input** | `maxlength` nos inputs HTML + validação regex no servidor para `prompt_name` |

### Avisos de Segurança

- ⚠️ O valor padrão de `FLASK_SECRET_KEY` (`prompt-manager-dev-key`) é inseguro. **Sempre defina uma chave forte via `.env` ou variável de ambiente.**
- ⚠️ Esta ferramenta é projetada para uso em **desenvolvimento local**. Não exponha na rede sem autenticação adicional.
- ⚠️ O diretório de prompts (`PROMPT_DIR`) deve ter permissões de arquivo restritas ao usuário desenvolvedor.

## Desenvolvimento

### Executar Testes Manuais

```bash
# 1. Iniciar servidor
FLASK_DEBUG=true python -m src.prompts_manager.src.main

# 2. Acessar http://127.0.0.1:5000 no navegador

# 3. Verificar CSRF ativo
curl -X POST http://127.0.0.1:5000/ \
  -d "prompt_name=test&prompt_content=test&model=gpt4&owner=dev&change_note=test"
# Deve retornar: 400 Bad Request — "The CSRF token is missing."

# 4. Verificar path traversal bloqueado
curl -X POST http://127.0.0.1:5000/ \
  -d "prompt_name=../../../etc/passwd&prompt_content=test&model=gpt4&owner=dev&change_note=test"
# Deve retornar: flash message de erro via formulário web
```

## Licença

Projeto interno — parte do MEU ASSISTENTE FINANCEIRO.
