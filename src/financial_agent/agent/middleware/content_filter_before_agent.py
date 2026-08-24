"""Guard determinístico para conteúdo não confiável antes de qualquer LLM.

O filtro inspeciona somente a última ``HumanMessage`` da execução atual. Ele
não tenta interpretar intenção nem reescrever o texto: apenas identifica
tentativas explícitas de substituir instruções de sistema ou revelá-las.
"""

from __future__ import annotations

import re
import unicodedata
from base64 import b64decode
from typing import Literal

from langchain_core.messages import HumanMessage

from financial_agent.agent.state_graph import GraphState

InputSafety = Literal["safe", "unsafe"]

_BANNED_PATTERNS = (
    re.compile(
        r"\b(?:ignore|desconsidere|esqueca|viole|quebre)\b"
        r"(?:\s+\w+){0,3}\s+\b(?:regras|instrucoes)\b"
        r"(?:\s+anteriores)?\b"
    ),
    re.compile(
        r"\b(?:ignore|disregard|forget)\b"
        r"(?:\s+\w+){0,3}\s+\b(?:instructions?|rules?)\b"
    ),
    re.compile(
        r"\b(?:revele|mostre|exiba|reveal|show|display)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:system\s+prompt|system\s+config|"
        r"developer\s+message|prompt\s+do\s+sistema|"
        r"configuracoes\s+do\s+sistema|instrucoes\s+do\s+sistema)\b"
    ),
    re.compile(
        r"\b(?:(?:system|sistema|developer|desenvolvedor)\s+override|"
        r"override\s+(?:system|sistema|developer|desenvolvedor))\b"
    ),
    re.compile(
        r"\b(?:you\s+are\s+now|voce\s+(?:e|agora\s+e)|"
        r"a\s+partir\s+de\s+agora\s+voce\s+e)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:developer|desenvolvedor|admin|"
        r"jailbreak|dan)\s+(?:mode|modo)\b"
    ),
    re.compile(
        r"\b(?:bypass|contorne|burle|desative)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:safety|seguranca|guardrails?|"
        r"filt(?:er|ros?))\b"
    ),
    re.compile(
        r"\b(?:repeat|print|output|show|display|give|tell|repita|imprima|"
        r"forneca|diga)\b(?:\s+\w+){0,5}\s+"
        r"\b(?:(?:all\s+)?(?:previous|prior|above|initial|hidden|your|"
        r"anteriores|acima|iniciais|ocultas|suas)\s+"
        r"(?:instructions?|instrucoes|prompts?|messages?|mensagens?)|"
        r"(?:all\s+)?(?:instructions?|instrucoes|prompts?|messages?|"
        r"mensagens?)\s+(?:above|prior|anteriores|acima)|"
        r"(?:your\s+)?(?:system\s+prompt|developer\s+message))\b"
    ),
    re.compile(
        r"\b(?:act\s+as|pretend\s+(?:to\s+be|you\s+are)|you\s+are|"
        r"finja\s+ser)\b"
        r"(?:\s+\w+){0,4}\s+\b(?:system|sistema|developer|"
        r"desenvolvedor|admin|dan|jailbreak)\b"
    ),
    re.compile(
        r"\b(?:do\s+not\s+follow|nao\s+siga)\b(?:\s+\w+){0,3}\s+"
        r"\b(?:previous|prior|anteriores)\s+"
        r"(?:instructions?|instrucoes)\b"
    ),
)

_TYPOGLYCEMIA_TARGETS = (
    "ignore",
    "disregard",
    "forget",
    "override",
    "reveal",
    "bypass",
    "desconsidere",
    "esqueca",
    "revele",
    "contorne",
)
_BASE64_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_+/=-])[A-Za-z0-9_+/-]{16,}={0,2}(?![A-Za-z0-9_+/=-])"
)
_HEX_TOKEN = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}[\s:-]?){8,}(?![0-9A-Fa-f])")
_SPACED_CHARACTERS = re.compile(r"(?<!\w)(?:[a-z]\s+){2,}[a-z](?!\w)")
_WORD = re.compile(r"\b[a-z]+\b")
_MAX_ENCODED_TOKEN_LENGTH = 16_384
_MAX_ENCODED_TOKENS = 10


