import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from prompts_manager.config import settings

_PROMPTS_DIR = Path(settings.prompt_dir)
_METADATA_PATH = _PROMPTS_DIR / "metadata.json"


class Metadata(TypedDict):
    active_versions: dict[str, str]


def _file_mtime_ns(path: Path) -> int:
    """Retorna a data de modificação do arquivo com precisão de nanossegundos"""
    return path.stat().st_mtime_ns


@lru_cache(maxsize=4)
def _load_metadata_cached(mtime_ns: int) -> Metadata:
    """
    Carrega o metadata.
    O mtime_ms faz parte da chave do cache. Quando o arquivo é alterado, uma nova entrada é criada
    """

    return json.loads(_METADATA_PATH.read_text(encoding="utf-8"))


def _load_metadata() -> Metadata:
    """Retorna o metadata, recarregando-o. quando o arquivo for modificado"""
    return _load_metadata_cached(_file_mtime_ns(_METADATA_PATH))


@lru_cache(maxsize=128)
def _load_prompt_config_cached(
    name: str,
    version: str,
    path: Path,
    prompt_mtime_ns: int,
) -> dict:
    """
    Carrega uma versão específica do prompt.
    A versão e a data de modificação do arquivo fazem parte da chave.
    """
    del prompt_mtime_ns  # Usado apenas como chave do cache.

    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt_config(name: str) -> dict:
    """Carrega a versão ativa de um prompt e retorna toda a configuração."""
    metadata = _load_metadata()

    try:
        version = metadata["active_versions"][name]
    except KeyError as exc:
        raise KeyError(f"Prompt não encontrado no metadata: {name!r}") from exc

    path = _PROMPTS_DIR / name / f"{version}.json"

    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo da versão ativa do prompt não encontrado: {path}"
        )

    return _load_prompt_config_cached(
        name=name,
        version=version,
        path=path,
        prompt_mtime_ns=_file_mtime_ns(path),
    )
