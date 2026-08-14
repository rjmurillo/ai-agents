"""Fixture loading and deterministic scoring for real-CLI parity evals."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
SUPPORTED_TOOLS = frozenset({"question", "write"})
SENTINEL = "PARITY_PROFILE_SENTINEL_4853"
GIT_CONTEXT_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
)


class ParityConfigError(ValueError):
    """The fixture corpus or CLI arguments are invalid."""


@dataclass(frozen=True, slots=True)
class AssertionSpec:
    kind: str
    pattern: str = ""
    path: str = ""
    value: str = ""


@dataclass(frozen=True, slots=True)
class Control:
    response: str
    files: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class Fixture:
    fixture_id: str
    claude_agent: Path
    copilot_agent: Path
    prompt: str
    setup_files: Mapping[str, str]
    tools: tuple[str, ...]
    assertions: tuple[AssertionSpec, ...]
    positive: Control
    negative: Control


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ParityConfigError(f"{field} must be an object")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ParityConfigError(f"{field} must be a non-empty string")
    return value


def _repo_file(value: object, field: str) -> Path:
    raw = _string(value, field)
    candidate = (REPO_ROOT / raw).resolve()
    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ParityConfigError(f"{field} escapes the repository root") from exc
    if not candidate.is_file():
        raise ParityConfigError(f"{field} does not exist: {raw}")
    return candidate


def _relative_path(value: object, field: str) -> str:
    raw = _string(value, field)
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ParityConfigError(f"{field} must stay inside the fixture workspace")
    return path.as_posix()


def _load_assertion(value: object, field: str) -> AssertionSpec:
    raw = _mapping(value, field)
    kind = _string(raw.get("kind"), f"{field}.kind")
    if kind in {"regex", "not_regex"}:
        pattern = _string(raw.get("pattern"), f"{field}.pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ParityConfigError(f"{field}.pattern is invalid: {exc}") from exc
        return AssertionSpec(kind=kind, pattern=pattern)
    if kind == "file_equals":
        return AssertionSpec(
            kind=kind,
            path=_relative_path(raw.get("path"), f"{field}.path"),
            value=_string(raw.get("value"), f"{field}.value"),
        )
    if kind == "file_absent":
        return AssertionSpec(
            kind=kind,
            path=_relative_path(raw.get("path"), f"{field}.path"),
        )
    raise ParityConfigError(f"{field}.kind is unsupported: {kind}")


def _load_control(value: object, field: str) -> Control:
    raw = _mapping(value, field)
    response = raw.get("response")
    if not isinstance(response, str):
        raise ParityConfigError(f"{field}.response must be a string")
    return Control(
        response=response,
        files=_load_files(raw.get("files", {}), f"{field}.files"),
    )


def _load_files(value: object, field: str) -> dict[str, str]:
    files_raw = _mapping(value, field)
    files: dict[str, str] = {}
    for path, content in files_raw.items():
        safe_path = _relative_path(path, f"{field} key")
        if not isinstance(content, str):
            raise ParityConfigError(f"{field}[{path!r}] must be a string")
        files[safe_path] = content
    return files


def load_fixtures(path: Path) -> list[Fixture]:
    """Load and validate a runtime parity fixture corpus."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParityConfigError(f"could not read fixtures: {exc}") from exc
    root = _mapping(payload, "fixture document")
    if root.get("schema_version") != SCHEMA_VERSION:
        raise ParityConfigError(f"schema_version must be {SCHEMA_VERSION}")
    raw_fixtures = root.get("fixtures")
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise ParityConfigError("fixtures must be a non-empty array")
    fixtures: list[Fixture] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_fixtures):
        fixture = _load_fixture(value, index)
        if fixture.fixture_id in seen:
            raise ParityConfigError(f"duplicate fixture id: {fixture.fixture_id}")
        seen.add(fixture.fixture_id)
        _validate_controls(fixture)
        fixtures.append(fixture)
    return fixtures


