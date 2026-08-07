"""Fixtures compartilhadas para testes de integração do prompts_manager."""

import pytest


@pytest.fixture
def temp_prompts_dir(tmp_path):
    """Diretório temporário para servir como raiz de prompts."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    return prompts_dir


@pytest.fixture
def patched_store(temp_prompts_dir, monkeypatch):
    """Substitui PROMPTS_DIR, METADATA_FILE e inicializa o store com dir temporário."""
    import prompts_manager.src.prompt_strore as store_module

    monkeypatch.setattr(store_module, "PROMPTS_DIR", temp_prompts_dir)
    monkeypatch.setattr(
        store_module,
        "METADATA_FILE",
        temp_prompts_dir / "metadata.json",
    )
    monkeypatch.setattr(store_module, "MAX_PROMPT_SIZE", 100_000)

    store_module.ensure_prompts_dir()
    return store_module
