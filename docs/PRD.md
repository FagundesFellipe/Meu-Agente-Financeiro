# PRD — Assistente Inteligente de Gestão de Gastos

## 1. Informações do produto

| Campo                             | Definição                                  |
| --------------------------------- | ------------------------------------------ |
| Produto                           | Assistente Inteligente de Gestão de Gastos |
| Fase                              | MVP                                        |
| Canal principal                   | WhatsApp                                   |
| Canal de desenvolvimento e testes | Telegram                                   |
| Plataforma complementar           | Interface web prevista para a Fase 2       |
| Status                            | Planejamento                               |
| Responsável                       | A definir                                  |
| Data                              | Julho de 2026                              |

---

## 2. Resumo executivo

O produto será um assistente financeiro conversacional capaz de registrar gastos, cadastrar despesas fixas, criar categorias e responder perguntas sobre os gastos do usuário por meio de mensagens de texto ou áudio.

A principal proposta de valor é reduzir ao mínimo o esforço necessário para manter o controle financeiro pessoal. Em vez de abrir aplicativos, preencher formulários, escolher categorias e selecionar datas, o usuário poderá simplesmente enviar mensagens como:

> “Gastei 35 reais no almoço.”

> “Paguei 120 de internet e 45 de combustível.”

> “Quanto gastei com comida esta semana?”

O assistente deverá interpretar a mensagem, estruturar os dados, registrar as informações corretas e confirmar a operação.

O MVP terá como prioridade a qualidade da interpretação, a confiança dos registros, o isolamento dos dados por usuário e uma arquitetura minimamente preparada para crescimento.

O registro de um novo gasto será considerado concluído quando:

1. O gasto estiver salvo no banco de dados.
2. A mensagem de confirmação tiver sido enviada ao usuário.

Esse fluxo deverá ocorrer em até 15 segundos.

---

## 3. Contexto e problema

O usuário possui disciplina financeira e estabelece limites mensais de gastos e valores destinados à economia. No entanto, não possui visibilidade detalhada sobre como o dinheiro é distribuído entre categorias como:

* Restaurantes;
* Bares;
* Roupas;
* Futebol;
* Supermercado;
* Combustível;
* Assinaturas;
* Outros gastos cotidianos.

Atualmente, a principal forma de acompanhamento é consultar o aplicativo bancário e observar o crescimento da fatura do cartão ou as movimentações via Pix.

Essa abordagem permite visualizar o total gasto, mas não responde facilmente perguntas como:

* Quanto foi gasto em restaurantes?
* Quanto foi gasto com roupas?
* Qual categoria consumiu mais dinheiro?
* Em qual semana do mês houve mais gastos?
* Quanto foi gasto no cartão em comparação com Pix?

Soluções como planilhas e aplicativos tradicionais apresentam uma barreira de esforço. O usuário precisa abrir o sistema, preencher campos, escolher categorias, selecionar datas e repetir esse processo para cada gasto.

Esse atrito faz com que o processo seja abandonado após poucos dias.

---

## 4. Visão do produto

Permitir que qualquer pessoa controle seus gastos pessoais por meio de uma conversa natural, sem precisar aprender a usar uma ferramenta financeira complexa.

O produto deverá funcionar como uma camada conversacional entre o usuário e seus dados financeiros.

A experiência ideal é:

1. O usuário informa um gasto naturalmente.
2. O assistente interpreta a mensagem.
3. O gasto é estruturado e armazenado.
4. O assistente confirma o registro.
5. O usuário pode consultar seus gastos fazendo perguntas em linguagem natural.

---

## 5. Objetivo do MVP

Desenvolver um assistente financeiro conversacional capaz de:

* Registrar gastos individuais;
* Registrar múltiplos gastos em uma única mensagem;
* Registrar gastos fixos mensais;
* Criar categorias;
* Consultar gastos por meio de perguntas previamente suportadas;
* Receber mensagens de texto e áudio;
* Operar prioritariamente pelo WhatsApp;
* Manter os dados isolados entre usuários;
* Processar mensagens com segurança mesmo em cenários de alto volume;
* Rastrear o custo de cada execução;
* Salvar e confirmar um novo gasto em até 15 segundos.

---

## 6. Critério principal de sucesso

O MVP será considerado bem-sucedido se o usuário:

> Utilizar o assistente durante 30 dias consecutivos e registrar pelo menos 85% dos gastos realizados, sem abandonar o processo.

A métrica deverá considerar a quantidade estimada de gastos realizados no período em comparação com os gastos efetivamente registrados no assistente.

Como o sistema não terá acesso automático às movimentações bancárias no MVP, a medição inicial poderá ser realizada por meio de:

* Autoavaliação do usuário;
* Comparação manual com fatura ou extrato ao final do período;
* Questionário de encerramento do teste;
* Verificação da frequência de uso ao longo dos 30 dias.

---

## 7. Metas do produto

### 7.1 Metas principais

* Tornar o registro de gastos mais simples do que abrir um aplicativo financeiro.
* Permitir o registro de um gasto por meio de uma única mensagem.
* Manter alto nível de confiança nos dados registrados.
* Reduzir confirmações desnecessárias.
* Responder às principais perguntas financeiras do usuário.
* Suportar usuários com diferentes níveis de familiaridade tecnológica.
* Construir uma base técnica preparada para múltiplos usuários.

### 7.2 Metas técnicas

* Registrar e confirmar um gasto em até 15 segundos.
* Responder às demais mensagens em até 25 segundos.
* Garantir isolamento lógico dos dados de cada usuário.
* Evitar registros duplicados.
* Suportar processamento concorrente.
* Garantir rastreabilidade por mensagem e execução.
* Registrar consumo e custo de modelos de linguagem.
* Possibilitar testes unitários, de integração e de carga.

---

## 8. Fora do escopo do MVP

Os seguintes itens não fazem parte do MVP:

* Integração com bancos;
* Leitura automática de extratos;
* Leitura automática de fatura de cartão;
* Open Finance;
* Exclusão de gastos pelo chat;
* Edição de gastos antigos pelo chat;
* Exclusão de categorias;
* Interface web para gerenciamento completo;
* Relatórios com gráficos;
* Exportação para planilhas;
* Compartilhamento de finanças entre usuários;
* Contas familiares;
* Metas financeiras avançadas;
* Orçamento por categoria;
* Alertas de estouro de orçamento;
* Previsão de gastos;
* Aprendizado automático de novos tipos de relatório;
* Recomendações financeiras;
* Planejamento de investimentos;
* Parcelamento avançado de compras;
* Controle de receitas;
* Conciliação bancária;
* Suporte a múltiplas moedas;
* Análise de anexos, notas fiscais ou comprovantes;
* Administração do produto por painel web.

Algumas dessas funcionalidades poderão ser consideradas na Fase 2.

---

## 9. Público e perfis de usuário

O produto não será limitado a um público demográfico específico. A experiência deverá ser acessível a usuários com diferentes níveis de conhecimento tecnológico.

### 9.1 Perfil A — Usuário familiarizado com tecnologia

Características:

* Utiliza aplicativos diariamente;
* Tem familiaridade com inteligência artificial;
* Escreve mensagens curtas;
* Espera respostas rápidas;
* Pode enviar vários gastos em uma única mensagem;
* Pode utilizar abreviações e linguagem informal.

Exemplo:

> “30 almoço pix e 80 gasolina crédito.”

### 9.2 Perfil B — Usuário com baixa familiaridade tecnológica

Características:

* Sabe utilizar WhatsApp;
* Pode escrever mensagens longas;
* Pode descrever o gasto de forma imprecisa;
* Pode omitir informações;
* Precisa de mensagens claras e sem termos técnicos;
* Pode utilizar áudio como principal forma de interação.

Exemplo:

> “Hoje eu fui ao mercado e acho que deu cento e cinquenta e poucos reais, deixa eu ver, foi cento e cinquenta e oito reais e vinte centavos.”

### 9.3 Princípio de acessibilidade

O usuário não deverá precisar conhecer:

* Comandos;
* Sintaxes especiais;
* Estruturas de formulário;
* Nomes internos de categorias;
* Funcionamento de agentes;
* Funcionamento de modelos de linguagem.

A interação deverá acontecer em linguagem natural.

---

## 10. Necessidades do usuário

O produto deverá atender às seguintes necessidades:

1. Registrar um gasto imediatamente após realizá-lo.
2. Registrar um gasto sem preencher formulários.
3. Registrar mais de um gasto na mesma mensagem.
4. Consultar os gastos do dia, semana ou mês.
5. Consultar gastos por categoria.
6. Consultar gastos de períodos anteriores.
7. Identificar em que categoria está gastando mais.
8. Registrar assinaturas e despesas recorrentes.
9. Corrigir rapidamente o último gasto registrado.
10. Ter segurança de que o assistente entendeu corretamente.
11. Evitar confirmações repetitivas quando a informação estiver clara.
12. Usar áudio quando não quiser digitar.

