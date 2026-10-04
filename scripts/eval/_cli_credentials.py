"""One credential resolution order for every subscription CLI transport.

Commonality: `claude-cli`, `codex-cli`, and `copilot-cli` all bill a seat, and
all find the credential the same way. Variability: the environment names each
CLI reads, where each CLI keeps its login on disk, and how to ask each CLI
whether it is already signed in. The order lives here once. Each transport
declares a `CredentialSpec` with its variability and calls
`resolve_credential`.

The order, first hit wins:

1. `env`: the transport's subscription variables, then dotenv files. The file
   list is `EVAL_DOTENV_FILES` (`os.pathsep`-separated: `:` on POSIX, `;` on
   Windows; `~` and globs expanded) and defaults to the repository-root `.env`.
   A named pipe (a 1Password mount, for example) is read with a timeout, and a
   timeout reads as not found.
   Recorded as `env` for the process environment and `dotenv` for a file.
2. `disk`: the credential the CLI itself stored. Recorded as `disk`. A spec
   that sets `own_login_first` swaps steps 2 and 3, so the CLI's own stored
   login wins and the disk source is the last resort. Copilot sets it: its own
   login is preferred over `gh auth token`, whose OAuth token usually carries
   wider scopes than Copilot needs. That fallback is recorded as
   `disk-gh-fallback`, never `disk`.
3. `existing-login`: the already-authenticated CLI as it stands, with no
   relocated config directory and no injected token. Taken only when the CLI
   reports a subscription login. Recorded as `existing-login`.
4. `prompt`: ask for the token, only when stdin is a terminal. Otherwise
   raise `CredentialNotFoundError` carrying the transport's own message.

Billing is not this module's job to enforce, but it must not weaken it: a
resolver reads only the names in its spec, never `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY`, and never logs or returns a value anywhere except in
`ResolvedCredential.secret`, which is excluded from `repr`. Callers record
`step`, never `secret`.
"""

from __future__ import annotations

import getpass
import glob
import os
import select
import stat
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "DOTENV_FILES_ENV",
    "EXISTING_LOGIN_NOTE",
    "STEP_DISK",
    "STEP_DISK_GH_FALLBACK",
    "STEP_DOTENV",
    "STEP_ENV",
    "STEP_EXISTING_LOGIN",
    "STEP_PROMPT",
    "CredentialNotFoundError",
    "CredentialSpec",
    "ResolvedCredential",
    "parse_dotenv",
    "recorded_steps",
    "reset_credential_cache",
    "resolve_cached",
    "resolve_credential",
    "step_label",
]

#: Colon-separated dotenv file list. Example for a 1Password mount:
#: `EVAL_DOTENV_FILES=~/.config/1password-env/*.env`.
DOTENV_FILES_ENV = "EVAL_DOTENV_FILES"

STEP_ENV = "env"
STEP_DOTENV = "dotenv"
STEP_DISK = "disk"
STEP_DISK_GH_FALLBACK = "disk-gh-fallback"
STEP_EXISTING_LOGIN = "existing-login"
STEP_PROMPT = "prompt"

#: What a report header says when the CLI ran on its own login.
EXISTING_LOGIN_NOTE = "existing login: user config may load"

#: Seconds to wait on a named pipe before treating it as not found.
FIFO_TIMEOUT_SECONDS = 5.0
_MAX_DOTENV_BYTES = 65536
_REPO_ROOT = Path(__file__).resolve().parents[2]


class CredentialNotFoundError(RuntimeError):
    """No step produced a credential and stdin cannot prompt for one."""


@dataclass(frozen=True)
class CredentialSpec:
    """The per-CLI variability the shared order needs."""

    transport: str
    #: Variables read in order, at step 1, from the environment and dotenv.
    env_names: tuple[str, ...]
    #: The one variable the CLI reads the credential from when it is injected.
    inject_env: str
    #: Step 2: return the stored credential or None. Must never raise.
    read_disk: Callable[[Mapping[str, str]], str | None]
    #: Step 3: True when the CLI reports a subscription login. Must never raise.
    login_probe: Callable[[str, Mapping[str, str]], bool]
    #: Raised at step 4 when stdin is not a terminal.
    missing_message: str
    #: True swaps steps 2 and 3: the CLI's own login beats the disk source.
    own_login_first: bool = False
    #: The step name recorded when the disk source hits.
    disk_step: str = STEP_DISK


@dataclass(frozen=True)
class ResolvedCredential:
    """Which step produced the credential, and the value for steps 1, 2, 4."""

    step: str
    secret: str | None = field(default=None, repr=False)

    @property
    def injects_token(self) -> bool:
        return self.secret is not None


def parse_dotenv(text: str, names: tuple[str, ...]) -> dict[str, str]:
    """Return the first value of each wanted name found in dotenv `text`."""
    wanted = set(names)
    found: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in wanted or key in found:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if value:
            found[key] = value
    return found


