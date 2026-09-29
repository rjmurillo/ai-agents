"""Routing benchmark scenario contract and strict corpus loader (issue #5425).

Pure parsing and validation. No model calls, no network. One directory under
the corpus root is one scenario:

    <id>/scenario.json   metadata, see `Scenario`
    <id>/initial/        the repository state the driver starts from
    <id>/hidden/         grader-only acceptance files, never shown to a driver
    <id>/known_good/     overlay that solves the scenario (control fixture)
    <id>/known_bad/      overlay that looks plausible and must be graded FAIL

Every file inside a fixture directory carries the `.fixture` suffix. That keeps
repository linters, type checkers, and pytest from treating fixture code as
live source; `_routing_grader.materialize` strips the suffix.

The corpus stays independent of concrete model names so any routing arm can
consume it (#5425 "Scenario contract"). `load_corpus` refuses model names in
every driver-visible field and file.

Fail-closed, like `_outcome_record.py`: unknown keys, missing keys, wrong
types, a missing category, a duplicate id, a path that escapes the fixture
root, or an answer-key leak into `initial/` raises `RoutingCorpusError`.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import TypeVar

from _routing_fixtures import RoutingCorpusError, fixture_files
from _routing_hygiene import check_model_neutral, check_no_answer_leak

_E = TypeVar("_E", bound=Enum)

SCHEMA_VERSION = 1
SCENARIO_FILE = "scenario.json"
FIXTURE_DIRS: tuple[str, ...] = ("initial", "hidden", "known_good", "known_bad")
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 300


class Category(str, Enum):
    """The six behavior classes of issue #5425, in the issue's order."""

    BOUNDED_IMPLEMENTATION = "bounded_implementation"
    MULTI_FILE_INVARIANTS = "multi_file_invariants"
    INVESTIGATE_BEFORE_EDIT = "investigate_before_edit"
    SCOPE_EXPANSION = "scope_expansion"
    PLAUSIBLE_BUT_WRONG = "plausible_but_wrong"
    ARCHITECTURE_RESOLVED = "architecture_resolved"


class DifficultyClass(str, Enum):
    """Difficulty declared before any model runs (#5422 "Fairness contract").

    `ordinary_bounded` is ordinary bounded work. `fallback_reasoning` is
    bounded work that needs materially more independent reasoning,
    exploration, or debugging. Runners record this value and never
    reclassify after seeing results.
    """

    ORDINARY_BOUNDED = "ordinary_bounded"
    FALLBACK_REASONING = "fallback_reasoning"


@dataclass(frozen=True, slots=True)
class Validation:
    commands: tuple[tuple[str, ...], ...]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class ReviewerFinding:
    """Category 5: the defect a reviewer is expected to report, known up front."""

    summary: str
    evidence_marker: str


@dataclass(frozen=True, slots=True)
class Architecture:
    """Category 6: the decision an orchestrator stage resolves before delegation."""

    question: str
    context_path: str
    resolved_decision: str
    driver_contract: str


@dataclass(frozen=True, slots=True)
class Provenance:
    kind: str
    reason: str
    source: str
    reference: str


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    category: Category
    difficulty: DifficultyClass
    title: str
    requirement: str
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    expected_changed_paths: tuple[str, ...]
    invariants: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    validation: Validation
    self_check: Validation | None
    judge_dimensions: tuple[str, ...]
    provenance: Provenance
    reviewer_finding: ReviewerFinding | None
    architecture: Architecture | None
    root: Path

    def fixture_dir(self, name: str) -> Path:
        return self.root / name


_TOP_REQUIRED = frozenset(
    {
        "schema_version",
        "id",
        "category",
        "difficulty",
        "title",
        "requirement",
        "allowed_scope",
        "expected_changed_paths",
        "invariants",
        "acceptance_criteria",
        "validation",
        "grading",
        "reset",
        "provenance",
    }
)
_TOP_OPTIONAL = frozenset({"self_check", "reviewer_finding", "architecture"})


