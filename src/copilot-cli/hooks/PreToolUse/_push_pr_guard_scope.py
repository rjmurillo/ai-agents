"""Relevance gate for the push-pr identity guard (issue #4764).

The host registers the guard on the plugin-wide ``Bash`` matcher, so it runs
on every Bash command and must decide relevance BEFORE policy.
:func:`_command_is_in_scope` returns False for any command that cannot reach
``new_pr.py``, and the guard then allows it untouched.

A command is in scope only when its text can name ``new_pr.py`` in an
execution position, when a Python invocation carries an expansion the guard
cannot statically resolve, or when one of its operands is a byte-identical
copy of the trusted script under a different name.

Position is what separates this module from the ones below it. ``git diff --
path/to/new_pr.py`` names the script as data; ``python3 path/to/new_pr.py``
names it as code. Only the second is in scope, and conflating them denied
ordinary read-only commands on the merged tree (issue #4764 finding 2).
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from _push_pr_guard_commands import (
    _effective_command_index,
    _execution_target,
    _is_python_interpreter,
    _python_arguments,
    _resolved_command,
    _resolves_to_known_command,
    _token_is_python_interpreter,
)
from _push_pr_guard_evaluators import (
    _command_is_evaluator,
    _is_command_delegator,
    _is_dynamic_evaluator_name,
)
from _push_pr_guard_expansion import (
    _names_new_pr,
    _path_names_new_pr,
    _scope_segments,
)
from _push_pr_guard_git import _git_delegated_operands
from _push_pr_guard_git_tables import _GIT_COMMAND_ENVIRONMENT
from _push_pr_guard_identity import _matches_trusted_file, _runtime_script
from _push_pr_guard_lex import (
    _NEW_PR_TARGET,
    ShellToken,
    _command_name,
    _contains_active_shell_expansion,
    _contains_shell_expansion,
    _is_assignment,
    _unversioned_command_name,
)
from _push_pr_guard_tables import (
    _DANGEROUS_LOADER_ENVIRONMENT,
    _DEBUG_EVALUATORS,
    _DYNAMIC_EVALUATORS,
    _EXECUTION_INFLUENCING_VARIABLES,
    _LAUNCHER_COMMANDS,
    _SHELL_EVALUATORS,
)


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
