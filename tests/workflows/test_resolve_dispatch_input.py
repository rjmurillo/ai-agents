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


# The integer check is `[0-9]`, an explicit ASCII range, and these tests exist to
# keep it that way. Python's `\d` matches every Unicode decimal digit, so the
# natural-looking "tidy up the regex" edit from `[0-9]+` to `\d+` would accept
# Arabic-Indic and fullwidth digits. `int()` parses those, so the value would
# survive validation and reach the consumer as a number nobody typed. Every case
# below passes under `[0-9]` and fails under `\d`, which is the point: the
# existing suite cannot tell the two regexes apart, and this class can.
_NON_ASCII_DIGITS = [
    pytest.param("\u0667", id="arabic-indic-seven"),
    pytest.param("\u0660\u0667", id="arabic-indic-leading-zero"),
    pytest.param("\uff10\uff17", id="fullwidth-zero-seven"),
    pytest.param("1\u0667", id="mixed-ascii-and-arabic-indic"),
    pytest.param("\u0967\u0968\u0969", id="devanagari-one-two-three"),
    pytest.param("\u06f7", id="extended-arabic-indic-seven"),
    pytest.param("\u1c47", id="lepcha-seven"),
]


class TestOnlyAsciiDigitsAreAccepted:
    @pytest.mark.parametrize("value", _NON_ASCII_DIGITS)
    def test_rejects_a_non_ascii_digit(
        self, value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code, written = _run(
            monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE=value
        )

        assert code == 1
        assert written == ""

    @pytest.mark.parametrize("value", _NON_ASCII_DIGITS)
    def test_python_would_parse_the_rejected_value_as_an_integer(
        self, value: str
    ) -> None:
        """Pin why rejection matters: these are not garbage, they are numbers.

        A reviewer could reasonably ask whether rejecting them is pedantry. It is
        not. `int()` accepts every one, so a widened regex would not fail loudly
        later; it would hand a silently different number to the consumer.
        """
        assert int(value) >= 0

    @pytest.mark.parametrize("value", ["07", "007", "0000009"])
    def test_accepts_an_ascii_leading_zero_form(
        self, value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Leading zeros are accepted, and that is deliberate.

        `int("007")` is 7, so the value the consumer sees is the value the
        dispatcher meant. The shell guard this script replaced rejected the whole
        `0*` family in order to reject zero; the script rejects zero on its own
        (`int(value) > 0`), so the family no longer has to go with it. Pinned
        because it is a real behaviour difference from the guard, not an accident.
        """
        code, written = _run(
            monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE=value
        )

        assert code == 0
        assert written == f"days={value}\n"

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("7\n", id="trailing-newline"),
            pytest.param("7\n8", id="embedded-newline"),
            pytest.param("7\r", id="trailing-carriage-return"),
            pytest.param("7\rdays=9", id="carriage-return-forging-an-output"),
        ],
    )
    def test_rejects_a_line_break_before_it_can_forge_an_output(
        self, value: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`$` alone would not catch this; `fullmatch` is what does.

        `re.match(r"^[0-9]+$", "7\\n")` succeeds, because `$` matches before a
        final newline. A value that reached `write_output` carrying a newline
        would append a second `name=value` line to `$GITHUB_OUTPUT` and forge an
        output the workflow never declared. Rejection has to happen here, at
        exit 1, not at the `write_output` guard, which reports a config error.
        """
        code, written = _run(
            monkeypatch, tmp_path, OUTPUT_NAME="days", INPUT_VALUE=value
        )

        assert code == 1
        assert written == ""
