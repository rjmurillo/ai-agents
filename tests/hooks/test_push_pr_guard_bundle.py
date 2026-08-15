"""Runtime bundle, interpreter floor, and pinned-digest tests.

Split from the former single ``tests/hooks/test_push_pr_script_identity_guard.py``
(issue #4764), which had grown to 2,077 lines and carried the whole policy
matrix for both harnesses in one module. Dispatcher runners, the payload shape,
and the temporary repository layout live in
``tests/hooks/push_pr_guard_harness.py`` so no module re-derives them.

Every case runs through BOTH dispatchers, because the guard ships twice: once
as the canonical Claude hook and once as the generated Copilot matcher shim.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.hooks.push_pr_guard_harness import (
    _COPILOT_SHIM,
    CLAUDE_PLUGIN_ROOT,
    COPILOT_PLUGIN_ROOT,
    PLUGIN_SCRIPT_REFERENCE,
    REPO_ROOT,
    SCRIPT_RELATIVE,
)
from tests.hooks.push_pr_guard_harness import (
    body_file as _body_file,
)
from tests.hooks.push_pr_guard_harness import (
    environment as _environment,
)
from tests.hooks.push_pr_guard_harness import (
    payload as _payload,
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
    run_guard_script as _run_guard_script,
)

IN_SCOPE_ASSIGNMENT = "PUSH_PR_SCRIPT=new_pr.py "

# The guard ships as one runtime unit: the dispatched entrypoint plus the
# ``_push_pr_guard_*`` siblings it imports (issue #4764). Anything that copies,
# reads, or interpreter-checks "the guard" has to cover the whole unit, or it
# checks a file that cannot run on its own.
GUARD_MODULE_GLOB = "_push_pr_guard_*.py"


def _guard_unit(guard: Path) -> tuple[Path, ...]:
    """Return the entrypoint and every sibling module it imports."""
    return (guard, *sorted(guard.parent.glob(GUARD_MODULE_GLOB)))


def _install_guard_unit(guard: Path, destination: Path) -> Path:
    """Copy the whole runtime unit next to ``destination`` and return the entry."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    for member in _guard_unit(guard):
        shutil.copy2(member, destination.parent / member.name)
    return destination.parent / guard.name


def _in_scope(command: str) -> str:
    """Return ``command`` placed inside the guard's relevance scope."""
    if "new_pr.py" in command:
        return command
    return IN_SCOPE_ASSIGNMENT + command


