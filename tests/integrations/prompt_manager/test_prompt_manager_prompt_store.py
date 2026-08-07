"""Testes de integração para prompts_manager.src.prompt_strore."""

import json
import re

import pytest

_FAKE_CONTENT = "This is fake prompt content for testing."
_FAKE_MODEL = "gpt-4-test"
_FAKE_OWNER = "ci-tester"
_FAKE_NOTE = "Automated test version."


class TestGetPromptDir:
    def test_valid_name(self, patched_store, temp_prompts_dir):
        """Nome de prompt válido resolve para caminho dentro do dir de prompts."""
        result = patched_store.get_prompt_dir("my-prompt_v1")
        expected = temp_prompts_dir / "my-prompt_v1"
        assert result == expected

    @pytest.mark.parametrize(
        "invalid_name",
        [
            "",
            "a b",
            "a.b",
            "../escape",
            "a/b",
        ],
    )
    def test_invalid_name_raises_valueerror(self, patched_store, invalid_name):
        """Nomes com caracteres inválidos lançam ValueError."""
        with pytest.raises(ValueError, match="Invalid prompt name"):
            patched_store.get_prompt_dir(invalid_name)

    def test_path_traversal_blocked(self, patched_store, monkeypatch):
        """Nome que passa na regex mas resolve fora de PROMPTS_DIR lança ValueError."""
        monkeypatch.setattr(patched_store, "_VALID_PROMPT_NAME", re.compile(r"^.+$"))
        with pytest.raises(ValueError, match="Path traversal blocked"):
            patched_store.get_prompt_dir("../../etc")


class TestCreatePromptVersion:
    def test_first_version_is_v1_0_0(self, patched_store):
        """A primeira versão criada para um prompt é sempre 'v1.0.0'."""
        version = patched_store.create_prompt_version(
            prompt_name="first-ver-test",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
            change_type="major",
        )
        assert version == "v1.0.0"

    def test_updates_metadata_correctly(self, patched_store):
        """Metadados são atualizados com a nova versão ativa após a criação."""
        patched_store.create_prompt_version(
            prompt_name="meta-test",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
        )

        active = patched_store.get_active_version("meta-test")
        assert active == "v1.0.0"

        metadata = patched_store.load_metadata()
        assert metadata["active_versions"]["meta-test"] == "v1.0.0"

    def test_rejects_oversized_content(self, patched_store, monkeypatch):
        """Conteúdo maior que MAX_PROMPT_SIZE lança ValueError."""
        monkeypatch.setattr(patched_store, "MAX_PROMPT_SIZE", 10)

        with pytest.raises(ValueError, match="exceeds maximum size"):
            patched_store.create_prompt_version(
                prompt_name="oversize-test",
                prompt_content="x" * 100,
                model=_FAKE_MODEL,
                owner=_FAKE_OWNER,
                change_note=_FAKE_NOTE,
            )

    def test_subsequent_version_bumps_correctly(self, patched_store):
        """Segunda criação usa o incremento semver correto."""
        patched_store.create_prompt_version(
            prompt_name="bump-test",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
        )
        version2 = patched_store.create_prompt_version(
            prompt_name="bump-test",
            prompt_content="Updated content.",
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note="Patch fix.",
            change_type="patch",
        )
        assert version2 == "v1.0.1"

    def test_old_active_is_deprecated_on_new_creation(self, patched_store):
        """A versão ativa anterior é marcada como deprecated após uma nova versão."""
        patched_store.create_prompt_version(
            prompt_name="deprecate-on-create",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
        )
        patched_store.create_prompt_version(
            prompt_name="deprecate-on-create",
            prompt_content="Newer content.",
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note="Updated.",
        )

        old = patched_store.load_prompt_specific_version(
            "deprecate-on-create", "v1.0.0"
        )
        assert old is not None
        assert old["status"] == "deprecated"


