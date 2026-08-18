"""Tests for --prepare-body-file acceptance and env --chdir worktree support.

Verifies the fix for issue #4930: the push-pr helper's --prepare-body-file
mode was denied by the identity guard because _validate_new_pr_arguments only
accepted --title + --body-file, and _script_reference required python3 -I at
token positions 0-1 (breaking env --chdir prefix).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    CLAUDE_PLUGIN_ROOT as _CLAUDE_PLUGIN_ROOT,
)
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
    environment as _environment,
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
    command = f'env --chdir={root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_prepare_body_file_with_env_c_short(runner, tmp_path: Path) -> None:
    """env -C <dir> is the short form of --chdir."""
    root, _script = _repository(tmp_path)
    command = f'env -C {root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
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
    """Denials must include the matched rule and the exact canonical command.

    A bare ``"Remediation" in result.stderr`` check passes even if the
    matched rule or the documented command text were deleted, so this
    asserts both pieces the acceptance criterion actually requires.
    """
    root, _script = _repository(tmp_path)
    command = f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --bad-option'
    result = runner(command, root)
    assert result.returncode == 2
    assert "new_pr.py accepts only --title, --body-file, or --prepare-body-file here" in (
        result.stderr
    )
    assert (
        'python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
        '/skills/github/scripts/pr/new_pr.py" --prepare-body-file' in result.stderr
    )


# -- Negative: the env prefix offset cannot be used to smuggle an untrusted
# -- interpreter or wrapper (PR #5106 review r3789851488).


@pytest.mark.parametrize("runner", _RUNNERS)
def test_leading_path_assignment_denied(runner, tmp_path: Path) -> None:
    """A leading PATH= assignment must not shift the python3 -I offset.

    Regression for the bypass this fix must not reopen: reusing a relevance
    classifier that skips leading assignments as the allowlist offset would
    let ``PATH=<attacker dir> python3 -I <trusted script>`` pass as if
    ``python3`` were still the offset-0 token the guard verified.
    """
    root, _script = _repository(tmp_path)
    command = f'PATH=/nonexistent python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_local_env_lookalike_denied(runner, tmp_path: Path) -> None:
    """A locally planted ``./env`` that is not the real system env is denied.

    ``env`` is matched by resolved content, not by the literal name ``env``,
    so a same-named script sitting in the worktree cannot stand in for the
    trusted system binary.
    """
    root, _script = _repository(tmp_path)
    fake_env = root / "env"
    fake_env.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    fake_env.chmod(0o755)
    command = f'./env --chdir={root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_env_with_extra_option_denied(runner, tmp_path: Path) -> None:
    """env --chdir combined with any other env option must be denied."""
    root, _script = _repository(tmp_path)
    command = (
        f'env --chdir={root} --unset=FOO python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    )
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_env_ignore_environment_denied(runner, tmp_path: Path) -> None:
    """env -i before --chdir must be denied; only a bare --chdir/-C is allowed."""
    root, _script = _repository(tmp_path)
    command = f'env -i --chdir={root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_wrapper_before_env_denied(runner, tmp_path: Path) -> None:
    """A wrapper preceding env (sudo, nice, ...) must be denied."""
    root, _script = _repository(tmp_path)
    command = f'sudo env --chdir={root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_env_chdir_shell_expansion_denied(runner, tmp_path: Path) -> None:
    """A --chdir value carrying shell expansion markers must be denied."""
    root, _script = _repository(tmp_path)
    command = f'env --chdir=$HOME python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_env_chdir_target_other_than_cwd_denied(runner, tmp_path: Path) -> None:
    """A --chdir target other than the hook's own cwd must be denied.

    Regression for the CWE-367 finding on PR #5106's automated security
    review: this guard resolves the relative plugin script reference
    against its own ``cwd``, while the real shell resolves the same
    relative operand against wherever ``env --chdir`` actually moved to.
    A directory carrying an attacker-controlled ``new_pr.py`` lookalike at
    the identical relative path must not be reachable by chdir-ing there.
    """
    root, _script = _repository(tmp_path)
    evil_root = tmp_path / "evil"
    evil_script = evil_root / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py"
    evil_script.parent.mkdir(parents=True, exist_ok=True)
    evil_script.write_text("#!/usr/bin/env python3\nprint('PWNED')\n", encoding="utf-8")
    evil_script.chmod(0o755)
    (evil_root / ".git").mkdir(parents=True, exist_ok=True)
    command = f'env --chdir={evil_root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_env_path_poisoned_with_fake_env_denied(runner, tmp_path: Path) -> None:
    """A fake ``env`` placed first on PATH must not pass as the trusted system env.

    Regression for PR #5106 review r3805395290: comparing the resolved
    ``env`` candidate against ``shutil.which("env")`` using the SAME ambient
    PATH degenerates to comparing a file with itself once that PATH is
    poisoned. The trusted baseline must resolve via a search path
    independent of the ambient one, so a fake ``env`` first on PATH is
    still denied.
    """
    root, _script = _repository(tmp_path)
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    fake_env = fake_bin / "env"
    fake_env.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    fake_env.chmod(0o755)
    poisoned_path = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    poisoned_environment = _environment(
        CLAUDE_PROJECT_DIR=str(root),
        CLAUDE_PLUGIN_ROOT=str(_CLAUDE_PLUGIN_ROOT),
        PATH=poisoned_path,
    )
    command = f'env --chdir={root} python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file'
    result = runner(command, root, env=poisoned_environment)
    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
def test_prepare_body_file_duplicate_denied(runner, tmp_path: Path) -> None:
    """Repeating --prepare-body-file must be denied, not silently accepted."""
    root, _script = _repository(tmp_path)
    command = f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --prepare-body-file --prepare-body-file'
    result = runner(command, root)
    assert result.returncode == 2


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
