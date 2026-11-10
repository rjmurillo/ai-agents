"""AC-DUP-7: Both scanners preserve rule parsing through shared code."""

import pytest

from scripts.ai_review_common.scan_rules import parse_scan_rules


@pytest.mark.parametrize("value,expected", [("", ("one", "two")), (" two , one ", ("two", "one"))])
def test_rule_selection_preserves_defaults_and_order(value: str, expected: tuple[str, ...]) -> None:
    assert parse_scan_rules(value, ("one", "two"), 1) == expected


def test_invalid_rules_keep_the_existing_exit_and_diagnostic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        parse_scan_rules("bad,missing", ("one", "two"), 1)
    assert error.value.code == 1
    assert capsys.readouterr().err == (
        "error: unknown rules: bad, missing\nvalid rules: one, two\n"
    )
