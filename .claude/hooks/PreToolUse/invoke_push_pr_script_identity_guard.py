#!/usr/bin/env python3
"""Deny noncanonical push-pr Python entrypoints (issue #4764).

Exit codes:
    0 = allow
    2 = block

Scope (relevance gate, issue #4825 review 4894113215)
-----------------------------------------------------
The host registers this guard on the plugin-wide ``Bash`` matcher, so it runs
on every Bash command. It therefore decides relevance BEFORE it decides policy.
``_command_is_in_scope`` runs first and returns 0 (allow, non-blocking) for any
command that cannot reach ``new_pr.py``. A command is in scope only when:

A. Its text names ``new_pr.py`` after line-continuation removal, quote,
   whitespace, ``+`` and backslash compaction, path-separator normalization,
   and bounded brace expansion; or
B. it is a Python invocation whose script operand carries shell expansion, so
   the guard cannot statically prove the operand is not ``new_pr.py``; or
C. one of its operands resolves to a regular file whose bytes match the trusted
   ``new_pr.py`` (a renamed copy).

Everything else, including ``git status && git diff``, ``bash -c``, Node, Perl,
unrelated Python scripts, ``python3 -m pytest`` and Git commands in a
repository with active hooks, is out of scope and passes untouched.

Residual risk (accepted, not a defect)
--------------------------------------
A command that reconstructs the path at runtime without naming it, for example
``python3 -c`` with a hex-decoded path or ``git clone ext::sh -c <payload>``
that never spells ``new_pr.py``, is outside the detection surface. This guard
bounds the identity of *named* push-pr invocations. It is not a Python or shell
sandbox: an actor able to run arbitrary code does not need ``new_pr.py`` to
open a pull request. Widening the scope to cover that case is what wedged every
unrelated Bash command, which is a larger, certain harm than the residual.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

# The guard ships as one runtime unit: this entrypoint plus the
# ``_push_pr_guard_*`` siblings the generator copies next to it. Resolving the
# directory from ``__file__`` is what makes the unit work on both harnesses.
# Claude runs this file directly; Copilot CLI inlines this body into a
# generated matcher shim that lives in the SAME directory, so ``__file__``
# names the shim and the siblings still resolve. Stdlib imports above run
# first so a sibling can never shadow one.
_GUARD_DIRECTORY = str(Path(__file__).resolve().parent)
_GUARD_DIRECTORY_INSERTED = _GUARD_DIRECTORY not in sys.path
if _GUARD_DIRECTORY_INSERTED:
    sys.path.insert(0, _GUARD_DIRECTORY)

from _push_pr_guard_commands import (  # noqa: E402
    _effective_command,
    _effective_command_index,
    _execution_target,
    _is_python_interpreter,
    _python_arguments,
    _resolves_to_installed_command,
)
from _push_pr_guard_evaluators import (  # noqa: E402
    _contains_dangerous_loader_environment,
    _contains_dynamic_evaluator,
    _contains_shell_evaluator,
)
from _push_pr_guard_identity import (  # noqa: E402
    _SCRIPT_RELATIVE_PATH,
    _regular_resolved_file,
    _runtime_script,
    _validate_runtime_bundle,
)
from _push_pr_guard_lex import (  # noqa: E402
    GuardViolationError,
    ShellToken,
    _command_name,
    _contains_active_parameter_expansion,
    _contains_active_shell_expansion,
    _contains_shell_expansion,
    _could_target_new_pr,
    _split_command,
)
from _push_pr_guard_scope import _command_is_in_scope  # noqa: E402
from _push_pr_guard_tables import _EXPANSION_SAFE_COMMANDS, _SHELL_EVALUATORS  # noqa: E402

# The entry is removed only when this file added it. Every module above
# imports its own dependencies at module scope, so nothing else needs to
# resolve by name after this point, and Copilot CLI runs several shims inside
# ONE process: leaving an entry this file added would let a file dropped in
# the hooks directory shadow a stdlib module for the shims that run next.
# Removing unconditionally would instead consume the dispatcher's own entry,
# which this guard does not own.
if _GUARD_DIRECTORY_INSERTED and _GUARD_DIRECTORY in sys.path:
    sys.path.remove(_GUARD_DIRECTORY)

_MAX_STDIN_BYTES = 128 * 1024

_PLUGIN_SCRIPT_REFERENCE = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr/new_pr.py"
)

_MAX_POLICY_TOKENS = 256


def _read_request() -> tuple[str, Path]:
    raw = sys.stdin.read(_MAX_STDIN_BYTES + 1)
    if len(raw) > _MAX_STDIN_BYTES:
        raise GuardViolationError("hook input exceeds 128 KiB")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise GuardViolationError("hook input is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise GuardViolationError("hook input is not a JSON object")

    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        raise GuardViolationError("tool_input is missing or invalid")
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        raise GuardViolationError("Bash command is missing or invalid")

    cwd_value = payload.get("cwd")
    if cwd_value is None:
        return command, Path.cwd().resolve()
    if not isinstance(cwd_value, str) or not cwd_value.strip():
        raise GuardViolationError("hook cwd is invalid")
    cwd = Path(cwd_value)
    if not cwd.is_absolute():
        cwd = Path.cwd() / cwd
    return command, cwd.resolve()


def _requires_identity_check(command: str, cwd: Path) -> bool:
    joined = command.replace("\\\r\n", "").replace("\\\n", "")
    compacted = joined.casefold().translate(str.maketrans("", "", "'\"+ \t\\"))
    if "new_pr.py" in compacted:
        return True
    if ".py" in compacted:
        return True
    tokens = _split_command(command)
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        return True
    if any(
        _command_name(token.value) in _SHELL_EVALUATORS
        and (
            _command_name(token.value) == "eval"
            or any(option.value == "-c" for option in tokens[index + 1 :])
        )
        for index, token in enumerate(tokens)
    ):
        return True
    if not _contains_shell_expansion(command):
        return False
    command_index = _effective_command_index(tokens)
    if command_index is None:
        return True
    effective_command = tokens[command_index]
    if _contains_shell_expansion(effective_command.raw):
        return True
    if not _resolves_to_installed_command(
        tokens,
        command_index,
        cwd,
        _EXPANSION_SAFE_COMMANDS,
    ):
        return True
    return any(_contains_active_parameter_expansion(token.raw) for token in tokens)


def _targets_new_pr(tokens: list[ShellToken], cwd: Path) -> bool:
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        target, dynamic = _execution_target(arguments)
        if target is not None and (
            _could_target_new_pr(target.value) or _could_target_new_pr(target.raw)
        ):
            return True
        if dynamic and any(
            _could_target_new_pr(argument.value) or _could_target_new_pr(argument.raw)
            for argument in arguments
        ):
            return True
        return any(
            token.value.startswith("PYTHONSTARTUP=")
            and _could_target_new_pr(token.value.partition("=")[2])
            for token in tokens
        )

    target_mentioned = any(
        _could_target_new_pr(token.value) or _could_target_new_pr(token.raw) for token in tokens
    )
    python_mentioned = any(
        _is_python_interpreter(token.value)
        or "python" in token.value.casefold()
        or "pypy" in token.value.casefold()
        for token in tokens
    )
    dynamic_command = any(
        any(marker in token.raw for marker in ("$", "*", "?", "[", "{", "\\\n")) for token in tokens
    )
    command = _effective_command(tokens)
    direct_command = command is not None and (
        _could_target_new_pr(command.value) or _could_target_new_pr(command.raw)
    )
    return target_mentioned and (python_mentioned or dynamic_command or direct_command)


def _interpreter_offset(tokens: list[ShellToken], cwd: Path) -> int:
    """Return the token index of ``python3`` after skipping env/wrappers."""
    index = _effective_command_index(tokens)
    if index is None:
        raise GuardViolationError("new_pr.py must run with python3 -I")
    return index


def _script_reference(tokens: list[ShellToken], cwd: Path) -> ShellToken:
    offset = _interpreter_offset(tokens, cwd)
    values = [token.value for token in tokens]
    if len(tokens) < offset + 3 or values[offset : offset + 2] != ["python3", "-I"]:
        raise GuardViolationError("new_pr.py must run with python3 -I")
    script_reference = tokens[offset + 2]
    if script_reference.value.startswith("-"):
        raise GuardViolationError("new_pr.py script path is missing")
    if script_reference.value != _PLUGIN_SCRIPT_REFERENCE and any(
        marker in script_reference.raw for marker in ("$", "`", "\\\n", "{", "[", "*", "?")
    ):
        raise GuardViolationError("new_pr.py script path cannot use shell expansion")
    args_start = offset + 3
    if any(("$" in token.raw or "`" in token.raw) for token in tokens[args_start:]):
        raise GuardViolationError("argument substitution is not allowed")
    if any(_contains_active_shell_expansion(token.raw) for token in tokens[args_start:]):
        raise GuardViolationError("argument shell expansion is not allowed")
    return script_reference


def _validate_new_pr_arguments(tokens: list[ShellToken], cwd: Path, offset: int) -> None:
    args_start = offset + 3
    values = _new_pr_option_values(tokens, args_start)
    option_keys = set(values)
    if option_keys == {"--prepare-body-file"}:
        # Prepare mode: no further validation needed
        return
    if option_keys != {"--title", "--body-file"}:
        raise GuardViolationError(
            "new_pr.py requires exactly --title and --body-file, "
            "or --prepare-body-file alone"
        )
    if not values["--title"].strip():
        raise GuardViolationError("new_pr.py title cannot be empty")
    _validate_new_pr_body_file(values["--body-file"], cwd)


def _new_pr_option_values(tokens: list[ShellToken], args_start: int) -> dict[str, str]:
    """Return the option/value pairs, rejecting anything outside the allowlist."""
    _ALLOWED_OPTIONS = {"--title", "--body-file", "--prepare-body-file"}
    values: dict[str, str] = {}
    index = args_start
    while index < len(tokens):
        option = tokens[index].value
        if option not in _ALLOWED_OPTIONS:
            raise GuardViolationError(
                "new_pr.py accepts only --title, --body-file, "
                "or --prepare-body-file here"
            )
        if option == "--prepare-body-file":
            values[option] = ""
            index += 1
            continue
        if option in values or index + 1 >= len(tokens):
            raise GuardViolationError(
                f"new_pr.py option {option} is duplicate or missing its value"
            )
        values[option] = tokens[index + 1].value
        index += 2
    return values


def _validate_new_pr_body_file(reference: str, cwd: Path) -> None:
    """Require one single-link regular .md file directly under .agents/scratch."""
    body_reference = Path(reference)
    if (
        body_reference.is_absolute()
        or len(body_reference.parts) != 3
        or body_reference.parts[:2] != (".agents", "scratch")
        or body_reference.suffix.casefold() != ".md"
    ):
        raise GuardViolationError(
            "new_pr.py body file must be one .md file directly under .agents/scratch"
        )
    if ".." in body_reference.parts:
        raise GuardViolationError("new_pr.py body file cannot traverse parent directories")
    body_path = cwd / body_reference
    for parent in (cwd / ".agents", cwd / ".agents" / "scratch"):
        if parent.is_symlink():
            raise GuardViolationError("new_pr.py body file parent cannot be a symlink")
    try:
        body_stat = body_path.lstat()
    except OSError as exc:
        raise GuardViolationError("new_pr.py body file must be an existing regular file") from exc
    if body_path.is_symlink() or not stat.S_ISREG(body_stat.st_mode) or body_stat.st_nlink != 1:
        raise GuardViolationError("new_pr.py body file must be a single-link regular file")


def _script_path(script_reference: ShellToken, cwd: Path) -> Path:
    if script_reference.value == _PLUGIN_SCRIPT_REFERENCE:
        if script_reference.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"':
            raise GuardViolationError(
                "plugin script reference must use the exact double-quoted form"
            )
        configured_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get(
            "CLAUDE_PLUGIN_ROOT"
        )
        root = Path(configured_root) if configured_root is not None else cwd / ".claude"
        if not root.is_absolute():
            root = cwd / root
        path = root / _SCRIPT_RELATIVE_PATH
    else:
        if "$" in script_reference.raw or "`" in script_reference.raw:
            raise GuardViolationError("script path substitution is not allowed")
        path = Path(script_reference.value)
        runtime_script = _runtime_script()
        if runtime_script is None or not path.is_absolute() or path != runtime_script:
            raise GuardViolationError(
                "literal script path must be the exact runtime new_pr.py path"
            )

    resolved = _regular_resolved_file(path)
    if resolved is None:
        raise GuardViolationError("script path is missing, unreadable, or a symlink")
    return resolved


def _deny(reason: str) -> int:
    print(
        f"push-pr script identity denied: {reason}.\n"
        "Remediation: use the exact documented form:\n"
        '  python3 -I "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}'
        '/skills/github/scripts/pr/new_pr.py" --prepare-body-file\n'
        "or with --title and --body-file for PR creation.",
        file=sys.stderr,
    )
    return 2


def _reject_execution_wrappers(tokens: list[ShellToken], cwd: Path) -> None:
    """Deny the wrapper families that can run code the guard cannot read."""
    if _contains_dangerous_loader_environment(tokens):
        raise GuardViolationError("dynamic loader environment variables are not allowed")
    if _contains_shell_evaluator(tokens, cwd):
        raise GuardViolationError("shell evaluator wrappers are not allowed")
    if _contains_dynamic_evaluator(tokens, cwd):
        raise GuardViolationError("dynamic evaluator wrappers are not allowed")


def _reject_unsupported_python_target(arguments: list[ShellToken]) -> None:
    """Deny ``-c``/``-m`` launchers and expansion-bearing script operands."""
    target, dynamic = _execution_target(arguments)
    if dynamic:
        raise GuardViolationError("dynamic Python -c and -m launchers are not allowed")
    if (
        target is not None
        and _contains_shell_expansion(target.raw)
        and target.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"'
    ):
        raise GuardViolationError("Python script paths cannot use shell expansion")


def _verify_new_pr_invocation(command: str, tokens: list[ShellToken], cwd: Path) -> None:
    """Require the command to be an exact, approved new_pr.py invocation."""
    arguments = _python_arguments(tokens, cwd)
    if _contains_shell_expansion(command) and arguments is None:
        raise GuardViolationError(
            "shell-expanded commands outside the exact allowlist are not allowed"
        )
    if arguments is not None:
        _reject_unsupported_python_target(arguments)
    if not _targets_new_pr(tokens, cwd):
        if arguments is not None:
            raise GuardViolationError("Python execution is limited to the approved new_pr.py")
        raise GuardViolationError("command references new_pr.py through an unsupported launcher")
    script = _script_path(_script_reference(tokens, cwd), cwd)
    if script != _runtime_script():
        raise GuardViolationError("resolved script is not an approved new_pr.py")
    _validate_runtime_bundle(script)
    offset = _interpreter_offset(tokens, cwd)
    _validate_new_pr_arguments(tokens, cwd, offset)


def main() -> int:
    try:
        command, cwd = _read_request()
        if not _command_is_in_scope(command, cwd):
            return 0
        tokens = _split_command(command)
        if len(tokens) > _MAX_POLICY_TOKENS:
            # In scope and too large to verify. The canonical invocation is
            # seven tokens; nothing legitimate reaches this. Denying here keeps
            # the policy off inputs that cost more than the host's 10s timeout,
            # where a Copilot timeout fails open (issue #4825).
            raise GuardViolationError("command has too many arguments to verify")
        _reject_execution_wrappers(tokens, cwd)
        if not _requires_identity_check(command, cwd):
            return 0
        _verify_new_pr_invocation(command, tokens, cwd)
        return 0
    except GuardViolationError as exc:
        return _deny(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
