"""Per-CLI variability for `_cli_credentials`: disk readers and login probes.

Every reader and probe here swallows its own failures and answers None or
False, so a corrupt, missing, or unreadable file falls through to the next
step. None of them logs, prints, or raises with a credential in the message.

Sources, each read on 2026-10-03:

- Claude Code: `.credentials.json` under the config directory with
  `claudeAiOauth.accessToken` and `expiresAt` (epoch milliseconds). The
  directory is `CLAUDE_CONFIG_DIR` when set, else `~/.claude`
  (https://code.claude.com/docs/en/claude-directory). Field names were
  confirmed against a live login on Linux. On macOS the login sits in the
  Keychain, so the file is absent and the order falls to `existing-login`.
  `claude auth status` prints JSON with `loggedIn` and `authMethod`;
  `claude.ai` is the subscription method.
- Codex: `$CODEX_HOME/auth.json`, default `~/.codex/auth.json`, shaped as
  `AuthDotJson` (`auth_mode`, `OPENAI_API_KEY`, `tokens.access_token`) in
  `codex-rs/login/src/auth/storage.rs` of github.com/openai/codex. A file that
  carries an API key is refused: it would bill the metered account.
  `codex login status` prints `Logged in using ChatGPT` for the plan login.
- Copilot: `copilot login --help` (CLI 1.0.91) lists the OAuth token from the
  GitHub CLI app as a supported token, so `gh auth token` is the disk source.
  A classic `ghp_` token is refused, as the same help text refuses it. The
  CLI's own store is the OS credential store or a plain-text file under
  `COPILOT_HOME`; its field layout is not documented, so it is not read here.
  `existing-login` covers it, because the CLI reads its own store itself. The
  probe reads `lastLoggedInUser.login` from `COPILOT_HOME/config.json`.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

__all__ = [
    "claude_disk_token",
    "claude_login_probe",
    "codex_auth_file_text",
    "codex_login_probe",
    "copilot_disk_token",
    "copilot_login_probe",
]

_PROBE_TIMEOUT_SECONDS = 20.0
_PROBE_ENV_NAMES = frozenset(
    {
        "APPDATA",
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "COPILOT_HOME",
        "HOME",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "USERPROFILE",
    }
)


def _home_dir(environ: Mapping[str, str], name: str, default: str) -> Path:
    configured = environ.get(name, "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(environ.get("HOME") or Path.home()) / default


_MAX_FILE_BYTES = 64 * 1024


def _read_regular_text(path: Path) -> str:
    """Read a small regular file; a FIFO, device, or oversized file raises OSError.

    Refusing non-regular files keeps a FIFO at an operator-set config path from
    hanging the run (CWE-400).
    """
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FILE_BYTES:
        raise OSError(f"not a small regular file: {path.name}")
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> object:
    try:
        return json.loads(_read_regular_text(path))
    except (OSError, ValueError):
        return None


def claude_disk_token(environ: Mapping[str, str]) -> str | None:
    """Return the stored Claude OAuth access token, or None."""
    payload = _read_json(_home_dir(environ, "CLAUDE_CONFIG_DIR", ".claude") / ".credentials.json")
    oauth = payload.get("claudeAiOauth") if isinstance(payload, dict) else None
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    expires = oauth.get("expiresAt")
    if not isinstance(token, str) or not token.strip():
        return None
    if isinstance(expires, (int, float)) and expires <= time.time() * 1000:
        return None
    return token.strip()


def codex_auth_file_text(environ: Mapping[str, str]) -> str | None:
    """Return the plan-login `auth.json` text, or None.

    The text is returned whole because Codex authenticates only from that file
    (`CODEX_ACCESS_TOKEN` is ignored for a ChatGPT login, see the README).
    """
    path = _home_dir(environ, "CODEX_HOME", ".codex") / "auth.json"
    try:
        text = _read_regular_text(path)
        payload = json.loads(text)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("OPENAI_API_KEY"):
        return None
    tokens = payload.get("tokens")
    access = tokens.get("access_token") if isinstance(tokens, dict) else None
    if not isinstance(access, str) or not access.strip():
        return None
    return text


def copilot_disk_token(environ: Mapping[str, str]) -> str | None:
    """Return the GitHub CLI's token for the Copilot CLI, or None."""
    try:
        completed = subprocess.run(
            ["gh", "auth", "token"],
            env=_probe_env(environ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = (completed.stdout or "").strip()
    refused = token.startswith(("ghp_", "ghs_"))
    if completed.returncode != 0 or not re.fullmatch(r"\S+", token) or refused:
        return None
    return token


def _probe_env(environ: Mapping[str, str]) -> dict[str, str]:
    """A minimal environment for a probe: no metered key can reach the CLI."""
    return {name: value for name in _PROBE_ENV_NAMES if (value := environ.get(name))}


def _probe_output(argv: list[str], environ: Mapping[str, str]) -> str | None:
    try:
        completed = subprocess.run(
            argv,
            env=_probe_env(environ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout or "" if completed.returncode == 0 else None


def claude_login_probe(executable: str, environ: Mapping[str, str]) -> bool:
    """True when `claude auth status` reports a claude.ai subscription login."""
    output = _probe_output([executable, "auth", "status"], environ)
    try:
        payload = json.loads(output) if output else None
    except ValueError:
        return False
    return (
        isinstance(payload, dict)
        and payload.get("loggedIn") is True
        and payload.get("authMethod") == "claude.ai"
    )


def codex_login_probe(executable: str, environ: Mapping[str, str]) -> bool:
    """True when `codex login status` reports the ChatGPT plan login."""
    output = _probe_output([executable, "login", "status"], environ)
    return output is not None and "ChatGPT" in output


def copilot_login_probe(executable: str, environ: Mapping[str, str]) -> bool:
    """True when the Copilot config records a logged-in user.

    The Copilot CLI has no status command, so this reads the same
    `lastLoggedInUser` record the CLI writes after `copilot login`.
    """
    del executable
    path = _home_dir(environ, "COPILOT_HOME", ".copilot") / "config.json"
    try:
        text = _read_regular_text(path)
    except (OSError, ValueError):
        return False
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    try:
        payload = json.loads(body)
    except ValueError:
        return False
    user = payload.get("lastLoggedInUser") if isinstance(payload, dict) else None
    return isinstance(user, dict) and bool(user.get("login"))
