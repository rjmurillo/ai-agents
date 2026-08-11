# _env_command_index walks GNU env's option grammar: each branch is a distinct
# option shape that moves the command index differently, and a wrong index
# picks the wrong executable. The branches stay explicit so each one keeps its
# own fail-closed reason.
# taste-lint: ignore complexity, flattening would merge option grammars.
"""Command resolution for the push-pr identity guard (issue #4764).

Answers "what does this command line actually run": which token is the
effective command after ``env``, assignments, and process wrappers; whether
that command is a Python interpreter; which operand is the Python script; and
whether a bare name on PATH resolves to a known executable by content rather
than by spelling.

Content comparison, not name comparison, is the rule here. An attacker
controls the name of anything on PATH, so :mod:`_push_pr_guard_identity`
decides sameness by digest and this module decides position.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from _push_pr_guard_identity import _same_executable_content
from _push_pr_guard_lex import (
    GuardViolationError,
    ShellToken,
    _command_name,
    _is_assignment,
    _unversioned_command_name,
)
from _push_pr_guard_tables import (
    _BUSYBOX_COMMANDS,
    _ENV_COMMANDS,
    _PROCESS_WRAPPER_FLAG_OPTIONS,
    _PROCESS_WRAPPER_OPERAND_OPTIONS,
)

_MAX_INTERPRETER_SEARCH = 64


def _is_python_interpreter(value: str) -> bool:
    name = Path(value).name.casefold()
    return bool(
        re.fullmatch(
            r"(?:python(?:[23](?:\.\d+)*)?|pypy(?:[23](?:\.\d+)*)?|py)(?:\.exe)?",
            name,
        )
    )


def _command_search_path(tokens: list[ShellToken], index: int) -> str:
    search_path = os.environ.get("PATH", os.defpath)
    for token in tokens[:index]:
        value = token.value
        if value in {"-i", "--ignore-environment"}:
            search_path = os.defpath
            continue
        name, separator, configured_value = value.partition("=")
        if separator and name == "PATH":
            search_path = configured_value
    return search_path


def _resolved_command(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
) -> Path | None:
    value = os.path.expanduser(tokens[index].value)
    candidate = Path(value)
    if candidate.is_absolute() or candidate.parent != Path("."):
        if not candidate.is_absolute():
            candidate = cwd / candidate
        try:
            return candidate.resolve(strict=True)
        except OSError:
            return None
    resolved = shutil.which(value, path=_command_search_path(tokens, index))
    return Path(resolved).resolve() if resolved is not None else None


def _resolves_to_known_command(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
    names: frozenset[str],
) -> bool:
    resolved = _resolved_command(tokens, index, cwd)
    if resolved is None:
        return False
    if _command_name(resolved.name) in names or _unversioned_command_name(resolved.name) in names:
        return True
    try:
        with resolved.open("rb") as stream:
            shebang = stream.readline(4096).decode("utf-8", errors="ignore")
    except OSError:
        shebang = ""
    if shebang.startswith("#!") and any(
        _command_name(part) in names or _unversioned_command_name(part) in names
        for part in shebang[2:].split()
    ):
        return True
    for name in names:
        known = shutil.which(name)
        if known is not None and _same_executable_content(
            resolved,
            Path(known).resolve(),
        ):
            return True
    return False


def _resolves_to_installed_command(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
    names: frozenset[str],
) -> bool:
    resolved = _resolved_command(tokens, index, cwd)
    if resolved is None:
        return False
    for name in names:
        known = shutil.which(name)
        if known is not None and _same_executable_content(
            resolved,
            Path(known).resolve(),
        ):
            return True
    return False


def _env_command_index(tokens: list[ShellToken], index: int) -> int | None:
    operand_options = {
        "-a",
        "-u",
        "--unset",
        "-C",
        "--chdir",
        "--argv0",
    }
    flag_options = {
        "-0",
        "--null",
        "-i",
        "--ignore-environment",
        "-v",
        "--debug",
    }
    while index < len(tokens):
        value = tokens[index].value
        if _is_env_split_string_option(value):
            raise GuardViolationError("env split-string launchers are not allowed")
        if value == "--":
            index += 1
            while index < len(tokens) and "=" in tokens[index].value:
                index += 1
            return index if index < len(tokens) else None
        if _is_env_assignment(value):
            index += 1
            continue
        if value in flag_options:
            index += 1
            continue
        if value in operand_options:
            index += 2
            continue
        if value.startswith(("--unset=", "--chdir=", "--argv0=")):
            index += 1
            continue
        if value.startswith(("-a", "-u", "-C")) and len(value) > 2:
            index += 1
            continue
        if value.startswith("-"):
            raise GuardViolationError("unsupported env options are not allowed")
        return index
    return None


def _is_env_split_string_option(value: str) -> bool:
    long_option = value.partition("=")[0]
    if len(long_option) > 2 and "--split-string".startswith(long_option):
        return True
    if not value.startswith("-") or value.startswith("--"):
        return False
    for option in value[1:]:
        if option == "S":
            return True
        if option in {"a", "C", "u"}:
            return False
        if option not in {"0", "i", "v"}:
            return False
    return False


def _is_env_assignment(value: str) -> bool:
    return "=" in value and not value.startswith("-")


def _token_is_python_interpreter(
    tokens: list[ShellToken],
    index: int,
    cwd: Path,
) -> bool:
    token = tokens[index]
    if _is_python_interpreter(token.value):
        return True
    resolved_interpreter = _resolved_command(tokens, index, cwd)
    if resolved_interpreter is None:
        return False
    try:
        with resolved_interpreter.open("rb") as stream:
            shebang = stream.readline(4096)
    except OSError:
        shebang = b""
    if shebang.startswith(b"#!") and re.search(
        rb"(?:^|[/\s])(?:python(?:[23](?:\.\d+)*)?|pypy(?:[23](?:\.\d+)*)?)(?:\s|$)",
        shebang,
        re.IGNORECASE,
    ):
        return True
    runtime_interpreter = Path(sys.executable).resolve()
    return _is_python_interpreter(resolved_interpreter.name) or _same_executable_content(
        resolved_interpreter,
        runtime_interpreter,
    )


def _python_arguments(tokens: list[ShellToken], cwd: Path) -> list[ShellToken] | None:
    index = _effective_command_index(tokens)
    if index is None:
        return None
    # Bounded search. _effective_command_index has already skipped assignments,
    # `env`, and process wrappers, so an interpreter that is actually being
    # invoked sits within a few tokens of here. Probing every token instead
    # cost a shebang read each, and an 87 KiB command took 10.2s against the
    # host's 10s timeout, where a Copilot timeout fails open (issue #4825).
    #
    # The scan reads shebangs, so it also classifies a Python SCRIPT as an
    # interpreter. That is deliberate and load-bearing: `uv run tools/copy.py`
    # is a real execution whose interpreter this guard cannot name. Relevance
    # therefore filters on the effective COMMAND (see `_operands_are_data`)
    # rather than on the operand, because the operand cannot tell the two
    # apart, and filtering here denied `git diff -- .../new_pr.py`
    # (issue #4764).
    limit = min(len(tokens), index + _MAX_INTERPRETER_SEARCH)
    for candidate_index in range(index, limit):
        if _token_is_python_interpreter(tokens, candidate_index, cwd):
            return tokens[candidate_index + 1 :]
    return None


def _skip_command_wrappers(tokens: list[ShellToken], index: int) -> int:
    while index < len(tokens) and tokens[index].value in {"command", "exec"}:
        wrapper = tokens[index].value
        index += 1
        while index < len(tokens) and tokens[index].value.startswith("-"):
            option = tokens[index].value
            if option == "--":
                index += 1
                break
            if wrapper == "exec" and option == "-a":
                index += 2
                continue
            index += 1
    return index


def _resolve_wrapper_long_option(wrapper: str, value: str) -> tuple[str, bool]:
    option_name, separator, _ = value.partition("=")
    options = _PROCESS_WRAPPER_OPERAND_OPTIONS.get(
        wrapper, frozenset()
    ) | _PROCESS_WRAPPER_FLAG_OPTIONS.get(wrapper, frozenset())
    candidates = {
        option for option in options if option.startswith("--") and option.startswith(option_name)
    }
    if len(option_name) <= 2 or len(candidates) != 1:
        raise GuardViolationError("unsupported process wrapper options are not allowed")
    return candidates.pop(), bool(separator)


def _skip_wrapper_short_options(
    tokens: list[ShellToken],
    index: int,
    wrapper: str,
) -> int:
    value = tokens[index].value
    operand_options = _PROCESS_WRAPPER_OPERAND_OPTIONS.get(wrapper, frozenset())
    flag_options = _PROCESS_WRAPPER_FLAG_OPTIONS.get(wrapper, frozenset())
    for option_index, option_name in enumerate(value[1:]):
        option = f"-{option_name}"
        if option in flag_options:
            continue
        if option not in operand_options:
            raise GuardViolationError("unsupported process wrapper options are not allowed")
        if option_index + 1 < len(value[1:]):
            return index + 1
        if index + 1 >= len(tokens):
            raise GuardViolationError("process wrapper option requires an operand")
        return index + 2
    return index + 1


def _skip_wrapper_options(
    tokens: list[ShellToken],
    index: int,
    wrapper: str,
) -> int:
    operand_options = _PROCESS_WRAPPER_OPERAND_OPTIONS.get(wrapper, frozenset())
    flag_options = _PROCESS_WRAPPER_FLAG_OPTIONS.get(wrapper, frozenset())
    while index < len(tokens) and tokens[index].value.startswith("-"):
        value = tokens[index].value
        if value == "--":
            return index + 1
        if value.startswith("--"):
            option, attached_operand = _resolve_wrapper_long_option(wrapper, value)
            if option in flag_options:
                index += 1
                continue
            if attached_operand:
                index += 1
                continue
            if option in operand_options and index + 1 < len(tokens):
                index += 2
                continue
            raise GuardViolationError("process wrapper option requires an operand")
        index = _skip_wrapper_short_options(tokens, index, wrapper)
    return index


def _skip_process_wrappers(tokens: list[ShellToken], index: int) -> int:
    wrappers = set(_PROCESS_WRAPPER_FLAG_OPTIONS)
    while index < len(tokens):
        wrapper = _command_name(tokens[index].value)
        if wrapper not in wrappers:
            break
        index += 1
        index = _skip_wrapper_options(tokens, index, wrapper)
        if wrapper == "timeout" and index < len(tokens):
            index += 1
    return index


def _effective_command(tokens: list[ShellToken]) -> ShellToken | None:
    index = _effective_command_index(tokens)
    return tokens[index] if index is not None else None


def _effective_command_index(tokens: list[ShellToken]) -> int | None:
    index = 0
    while index < len(tokens) and _is_assignment(tokens[index].value):
        index += 1
    while index < len(tokens):
        index = _skip_command_wrappers(tokens, index)
        index = _skip_process_wrappers(tokens, index)
        if index >= len(tokens):
            return None
        if _command_name(tokens[index].value) in _BUSYBOX_COMMANDS:
            index += 1
            continue
        if _command_name(tokens[index].value) not in _ENV_COMMANDS:
            return index
        command_index = _env_command_index(tokens, index + 1)
        if command_index is None:
            return None
        index = command_index
    return None


def _execution_target(
    arguments: list[ShellToken],
) -> tuple[ShellToken | None, bool]:
    if not arguments:
        return None, False
    value_options = {"-W", "-X", "--check-hash-based-pycs"}
    no_value_short_options = frozenset("bBdEhiIOPqRsSuvVx")
    index = 0
    while index < len(arguments):
        token = arguments[index]
        value = token.value
        if value in {"-c", "-m"}:
            target = arguments[index + 1] if index + 1 < len(arguments) else token
            return target, True
        if value.startswith(("-c", "-m")) and len(value) > 2:
            return ShellToken(token.raw[2:], value[2:]), True
        if value.startswith("-") and not value.startswith("--"):
            cluster = value[1:]
            consumed_value = False
            for option_index, option in enumerate(cluster):
                if option in {"c", "m"}:
                    attached = cluster[option_index + 1 :]
                    if attached:
                        return ShellToken(attached, attached), True
                    target = arguments[index + 1] if index + 1 < len(arguments) else token
                    return target, True
                if option in {"W", "X"}:
                    index += 1 if cluster[option_index + 1 :] else 2
                    consumed_value = True
                    break
                if option not in no_value_short_options:
                    break
            if consumed_value:
                continue
        if value == "--":
            target = arguments[index + 1] if index + 1 < len(arguments) else token
            return target, False
        if value in value_options:
            index += 2
            continue
        if value.startswith(("-W", "-X")) and len(value) > 2:
            index += 1
            continue
        if not value.startswith("-"):
            return token, False
        index += 1
    return None, False
