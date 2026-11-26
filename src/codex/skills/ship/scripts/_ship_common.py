"""Shared result-line protocol and guards for the ship driver scripts (ADR-127).

Every ship script prints ``KEY: value`` lines and ends on one ``NEXT: <act>``
or ``STOP: <reason> [detail]`` line (ADR-127 decision 4). This module owns
that protocol so the three scripts cannot drift apart:

* values are one line: control characters and Unicode line breaks become
  spaces, and URL userinfo is stripped, so a remote value cannot forge a
  control line or leak a credential;
* stdout stays within 60 lines and 32,000 bytes; overflow goes to a detail
  file in the scratch directory, whose path is printed;
* ``NEXT`` pairs with exit 0 and ``STOP`` with an ADR-035 code 1 to 4;
* ``--output-format json`` emits the ADR-103 envelope with the same keys.

Stdlib only, Python 3.10 floor: the scripts run on the host interpreter under
``python3 -I``, which drops the script directory from ``sys.path``. Each script
loads this file by absolute path, leaving ``sys.path`` alone.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, NoReturn

KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
TOKEN_RE = re.compile(r"^[a-z][a-z0-9-]*$")
MAX_LINES = 60
MAX_BYTES = 32000
# A STOP detail is one line of evidence, never a log. JSON prints it twice
# (Data.STOP and Error.Message), so it is capped well under MAX_BYTES / 2.
MAX_DETAIL_CHARS = 500
# Room kept under the byte cap for the DETAIL_FILE and terminal lines.
_TAIL_RESERVE = 1024

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4
_STOP_CODES = (EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL, EXIT_AUTH)
_ERROR_TYPES = {
    EXIT_LOGIC: "VerificationFailed",
    EXIT_CONFIG: "InvalidParams",
    EXIT_EXTERNAL: "ApiError",
    EXIT_AUTH: "AuthError",
}

OUTPUT_FORMATS = ("json", "human", "auto")
VERSION = "1.0.0"

CONTROL_RE = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")  # C0, DEL, C1, line breaks
_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}")


# A token ends only at ASCII whitespace. Unicode spaces and control
# characters stay inside it, so a password holding one is still cut.
_ASCII_SPACE = frozenset(" \t\n\r\v\f")


def _strip_userinfo(text: str) -> str:
    """Drop everything between ``://`` and the last ``@`` of the same token.

    A token is the run of non-space characters after ``://``. Cutting to the
    last ``@`` removes a password that itself holds ``@`` or ``/``, at any
    length. A path segment holding ``@`` is over-redacted; that is the safe
    side. One pass over the text, so a long value stays linear.
    """
    out: list[str] = []
    start = 0
    while True:
        marker = text.find("://", start)
        if marker < 0:
            out.append(text[start:])
            return "".join(out)
        token_start = marker + 3
        token_end = token_start
        while token_end < len(text) and text[token_end] not in _ASCII_SPACE:
            token_end += 1
        token = text[token_start:token_end]
        out.append(text[start:token_start])
        out.append(token[token.rfind("@") + 1 :])
        start = token_end


def load_sibling(
    name: str,
) -> ModuleType:  # pragma: no cover - runs only in a fresh interpreter; see test_ship_edges.py::test_script_runs_under_isolated_mode
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().with_name(f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if TYPE_CHECKING:
    import _ship_paths as _paths
    import _ship_remote as _remote
    import _ship_windows as _windows
else:
    _remote = load_sibling("_ship_remote")
    _paths = load_sibling("_ship_paths")
    _windows = load_sibling("_ship_windows")
SCRATCH_REL = _paths.SCRATCH_REL
scratch_dir = _paths.scratch_dir
write_private = _paths.write_private
confine_body_file = _paths.confine_body_file
stored_int = _paths.stored_int
remote_host = _remote.remote_host
classify_host = _remote.classify_host


def clean(value: object) -> str:
    """Return ``value`` as one safe line: no userinfo, no control characters."""
    text = _strip_userinfo(str(value))
    text = CONTROL_RE.sub(" ", text)
    return " ".join(text.split())


class UsageError(Exception):
    """Raised by ``ResultParser`` instead of printing usage and exiting."""


class ResultParser(argparse.ArgumentParser):
    """An argparse parser that never abbreviates and never exits on a bad argument.

    A bad argument becomes ``STOP: bad-arguments`` with exit 2, so the driver
    always sees a terminal line (ADR-127 decision 4 item 7).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["allow_abbrev"] = False
        # argparse -h prints usage and exits 0 with no terminal line.
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)

    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def add_output_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-format", choices=OUTPUT_FORMATS, default="auto")


