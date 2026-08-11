# _is_command_delegator tests one command against several delegation shapes:
# name, resolved content, option form, and environment. Each shape denies for
# its own reason, and merging them would report one reason for four different
# findings.
# taste-lint: ignore complexity, flattening would merge delegation shapes.
"""Evaluator and delegator detection for the push-pr identity guard (#4764).

A command that evaluates text (``bash -c``, ``python3 -c``, ``perl -e``) or
delegates to another command (``xargs``, ``timeout``, ``sudo``, ``nice``) can
reach ``new_pr.py`` without naming it in an execution position. The guard
cannot statically prove such a command safe, so it treats the presence of one
as a reason to fall through to the identity check rather than to allow.

Recognition is by resolved content where a name can be aliased, so a renamed
``bash`` on PATH is still an evaluator.
"""

from __future__ import annotations

from pathlib import Path

from _push_pr_guard_commands import (
    _effective_command_index,
    _resolves_to_installed_command,
    _resolves_to_known_command,
)
from _push_pr_guard_git import _contains_git_execution_delegation, _normalized_git_invocation
from _push_pr_guard_lex import ShellToken, _command_name, _unversioned_command_name
from _push_pr_guard_tables import (
    _BUSYBOX_COMMANDS,
    _COMMAND_DELEGATION_ENVIRONMENT,
    _COMMAND_DELEGATION_OPTIONS,
    _COMMAND_DELEGATORS,
    _DANGEROUS_LOADER_ENVIRONMENT,
    _DEBUG_EVALUATORS,
    _DYNAMIC_EVALUATORS,
    _EXPANSION_SAFE_COMMANDS,
    _SHELL_EVALUATORS,
)


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


def _contains_dangerous_loader_environment(tokens: list[ShellToken]) -> bool:
    command_index = _effective_command_index(tokens)
    if command_index is None:
        return False
    for token in tokens[:command_index]:
        name, separator, _ = token.value.partition("=")
        if separator and (name in _DANGEROUS_LOADER_ENVIRONMENT or name.startswith("DYLD_")):
            return True
    return False
