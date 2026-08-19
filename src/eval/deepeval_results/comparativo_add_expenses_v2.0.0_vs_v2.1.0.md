# Relatório comparativo — ADD_EXPENSES v2.0.0 × v2.1.0

**Fontes analisadas:**

- Prompt v2.0.0 e avaliação `20260818_095506`.
- Prompt v2.1.0 e avaliação `20260818_110602`.
- 46 cenários idênticos em cada execução.

> Os arquivos de avaliação não registram explicitamente a versão do prompt usada. O pareamento acima segue a sequência informada e é corroborado pelas mudanças observadas nos resultados (especialmente `installments: null`).

## Resumo executivo

A v2.1.0 melhorou o resultado líquido: **39/46 aprovações (84,78%)**, contra **37/46 (80,43%)** na v2.0.0 — dois casos a mais aprovados e sete falhas, contra nove. A validade sintática permaneceu perfeita: **100% de JSON correto** nas duas execuções.

O principal acerto foi tornar `installments: null` obrigatório quando não há parcelamento; isso eliminou quatro falhas. Contudo, a nova regra de exclusão de assinaturas conflita com a expectativa dos testes e introduziu uma regressão para plano de saúde. Permanecem falhas de categorização e, de maneira especialmente preocupante, o aporte no Tesouro continua sendo omitido apesar de agora existir instrução e exemplo explícitos para ele.

| Indicador | v2.0.0 | v2.1.0 | Variação |
|---|---:|---:|---:|
| Casos aprovados (Field Correctness) | 37/46 | 39/46 | +2 |
| Taxa de aprovação | 80,43% | 84,78% | +4,35 p.p. |
| Falhas | 9 | 7 | −2 |
| Nota média do avaliador | 0,83 | 0,83 | sem mudança visível (arredondada) |
| JSON válido | 46/46 | 46/46 | estável |

## Alterações relevantes no prompt v2.1.0

1. Passou a aceitar aportes e aplicações como saída orçamentária, incluindo orientação de categoria e um exemplo para Tesouro.
2. Passou a excluir assinaturas e serviços recorrentes deste fluxo.
3. Tornou explícito que gasto sem parcelamento deve usar `installments: null`, nunca `1`.
4. Adicionou exemplos para gíria (`pila`) e múltiplos gastos com meios de pagamento diferentes.
5. Reorganizou e simplificou instruções já existentes, sem alterar materialmente o contrato de data, descrição ou categorização geral.

## Casos corrigidos na v2.1.0

| Caso | Erro na v2.0.0 | Resultado na v2.1.0 | Relação com a mudança |
|---|---|---|---|
| `gasto-conta-luz` | `installments: 1` em vez de `null` | Aprovado | Correção direta da nova regra de parcelas. |
| `gasto-giria-pila` | `installments: 1` em vez de `null` | Aprovado | Correção direta; exemplo adicional reforça o padrão. |
| `gasto-multiplo-tres-itens-metodos-diferentes` | `installments: 1` nos três itens | Aprovado | Correção direta; novo exemplo é praticamente o cenário avaliado. |
| `gasto-formato-milhar-br` | `1500` em vez de `1500,00` | Aprovado | Melhora observada, mas não há regra nova explícita para preservar `,00`; pode ser sensível ao modelo. |
| `gasto-parcela-sem-numero-nem-valor` | Mensagem de esclarecimento avaliada abaixo do limiar | Aprovado | Melhorou a formulação, embora sem exemplo específico novo. |

## Falhas persistentes

| Caso | Comportamento nas duas versões | Diagnóstico | Prioridade |
|---|---|---|---:|
| `gasto-parcelado-valor-da-parcela` | “compra ... no shopping” categorizada como `Lazer e entretenimento`; esperado `Compras` | A categoria do local (“shopping”) está sobrepondo a natureza genérica da compra. Não há regra de desempate. | P2 |
| `gasto-pix` | “churrasco” categorizado como `Lazer e entretenimento`; esperado `Alimentação` | Caso ambíguo, mas sem regra que priorize alimento/refeição sobre evento social. | P2 |
| `gasto-streaming` | Nenhuma despesa retornada (na v2.1.0, também sem `needs_clarification`) | Há conflito entre o comportamento desejado no teste e a nova regra do prompt; ver seção seguinte. | P1 |
| `gasto-investimento` | “Apliquei 500 reais no Tesouro” continua retornando `expenses: []` | É uma não-obediência a uma instrução repetida três vezes na v2.1.0 (classificação, regra de categoria e exemplo). Pode indicar prompt efetivo desatualizado, regra externa concorrente ou fragilidade do modelo. | P0 |

