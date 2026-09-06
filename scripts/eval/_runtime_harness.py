"""Harness installation, isolated profiles, and CLI invocation for parity evals.

Split out of `_runtime_parity` after the review of PR #5630. The seam is what
changes together: everything here changes when a harness changes how it is
installed, configured, or launched, and nothing here changes when the fixture
schema or the scoring rules change. `_runtime_parity` keeps those, and the
dependency runs one way, this module onto that one, so the boundary is real
rather than a pair of files importing each other.

The split was forced rather than chosen. Adding a codex guard and its comments
took `_runtime_parity` from 498 lines to 525, past the 500-line file-size
lint, and the gate accepted it only because the taste baseline carried a unit
of unrecorded slack. Trimming the prose would have cleared the number without
touching the design; this addresses what the number was pointing at.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from _runtime_parity import (
    Fixture,
    ParityConfigError,
    safe_workspace_file,
)

SENTINEL = "PARITY_PROFILE_SENTINEL_4853"
GIT_CONTEXT_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
)


AGENT_NAME = "parity"


def _installed_agent_bytes(source: Path) -> bytes:
    """Return the exact agent bytes installed for a parity run.

    Claude Code and Copilot CLI resolve `--agent <name>` against the frontmatter
    `name:` field, not the filename. Copying `orchestrator.md` to `parity.md`
    therefore registers an agent still called `orchestrator`, and the CLI exits
    1 with `--agent 'parity' not found` before the model is ever called.
    """
    with source.open(encoding="utf-8", newline="") as source_file:
        text = source_file.read()
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ParityConfigError(f"{source} has no frontmatter block")
    renamed = False
    for index in range(1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "---":
            break
        if lines[index].startswith("name:"):
            line_ending = lines[index][len(lines[index].rstrip("\r\n")) :]
            lines[index] = f"name: {AGENT_NAME}{line_ending}"
            renamed = True
            break
    if not renamed:
        raise ParityConfigError(f"{source} frontmatter has no name field")
    return "".join(lines).encode("utf-8")


def hash_installed_agent(source: Path) -> str:
    """Return the digest of the transformed bytes loaded by the CLI."""
    return hashlib.sha256(_installed_agent_bytes(source)).hexdigest()


def _install_agent(source: Path, target: Path) -> None:
    """Install an agent under the name used by both CLI invocations."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_installed_agent_bytes(source))


def _nested_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in GIT_CONTEXT_VARIABLES:
        env.pop(name, None)
    return env


#: Harnesses `prepare_workspace` can install a fixture agent for. `runtime_env`
#: knows a third, codex, for the version-probe flow, which needs no artifact.
_FIXTURE_HARNESSES: frozenset[str] = frozenset({"claude", "copilot"})


def prepare_workspace(fixture: Fixture, harness: str, workspace: Path) -> None:
    """Create one isolated git repository and install its agent artifact.

    Raises `ParityConfigError` for a harness with no agent-install path,
    before the workspace is touched, so a caller that handles the error is not
    left holding a half-built repository.
    """
    if harness not in _FIXTURE_HARNESSES:
        # `runtime_env` accepts codex for the version-probe flow, which needs
        # only an isolated profile. Fixture execution needs an agent artifact
        # and an instructions file, and no codex shape for either is verified
        # in this repository. Falling through would write Copilot artifacts
        # into a codex workspace and parse the run with the Copilot parser,
        # reporting a parity result about a harness that never saw the fixture.
        raise ParityConfigError(
            f"no agent-install path is defined for {harness!r}; only "
            f"{', '.join(sorted(_FIXTURE_HARNESSES))} fixtures can be prepared"
        )
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
            f"Append {SENTINEL} to every answer.", encoding="utf-8"
        )
        _install_agent(fixture.claude_agent, workspace / ".claude" / "agents" / "parity.md")
        return
    (profile / "copilot-instructions.md").write_text(
        f"Append {SENTINEL} to every answer.", encoding="utf-8"
    )
    _install_agent(
        fixture.copilot_agent, workspace / ".github" / "agents" / "parity.agent.md"
    )
    (workspace / ".github" / "copilot-instructions.md").write_text(
        f"Append {SENTINEL} to every answer.", encoding="utf-8"
    )


def _profile_roots(profile: Path) -> dict[str, str]:
    """Point every home and cache root at the workspace profile.

    Copilot's bootstrap reads LOCALAPPDATA, XDG_CACHE_HOME, and
    COPILOT_CACHE_HOME before COPILOT_HOME, so leaving the operator's values in
    place lets a run read or write cached packages and profile state outside
    the workspace. All harnesses get the same treatment.
    """
    home = profile / "home"
    roots = {
        "HOME": home,
        "USERPROFILE": home,
        "APPDATA": home / "AppData" / "Roaming",
        "LOCALAPPDATA": home / "AppData" / "Local",
        "XDG_CACHE_HOME": profile / "cache",
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local" / "share",
        "XDG_STATE_HOME": home / ".local" / "state",
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
    # CODEX_API_KEY ("Supplies an API key to non-interactive processes") and
    # CODEX_ACCESS_TOKEN ("Furnishes access tokens for trusted automation")
    # are Codex's own non-interactive auth variables, quoted from
    # https://developers.openai.com/codex/environment-variables, fetched
    # 2026-09-06. OPENAI_API_KEY is documented elsewhere only as a value piped
    # into the interactive `codex login --with-api-key` command, not as an
    # ambient variable Codex reads at runtime, so it is excluded here.
    # `scripts/eval/README.md` does map codex to OPENAI_API_KEY, but for the
    # direct-API provider path in `_providers.py`, not for this CLI
    # subprocess. An operator whose environment follows that row will find the
    # variable stripped here and the probe failing to authenticate, which is
    # the fail-closed direction; a live step-3 run should confirm the real
    # variable before either name is treated as settled.
    authentication = {
        "claude": {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"},
        "copilot": {"COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"},
        "codex": {"CODEX_API_KEY", "CODEX_ACCESS_TOKEN"},
    }
    # A harness outside this mapping raises KeyError here rather than falling
    # through to the profile branch below, so that branch's final `else` is
    # reachable only for "codex".
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
    elif harness == "copilot":
        session_state = profile / "session-state"
        session_state.mkdir(exist_ok=True)
        env["COPILOT_HOME"] = str(profile)
        env["COPILOT_SESSION_STATE_DIR"] = str(session_state)
    else:
        # CODEX_HOME "Sets the root for Codex state, including config, auth,
        # logs, sessions, skills, and standalone package metadata," default
        # ~/.codex (same source as above, fetched 2026-09-06). Pointing it at
        # the workspace profile isolates state the same way CLAUDE_CONFIG_DIR
        # and COPILOT_HOME do.
        env["CODEX_HOME"] = str(profile)
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
    # Codex needs no equivalent flag: third-party references describe
    # `codex --version` as a plain `codex-cli x.y.z` line needing no login
    # (the official flag reference 404s as of 2026-09-06, so this is
    # web-search evidence, not a fetched primary source). It is also already
    # the default for every harness other than copilot.
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
