#!/usr/bin/env python3
# Standalone hook must carry its parser and policy into one generated shim.
# taste-lint: ignore file-size, splitting would break cross-harness parity.
# Parser branches preserve distinct lexical states and fail-closed reasons.
# taste-lint: ignore complexity, flattening would merge security decisions.
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

import fnmatch
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
if _GUARD_DIRECTORY not in sys.path:
    sys.path.insert(0, _GUARD_DIRECTORY)
from _push_pr_guard_commands import (  # noqa: E402
    _effective_command,
    _effective_command_index,
    _execution_target,
    _is_python_interpreter,
    _python_arguments,
    _resolved_command,
    _resolves_to_installed_command,
    _resolves_to_known_command,
    _token_is_python_interpreter,
)
from _push_pr_guard_expansion import (  # noqa: E402
    _names_new_pr,
    _path_names_new_pr,
    _scope_segments,
)
from _push_pr_guard_git import (  # noqa: E402
    _contains_git_execution_delegation,
    _git_delegated_operands,
    _normalized_git_invocation,
)
from _push_pr_guard_git_tables import (  # noqa: E402
    _GIT_COMMAND_ENVIRONMENT,
)
from _push_pr_guard_identity import (  # noqa: E402
    _SCRIPT_RELATIVE_PATH,
    _matches_trusted_file,
    _regular_resolved_file,
    _runtime_script,
    _validate_runtime_bundle,
)
from _push_pr_guard_lex import (  # noqa: E402
    _NEW_PR_TARGET,
    GuardViolationError,
    ShellToken,
    _command_name,
    _contains_active_parameter_expansion,
    _contains_active_shell_expansion,
    _contains_shell_expansion,
    _could_target_new_pr,
    _is_assignment,
    _split_command,
    _unversioned_command_name,
)
from _push_pr_guard_tables import (  # noqa: E402
    _BUSYBOX_COMMANDS,
    _COMMAND_DELEGATION_ENVIRONMENT,
    _COMMAND_DELEGATION_OPTIONS,
    _COMMAND_DELEGATORS,
    _DANGEROUS_LOADER_ENVIRONMENT,
    _DEBUG_EVALUATORS,
    _DYNAMIC_EVALUATORS,
    _EXECUTION_INFLUENCING_VARIABLES,
    _EXPANSION_SAFE_COMMANDS,
    _LAUNCHER_COMMANDS,
    _SHELL_EVALUATORS,
)

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


def _execution_position_names_new_pr(tokens: list[ShellToken], cwd: Path) -> bool:
    """Scope rule D: an executed path is a glob or escape naming new_pr.py.

    Position, not a literal prefix, separates a targeted glob from a data glob.
    ``./attacker/pr/?ew_pr.py`` and ``./attacker/pr/[!x]ew_pr.py`` both expand
    to the lookalike and both have an empty literal prefix, so a
    prefix-threshold heuristic let them through while a direct launch missed
    scope rules B and C (issue #4825). ``echo *.py`` stays out of scope because
    an argument to ``echo`` is not an execution position.

    ANSI-C quoting in an execution position fails closed. Decoding covers the
    escapes ``unicode_escape`` knows; a path that runs and still needs
    ``$'...'`` to spell itself is not a shape this guard can clear.
    """
    for token in _execution_position_tokens(tokens, cwd):
        if "$'" in token.raw:
            return True
        basename = token.value.rsplit("/", 1)[-1]
        if not basename or not any(marker in basename for marker in "?*["):
            continue
        if fnmatch.fnmatch(_NEW_PR_TARGET, basename):
            return True
    return False


