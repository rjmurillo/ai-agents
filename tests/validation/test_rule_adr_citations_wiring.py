"""Wiring tests for the rule ADR citations gate (issue #5200).

The gate's behavior is covered in `test_check_rule_adr_citations.py`. This file
proves what those tests structurally cannot: that `pre_pr` reaches the gate, and
that the adapter converts each exit code into the right boolean. Registration is
read from the parsed `_SEQUENCE` tuple, never from a substring of the module
source (`testing.md` MUST 9), and the row is driven to prove it reached THIS
validator and not a neighbour with a matching name.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_rule_adr_citations import validate_rule_adr_citations


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )


def _registered_row():
    from pre_pr_sequence import _SEQUENCE

    wired = [gate for gate in _SEQUENCE if "Rule ADR Citations" in gate.name]
    assert len(wired) == 1, f"expected exactly one row, found {len(wired)}"
    return wired[0]


def test_gate_has_exactly_one_row_in_the_pre_pr_sequence() -> None:
    assert _registered_row() is not None


def test_the_registered_row_actually_calls_this_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import pre_pr_sequence as sequence

    seen: list[Path] = []

    def _spy(repo_root: Path) -> bool:
        seen.append(repo_root)
        return True

    monkeypatch.setattr(sequence, "validate_rule_adr_citations", _spy)
    _git(tmp_path, "init", "--quiet")
    result = _registered_row().run(tmp_path, argparse.Namespace())

    assert seen == [tmp_path], "the row resolved some other validator, so this gate never runs"
    assert result is True


def test_pre_pr_facade_reexports_the_adapter() -> None:
    from pre_pr import validate_rule_adr_citations as reexported

    assert reexported is validate_rule_adr_citations


@pytest.mark.parametrize(("code", "expected"), [(0, True), (1, False), (2, False), (3, False)])
def test_adapter_converts_each_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int, expected: bool
) -> None:
    """Only exit 0 is a pass. A configuration or external fault is a gate that
    did not run, and scoring it as a pass is the silent-pass failure
    `ci-scripts.md` MUST 11 and 12 exist to stop."""
    import check_rule_adr_citations as mod

    seen: list[list[str]] = []

    def _fake_main(argv: list[str] | None = None) -> int:
        seen.append(list(argv or []))
        return code

    monkeypatch.setattr(mod, "main", _fake_main)
    assert validate_rule_adr_citations(tmp_path) is expected
    assert seen == [["--repo-root", str(tmp_path)]]


def test_adapter_is_false_on_an_unrun_gate(tmp_path: Path) -> None:
    assert validate_rule_adr_citations(tmp_path / "no-such-repo") is False
