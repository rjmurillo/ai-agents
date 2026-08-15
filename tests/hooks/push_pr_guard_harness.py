"""Shared harness for the push-pr script identity guard tests (issue #4764).

Extracted from ``tests/hooks/test_push_pr_script_identity_guard.py`` so the
guard's test suite can be split across cohesive modules without each one
re-deriving the dispatcher invocation, the payload shape, or the temporary
repository layout. Every helper here was moved verbatim in behavior; the only
change is that they now live in one place instead of being copied per module.

Two dispatchers run the same guard, so both runners live here together:

* ``run_claude`` drives ``.claude/hooks/invoke_dispatch_claude.py --group
  plugin-pretooluse-9-push_pr_script_identity``.
* ``run_copilot`` drives ``src/copilot-cli/hooks/PreToolUse/_dispatch.py``.

The Copilot dispatcher rejects a payload without a string ``tool_name``
(measured: ``matcher-shim [Bash]: dispatch error: hook input missing string
`tool_name`/`toolName` field``, exit 2), so ``payload`` always emits it. A
harness that omitted it would report exit 2 for every command and read as a
denial on both harnesses regardless of guard behavior.

Issue #5013 retired the guard from the generated Copilot shim tree
(dispatch_groups.json marks it ``copilotExclude``), so the guard now runs on
only one of the two dispatchers. ``RUNNERS`` below is what guard-policy tests
should parametrize over; ``run_copilot`` stays exported for tests that check
the Copilot dispatcher's own behavior rather than this guard's decisions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DISPATCHER = REPO_ROOT / ".claude" / "hooks" / "invoke_dispatch_claude.py"
COPILOT_DISPATCHER = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse" / "_dispatch.py"
CLAUDE_PLUGIN_ROOT = REPO_ROOT / ".claude"
COPILOT_PLUGIN_ROOT = REPO_ROOT / "src" / "copilot-cli"
GROUP = "plugin-pretooluse-9-push_pr_script_identity"
# Fixed argument vectors. Both runners execute one constant dispatcher path;
# nothing a caller supplies reaches argv, only stdin, cwd, and the environment.
_CLAUDE_ARGV = [sys.executable, "-I", str(CLAUDE_DISPATCHER), "--group", GROUP]
SCRIPT_RELATIVE = Path("skills/github/scripts/pr/new_pr.py")
REPOSITORY_SCRIPT = Path(".claude") / SCRIPT_RELATIVE
PLUGIN_SCRIPT_REFERENCE = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py"
)

CLAUDE_GUARD = (
    REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_push_pr_script_identity_guard.py"
)
# Issue #5013: the generated Copilot matcher shim for this guard was retired
# (dispatch_groups.json marks the shim copilotExclude, so the generator omits
# it). There is no COPILOT_GUARD path anymore; the guard now ships only on the
# Claude side. Do not reintroduce a constant that points at a generated file,
# and do not point a "copilot" test at CLAUDE_GUARD to fake parity: #5013
# removed the Copilot copy, it did not relocate it.


def write_script(path: Path) -> Path:
    """Write a lookalike new_pr.py.

    Carries the real script's ``#!/usr/bin/env python3`` shebang. Without it the
    fixture is not a faithful lookalike: the guard classifies interpreters by
    reading shebangs, so a shebang-less fixture takes a different path through
    the relevance rules than the file it stands in for, and a test can pass
    because the fixture is wrong rather than because the guard is right.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env python3\nprint('new pr')\n", encoding="utf-8")
    return path


def repository(tmp_path: Path) -> tuple[Path, Path]:
    """Create a temporary repository containing a lookalike new_pr.py."""
    root = tmp_path / "repository"
    (root / ".git").mkdir(parents=True)
    return root, write_script(root / REPOSITORY_SCRIPT)


def body_file(root: Path) -> Path:
    path = root / ".agents" / "scratch" / "body.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Pull request\n", encoding="utf-8")
    return path.relative_to(root)


def payload(command: object, cwd: Path) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})


def environment(**updates: str) -> dict[str, str]:
    env = os.environ.copy()
    for name in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        env.pop(name, None)
    env.update(updates)
    return env


# Hook payloads the dispatcher must reject. They live here, with the code that
# builds a well-formed payload, because the malformed shapes are defined by the
# same contract: a test that spelled them inline would drift from `payload` the
# first time that contract changed. Callers name a case by id, so nothing a
# test supplies reaches a subprocess, which is also what keeps the taint
# scanner's command-injection rule from firing on a stdin string.
INVALID_REQUESTS: dict[str, str] = {
    "empty": "",
    "array": "[]",
    "object": "{}",
    "missing-command": '{"tool_input": {}}',
    "non-string-command": '{"tool_input": {"command": 7}}',
    "non-string-cwd": '{"tool_input": {"command": "python3 x/pr/new_pr.py"}, "cwd": 7}',
    "oversize": "x" * (128 * 1024 + 1),
}


def run_claude_invalid(
    request_id: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Drive the Claude dispatcher with one named malformed payload."""
    return subprocess.run(
        _CLAUDE_ARGV,
        input=INVALID_REQUESTS[request_id],
        cwd=cwd,
        env=environment(
            CLAUDE_PROJECT_DIR=str(cwd),
            CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
        ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def run_claude(
    command: object,
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    stdin = payload(command, cwd)
    dispatch_environment = env or environment(
        CLAUDE_PROJECT_DIR=str(cwd),
        CLAUDE_PLUGIN_ROOT=str(CLAUDE_PLUGIN_ROOT),
    )
    return subprocess.run(
        _CLAUDE_ARGV,
        input=stdin,
        cwd=cwd,
        env=dispatch_environment,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def run_copilot(
    command: str,
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(COPILOT_DISPATCHER)],
        input=payload(command, cwd),
        cwd=cwd,
        env=env
        or environment(
            COPILOT_PLUGIN_ROOT=str(COPILOT_PLUGIN_ROOT),
        ),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def run_guard_script(
    guard: Path,
    command: str,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", str(guard)],
        input=payload(command, cwd),
        cwd=cwd,
        env=environment(),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def run_both(command: str, cwd: Path) -> dict[str, subprocess.CompletedProcess[str]]:
    """Run one command through both dispatchers.

    Returned as a mapping so an assertion failure names the harness that
    disagreed instead of reporting an anonymous tuple index.
    """
    return {"claude": run_claude(command, cwd), "copilot": run_copilot(command, cwd)}


# Issue #5013: the push-pr identity guard is copilotExclude in
# dispatch_groups.json, so build/scripts/generate_hooks_expand.py never emits
# it into the Copilot shim tree. invoke_dispatch_claude.py does not read
# copilotExclude, so the guard keeps running unchanged on the Claude side.
# Guard POLICY assertions (deny/allow decisions the guard itself makes)
# therefore only have a runner to test on Claude; parametrizing them over
# run_copilot would either fail (the Copilot dispatcher no longer denies
# anything the guard used to deny) or pass vacuously (an "allow" the guard
# never decided, because nothing dispatches to it). RUNNERS is the single
# place that set narrows to, so a future guard retired from the other surface
# only has to change here.
#
# run_copilot itself is still exported and still used directly by tests that
# check the Copilot dispatcher's OWN behavior (it allows an unrelated
# command, it still runs its remaining shims) rather than this guard's
# policy.
RUNNERS = (run_claude,)