def _shell_evaluator_argument_is_in_scope(
    tokens: list[ShellToken],
    cwd: Path,
    depth: int,
) -> bool:
    index = _effective_command_index(tokens)
    if index is None:
        return False
    command_name = _command_name(tokens[index].value)
    unversioned_name = _unversioned_command_name(tokens[index].value)
    if command_name not in _SHELL_EVALUATORS and unversioned_name not in _SHELL_EVALUATORS:
        return False
    for offset, token in enumerate(tokens[index + 1 :], start=index + 1):
        value = token.value
        if value == "-c":
            return offset + 1 < len(tokens) and _command_text_is_in_scope(
                tokens[offset + 1].value,
                cwd,
                depth + 1,
            )
        if value.startswith("-") and not value.startswith("--") and "c" in value[1:]:
            return offset + 1 < len(tokens) and _command_text_is_in_scope(
                tokens[offset + 1].value,
                cwd,
                depth + 1,
            )
    return command_name == "eval" and any(
        _command_text_is_in_scope(token.value, cwd, depth + 1) for token in tokens[index + 1 :]
    )


def _unresolvable_python_target(tokens: list[ShellToken], cwd: Path) -> bool:
    """Scope rule B: a Python script operand the guard cannot resolve."""
    arguments = _python_arguments(tokens, cwd)
    if arguments is None:
        return False
    target, dynamic = _execution_target(arguments)
    if target is None or dynamic:
        return False
    return _contains_shell_expansion(target.raw) or _contains_shell_expansion(target.value)


def _execution_position_tokens(tokens: list[ShellToken], cwd: Path) -> list[ShellToken]:
    """Return the tokens a file could actually execute from.

    Only three positions run a file: the effective command, a Python
    interpreter reached through wrappers, and that interpreter's script
    operand. An operand sitting elsewhere is a filename argument, not an
    execution, so it is not this guard's business.

    Consults ``_operands_are_data`` first, so every scope rule shares one
    definition of an execution position. Without that, the interpreter search
    reads shebangs and reports the real new_pr.py as an "interpreter" whenever
    it appears as an operand, which put ``git diff -- .../new_pr.py`` and
    ``ruff check .../new_pr.py`` back in scope through the renamed-copy rule
    even after the path rule had correctly classified them as data
    (issue #4764).
    """
    index = _effective_command_index(tokens)
    if index is None:
        return []
    if _operands_are_data(tokens, index, cwd):
        return [tokens[index]]
    positions = [tokens[index]]
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        interpreter_index = len(tokens) - len(arguments) - 1
        if 0 <= interpreter_index < len(tokens):
            positions.append(tokens[interpreter_index])
        target, dynamic = _execution_target(arguments)
        if target is not None and not dynamic:
            positions.append(target)
    return positions


def _operand_is_new_pr_copy(tokens: list[ShellToken], cwd: Path) -> bool:
    """Scope rule C: an executed file is a byte-identical copy of new_pr.py.

    This inspects execution positions, not every token. A fixed 64-token window
    let a command pad itself past the cap with `env` assignments and hide a
    byte-identical copy behind them (issue #4825). Raising or fail-closing the
    cap traded that leak for denying large ordinary commands. Position is the
    property that actually matters: a copy in argument slot 500 never runs.
    """
    runtime_script = _runtime_script()
    if runtime_script is None:
        return False
    try:
        trusted = runtime_script.stat()
    except OSError:
        return False
    for token in _execution_position_tokens(tokens, cwd):
        value = token.value
        if not value or value.startswith("-"):
            continue
        candidate = Path(os.path.expanduser(value))
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if _matches_trusted_file(candidate, runtime_script, trusted):
            return True
    return False