def resolve_format(requested: str) -> str:
    """ADR-103: ``auto`` is ``json`` when stdout is captured, else ``human``."""
    if requested in ("json", "human"):
        return requested
    try:
        return "human" if sys.stdout.isatty() else "json"
    except (AttributeError, ValueError):
        return "json"


def peek_format(argv: list[str]) -> str:
    """Read ``--output-format`` from raw argv, for output when parsing failed."""
    for index, token in enumerate(argv):
        if token == "--output-format" and index + 1 < len(argv):
            candidate = argv[index + 1]
        elif token.startswith("--output-format="):
            candidate = token.split("=", 1)[1]
        else:
            continue
        if candidate in OUTPUT_FORMATS:
            return resolve_format(candidate)
    return resolve_format("auto")


class Result:
    """The ordered result lines and one terminal line of a script run.

    State changes only through ``add``, ``next``, and ``stop``; the
    properties are read-only, so no caller can forge a terminal line or
    rewrite a recorded value.
    """

    __slots__ = ("_script", "_reasons", "_lines", "_terminal", "_exit_code")

    def __init__(self, script: str, reasons: frozenset[str]) -> None:
        self._script = script
        self._reasons = frozenset(reasons)
        self._lines: list[tuple[str, str]] = []
        self._terminal: tuple[str, str] | None = None
        self._exit_code = EXIT_OK

    @property
    def script(self) -> str:
        return self._script

    @property
    def lines(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._lines)

    @property
    def terminal(self) -> tuple[str, str] | None:
        return self._terminal

    @property
    def exit_code(self) -> int:
        return self._exit_code

    def add(self, key: str, value: object) -> Result:
        if not KEY_RE.fullmatch(key) or key in ("NEXT", "STOP"):
            raise ValueError(f"invalid result key: {key!r}")
        self._lines.append((key, clean(value)))
        return self

    def next(self, act: str) -> Result:
        if not TOKEN_RE.fullmatch(act):
            raise ValueError(f"invalid NEXT act: {act!r}")
        self._set_terminal(("NEXT", act), EXIT_OK)
        return self

    def stop(self, reason: str, code: int, detail: object = "") -> Result:
        if reason not in self._reasons or not TOKEN_RE.fullmatch(reason):
            raise ValueError(f"undeclared STOP reason: {reason!r}")
        if code not in _STOP_CODES:
            raise ValueError(f"STOP needs an exit code 1 to 4, got {code}")
        text = clean(detail)
        if len(text) > MAX_DETAIL_CHARS:
            text = text[: MAX_DETAIL_CHARS - 3] + "..."
        self._set_terminal(("STOP", f"{reason} {text}".rstrip()), code)
        return self

    def _set_terminal(self, terminal: tuple[str, str], code: int) -> None:
        if self._terminal is not None:
            raise ValueError("terminal line already set")
        self._terminal = terminal
        self._exit_code = code


def _line_size(line: str) -> int:
    """Bytes one result line costs in the larger of the two formats.

    The JSON form escapes quotes and backslashes, so a line is charged its
    JSON-encoded size. That keeps the byte cap true for both formats
    (ADR-127 decision 4 items 9 and 12).
    """
    return len(json.dumps(line, ensure_ascii=False).encode("utf-8")) + 1


