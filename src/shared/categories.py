"""Categorias globais — fonte única da verdade.

Este módulo define todas as categorias globais padrão do sistema.
Qualquer alteração (adição, remoção, renomeação) deve ser feita
exclusivamente aqui. Todos os consumidores (agente, ferramentas,
sincronização com banco de dados) referenciam este módulo.

Uso:
    from financial_agent.shared.categories import GLOBAL_CATEGORIES, Category

    for cat in GLOBAL_CATEGORIES:
        print(cat.name, cat.description)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """Representação imutável de uma categoria."""

    name: str
    normalized_name: str
    description: str
    is_default: bool = True
    is_active: bool = True


GLOBAL_CATEGORIES: tuple[Category, ...] = (
    Category(
        name="Alimentação",
        normalized_name="alimentacao",
        description="Restaurantes, lanchonetes, cafés, delivery, padaria e feira",
    ),
    Category(
        name="Moradia",
        normalized_name="moradia",
        description="Aluguel, financiamento, condomínio, manutenção e reformas",
    ),
    Category(
        name="Transporte",
        normalized_name="transporte",
        description=(
            "Combustível, transporte público, aplicativos de corrida "
            "(e.g: Uber, 99, Itacar), estacionamento e manutenção do veículo"
        ),
    ),
    Category(
        name="Contas e serviços essenciais",
        normalized_name="contas_e_servicos_essenciais",
        description="Energia, água, gás, telefone, internet e TV",
    ),
    Category(
        name="Saúde e bem-estar",
        normalized_name="saude_e_bem-estar",
        description="Plano de saúde, consultas, exames, farmácia, dentista e academia",
    ),
    Category(
        name="Compras",
        normalized_name="compras",
        description=(
            "Eletrônicos, móveis, utensílios domésticos, "
            "decoração e comércio eletrônico"
        ),
    ),
    Category(
        name="Lazer e entretenimento",
        normalized_name="lazer_e_entretenimento",
        description="Cinema, eventos, jogos, hobbies, bares e atividades culturais",
    ),
    Category(
        name="Educação",
        normalized_name="educacao",
        description="Escola, faculdade, cursos, livros, mensalidades e materiais",
    ),
    Category(
        name="Viagens",
        normalized_name="viagens",
        description=(
            "Passagens, hospedagem, turismo, aluguel de veículos "
            "e alimentação em viagem"
        ),
    ),
    Category(
        name="Dívidas e financiamentos",
        normalized_name="dividas_e_financiamentos",
        description=(
            "Empréstimos, financiamento de veículo, crédito pessoal e parcelamentos"
        ),
    ),
    Category(
        name="Poupança e investimentos",
        normalized_name="poupanca_e_investimentos",
        description="Reserva de emergência, previdência, renda fixa, fundos e ações",
    ),
    Category(
        name="Seguros",
        normalized_name="seguros",
        description="Seguro residencial, automóvel, vida, viagem e saúde",
    ),
    Category(
        name="Cuidados pessoais",
        normalized_name="cuidados_pessoais",
        description="Cabeleireiro, cosméticos, estética, higiene",
    ),
    Category(
        name="Impostos, taxas e tarifas",
        normalized_name="impostos_taxas_e_tarifas",
        description="IPTU, IPVA, Imposto de Renda, tarifas bancárias, juros e multas",
    ),
    Category(
        name="Família e filhos",
        normalized_name="familia_e_filhos",
        description=(
            "Creche, babá, atividades infantis, mesada e despesas com dependentes"
        ),
    ),
    Category(
        name="Supermercado",
        normalized_name="supermercado",
        description=(
            "Compras de supermercado, hortifrúti, açougue, "
            "padaria e produtos de limpeza doméstica"
        ),
    ),
    Category(
        name="Roupas e acessórios",
        normalized_name="roupas_e_acessorios",
        description=(
            "Vestuário, calçados, bolsas, joias, bijuterias e acessórios pessoais"
        ),
    ),
    Category(
        name="Pets",
        normalized_name="pets",
        description=(
            "Ração, veterinário, banho, tosa, "
            "medicamentos e acessórios para animais de estimação"
        ),
    ),
    Category(
        name="Assinaturas e Streaming",
        normalized_name="assinaturas_e_streaming",
        description=(
            "Netflix, Spotify, Amazon Prime, Disney+, "
            "HBO Max e outras assinaturas digitais"
        ),
    ),
    Category(
        name="Outros gastos",
        normalized_name="outros_gastos",
        description="Despesas diversas que não se enquadram nas demais categorias",
    ),
)