def _operands_are_data(tokens: list[ShellToken], index: int, cwd: Path) -> bool:
    """True when the effective command READS its operands instead of running them.

    This is the discriminator that fixes the issue #4764 false denials without
    weakening execution detection. ``git diff -- .../new_pr.py``, ``cat
    .../new_pr.py`` and ``ruff check .../new_pr.py`` all name the script in an
    operand, and none of them execute an operand, so the reference is data.

    Stated as four disqualifications rather than an allowlist of readers. An
    allowlist would have to name every tool anyone runs against a Python file,
    and every omission is a false denial of a routine command. The
    disqualifications below are closed sets the guard already maintains, so an
    unlisted READER is handled correctly by default and only an unlisted
    EXECUTOR needs adding.

    Operands are NOT data when:

    1. A leading assignment is present. ``/usr/bin/env PATH=. cat
       attacker/new_pr.py`` reads like a plain read, but ``PATH=.`` decides
       which ``cat`` runs, so the command is no longer the one it names.
    2. The command word carries active shell expansion. ``/usr/bin/pytho[n]3``,
       ``pytho{n,xx}3`` and ``$PY`` all resolve at runtime to something the
       guard cannot name, so it must assume the worst.
    3. The command is an interpreter, evaluator, or launcher. These exist to
       run their operands.
    4. The command does not resolve to a program on disk. An unresolvable
       command word is an unknown program, and this fails closed.

    Anything that survives all four is a resolvable, non-executing program, and
    a path in its argument vector is data.
    """
    if any(_is_assignment(token.value) for token in tokens[:index]):
        return False
    token = tokens[index]
    if _contains_active_shell_expansion(token.raw):
        return False
    name = _command_name(token.value)
    unversioned = _unversioned_command_name(token.value)
    executors = _SHELL_EVALUATORS | _DYNAMIC_EVALUATORS | _DEBUG_EVALUATORS | _LAUNCHER_COMMANDS
    if name in executors or unversioned in executors:
        return False
    if _is_python_interpreter(token.value) or _is_dynamic_evaluator_name(token.value):
        return False
    # `script -q -c '<command>'` and `nsenter --target 1 --mount <command>` run
    # a program named in their arguments without being interpreters. The policy
    # layer already classifies them through `_is_command_delegator`; relevance
    # reuses it so a shape the policy would deny cannot fall out of scope first.
    #
    # `_contains_dynamic_evaluator` is deliberately NOT reused here even though
    # it is the fuller predicate: it calls `_repository_has_active_git_hooks`,
    # which returns True for an ordinary repository, so every `git` command
    # would be classified as an executor and `git diff -- .../new_pr.py` would
    # be denied again.
    if _is_command_delegator(tokens, index):
        return False
    if _resolves_to_known_command(tokens, index, cwd, executors):
        return False
    if _resolved_command(tokens, index, cwd) is None:
        return False
    return not _token_is_python_interpreter(tokens, index, cwd)


def _execution_capable_paths(tokens: list[ShellToken], cwd: Path) -> list[ShellToken]:
    """Return the tokens whose VALUE is a path something could execute.

    Issue #4764 narrowed relevance to these positions. The previous rule placed
    a command in scope whenever its text mentioned new_pr.py anywhere, which
    denied ``git diff -- .../new_pr.py`` and ``python3 -m pytest
    tests/test_new_pr.py``: routine commands that read the file or merely share
    a name suffix with it. Both were measured returning 2 on both dispatchers.

    A path reaches execution through exactly these doors:

    1. the effective command, after assignments and wrappers are skipped;
    2. a Python interpreter reached through those wrappers, and its script
       operand when the launcher is static;
    3. every remaining word, whenever the effective command is not provably a
       reader (see ``_operands_are_data``). This is the fail-closed default:
       an interpreter, a launcher, an obfuscated command word, or one the guard
       cannot resolve gives it no way to tell an operand from a target;
    4. an assignment the loader or interpreter acts on (``PYTHONSTARTUP``,
       ``LD_PRELOAD``, ``BASH_ENV``, ``GIT_*``), which executes its value
       without it ever appearing as an operand;
    5. an operand Git delegates execution to (``-c core.pager=``,
       ``--upload-pack=``, ``--open-files-in-pager=``, an ``ext::`` remote).

    Doors 4 and 5 are additive and apply even to a reader, because they are how
    a command that otherwise only reads can still run a program.

    What this removes is door 0 of the merged tree: "the command text mentions
    new_pr.py anywhere". That rule is what denied ``git diff`` and ``pytest``.
    """
    index = _effective_command_index(tokens)
    if index is None:
        return []

    positions: list[ShellToken] = [tokens[index]]
    positions.extend(
        ShellToken(token.raw, token.value.partition("=")[2])
        for token in tokens[:index]
        if _is_execution_influencing_assignment(token.value)
    )
    positions.extend(_git_delegated_operands(tokens, index, cwd))

    if _operands_are_data(tokens, index, cwd):
        return positions

    # Not provably a reader, so every remaining word is a candidate path. This
    # is the fail-closed branch: an obfuscated command word
    # (`/usr/bin/pytho[n]3`), an unresolvable one (`./p`), or one preceded by an
    # assignment that redirects resolution (`PATH=. cat`) gives the guard no way
    # to know which operand the program will run, so it treats them all as
    # execution-capable. Narrowing this to _execution_position_tokens alone
    # allowed six such shapes that the merged tree denied.
    positions.extend(tokens[index:])
    return positions


