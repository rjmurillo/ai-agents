"""Fixture loading and deterministic scoring for real-CLI parity evals."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import _runtime_workspace as workspace
from _runtime_parity_types import ParityConfigError
from _runtime_workspace import safe_workspace_file

GIT_CONTEXT_VARIABLES = workspace.GIT_CONTEXT_VARIABLES
SENTINEL = workspace.SENTINEL
_install_agent = workspace._install_agent
hash_installed_agent = workspace.hash_installed_agent
prepare_workspace = workspace.prepare_workspace
probe_version = workspace.probe_version
runtime_env = workspace.runtime_env

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = 1
SUPPORTED_TOOLS = frozenset({"question", "write"})
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
    claude_instruction: Path | None = None
    copilot_instruction: Path | None = None


SemanticTailGrader = Callable[[str], Mapping[str, str]]


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
    if kind == "semantic_response_tail":
        expected = _string(raw.get("value"), f"{field}.value")
        if expected not in {"terminal", "reopened"}:
            raise ParityConfigError(
                f"{field}.value must be 'terminal' or 'reopened'"
            )
        return AssertionSpec(kind=kind, value=expected)
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
    instructions_value = raw.get("instructions")
    instructions = (
        {}
        if instructions_value is None
        else _mapping(instructions_value, f"{field}.instructions")
    )
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
        claude_instruction=(
            _repo_file(
                instructions.get("claude"),
                f"{field}.instructions.claude",
            )
            if "claude" in instructions
            else None
        ),
        copilot_instruction=(
            _repo_file(
                instructions.get("copilot"),
                f"{field}.instructions.copilot",
            )
            if "copilot" in instructions
            else None
        ),
    )


def score_assertions(
    fixture: Fixture,
    response: str,
    files: Mapping[str, str],
    semantic_tail_grader: SemanticTailGrader | None = None,
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
        elif spec.kind == "semantic_response_tail":
            grade = (
                semantic_tail_grader(response)
                if semantic_tail_grader is not None
                else _obvious_response_tail_grade(response)
            )
            actual = grade["verdict"]
            passed = actual == spec.value
            results.append(
                {
                    "kind": spec.kind,
                    "path": None,
                    "expected": spec.value,
                    "actual": actual,
                    "reason": grade.get("reason", ""),
                    "grader_provider": grade.get("grader_provider"),
                    "grader_model": grade.get("grader_model"),
                    "passed": passed,
                }
            )
            continue
        results.append(
            {
                "kind": spec.kind,
                "path": spec.path or None,
                "expected": expected,
                "passed": passed,
            }
        )
    return results


def _obvious_response_tail_grade(response: str) -> dict[str, str]:
    """Classify deliberately explicit controls without making a model call."""
    tail = response.strip().lower()
    reopening = re.search(
        r"(?:\bwould you like me to\b|\bwant me to\b|\bshall i\b|"
        r"\bshould i\b|\bwhat should i do next\b|\banything else\b|\?\s*$)",
        tail,
    )
    return {
        "verdict": "reopened" if reopening else "terminal",
        "reason": "deterministic fixture-control classification",
    }


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


def live_files(fixture: Fixture, workspace: Path) -> dict[str, str]:
    """Read only files named by assertions from one isolated workspace."""
    files: dict[str, str] = {}
    for spec in fixture.assertions:
        if not spec.path:
            continue
        path = safe_workspace_file(workspace, spec.path)
        if path.is_file():
            files[spec.path] = path.read_text(encoding="utf-8", errors="replace")
    return files


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
