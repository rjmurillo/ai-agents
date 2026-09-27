"""Tests for the pre-PR path-local ratchet gate (issue #4880, REQ-6).

The gate runs ``effective_context.py --ci`` as a subprocess named by path.
The path literal is the edge the script reachability guard follows, and a
subprocess keeps ``checks_tooling`` from loading the ``scripts.validation``
package under a second module name, which the mypy changed-files gate
rejects.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validation import checks_tooling
from scripts.validation.checks_tooling import validate_effective_context_ratchet

SCRIPT = REPO_ROOT / "scripts" / "validation" / "effective_context.py"


def test_skips_when_the_module_is_absent(tmp_path: Path) -> None:
    """REQ-6: a downstream install without the module reports SKIP, not FAIL."""
    with pytest.raises(checks_tooling.MissingScriptSkip):
        validate_effective_context_ratchet(tmp_path)


@pytest.mark.parametrize(
    ("exit_code", "expected", "shown"),
    [(0, True, False), (1, False, True), (3, False, True)],
)
def test_maps_exit_code_and_prints_output_only_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exit_code: int,
    expected: bool,
    shown: bool,
) -> None:
    """REQ-6: exit 0 passes quietly; any other exit fails and shows the report."""
    calls: list[tuple[list[str], Path]] = []

    def _fake_run(argv: list[str], cwd: Path, **_kwargs: object) -> tuple[int, str, str]:
        calls.append((argv, cwd))
        return exit_code, "RATCHET REPORT", "ERR DETAIL"

    monkeypatch.setattr(checks_tooling, "_run_subprocess", _fake_run)
    assert validate_effective_context_ratchet(REPO_ROOT) is expected
    assert calls == [([sys.executable, str(SCRIPT), "--ci"], REPO_ROOT)]
    captured = capsys.readouterr()
    assert ("RATCHET REPORT" in captured.out) is shown
    assert ("ERR DETAIL" in captured.err) is shown


def test_real_repository_passes_the_gate() -> None:
    """REQ-6: the committed ceilings hold for this repository."""
    assert validate_effective_context_ratchet(REPO_ROOT) is True
