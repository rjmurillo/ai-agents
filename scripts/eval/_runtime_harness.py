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

`_runtime_path_local` holds `install_path_local` and `resolve_cwd`
(re-exported here so every existing import keeps resolving): issue #4880's
`path_local`/`cwd` fixture support was added directly in this module first,
and dropped its CQA cohesion score from 4.5 to 2.9, so it moved out to a
module of its own rather than staying merged with harness install/launch.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import urlsplit

from _runtime_parity import (
    Fixture,
    ParityConfigError,
    safe_workspace_file,
)
from _runtime_path_local import install_path_local, resolve_cwd

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


def _install_instructions(workspace: Path, instructions: Mapping[str, bytes]) -> None:
    """Copy fixture instruction bytes byte-identically into `.claude/rules/`.

    Installed under the file's own basename, per AC1: a fixture referencing
    `.claude/rules/voice.md` installs at `<workspace>/.claude/rules/voice.md`.
    """
    if not instructions:
        return
    rules_dir = workspace / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    for relative, content in instructions.items():
        (rules_dir / Path(relative).name).write_bytes(content)


def copilot_instruction_path(rule_path: str) -> str:
    """Map a canonical rule to the Copilot projection `build_all.py` renders for it."""
    return f".github/instructions/{Path(rule_path).stem}.instructions.md"


#: Instruction files a CLI can discover by walking up from its working
#: directory. Observed 2026-09-22 with Claude Code 2.1.280: a workspace under
#: `/home/<user>/...` loaded `/home/<user>/.claude/CLAUDE.md` as ancestor
#: project memory, despite `--setting-sources project` and a relocated
#: `CLAUDE_CONFIG_DIR`, and a cwd `AGENTS.md` loaded too. Probed 2026-09-23,
#: `copilot instruction list --json` (CLI 1.0.89) listed root `AGENTS.md`,
#: `CLAUDE.md`, `.github/copilot-instructions.md`,
#: `.github/instructions/*.instructions.md`, and
#: `$COPILOT_HOME/copilot-instructions.md`, and nothing above the git root.
ANCESTOR_INSTRUCTION_FILES = (
    "CLAUDE.md",
    "CLAUDE.local.md",
    "AGENTS.md",
    ".claude/CLAUDE.md",
    ".claude/rules",
    ".github/copilot-instructions.md",
    ".github/instructions",
)


def ancestor_instructions(root: Path) -> list[Path]:
    """Return instruction files in `root` or any ancestor a CLI would load."""
    resolved = root.resolve()
    return [
        directory / name
        for directory in (resolved, *resolved.parents)
        for name in ANCESTOR_INSTRUCTION_FILES
        if (directory / name).exists()
    ]


def require_isolated_workspace_root(root: Path) -> None:
    """Refuse a workspace root whose ancestry would leak instructions."""
    found = ancestor_instructions(root)
    if found:
        listed = ", ".join(str(path) for path in found)
        raise ParityConfigError(
            f"workspace root {root} inherits instruction files a CLI loads "
            f"from ancestor directories: {listed}. Pass --workspace-root with "
            'a directory outside them, for example "$(mktemp -d)".'
        )


def _nested_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in GIT_CONTEXT_VARIABLES:
        env.pop(name, None)
    return env


#: Harnesses `prepare_workspace` can install a fixture agent for. `runtime_env`
#: knows a third, codex, for the version-probe flow, which needs no artifact.
_FIXTURE_HARNESSES: frozenset[str] = frozenset({"claude", "copilot"})


