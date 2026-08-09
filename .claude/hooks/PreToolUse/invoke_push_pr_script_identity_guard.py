#!/usr/bin/env python3
"""Deny noncanonical push-pr Python entrypoints (issue #4764)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import NamedTuple

_MAX_STDIN_BYTES = 128 * 1024
_SCRIPT_RELATIVE_PATH = Path("skills/github/scripts/pr/new_pr.py")
_PLUGIN_SCRIPT_REFERENCE = (
    "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/"
    "skills/github/scripts/pr/new_pr.py"
)
_SHELL_EXPANSION_MARKERS = ("$", "`", "\\\n", "{", "[", "*", "?")
_SHELL_EVALUATORS = frozenset(
    {
        "ash",
        "bash",
        "cmd",
        "cmd.exe",
        "csh",
        "dash",
        "eval",
        "fish",
        "ksh",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "tcsh",
        "zsh",
    }
)
_ENV_COMMANDS = frozenset({"env", "env.exe"})
_BUSYBOX_COMMANDS = frozenset({"busybox", "busybox.exe"})
_EXPANSION_SAFE_COMMANDS = frozenset({"printf"})
_TRUSTED_NEW_PR_SHA256 = (
    "f97ef04148e297d1a2aa1a9e157ca65009b8a6323e1dab4e23ddcf18c3a4c086"
)
_TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256 = (
    "2ccbe08d1084a1d5a3639645fa0cc7068e9f8e28e1aa17603c0e3d9c34b4bec2"
)
class GuardViolationError(ValueError):
    """A command shape the push-pr identity policy rejects."""


class ShellToken(NamedTuple):
    """One shell word with both source spelling and interpreted value."""

    raw: str
    value: str


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


def _split_command(command: str) -> list[ShellToken]:
    tokens: list[ShellToken] = []
    raw: list[str] = []
    value: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if char in "\r\n\0":
            raise GuardViolationError("command contains a line break or null byte")
        if quote == "'":
            raw.append(char)
            if char == "'":
                quote = None
            else:
                value.append(char)
            index += 1
            continue
        if quote == '"':
            raw.append(char)
            if char == '"':
                quote = None
            elif char == "`":
                raise GuardViolationError("command substitution is not allowed")
            elif char == "$" and command[index + 1 : index + 2] == "(":
                raise GuardViolationError("command substitution is not allowed")
            elif char == "\\":
                index += 1
                if index >= len(command):
                    raise GuardViolationError("command has incomplete shell quoting")
                raw.append(command[index])
                if command[index] in {'$', "`", '"', "\\"}:
                    value.append(command[index])
                else:
                    value.extend(("\\", command[index]))
            else:
                value.append(char)
            index += 1
            continue
        if char.isspace():
            if raw:
                tokens.append(ShellToken("".join(raw), "".join(value)))
                raw.clear()
                value.clear()
            index += 1
            continue
        if char == "\\":
            raw.append(char)
            index += 1
            if index >= len(command):
                raise GuardViolationError("command has incomplete shell quoting")
            raw.append(command[index])
            value.append(command[index])
            index += 1
            continue
        if char in ("'", '"'):
            raw.append(char)
            quote = char
        elif char in ";&|<>()":
            raise GuardViolationError("shell operators are not allowed")
        elif char == "`":
            raise GuardViolationError("command substitution is not allowed")
        elif char == "#" and not raw:
            raise GuardViolationError("shell comments are not allowed")
        else:
            raw.append(char)
            value.append(char)
        index += 1

    if quote is not None:
        raise GuardViolationError("command has incomplete shell quoting")
    if raw:
        tokens.append(ShellToken("".join(raw), "".join(value)))
    return tokens


def _could_target_new_pr(value: str) -> bool:
    literal = value.replace("\\\r\n", "").replace("\\\n", "").casefold()
    variants = {literal, literal.replace("\\", "/"), literal.replace("\\", "")}
    for normalized in variants:
        compacted = normalized.translate(str.maketrans("", "", "'\"+ \t"))
        if "new_pr.py" in compacted:
            return True
    return False


def _contains_shell_expansion(value: str) -> bool:
    return any(marker in value for marker in _SHELL_EXPANSION_MARKERS)


def _contains_active_parameter_expansion(raw: str) -> bool:
    quote: str | None = None
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if char == "'":
            quote = None if quote == "'" else "'" if quote is None else quote
        elif char == '"':
            quote = None if quote == '"' else '"' if quote is None else quote
        elif char in {"$", "`"} and quote != "'":
            return True
        index += 1
    return False


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
        Path(token.value).name in _SHELL_EVALUATORS
        and (
            Path(token.value).name == "eval"
            or any(option.value == "-c" for option in tokens[index + 1 :])
        )
        for index, token in enumerate(tokens)
    ):
        return True
    if not _contains_shell_expansion(command):
        return False
    effective_command = _effective_command(tokens)
    if effective_command is None:
        return True
    if _contains_shell_expansion(effective_command.raw):
        return True
    if (
        Path(effective_command.value).name.casefold()
        not in _EXPANSION_SAFE_COMMANDS
    ):
        return True
    return any(
        _contains_active_parameter_expansion(token.raw)
        for token in tokens
    )


def _is_assignment(token: str) -> bool:
    name, separator, _ = token.partition("=")
    return bool(separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def _is_python_interpreter(value: str) -> bool:
    name = Path(value).name.casefold()
    return bool(
        re.fullmatch(
            r"(?:python(?:3(?:\.\d+)?)?|pypy3?|py)(?:\.exe)?",
            name,
        )
    )


def _same_executable_content(left: Path, right: Path) -> bool:
    try:
        if left.samefile(right):
            return True
        if left.stat().st_size != right.stat().st_size:
            return False
        with left.open("rb") as left_stream, right.open("rb") as right_stream:
            return hashlib.file_digest(
                left_stream, "sha256"
            ).digest() == hashlib.file_digest(right_stream, "sha256").digest()
    except OSError:
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
            return index + 1 if index + 1 < len(tokens) else None
        if _is_assignment(value):
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


def _token_is_python_interpreter(token: ShellToken, cwd: Path) -> bool:
    if _is_python_interpreter(token.value):
        return True
    interpreter = Path(token.value)
    if not interpreter.is_absolute():
        interpreter = cwd / interpreter
    try:
        resolved_interpreter = interpreter.resolve(strict=True)
    except OSError:
        return False
    try:
        with resolved_interpreter.open("rb") as stream:
            shebang = stream.readline(4096)
    except OSError:
        shebang = b""
    if shebang.startswith(b"#!") and re.search(
        rb"(?:^|[/\s])(?:python(?:3(?:\.\d+)?)?|pypy3?)(?:\s|$)",
        shebang,
        re.IGNORECASE,
    ):
        return True
    runtime_interpreter = Path(sys.executable).resolve()
    return _is_python_interpreter(
        resolved_interpreter.name
    ) or _same_executable_content(
        resolved_interpreter,
        runtime_interpreter,
    )


def _python_arguments(tokens: list[ShellToken], cwd: Path) -> list[ShellToken] | None:
    index = _effective_command_index(tokens)
    if index is None:
        return None
    for candidate_index in range(index, len(tokens)):
        if _token_is_python_interpreter(tokens[candidate_index], cwd):
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


def _skip_process_wrappers(tokens: list[ShellToken], index: int) -> int:
    wrappers = {"nohup", "nice", "setsid", "stdbuf", "time", "timeout"}
    operand_options = {
        "nice": {"-n", "--adjustment"},
        "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
        "timeout": {"-k", "-s", "--kill-after", "--signal"},
    }
    while index < len(tokens) and Path(tokens[index].value).name in wrappers:
        wrapper = Path(tokens[index].value).name
        index += 1
        while index < len(tokens) and tokens[index].value.startswith("-"):
            option = tokens[index].value
            if option == "--":
                index += 1
                break
            if option in operand_options.get(wrapper, set()):
                index += 2
                continue
            index += 1
        if wrapper == "timeout" and index < len(tokens):
            index += 1
    return index


def _contains_shell_evaluator(tokens: list[ShellToken]) -> bool:
    for index, token in enumerate(tokens):
        command_name = Path(token.value).name.casefold()
        if command_name in _SHELL_EVALUATORS:
            return True
        if (
            command_name in _BUSYBOX_COMMANDS
            and index + 1 < len(tokens)
            and Path(tokens[index + 1].value).name.casefold()
            in _SHELL_EVALUATORS
        ):
            return True
    return False


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
        if Path(tokens[index].value).name.casefold() not in _ENV_COMMANDS:
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
                    target = (
                        arguments[index + 1]
                        if index + 1 < len(arguments)
                        else token
                    )
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


def _targets_new_pr(tokens: list[ShellToken], cwd: Path) -> bool:
    arguments = _python_arguments(tokens, cwd)
    if arguments is not None:
        target, dynamic = _execution_target(arguments)
        if target is not None and (
            _could_target_new_pr(target.value) or _could_target_new_pr(target.raw)
        ):
            return True
        if dynamic and any(
            _could_target_new_pr(argument.value)
            or _could_target_new_pr(argument.raw)
            for argument in arguments
        ):
            return True
        return any(
            token.value.startswith("PYTHONSTARTUP=")
            and _could_target_new_pr(token.value.partition("=")[2])
            for token in tokens
        )

    target_mentioned = any(
        _could_target_new_pr(token.value) or _could_target_new_pr(token.raw)
        for token in tokens
    )
    python_mentioned = any(
        _is_python_interpreter(token.value)
        or "python" in token.value.casefold()
        or "pypy" in token.value.casefold()
        for token in tokens
    )
    dynamic_command = any(
        any(marker in token.raw for marker in ("$", "*", "?", "[", "{", "\\\n"))
        for token in tokens
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
        marker in script_reference.raw
        for marker in ("$", "`", "\\\n", "{", "[", "*", "?")
    ):
        raise GuardViolationError("new_pr.py script path cannot use shell expansion")
    if any(("$" in token.raw or "`" in token.raw) for token in tokens[3:]):
        raise GuardViolationError("argument substitution is not allowed")
    return script_reference


def _validate_new_pr_arguments(tokens: list[ShellToken], cwd: Path) -> None:
    values: dict[str, str] = {}
    index = 3
    while index < len(tokens):
        option = tokens[index].value
        if option not in {"--title", "--body-file"}:
            raise GuardViolationError(
                "new_pr.py accepts only --title and --body-file here"
            )
        if option in values or index + 1 >= len(tokens):
            raise GuardViolationError(
                f"new_pr.py option {option} is duplicate or missing its value"
            )
        values[option] = tokens[index + 1].value
        index += 2
    if set(values) != {"--title", "--body-file"}:
        raise GuardViolationError(
            "new_pr.py requires exactly --title and --body-file"
        )
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
            "new_pr.py body file must be one .md file directly under "
            ".agents/scratch"
        )
    if ".." in body_reference.parts:
        raise GuardViolationError(
            "new_pr.py body file cannot traverse parent directories"
        )
    body_path = cwd / body_reference
    for parent in (cwd / ".agents", cwd / ".agents" / "scratch"):
        if parent.is_symlink():
            raise GuardViolationError(
                "new_pr.py body file parent cannot be a symlink"
            )
    try:
        body_stat = body_path.lstat()
    except OSError as exc:
        raise GuardViolationError(
            "new_pr.py body file must be an existing regular file"
        ) from exc
    if (
        body_path.is_symlink()
        or not stat.S_ISREG(body_stat.st_mode)
        or body_stat.st_nlink != 1
    ):
        raise GuardViolationError(
            "new_pr.py body file must be a single-link regular file"
        )


def _regular_resolved_file(path: Path) -> Path | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _require_trusted_digest(path: Path, expected: str, label: str) -> None:
    try:
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as exc:
        raise GuardViolationError(f"{label} is unreadable") from exc
    if actual != expected:
        raise GuardViolationError(f"{label} does not match the trusted plugin copy")


def _validate_runtime_bundle(script: Path) -> None:
    _require_trusted_digest(script, _TRUSTED_NEW_PR_SHA256, "new_pr.py")
    helper = _regular_resolved_file(script.parent / "validate_pr_description.py")
    if helper is None:
        raise GuardViolationError(
            "validate_pr_description.py is missing, unreadable, or a symlink"
        )
    _require_trusted_digest(
        helper,
        _TRUSTED_VALIDATE_PR_DESCRIPTION_SHA256,
        "validate_pr_description.py",
    )


def _runtime_script() -> Path | None:
    runtime_root = Path(__file__).resolve().parents[2]
    return _regular_resolved_file(runtime_root / _SCRIPT_RELATIVE_PATH)


def _script_path(script_reference: ShellToken, cwd: Path) -> Path:
    if script_reference.value == _PLUGIN_SCRIPT_REFERENCE:
        if script_reference.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"':
            raise GuardViolationError(
                "plugin script reference must use the exact double-quoted form"
            )
        configured_root = (
            os.environ.get("COPILOT_PLUGIN_ROOT")
            or os.environ.get("CLAUDE_PLUGIN_ROOT")
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
        if (
            runtime_script is None
            or not path.is_absolute()
            or path != runtime_script
        ):
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
        tokens = _split_command(command)
        if _contains_shell_evaluator(tokens):
            raise GuardViolationError("shell evaluator wrappers are not allowed")
        if not _requires_identity_check(command, cwd):
            return 0
        if _contains_shell_expansion(command) and _python_arguments(
            tokens, cwd
        ) is None:
            raise GuardViolationError(
                "shell-expanded commands outside the exact allowlist are not allowed"
            )
        arguments = _python_arguments(tokens, cwd)
        if arguments is not None:
            target, dynamic = _execution_target(arguments)
            if dynamic:
                raise GuardViolationError(
                    "dynamic Python -c and -m launchers are not allowed"
                )
            if (
                target is not None
                and not dynamic
                and _contains_shell_expansion(target.raw)
                and target.raw != f'"{_PLUGIN_SCRIPT_REFERENCE}"'
            ):
                raise GuardViolationError(
                    "Python script paths cannot use shell expansion"
                )
        if not _targets_new_pr(tokens, cwd):
            if arguments is not None:
                raise GuardViolationError(
                    "Python execution is limited to the approved new_pr.py"
                )
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