---

## 11. Princípios de experiência

### 11.1 Conversa antes de formulário

O sistema deverá adaptar a informação do usuário ao modelo de dados, e não exigir que o usuário adapte sua fala ao sistema.

### 11.2 Confirmação proporcional ao risco

O assistente não deverá pedir confirmação para toda operação.

A confirmação prévia será utilizada apenas quando houver ambiguidade relevante.

### 11.3 Transparência

A mensagem final deverá informar claramente o que foi registrado.

Exemplo:

> Gasto registrado: R$ 35,00 em Restaurante, hoje às 12:42, pago via Pix.

### 11.4 Correções simples

O usuário poderá corrigir apenas o último gasto registrado por meio do chat.

Exemplo:

> “Na verdade foram 38 reais.”

### 11.5 Segurança contra suposições

O assistente não deverá inventar valores, datas, formas de pagamento ou descrições.

### 11.6 Linguagem simples

As mensagens deverão ser curtas, objetivas e compreensíveis.

---

## 12. Escopo funcional do MVP

O MVP será composto pelos seguintes módulos lógicos:

1. Agente roteador;
2. Agente registrador;
3. Agente relator;
4. Agente de comandos fixos;
5. Agente auxiliar;
6. Agente de onboarding;
7. Serviço de transcrição de áudio;
8. Serviço de persistência;
9. Serviço de filas;
10. Serviço de observabilidade e custos.

Os agentes podem ser implementados como nós ou subgrafos dentro do LangGraph, não sendo obrigatório que cada agente corresponda a um processo independente.

---

# 13. Requisitos funcionais

## RF-001 — Identificação do usuário

O sistema deverá identificar o usuário pelo identificador fornecido pelo canal.

No WhatsApp, o identificador principal será o número de telefone normalizado.

No Telegram, o identificador principal será o ID da conta ou do chat, conforme a estratégia de integração.

### Critérios de aceite

* Cada mensagem deverá ser associada a um único usuário.
* Os dados de um usuário não poderão ser acessados por outro.
* O identificador do canal não deverá ser utilizado diretamente como chave primária interna.
* O sistema deverá possuir um identificador interno de usuário.

---

## RF-002 — Onboarding inicial

Na primeira interação, o usuário deverá ser direcionado ao fluxo de onboarding.

O onboarding deverá:

1. Solicitar o nome do usuário;
2. Explicar brevemente a função do assistente;
3. Sugerir categorias iniciais;
4. Solicitar aprovação das categorias;
5. Perguntar se o usuário deseja cadastrar gastos fixos;
6. Permitir o cadastro dos gastos fixos;
7. Informar exemplos de mensagens aceitas;
8. Finalizar o cadastro.

### Categorias iniciais sugeridas

* Alimentação;
* Restaurante;
* Bar;
* Supermercado;
* Transporte;
* Combustível;
* Moradia;
* Saúde;
* Lazer;
* Roupas;
* Esporte;
* Assinaturas;
* Outros.

A lista poderá ser reduzida ou adaptada antes da implementação.

### Regras

* O usuário poderá aprovar todas as categorias sugeridas.
* O usuário poderá rejeitar categorias.
* O usuário poderá solicitar novas categorias.
* O onboarding não deverá impedir o registro de um gasto urgente.
* Caso o usuário envie um gasto durante o onboarding, o sistema deverá registrar o gasto e retomar o fluxo posteriormente.
* O onboarding deverá possuir estado persistente.

### Critérios de aceite

* O onboarding deverá acontecer apenas para novos usuários.
* O sistema deverá reconhecer quando o onboarding estiver incompleto.
* O usuário deverá conseguir registrar seu primeiro gasto mesmo sem concluir todas as etapas.
* As categorias aprovadas deverão estar disponíveis imediatamente.

---

## RF-003 — Agente roteador

O agente roteador deverá identificar a intenção principal da mensagem.

### Intenções mínimas

* Registrar gasto;
* Registrar múltiplos gastos;
* Corrigir último gasto;
* Consultar gastos;
* Executar comando fixo;
* Criar categoria;
* Criar gasto fixo;
* Excluir gasto fixo;
* Continuar onboarding;
* Conversa não relacionada;
* Intenção não identificada.

### Regras

* Uma mesma mensagem poderá conter mais de uma intenção.
* O roteador deverá preservar as informações originais da mensagem.
* O roteador deverá produzir uma saída estruturada.
* A decisão deverá incluir um nível de confiança.
* O roteador não deverá registrar ou alterar dados diretamente.

### Exemplo de saída estruturada

```json
{
  "intents": [
    {
      "type": "register_expense",
      "confidence": 0.96
    }
  ],
  "requires_confirmation": false,
  "original_message_id": "message_uuid"
}
```

### Critérios de aceite

* Mensagens claras de gasto deverão ser encaminhadas ao agente registrador.
* Perguntas financeiras deverão ser encaminhadas ao agente relator.
* Solicitações de categorias ou gastos fixos deverão ser encaminhadas ao agente auxiliar.
* Mensagens ambíguas deverão ser tratadas sem criação indevida de registros.

---

## RF-004 — Registro de gasto individual

O agente registrador deverá extrair e armazenar as seguintes informações obrigatórias:

* Data;
* Horário;
* Descrição;
* Valor;
* Categoria;
* Usuário;
* Identificador da mensagem de origem;
* Data e hora de criação do registro.

### Informações opcionais

* Meio de pagamento;
* Texto original;
* Texto transcrito;
* Descrição normalizada;
* Nível de confiança;
* Origem da mensagem;
* Modelo utilizado;
* Metadados de rastreabilidade.

### Meios de pagamento suportados

* Pix;
* Cartão de crédito;
* Cartão de débito;
* Dinheiro;
* Não informado.

### Exemplo

Mensagem:

> “Gastei 32 reais com almoço no Pix.”

Registro esperado:

```json
{
  "amount": 32.00,
  "description": "Almoço",
  "category": "Restaurante",
  "payment_method": "pix",
  "occurred_at": "data e hora atuais",
  "source": "whatsapp"
}
```

### Critérios de aceite

* O valor deverá ser salvo com precisão decimal.
* O gasto deverá estar associado ao usuário correto.
* O gasto deverá possuir categoria.
* O gasto deverá ser confirmado ao usuário.
* O processo completo deverá ocorrer em até 15 segundos.

---

## RF-005 — Data e hora do gasto

### Regra padrão

Quando o usuário não informar data ou horário, o sistema deverá utilizar a data e hora da mensagem recebida.

### Data passada sem indicação de mês

Quando o usuário informar apenas um dia anterior, o sistema deverá considerar o mês atual.

Exemplo:

Em 20 de julho:

> “No dia 15 gastei 40 no mercado.”

Resultado:

> 15 de julho do ano atual.

### Data futura

O sistema não deverá registrar gastos com data futura.

Exemplo:

> “Amanhã vou gastar 100 reais no mercado.”

O sistema deverá informar que gastos futuros não podem ser registrados como realizados.

### Data ambígua

Exemplo:

> “Gastei 80 no dia 10.”

Se houver apenas uma interpretação válida no mês atual, o gasto poderá ser registrado.

Caso a interpretação resulte em data futura, o sistema deverá solicitar esclarecimento ou informar a restrição.

### Horário informado

Se o usuário mencionar um horário, ele deverá ser respeitado.

Exemplo:

> “Hoje às 14h gastei 20 reais.”

### Critérios de aceite

* Datas futuras não poderão gerar registros de gastos realizados.
* A data padrão deverá ser a data da mensagem.
* A resolução de data deverá respeitar o fuso horário configurado para o usuário.
* O sistema deverá armazenar datas em formato consistente, preferencialmente UTC, com conversão para o fuso do usuário.

---

## RF-006 — Descrição do gasto

O sistema deverá armazenar:

1. A mensagem original ou trecho original;
2. Uma descrição normalizada.

Exemplo:

Mensagem original:

> “Paguei 42 conto naquele hambúrguer.”

Descrição normalizada:

> “Hambúrguer”

### Regras

* A descrição normalizada não deverá alterar o significado.
* Marcas, estabelecimentos e produtos mencionados poderão ser preservados.
* O texto original deverá permanecer disponível para auditoria.
* O sistema não deverá enriquecer a descrição com informações não fornecidas.

---

## RF-007 — Categorização do gasto

O sistema deverá associar cada gasto a uma categoria existente do usuário.

### Estratégia

