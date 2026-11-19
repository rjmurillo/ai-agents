"""validate_doc_accuracy_same_pr: advisory wrapper over doc_accuracy.py --same-pr."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_spec
import pre_pr_sequence


def _stub(
    monkeypatch: pytest.MonkeyPatch, diff: str, scan: tuple[int, str, str]
) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(cmd: list[str], *_a: object, **_k: object) -> tuple[int, str, str]:
        calls.append(cmd)
        return (0, diff, "") if cmd[0] == "git" else scan

    monkeypatch.setattr(checks_spec, "_run_subprocess", run)
    monkeypatch.setattr(checks_spec, "_resolve_branch_base_ref", lambda _root: "origin/main")
    return calls


def test_skips_the_scan_when_no_code_file_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _stub(monkeypatch, "docs/a.md\n", (2, "", "boom"))

    assert checks_spec.validate_doc_accuracy_same_pr(REPO_ROOT) is True
    assert all(cmd[0] == "git" for cmd in calls)


def test_runs_same_pr_with_the_resolved_base_when_code_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _stub(monkeypatch, "docs/a.md\nsrc/x.py\n", (0, "Same-PR findings: 0 (none)\n", ""))

    assert checks_spec.validate_doc_accuracy_same_pr(REPO_ROOT) is True
    scan = calls[-1]
    assert "--same-pr" in scan
    assert scan[scan.index("--diff-base") + 1] == "origin/main"


def test_findings_exit_still_passes_and_is_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stub(monkeypatch, "src/x.py\n", (10, "Same-PR findings: 2 (R2: 2)\n", ""))

    assert checks_spec.validate_doc_accuracy_same_pr(REPO_ROOT) is True
    assert "Same-PR findings: 2" in capsys.readouterr().out


@pytest.mark.parametrize("code", [1, 2, 3])
def test_config_or_crash_exit_fails_the_gate(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    _stub(monkeypatch, "src/x.py\n", (code, "", "config error"))

    assert checks_spec.validate_doc_accuracy_same_pr(REPO_ROOT) is False


def test_unresolved_base_is_a_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks_spec, "_resolve_branch_base_ref", lambda _root: None)

    with pytest.raises(checks_spec.MissingScriptSkip):
        checks_spec.validate_doc_accuracy_same_pr(REPO_ROOT)


def test_gate_is_registered_in_the_sequence() -> None:
    names = [gate.name for gate in pre_pr_sequence._SEQUENCE]

    assert names.count("Doc Accuracy Same-PR (advisory)") == 1