def _obj(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RoutingCorpusError(f"{path}: expected an object, got {type(value).__name__}")
    return value


def _keys(
    data: dict[str, object], required: frozenset[str], optional: frozenset[str], path: str
) -> None:
    missing = required - data.keys()
    if missing:
        raise RoutingCorpusError(f"{path}: missing required key(s) {sorted(missing)}")
    unknown = data.keys() - required - optional
    if unknown:
        raise RoutingCorpusError(f"{path}: unknown key(s) {sorted(unknown)}")


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RoutingCorpusError(f"{path}: expected a non-empty string, got {value!r}")
    return value


def _text_list(value: object, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise RoutingCorpusError(f"{path}: expected a non-empty list of strings")
    return tuple(_text(item, f"{path}[{index}]") for index, item in enumerate(value))


def _safe_glob(value: str, path: str) -> str:
    """Refuse absolute paths and `..` so a glob cannot name files off the tree (CWE-22)."""
    posix = PurePosixPath(value)
    if posix.is_absolute() or "\\" in value or ".." in posix.parts:
        raise RoutingCorpusError(f"{path}: path {value!r} must be relative with no '..'")
    return value


def _glob_list(value: object, path: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    items = _text_list(value, path, allow_empty=allow_empty)
    return tuple(_safe_glob(item, f"{path}[{index}]") for index, item in enumerate(items))


def _command(value: object, path: str) -> tuple[str, ...]:
    argv = _text_list(value, path)
    if argv[0] != "python":
        raise RoutingCorpusError(
            f"{path}: first argv element must be 'python' (the grader substitutes the "
            f"current interpreter), got {argv[0]!r}"
        )
    return argv


def _validation(value: object, path: str) -> Validation:
    data = _obj(value, path)
    _keys(data, frozenset({"commands", "timeout_seconds"}), frozenset(), path)
    raw = data["commands"]
    if not isinstance(raw, list) or not raw:
        raise RoutingCorpusError(f"{path}.commands: expected a non-empty list of argv lists")
    commands = tuple(_command(item, f"{path}.commands[{i}]") for i, item in enumerate(raw))
    timeout = data["timeout_seconds"]
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        raise RoutingCorpusError(f"{path}.timeout_seconds: expected an int, got {timeout!r}")
    if not MIN_TIMEOUT_SECONDS <= timeout <= MAX_TIMEOUT_SECONDS:
        raise RoutingCorpusError(
            f"{path}.timeout_seconds: {timeout} outside "
            f"[{MIN_TIMEOUT_SECONDS}, {MAX_TIMEOUT_SECONDS}]"
        )
    return Validation(commands, timeout)


def _enum(enum: type[_E], value: object, path: str) -> _E:
    try:
        return enum(value)
    except ValueError as exc:
        allowed = sorted(str(item.value) for item in enum)
        raise RoutingCorpusError(f"{path}: {value!r} is not one of {allowed}") from exc


def _provenance(value: object, path: str) -> Provenance:
    data = _obj(value, path)
    kind = _text(data.get("kind"), f"{path}.kind")
    if kind == "synthetic":
        _keys(data, frozenset({"kind", "reason"}), frozenset(), path)
        return Provenance(kind, _text(data["reason"], f"{path}.reason"), "", "")
    if kind == "adapted":
        _keys(data, frozenset({"kind", "source", "reference"}), frozenset(), path)
        source = _safe_glob(_text(data["source"], f"{path}.source"), f"{path}.source")
        return Provenance(kind, "", source, _text(data["reference"], f"{path}.reference"))
    raise RoutingCorpusError(f"{path}.kind: {kind!r} is not 'synthetic' or 'adapted'")


def _grading(value: object, path: str) -> tuple[str, ...]:
    data = _obj(value, path)
    _keys(data, frozenset({"method"}), frozenset({"judge_dimensions"}), path)
    if data["method"] != "deterministic":
        raise RoutingCorpusError(f"{path}.method: only 'deterministic' is supported")
    return _text_list(
        data.get("judge_dimensions", []), f"{path}.judge_dimensions", allow_empty=True
    )


def _reset(value: object, path: str) -> None:
    data = _obj(value, path)
    _keys(data, frozenset({"method", "notes"}), frozenset(), path)
    if data["method"] != "fresh_copy":
        raise RoutingCorpusError(f"{path}.method: only 'fresh_copy' is supported")
    _text(data["notes"], f"{path}.notes")


def _reviewer_finding(value: object, path: str) -> ReviewerFinding:
    data = _obj(value, path)
    _keys(data, frozenset({"summary", "evidence_marker"}), frozenset(), path)
    return ReviewerFinding(
        _text(data["summary"], f"{path}.summary"),
        _text(data["evidence_marker"], f"{path}.evidence_marker"),
    )


def _architecture(value: object, path: str) -> Architecture:
    data = _obj(value, path)
    keys = frozenset({"question", "context_path", "resolved_decision", "driver_contract"})
    _keys(data, keys, frozenset(), path)
    context = _safe_glob(
        _text(data["context_path"], f"{path}.context_path"), f"{path}.context_path"
    )
    return Architecture(
        _text(data["question"], f"{path}.question"),
        context,
        _text(data["resolved_decision"], f"{path}.resolved_decision"),
        _text(data["driver_contract"], f"{path}.driver_contract"),
    )


def _scope(value: object, path: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    data = _obj(value, path)
    _keys(data, frozenset({"paths"}), frozenset({"forbidden"}), path)
    allowed = _glob_list(data["paths"], f"{path}.paths")
    forbidden = _glob_list(data.get("forbidden", []), f"{path}.forbidden", allow_empty=True)
    return allowed, forbidden


def parse_scenario(data: object, root: Path) -> Scenario:
    """Parse one `scenario.json` document. Raises `RoutingCorpusError`."""
    doc = _obj(data, "scenario")
    _keys(doc, _TOP_REQUIRED, _TOP_OPTIONAL, "scenario")
    if doc["schema_version"] != SCHEMA_VERSION:
        raise RoutingCorpusError(f"scenario.schema_version: expected {SCHEMA_VERSION}")
    allowed, forbidden = _scope(doc["allowed_scope"], "allowed_scope")
    _reset(doc["reset"], "reset")
    return Scenario(
        scenario_id=_text(doc["id"], "id"),
        category=_enum(Category, doc["category"], "category"),
        difficulty=_enum(DifficultyClass, doc["difficulty"], "difficulty"),
        title=_text(doc["title"], "title"),
        requirement=_text(doc["requirement"], "requirement"),
        allowed_paths=allowed,
        forbidden_paths=forbidden,
        expected_changed_paths=_glob_list(doc["expected_changed_paths"], "expected_changed_paths"),
        invariants=_text_list(doc["invariants"], "invariants"),
        acceptance_criteria=_text_list(doc["acceptance_criteria"], "acceptance_criteria"),
        validation=_validation(doc["validation"], "validation"),
        self_check=_validation(doc["self_check"], "self_check") if "self_check" in doc else None,
        judge_dimensions=_grading(doc["grading"], "grading"),
        provenance=_provenance(doc["provenance"], "provenance"),
        reviewer_finding=(
            _reviewer_finding(doc["reviewer_finding"], "reviewer_finding")
            if "reviewer_finding" in doc
            else None
        ),
        architecture=(
            _architecture(doc["architecture"], "architecture") if "architecture" in doc else None
        ),
        root=root,
    )


def _check_fixtures(scenario: Scenario) -> None:
    for name in FIXTURE_DIRS:
        if not scenario.fixture_dir(name).is_dir():
            raise RoutingCorpusError(f"{scenario.scenario_id}: missing fixture directory {name}/")
    initial = fixture_files(scenario.fixture_dir("initial"))
    hidden = fixture_files(scenario.fixture_dir("hidden"))
    if not initial or not hidden:
        raise RoutingCorpusError(f"{scenario.scenario_id}: initial/ and hidden/ must hold files")
    for name in ("known_good", "known_bad"):
        if not fixture_files(scenario.fixture_dir(name)):
            raise RoutingCorpusError(f"{scenario.scenario_id}: {name}/ must hold files")
    overlap = sorted(initial.keys() & hidden.keys())
    if overlap:
        raise RoutingCorpusError(
            f"{scenario.scenario_id}: hidden/ shadows initial/ file(s) {overlap}"
        )


def _check_category_fields(scenario: Scenario) -> None:
    sid = scenario.scenario_id
    is_plausible = scenario.category is Category.PLAUSIBLE_BUT_WRONG
    is_architecture = scenario.category is Category.ARCHITECTURE_RESOLVED
    if is_plausible != (scenario.reviewer_finding is not None):
        raise RoutingCorpusError(
            f"{sid}: reviewer_finding is required for, and only for, plausible_but_wrong"
        )
    if is_plausible != (scenario.self_check is not None):
        raise RoutingCorpusError(
            f"{sid}: self_check is required for, and only for, plausible_but_wrong"
        )
    if is_architecture != (scenario.architecture is not None):
        raise RoutingCorpusError(
            f"{sid}: architecture is required for, and only for, architecture_resolved"
        )
    if scenario.category is Category.SCOPE_EXPANSION and not scenario.forbidden_paths:
        raise RoutingCorpusError(f"{sid}: scope_expansion needs at least one forbidden path")
    architecture = scenario.architecture
    if architecture is not None:
        initial = fixture_files(scenario.fixture_dir("initial"))
        if architecture.context_path not in initial:
            raise RoutingCorpusError(
                f"{sid}: architecture.context_path {architecture.context_path!r} not in initial/"
            )
        if architecture.driver_contract.strip() == scenario.requirement.strip():
            raise RoutingCorpusError(f"{sid}: driver_contract must differ from the requirement")


def load_scenario(directory: Path) -> Scenario:
    """Load and validate one scenario directory."""
    document = directory / SCENARIO_FILE
    try:
        raw = json.loads(document.read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        raise RoutingCorpusError(f"{document}: cannot read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RoutingCorpusError(f"{document}: invalid JSON: {exc}") from exc
    scenario = parse_scenario(raw, directory)
    _check_fixtures(scenario)
    _check_category_fields(scenario)
    check_model_neutral(scenario)
    check_no_answer_leak(scenario)
    return scenario


def load_corpus(root: Path) -> list[Scenario]:
    """Load every scenario under `root`, then check corpus-level rules.

    Each directory name must equal its scenario id. The corpus must hold no
    duplicate id, every category in `Category`, and exactly one scenario per
    category (#5425: one primary scenario per category keeps the paid matrix
    bounded).
    """
    if not root.is_dir():
        raise RoutingCorpusError(f"{root}: corpus root is not a directory")
    directories = sorted(path for path in root.iterdir() if path.is_dir())
    scenarios = [load_scenario(directory) for directory in directories]
    seen: set[str] = set()
    for scenario in scenarios:
        if scenario.scenario_id in seen:
            raise RoutingCorpusError(f"duplicate scenario id {scenario.scenario_id!r}")
        seen.add(scenario.scenario_id)
        if scenario.root.name != scenario.scenario_id:
            raise RoutingCorpusError(
                f"{scenario.root}: directory name must equal scenario id {scenario.scenario_id!r}"
            )
    counts = Counter(scenario.category for scenario in scenarios)
    missing = {item for item in Category} - counts.keys()
    if missing:
        raise RoutingCorpusError(f"missing required categories {sorted(c.value for c in missing)}")
    crowded = sorted(category.value for category, count in counts.items() if count > 1)
    if crowded:
        raise RoutingCorpusError(
            f"one primary scenario per category keeps the paid matrix bounded, "
            f"got more in {crowded}"
        )
    return scenarios