def _is_execution_influencing_assignment(value: str) -> bool:
    """True when a leading ``NAME=value`` assignment can execute its value."""
    name, separator, _ = value.partition("=")
    if not separator:
        return False
    return (
        name in _EXECUTION_INFLUENCING_VARIABLES
        or name in _DANGEROUS_LOADER_ENVIRONMENT
        or name.startswith(("DYLD_", "GIT_CONFIG_"))
        or name in _GIT_COMMAND_ENVIRONMENT
    )


def _execution_capable_code(tokens: list[ShellToken], cwd: Path) -> list[str]:
    """Return argument text that is CODE rather than a path.

    Code is tested by substring, because a program that reaches new_pr.py spells
    the name inside a larger expression: ``runpy.run_path('new_pr.py')`` is not
    a path and has no basename to compare. Applying the substring test only here
    is what lets ``python3 -m pytest tests/test_new_pr.py`` out of scope while
    keeping ``python3 -c "...new_pr.py..."`` in it.
    """
    index = _effective_command_index(tokens)
    if index is None:
        return []

    code: list[str] = []
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        target, dynamic = _execution_target(arguments)
        if dynamic and target is not None:
            code.append(target.value)
            code.append(target.raw)

    # An evaluator's arguments are a program in its own language, and this
    # guard has no parser for awk, perl, or node. Substring over the whole
    # argument list is what the merged tree already applied to every command;
    # confining it to evaluators is strictly narrower, so it cannot deny
    # anything the merged tree allowed.
    if _command_is_evaluator(tokens, index, cwd):
        code.extend(token.value for token in tokens[index + 1 :])
        code.extend(token.raw for token in tokens[index + 1 :])
    return code


def _command_is_evaluator(tokens: list[ShellToken], index: int, cwd: Path) -> bool:
    """True when the effective command interprets its arguments as a program."""
    command_name = _command_name(tokens[index].value)
    unversioned = _unversioned_command_name(tokens[index].value)
    if command_name in _SHELL_EVALUATORS or unversioned in _SHELL_EVALUATORS:
        return True
    if any(_is_dynamic_evaluator_name(token.value) for token in tokens[index : index + 2]):
        return True
    return _resolves_to_known_command(
        tokens,
        index,
        cwd,
        _DYNAMIC_EVALUATORS | _DEBUG_EVALUATORS,
    )


def _command_is_in_scope(command: str, cwd: Path) -> bool:
    """Non-blocking relevance gate. See the module docstring for the contract."""
    return _command_text_is_in_scope(command, cwd, 0)


def _segments_are_in_scope(tokens: list[ShellToken], cwd: Path, depth: int) -> bool:
    """Decide relevance for one shell segment."""
    if any(_path_names_new_pr(token.value) for token in _execution_capable_paths(tokens, cwd)):
        return True
    if any(_names_new_pr(text) for text in _execution_capable_code(tokens, cwd)):
        return True
    return (
        _unresolvable_python_target(tokens, cwd)
        or _execution_position_names_new_pr(tokens, cwd)
        or _operand_is_new_pr_copy(tokens, cwd)
        or _shell_evaluator_argument_is_in_scope(tokens, cwd, depth)
    )


def _command_text_is_in_scope(command: str, cwd: Path, depth: int) -> bool:
    if depth > 4:
        return True
    return any(_segments_are_in_scope(tokens, cwd, depth) for tokens in _scope_segments(command))


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


