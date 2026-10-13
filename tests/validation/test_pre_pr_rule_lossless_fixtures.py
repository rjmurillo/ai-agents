"""Tests for the ``Rule Lossless Fixtures`` pre-PR gate (issue #6440).

``tests/build_scripts/test_rule_templates_lossless.py`` compares each
``src/claude/rules/<name>.md`` to a hand-copied fixture under
``tests/build_scripts/fixtures/rule_templates_b2/expected/``. ``build_all.py``
never refreshes that fixture, so a rule edit that cleared every local gate
failed only in CI. The gate runs the test locally and names the files to copy.

Coverage:

- positive: a clean tree passes, and the gate is wired into the sequence.
- negative: a stale fixture fails and the output names the exact copy command.
- edge: a failure with no stale fixture still fails, with no copy command;
  a downstream install without the test raises the skip signal.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way the runner does; see test_pre_pr_worktree_gate_wiring.py for
# why sys.path is inserted once and deliberately never restored.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_portability
import pre_pr_sequence
from checks_common import MissingScriptSkip

GATE = "Rule Lossless Fixtures"
LOSSLESS_TEST = Path("tests") / "build_scripts" / "test_rule_templates_lossless.py"
FIXTURE_DIR = Path("tests") / "build_scripts" / "fixtures" / "rule_templates_b2" / "expected"
RULES_DIR = Path("src") / "claude" / "rules"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _tree(root: Path, rules: dict[str, tuple[str, str]]) -> None:
    """Build a repo with the lossless test file and ``name -> (src, fixture)`` pairs."""
    _write(root / LOSSLESS_TEST, "")
    for name, (src_text, fixture_text) in rules.items():
        _write(root / RULES_DIR / f"{name}.md", src_text)
        _write(root / FIXTURE_DIR / f"{name}.md", fixture_text)


def _fake_runner(monkeypatch: pytest.MonkeyPatch, exit_code: int) -> list[list[str]]:
    """Replace the subprocess runner; return the recorded argument vectors."""
    calls: list[list[str]] = []

    def fake(cmd: list[str], **_kwargs: object) -> tuple[int, str, str]:
        calls.append(cmd)
        return exit_code, "pytest output", ""

    monkeypatch.setattr(checks_portability, "_run_subprocess", fake)
    return calls


class TestStaleRuleFixtures:
    def test_lists_only_fixtures_whose_bytes_differ(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"alpha": ("new\n", "old\n"), "beta": ("same\n", "same\n")})

        assert checks_portability.stale_rule_fixtures(tmp_path) == ["alpha"]

    def test_is_empty_when_every_fixture_matches(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"alpha": ("a\n", "a\n"), "beta": ("b\n", "b\n")})

        assert checks_portability.stale_rule_fixtures(tmp_path) == []

    def test_sorts_names(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"zeta": ("1\n", "2\n"), "alpha": ("1\n", "2\n")})

        assert checks_portability.stale_rule_fixtures(tmp_path) == ["alpha", "zeta"]

    def test_ignores_a_fixture_with_no_rule(self, tmp_path: Path) -> None:
        _tree(tmp_path, {})
        _write(tmp_path / FIXTURE_DIR / "orphan.md", "x\n")

        assert checks_portability.stale_rule_fixtures(tmp_path) == []

    def test_compares_bytes_not_line_endings(self, tmp_path: Path) -> None:
        _tree(tmp_path, {"alpha": ("a\r\n", "a\n")})

        assert checks_portability.stale_rule_fixtures(tmp_path) == ["alpha"]

    def test_is_empty_without_a_fixture_directory(self, tmp_path: Path) -> None:
        assert checks_portability.stale_rule_fixtures(tmp_path) == []


class TestValidateRuleLosslessFixtures:
    def test_passes_when_pytest_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _tree(tmp_path, {"alpha": ("a\n", "a\n")})
        calls = _fake_runner(monkeypatch, 0)

        assert checks_portability.validate_rule_lossless_fixtures(tmp_path) is True
        assert len(calls) == 1
        assert str(LOSSLESS_TEST) in calls[0]
        assert calls[0][1:3] == ["-m", "pytest"]

    def test_fails_and_names_the_copy_for_a_stale_fixture(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _tree(tmp_path, {"alpha": ("new\n", "old\n"), "beta": ("b\n", "b\n")})
        _fake_runner(monkeypatch, 1)

        assert checks_portability.validate_rule_lossless_fixtures(tmp_path) is False

        out = capsys.readouterr().out
        assert "cp src/claude/rules/alpha.md" in out
        assert "tests/build_scripts/fixtures/rule_templates_b2/expected/alpha.md" in out
        assert "beta" not in out

    def test_fails_without_a_copy_command_when_no_fixture_is_stale(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _tree(tmp_path, {"alpha": ("a\n", "a\n")})
        _fake_runner(monkeypatch, 1)

        assert checks_portability.validate_rule_lossless_fixtures(tmp_path) is False

        out = capsys.readouterr().out
        assert "cp " not in out
        assert "pytest output" in out

    def test_skips_when_the_lossless_test_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _fake_runner(monkeypatch, 1)

        with pytest.raises(MissingScriptSkip):
            checks_portability.validate_rule_lossless_fixtures(tmp_path)
        assert calls == []


def _run_sequence(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Drive the real sequence filtered to this gate; return its verdict."""
    verdicts: dict[str, bool] = {}

    class _State:
        total = 0
        skipped = 0

    def record(name: str, state: _State, callback: Callable[[], bool], skip: bool = False) -> bool:
        state.total += 1
        result = bool(callback())
        verdicts[name] = result
        return result

    wanted = [gate for gate in pre_pr_sequence._SEQUENCE if gate.name == GATE]
    monkeypatch.setattr(pre_pr_sequence, "_SEQUENCE", tuple(wanted))
    args = argparse.Namespace(quick=False, skip_tests=False, verbose=False)
    pre_pr_sequence.run_all_validations(REPO_ROOT, args, _State(), record)
    return verdicts


def test_the_gate_is_registered_in_the_sequence() -> None:
    assert GATE in [gate.name for gate in pre_pr_sequence._SEQUENCE]


def test_the_sequence_runs_the_gate_and_it_passes_on_the_real_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _run_sequence(monkeypatch) == {GATE: True}


def test_the_sequence_gate_fails_when_the_lossless_test_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control: same run, pytest forced red, verdict must flip."""
    _fake_runner(monkeypatch, 1)

    assert _run_sequence(monkeypatch) == {GATE: False}
