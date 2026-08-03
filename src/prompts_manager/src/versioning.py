"""Utilitários de parsing, formatação e incremento de versão semântica para versionamento de prompts."""

import re


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Converte uma string de versão em uma tupla ``(major, minor, patch)``.

    Aceita ``"v1.2.3"`` ou ``"1.2.3"``. Lança ``ValueError``
    se a string não corresponder ao padrão ``X.Y.Z`` esperado.
    """
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def format_version(major: int, minor: int, patch: int) -> str:
    """Formata uma tupla ``(major, minor, patch)`` em uma string de versão.

    Exemplo: ``"v1.2.3"``.
    """
    return f"v{major}.{minor}.{patch}"


def get_next_version(existing_versions: list[str], change_type: str = "patch") -> str:
    """Calcula a próxima versão com base nas versões existentes e no tipo de incremento.

    Se nenhuma versão válida for encontrada, retorna ``"v1.0.0"``.

    Args:
        existing_versions: Lista de strings de versão já em uso.
        change_type: Um de ``"major"``, ``"minor"`` ou ``"patch"`` (padrão).

    Returns:
        A string da próxima versão.
    """
    if not existing_versions:
        return "v1.0.0"

    versions = []
    for v in existing_versions:
        try:
            parsed = parse_version(v)
            versions.append(parsed)
        except ValueError:
            continue

    if not versions:
        return "v1.0.0"

    latest = max(versions, key=lambda x: (x[0], x[1], x[2]))
    major, minor, patch = latest

    if change_type == "major":
        return format_version(major + 1, 0, 0)
    elif change_type == "minor":
        return format_version(major, minor + 1, 0)
    else:
        return format_version(major, minor, patch + 1)