## Regressões introduzidas na v2.1.0

| Caso | v2.0.0 | v2.1.0 | Causa provável |
|---|---|---|---|
| `gasto-plano-saude` | Registrava `450` em `Saúde e bem-estar` | Bloqueia como assinatura recorrente e pede confirmação | A nova classe “assinatura recorrente” é ampla demais: “mensalidade” e “plano de saúde” acionam a exclusão. |
| `gasto-familia` | Mantinha “creche para o meu filho” | Reduz a descrição para “creche” | Perda de fidelidade textual; o prompt diz “o mais próximo possível”, mas não proíbe remover complementos semânticos. |
| `gasto-valor-sem-centavos-hifen` | Registra aluguel normalmente | Cria `date_hint` de hoje e pede esclarecimento por “esse mês” | O modelo passou a tratar uma referência mensal como data ambígua. O contrato esperado é `date_hint: null` e nenhum esclarecimento. |

## Conflito de especificação: assinaturas

O teste `gasto-streaming` espera registrar “Assinatura do Netflix de 39,90” em `Assinaturas e Streaming`. A v2.1.0, porém, determina expressamente que assinaturas recorrentes **não devem ser registradas**. Portanto, esse teste não pode passar sem alterar uma das duas fontes de verdade.

Há duas decisões possíveis:

1. **Assinaturas devem ser despesas neste módulo:** remover a exclusão, registrar Netflix e tratar mensalidades informadas como gastos pontuais. Essa opção também evita a regressão de plano de saúde.
2. **Assinaturas realmente estão fora do módulo:** manter a regra e atualizar o teste para esperar `expenses: []`, `needs_clarification: true` e uma mensagem explicativa. Nesse caso, o resultado atual ainda está incorreto porque retorna `needs_clarification: false` e não explica a recusa.

Pelo conjunto de expectativas atual — que inclui Netflix e plano de saúde como despesas — a primeira opção é a consistente com a suíte.

## Recomendações para uma próxima versão

1. **Resolver a decisão de produto sobre assinaturas antes de novo ajuste.** Se a suíte for o contrato, remova a exclusão de assinaturas e acrescente exemplos de Netflix e plano de saúde como lançamentos pontuais.
2. **Resolvido em 18/08:** a falha de investimento estava no roteador anterior ao `ADD_EXPENSES`, que não reconhecia aportes. O `ROUTER_SYSTEM_PROMPT` v1.2.0 agora direciona Tesouro, poupança e investimentos para `add_new_expenses`; uma chamada direta validou o roteamento e a extração de `Apliquei 500 reais no Tesouro`.
3. **Adicionar regra de categorização por precedência:** “compra no shopping” sem item de lazer → `Compras`; “churrasco”, refeição e alimentos → `Alimentação`, salvo indicação explícita de ingresso/evento.
4. **Preservar qualificadores úteis na descrição.** Instruir: não remover destinatário, finalidade ou vínculo familiar quando eles distinguem o gasto (por exemplo, `creche para o meu filho`).
5. **Tratar referências de período sem dia como não-datas.** “Este mês” deve manter `date_hint: null`, não exigir confirmação; apenas datas explícitas, relativas resolvíveis ou futuras devem influenciar a decisão.
6. **Adicionar esses sete cenários como regressão obrigatória** à avaliação de qualquer nova versão, incluindo os dois lados da decisão de assinaturas após ela ser definida.

## Leitura final

A v2.1.0 resolveu de forma efetiva o defeito sistêmico de parcelas e elevou a taxa de aprovação. Ainda assim, ela mistura uma alteração de produto (excluir assinaturas) com correções de extração e não consolidou o caso de investimentos, que era o objetivo mais explícito da mudança. A próxima iteração deve ser curta e orientada por contrato: decidir assinaturas, validar o caminho de investimento e acrescentar três regras pontuais para categorização, descrição e referências mensais.
