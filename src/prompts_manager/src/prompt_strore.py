"""Armazenamento de prompts em arquivos com versionamento semântico.

Os prompts são armazenados como arquivos JSON em uma estrutura de diretórios
organizada por nome. Cada diretório de prompt contém um arquivo JSON por
versão, e um arquivo ``metadata.json`` na raiz rastreia qual versão está
ativa para cada prompt.
"""

import fcntl
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from prompts_manager.config import settings
from prompts_manager.src import versioning

PROMPTS_DIR = Path(settings.prompt_dir)
METADATA_FILE = PROMPTS_DIR / "metadata.json"
_VALID_PROMPT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
MAX_PROMPT_SIZE = settings.max_prompt_size


# ---- UTIL ----
def ensure_prompts_dir():
    """Cria o diretório de prompts e um arquivo de metadados vazio se não existirem."""
    PROMPTS_DIR.mkdir(exist_ok=True)
    if not METADATA_FILE.exists():
        with open(METADATA_FILE, "w") as file:
            json.dump({"active_versions": {}}, file, indent=2, ensure_ascii=False)


# ---- METADATA ----
def load_metadata() -> dict:
    """Carrega e retorna o dicionário de metadados do ``metadata.json``.

    Cria o arquivo com a estrutura padrão se ele não existir.
    """
    ensure_prompts_dir()

    if not METADATA_FILE.exists():
        return {"active_versions": {}}
    with open(METADATA_FILE) as file:
        return json.load(file)


def save_metadata(metadata: dict):
    """Persiste o dicionário de metadados no ``metadata.json`` atomicamente.

    Adquire um lock exclusivo para evitar condições de corrida entre
    ciclos concorrentes de leitura-modificação-escrita.
    """
    ensure_prompts_dir()
    with open(METADATA_FILE, "r+") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        file.seek(0)
        json.dump(metadata, file, indent=2, ensure_ascii=False)
        file.truncate()
        fcntl.flock(file, fcntl.LOCK_UN)


# ---- PROMPTS
def get_prompt_dir(prompt_name: str) -> Path:
    """Retorna o caminho do diretório para um dado nome de prompt.

    Lança ValueError se o nome contiver caracteres inválidos ou
    resolver para fora do diretório de prompts.
    """
    if not _VALID_PROMPT_NAME.match(prompt_name):
        raise ValueError(
            f"Invalid prompt name: '{prompt_name}'. "
            "Use only letters, numbers, hyphens, and underscores (max 64 chars)."
        )
    resolved = (PROMPTS_DIR / prompt_name).resolve()
    if not str(resolved).startswith(str(PROMPTS_DIR.resolve())):
        raise ValueError(f"Path traversal blocked for prompt: {prompt_name}")
    return resolved


def list_prompts() -> list[str]:
    """Retorna uma lista com todos os nomes de prompts.

    Subdiretórios dentro da raiz de prompts, excluindo ``.git``.
    """
    ensure_prompts_dir()

    if not PROMPTS_DIR:
        return []

    return [d.name for d in PROMPTS_DIR.iterdir() if d.is_dir() and d.name != ".git"]


def list_versions(prompt_name: str) -> list[str]:
    """Retorna as versões disponíveis de um prompt, da mais antiga para a mais nova.

    Arquivos JSON cujo nome é ``"metadatajson"`` (sem ponto) são excluídos.
    """
    prompt_dir = get_prompt_dir(prompt_name)

    if not prompt_dir.exists():
        return []
    versions = []

    for file in prompt_dir.glob("*.json"):
        if file.name != "metadatajson":
            versions.append(file.stem)

    try:
        return sorted(versions, key=lambda v: versioning.parse_version(v))
    except ValueError:
        return sorted(versions)


def load_prompt_specific_version(
    prompt_name: str, version: str | None = None
) -> dict | None:
    """Carrega e retorna os dados JSON de uma versão específica do prompt.

    Se nenhuma versão for informada, usa a versão ativa dos metadados.
    Recorre à versão mais recente disponível se não houver versão ativa.
    Retorna ``None`` se o prompt ou a versão não existir.
    """
    ensure_prompts_dir()

    if version is None:
        metadata = load_metadata()
        version = metadata["active_versions"].get(prompt_name)

        if not version:
            versions = list_versions(prompt_name)
            if not versions:
                return None
            version = versions[-1]

    version_file = get_prompt_dir(prompt_name) / f"{version}.json"

    if not version_file.exists():
        return None

    with open(version_file) as file:
        return json.load(file)