1. Identificar uma categoria compatível.
2. Utilizar o histórico do usuário quando aplicável.
3. Avaliar o nível de confiança.
4. Confirmar apenas em casos ambíguos.
5. Utilizar “Outros” quando nenhuma categoria adequada for identificada com segurança.

### Exemplo de alta confiança

> “Gastei 80 no supermercado.”

Categoria:

> Supermercado.

### Exemplo de ambiguidade

> “Gastei 90 no clube.”

Possíveis categorias:

* Lazer;
* Esporte;
* Assinaturas.

Nesse caso, o sistema deverá solicitar esclarecimento.

### Critérios de aceite

* Todo gasto deverá possuir uma categoria.
* A categoria deverá pertencer ao usuário ou ser uma categoria padrão autorizada.
* O agente não poderá criar uma categoria silenciosamente.
* Uma nova categoria dependerá de solicitação ou aprovação do usuário.

---

## RF-008 — Registro de múltiplos gastos

O sistema deverá registrar mais de um gasto enviado na mesma mensagem.

Exemplo:

> “Gastei 30 com pastel e mais 20 de gasolina.”

Resultado esperado:

1. R$ 30,00 — Pastel — Alimentação;
2. R$ 20,00 — Gasolina — Combustível.

### Regras

* Cada gasto deverá gerar um registro independente.
* Todos os gastos deverão possuir o mesmo identificador de mensagem de origem.
* Cada gasto poderá possuir categoria e meio de pagamento diferentes.
* O sistema deverá confirmar todos os registros de forma agrupada.
* Caso apenas um dos gastos esteja ambíguo, os demais gastos claros poderão ser registrados.
* O gasto ambíguo deverá ser apresentado separadamente para confirmação.

### Exemplo de confirmação

> Registrei 2 gastos:
>
> • R$ 30,00 em Alimentação — Pastel
> • R$ 20,00 em Combustível — Gasolina
>
> Total: R$ 50,00.

### Critérios de aceite

* O sistema não deverá somar múltiplos gastos em um único registro.
* A quantidade de registros deverá corresponder à quantidade de gastos identificados.
* O valor total da confirmação deverá corresponder à soma dos registros.

---

## RF-009 — Confirmação de registro

Após salvar o gasto, o assistente deverá enviar uma mensagem de confirmação.

A confirmação deverá conter:

* Valor;
* Descrição;
* Categoria;
* Data, quando diferente da data atual;
* Meio de pagamento, quando informado.

### Exemplo

> Registrei R$ 45,00 em Restaurante, pago via Pix.

### Regra de conclusão

A operação será considerada concluída apenas quando:

1. O registro estiver persistido;
2. A confirmação tiver sido enviada ao canal.

### Critérios de aceite

* Uma falha no envio da confirmação deverá ser registrada.
* O sistema não deverá inserir o gasto novamente caso o canal repita a entrega da mensagem.
* Reprocessamentos deverão ser idempotentes.

---

## RF-010 — Confirmação por ambiguidade

O sistema deverá solicitar confirmação apenas quando houver risco relevante de registro incorreto.

### Situações que exigem confirmação

* Valor ausente;
* Mais de um valor possível para o mesmo gasto;
* Data ambígua;
* Categoria com baixa confiança;
* Descrição insuficiente;
* Divergência entre o áudio e a interpretação;
* Meio de pagamento conflitante;
* Mensagem que pode representar intenção futura;
* Incerteza sobre a quantidade de gastos;
* Correção que pode afetar mais de um campo.

### Situações que não exigem confirmação

* Gasto claro com valor e descrição;
* Categoria inferida com alta confiança;
* Meio de pagamento ausente;
* Data e horário ausentes;
* Uso de linguagem informal sem impacto no significado.

### Política inicial de confiança

Os valores exatos deverão ser calibrados durante os testes.

Sugestão inicial:

| Confiança         | Ação                                      |
| ----------------- | ----------------------------------------- |
| 0,90 ou maior     | Registrar sem confirmação prévia          |
| Entre 0,70 e 0,89 | Avaliar regras determinísticas e contexto |
| Abaixo de 0,70    | Solicitar confirmação                     |

O nível de confiança do modelo não deverá ser o único critério. Regras determinísticas deverão ter prioridade.

### Exemplo

Mensagem:

> “Gastei cinquenta e alguma coisa no mercado.”

Resposta:

> Qual foi o valor exato do gasto no mercado?

---

## RF-011 — Correção do último gasto

O usuário poderá alterar apenas o último gasto registrado.

Exemplos:

> “Na verdade foram 45 reais.”

> “Foi no débito, não no Pix.”

> “Coloca como supermercado.”

### Regras

* A correção deverá afetar apenas o último gasto elegível do usuário.
* O sistema deverá validar se a mensagem representa uma correção.
* O gasto anterior deverá permanecer auditável.
* A alteração deverá gerar histórico de versão ou evento de auditoria.
* Caso não exista gasto anterior, o sistema deverá informar que não encontrou um gasto para corrigir.
* Caso o usuário solicite alteração de um gasto mais antigo, deverá ser informado de que isso estará disponível na interface web da Fase 2.

### Caso de múltiplos gastos

Se a mensagem anterior tiver gerado múltiplos gastos, uma correção como “o segundo foi 25” poderá ser aceita somente se a referência for clara.

Caso contrário, o sistema deverá solicitar esclarecimento.

### Critérios de aceite

* Apenas registros do próprio usuário poderão ser alterados.
* O histórico da alteração deverá ser preservado.
* A confirmação deverá apresentar os novos dados.

---

## RF-012 — Exclusão de gastos

O assistente não deverá excluir gastos pelo chat no MVP.

Ao receber uma solicitação de exclusão, deverá responder de forma clara.

Exemplo:

> A exclusão de gastos ainda não está disponível pelo WhatsApp. Essa função será disponibilizada em uma interface web em uma próxima fase.

O sistema não deverá apagar, ocultar ou invalidar o gasto.

---

## RF-013 — Criação de categorias

O agente auxiliar deverá permitir que o usuário crie novas categorias.

Exemplos:

> “Crie uma categoria chamada Pet.”

> “Quero uma categoria para presentes.”

### Regras

* A categoria deverá pertencer ao usuário.
* O nome deverá ser normalizado.
* Categorias duplicadas não deverão ser criadas.
* O sistema poderá sugerir a utilização de uma categoria existente.
* A criação deverá ser confirmada.
* O sistema deverá permitir o uso imediato da categoria.

### Critérios de aceite

* Categorias com o mesmo nome normalizado não poderão ser duplicadas para o mesmo usuário.
* Categorias de usuários diferentes poderão ter o mesmo nome.
* A criação deverá gerar evento de auditoria.

---

## RF-014 — Exclusão de categorias

O sistema não deverá excluir categorias no MVP.

Ao receber essa solicitação, deverá explicar que a funcionalidade não está disponível.

O agente nunca deverá excluir uma categoria por inferência.

---

## RF-015 — Cadastro de gastos fixos

O usuário deverá poder cadastrar despesas recorrentes mensais.

Exemplos:

> “Todo dia 10 eu pago R$ 120 de internet.”

> “Adicione Netflix por R$ 39,90 todo dia 5.”

### Informações obrigatórias

* Descrição;
* Valor;
* Dia de recorrência;
* Categoria;
* Usuário;
* Status ativo.

### Informações opcionais

* Meio de pagamento;
* Data inicial;
* Data final;
* Observação.

### Regras

* O gasto fixo deverá representar uma regra de recorrência.
* O cadastro do gasto fixo não deverá necessariamente criar imediatamente um gasto realizado.
* A geração automática dos lançamentos deverá ser definida pela estratégia do MVP.
* Gastos fixos deverão ser listáveis.
* O usuário deverá poder excluir ou desativar gastos fixos pelo chat.
* A exclusão do gasto fixo não deverá excluir lançamentos históricos.

### Estratégia recomendada para o MVP

O sistema deverá gerar automaticamente o lançamento do gasto fixo no dia programado.

O lançamento deverá possuir referência ao gasto fixo de origem.

Caso a geração automática ainda não seja implementada na primeira versão técnica, o produto deverá:

* Armazenar o gasto fixo;
* Informar claramente que ele foi cadastrado;
* Não contabilizá-lo como gasto realizado até que um lançamento seja criado.

Essa decisão deverá ser fechada antes do início do desenvolvimento.

---

## RF-016 — Exclusão ou desativação de gastos fixos

O usuário deverá poder desativar um gasto fixo.

Exemplo:

> “Cancelei a Netflix.”

### Regras

* Apenas o gasto fixo deverá ser desativado.
* Gastos históricos deverão ser mantidos.
* O sistema deverá solicitar esclarecimento caso existam gastos fixos com nomes semelhantes.
* A ação deverá ser confirmada.

