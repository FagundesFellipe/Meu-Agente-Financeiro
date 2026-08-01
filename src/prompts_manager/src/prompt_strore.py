"""File-based prompt store with semantic versioning.

Prompts are stored as JSON files in a directory structure keyed by name.
Each prompt directory holds one JSON file per version, and a top-level
``metadata.json`` tracks which version is currently active for each prompt.
"""

import json
import re
import fcntl
from datetime import datetime, timezone
from pathlib import Path

from prompts_manager.config import settings
from prompts_manager.src import versioning

PROMPTS_DIR = Path(settings.prompt_dir)
METADATA_FILE = PROMPTS_DIR / "metadata.json"
_VALID_PROMPT_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
MAX_PROMPT_SIZE = settings.max_prompt_size


# ---- UTIL ----
def ensure_prompts_dir():
    """Create the prompts directory and an empty metadata file if they do not exist."""
    PROMPTS_DIR.mkdir(exist_ok=True)
    if not METADATA_FILE.exists():
        with open(METADATA_FILE, "w") as file:
            json.dump({"active_versions": {}}, file, indent=2)


# ---- METADATA ----
def load_metadata() -> dict:
    """Load and return the metadata dictionary from ``metadata.json``.

    Creates the file with a default structure if it does not exist.
    """
    ensure_prompts_dir()

    if not METADATA_FILE.exists():
        return {"active_versions": {}}
    with open(METADATA_FILE) as file:
        return json.load(file)


def save_metadata(metadata: dict):
    """Persist the given metadata dictionary to ``metadata.json`` atomically.

    Acquires an exclusive lock to prevent race conditions between
    concurrent read-modify-write cycles.
    """
    ensure_prompts_dir()
    with open(METADATA_FILE, "r+") as file:
        fcntl.flock(file, fcntl.LOCK_EX)
        file.seek(0)
        json.dump(metadata, file, indent=2)
        file.truncate()
        fcntl.flock(file, fcntl.LOCK_UN)


# ---- PROMPTS
def get_prompt_dir(prompt_name: str) -> Path:
    """Return the directory path for a given prompt name.

    Raises ValueError if the name contains invalid characters or
    would resolve outside the prompts directory.
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
    """Return a list of all prompt names.

    Subdirectories inside the prompts root, excluding ``.git``.
    """
    ensure_prompts_dir()

    if not PROMPTS_DIR:
        return []

    return [d.name for d in PROMPTS_DIR.iterdir() if d.is_dir() and d.name != ".git"]


def list_versions(prompt_name: str) -> list[str]:
    """Return all available version strings for a prompt, sorted from oldest to newest.

    JSON files whose name is ``"metadatajson"`` (no dot) are excluded.
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
    """Load and return the JSON data for a specific prompt version.

    If no version is given, the active version from metadata is used.
    Falls back to the latest available version if no active version is set.
    Returns ``None`` if the prompt or version does not exist.
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
    """Create a new version of a prompt and set it as the active version.

    The previous active version is automatically marked as deprecated.
    Returns the newly created version string.
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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "active",
    }

    version_file = prompt_dir / f"{prompt_version}.json"
    with open(version_file, "w") as file:
        json.dump(prompts_data, file, indent=2)

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
                    json.dump(old_version_data, file, indent=2)

        metadata["active_versions"][prompt_name] = prompt_version

    save_metadata(metadata)
    return prompt_version


# ---- ACTIONS ----


def get_active_version(prompt_name: str) -> str | None:
    """Return the currently active version string for a prompt.

    Returns ``None`` if none is set.
    """
    metadata = load_metadata()
    return metadata["active_versions"].get(prompt_name)


def active_version(prompt_name: str, version: str) -> bool:
    """Set a specific version as the active version for a prompt.

    The previously active version is marked as deprecated.
    Returns ``True`` on success, ``False`` if the requested version does not exist.
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
                json.dump(old_data, file, indent=2)

    version_data["status"] = "active"
    version_file = get_prompt_dir(prompt_name) / f"{version}.json"
    with open(version_file, "w") as file:
        json.dump(version_data, file, indent=2)

    metadata["active_versions"][prompt_name] = version
    save_metadata(metadata)
    return True


def deprecate_version(prompt_name: str, version: str) -> bool:
    """Mark a version as deprecated without changing the active version.

    The currently active version cannot be deprecated directly.
    Returns ``True`` on success, ``False`` if the version does not exist or is active.
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
        json.dump(version_data, file, indent=2)

    return True


def get_all_prompt_version(prompt_name: str) -> list[dict]:
    """Return all versions of a prompt as loaded JSON dicts.

    Sorted by creation date (newest first).
    """
    ensure_prompts_dir()

    versions = list_versions(prompt_name)

    versions_list = []
    for version in versions:
        data = load_prompt_specific_version(prompt_name, version)
        if data:
            versions_list.append(data)

    return sorted(versions_list, key=lambda x: x["created_at"], reverse=True)
