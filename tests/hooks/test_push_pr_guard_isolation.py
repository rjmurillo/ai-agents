"""Plugin-root, isolated-mode, and shipped-shim launcher tests.

Split from the former single ``tests/hooks/test_push_pr_script_identity_guard.py``
(issue #4764), which had grown to 2,077 lines and carried the whole policy
matrix for both harnesses in one module. Dispatcher runners, the payload shape,
and the temporary repository layout live in
``tests/hooks/push_pr_guard_harness.py`` so no module re-derives them.

Issue #5013 retired the guard from the generated Copilot shim tree
(dispatch_groups.json marks it copilotExclude, so the generator omits it).
Guard POLICY cases (the ``runner`` parametrizations below) run through the
Claude dispatcher only now, which is where the guard still runs;
invoke_dispatch_claude.py does not read copilotExclude. A few tests here
still call the Copilot dispatcher directly, but to check the Copilot
dispatcher's OWN behavior (it still allows an installed reference, it still
allows a non-matching command, it no longer runs the retired guard), not to
check the guard's policy.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    CLAUDE_GUARD,
    CLAUDE_PLUGIN_ROOT,
    COPILOT_PLUGIN_ROOT,
    PLUGIN_SCRIPT_REFERENCE,
    REPO_ROOT,
    SCRIPT_RELATIVE,
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
from tests.hooks.push_pr_guard_harness import (
    run_claude as _run_claude,
)
from tests.hooks.push_pr_guard_harness import (
    run_copilot as _run_copilot,
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


def test_claude_denies_spoofed_plugin_root(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    attacker_root = tmp_path / "attacker-plugin"
    _write_script(attacker_root / SCRIPT_RELATIVE)

    result = _run_claude(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --title fix',
        repository,
        env=_environment(
            CLAUDE_PROJECT_DIR=str(repository),
            CLAUDE_PLUGIN_ROOT=str(attacker_root),
        ),
    )

    assert result.returncode == 2
    assert "not an approved new_pr.py" in result.stderr


def test_claude_denies_whitespace_plugin_root(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    attacker_root = repository / " "
    _write_script(attacker_root / SCRIPT_RELATIVE)

    result = _run_claude(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" --title fix',
        repository,
        env=_environment(
            CLAUDE_PROJECT_DIR=str(repository),
            COPILOT_PLUGIN_ROOT=" ",
            CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
        ),
    )

    assert result.returncode == 2
    assert "not an approved new_pr.py" in result.stderr


def test_python_isolated_mode_blocks_pythonpath_injection(tmp_path: Path) -> None:
    attacker = tmp_path / "attacker"
    marker = tmp_path / "imported-attacker"
    attacker.mkdir()
    (attacker / "argparse.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "raise RuntimeError('attacker argparse loaded')\n",
        encoding="utf-8",
    )
    env = _environment(PYTHONPATH=str(attacker))
    script = CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE

    vulnerable = subprocess.run(
        [sys.executable, str(script), "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert vulnerable.returncode != 0
    assert marker.exists()

    marker.rename(tmp_path / "imported-attacker-control")
    isolated = subprocess.run(
        [sys.executable, "-I", str(script), "--help"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert isolated.returncode == 0, isolated.stderr
    assert not marker.exists()


def test_isolated_description_validator_blocks_sibling_shadow(
    tmp_path: Path,
) -> None:
    script_dir = tmp_path / "validator"
    script_dir.mkdir()
    validator = script_dir / "validate_pr_description.py"
    shutil.copy2(
        CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent / "validate_pr_description.py",
        validator,
    )
    marker = tmp_path / "shadow-imported"
    (script_dir / "json.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-I", str(validator), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()


@pytest.mark.parametrize("runner", _RUNNERS)
def test_dispatcher_isolated_mode_blocks_pythonpath_injection(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    lookalike = _write_script(repository / "attacker" / "pr" / "new_pr.py")
    attacker = tmp_path / "attacker-modules"
    marker = tmp_path / "dispatcher-imported-attacker"
    attacker.mkdir()
    (attacker / "json.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "raise RuntimeError('attacker json loaded')\n",
        encoding="utf-8",
    )
    env = _environment(
        PYTHONPATH=str(attacker),
        CLAUDE_PROJECT_DIR=str(repository),
        CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
        COPILOT_PLUGIN_ROOT=str(COPILOT_PLUGIN_ROOT),
    )

    result = runner(f"python3 -I '{lookalike}'", repository, env=env)

    assert result.returncode == 2
    assert not marker.exists()


def test_copilot_dispatcher_allows_installed_script_reference(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    body_file = _body_file(repository)

    result = _run_copilot(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        f"--title 'fix: identity gate' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr


def test_copilot_dispatcher_allows_repository_lookalike_after_exclusion(
    tmp_path: Path,
) -> None:
    """Issue #5013: Copilot no longer runs the push-pr identity guard.

    Before #5013 this exact payload was denied on Copilot too (exit 2,
    "push-pr script identity denied"). dispatch_groups.json now marks the
    guard's shim entry ``copilotExclude: true``, generate_hooks_expand.py
    omits it from the Copilot tree, and the committed
    src/copilot-cli/hooks/PreToolUse/_manifest.json carries no guard shim
    (the shim file itself was deleted). Asserting the old denial here would
    test a file that no longer ships; this asserts the current, intentional
    behavior, so a regression that silently reintroduces the shim shows up
    as an unexpected denial instead of passing unnoticed.

    The canonical guard still runs and still denies this exact command on
    the Claude dispatcher: see
    ``test_claude_dispatcher_denies_repository_lookalike`` below.
    """
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    lookalike = _write_script(repository / "attacker" / "pr" / "new_pr.py")

    result = _run_copilot(f"python3 '{lookalike}' --title fix", repository)

    assert result.returncode == 0, f"copilot ran the retired guard and denied: {result.stderr}"


def test_claude_dispatcher_denies_repository_lookalike(
    tmp_path: Path,
) -> None:
    """The canonical Claude guard still denies a repository-controlled lookalike.

    Companion control for the Copilot exclusion above: issue #5013 removed
    the guard from ONE surface only. invoke_dispatch_claude.py does not read
    ``copilotExclude``, so the guard must still run, unchanged, on Claude.
    """
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)
    lookalike = _write_script(repository / "attacker" / "pr" / "new_pr.py")

    result = _run_claude(f"python3 '{lookalike}' --title fix", repository)

    assert result.returncode == 2
    assert "push-pr script identity denied" in result.stderr


def test_copilot_dispatcher_allows_nonmatching_bash(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    (repository / ".git").mkdir(parents=True)

    result = _run_copilot("git status --short", repository)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "runner_lib",
    [
        REPO_ROOT / ".claude" / "lib" / "hook_dispatch_timeout.py",
        COPILOT_PLUGIN_ROOT / "lib" / "hook_dispatch_timeout.py",
    ],
    ids=["claude", "copilot"],
)
def test_timed_shim_launcher_keeps_sibling_imports(runner_lib: Path) -> None:
    """Timed shims must keep their own directory on sys.path.

    `-I` implies `-P`, which drops the script's directory, and every timed shim
    imports its sibling `_bootstrap`. Under `-I` the child died with
    ModuleNotFoundError before its policy ran, so the markdownlint push guard
    was disabled at runtime (issue #4825). `-E -s` keeps the injection
    protection (no PYTHONPATH, no user site-packages) without dropping the
    script directory.
    """
    source = runner_lib.read_text(encoding="utf-8")

    assert '"-E", "-s"' in source, f"{runner_lib.name} lost the -E -s launcher flags"
    assert '"-I", str(shim_path)' not in source, (
        f"{runner_lib.name} launches timed shims with -I, which breaks sibling imports"
    )


def test_timed_shim_launcher_ignores_pythonpath(tmp_path: Path) -> None:
    """The launcher flags still block PYTHONPATH injection.

    Negative control for the flag change above: an attacker directory on
    PYTHONPATH must not reach the child's sys.path.
    """
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    probe = f"import sys;print(int({str(attacker)!r} in sys.path))"
    env = _environment(PYTHONPATH=str(attacker))

    isolated = subprocess.run(
        [sys.executable, "-E", "-s", "-c", probe],
        capture_output=True, encoding="utf-8", errors="replace", env=env,
        timeout=60, check=True,
    ).stdout.strip()
    control = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, encoding="utf-8", errors="replace", env=env,
        timeout=60, check=True,
    ).stdout.strip()

    assert isolated == "0", "-E -s let PYTHONPATH through"
    assert control == "1", "negative control did not honor PYTHONPATH"


def test_push_pr_command_grants_no_unrestricted_write() -> None:
    """/push-pr must not pre-approve unrestricted Write.

    It reads untrusted repository diffs and already holds git add, commit and
    push, so a pre-approved Write would let a prompt-injected diff redirect the
    body write to a source or hook file and publish it (issue #4825). The host
    prompts for the single .agents/scratch body write instead, which is the
    posture this command shipped with before the scratch-path change.
    """
    for path in (
        REPO_ROOT / ".claude" / "commands" / "push-pr.md",
        COPILOT_PLUGIN_ROOT / "skills" / "push-pr" / "SKILL.md",
    ):
        line = next(
            entry
            for entry in path.read_text(encoding="utf-8").splitlines()
            if entry.startswith("allowed-tools:")
        )
        granted = {item.strip() for item in line.removeprefix("allowed-tools:").split(",")}

        assert "Write" not in granted, f"{path.name} pre-approves unrestricted Write"
        assert "Bash(mkdir:-p .agents/scratch)" in granted, (
            f"{path.name} lost the narrow scratch-directory grant"
        )




def test_guard_removes_its_module_directory_from_sys_path() -> None:
    """The guard must not leave the hooks directory importable after it loads.

    Copilot CLI runs every registered shim for an event inside ONE process, so
    a `sys.path` entry the guard adds outlives the guard. The hooks directory
    holds files a plugin install writes, and leaving it ahead of the stdlib
    would let a file dropped there shadow `hashlib` or `subprocess` for the
    shims that run next.

    The entry is needed only while the sibling modules import, and every one
    of them imports its dependencies at module scope, so nothing resolves by
    name afterward.
    """
    guard_directory = str(CLAUDE_GUARD.parent)
    probe = (
        "import json, sys;"
        "spec = __import__('importlib.util', fromlist=['util']).spec_from_file_location("
        "'guard_under_test', sys.argv[1]);"
        "module = __import__('importlib.util', fromlist=['util']).module_from_spec(spec);"
        "spec.loader.exec_module(module);"
        "print(json.dumps(sys.argv[2] in sys.path))"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(CLAUDE_GUARD), guard_directory],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "false", (
        f"guard left {guard_directory} on sys.path: {result.stdout!r}"
    )


def test_guard_keeps_a_dispatcher_owned_sys_path_entry() -> None:
    """Removing the entry unconditionally would consume one the guard did not add.

    The Copilot dispatcher inserts the event directory itself before it runs
    any shim, so in that arrangement the guard never inserts. A removal keyed
    on position rather than on ownership deleted the dispatcher's entry, and
    nothing broke only because `_dispatch.py` happens to insert it twice.
    """
    guard_directory = str(CLAUDE_GUARD.parent)
    probe = (
        "import json, sys;"
        "sys.path.insert(0, sys.argv[2]);"
        "spec = __import__('importlib.util', fromlist=['util']).spec_from_file_location("
        "'guard_under_test', sys.argv[1]);"
        "module = __import__('importlib.util', fromlist=['util']).module_from_spec(spec);"
        "spec.loader.exec_module(module);"
        "print(json.dumps(sys.path.count(sys.argv[2])))"
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", probe, str(CLAUDE_GUARD), guard_directory],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1", (
        f"guard consumed a sys.path entry it did not add: {result.stdout!r}"
    )