### Exemplo

> O gasto fixo “Netflix — R$ 39,90” foi desativado. Os registros anteriores foram mantidos.

---

## RF-017 — Consulta de gastos

O agente relator deverá responder perguntas financeiras suportadas pelo MVP.

### Consultas mínimas

* Quanto gastei hoje?
* Quanto gastei ontem?
* Quanto gastei esta semana?
* Quanto gastei na semana passada?
* Quanto gastei este mês?
* Quanto gastei em uma categoria hoje?
* Quanto gastei em uma categoria esta semana?
* Quanto gastei em uma categoria este mês?
* Quanto gastei em duas semanas combinadas?
* Quanto gastei em supermercado nesta semana e na semana passada?
* Qual semana do mês teve mais gastos?
* Quanto gastei por meio de pagamento?
* Quais foram meus últimos gastos?
* Quais foram os gastos de determinado dia?

### Regras

* Os cálculos deverão ser executados sobre dados estruturados.
* O modelo de linguagem não deverá calcular totais a partir de texto livre.
* Consultas financeiras deverão ser convertidas em filtros estruturados.
* O banco de dados deverá executar agregações e somas.
* A resposta deverá ser gerada a partir do resultado calculado.
* O período deverá respeitar o fuso horário do usuário.
* A definição de início da semana deverá ser configurada. Para o MVP, recomenda-se segunda-feira.

### Critérios de aceite

* Os valores exibidos deverão corresponder aos dados armazenados.
* O sistema deverá informar quando não houver gastos.
* O sistema não deverá inventar registros.
* A resposta deverá informar claramente o período consultado.

---

## RF-018 — Comandos fixos de relatório

O sistema deverá reconhecer comandos frequentes, mesmo que sejam escritos com pequenas variações.

### Comandos mínimos

* “Últimos gastos”;
* “Meus últimos gastos”;
* “Gastos de hoje”;
* “Gastos de ontem”;
* “Gastos desta semana”;
* “Gastos do mês”;
* “Gastos fixos”;
* “Minhas categorias”.

### Últimos gastos

O comando “últimos gastos” deverá listar os cinco lançamentos mais recentes.

Cada item deverá apresentar:

* Valor;
* Descrição;
* Categoria;
* Data;
* Meio de pagamento, quando disponível.

### Exemplo

> Seus últimos 5 gastos:
>
> 1. R$ 45,00 — Almoço — Restaurante — hoje, 12:40
> 2. R$ 120,00 — Combustível — ontem, 18:10
> 3. R$ 32,90 — Farmácia — Saúde — ontem, 10:22
> 4. R$ 18,00 — Café — Alimentação — 22/07
> 5. R$ 79,90 — Camiseta — Roupas — 21/07

---

## RF-019 — Perguntas não suportadas

Quando o usuário fizer uma pergunta que o MVP não consegue responder, o assistente deverá:

1. Informar que a consulta ainda não é suportada;
2. Não inventar uma resposta;
3. Sugerir consultas próximas que estejam disponíveis;
4. Registrar a intenção não atendida para análise futura.

### Exemplo

> Ainda não consigo prever quanto você gastará até o fim do mês. Posso informar quanto você gastou até agora ou comparar com a semana passada.

O aprendizado automático de novas consultas não faz parte do MVP.

---

## RF-020 — Entrada por áudio

O sistema deverá aceitar mensagens de áudio.

### Fluxo

1. Receber o arquivo de áudio;
2. Validar formato e tamanho;
3. Transcrever;
4. Armazenar a transcrição;
5. Encaminhar o texto transcrito ao roteador;
6. Processar a intenção;
7. Responder ao usuário em texto.

### Regras

* O áudio original poderá ser armazenado temporariamente.
* A política de retenção deverá ser definida.
* A transcrição deverá estar associada à mensagem.
* O sistema deverá informar quando não conseguir compreender o áudio.
* Informações financeiras críticas com baixa confiança deverão ser confirmadas.

### Exemplo

> Entendi “R$ 70 ou R$ 17”. Qual foi o valor correto?

### Critérios de aceite

* O usuário deverá conseguir registrar um gasto usando apenas áudio.
* A transcrição deverá ser rastreável.
* Falhas de transcrição não deverão criar registros incorretos.

---

## RF-021 — Mensagens duplicadas

O sistema deverá impedir registros duplicados causados por:

* Reenvio do provedor;
* Timeout;
* Retry de webhook;
* Retry do worker;
* Reprocessamento manual;
* Entrega duplicada do canal.

### Estratégia

Cada mensagem recebida deverá possuir uma chave de idempotência formada preferencialmente por:

* Canal;
* Identificador externo da mensagem;
* Identificador do usuário.

### Critérios de aceite

* Uma mesma mensagem externa não poderá gerar mais de um conjunto de lançamentos.
* O sistema deverá retornar ou reutilizar o resultado anterior quando apropriado.
* O comportamento deverá ser testado em cenários concorrentes.

---

## RF-022 — Ordenação de mensagens por usuário

As mensagens de um mesmo usuário deverão ser processadas na ordem correta sempre que a ordem afetar o resultado.

Isso é necessário para casos como:

1. “Gastei 30 no almoço.”
2. “Na verdade foram 35.”

### Regras

* O sistema deverá evitar o processamento paralelo desordenado de mensagens do mesmo usuário.
* Usuários diferentes poderão ser processados em paralelo.
* O mecanismo poderá utilizar chave de partição, lock por usuário ou controle transacional.

---

## RF-023 — Rastreabilidade

Cada execução deverá possuir um identificador de correlação.

O sistema deverá registrar:

* Usuário;
* Canal;
* Mensagem recebida;
* Intenção identificada;
* Agentes executados;
* Modelos utilizados;
* Chamadas externas;
* Tokens de entrada;
* Tokens de saída;
* Custo estimado;
* Tempo de execução;
* Resultado;
* Erros;
* Tentativas;
* Registros criados ou alterados.

Dados sensíveis deverão ser protegidos nos logs.

---

## RF-024 — Rastreabilidade de custo

O sistema deverá calcular ou estimar o custo de cada execução.

### Informações mínimas

* Provedor;
* Modelo;
* Tokens de entrada;
* Tokens de saída;
* Custo da transcrição;
* Custo total da execução;
* Identificador da mensagem;
* Identificador interno do usuário;
* Tipo de operação.

### Relatórios internos desejados

* Custo médio por gasto registrado;
* Custo médio por mensagem;
* Custo médio por usuário;
* Custo por agente;
* Custo por modelo;
* Custo por canal;
* Custo total diário e mensal.

---

# 14. Requisitos não funcionais

## RNF-001 — Desempenho do registro

O fluxo de registro de gasto deverá ser concluído em até 15 segundos.

A medição começa no momento em que o webhook é recebido pelo sistema e termina quando o envio da mensagem de confirmação é aceito pelo provedor do canal.

### Meta recomendada

| Percentil | Tempo máximo |
| --------- | -----------: |
| P50       |   5 segundos |
| P90       |  10 segundos |
| P95       |  15 segundos |
| P99       |  25 segundos |

O requisito obrigatório do MVP será P95 em até 15 segundos em condições normais de operação.

---

## RNF-002 — Tempo de resposta geral

Mensagens que não representam registro de gasto deverão receber resposta em até 25 segundos.

Exemplos:

* Relatórios;
* Criação de categorias;
* Cadastro de gastos fixos;
* Perguntas de onboarding.

---

## RNF-003 — Concorrência

O sistema deverá suportar múltiplos usuários simultâneos.

A arquitetura deverá permitir:

* Aumento do número de workers;
* Processamento paralelo entre usuários;
* Ordenação por usuário;
* Retry controlado;
* Recuperação após falhas;
* Distribuição segura das tarefas.

A capacidade exata de usuários simultâneos deverá ser definida após o primeiro teste de carga.

---

## RNF-004 — Isolamento de dados

Todos os registros financeiros deverão conter um identificador interno de usuário.

Toda consulta ou alteração deverá filtrar explicitamente pelo identificador do usuário.

### Regras

* Nenhuma consulta financeira poderá ocorrer sem filtro de usuário.
* Chaves estrangeiras deverão preservar o vínculo com o usuário.
* Testes automatizados deverão validar o isolamento.
* O sistema deverá evitar uso exclusivo de filtros aplicados na camada de aplicação.
* Sempre que possível, deverão ser utilizadas proteções adicionais no banco, como Row-Level Security.

---

## RNF-005 — Segurança

O sistema deverá:

* Utilizar HTTPS;
* Validar webhooks dos provedores;
* Proteger credenciais;
* Utilizar variáveis de ambiente ou serviço de segredos;
* Não registrar tokens em logs;
* Limitar tentativas abusivas;
* Sanitizar entradas;
* Implementar controle de acesso na futura interface web;
* Manter trilha de auditoria;
* Minimizar exposição de dados pessoais.

