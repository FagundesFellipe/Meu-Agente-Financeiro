"""Testes unitários para funções auxiliares de prompts_manager.src.frontend.app."""

from prompts_manager.src.frontend.app import _parse_optional_float


class TestParseOptionalFloat:
    def test_valid_float_string(self):
        """'0.7' retorna 0.7, '1' retorna 1.0."""
        assert _parse_optional_float("0.7") == 0.7
        assert _parse_optional_float("1") == 1.0

    def test_empty_and_none_return_none(self):
        """String vazia e None retornam None."""
        assert _parse_optional_float("") is None
        assert _parse_optional_float(None) is None

    def test_invalid_string_returns_none(self):
        """Strings não numéricas e números malformados retornam None."""
        assert _parse_optional_float("abc") is None
        assert _parse_optional_float("1.2.3") is None