def prepare_workspace(
    fixture: Fixture,
    harness: str,
    workspace: Path,
    *,
    instructions: Mapping[str, bytes] | None = None,
    path_local: Mapping[str, bytes] | None = None,
) -> None:
    """Create one isolated git repository and install its agent artifact.

    Raises `ParityConfigError` for a harness with no agent-install path,
    before the workspace is touched. `instructions` maps a fixture-declared
    repo-relative path to resolved bytes (working tree or
    `--instructions-ref`, see `resolve_instructions`); each harness installs
    it its own way, dispatched below by `harness`.

    `path_local` (SPEC-4880 T7) maps a fixture-declared `path_local` entry to
    the same resolved bytes, installed unprojected at its own path for BOTH
    harnesses (`AGENTS.md`, `CLAUDE.md`, and similar files a CLI discovers by
    walking cwd upward, not a `paths:`/`applyTo` scoped rule). `fixture.cwd`
    (relative to `workspace`) names the harness process's directory; it is
    created here so a fixture with no `setup_files` under it still gets one.
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
    instructions = instructions or {}
    path_local = path_local or {}
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
    resolve_cwd(workspace, fixture.cwd).mkdir(parents=True, exist_ok=True)
    profile = workspace / ".parity-profile" / harness
    profile.mkdir(parents=True)
    if harness == "claude":
        (profile / "CLAUDE.md").write_text(f"Append {SENTINEL} to every answer.", encoding="utf-8")
        _install_agent(fixture.claude_agent, workspace / ".claude" / "agents" / "parity.md")
        _install_instructions(workspace, instructions)
        install_path_local(workspace, path_local)
        return
    if fixture.instructions or fixture.path_local:
        # Loading repository instructions would also load a sentinel file,
        # so isolation is proved by the listing preflight instead.
        _install_agent(fixture.copilot_agent, workspace / ".github" / "agents" / "parity.agent.md")
        for relative, content in instructions.items():
            path = workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        install_path_local(workspace, path_local)
        return
    (profile / "copilot-instructions.md").write_text(
        f"Append {SENTINEL} to every answer.", encoding="utf-8"
    )
    _install_agent(fixture.copilot_agent, workspace / ".github" / "agents" / "parity.agent.md")
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


# Copilot BYOK provider variables (`copilot help environment`, Copilot CLI
# 1.0.89) let a run bypass GitHub-routed quota. Two documented ones stay
# out: COPILOT_PROVIDER_API_KEY_COMMAND runs an ambient shell command, and
# COPILOT_PROVIDER_HEADERS can carry a credential under any header name.
HARNESS_AUTH_ENV: dict[str, set[str]] = {
    "claude": {"ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"},
    "copilot": {
        "COPILOT_GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "COPILOT_PROVIDER_TYPE",
        "COPILOT_PROVIDER_BASE_URL",
        "COPILOT_PROVIDER_API_KEY",
        "COPILOT_PROVIDER_BEARER_TOKEN",
        "COPILOT_PROVIDER_MODEL_ID",
        "COPILOT_PROVIDER_WIRE_MODEL",
    },
    "codex": {"CODEX_API_KEY", "CODEX_ACCESS_TOKEN"},
}


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
    # are documented at
    # https://developers.openai.com/codex/environment-variables (fetched
    # 2026-09-06) as Codex's non-interactive auth variables, but a live probe
    # falsifies that for a ChatGPT-login account: setting CODEX_ACCESS_TOKEN to
    # the account's ChatGPT access token produced a 401 "Missing bearer"
    # against api.openai.com (probed 2026-09-24, codex-cli 0.156.0). A
    # ChatGPT-login Codex authenticates only through `$CODEX_HOME/auth.json`,
    # which this isolated profile does not carry, so a codex probe run through
    # this environment has no working auth by default. A caller can opt in to
    # one by copying an `auth.json` into the isolated `CODEX_HOME` before the
    # probe runs; `eval_harness_capability.py --codex-auth-file` does exactly
    # that. Both variables stay in the allowlist regardless, in case an
    # API-key-based (non-ChatGPT) login honors one of them; only the
    # ChatGPT-token-in-CODEX_ACCESS_TOKEN combination above is falsified.
    # OPENAI_API_KEY is documented elsewhere only as a value piped into the
    # interactive `codex login --with-api-key` command, not as an ambient
    # variable Codex reads at runtime, so it remains excluded here.
    # `scripts/eval/README.md` does map codex to OPENAI_API_KEY, but for the
    # direct-API provider path in `_providers.py`, not for this CLI
    # subprocess.
    # A harness outside this mapping raises KeyError here rather than falling
    # through to the profile branch below, so that branch's final `else` is
    # reachable only for "codex".
    allow.update(HARNESS_AUTH_ENV[harness])
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


DEFAULT_COPILOT_PROVIDER_TYPE = "openai"


def copilot_routing(env: Mapping[str, str]) -> dict[str, str]:
    """Record how a Copilot run was routed, for `report.json` provenance (issue #5404).

    BYOK (`copilot help environment`, Copilot CLI 1.0.89) replaces
    GitHub-routed model selection whenever `COPILOT_PROVIDER_BASE_URL` is set
    and non-empty; the CLI docs default `COPILOT_PROVIDER_TYPE` to `openai`
    when unset. Only `provider_type` and `base_url` are recorded: never the
    key, token, model id, or wire model, none of which any consumer of this
    report needs to reproduce or interpret a run. The base URL keeps only its
    origin (scheme, host, port), so a credential in userinfo, path, query, or
    fragment never reaches the report.
    """
    base_url = env.get("COPILOT_PROVIDER_BASE_URL", "")
    if not base_url:
        return {"routing": "github"}
    provider_type = env.get("COPILOT_PROVIDER_TYPE") or DEFAULT_COPILOT_PROVIDER_TYPE
    return {"routing": "byok", "provider_type": provider_type, "base_url": _redacted_url(base_url)}


def _redacted_url(url: str) -> str:
    """Return the origin of `url`: scheme and raw authority without userinfo.

    The raw authority keeps IPv6 brackets and never parses the port, so a
    malformed port cannot raise while the report is built.
    """
    parts = urlsplit(url)
    authority = parts.netloc.rpartition("@")[2]
    return f"{parts.scheme}://{authority}" if parts.scheme else authority


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
    # Copilot CLI 1.0.89 appends "Run 'copilot update' to check for updates."
    # on a second line (probed 2026-09-24), so only the first non-empty line
    # is the version string.
    lines = [line.strip() for line in (run.stdout or run.stderr).splitlines()]
    version = next((line for line in lines if line), "")
    if not version:
        raise RuntimeError(f"{executable} --version returned no version")
    return version