---

## RNF-006 — Privacidade

O sistema deverá armazenar apenas os dados necessários para o funcionamento do produto.

Deverão ser definidas políticas para:

* Retenção de mensagens;
* Retenção de áudios;
* Exclusão da conta;
* Exportação dos dados;
* Anonimização de logs;
* Uso de mensagens em ambientes de desenvolvimento;
* Envio de dados a provedores de modelos.

O produto deverá considerar os requisitos aplicáveis da LGPD.

---

## RNF-007 — Disponibilidade

Meta inicial recomendada para o MVP:

> 99% de disponibilidade mensal, desconsiderando manutenções programadas.

Falhas em modelos ou provedores externos deverão possuir tratamento adequado.

---

## RNF-008 — Resiliência

O sistema deverá possuir:

* Retry com limite;
* Backoff exponencial;
* Dead-letter queue ou tabela de falhas;
* Timeout por serviço externo;
* Circuit breaker quando necessário;
* Idempotência;
* Logs estruturados;
* Reprocessamento seguro.

---

## RNF-009 — Observabilidade

O sistema deverá possuir métricas, logs e rastreamento distribuído ou correlacionado.

### Métricas mínimas

* Mensagens recebidas;
* Mensagens processadas;
* Mensagens com erro;
* Tempo por etapa;
* Tamanho da fila;
* Idade da mensagem mais antiga da fila;
* Quantidade de retries;
* Gastos registrados;
* Gastos corrigidos;
* Confirmações solicitadas;
* Taxa de ambiguidade;
* Consultas respondidas;
* Consultas não suportadas;
* Custo por execução;
* Tokens consumidos;
* Falhas por modelo;
* Falhas por canal.

---

## RNF-010 — Auditabilidade

Alterações financeiras deverão produzir eventos de auditoria.

A auditoria deverá permitir responder:

* Quem realizou a ação;
* Quando a ação ocorreu;
* Qual mensagem originou a ação;
* Quais eram os dados anteriores;
* Quais são os dados atuais;
* Qual agente e modelo participaram da decisão.

---

## RNF-011 — Qualidade da interpretação

A qualidade da extração deverá ser medida por campo.

### Métricas mínimas

* Precisão do valor;
* Precisão da data;
* Precisão da descrição;
* Precisão da categoria;
* Precisão do meio de pagamento;
* Precisão da quantidade de gastos;
* Precisão da intenção;
* Taxa de registros que precisaram de correção.

### Meta inicial recomendada

| Campo                |                  Meta |
| -------------------- | --------------------: |
| Valor                |                   99% |
| Quantidade de gastos |                   98% |
| Data                 |                   98% |
| Intenção             |                   97% |
| Categoria            |                   90% |
| Meio de pagamento    | 95%, quando informado |

As metas deverão ser avaliadas em um conjunto de testes representativo.

---

# 15. Arquitetura proposta

## 15.1 Componentes principais

```text
WhatsApp / Telegram
        |
        v
     FastAPI
        |
        v
Validação do webhook
        |
        v
Persistência da mensagem
        |
        v
Fila no PostgreSQL
        |
        v
Workers de processamento
        |
        v
LangGraph / Agentes
        |
        +----------------------+
        |                      |
        v                      v
OpenRouter / LLM         Transcrição de áudio
        |
        v
Serviços de domínio
        |
        v
PostgreSQL
        |
        v
Envio da resposta
```

---

## 15.2 FastAPI

Responsabilidades:

* Receber webhooks;
* Validar autenticidade;
* Normalizar eventos;
* Persistir mensagens;
* Criar tarefas na fila;
* Responder rapidamente ao provedor;
* Expor endpoints internos;
* Fornecer health checks;
* Expor métricas.

O webhook não deverá aguardar todo o processamento do agente.

---

## 15.3 PostgreSQL

O PostgreSQL será utilizado para:

* Armazenamento de usuários;
* Armazenamento de mensagens;
* Armazenamento de gastos;
* Armazenamento de categorias;
* Armazenamento de gastos fixos;
* Armazenamento de auditoria;
* Armazenamento de custos;
* Gerenciamento inicial da fila.

### Estratégia de fila

Poderá ser utilizada uma tabela de tarefas com:

* Status;
* Prioridade;
* Data de criação;
* Número de tentativas;
* Próxima tentativa;
* Worker responsável;
* Lock;
* Payload;
* Chave de partição por usuário.

O consumo concorrente poderá utilizar:

```sql
FOR UPDATE SKIP LOCKED
```

A implementação deverá evitar que dois workers processem simultaneamente mensagens conflitantes do mesmo usuário.

---

## 15.4 LangGraph

O LangGraph deverá coordenar o fluxo de processamento.

### Estado mínimo do grafo

```python
class AssistantState(TypedDict):
    execution_id: str
    user_id: str
    channel: str
    message_id: str
    original_text: str | None
    transcribed_text: str | None
    intents: list
    confidence: float | None
    pending_confirmation: dict | None
    expenses: list
    report_request: dict | None
    response_text: str | None
    errors: list
```

### Nós sugeridos

1. Carregar contexto do usuário;
2. Transcrever áudio;
3. Normalizar entrada;
4. Classificar intenção;
5. Extrair gastos;
6. Validar regras;
7. Avaliar ambiguidade;
8. Solicitar confirmação;
9. Persistir gastos;
10. Executar consulta;
11. Gerenciar categorias;
12. Gerenciar gastos fixos;
13. Gerar resposta;
14. Enviar resposta;
15. Registrar custos e métricas.

---

## 15.5 OpenRouter

O OpenRouter será utilizado como camada de roteamento entre modelos.

### Requisitos

* Possibilitar troca de modelo por variável de ambiente;
* Registrar modelo utilizado;
* Registrar tokens e custos;
* Possuir timeout;
* Possuir fallback;
* Diferenciar modelos por tarefa;
* Evitar uso de modelos caros em tarefas simples.

### Estratégia inicial

* Modelo de baixo custo para classificação de intenção;
* Modelo de maior qualidade para extrações complexas;
* Regras determinísticas para validações;
* SQL e código para cálculos financeiros.

---

## 15.6 Docker

A solução deverá ser contenerizada.

### Serviços iniciais

* API;
* Worker;
* PostgreSQL;
* Serviço de testes ou utilitários;
* Observabilidade, quando aplicável.

API e worker deverão utilizar a mesma base de código, com processos separados.

---

# 16. Modelo de dados inicial

## 16.1 users

| Campo             | Tipo      | Descrição             |
| ----------------- | --------- | --------------------- |
| id                | UUID      | Identificador interno |
| name              | VARCHAR   | Nome do usuário       |
| timezone          | VARCHAR   | Fuso horário          |
| currency          | VARCHAR   | Moeda padrão          |
| onboarding_status | VARCHAR   | Estado do onboarding  |
| created_at        | TIMESTAMP | Data de criação       |
| updated_at        | TIMESTAMP | Data de alteração     |

---

## 16.2 user_channels

| Campo            | Tipo      | Descrição              |
| ---------------- | --------- | ---------------------- |
| id               | UUID      | Identificador          |
| user_id          | UUID      | Usuário                |
| channel          | VARCHAR   | WhatsApp ou Telegram   |
| external_user_id | VARCHAR   | Identificador do canal |
| verified         | BOOLEAN   | Canal validado         |
| created_at       | TIMESTAMP | Data de criação        |

Restrição única recomendada:

```text
channel + external_user_id
```

---

## 16.3 messages

| Campo               | Tipo      | Descrição              |
| ------------------- | --------- | ---------------------- |
| id                  | UUID      | Identificador interno  |
| user_id             | UUID      | Usuário                |
| channel             | VARCHAR   | Canal                  |
| external_message_id | VARCHAR   | ID da mensagem externa |
| message_type        | VARCHAR   | Texto ou áudio         |
| original_text       | TEXT      | Texto original         |
| transcribed_text    | TEXT      | Transcrição            |
| received_at         | TIMESTAMP | Recebimento            |
| processed_at        | TIMESTAMP | Processamento          |
| status              | VARCHAR   | Estado                 |
| idempotency_key     | VARCHAR   | Chave única            |
| metadata            | JSONB     | Dados adicionais       |

---

## 16.4 categories

| Campo           | Tipo      | Descrição         |
| --------------- | --------- | ----------------- |
| id              | UUID      | Identificador     |
| user_id         | UUID      | Usuário           |
| name            | VARCHAR   | Nome              |
| normalized_name | VARCHAR   | Nome normalizado  |
| is_default      | BOOLEAN   | Categoria inicial |
| is_active       | BOOLEAN   | Estado            |
| created_at      | TIMESTAMP | Criação           |