def create_prompt_version(
    prompt_name: str,
    prompt_content: str,
    model: str,
    owner: str,
    change_note: str,
    change_type: str = "patch",
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> str:
    """Cria uma nova versão de um prompt e a define como versão ativa.

    A versão ativa anterior é automaticamente marcada como deprecated.
    Retorna a string da versão recém-criada.
    """
    ensure_prompts_dir()

    prompt_dir = get_prompt_dir(prompt_name)
    prompt_dir.mkdir(exist_ok=True)

    existing_versions = list_versions(prompt_name)
    prompt_version = versioning.get_next_version(existing_versions, change_type)

    if len(prompt_content.encode("utf-8")) > MAX_PROMPT_SIZE:
        raise ValueError(
            f"Prompt content exceeds maximum size of {MAX_PROMPT_SIZE:,} bytes"
        )

    prompts_data = {
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_content": prompt_content,
        "llm_model": model,
        "llm_temperature": temperature,
        "llm_reasoning_effort": reasoning_effort,
        "owner": owner,
        "change_note": change_note,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
    }

    version_file = prompt_dir / f"{prompt_version}.json"
    with open(version_file, "w") as file:
        json.dump(prompts_data, file, indent=2, ensure_ascii=False)

    metadata = load_metadata()
    if prompt_name not in metadata["active_versions"]:
        metadata["active_versions"][prompt_name] = prompt_version
    else:
        version_active = metadata["active_versions"][prompt_name]
        if prompt_version != version_active:
            old_version_data = load_prompt_specific_version(prompt_name, version_active)
            if old_version_data:
                old_version_data["status"] = "deprecated"
                old_file = prompt_dir / f"{version_active}.json"
                with open(old_file, "w") as file:
                    json.dump(old_version_data, file, indent=2, ensure_ascii=False)

        metadata["active_versions"][prompt_name] = prompt_version

    save_metadata(metadata)
    return prompt_version


# ---- ACTIONS ----


def get_active_version(prompt_name: str) -> str | None:
    """Retorna a versão atualmente ativa de um prompt.

    Retorna ``None`` se nenhuma estiver definida.
    """
    metadata = load_metadata()
    return metadata["active_versions"].get(prompt_name)


def active_version(prompt_name: str, version: str) -> bool:
    """Define uma versão específica como ativa para um prompt.

    A versão anteriormente ativa é marcada como deprecated.
    Retorna ``True`` em caso de sucesso, ``False`` se a versão solicitada não existir.
    """
    ensure_prompts_dir()

    version_data = load_prompt_specific_version(prompt_name, version)
    if not version_data:
        return False

    metadata = load_metadata()

    old_version = metadata["active_versions"].get(prompt_name)

    if old_version and old_version != version:
        old_data = load_prompt_specific_version(prompt_name, old_version)
        if old_data:
            old_data["status"] = "deprecated"
            old_file = get_prompt_dir(prompt_name) / f"{old_version}.json"
            with open(old_file, "w") as file:
                json.dump(old_data, file, indent=2, ensure_ascii=False)

    version_data["status"] = "active"
    version_file = get_prompt_dir(prompt_name) / f"{version}.json"
    with open(version_file, "w") as file:
        json.dump(version_data, file, indent=2, ensure_ascii=False)

    metadata["active_versions"][prompt_name] = version
    save_metadata(metadata)
    return True


def deprecate_version(prompt_name: str, version: str) -> bool:
    """Marca uma versão como deprecated sem alterar a versão ativa.

    A versão atualmente ativa não pode ser depreciada diretamente.
    Retorna ``True`` em caso de sucesso, ``False`` se não existir ou estiver ativa.
    """
    ensure_prompts_dir()

    version_data = load_prompt_specific_version(prompt_name, version)
    if not version_data:
        return False

    metadata = load_metadata()
    if metadata["active_versions"].get(prompt_name) == version:
        return False

    version_data["status"] = "deprecated"
    version_file = get_prompt_dir(prompt_name) / f"{version}.json"

    with open(version_file, "w") as file:
        json.dump(version_data, file, indent=2, ensure_ascii=False)

    return True


def get_all_prompt_version(prompt_name: str) -> list[dict]:
    """Retorna todas as versões de um prompt como dicionários JSON carregados.

    Ordenadas por data de criação (mais recente primeiro).
    """
    ensure_prompts_dir()

    versions = list_versions(prompt_name)

    versions_list = []
    for version in versions:
        data = load_prompt_specific_version(prompt_name, version)
        if data:
            versions_list.append(data)

    return sorted(versions_list, key=lambda x: x["created_at"], reverse=True)
