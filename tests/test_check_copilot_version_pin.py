"""Tests for the Copilot CLI version-pin guard (Issue #2630).

The guard reads the pinned ``COPILOT_VERSION`` from
``.github/actions/ai-review/action.yml`` and fails when the pin is missing,
unparseable, or on the known-bad list. ``0.0.397`` is the seed known-bad entry:
npm flags it deprecated for "invalid session id errors", which broke the
PR-comment-processing step of the PR Maintenance workflow.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "validation"
    / "check_copilot_version_pin.py"
)
_spec = importlib.util.spec_from_file_location("check_copilot_version_pin", _MODULE_PATH)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _write_action(tmp_path: Path, version_line: str) -> Path:
    action = tmp_path / "action.yml"
    action.write_text(
        "runs:\n"
        "  steps:\n"
        "    - name: Install GitHub Copilot CLI\n"
        "      run: |\n"
        "        set -e\n"
        f"        {version_line}\n"
        '        npm install -g "@github/copilot@${COPILOT_VERSION}"\n',
        encoding="utf-8",
    )
    return action


def test_extract_version_reads_pin(tmp_path: Path) -> None:
    action = _write_action(tmp_path, 'COPILOT_VERSION="1.0.63"')
    assert mod.extract_pinned_version(action) == "1.0.63"


def test_extract_version_missing_pin_raises(tmp_path: Path) -> None:
    action = tmp_path / "action.yml"
    action.write_text("runs:\n  steps: []\n", encoding="utf-8")
    with pytest.raises(mod.VersionPinError):
        mod.extract_pinned_version(action)


def test_known_bad_version_fails(tmp_path: Path) -> None:
    action = _write_action(tmp_path, 'COPILOT_VERSION="0.0.397"')
    rc = mod.check_action(action)
    assert rc == mod.EXIT_LOGIC


def test_good_version_passes(tmp_path: Path) -> None:
    action = _write_action(tmp_path, 'COPILOT_VERSION="1.0.63"')
    assert mod.check_action(action) == mod.EXIT_OK


def test_unparseable_version_fails(tmp_path: Path) -> None:
    action = _write_action(tmp_path, 'COPILOT_VERSION="not-a-version"')
    assert mod.check_action(action) == mod.EXIT_LOGIC


def test_is_known_bad_matches_seed() -> None:
    assert mod.is_known_bad("0.0.397") is True
    assert mod.is_known_bad("1.0.63") is False


def test_is_parseable() -> None:
    assert mod.is_parseable("1.0.63") is True
    assert mod.is_parseable("0.0.397") is True
    assert mod.is_parseable("1.0.62-2") is True
    assert mod.is_parseable("garbage") is False


def test_repo_action_pin_is_clean() -> None:
    """The real action.yml in this repo must pass the guard.

    This is the regression anchor: it fails if anyone re-pins to a known-bad
    version (e.g. reverts to 0.0.397) before the change reaches CI.
    """
    repo_action = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "actions"
        / "ai-review"
        / "action.yml"
    )
    assert mod.check_action(repo_action) == mod.EXIT_OK


def test_main_default_targets_repo_action() -> None:
    assert mod.main([]) == mod.EXIT_OK
