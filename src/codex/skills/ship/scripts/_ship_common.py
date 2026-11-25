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
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

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
SCRATCH_REL = Path(".project-toolkit") / "scratch"
VERSION = "1.0.0"

_CONTROL_RE = re.compile("[\x00-\x1f\x7f\x85  ]")
# Bounded and anchored so a long value cannot make the scan quadratic: a
# scheme starts after a non-scheme character and is at most 32 characters,
# and userinfo is at most 256.
_USERINFO_RE = re.compile(r"(?<![A-Za-z0-9+.-])([A-Za-z][A-Za-z0-9+.-]{0,31}://)[^/@\s]{0,256}@")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
# ADR-127 decision 3 item 4: a remote URL must match an allowed scheme list.
# git also accepts transports such as ext::, file://, and git://; none of
# them is a GitHub or Azure DevOps remote, so they are refused.
ALLOWED_URL_SCHEMES = frozenset({"https", "ssh"})
_URL_HOST_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://(?:[^/@]*@)?([^/:\s]+)")
_SCP_HOST_RE = re.compile(r"^(?:[^@/:\s]+@)?([^/:\s]+):(?![/:])\S")
# One or more DNS labels: letters, digits, inner dashes. No empty label,
# no trailing dot, no bracket literal, at least two characters in all.
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_PLAIN_HOST_RE = re.compile(rf"^(?=.{{2,253}}$){_LABEL}(?:\.{_LABEL})*$")
_ADO_HOSTS = frozenset({"dev.azure.com", "ssh.dev.azure.com"})


def clean(value: object) -> str:
    """Return ``value`` as one safe line: no userinfo, no control characters."""
    text = _USERINFO_RE.sub(r"\1", str(value))
    text = _CONTROL_RE.sub(" ", text)
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


@dataclass
class Result:
    """The ordered result lines and one terminal line of a script run."""

    script: str
    reasons: frozenset[str]
    lines: list[tuple[str, str]] = field(default_factory=list)
    terminal: tuple[str, str] | None = None
    exit_code: int = EXIT_OK

    def add(self, key: str, value: object) -> Result:
        if not KEY_RE.match(key) or key in ("NEXT", "STOP"):
            raise ValueError(f"invalid result key: {key!r}")
        self.lines.append((key, clean(value)))
        return self

    def next(self, act: str) -> Result:
        if not TOKEN_RE.match(act):
            raise ValueError(f"invalid NEXT act: {act!r}")
        self._set_terminal(("NEXT", act), EXIT_OK)
        return self

    def stop(self, reason: str, code: int, detail: object = "") -> Result:
        if reason not in self.reasons or not TOKEN_RE.match(reason):
            raise ValueError(f"undeclared STOP reason: {reason!r}")
        if code not in _STOP_CODES:
            raise ValueError(f"STOP needs an exit code 1 to 4, got {code}")
        text = clean(detail)
        if len(text) > MAX_DETAIL_CHARS:
            text = text[: MAX_DETAIL_CHARS - 3] + "..."
        self._set_terminal(("STOP", f"{reason} {text}".rstrip()), code)
        return self

    @property
    def stopped(self) -> bool:
        return self.terminal is not None and self.terminal[0] == "STOP"

    def _set_terminal(self, terminal: tuple[str, str], code: int) -> None:
        if self.terminal is not None:
            raise ValueError("terminal line already set")
        self.terminal = terminal
        self.exit_code = code


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


def scratch_dir(root: Path, create: bool = False) -> Path | None:
    """Return the real scratch directory under ``root``, or None when it is unsafe.

    Each component (``.project-toolkit`` and ``scratch``) must be a real
    directory, not a symlink, and the result must resolve under the real
    repository root. A symlinked component could point the confinement anchor
    anywhere on disk, so it is refused rather than followed.
    """
    try:
        real_root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    current = real_root
    for part in SCRATCH_REL.parts:
        current = current / part
        if current.is_symlink():
            return None
        if not current.exists():
            if not create:
                return None
            try:
                current.mkdir(mode=0o700)
            except OSError:
                return None
        if not current.is_dir():
            return None
    try:
        resolved = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved != real_root / SCRATCH_REL:
        return None
    return resolved


def write_private(root: Path, prefix: str, suffix: str, text: str) -> Path | None:
    """Write ``text`` to a new owner-only file in the scratch directory."""
    directory = scratch_dir(root, create=True)
    if directory is None:
        return None
    path = directory / f"{prefix}-{uuid.uuid4().hex}{suffix}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        return None
    return path


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


def run(
    argv: list[str],
    cwd: Path | None = None,
    timeout: float = 120,
    stdin_text: str | None = None,
) -> Completed:
    """Run ``argv`` without a shell. A missing binary is 127; a timeout is 124."""
    try:
        done = subprocess.run(
            argv,
            cwd=str(cwd) if cwd is not None else None,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError:
        return Completed(127, "", f"{argv[0]}: not found")
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
    if not _REF_RE.match(value):
        return False
    if ".." in value or "//" in value or value.endswith(("/", ".lock", ".")):
        return False
    return "@{" not in value


def remote_host(url: str) -> str | None:
    """Return the lowercase host of a git remote URL, or None when it is not allowed.

    Allowed forms: ``https://`` and ``ssh://`` URLs, and the scp-like
    ``[user@]host:path`` form. A local path, another scheme, and a transport
    such as ``ext::`` all return None.
    """
    url = url.strip()
    if "://" in url:
        match = _URL_HOST_RE.match(url)
        if match is None or match.group(1).lower() not in ALLOWED_URL_SCHEMES:
            return None
        return _plain_host(match.group(2).lower())
    if url.startswith(("/", ".", "~")):
        return None
    match = _SCP_HOST_RE.match(url)
    if match is None:
        return None
    return _plain_host(match.group(1).lower())


def _plain_host(host: str) -> str | None:
    """Return ``host`` when it is a plain DNS-style name, else None.

    A host is at least two characters, starts with a letter or digit, and
    holds only letters, digits, dots, and dashes. That refuses a Windows
    drive path (C:\\repo), an ssh option (-oX=y:z), and a bracket literal.
    """
    if _PLAIN_HOST_RE.match(host) is None:
        return None
    return host


def classify_host(host: str) -> str:
    """Map a parsed host to ``ado`` or ``github``. Matches the host, not a substring."""
    if host in _ADO_HOSTS or host.endswith(".visualstudio.com"):
        return "ado"
    return "github"


def confine_body_file(raw: str, root: Path) -> Path | None:
    """Return the resolved body file when it is a regular file in the scratch dir."""
    if not raw or raw.startswith("-") or raw.startswith("@"):
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    scratch = scratch_dir(root)
    if scratch is None:
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if scratch not in resolved.parents or not resolved.is_file():
        return None
    return resolved


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