def _capped_lines(result: Result, repo_root: Path | None) -> list[tuple[str, str]]:
    """Return lines within the caps, spilling the full set to a detail file."""
    body = [f"{key}: {value}" for key, value in result.lines]
    terminal = f"{result.terminal[0]}: {result.terminal[1]}" if result.terminal else ""
    total = sum(_line_size(line) for line in body) + _line_size(terminal)
    if len(body) + 1 <= MAX_LINES and total <= MAX_BYTES - _TAIL_RESERVE:
        return list(result.lines)
    kept: list[tuple[str, str]] = []
    used = 0
    budget = MAX_BYTES - _TAIL_RESERVE - _line_size(terminal)
    # The check above guarantees a break: over the line cap, kept stops at
    # MAX_LINES - 2; over the byte cap, the lines alone exceed the budget.
    for (key, value), line in zip(result.lines, body, strict=True):  # pragma: no branch
        size = _line_size(line)
        if len(kept) >= MAX_LINES - 2 or used + size > budget:
            break
        kept.append((key, value))
        used += size
    kept.append(("DETAIL_FILE", write_detail_file(body, repo_root)))
    return kept


def write_detail_file(body: list[str], repo_root: Path | None) -> str:
    """Write every result line to an owner-only scratch file; return its path."""
    if repo_root is None:
        return "unavailable"
    path = write_private(repo_root, "ship-detail", ".txt", "\n".join(body) + "\n")
    if path is None:
        return "unavailable"
    return path.relative_to(repo_root.resolve()).as_posix()


