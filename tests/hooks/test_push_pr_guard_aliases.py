"""Symlink, alias, and renamed-interpreter resolution tests.

Split from the former single ``tests/hooks/test_push_pr_script_identity_guard.py``
(issue #4764), which had grown to 2,077 lines and carried the whole policy
matrix for both harnesses in one module. Dispatcher runners, the payload shape,
and the temporary repository layout live in
``tests/hooks/push_pr_guard_harness.py`` so no module re-derives them.

Issue #5013 retired the guard from the generated Copilot shim tree
(dispatch_groups.json marks it copilotExclude, so the generator omits it).
Every case here now runs through the Claude dispatcher only, which is where
the guard still runs; invoke_dispatch_claude.py does not read
copilotExclude.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    CLAUDE_PLUGIN_ROOT,
    REPOSITORY_SCRIPT,
    SCRIPT_RELATIVE,
)
from tests.hooks.push_pr_guard_harness import (
    RUNNERS as _RUNNERS,
)
from tests.hooks.push_pr_guard_harness import (
    repository as _repository,
)
from tests.hooks.push_pr_guard_harness import (
    run_claude as _run_claude,
)
from tests.hooks.push_pr_guard_harness import (
    write_script as _write_script,
)

IN_SCOPE_ASSIGNMENT = "PUSH_PR_SCRIPT=new_pr.py "


def _in_scope(command: str) -> str:
    """Return ``command`` placed inside the guard's relevance scope."""
    if "new_pr.py" in command:
        return command
    return IN_SCOPE_ASSIGNMENT + command


def test_claude_denies_symlinked_repository_script(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    target = _write_script(repository / "attacker.py")
    script = repository / REPOSITORY_SCRIPT
    script.parent.mkdir(parents=True)
    try:
        script.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = _run_claude(f"python3 -I '{script}' --title fix", repository)

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_normalized_alias_of_runtime_script(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    # RUNNERS is Claude-only since issue #5013 (the guard's Copilot shim was
    # retired), so the runtime script always anchors to the Claude plugin root.
    plugin_root = CLAUDE_PLUGIN_ROOT
    script = plugin_root / SCRIPT_RELATIVE
    normalized_alias = f"{script.parent}/../pr/{script.name}"

    result = runner(f"python3 -I '{normalized_alias}' --title fix", repository)

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_parent_symlink_alias_of_runtime_script(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    # RUNNERS is Claude-only since issue #5013; see the note above.
    plugin_root = CLAUDE_PLUGIN_ROOT
    alias = repository / "trusted-script-parent"
    try:
        alias.symlink_to(
            plugin_root / SCRIPT_RELATIVE.parent,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = runner(f"python3 -I '{alias / 'new_pr.py'}' --title fix", repository)

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_symlinked_python_interpreter(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    lookalike = _write_script(repository / "attacker" / "new_pr.py")
    interpreter = repository / "p"
    try:
        interpreter.symlink_to(sys.executable)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    for command in (
        f"./p '{lookalike}'",
        f"nohup ./p '{lookalike}'",
        f"nice -n 5 ./p '{lookalike}'",
        f"stdbuf -o 0 ./p '{lookalike}'",
        f"timeout 5 ./p '{lookalike}'",
    ):
        result = runner(command, repository)
        assert result.returncode == 2, command


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_path_resolved_python_alias(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    interpreter_directory = repository / "attacker-bin"
    interpreter_directory.mkdir()
    interpreter = interpreter_directory / "fail2ban-python"
    try:
        interpreter.symlink_to(sys.executable)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    result = runner(
        _in_scope(f"PATH='{interpreter_directory}' fail2ban-python -c \"print('attacker')\""),
        repository,
    )

    assert result.returncode == 2
    assert "dynamic Python -c and -m launchers are not allowed" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_copied_renamed_python_interpreter(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    interpreter = repository / "p"
    shutil.copy2(sys.executable, interpreter)
    interpreter.chmod(0o755)

    result = runner(_in_scope("./p -c \"print('attacker')\""), repository)

    assert result.returncode == 2
    assert "dynamic Python -c" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_allow_extensionless_python_entrypoint(
    tmp_path: Path,
    runner,
) -> None:
    """An unrelated Python entrypoint is out of scope (issue #4825)."""
    repository, _ = _repository(tmp_path)
    entrypoint = repository / "tool"
    entrypoint.write_text(
        "#!/usr/bin/env python3\nprint('attacker')\n",
        encoding="utf-8",
    )
    entrypoint.chmod(0o755)

    result = runner("./tool", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_expanding_path_with_trusted_literal_symlink(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    literal_parent = repository / "gate" / "{attacker,unused}"
    literal_parent.parent.mkdir(parents=True)
    trusted_parent = CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent
    try:
        literal_parent.symlink_to(trusted_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    _write_script(repository / "gate" / "attacker" / "new_pr.py")

    result = runner(
        "python3 -I gate/{attacker,unused}/new_pr.py",
        repository,
    )

    assert result.returncode == 2


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize(
    "command",
    [
        "python3 -I tools/trusted_helper.py --title fix",
        "bash -c 'python3 -I tools/trusted_helper.py --title fix'",
    ],
)
def test_claude_deny_renamed_copy_by_content(
    tmp_path: Path,
    runner,
    command: str,
) -> None:
    """Scope rule C: a byte-identical copy under another name is in scope."""
    repository, _ = _repository(tmp_path)
    copied = repository / "tools" / "trusted_helper.py"
    copied.parent.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, copied)

    result = runner(command, repository)

    assert result.returncode == 2
    if command.startswith("bash -c"):
        assert "shell evaluator wrappers are not allowed" in result.stderr
    else:
        assert "Python execution is limited" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
def test_claude_deny_renamed_copy_of_new_pr(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    copied = repository / "tools" / "trusted.py"
    copied.parent.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, copied)

    result = runner(
        "python3 -I tools/trusted.py --title 'fix: alias' "
        "--body-file /etc/hosts --skip-validation --audit-reason x",
        repository,
    )

    assert result.returncode == 2
    assert "Python execution is limited" in result.stderr

    result = runner(
        "uv run tools/trusted.py --title 'fix: alias' "
        "--body-file /etc/hosts --skip-validation --audit-reason x",
        repository,
    )

    assert result.returncode == 2
    assert "Python execution is limited" in result.stderr


@pytest.mark.parametrize("runner", _RUNNERS)
@pytest.mark.parametrize("padding", [0, 40, 63, 70, 200])
def test_claude_deny_padded_renamed_copy(
    tmp_path: Path,
    runner,
    padding: int,
) -> None:
    """Environment padding must not push an executed copy out of view.

    Scope rule C once scanned a fixed 64-token window over all tokens, so a
    command could pad itself past the cap with `env` assignments and hide a
    byte-identical copy behind them. Measured: padding 63 and above returned
    exit 0 (issue #4825). The rule now inspects execution positions, which
    padding cannot move.
    """
    repository, _ = _repository(tmp_path)
    copied = repository / "tools" / "helper.py"
    copied.parent.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, copied)
    prefix = " ".join(f"A{index}=1" for index in range(padding))
    command = f"{prefix} python3 -I tools/helper.py --title x".strip()

    result = runner(command, repository)

    assert result.returncode == 2, f"padding={padding}: allowed"
    assert "Python execution is limited" in result.stderr