def _contains_dangerous_loader_environment(tokens: list[ShellToken]) -> bool:
    command_index = _effective_command_index(tokens)
    if command_index is None:
        return False
    for token in tokens[:command_index]:
        name, separator, _ = token.value.partition("=")
        if separator and (name in _DANGEROUS_LOADER_ENVIRONMENT or name.startswith("DYLD_")):
            return True
    return False


def _contains_shell_evaluator(tokens: list[ShellToken], cwd: Path) -> bool:
    for index, token in enumerate(tokens):
        command_name = _command_name(token.value)
        unversioned_name = _unversioned_command_name(token.value)
        if command_name in _SHELL_EVALUATORS or unversioned_name in _SHELL_EVALUATORS:
            return True
        if (
            command_name in _BUSYBOX_COMMANDS
            and index + 1 < len(tokens)
            and _command_name(tokens[index + 1].value) in _SHELL_EVALUATORS
        ):
            return True
    command_index = _effective_command_index(tokens)
    return command_index is not None and _resolves_to_known_command(
        tokens,
        command_index,
        cwd,
        _SHELL_EVALUATORS,
    )


def _is_dynamic_evaluator_name(value: str) -> bool:
    command_name = _command_name(value)
    unversioned_name = _unversioned_command_name(value)
    return (
        command_name in _DYNAMIC_EVALUATORS
        or command_name in _DEBUG_EVALUATORS
        or unversioned_name in _DYNAMIC_EVALUATORS
        or unversioned_name in _DEBUG_EVALUATORS
    )


def _is_command_delegator(tokens: list[ShellToken], index: int) -> bool:
    command_name = _command_name(tokens[index].value)
    argument_index = index + 1
    if command_name in _BUSYBOX_COMMANDS and argument_index < len(tokens):
        command_name = _command_name(tokens[argument_index].value)
        argument_index += 1
    if command_name in _COMMAND_DELEGATORS:
        return True
    dangerous_environment = _COMMAND_DELEGATION_ENVIRONMENT.get(
        command_name,
        frozenset(),
    )
    for token in tokens[:index]:
        name, separator, _ = token.value.partition("=")
        if separator and name in dangerous_environment:
            return True
    delegation_options = _COMMAND_DELEGATION_OPTIONS.get(command_name, frozenset())
    arguments = tokens[argument_index:]
    for token in arguments:
        value = token.value
        option_name = value.partition("=")[0]
        for option in delegation_options:
            if value == option or value.startswith(f"{option}="):
                return True
            if (
                option.startswith("--")
                and option_name.startswith("--")
                and len(option_name) > 2
                and option.startswith(option_name)
            ):
                return True
            if (
                len(option) == 2
                and option.startswith("-")
                and not option.startswith("--")
                and not value.startswith("--")
                and value.startswith(option)
            ):
                return True
    if command_name == "tar" and arguments:
        first = arguments[0].value
        if not first.startswith("-") and any(option in first for option in {"F", "I"}):
            return True
        if any(
            token.value.startswith("-")
            and not token.value.startswith("--")
            and any(option in token.value[1:] for option in {"F", "I"})
            for token in arguments
        ):
            return True
    return False


def _contains_dynamic_evaluator(tokens: list[ShellToken], cwd: Path) -> bool:
    index = _effective_command_index(tokens)
    if index is None:
        return False
    command_name = _command_name(tokens[index].value)
    if _resolves_to_known_command(
        tokens,
        index,
        cwd,
        _DYNAMIC_EVALUATORS | _DEBUG_EVALUATORS,
    ):
        return True
    if _is_command_delegator(tokens, index):
        return True
    git_invocation = _normalized_git_invocation(tokens, index, cwd)
    if git_invocation is not None and _contains_git_execution_delegation(
        *git_invocation,
        cwd,
    ):
        return True
    if command_name in _EXPANSION_SAFE_COMMANDS:
        return not _resolves_to_installed_command(
            tokens,
            index,
            cwd,
            _EXPANSION_SAFE_COMMANDS,
        )
    if any(_is_dynamic_evaluator_name(token.value) for token in tokens[index:]):
        return True
    return (
        _command_name(tokens[index].value) in _BUSYBOX_COMMANDS
        and index + 1 < len(tokens)
        and _is_dynamic_evaluator_name(tokens[index + 1].value)
    )


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