def test_claude_allows_runtime_script_literal(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    script = CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE
    body_file = _body_file(repository)

    result = _run_claude(
        f"python3 -I '{script}' --title 'fix: identity gate' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_claude_denies_repository_script_relative_path(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)

    result = _run_claude(
        "python3 -I .claude/skills/github/scripts/pr/new_pr.py "
        "--title 'fix: identity gate' --body-file body.md",
        repository,
    )

    assert result.returncode == 2
    assert "exact runtime new_pr.py path" in result.stderr


def test_claude_allows_installed_plugin_reference(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)

    result = _run_claude(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        f"--title 'fix: identity gate' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 0, result.stderr


def _minimum_supported_interpreter() -> str | None:
    """Return a Python 3.10 interpreter path, or None when none is installed.

    The generated launchers accept any interpreter at 3.10 or newer, so 3.10 is
    the floor the shipped guard must actually run on.
    """
    for candidate in ("python3.10", "python3.11"):
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    uv = shutil.which("uv")
    if uv is None:
        return None
    result = subprocess.run(
        [uv, "python", "find", "3.10"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    path = result.stdout.strip()
    return path if result.returncode == 0 and path and Path(path).is_file() else None


@pytest.mark.parametrize(
    ("guard", "plugin_root"),
    [
        (
            REPO_ROOT
            / ".claude"
            / "hooks"
            / "PreToolUse"
            / "invoke_push_pr_script_identity_guard.py",
            CLAUDE_PLUGIN_ROOT,
        ),
        (
            COPILOT_PLUGIN_ROOT
            / "hooks"
            / "PreToolUse"
            / _COPILOT_SHIM,
            COPILOT_PLUGIN_ROOT,
        ),
    ],
    ids=["claude", "copilot"],
)
def test_guards_run_on_the_minimum_supported_interpreter(
    tmp_path: Path,
    guard: Path,
    plugin_root: Path,
) -> None:
    """The guard must run on Python 3.10, the floor the launchers accept.

    `hashlib.file_digest` landed in 3.11. On 3.10 the digest check raised
    AttributeError and the guard exited 1, which a PreToolUse host treats as a
    hook error rather than a block, so the identity gate silently stopped
    enforcing. Reproduced on cpython 3.10.20 before the fix (issue #4825).
    """
    interpreter = _minimum_supported_interpreter()
    if interpreter is None:
        pytest.skip("no Python 3.10 or 3.11 interpreter available")
    version = subprocess.run(
        [interpreter, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
        capture_output=True, encoding="utf-8", errors="replace", check=True, timeout=60,
    ).stdout.strip()
    repository, _ = _repository(tmp_path)
    # Each guard anchors trust to the plugin tree it ships in.
    script = plugin_root / SCRIPT_RELATIVE
    body_file = _body_file(repository)

    cases = (
        (f"python3 -I '{script}' --title 'fix: floor' --body-file {body_file}", 0),
        ("python3 -I attacker/pr/new_pr.py", 2),
        ("git status && git diff", 0),
    )
    for command, expected in cases:
        result = subprocess.run(
            [interpreter, "-I", str(guard)],
            input=_payload(command, repository),
            cwd=repository,
            env=_environment(),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        assert result.returncode == expected, (
            f"python {version}: {command} exited {result.returncode}: {result.stderr}"
        )
        assert "Traceback" not in result.stderr, f"python {version}: {result.stderr}"


@pytest.mark.parametrize(
    "guard",
    [
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        COPILOT_PLUGIN_ROOT
        / "hooks"
        / "PreToolUse"
        / _COPILOT_SHIM,
    ],
    ids=["claude", "copilot"],
)
def test_guards_do_not_use_post_310_hashlib_api(guard: Path) -> None:
    """Pin the specific API that broke the 3.10 floor.

    The runtime test above skips when no 3.10 interpreter is installed, which
    is the common case on a 3.14 developer machine and in CI. This assertion
    always runs, so the regression cannot return unnoticed.

    Every member of the runtime unit is read, not just the entrypoint. The
    digest code moved into ``_push_pr_guard_identity.py`` when the guard was
    split, so an entrypoint-only check would now pass while the call it exists
    to forbid sits one import away.
    """
    for member in _guard_unit(guard):
        source = member.read_text(encoding="utf-8")

        assert "hashlib.file_digest(" not in source, (
            f"{member.name} calls hashlib.file_digest, which does not exist on Python 3.10"
        )


def test_trusted_digests_match_the_shipped_bundle() -> None:
    """The pinned digests must equal the files they gate, on both surfaces.

    `_validate_runtime_bundle` denies every push-pr invocation whose new_pr.py
    or validate_pr_description.py digest differs from the pinned constant. A
    stale constant therefore wedges `/push-pr` for every user with no other
    signal, and nothing else in the tree recomputes it. This is that gate.

    The constants live in the ``_push_pr_guard_identity`` member of the runtime
    unit, so the search covers every member rather than the entrypoint alone.
    """
    expected = {
        "_TRUSTED_NEW_PR_SHA256": CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE,
        "_TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256": (
            CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent / "validate_pr_description.py"
        ),
        # Joined the bundle in issue #4764 when new_pr.py was split for
        # cohesion. new_pr.py loads it by absolute path at import time, so an
        # unpinned sibling would be an unverified code path inside the script
        # the guard exists to verify.
        "_TRUSTED_PR_VALIDATIONS_SHA256": (
            CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE.parent / "pr_validations.py"
        ),
    }
    guards = (
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        COPILOT_PLUGIN_ROOT
        / "hooks"
        / "PreToolUse"
        / _COPILOT_SHIM,
    )

    for guard in guards:
        source = "\n".join(member.read_text(encoding="utf-8") for member in _guard_unit(guard))
        for constant, target in expected.items():
            match = re.search(rf'{constant} = \(?\s*"([0-9a-f]{{64}})"', source)
            assert match is not None, f"{guard.name} does not pin {constant}"
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            assert match.group(1) == digest, (
                f"{guard.name}:{constant} is stale; {target.name} now hashes to {digest}"
            )


def test_guard_denies_modified_runtime_helper(tmp_path: Path) -> None:
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)
    runtime_root = tmp_path / "runtime" / ".claude"
    guard = runtime_root / "hooks" / "PreToolUse" / ("invoke_push_pr_script_identity_guard.py")
    script_dir = runtime_root / SCRIPT_RELATIVE.parent
    script_dir.mkdir(parents=True)
    _install_guard_unit(
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        guard,
    )
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, script_dir / "new_pr.py")
    (script_dir / "validate_pr_description.py").write_text(
        "raise SystemExit('attacker helper ran')\n",
        encoding="utf-8",
    )

    result = _run_guard_script(
        guard,
        f"python3 -I '{script_dir / 'new_pr.py'}' "
        f"--title 'fix: helper identity' --body-file {body_file}",
        repository,
    )

    assert result.returncode == 2
    assert "does not match the trusted plugin copy" in result.stderr


def test_guard_fails_closed_without_its_runtime_modules(tmp_path: Path) -> None:
    """An entrypoint installed without its siblings must block, never allow.

    The split made the guard a multi-file unit, so a partial install is now
    possible where it was not before. The generator publishes the owner and its
    companions in one transaction to prevent that, but the runtime behavior
    still has to be the safe one: an ImportError has to deny, because a guard
    that cannot load has verified nothing.
    """
    repository, _ = _repository(tmp_path)
    body_file = _body_file(repository)
    runtime_root = tmp_path / "partial" / ".claude"
    guard = runtime_root / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py"
    guard.parent.mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py",
        guard,
    )
    script_dir = runtime_root / SCRIPT_RELATIVE.parent
    script_dir.mkdir(parents=True)
    shutil.copy2(CLAUDE_PLUGIN_ROOT / SCRIPT_RELATIVE, script_dir / "new_pr.py")

    result = _run_guard_script(
        guard,
        f"python3 -I '{script_dir / 'new_pr.py'}' "
        f"--title 'fix: partial install' --body-file {body_file}",
        repository,
    )

    assert result.returncode != 0, "a guard that cannot import its own modules must not allow"


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
@pytest.mark.parametrize(
    "arguments",
    [
        "--title 'fix: exfil' --body-file /etc/hosts",
        "--title 'fix: traversal' --body-file .agents/scratch/../../secret",
        "--title 'fix: nested' --body-file .agents/scratch/leak/hosts.md",
        "--title 'fix: bypass' --body-file .agents/scratch/body.md --skip-validation",
    ],
)
def test_dispatchers_deny_noncanonical_new_pr_arguments(
    tmp_path: Path,
    runner,
    arguments: str,
) -> None:
    repository, _ = _repository(tmp_path)
    _body_file(repository)

    result = runner(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" {arguments}',
        repository,
    )

    assert result.returncode == 2
    assert "push-pr script identity denied" in result.stderr


@pytest.mark.parametrize("runner", [_run_claude, _run_copilot])
def test_dispatchers_deny_hardlinked_body_file(
    tmp_path: Path,
    runner,
) -> None:
    repository, _ = _repository(tmp_path)
    body_file = repository / _body_file(repository)
    secret = repository / "secret.md"
    secret.write_text("secret\n", encoding="utf-8")
    body_file.unlink()
    try:
        os.link(secret, body_file)
    except OSError as exc:
        pytest.skip(f"hardlinks unavailable: {exc}")

    result = runner(
        f'python3 -I "{PLUGIN_SCRIPT_REFERENCE}" '
        "--title 'fix: hardlink' --body-file .agents/scratch/body.md",
        repository,
    )

    assert result.returncode == 2
    assert "single-link regular file" in result.stderr


