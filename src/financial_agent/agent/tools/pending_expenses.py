"""Operações determinísticas sobre rascunhos pendentes.

Estas funções valem tanto para o rascunho de gasto pontual quanto para o de
gasto recorrente: o que elas precisam saber de um rascunho está declarado no
protocolo :class:`PendingDraft`, e nada além disso. Manter o módulo estrutural
(sem conhecer os modelos concretos) é o que evita duplicar TTL, metadados e
formatação de perguntas em cada fluxo novo.
"""

from collections.abc import Container, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Protocol, Self, TypeVar
from uuid import uuid4

PENDING_EXPENSE_TTL = timedelta(hours=24)


class PendingDraft(Protocol):
    """O mínimo que um rascunho pendente precisa expor para ser gerenciado aqui."""

    @property
    def id(self) -> str | None: ...

    @property
    def created_at(self) -> datetime | None: ...

    @property
    def clarification_message(self) -> str: ...

    @property
    def missing_fields(self) -> Sequence[str]: ...

    def model_copy(
        self, *, update: Mapping[str, Any] | None = None, deep: bool = False
    ) -> Self: ...


class ModelProposal(Protocol):
    """Proposta estruturada devolvida pelo LLM para completar um rascunho."""

    def model_dump(self) -> dict[str, Any]: ...


DraftT = TypeVar("DraftT", bound=PendingDraft)
ProposalT = TypeVar("ProposalT", bound=ModelProposal)


def enforce_missing_field_dependencies(pending: DraftT) -> DraftT:
    """Corrige `missing_fields` para refletir o que pode ser considerado confirmado.

    O LLM às vezes marca só `description` como faltando, mas deixa `category_hint`
    em branco sem marcar `category` como faltando também. Categoria de um item
    desconhecido nunca é segura — ela depende do próprio item. Sem essa correção,
    o guard determinístico (:func:`accept_if_confirmed_fields_untouched`) trata
    esse branco como "confirmado: sem categoria" e trava a pendência para sempre,
    mesmo depois da descrição ser respondida.
    """
    if (
        "description" in pending.missing_fields
        and "category" not in pending.missing_fields
    ):
        return pending.model_copy(
            update={
                "missing_fields": [*pending.missing_fields, "category"],
                "category_hint": None,
            }
        )
    return pending


def assign_pending_metadata(
    pending_expenses: list[DraftT], now: datetime
) -> list[DraftT]:
    """Cria identificadores estáveis para os rascunhos desta extração."""
    return [
        enforce_missing_field_dependencies(pending).model_copy(
            update={
                "id": uuid4().hex,
                "created_at": now,
            }
        )
        for pending in pending_expenses
    ]


def keep_pending_metadata(pending: DraftT, now: datetime) -> DraftT:
    """Garante metadados para rascunhos produzidos fora da extração principal."""
    return enforce_missing_field_dependencies(pending).model_copy(
        update={
            "id": pending.id or uuid4().hex,
            "created_at": pending.created_at or now,
        }
    )


def split_expired_pending_expenses(
    pending_expenses: list[DraftT], now: datetime
) -> tuple[list[DraftT], list[DraftT]]:
    """Separa pendências ativas das que ultrapassaram a janela de 24 horas."""
    expiration_cutoff = now - PENDING_EXPENSE_TTL
    active: list[DraftT] = []
    expired: list[DraftT] = []

    for pending in pending_expenses:
        if pending.created_at is not None and pending.created_at <= expiration_cutoff:
            expired.append(pending)
        else:
            active.append(pending)

    return active, expired


def format_pending_questions(pending_expenses: Sequence[PendingDraft]) -> str:
    """Agrupa as perguntas sem transformar rascunhos em gastos confirmados."""
    return "\n".join(pending.clarification_message for pending in pending_expenses)


def format_expired_pending_message() -> str:
    """Explica como retomar uma pendência que não existe mais no checkpoint."""
    return (
        "Essa pendência expirou após 24 horas. Envie novamente o gasto completo, "
        "com descrição e valor, para eu registrar com segurança."
    )


def accept_if_confirmed_fields_untouched(
    proposal: ProposalT,
    confirmed_value_by_attribute: Mapping[str, object],
    missing_field_name_by_attribute: Mapping[str, str],
    still_missing_fields: Container[str],
) -> ProposalT | None:
    """Devolve a proposta só se ela não alterou nenhum campo já confirmado.

    Um campo é considerado confirmado quando o nome com que ele aparece em
    ``missing_fields`` não está mais lá. Reescrever um campo confirmado é o
    sintoma clássico de o modelo ter "recomeçado" a extração a partir de uma
    resposta curta — e é exatamente o que não pode virar gasto persistido.

    Args:
        proposal: Extração proposta pelo LLM para completar o rascunho.
        confirmed_value_by_attribute: Valor que o rascunho já tem, por atributo
            da proposta.
        missing_field_name_by_attribute: Nome do atributo dentro de
            ``missing_fields``, que nem sempre é igual ao nome do atributo
            (``amount_raw`` aparece como ``amount``).
        still_missing_fields: Campos que o rascunho ainda espera receber.

    Returns:
        A própria proposta quando nada confirmado mudou; ``None`` caso contrário.
    """
    proposed_values = proposal.model_dump()

    for attribute, confirmed_value in confirmed_value_by_attribute.items():
        is_still_confirmed = (
            missing_field_name_by_attribute[attribute] not in still_missing_fields
        )
        if is_still_confirmed and proposed_values[attribute] != confirmed_value:
            return None

    return proposal