def _script_reference(tokens: list[ShellToken]) -> ShellToken:
    values = [token.value for token in tokens]
    if len(tokens) < 3 or values[:2] != ["python3", "-I"]:
        raise GuardViolationError("new_pr.py must run with python3 -I")
    script_reference = tokens[2]
    if script_reference.value.startswith("-"):
        raise GuardViolationError("new_pr.py script path is missing")
    if script_reference.value != _PLUGIN_SCRIPT_REFERENCE and any(
        marker in script_reference.raw for marker in ("$", "`", "\\\n", "{", "[", "*", "?")
    ):
        raise GuardViolationError("new_pr.py script path cannot use shell expansion")
    if any(("$" in token.raw or "`" in token.raw) for token in tokens[3:]):
        raise GuardViolationError("argument substitution is not allowed")
    if any(_contains_active_shell_expansion(token.raw) for token in tokens[3:]):
        raise GuardViolationError("argument shell expansion is not allowed")
    return script_reference


def _validate_new_pr_arguments(tokens: list[ShellToken], cwd: Path) -> None:
    values: dict[str, str] = {}
    index = 3
    while index < len(tokens):
        option = tokens[index].value
        if option not in {"--title", "--body-file"}:
            raise GuardViolationError("new_pr.py accepts only --title and --body-file here")
        if option in values or index + 1 >= len(tokens):
            raise GuardViolationError(
                f"new_pr.py option {option} is duplicate or missing its value"
            )
        values[option] = tokens[index + 1].value
        index += 2
    if set(values) != {"--title", "--body-file"}:
        raise GuardViolationError("new_pr.py requires exactly --title and --body-file")
    if not values["--title"].strip():
        raise GuardViolationError("new_pr.py title cannot be empty")

    body_reference = Path(values["--body-file"])
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
        "push-pr script identity denied: "
        f"{reason}. Run only the repository or installed-plugin new_pr.py.",
        file=sys.stderr,
    )
    return 2


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
        if _contains_dangerous_loader_environment(tokens):
            raise GuardViolationError("dynamic loader environment variables are not allowed")
        if _contains_shell_evaluator(tokens, cwd):
            raise GuardViolationError("shell evaluator wrappers are not allowed")
        if _contains_dynamic_evaluator(tokens, cwd):
            raise GuardViolationError("dynamic evaluator wrappers are not allowed")
        if not _requires_identity_check(command, cwd):
            return 0
        if _contains_shell_expansion(command) and _python_arguments(tokens, cwd) is None:
            raise GuardViolationError(
                "shell-expanded commands outside the exact allowlist are not allowed"
            )
        arguments = _python_arguments(tokens, cwd)
        if arguments is not None:
            target, dynamic = _execution_target(arguments)
            if dynamic:
                raise GuardViolationError("dynamic Python -c and -m launchers are not allowed")
            if (
                target is not None
                and not dynamic
                and _contains_shell_expansion(target.raw)
                and target.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"'
            ):
                raise GuardViolationError("Python script paths cannot use shell expansion")
        if not _targets_new_pr(tokens, cwd):
            if arguments is not None:
                raise GuardViolationError("Python execution is limited to the approved new_pr.py")
            raise GuardViolationError(
                "command references new_pr.py through an unsupported launcher"
            )
        script_reference = _script_reference(tokens)
        script = _script_path(script_reference, cwd)
        if script != _runtime_script():
            raise GuardViolationError("resolved script is not an approved new_pr.py")
        _validate_runtime_bundle(script)
        _validate_new_pr_arguments(tokens, cwd)
        return 0
    except GuardViolationError as exc:
        return _deny(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