def _load_fixture(value: object, index: int) -> Fixture:
    field = f"fixtures[{index}]"
    raw = _mapping(value, field)
    agents = _mapping(raw.get("agents"), f"{field}.agents")
    tools_raw = raw.get("tools", [])
    if not isinstance(tools_raw, list) or not all(
        isinstance(tool, str) and tool for tool in tools_raw
    ):
        raise ParityConfigError(f"{field}.tools must be an array of strings")
    unsupported_tools = sorted(set(tools_raw) - SUPPORTED_TOOLS)
    if unsupported_tools:
        raise ParityConfigError(
            f"{field}.tools contains unsupported values: {unsupported_tools}"
        )
    assertions_raw = raw.get("assertions")
    if not isinstance(assertions_raw, list) or not assertions_raw:
        raise ParityConfigError(f"{field}.assertions must be a non-empty array")
    controls = _mapping(raw.get("controls"), f"{field}.controls")
    return Fixture(
        fixture_id=_relative_path(raw.get("id"), f"{field}.id"),
        claude_agent=_repo_file(agents.get("claude"), f"{field}.agents.claude"),
        copilot_agent=_repo_file(
            agents.get("copilot"), f"{field}.agents.copilot"
        ),
        prompt=_string(raw.get("prompt"), f"{field}.prompt"),
        setup_files=_load_files(
            raw.get("setup_files", {}), f"{field}.setup_files"
        ),
        tools=tuple(tools_raw),
        assertions=tuple(
            _load_assertion(item, f"{field}.assertions[{assertion_index}]")
            for assertion_index, item in enumerate(assertions_raw)
        ),
        positive=_load_control(
            controls.get("positive"), f"{field}.controls.positive"
        ),
        negative=_load_control(
            controls.get("negative"), f"{field}.controls.negative"
        ),
    )


def score_assertions(
    fixture: Fixture,
    response: str,
    files: Mapping[str, str],
) -> list[dict[str, object]]:
    """Score deterministic response and file assertions."""
    results: list[dict[str, object]] = []
    for spec in fixture.assertions:
        passed = False
        expected = spec.pattern or spec.value or "absent"
        if spec.kind == "regex":
            passed = re.search(spec.pattern, response) is not None
        elif spec.kind == "not_regex":
            passed = re.search(spec.pattern, response) is None
        elif spec.kind == "file_equals":
            passed = files.get(spec.path) == spec.value
        elif spec.kind == "file_absent":
            passed = spec.path not in files
        results.append(
            {
                "kind": spec.kind,
                "path": spec.path or None,
                "expected": expected,
                "passed": passed,
            }
        )
    return results


def _validate_controls(fixture: Fixture) -> None:
    positive = score_assertions(
        fixture, fixture.positive.response, fixture.positive.files
    )
    negative = score_assertions(
        fixture, fixture.negative.response, fixture.negative.files
    )
    if not all(result["passed"] for result in positive):
        raise ParityConfigError(
            f"fixture {fixture.fixture_id!r} positive control does not pass"
        )
    if all(result["passed"] for result in negative):
        raise ParityConfigError(
            f"fixture {fixture.fixture_id!r} negative control does not fail"
        )


def hash_file(path: Path) -> str:
    """Return a SHA-256 digest for an installed prompt surface."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_workspace_file(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ParityConfigError(f"assertion path escapes workspace: {relative}") from exc
    return candidate


def live_files(fixture: Fixture, workspace: Path) -> dict[str, str]:
    """Read only files named by assertions from one isolated workspace."""
    files: dict[str, str] = {}
    for spec in fixture.assertions:
        if not spec.path:
            continue
        path = _safe_workspace_file(workspace, spec.path)
        if path.is_file():
            files[spec.path] = path.read_text(encoding="utf-8", errors="replace")
    return files


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


def prepare_workspace(fixture: Fixture, harness: str, workspace: Path) -> None:
    """Create one isolated git repository and install its agent artifact."""
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
        path = _safe_workspace_file(workspace, relative)
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
    the workspace. Both harnesses get the same treatment.
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


def verify_worktree_identity() -> None:
    """Require cwd and this evaluator to belong to the same worktree."""
    try:
        run = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ParityConfigError(
            f"could not resolve current worktree: {exc}"
        ) from exc
    if run.returncode != 0:
        raise ParityConfigError("current directory is not inside a git worktree")
    current_directory = Path.cwd().resolve()
    top_level = Path(run.stdout.strip()).resolve()
    if not current_directory.is_relative_to(top_level):
        raise ParityConfigError("current directory is outside reported worktree")
    if top_level != REPO_ROOT:
        raise ParityConfigError(
            "current worktree does not contain this evaluator"
        )
