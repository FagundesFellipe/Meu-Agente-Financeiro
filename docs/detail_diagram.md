flowchart TD
    A["📨 Mensagem do usuário<br/>(WhatsApp / Telegram)"] --> B["🌐 FastAPI Webhook"]
    B --> C["💾 Persiste mensagem em<br/>message_queue (Postgres)"]
    C --> D["📬 Worker (FOR UPDATE SKIP LOCKED)"]
    D --> E["🧠 LangGraph: build_graph_workflow.py"]

    E --> F["🔀 llm_call_router<br/><b>LLM (OpenRouter)</b><br/>Classifica intenção com<br/>ROUTER_SYSTEM_PROMPT"]
    F --> G{"route_decision()<br/>Qual intenção?"}

    G -->|"add_new_expenses"| H["📝 add_new_expenses_agent"]
    G -->|"greeting"| I["👋 greeting_agent<br/><i>responde saudação</i>"]
    G -->|"report / categories / undefined"| J["🚧 Placeholder<br/>'em construção'"]
    I --> END_NODE[END]
    J --> END_NODE

    H --> H1["🔍 resolve_user(channel, phone_number)<br/>Tenta user_channel → fallback phone"]
    H1 --> H2{"Usuário<br/>encontrado?"}
    H2 -->|"❌ Não"| H2a["❌ response_text: 'Não encontrei<br/>seu cadastro...'"]
    H2a --> END_NODE
    H2 -->|"✅ Sim"| H3["📋 list_available_categories(user.id)<br/>Busca categorias do banco"]

    H3 --> H4["🕐 user_now(user.timezone)<br/>Obtém data/hora no fuso do usuário"]
    H4 --> H5["📐 build_context_message(now, categories)<br/>Monta SystemMessage com:<br/>• DATA_HORA_ATUAL<br/>• CATEGORIAS_DISPONIVEIS"]

    H5 --> H6["🤖 _extract(state, context)<br/><b>LLM (OpenRouter)</b><br/>ADD_EXPENSES_SYSTEM_PROMPT<br/>→ AddExpensesResult<br/>(ToolStrategy / structured output)"]

    H6 --> H7["🔧 resolve_extracted_expenses()<br/><b>PÓS-PROCESSAMENTO PYTHON</b>"]
    H7 --> H7a["Para cada ExtractedExpense:"]
    H7a --> H7b["1️⃣ parse_amount(amount_raw) → Decimal"]
    H7b --> H7c["2️⃣ resolve_occurred_at(date_hint, time_hint, tz) → datetime"]
    H7c --> H7d["3️⃣ resolve_category(hint, categories) → CategoryRecord"]
    H7d --> H7e["❌ Erro em algum? → problems[] (pergunta ao usuário)"]
    H7e --> H7f["✅ Sucesso? → ExpenseDetails (frozen)"]
    H7f --> H7g["4️⃣ normalize_payment_method(hint) → PaymentMethod"]
    H7g --> H7h["5️⃣ installments > 1? → _expand_installments()<br/>(cria N registros, datas mensais, (1/N))"]

    H7h --> H8{"outcome.expenses<br/>tem itens?"}
    H8 -->|"✅ Sim"| H9["💿 insert_expenses(user_id, expenses, source_message_id)"]
    H8 -->|"❌ Não"| H10["⏭️ Pula persistência"]

    H9 --> H9a["🔒 pg_advisory_xact_lock(message_id)"]
    H9a --> H9b{"Já existe gasto<br/>dessa mensagem?"}
    H9b -->|"✅ Sim"| H9c["♻️ Retorna registros existentes<br/>(IDEMPOTÊNCIA)"]
    H9b -->|"❌ Não"| H9d["📝 INSERT INTO expense<br/>(um por registro)"]
    H9d --> H9e["📋 INSERT INTO expense_audit_log<br/>(action='created')"]
    H9e --> H9c

    H9c --> H11["📊 Monta response_text"]

    H11 --> H11a{"Combinação de<br/>records + problems"}
    H11a -->|"✅ records + ⚠️ pending"| H11b["📝 Confirmação<br/>+ Perguntas pendentes"]
    H11a -->|"✅ só records"| H11c["📝 format_confirmation()<br/>'Anotado: ... — R$ XX.XX'"]
    H11a -->|"⚠️ só pending"| H11d["❓ Perguntas ao usuário"]
    H11a -->|"❌ nenhum"| H11e["❓ 'Não consegui identificar<br/>nenhum gasto...'"]

    H11b --> H12["📤 Retorna ao grafo:<br/>• response_text<br/>• expense_details<br/>• user_id/name/timezone<br/>• extracted_expenses"]
    H11c --> H12
    H11d --> H12
    H11e --> H12
    H10 --> H12
    H12 --> END_NODE

    style H7 fill:#e1f5fe
    style H9 fill:#c8e6c9
    style H6 fill:#fff9c4
    style F fill:#fff9c4