Restrição única recomendada:

```text
user_id + normalized_name
```

---

## 16.5 expenses

| Campo                | Tipo      | Descrição             |
| -------------------- | --------- | --------------------- |
| id                   | UUID      | Identificador         |
| user_id              | UUID      | Usuário               |
| category_id          | UUID      | Categoria             |
| source_message_id    | UUID      | Mensagem de origem    |
| recurring_expense_id | UUID      | Gasto fixo de origem  |
| amount               | NUMERIC   | Valor                 |
| description          | VARCHAR   | Descrição normalizada |
| original_description | TEXT      | Descrição original    |
| payment_method       | VARCHAR   | Meio de pagamento     |
| occurred_at          | TIMESTAMP | Data e hora do gasto  |
| confidence           | NUMERIC   | Confiança             |
| created_at           | TIMESTAMP | Criação               |
| updated_at           | TIMESTAMP | Alteração             |

---

## 16.6 recurring_expenses

| Campo          | Tipo      | Descrição     |
| -------------- | --------- | ------------- |
| id             | UUID      | Identificador |
| user_id        | UUID      | Usuário       |
| category_id    | UUID      | Categoria     |
| description    | VARCHAR   | Descrição     |
| amount         | NUMERIC   | Valor         |
| payment_method | VARCHAR   | Meio          |
| recurrence_day | INTEGER   | Dia do mês    |
| starts_at      | DATE      | Início        |
| ends_at        | DATE      | Término       |
| is_active      | BOOLEAN   | Estado        |
| created_at     | TIMESTAMP | Criação       |
| updated_at     | TIMESTAMP | Alteração     |

---

## 16.7 expense_audit_log

| Campo             | Tipo      | Descrição       |
| ----------------- | --------- | --------------- |
| id                | UUID      | Identificador   |
| expense_id        | UUID      | Gasto           |
| user_id           | UUID      | Usuário         |
| action            | VARCHAR   | Ação            |
| before_data       | JSONB     | Estado anterior |
| after_data        | JSONB     | Estado atual    |
| source_message_id | UUID      | Mensagem        |
| created_at        | TIMESTAMP | Data            |

---

## 16.8 executions

| Campo       | Tipo      | Descrição |
| ----------- | --------- | --------- |
| id          | UUID      | Execução  |
| user_id     | UUID      | Usuário   |
| message_id  | UUID      | Mensagem  |
| intent      | VARCHAR   | Intenção  |
| status      | VARCHAR   | Estado    |
| started_at  | TIMESTAMP | Início    |
| finished_at | TIMESTAMP | Fim       |
| duration_ms | INTEGER   | Duração   |
| error       | JSONB     | Erro      |
| metadata    | JSONB     | Metadados |

---

## 16.9 model_usage

| Campo         | Tipo      | Descrição         |
| ------------- | --------- | ----------------- |
| id            | UUID      | Identificador     |
| execution_id  | UUID      | Execução          |
| provider      | VARCHAR   | Provedor          |
| model         | VARCHAR   | Modelo            |
| input_tokens  | INTEGER   | Tokens de entrada |
| output_tokens | INTEGER   | Tokens de saída   |
| cost          | NUMERIC   | Custo             |
| latency_ms    | INTEGER   | Latência          |
| created_at    | TIMESTAMP | Data              |

---

## 16.10 jobs

| Campo        | Tipo      | Descrição        |
| ------------ | --------- | ---------------- |
| id           | UUID      | Tarefa           |
| user_id      | UUID      | Usuário          |
| message_id   | UUID      | Mensagem         |
| job_type     | VARCHAR   | Tipo             |
| status       | VARCHAR   | Estado           |
| priority     | INTEGER   | Prioridade       |
| attempts     | INTEGER   | Tentativas       |
| available_at | TIMESTAMP | Próxima execução |
| locked_at    | TIMESTAMP | Lock             |
| locked_by    | VARCHAR   | Worker           |
| payload      | JSONB     | Dados            |
| created_at   | TIMESTAMP | Criação          |
| updated_at   | TIMESTAMP | Alteração        |

---

# 17. Fluxos principais

## 17.1 Registro simples

```text
Usuário envia mensagem
        |
Sistema recebe webhook
        |
Mensagem é persistida
        |
Tarefa é criada
        |
Worker consome tarefa
        |
Roteador identifica registro de gasto
        |
Registrador extrai os campos
        |
Validações determinísticas são executadas
        |
Confiança é suficiente?
    |               |
   Sim             Não
    |               |
Gasto é salvo   Solicita esclarecimento
    |
Confirmação é enviada
```

---

## 17.2 Registro de múltiplos gastos

```text
Mensagem recebida
        |
Extração identifica N gastos
        |
Cada gasto é validado
        |
Gastos claros são persistidos
        |
Gastos ambíguos são separados
        |
Resposta confirma registros claros
        |
Sistema pergunta sobre itens ambíguos
```

---

## 17.3 Correção do último gasto

```text
Usuário envia correção
        |
Roteador identifica intenção de correção
        |
Sistema busca último gasto elegível
        |
Extrai campos alterados
        |
Registra auditoria
        |
Atualiza gasto
        |
Envia confirmação
```

---

## 17.4 Consulta de relatório

```text
Usuário faz pergunta
        |
Roteador identifica consulta
        |
Relator gera filtros estruturados
        |
Validador verifica período e categoria
        |
Banco executa consulta
        |
Sistema gera resposta textual
        |
Resposta é enviada
```

---

## 17.5 Entrada por áudio

```text
Áudio recebido
        |
Arquivo validado
        |
Transcrição executada
        |
Confiança da transcrição avaliada
        |
Texto segue fluxo normal
```

---

# 18. Contratos estruturados dos agentes

## 18.1 Saída do roteador

```json
{
  "intents": [
    {
      "type": "register_expense",
      "confidence": 0.97
    }
  ],
  "entities": {},
  "requires_context": false
}
```

---

## 18.2 Saída do registrador

```json
{
  "expenses": [
    {
      "amount": "30.00",
      "description": "Pastel",
      "category_name": "Alimentação",
      "payment_method": null,
      "occurred_at": "2026-07-25T12:30:00-03:00",
      "confidence": {
        "amount": 0.99,
        "description": 0.96,
        "category": 0.93,
        "date": 0.99
      }
    }
  ],
  "requires_confirmation": false,
  "ambiguities": []
}
```

---

## 18.3 Saída do relator

```json
{
  "metric": "total_spent",
  "date_range": {
    "start": "2026-07-20T00:00:00-03:00",
    "end": "2026-07-26T23:59:59-03:00"
  },
  "category_filters": ["Supermercado"],
  "payment_methods": [],
  "group_by": null,
  "limit": null
}
```

O SQL não deverá ser produzido e executado diretamente pelo modelo sem validação.

---

# 19. Regras de negócio

## RB-001

Todo gasto deverá pertencer a exatamente um usuário.

## RB-002

Todo gasto deverá possuir valor maior que zero.

## RB-003

Todo gasto deverá possuir uma categoria.

## RB-004

Um gasto não poderá possuir data futura.

## RB-005

Na ausência de data, será utilizada a data da mensagem.

## RB-006

Na ausência de horário, será utilizado o horário da mensagem.

## RB-007

Na ausência de meio de pagamento, o campo será salvo como não informado.

## RB-008

O chat poderá alterar apenas o último gasto elegível.

## RB-009

O chat não poderá excluir gastos.

## RB-010

O chat não poderá excluir categorias.

## RB-011

O chat poderá desativar gastos fixos.

## RB-012

Uma mensagem poderá gerar múltiplos gastos.

## RB-013

Uma mesma mensagem externa não poderá gerar registros duplicados.

## RB-014

Consultas financeiras deverão considerar apenas gastos do usuário autenticado.

## RB-015

O modelo de linguagem não será a fonte final dos cálculos financeiros.

## RB-016

Valores monetários deverão utilizar tipo decimal, nunca ponto flutuante binário.

## RB-017

Todos os horários deverão ser interpretados no fuso do usuário.

## RB-018

A semana deverá começar na segunda-feira, salvo configuração futura.

## RB-019

Alterações deverão gerar registro de auditoria.

## RB-020

Em caso de ambiguidade crítica, nenhum registro incerto deverá ser criado.

---

# 20. Experiência conversacional

## 20.1 Registro claro

**Usuário**

> Gastei 35 no almoço.

**Assistente**

> Registrei R$ 35,00 em Restaurante — Almoço.

---

## 20.2 Registro com meio de pagamento

**Usuário**

> Paguei 80 de gasolina no crédito.

**Assistente**

