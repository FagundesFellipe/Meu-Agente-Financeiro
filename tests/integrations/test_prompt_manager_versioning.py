"""Unit tests for prompts_manager.src.versioning."""

import pytest

from prompts_manager.src.versioning import (
    format_version,
    get_next_version,
    parse_version,
)


class TestParseVersion:
    def test_with_v_prefix(self):
        """'v1.2.3' parses into (1, 2, 3)."""
        assert parse_version("v1.2.3") == (1, 2, 3)

    def test_without_v_prefix(self):
        """'1.2.3' parses into (1, 2, 3)."""
        assert parse_version("1.2.3") == (1, 2, 3)

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "",
            "abc",
            "1.2",
            "v1.2",
            "vabc",
            "1",
            "v1.2.a",
            "v1.a.0",
        ],
    )
    def test_invalid_raises_valueerror(self, invalid_input):
        """Non-conforming strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid version format"):
            parse_version(invalid_input)


class TestFormatVersion:
    def test_formats_tuple(self):
        """(1, 2, 3) formats to 'v1.2.3'."""
        assert format_version(1, 2, 3) == "v1.2.3"

    def test_formats_with_zeros(self):
        """(0, 0, 0) formats to 'v0.0.0'."""
        assert format_version(0, 0, 0) == "v0.0.0"


class TestGetNextVersion:
    def test_empty_list_returns_v1_0_0(self):
        """Empty list always returns 'v1.0.0'."""
        assert get_next_version([]) == "v1.0.0"

    def test_defaults_to_patch_bump(self):
        """When change_type is omitted it defaults to patch."""
        assert get_next_version(["v1.0.0"]) == "v1.0.1"

    def test_patch_bump(self):
        """Explicit 'patch' bumps the patch segment."""
        assert get_next_version(["v1.0.0"], "patch") == "v1.0.1"

    def test_minor_bump_resets_patch(self):
        """'minor' bumps minor and resets patch to zero."""
        assert get_next_version(["v2.1.7"], "minor") == "v2.2.0"

    def test_major_bump_resets_minor_and_patch(self):
        """'major' bumps major and resets minor and patch to zero."""
        assert get_next_version(["v3.4.5"], "major") == "v4.0.0"

    def test_ignores_invalid_entries(self):
        """Invalid version strings are skipped; bump is based on valid ones."""
        result = get_next_version(["v1.0.0", "lixo", "abc"], "patch")
        assert result == "v1.0.1"

    def test_all_invalid_returns_v1_0_0(self):
        """When all entries are invalid it falls back to 'v1.0.0'."""
        assert get_next_version(["abc", "xyz"], "minor") == "v1.0.0"

    def test_picks_highest_when_unsorted(self):
        """The highest semver among existing versions determines the bump base."""
        result = get_next_version(["v1.0.5", "v1.0.1", "v2.0.0"], "patch")
        assert result == "v2.0.1"

    def test_first_version_is_always_v1_0_0(self):
        """Regardless of change_type, first version is always 'v1.0.0'."""
        assert get_next_version([], "major") == "v1.0.0"