def _format(result: Result, lines: list[tuple[str, str]], output_format: str) -> str:
    """Format ``lines`` plus the terminal line in ``output_format``."""
    assert result.terminal is not None
    if output_format == "json":
        data: dict[str, object] = {}
        for key, value in lines:
            if key in data:
                existing = data[key]
                data[key] = [*existing, value] if isinstance(existing, list) else [existing, value]
            else:
                data[key] = value
        data[result.terminal[0]] = result.terminal[1]
        error = None
        if result.exit_code != EXIT_OK:
            error = {
                "Message": result.terminal[1],
                "Code": result.exit_code,
                "Type": _ERROR_TYPES[result.exit_code],
            }
        envelope = {
            "Success": result.exit_code == EXIT_OK,
            "Data": data,
            "Error": error,
            "Metadata": {
                "Script": result.script,
                "Version": VERSION,
                "Timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
        return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False) + "\n"
    text = [f"{key}: {value}" for key, value in lines]
    text.append(f"{result.terminal[0]}: {result.terminal[1]}")
    return "\n".join(text) + "\n"


def render(result: Result, output_format: str, repo_root: Path | None) -> str:
    """Return the stdout text for ``result`` in ``output_format``, within the caps.

    ``_capped_lines`` spills by an estimate. The final check here measures
    the rendered text itself and drops kept lines into the detail file until
    it fits, so the 32,000-byte cap holds for any input in either format.
    """
    if result.terminal is None:
        raise ValueError("result has no terminal line")
    lines = _capped_lines(result, repo_root)
    text = _format(result, lines, output_format)
    while len(text.encode("utf-8")) > MAX_BYTES:
        # Defensive: _capped_lines charges each line its JSON size and reserves room for
        # the doubled terminal line, so it has already spilled whenever this loop runs.
        if not any(key == "DETAIL_FILE" for key, _value in lines):  # pragma: no cover
            body = [f"{key}: {value}" for key, value in result.lines]
            lines.append(("DETAIL_FILE", write_detail_file(body, repo_root)))
        droppable = [index for index, (key, _value) in enumerate(lines) if key != "DETAIL_FILE"]
        if not droppable:  # pragma: no cover - a capped terminal line plus the envelope fit alone
            break
        del lines[droppable[-1]]
        text = _format(result, lines, output_format)
    return text


def emit(result: Result, output_format: str, repo_root: Path | None) -> int:
    """Print ``result`` and return its exit code."""
    sys.stdout.write(render(result, output_format, repo_root))
    sys.stdout.flush()
    return result.exit_code


@dataclass(frozen=True)
class Completed:
    returncode: int
    stdout: str
    stderr: str


# Variables that would point a child at another repository or host than the
# checkout and its origin (ADR-127 decision 3 item 6). Calls that do not read
# the origin remote, such as gh api, name the host with --hostname instead.
# Git configuration (GIT_CONFIG_*, GIT_SSH_COMMAND) is user setup, not a
# target, and passes through.
CHILD_ENV_DROP = frozenset(
    {
        "GH_REPO",
        "GH_HOST",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
    }
)


def child_env() -> dict[str, str]:
    """The environment for child processes, without target-changing variables."""
    return {key: value for key, value in os.environ.items() if key not in CHILD_ENV_DROP}


# One script run is one agent tool call, which the host kills at 600 seconds.
# Every child call shares this budget, so the run ends on a terminal line.
RUN_BUDGET_SECONDS = 540
_RUN_DEADLINE = time.monotonic() + RUN_BUDGET_SECONDS


# Lines a helper prints after the real cause: they name the failure, not why.
_FOOTER_RE = re.compile(
    r"^(PR creation failed \(exit code|error: failed to push some refs|hint:|To \S)"
)


def cause_line(stderr: str, fallback: str) -> str:
    """The last stderr line that states a cause, skipping helper footer lines."""
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    causes = [line for line in lines if not _FOOTER_RE.match(line)]
    return (causes or lines or [fallback])[-1]


def remaining_seconds() -> float:
    """Seconds left in this run's shared budget, never below 1."""
    return max(1.0, _RUN_DEADLINE - time.monotonic())


def run(
    argv: list[str],
    cwd: Path | None = None,
    timeout: float = 120,
    stdin_text: str | None = None,
) -> Completed:
    """Run ``argv`` without a shell. A missing binary is 127; a timeout is 124.

    On Windows, ``_ship_windows`` resolves a bare name, and an argument that
    cmd.exe would rewrite for a ``.cmd`` target is refused as 126.

    The timeout never exceeds the time left in the run's shared budget.
    """
    timeout = min(timeout, remaining_seconds())
    command = _windows.command(argv)
    if command is None:
        return Completed(126, "", f"{argv[0]}: refused an argument cmd.exe would rewrite")
    try:
        done = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
            env=child_env(),
        )
    except FileNotFoundError:
        return Completed(127, "", f"{argv[0]}: not found")
    except OSError as exc:
        # A binary that exists but cannot run (no execute bit, bad format) is
        # a failed call, never a crash, so the script still ends on STOP.
        return Completed(126, "", f"{argv[0]}: cannot run: {exc.strerror or exc}")
    except subprocess.TimeoutExpired:
        return Completed(124, "", f"{argv[0]}: timed out after {timeout:g}s")
    return Completed(done.returncode, done.stdout or "", done.stderr or "")


def git(args: list[str], cwd: Path | None = None, timeout: float = 60) -> Completed:
    return run(["git", *args], cwd=cwd, timeout=timeout)


def repo_root(cwd: Path | None = None) -> Path | None:
    done = git(["rev-parse", "--show-toplevel"], cwd=cwd)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    return Path(done.stdout.strip()).resolve()


def safe_ref(value: str) -> bool:
    """Return whether ``value`` is a plain branch name safe to pass as an argument."""
    if not _REF_RE.fullmatch(value):
        return False
    if ".." in value or "//" in value or value.endswith(("/", ".lock", ".")):
        return False
    return "@{" not in value


def skill_script(skill: str, *parts: str) -> Path:
    """Path of a script in a sibling skill of the same install tree."""
    return Path(__file__).resolve().parents[2].joinpath(skill, "scripts", *parts)


def parse_json(text: str) -> object | None:
    """Parse ``text`` as JSON; return None when it does not parse."""
    try:
        value: object = json.loads(text)
        return value
    except (json.JSONDecodeError, ValueError):
        return None