> Registrei R$ 80,00 em Combustível, pago no cartão de crédito.

---

## 20.3 Registro múltiplo

**Usuário**

> Gastei 30 no almoço e 22 de Uber.

**Assistente**

> Registrei 2 gastos:
>
> • R$ 30,00 em Restaurante — Almoço
> • R$ 22,00 em Transporte — Uber
>
> Total: R$ 52,00.

---

## 20.4 Valor ausente

**Usuário**

> Gastei no mercado.

**Assistente**

> Qual foi o valor gasto no mercado?

---

## 20.5 Data futura

**Usuário**

> Amanhã vou gastar 100 no mercado.

**Assistente**

> Não registro gastos futuros como realizados. Quando a compra acontecer, envie o valor e eu faço o registro.

---

## 20.6 Correção

**Usuário**

> Gastei 40 no almoço.

**Assistente**

> Registrei R$ 40,00 em Restaurante — Almoço.

**Usuário**

> Na verdade foram 45.

**Assistente**

> Corrigi seu último gasto para R$ 45,00.

---

## 20.7 Alteração de gasto antigo

**Usuário**

> Altere o mercado da semana passada para 130.

**Assistente**

> Pelo WhatsApp, só consigo corrigir o último gasto registrado. A edição de gastos anteriores será disponibilizada na interface web.

---

## 20.8 Consulta

**Usuário**

> Quanto gastei com comida esta semana?

**Assistente**

> Você gastou R$ 284,50 com alimentação nesta semana, de segunda-feira até hoje.

---

## 20.9 Nenhum gasto encontrado

**Usuário**

> Quanto gastei ontem?

**Assistente**

> Não encontrei gastos registrados ontem.

---

## 20.10 Consulta não suportada

**Usuário**

> Quanto eu provavelmente vou gastar até o fim do ano?

**Assistente**

> Ainda não faço projeções de gastos. Posso mostrar quanto você gastou neste mês ou comparar com o mês anterior.

---

# 21. Métricas do MVP

## 21.1 Métrica principal

### Taxa de registro em 30 dias

```text
Quantidade de gastos registrados
÷
Quantidade estimada de gastos realizados
```

Meta:

> Pelo menos 85%.

---

## 21.2 Métricas de ativação

* Percentual de usuários que concluem o onboarding;
* Percentual de usuários que registram o primeiro gasto;
* Tempo até o primeiro gasto registrado;
* Percentual de usuários que criam pelo menos uma categoria;
* Percentual de usuários que cadastram pelo menos um gasto fixo.

---

## 21.3 Métricas de engajamento

* Usuários ativos por dia;
* Usuários ativos por semana;
* Número médio de gastos registrados por usuário;
* Dias com pelo menos um registro;
* Taxa de retenção após 7 dias;
* Taxa de retenção após 30 dias;
* Número médio de consultas por usuário.

---

## 21.4 Métricas de qualidade

* Taxa de correção do último gasto;
* Taxa de mensagens ambíguas;
* Taxa de confirmações solicitadas;
* Taxa de falsos registros;
* Taxa de registros duplicados;
* Precisão por campo;
* Taxa de consultas respondidas corretamente;
* Taxa de mensagens não compreendidas.

---

## 21.5 Métricas de desempenho

* Latência total;
* Latência por agente;
* Latência do modelo;
* Latência do banco;
* Latência da transcrição;
* Tempo na fila;
* Tempo de envio ao canal;
* P50, P90, P95 e P99.

---

## 21.6 Métricas financeiras do produto

* Custo médio por mensagem;
* Custo médio por gasto registrado;
* Custo médio por relatório;
* Custo médio por usuário ativo;
* Custo de transcrição;
* Custo por modelo;
* Custo total mensal.

---

# 22. Estratégia de testes

## 22.1 Testes unitários com Pytest

Deverão cobrir:

* Resolução de datas;
* Rejeição de datas futuras;
* Normalização de valores;
* Normalização de categorias;
* Chaves de idempotência;
* Regras de alteração;
* Filtros por usuário;
* Cálculos de períodos;
* Cálculos semanais;
* Agregações financeiras;
* Formatação de respostas.

---

## 22.2 Testes de contrato dos agentes

Deverão validar:

* Estrutura do JSON;
* Campos obrigatórios;
* Valores permitidos;
* Tratamento de dados ausentes;
* Tratamento de múltiplos gastos;
* Tratamento de ambiguidades;
* Compatibilidade entre versões de prompts.

---

## 22.3 Conjunto de avaliação de linguagem

Deverá ser criado um dataset com mensagens como:

* “Gastei 30 no almoço”;
* “Foi 30 de almoço”;
* “30 almoço pix”;
* “Paguei trinta conto no rango”;
* “Gastei 30 no almoço e 20 no Uber”;
* “Ontem paguei 50 no mercado”;
* “Dia 10 gastei 90”;
* “Amanhã vou pagar 100”;
* “Foram 50 ou 60, não lembro”;
* “Na verdade foi 45”;
* “Quanto gastei essa semana?”;
* “Quanto deu mercado esta semana e a passada?”;
* Mensagens com erros de digitação;
* Mensagens transcritas de áudio;
* Mensagens com valores por extenso;
* Mensagens com centavos;
* Mensagens com múltiplas intenções.

O dataset deverá possuir resultado esperado para comparação automatizada.

---

## 22.4 Testes de integração

Deverão cobrir:

* Webhook → banco;
* Banco → fila;
* Fila → worker;
* Worker → LangGraph;
* LangGraph → banco;
* Banco → resposta;
* Twilio → aplicação;
* Telegram → aplicação;
* OpenRouter → aplicação;
* Serviço de áudio → aplicação.

---

## 22.5 Testes de carga com Locust

Cenários mínimos:

1. Muitos usuários enviando um gasto simultaneamente;
2. Um usuário enviando mensagens sequenciais;
3. Mensagens duplicadas;
4. Mensagens com múltiplos gastos;
5. Consultas de relatórios;
6. Entrada de áudio;
7. Lentidão do modelo;
8. Falha de worker;
9. Retry de tarefas;
10. Crescimento da fila.

### Métricas dos testes

* Throughput;
* Tempo de resposta;
* Tempo na fila;
* Taxa de erro;
* Tamanho máximo da fila;
* Uso de CPU;
* Uso de memória;
* Conexões do PostgreSQL;
* Quantidade de workers;
* Taxa de reprocessamento;
* Registros duplicados.

---

## 22.6 Testes de isolamento

Deverão validar explicitamente:

* Usuário A não consulta gastos do usuário B;
* Usuário A não altera gastos do usuário B;
* Usuário A não utiliza categorias do usuário B;
* Mensagens concorrentes não misturam contexto;
* Relatórios sempre incluem filtro de usuário;
* Cache, quando existente, utiliza chave por usuário.

---

# 23. Critérios de aceite do MVP

O MVP estará pronto para teste de 30 dias quando:

* O usuário puder iniciar uma conversa pelo WhatsApp;
* O onboarding estiver funcional;
* Gastos puderem ser registrados por texto;
* Gastos puderem ser registrados por áudio;
* Múltiplos gastos puderem ser registrados;
* Gastos forem categorizados;
* Datas passadas forem interpretadas;
* Datas futuras forem rejeitadas;
* O último gasto puder ser corrigido;
* Gastos não puderem ser excluídos pelo chat;
* Categorias puderem ser criadas;
* Categorias não puderem ser excluídas;
* Gastos fixos puderem ser criados;
* Gastos fixos puderem ser desativados;
* Os cinco últimos gastos puderem ser consultados;
* Gastos de hoje, ontem, semana e mês puderem ser consultados;
* Consultas por categoria estiverem funcionais;
* Mensagens duplicadas não gerarem gastos duplicados;
* Os dados estiverem isolados por usuário;
* Custos de execução estiverem registrados;
* O fluxo de salvar e confirmar gastos atender ao SLA de 15 segundos;
* Testes unitários e de integração essenciais estiverem aprovados;
* Testes de carga não apresentarem perda de mensagens;
* Logs permitirem rastrear uma execução completa.

---

# 24. Riscos e mitigações

## 24.1 Interpretação incorreta de valores

**Risco:** registrar R$ 17,00 em vez de R$ 70,00.

**Mitigação:**

* Confiança por campo;
* Confirmação em casos ambíguos;
* Validação de transcrição;
* Dataset de avaliação;
* Registro do texto original.

---

## 24.2 Categorias inconsistentes

**Risco:** o mesmo tipo de gasto ser classificado em categorias diferentes.

**Mitigação:**

* Categorias por usuário;
* Histórico de categorização;
* Regras determinísticas;
* Normalização de nomes;
* Feedback por correção.

---

## 24.3 Confirmações excessivas

