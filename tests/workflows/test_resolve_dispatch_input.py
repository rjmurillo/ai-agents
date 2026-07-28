"""Tests for the workflow input validator extracted under ADR-006."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "workflows"
    / "resolve_dispatch_input.py"
)
_SPEC = importlib.util.spec_from_file_location("resolve_dispatch_input", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
resolver = importlib.util.module_from_spec(_SPEC)
sys.modules["resolve_dispatch_input"] = resolver
_SPEC.loader.exec_module(resolver)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    **env: str,
) -> tuple[int, str]:
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    code = resolver.main()
    return code, output.read_text(encoding="utf-8") if output.exists() else ""


class TestIntegerValues:
    def test_accepts_a_positive_integer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, written = _run(
            monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE="7"
        )

        assert code == 0
        assert written == "days=7\n"

    def test_rejects_a_shell_metacharacter(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, written = _run(
            monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE="7; curl evil"
        )

        assert code == 1
        assert written == ""

    def test_rejects_an_empty_value(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE="")

        assert code == 1

    def test_rejects_zero_because_the_message_promises_positive(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE="0")

        assert code == 1

    def test_rejects_a_negative_value(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE="-1")

        assert code == 1

    def test_rejects_leading_whitespace(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE=" 7")

        assert code == 1


class TestChoiceValues:
    def test_accepts_a_listed_choice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, written = _run(
            monkeypatch,
            tmp_path,
            OUTPUT_NAME="format",
            INPUT_VALUE="json",
            VALUE_KIND="choice",
            ALLOWED_CHOICES="summary,markdown,json",
        )

        assert code == 0
        assert written == "format=json\n"

    def test_rejects_an_unlisted_choice(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, written = _run(
            monkeypatch,
            tmp_path,
            OUTPUT_NAME="format",
            INPUT_VALUE="yaml",
            VALUE_KIND="choice",
            ALLOWED_CHOICES="summary,markdown,json",
        )

        assert code == 1
        assert written == ""

    def test_choice_matching_is_exact_not_prefix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(
            monkeypatch,
            tmp_path,
            OUTPUT_NAME="format",
            INPUT_VALUE="json ",
            VALUE_KIND="choice",
            ALLOWED_CHOICES="summary,markdown,json",
        )

        assert code == 1

    def test_choice_without_a_list_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(
            monkeypatch,
            tmp_path,
            OUTPUT_NAME="format",
            INPUT_VALUE="json",
            VALUE_KIND="choice",
            ALLOWED_CHOICES="",
        )

        assert code == 2


class TestConfigErrors:
    def test_unknown_kind_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, _ = _run(
            monkeypatch,
            tmp_path,
            OUTPUT_NAME="days",
            INPUT_VALUE="7",
            VALUE_KIND="fortran",
        )

        assert code == 2

    def test_missing_output_name_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("OUTPUT_NAME", raising=False)
        monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out"))
        monkeypatch.setenv("INPUT_VALUE", "7")

        assert resolver.main() == 2

    def test_missing_github_output_is_a_config_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        monkeypatch.setenv("OUTPUT_NAME", "days")
        monkeypatch.setenv("INPUT_VALUE", "7")

        assert resolver.main() == 2

    def test_an_injected_output_name_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, written = _run(
            monkeypatch, tmp_path, OUTPUT_NAME="days\nevil", INPUT_VALUE="7"
        )

        assert code == 2
        assert written == ""


class TestOutputAppending:
    def test_appends_rather_than_truncates(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        output = tmp_path / "github_output"
        output.write_text("existing=1\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.setenv("OUTPUT_NAME", "days")
        monkeypatch.setenv("INPUT_VALUE", "3")
        monkeypatch.delenv("VALUE_KIND", raising=False)
        monkeypatch.delenv("ALLOWED_CHOICES", raising=False)

        assert resolver.main() == 0
        assert output.read_text(encoding="utf-8") == "existing=1\ndays=3\n"