class TestDeprecateVersion:
    def test_cannot_deprecate_active_version(self, patched_store):
        """Depreciar a versão atualmente ativa retorna False."""
        patched_store.create_prompt_version(
            prompt_name="dep-test",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
        )

        result = patched_store.deprecate_version("dep-test", "v1.0.0")
        assert result is False

    def test_cannot_deprecate_nonexistent_version(self, patched_store):
        """Depreciar uma versão que não existe retorna False."""
        result = patched_store.deprecate_version("no-such-prompt", "v9.9.9")
        assert result is False

    def test_can_deprecate_non_active_version(self, patched_store):
        """Uma versão não ativa pode ser depreciada com sucesso."""
        patched_store.create_prompt_version(
            prompt_name="dep-ok-test",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
        )
        patched_store.create_prompt_version(
            prompt_name="dep-ok-test",
            prompt_content="v2 content.",
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note="v2",
        )

        result = patched_store.deprecate_version("dep-ok-test", "v1.0.0")
        assert result is True

        data = patched_store.load_prompt_specific_version("dep-ok-test", "v1.0.0")
        assert data["status"] == "deprecated"


class TestActiveVersion:
    def test_activate_nonexistent_version_returns_false(self, patched_store):
        """Ativar uma versão que não existe retorna False."""
        result = patched_store.active_version("no-such-prompt", "v9.9.9")
        assert result is False

    def test_activate_existing_version_succeeds(self, patched_store):
        """Ativar uma versão conhecida retorna True e atualiza os metadados."""
        patched_store.create_prompt_version(
            prompt_name="act-test",
            prompt_content=_FAKE_CONTENT,
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note=_FAKE_NOTE,
        )
        patched_store.create_prompt_version(
            prompt_name="act-test",
            prompt_content="v2 content.",
            model=_FAKE_MODEL,
            owner=_FAKE_OWNER,
            change_note="v2",
        )

        result = patched_store.active_version("act-test", "v1.0.0")
        assert result is True
        assert patched_store.get_active_version("act-test") == "v1.0.0"


class TestListVersions:
    def test_sorts_semantically_not_alphabetically(self, patched_store):
        """list_versions ordena por versão semântica, não por ordenação alfabética."""
        prompt_dir = patched_store.get_prompt_dir("sort-test")
        prompt_dir.mkdir()

        template = {
            "prompt_name": "sort-test",
            "prompt_content": "test",
            "llm_model": "gpt-4",
            "owner": "tester",
            "change_note": "test",
            "llm_temperature": None,
            "llm_reasoning_effort": None,
            "created_at": "2025-01-01T00:00:00+00:00",
            "status": "deprecated",
        }

        for ver in ("v1.10.0", "v1.2.0", "v2.0.0", "v1.1.0"):
            data = {**template, "prompt_version": ver}
            with open(prompt_dir / f"{ver}.json", "w") as f:
                json.dump(data, f)

        versions = patched_store.list_versions("sort-test")
        assert versions == ["v1.1.0", "v1.2.0", "v1.10.0", "v2.0.0"]


class TestLoadPromptSpecificVersion:
    def test_falls_back_to_latest_when_no_active(self, patched_store):
        """Sem versão ativa definida, a versão semver mais recente é carregada."""
        prompt_dir = patched_store.get_prompt_dir("fallback-test")
        prompt_dir.mkdir()

        template = {
            "prompt_name": "fallback-test",
            "prompt_content": "test content",
            "llm_model": "gpt-4",
            "owner": "tester",
            "change_note": "test",
            "llm_temperature": None,
            "llm_reasoning_effort": None,
            "created_at": "2025-01-01T00:00:00+00:00",
        }

        for ver in ("v1.0.0", "v1.1.0"):
            data = {**template, "prompt_version": ver, "status": "deprecated"}
            with open(prompt_dir / f"{ver}.json", "w") as f:
                json.dump(data, f)

        result = patched_store.load_prompt_specific_version("fallback-test")
        assert result is not None
        assert result["prompt_version"] == "v1.1.0"

    def test_returns_none_for_unknown_prompt(self, patched_store):
        """Carregar um prompt que não tem versões retorna None."""
        result = patched_store.load_prompt_specific_version("does-not-exist")
        assert result is None
