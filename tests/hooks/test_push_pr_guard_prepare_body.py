"""Tests for --prepare-body-file acceptance and env --chdir worktree support.

Verifies the fix for issue #4930: the push-pr helper's --prepare-body-file
mode was denied by the identity guard because _validate_new_pr_arguments only
accepted --title + --body-file, and _script_reference required python3 -I at
token positions 0-1 (breaking env --chdir prefix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    PLUGIN_SCRIPT_REFERENCE,
)
from tests.hooks.push_pr_guard_harness import (
    RUNNERS as _RUNNERS,
)
from tests.hooks.push_pr_guard_harness import (
    body_file as _body_file,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
)

# -- Positive: --prepare-body-file is allowed --


@pytest.mark.parametrize("runner", _RUNNERS)
def test_prepare_body_file_bare(runner, tmp_path: Path) -> None:
    """The exact documented prepare command must be allowed."""
    root, _script = _repository(tmp_path)
    command = f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_prepare_body_file_with_env_chdir(runner, tmp_path: Path) -> None:
    """External worktrees using env --chdir must be allowed."""
    root, _script = _repository(tmp_path)
    command = (
        f'env --chdir={root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    )
    result = runner(command, root)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_prepare_body_file_with_env_C_short(runner, tmp_path: Path) -> None:
    """env -C <dir> is the short form of --chdir."""
    root, _script = _repository(tmp_path)
    command = (
        f'env -C {root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    )
    result = runner(command, root)
    assert result.returncode == 0, result.stderr


# -- Negative: invalid arguments still denied --


@pytest.mark.parametrize("runner", _RUNNERS)
def test_unknown_option_denied(runner, tmp_path: Path) -> None:
    """Unknown options must be denied."""
    root, _script = _repository(tmp_path)
    command = f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --unknown-flag'
    result = runner(command, root)
    assert result.returncode == 2
    assert "accepts only" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_prepare_body_file_mixed_with_title_denied(runner, tmp_path: Path) -> None:
    """--prepare-body-file cannot be combined with --title."""
    root, _script = _repository(tmp_path)
    body = _body_file(root)
    command = (
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        f'--prepare-body-file --title "test" --body-file "{body}"'
    )
    result = runner(command, root)
    assert result.returncode == 2


# -- Edge: remediation text in denials --


@pytest.mark.parametrize("runner", _RUNNERS)
def test_denial_includes_remediation(runner, tmp_path: Path) -> None:
    """Denials must include the matched rule and remediation guidance."""
    root, _script = _repository(tmp_path)
    command = f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --bad-option'
    result = runner(command, root)
    assert result.returncode == 2
    assert "Remediation" in result.stderr


# -- Negative: gh pr create is out of scope (stays allowed=0 by this guard) --


@pytest.mark.parametrize("runner", _RUNNERS)
def test_gh_pr_create_out_of_scope(runner, tmp_path: Path) -> None:
    """gh pr create does not mention new_pr.py so this guard allows it (exit 0).

    The denial of gh pr create is enforced by the tool allowlist, not this guard.
    This test verifies the guard does not regress by accidentally pulling gh
    commands into scope.
    """
    root, _script = _repository(tmp_path)
    command = "gh pr create --title test --body test"
    result = runner(command, root)
    assert result.returncode == 0