**Risco:** o produto ficar tão trabalhoso quanto um aplicativo.

**Mitigação:**

* Confirmar apenas ambiguidade crítica;
* Medir taxa de confirmação;
* Ajustar limiares;
* Utilizar contexto e regras.

---

## 24.4 Ausência de confirmações necessárias

**Risco:** registros incorretos reduzirem a confiança.

**Mitigação:**

* Validação por campo;
* Regras para datas e valores;
* Política conservadora para áudio;
* Auditoria;
* Correção rápida do último gasto.

---

## 24.5 Mensagens fora de ordem

**Risco:** uma correção alterar o gasto errado.

**Mitigação:**

* Ordenação por usuário;
* Lock lógico;
* Sequenciamento;
* Persistência antes do processamento.

---

## 24.6 Registros duplicados

**Risco:** retries do canal criarem gastos repetidos.

**Mitigação:**

* Idempotência;
* Restrição única;
* Processamento transacional;
* Testes concorrentes.

---

## 24.7 Crescimento da fila

**Risco:** aumento do tempo de resposta acima de 15 segundos.

**Mitigação:**

* Escala horizontal de workers;
* Métrica de idade da fila;
* Priorização de registros;
* Timeout de modelos;
* Fallback;
* Redução de chamadas ao LLM.

---

## 24.8 Dependência de provedores externos

**Risco:** indisponibilidade da Twilio, Telegram, OpenRouter ou serviço de áudio.

**Mitigação:**

* Retry;
* Timeout;
* Fallback;
* Circuit breaker;
* Persistência da mensagem antes do processamento;
* Alertas.

---

## 24.9 Custo imprevisível

**Risco:** uso de modelos tornar o produto caro.

**Mitigação:**

* Medição por execução;
* Modelos diferentes por tarefa;
* Cache quando seguro;
* Regras determinísticas;
* Limite de contexto;
* Prompts curtos;
* Avaliação contínua de custo.

---

## 24.10 Exposição de dados financeiros

**Risco:** vazamento ou mistura de informações entre usuários.

**Mitigação:**

* Isolamento por usuário;
* Criptografia;
* Segredos protegidos;
* Logs sanitizados;
* Testes de segurança;
* Row-Level Security;
* Auditoria.

---

# 25. Plano de implementação sugerido

## Etapa 1 — Fundação

* Estrutura do projeto;
* Docker;
* FastAPI;
* PostgreSQL;
* Migrations;
* Modelos principais;
* Configuração de ambiente;
* Logs estruturados;
* Health checks.

## Etapa 2 — Mensageria e fila

* Webhook do Telegram;
* Persistência de mensagens;
* Fila no PostgreSQL;
* Worker;
* Idempotência;
* Retry;
* Ordenação por usuário.

## Etapa 3 — Registro de gastos

* LangGraph;
* Roteador;
* Registrador;
* Extração estruturada;
* Validação;
* Persistência;
* Confirmação;
* Múltiplos gastos.

## Etapa 4 — Categorias e correções

* Categorias padrão;
* Criação de categorias;
* Categorização;
* Correção do último gasto;
* Auditoria.

## Etapa 5 — Relatórios

* Consultas fixas;
* Períodos;
* Categorias;
* Últimos gastos;
* Agregações;
* Respostas textuais.

## Etapa 6 — Gastos fixos

* Cadastro;
* Listagem;
* Desativação;
* Geração de lançamentos, conforme decisão.

## Etapa 7 — Áudio

* Recebimento;
* Transcrição;
* Confiança;
* Tratamento de falhas;
* Testes.

## Etapa 8 — WhatsApp

* Integração Twilio;
* Validação do webhook;
* Templates quando necessários;
* Tratamento de erros;
* Testes ponta a ponta.

## Etapa 9 — Qualidade e escala

* Pytest;
* Dataset de avaliação;
* Locust;
* Testes de isolamento;
* Métricas;
* Custos;
* Alertas.

## Etapa 10 — Teste de 30 dias

* Ativação do usuário;
* Monitoramento diário;
* Registro de problemas;
* Comparação com extratos;
* Avaliação do critério de 85%.

---

# 26. Decisões já definidas

* O canal principal será WhatsApp.
* O Telegram será utilizado em desenvolvimento e testes.
* O registro de gasto deverá ser salvo e confirmado em até 15 segundos.
* O tempo máximo geral de resposta será de 25 segundos.
* O produto aceitará texto e áudio.
* O chat poderá corrigir apenas o último gasto.
* O chat não poderá excluir gastos.
* O chat não poderá excluir categorias.
* O chat poderá cadastrar e desativar gastos fixos.
* O MVP utilizará PostgreSQL para dados e fila.
* O sistema utilizará LangChain e LangGraph v1.
* O acesso a modelos ocorrerá por meio do OpenRouter.
* O backend será desenvolvido com FastAPI.
* A aplicação será contenerizada com Docker.
* Pytest e Locust serão utilizados para testes.
* O MVP deverá ser preparado para isolamento de usuários e escala.

---

# 27. Pontos em aberto

## 27.1 Relatório financeiro principal

Ainda não foi definido qual relatório deverá receber maior destaque no MVP.

Até que essa decisão seja tomada, o produto deverá priorizar:

1. Gastos de hoje;
2. Gastos da semana;
3. Gastos do mês;
4. Gastos por categoria;
5. Últimos cinco gastos.

A definição do relatório principal poderá considerar qual pergunta é mais frequente durante o teste de 30 dias.

---

## 27.2 Geração de lançamentos de gastos fixos

É necessário decidir se o gasto fixo:

* Será lançado automaticamente no dia configurado;
* Será apenas sugerido ao usuário;
* Será lançado após confirmação;
* Será registrado somente como regra, sem lançamento automático no MVP.

Recomendação:

> Gerar automaticamente o lançamento e enviar uma notificação informativa, permitindo correção caso o valor tenha mudado.

---

## 27.3 Fuso horário

O sistema deverá definir como obter o fuso horário do usuário.

Possibilidades:

* Fuso padrão da operação;
* Definição durante onboarding;
* Inferência pelo número de telefone;
* Configuração manual.

Recomendação:

> Solicitar ou confirmar o fuso durante o onboarding e utilizar um valor padrão para usuários brasileiros.

---

## 27.4 Moeda

O MVP deverá definir se trabalhará exclusivamente com real brasileiro.

Recomendação:

> Utilizar BRL como moeda padrão no MVP, mantendo o campo de moeda no modelo de dados para evolução futura.

---

## 27.5 Retenção de áudio

É necessário definir:

* Se o áudio original será armazenado;
* Por quanto tempo;
* Quem poderá acessá-lo;
* Se será mantida apenas a transcrição.

Recomendação:

> Manter o áudio apenas pelo tempo necessário para processamento e depuração controlada, preservando a transcrição e os metadados necessários.

---

## 27.6 Provedor de transcrição

O provedor de transcrição ainda deverá ser selecionado com base em:

* Custo;
* Latência;
* Qualidade em português brasileiro;
* Privacidade;
* Facilidade de integração;
* Limites de duração.

---

## 27.7 Taxa de confiança

Os limites de confiança deverão ser calibrados com testes reais.

A política inicial sugerida não deverá ser considerada definitiva.

---

# 28. Definição de pronto

Uma funcionalidade será considerada pronta quando:

* Possuir critérios de aceite implementados;
* Possuir testes unitários relevantes;
* Possuir teste de integração quando aplicável;
* Gerar logs rastreáveis;
* Registrar custo quando utilizar modelo;
* Respeitar isolamento de usuário;
* Tratar erros;
* Possuir documentação técnica mínima;
* Não introduzir registros duplicados;
* Ser validada no Telegram;
* Ser validada no WhatsApp quando fizer parte do fluxo de produção.

---

# 29. Hipótese central do produto

A hipótese principal é:

> Se o usuário puder registrar um gasto enviando uma mensagem natural pelo WhatsApp e receber uma confirmação confiável em poucos segundos, ele terá menos atrito e maior consistência do que teria utilizando planilhas ou aplicativos financeiros tradicionais.

Essa hipótese será validada quando o usuário mantiver o uso por 30 dias e registrar pelo menos 85% de seus gastos.

---

# 30. Resultado esperado do MVP

Ao final do MVP, o usuário deverá conseguir utilizar o WhatsApp como sua principal interface de controle financeiro.

O sistema deverá ser capaz de transformar mensagens naturais em registros financeiros estruturados, armazenar esses dados com segurança e responder perguntas básicas sobre hábitos de consumo.

O sucesso do produto não será medido apenas pela capacidade técnica de registrar gastos, mas principalmente pela capacidade de manter o usuário engajado durante todo o mês com o menor esforço possível.
