"""Isolated workspace setup for real-CLI runtime parity evaluation."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from _runtime_parity_types import ParityConfigError

SENTINEL = "PARITY_PROFILE_SENTINEL_4853"
GIT_CONTEXT_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
)
AGENT_NAME = "parity"


class WorkspaceFixture(Protocol):
    prompt: str
    setup_files: Mapping[str, str]
    claude_agent: Path
    copilot_agent: Path
    claude_instruction: Path | None
    copilot_instruction: Path | None


def safe_workspace_file(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ParityConfigError(f"assertion path escapes workspace: {relative}") from exc
    return candidate


def _installed_agent_bytes(source: Path) -> bytes:
    """Return the exact agent bytes installed under the parity name."""
    with source.open(encoding="utf-8", newline="") as source_file:
        text = source_file.read()
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ParityConfigError(f"{source} has no frontmatter block")
    for index in range(1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "---":
            break
        if lines[index].startswith("name:"):
            line_ending = lines[index][len(lines[index].rstrip("\r\n")) :]
            lines[index] = f"name: {AGENT_NAME}{line_ending}"
            return "".join(lines).encode("utf-8")
    raise ParityConfigError(f"{source} frontmatter has no name field")


def hash_installed_agent(source: Path) -> str:
    """Return the digest of the transformed bytes loaded by the CLI."""
    return hashlib.sha256(_installed_agent_bytes(source)).hexdigest()


def _install_agent(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_installed_agent_bytes(source))


def _install_instruction(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def _nested_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in GIT_CONTEXT_VARIABLES:
        env.pop(name, None)
    return env


def prepare_workspace(
    fixture: WorkspaceFixture,
    harness: str,
    workspace: Path,
) -> None:
    """Create one isolated git repository and install its prompt artifacts."""
    workspace.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=workspace,
        env=_nested_git_env(),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (workspace / "PARITY_FIXTURE.md").write_text(fixture.prompt, encoding="utf-8")
    for relative, content in fixture.setup_files.items():
        path = safe_workspace_file(workspace, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    profile = workspace / ".parity-profile" / harness
    profile.mkdir(parents=True)
    if harness == "claude":
        (profile / "CLAUDE.md").write_text(
            f"Append {SENTINEL} to every answer.",
            encoding="utf-8",
        )
        _install_agent(fixture.claude_agent, workspace / ".claude/agents/parity.md")
        if fixture.claude_instruction is not None:
            _install_instruction(
                fixture.claude_instruction,
                workspace / ".claude/rules/completion-terminal.md",
            )
        return
    (profile / "copilot-instructions.md").write_text(
        f"Append {SENTINEL} to every answer.",
        encoding="utf-8",
    )
    _install_agent(fixture.copilot_agent, workspace / ".github/agents/parity.agent.md")
    if fixture.copilot_instruction is not None:
        _install_instruction(
            fixture.copilot_instruction,
            workspace / ".github/instructions/completion-terminal.instructions.md",
        )
    else:
        (workspace / ".github/copilot-instructions.md").write_text(
            f"Append {SENTINEL} to every answer.",
            encoding="utf-8",
        )


def _profile_roots(profile: Path) -> dict[str, str]:
    home = profile / "home"
    roots = {
        "HOME": home,
        "USERPROFILE": home,
        "APPDATA": home / "AppData/Roaming",
        "LOCALAPPDATA": home / "AppData/Local",
        "XDG_CACHE_HOME": profile / "cache",
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local/share",
        "XDG_STATE_HOME": home / ".local/state",
        "COPILOT_CACHE_HOME": profile / "cache",
    }
    for path in roots.values():
        path.mkdir(parents=True, exist_ok=True)
    return {key: str(path) for key, path in roots.items()}


def runtime_env(workspace: Path, harness: str) -> dict[str, str]:
    """Build an allowlisted environment rooted at an isolated CLI profile."""
    allow = {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
    }
    authentication = {
        "claude": {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"},
        "copilot": {"COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"},
    }
    allow.update(authentication[harness])
    env = {key: value for key, value in os.environ.items() if key in allow}
    runtime = workspace / ".runtime"
    runtime.mkdir(exist_ok=True)
    env.update({"PYTHONUTF8": "1", "TEMP": str(runtime), "TMP": str(runtime)})
    profile = workspace / ".parity-profile" / harness
    profile.mkdir(parents=True, exist_ok=True)
    env.update(_profile_roots(profile))
    if harness == "claude":
        env["CLAUDE_CONFIG_DIR"] = str(profile)
    else:
        session_state = profile / "session-state"
        session_state.mkdir(exist_ok=True)
        env["COPILOT_HOME"] = str(profile)
        env["COPILOT_SESSION_STATE_DIR"] = str(session_state)
    return env


def probe_version(
    executable: str,
    harness: str,
    workspace: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    timeout: float,
) -> str:
    """Read one CLI version through the same isolated profile as its fixtures."""
    workspace.mkdir(parents=True, exist_ok=True)
    argv = [executable, "--version"]
    if harness == "copilot":
        argv.insert(1, "--no-auto-update")
    run = runner(
        argv,
        env=runtime_env(workspace, harness),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if run.returncode != 0:
        raise RuntimeError(f"{executable} --version failed")
    version = (run.stdout or run.stderr).strip()
    if not version:
        raise RuntimeError(f"{executable} --version returned no version")
    return version