def _read_fifo(path: str, timeout: float) -> str | None:
    """Read a named pipe, or None when no writer answers within `timeout`.

    The pipe opens non-blocking, so a mount with no writer cannot hang the
    run. `select` bounds every wait, and EOF ends the read.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    except OSError:
        return None
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    size = 0
    try:
        while size <= _MAX_DOTENV_BYTES:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                return None
            data = os.read(fd, 4096)
            if not data:
                break
            chunks.append(data)
            size += len(data)
    except OSError:
        return None
    finally:
        os.close(fd)
    if not chunks or size > _MAX_DOTENV_BYTES:
        return None
    return b"".join(chunks).decode("utf-8", errors="replace")


def _read_dotenv_file(path: str, timeout: float, *, allow_symlink: bool) -> str | None:
    """Return a dotenv file's text, or None for anything unreadable."""
    try:
        if Path(path).is_symlink() and not allow_symlink:
            return None
        mode = os.stat(path).st_mode
    except OSError:
        return None
    if stat.S_ISFIFO(mode):
        return _read_fifo(path, timeout)
    if not stat.S_ISREG(mode):
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_DOTENV_BYTES + 1)
    except OSError:
        return None
    # A cut-off file could yield a truncated token, so refuse it whole.
    if len(data) > _MAX_DOTENV_BYTES:
        return None
    return data.decode("utf-8", errors="replace")


def _dotenv_candidates(environ: Mapping[str, str]) -> list[tuple[str, bool]]:
    """Return (path, symlink_allowed) pairs in lookup order.

    The default is the repository-root `.env` with symlinks refused: the same
    CWE-22 stance `_anthropic_api.load_api_key` takes. Paths the operator names
    in `EVAL_DOTENV_FILES` are an explicit choice, so a symlink is allowed.
    """
    configured = environ.get(DOTENV_FILES_ENV, "").strip()
    if not configured:
        return [(str(_REPO_ROOT / ".env"), False)]
    paths: list[tuple[str, bool]] = []
    for entry in configured.split(os.pathsep):
        pattern = os.path.expanduser(entry.strip())
        if not pattern:
            continue
        matches = sorted(glob.glob(pattern)) or [pattern]
        paths.extend((match, True) for match in matches)
    return paths


def _from_dotenv(names: tuple[str, ...], environ: Mapping[str, str], timeout: float) -> str | None:
    values: dict[str, str] = {}
    for path, allow_symlink in _dotenv_candidates(environ):
        text = _read_dotenv_file(path, timeout, allow_symlink=allow_symlink)
        if text is None:
            continue
        for key, value in parse_dotenv(text, names).items():
            values.setdefault(key, value)
    return next((values[name] for name in names if name in values), None)


def _from_environment(names: tuple[str, ...], environ: Mapping[str, str]) -> str | None:
    for name in names:
        value = environ.get(name, "").strip()
        if value:
            return value
    return None


def _prompt_for_token(spec: CredentialSpec) -> str | None:
    value = getpass.getpass(f"{spec.transport} subscription token ({spec.inject_env}): ")
    return value.strip() or None


def resolve_credential(
    spec: CredentialSpec,
    *,
    executable: str,
    environ: Mapping[str, str] | None = None,
    stdin_is_tty: bool | None = None,
    fifo_timeout: float | None = None,
) -> ResolvedCredential:
    """Walk the four steps and return the first hit. See the module docstring."""
    env = os.environ if environ is None else environ
    wait = FIFO_TIMEOUT_SECONDS if fifo_timeout is None else fifo_timeout
    if (token := _from_environment(spec.env_names, env)) is not None:
        return ResolvedCredential(STEP_ENV, token)
    if (token := _from_dotenv(spec.env_names, env, wait)) is not None:
        return ResolvedCredential(STEP_DOTENV, token)
    if spec.own_login_first and spec.login_probe(executable, env):
        return ResolvedCredential(STEP_EXISTING_LOGIN)
    if (token := spec.read_disk(env)) is not None:
        return ResolvedCredential(spec.disk_step, token)
    if not spec.own_login_first and spec.login_probe(executable, env):
        return ResolvedCredential(STEP_EXISTING_LOGIN)
    tty = sys.stdin.isatty() if stdin_is_tty is None else stdin_is_tty
    if tty and (token := _prompt_for_token(spec)) is not None:
        return ResolvedCredential(STEP_PROMPT, token)
    raise CredentialNotFoundError(spec.missing_message)


_RESOLVED: dict[str, ResolvedCredential] = {}


def resolve_cached(spec: CredentialSpec, *, executable: str) -> ResolvedCredential:
    """Resolve once per process, so a prompt is never repeated per call."""
    cached = _RESOLVED.get(spec.transport)
    if cached is None:
        cached = resolve_credential(spec, executable=executable)
        _RESOLVED[spec.transport] = cached
    return cached


def reset_credential_cache() -> None:
    _RESOLVED.clear()


def recorded_steps() -> list[str]:
    """Steps chosen so far in this process, for the report. Never a value."""
    return sorted({resolved.step for resolved in _RESOLVED.values()})


def step_label(step: str) -> str:
    """Human wording for a report header."""
    return EXISTING_LOGIN_NOTE if step == STEP_EXISTING_LOGIN else step