def _text_content(content: object) -> str:
    """Extrai texto de conteúdo simples ou de blocos de mensagem."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in content
            if isinstance(block, str | dict)
        )
    return str(content)


def _normalize_for_match(text: str) -> str:
    """Normaliza caixa, acentos e espaços para a comparação determinística."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[\W_]+", " ", without_accents).strip().casefold()


def _casefold_without_accents(text: str) -> str:
    """Preserva limites de palavras não ASCII ao remover somente acentos."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(
        char for char in decomposed if not unicodedata.combining(char)
    ).casefold()


def _collapse_character_spacing(text: str) -> str:
    """Remove espaços inseridos entre caracteres para evadir filtros."""
    return _SPACED_CHARACTERS.sub(lambda match: match.group().replace(" ", ""), text)


def _is_typoglycemia_variant(word: str, target: str) -> bool:
    """Identifica anagramas internos, como ``ignroe`` para ``ignore``."""
    return (
        len(word) == len(target)
        and len(word) >= 4
        and word != target
        and word[0] == target[0]
        and word[-1] == target[-1]
        and sorted(word[1:-1]) == sorted(target[1:-1])
    )


def _normalize_typoglycemia(text: str) -> str:
    """Troca variantes embaralhadas por palavras usadas nos padrões."""
    targets = _TYPOGLYCEMIA_TARGETS

    def replace(word_match: re.Match[str]) -> str:
        word = word_match.group()
        return next(
            (target for target in targets if _is_typoglycemia_variant(word, target)),
            word,
        )

    return _WORD.sub(replace, text)


def _decoded_candidates(text: str) -> list[str]:
    """Decodifica, de forma limitada, Base64 e hex que possam ocultar texto."""
    decoded: list[str] = []
    for token_index, match in enumerate(_BASE64_TOKEN.finditer(text)):
        if token_index >= _MAX_ENCODED_TOKENS:
            break
        token = match.group()
        if len(token) > _MAX_ENCODED_TOKEN_LENGTH:
            continue
        try:
            normalized_token = token.replace("-", "+").replace("_", "/")
            padded_token = normalized_token + "=" * (-len(normalized_token) % 4)
            value = b64decode(padded_token, validate=True).decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        if value.isprintable() or any(char.isspace() for char in value):
            decoded.append(value)

    for token_index, match in enumerate(_HEX_TOKEN.finditer(text)):
        if token_index >= _MAX_ENCODED_TOKENS:
            break
        token = match.group()
        if len(token) > _MAX_ENCODED_TOKEN_LENGTH:
            continue
        compact = re.sub(r"[\s:-]", "", token)
        try:
            value = bytes.fromhex(compact).decode("utf-8")
        except ValueError:
            continue
        if value.isprintable() or any(char.isspace() for char in value):
            decoded.append(value)
    return decoded


def _matches_injection_pattern(text: str) -> bool:
    """Aplica regex também às formas normalizadas de evasão conhecidas."""
    normalized = _normalize_for_match(text)
    candidates = (
        _casefold_without_accents(text),
        normalized,
        _collapse_character_spacing(normalized),
    )
    candidates += tuple(_normalize_typoglycemia(candidate) for candidate in candidates)
    candidates += tuple(
        candidate
        for value in _decoded_candidates(text)
        for candidate in (
            _casefold_without_accents(value),
            re.sub(r"[^a-z0-9\s]", " ", _casefold_without_accents(value)),
            _normalize_typoglycemia(
                _collapse_character_spacing(_normalize_for_match(value))
            ),
        )
    )
    return any(
        pattern.search(candidate)
        for candidate in candidates
        for pattern in _BANNED_PATTERNS
    )


def ensure_input_content_safe(state: GraphState) -> InputSafety:
    """Classifica a mensagem atual como segura ou insegura.

    Mensagens que não são humanas não são inspecionadas e seguem o fluxo
    normal. Isso evita tratar mensagens do sistema, respostas do assistente e
    eventos internos como entrada não confiável do usuário.
    """
    messages = state.get("messages", [])
    if not messages:
        return "safe"

    last_message = messages[-1]
    if not isinstance(last_message, HumanMessage):
        return "safe"

    text = _text_content(last_message.content)
    if _matches_injection_pattern(text):
        return "unsafe"
    return "safe"
