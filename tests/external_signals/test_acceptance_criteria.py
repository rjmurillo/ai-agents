"""Tests for scripts.external_signals.acceptance_criteria."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.external_signals import acceptance_criteria as ac


BODY_OK = """\
# Title

## Acceptance

- [x] Adds `external_signals` helper module
- [x] Returns deterministic verdict

## Notes

unrelated
"""

BODY_MIXED = """\
## Acceptance Criteria

- [ ] Add validator
- [x] Document the contract
"""

BODY_NONE = """\
# Random doc

No acceptance section here.
"""


def test_parse_criteria_extracts_section():
    crits = ac.parse_criteria(BODY_OK)
    assert [c.text for c in crits] == [
        "Adds `external_signals` helper module",
        "Returns deterministic verdict",
    ]
    assert all(c.checked for c in crits)


def test_parse_criteria_mixed_check_state():
    crits = ac.parse_criteria(BODY_MIXED)
    assert [c.checked for c in crits] == [False, True]


def test_parse_criteria_no_section():
    assert ac.parse_criteria(BODY_NONE) == []


def test_evaluate_pass_all_checked():
    report = ac.evaluate(BODY_OK)
    assert report.passed
    assert report.unchecked == []


def test_evaluate_fails_when_unchecked():
    report = ac.evaluate(BODY_MIXED)
    assert not report.passed
    assert report.unchecked == ["Add validator"]


def test_diff_misses_flags_unmatched():
    body = "## Acceptance\n\n- [x] Implement `widget_factory` helper\n"
    diff = "+++ b/scripts/other.py\n+def something(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == ["Implement `widget_factory` helper"]


def test_diff_misses_clears_when_keyword_present():
    body = "## Acceptance\n\n- [x] Implement widget_factory helper\n"
    diff = "+++ b/scripts/x.py\n+def widget_factory(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == []


def test_diff_misses_ignores_deleted_lines():
    """Keyword in a deleted line must not satisfy the criterion."""
    body = "## Acceptance\n\n- [x] Add api endpoint\n"
    # The keyword 'api' only appears on a deleted line, not an added one.
    diff = "+++ b/scripts/x.py\n-def api(): pass\n+def other(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == ["Add api endpoint"]


def test_diff_misses_matches_added_lines_only():
    """Keyword in an added line satisfies the criterion."""
    body = "## Acceptance\n\n- [x] Add api endpoint\n"
    diff = "+++ b/scripts/x.py\n-def old(): pass\n+def api(): pass\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == []


def test_keywords_includes_three_char_tech_terms():
    """3-char technical terms like 'api', 'cli', 'git' must be extracted."""
    assert "api" in ac._keywords("Add API endpoint")
    assert "cli" in ac._keywords("cli command")
    assert "git" in ac._keywords("git commit")


def test_keywords_excludes_stop_words():
    """Common 3-char stop words like 'the', 'and', 'for' must be excluded."""
    assert "the" not in ac._keywords("fix the bug")
    assert "and" not in ac._keywords("add and remove")
    assert "for" not in ac._keywords("run for testing")


def test_keywords_short_criterion_not_silently_skipped():
    """A criterion with only short tech terms should still match the diff."""
    body = "## Acceptance\n\n- [x] Add CLI\n"
    diff = "+++ b/scripts/x.py\n+cli_main()\n"
    report = ac.evaluate(body, diff)
    assert report.diff_misses == []


def test_cli_fails_when_no_criteria(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    body = tmp_path / "body.md"
    body.write_text(BODY_NONE, encoding="utf-8")
    rc = ac.main(["--body", str(body)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "no acceptance criteria" in err


def test_cli_allow_empty(tmp_path: Path):
    body = tmp_path / "body.md"
    body.write_text(BODY_NONE, encoding="utf-8")
    assert ac.main(["--body", str(body), "--allow-empty"]) == 0


def test_cli_json_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    body = tmp_path / "body.md"
    body.write_text(BODY_OK, encoding="utf-8")
    rc = ac.main(["--body", str(body), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"passed": true' in out


def test_cli_unreadable_body_is_config_error(tmp_path: Path):
    missing = tmp_path / "nope.md"
    with pytest.raises(SystemExit) as exc:
        ac.main(["--body", str(missing)])
    assert exc.value.code == 2
