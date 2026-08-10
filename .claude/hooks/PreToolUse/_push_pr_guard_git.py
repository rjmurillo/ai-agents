"""Git execution semantics for the push-pr identity guard (issue #4764).

Git is a command runner. ``git -c core.pager=... log``, ``git submodule
foreach``, ``git clone ext::sh -c``, and a repository with active hooks all
turn a Git invocation into arbitrary execution, so the guard has to read the
Git command line as carefully as it reads a shell one.

Two questions live here. Does this Git invocation delegate execution
(:func:`_contains_git_execution_delegation`), and which operands does it hand
to something that executes (:func:`_git_delegated_operands`)? The relevance
gate uses the second to decide whether an operand could reach ``new_pr.py``.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from _push_pr_guard_commands import _resolves_to_known_command
from _push_pr_guard_git_tables import (
    _GIT_BUILTIN_COMMANDS,
    _GIT_COMMAND_ENVIRONMENT,
    _GIT_CONFIG_READ_ACTIONS,
    _GIT_CONFIG_READ_MODIFIERS,
    _GIT_EXECUTION_OPERANDS_BY_SUBCOMMAND,
    _GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND,
    _GIT_GLOBAL_EXECUTION_OPTIONS,
    _GIT_GLOBAL_EXECUTION_PREFIXES,
    _GIT_HOOK_FREE_SUBCOMMANDS,
    _GIT_OPTION_OPERANDS_BY_SUBCOMMAND,
    _GIT_REMOTE_SUBCOMMANDS,
    _GIT_SAFE_REMOTE_SCHEMES,
    _GIT_SHORT_CLUSTER_OPERANDS_BY_SUBCOMMAND,
)
from _push_pr_guard_lex import GuardViolationError, ShellToken, _command_name


def _is_safe_git_config(value: str) -> bool:
    key, separator, configured_value = value.partition("=")
    return bool(
        separator
        and key.casefold().startswith("color.")
        and configured_value.casefold() in {"always", "auto", "false", "never", "true"}
    )


def _has_unsafe_git_remote(value: str) -> bool:
    remote = value.partition("=")[2] or value
    if re.match(r"[A-Za-z][A-Za-z0-9+.-]*::", remote):
        return True
    scheme_match = re.match(r"([A-Za-z][A-Za-z0-9+.-]*)://", remote)
    return bool(
        scheme_match is not None
        and scheme_match.group(1).casefold() not in _GIT_SAFE_REMOTE_SCHEMES
    )


def _is_literal_safe_git_remote(value: str) -> bool:
    if _has_unsafe_git_remote(value):
        return False
    if re.match(r"^[A-Za-z]:", value) or value.startswith(("\\", "//")):
        return False
    scheme_match = re.match(r"([A-Za-z][A-Za-z0-9+.-]*)://", value)
    if scheme_match is not None:
        return scheme_match.group(1).casefold() in _GIT_SAFE_REMOTE_SCHEMES
    if re.match(r"(?:[^/@:]+@)?[^/:]+:.+", value):
        return True
    return False


def _git_remote_operand(
    tokens: list[ShellToken],
    subcommand_index: int,
) -> str | None:
    subcommand = tokens[subcommand_index].value.casefold()
    operand_options = _GIT_OPTION_OPERANDS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    arguments = tokens[subcommand_index + 1 :]
    index = 0
    while index < len(arguments):
        token = arguments[index]
        value = token.value
        if value in {"--remote", "--repo"}:
            return arguments[index + 1].value if index + 1 < len(arguments) else None
        if value.startswith(("--remote=", "--repo=")):
            return value.partition("=")[2]
        if value == "--":
            return arguments[index + 1].value if index + 1 < len(arguments) else None
        if value.startswith("--"):
            option_name, separator, _ = value.partition("=")
            matches = [
                option
                for option in operand_options
                if option.startswith("--")
                and (
                    option_name == option
                    or (len(option_name) > 2 and option.startswith(option_name))
                )
            ]
            if len(matches) == 1:
                index += 1 if separator else 2
                continue
            index += 1
            continue
        if value.startswith("-"):
            consumed_next = False
            for option_index, option in enumerate(value[1:]):
                if f"-{option}" not in operand_options:
                    continue
                consumed_next = not value[option_index + 2 :]
                break
            index += 2 if consumed_next else 1
            continue
        if not value.startswith("-"):
            return value
        index += 1
    return None


def _git_subcommand_index(tokens: list[ShellToken], command_index: int) -> int | None:
    index = command_index + 1
    safe_flags = {
        "-P",
        "--glob-pathspecs",
        "--icase-pathspecs",
        "--literal-pathspecs",
        "--no-lazy-fetch",
        "--no-advice",
        "--no-optional-locks",
        "--no-pager",
        "--no-replace-objects",
        "--noglob-pathspecs",
    }
    while index < len(tokens):
        value = tokens[index].value
        if value == "-c":
            index += 2
            continue
        if value.startswith("-c") and len(value) > 2:
            index += 1
            continue
        if value in safe_flags:
            index += 1
            continue
        if value.startswith("-"):
            raise GuardViolationError("unsupported Git global options are not allowed")
        return index
    return None


def _git_subcommand_index_or_none(tokens: list[ShellToken], command_index: int) -> int | None:
    """``_git_subcommand_index`` without its policy exception.

    The policy version raises on unsupported global options, which is correct
    when deciding whether to DENY. Relevance must not raise: a command it
    cannot classify is simply one with no extractable delegation operand, and
    the other scope rules still apply to it.
    """
    try:
        return _git_subcommand_index(tokens, command_index)
    except GuardViolationError:
        return None


def _is_read_only_git_config(tokens: list[ShellToken], subcommand_index: int) -> bool:
    for token in tokens[subcommand_index + 1 :]:
        value = token.value
        if value in _GIT_CONFIG_READ_MODIFIERS:
            continue
        return value in _GIT_CONFIG_READ_ACTIONS
    return False


def _matches_git_option(
    subcommand: str,
    value: str,
    options: frozenset[str],
) -> bool:
    option_name = value.partition("=")[0]
    for option in options:
        if value == option or value.startswith(f"{option}="):
            return True
        if (
            option.startswith("--")
            and option_name.startswith("--")
            and len(option_name) > 2
            and option.startswith(option_name)
        ):
            return True
        if option.startswith("-") and not option.startswith("--"):
            if len(option) == 2 and not value.startswith("--") and value.startswith(option):
                return True
    if not value.startswith("-") or value.startswith("--"):
        return False
    dangerous_options = {
        option[1]
        for option in options
        if len(option) == 2 and option.startswith("-") and not option.startswith("--")
    }
    operand_options = _GIT_SHORT_CLUSTER_OPERANDS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    for option in value[1:]:
        if option in dangerous_options:
            return True
        if option in operand_options:
            return False
    return False


def _repository_has_active_git_hooks(cwd: Path) -> bool:
    git = shutil.which("git")
    if git is None:
        return False
    try:
        result = subprocess.run(
            [git, "-C", str(cwd), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    hooks_path = Path(result.stdout.strip())
    if not hooks_path.is_absolute():
        hooks_path = cwd / hooks_path
    try:
        hooks = hooks_path.resolve(strict=True).iterdir()
    except OSError:
        return False
    for hook in hooks:
        try:
            mode = hook.stat().st_mode
        except OSError:
            continue
        if (
            hook.is_file()
            and not hook.name.endswith(".sample")
            and (os.name == "nt" or mode & stat.S_IXUSR)
        ):
            return True
    return False


def _contains_git_execution_delegation(
    tokens: list[ShellToken],
    command_index: int,
    cwd: Path,
) -> bool:
    for token in tokens[:command_index]:
        name, separator, _ = token.value.partition("=")
        if not separator:
            continue
        if name.startswith("GIT_CONFIG_") or name in _GIT_COMMAND_ENVIRONMENT:
            return True

    index = command_index + 1
    while index < len(tokens):
        value = tokens[index].value
        if value == "-c":
            index += 1
            if index >= len(tokens) or not _is_safe_git_config(tokens[index].value):
                return True
        elif value.startswith("-c") and len(value) > 2:
            if not _is_safe_git_config(value[2:]):
                return True
        elif value in _GIT_GLOBAL_EXECUTION_OPTIONS:
            return True
        elif value.startswith(_GIT_GLOBAL_EXECUTION_PREFIXES):
            return True
        if _has_unsafe_git_remote(value):
            return True
        index += 1

    subcommand_index = _git_subcommand_index(tokens, command_index)
    if subcommand_index is None:
        return False
    subcommand = tokens[subcommand_index].value.casefold()
    if subcommand not in _GIT_BUILTIN_COMMANDS:
        return True
    if subcommand == "config" and not _is_read_only_git_config(
        tokens,
        subcommand_index,
    ):
        return True
    if subcommand not in _GIT_HOOK_FREE_SUBCOMMANDS and _repository_has_active_git_hooks(cwd):
        return True
    if subcommand in _GIT_REMOTE_SUBCOMMANDS:
        remote = _git_remote_operand(tokens, subcommand_index)
        if remote is None or not _is_literal_safe_git_remote(remote):
            return True
    execution_options = _GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    execution_operands = _GIT_EXECUTION_OPERANDS_BY_SUBCOMMAND.get(
        subcommand,
        frozenset(),
    )
    for token in tokens[subcommand_index + 1 :]:
        if _matches_git_option(subcommand, token.value, execution_options):
            return True
        if token.value.casefold() in execution_operands:
            return True
    return False


def _normalized_git_invocation(
    tokens: list[ShellToken],
    command_index: int,
    cwd: Path,
) -> tuple[list[ShellToken], int] | None:
    command_name = _command_name(tokens[command_index].value)
    if command_name == "git":
        return tokens, command_index
    if command_name.startswith("git-") and len(command_name) > 4:
        subcommand = command_name.removeprefix("git-")
        normalized = list(tokens)
        normalized[command_index] = ShellToken("git", "git")
        normalized.insert(command_index + 1, ShellToken(subcommand, subcommand))
        return normalized, command_index
    if _resolves_to_known_command(
        tokens,
        command_index,
        cwd,
        frozenset({"git"}),
    ):
        return tokens, command_index
    return None


def _git_delegated_operands(
    tokens: list[ShellToken],
    command_index: int,
    cwd: Path,
) -> list[ShellToken]:
    """Return operands a Git invocation would hand to a program to execute.

    Keeps the Git pager and external-transport vectors in scope after relevance
    narrowed to execution positions. ``git -c core.pager=<path> log`` and
    ``git clone ext::<payload>`` never place the executed path in a command
    position, so ``_execution_position_tokens`` cannot see it.

    Narrower than ``_contains_git_execution_delegation``, deliberately. That
    predicate answers "could this Git command run a hook or helper at all",
    which is true for almost every subcommand in a repository with hooks
    installed, and using it for relevance is what denied ``git diff``. This
    returns only the operands whose VALUE names a program.
    """
    git_invocation = _normalized_git_invocation(tokens, command_index, cwd)
    if git_invocation is None:
        return []
    normalized, index = git_invocation

    operands: list[ShellToken] = []
    position = index + 1
    while position < len(normalized):
        token = normalized[position]
        value = token.value
        if value == "-c" and position + 1 < len(normalized):
            configured = normalized[position + 1]
            operands.append(ShellToken(configured.raw, configured.value.partition("=")[2]))
            position += 2
            continue
        if value.startswith("-c") and len(value) > 2:
            operands.append(ShellToken(token.raw, value[2:].partition("=")[2]))
        elif value in _GIT_GLOBAL_EXECUTION_OPTIONS and position + 1 < len(normalized):
            operands.append(normalized[position + 1])
        elif value.startswith(_GIT_GLOBAL_EXECUTION_PREFIXES):
            operands.append(ShellToken(token.raw, value.partition("=")[2] or value))
        elif _has_unsafe_git_remote(value):
            operands.append(token)
        position += 1

    # Per-subcommand execution options, e.g. `git grep
    # --open-files-in-pager=<program>`. These are not global options, so the
    # loop above cannot see them, and omitting them let a pager-delegated
    # execution out of scope.
    subcommand_index = _git_subcommand_index_or_none(normalized, index)
    if subcommand_index is not None:
        subcommand = normalized[subcommand_index].value.casefold()
        execution_options = _GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND.get(subcommand, frozenset())
        for offset, token in enumerate(
            normalized[subcommand_index + 1 :], start=subcommand_index + 1
        ):
            if not _matches_git_option(subcommand, token.value, execution_options):
                continue
            _key, separator, configured = token.value.partition("=")
            if separator:
                operands.append(ShellToken(token.raw, configured))
            elif offset + 1 < len(normalized):
                operands.append(normalized[offset + 1])
    return operands
