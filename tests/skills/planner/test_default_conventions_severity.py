"""default-conventions.md uses the dispositions code-reviewer reports.

Executor step 4 sends code-reviewer to resources/default-conventions.md and
expects findings marked blocking, non-blocking, or polish. The review skill's
technical-review contract defines that set. This test reads the set from the
contract, so a change there flags any convention label it no longer covers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "src" / "claude" / "skills" / "review" / "resources" / "technical-review.md"
EXECUTOR = REPO_ROOT / "src" / "claude" / "skills" / "planner" / "scripts" / "executor.py"
CONVENTIONS_REL = Path("skills") / "planner" / "resources" / "default-conventions.md"
# Every copy, found by glob so a new mirror cannot go unchecked. The
# .claude/skills/planner link points into src/claude (ADR-119), so dedupe on
# the resolved path to test each real file once.
_CANDIDATES = (
    *REPO_ROOT.glob(f"src/*/{CONVENTIONS_REL.as_posix()}"),
    REPO_ROOT / ".claude" / CONVENTIONS_REL,
)
CONVENTIONS_FILES = tuple(sorted({path.resolve(): path for path in reversed(_CANDIDATES)}.values()))
PARENTHETICAL = re.compile(r"\([^)]*\)")
DISPOSITION_LINE = re.compile(r"^- \*\*disposition\*\*: (?P<values>.+)\.$", re.MULTILINE)
SEVERITY_LINE = re.compile(r"^Severity: (?P<value>.+)$", re.MULTILINE)
SEVERITY_TABLE = re.compile(
    r"^## Severity Levels\n(?:(?!\||#).*\n)*(?P<table>(?:\|.*\n)+)", re.MULTILINE
)


def contract_dispositions() -> frozenset[str]:
    match = DISPOSITION_LINE.search(CONTRACT.read_text(encoding="utf-8"))
    assert match, f"{CONTRACT} has no '- **disposition**:' line"
    return frozenset(re.findall(r"`([^`]+)`", match.group("values")))


def severity_values(text: str) -> list[str]:
    """Each label named on a `Severity:` line, minus its parenthetical note."""
    labels: list[str] = []
    for match in SEVERITY_LINE.finditer(text):
        value = PARENTHETICAL.sub("", match.group("value"))
        labels.extend(part.strip() for part in value.split(","))
    return labels


def table_levels(text: str) -> list[str]:
    match = SEVERITY_TABLE.search(text)
    assert match, "default-conventions.md has no '## Severity Levels' table"
    rows = match.group("table").strip().splitlines()[2:]
    return [row.split("|")[1].strip().strip("`") for row in rows]


def test_contract_defines_three_dispositions() -> None:
    assert contract_dispositions() == {"blocking", "non-blocking", "polish"}


def test_executor_step_4_expects_the_contract_dispositions() -> None:
    text = EXECUTOR.read_text(encoding="utf-8")
    assert "resources/default-conventions.md" in text
    assert "findings marked blocking, non-blocking, or polish" in text


def test_every_planner_tree_has_a_conventions_copy() -> None:
    assert len(CONVENTIONS_FILES) >= 2, CONVENTIONS_FILES
    for path in CONVENTIONS_FILES:
        assert path.is_file(), path


@pytest.mark.parametrize(
    "path", CONVENTIONS_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_severity_table_uses_contract_dispositions(path: Path) -> None:
    levels = table_levels(path.read_text(encoding="utf-8"))
    assert levels, path
    assert set(levels) <= contract_dispositions(), levels


@pytest.mark.parametrize(
    "path", CONVENTIONS_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_every_convention_severity_uses_contract_dispositions(path: Path) -> None:
    labels = severity_values(path.read_text(encoding="utf-8"))
    assert len(labels) >= 10, labels
    unknown = sorted(set(labels) - contract_dispositions())
    assert not unknown, f"{path}: labels outside the contract: {unknown}"


@pytest.mark.parametrize(
    "path", CONVENTIONS_FILES, ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_no_retired_label_remains(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "SHOULD_FIX" not in text
    assert "SUGGESTION" not in text


def test_severity_parser_strips_notes_and_splits_pairs() -> None:
    text = "Severity: non-blocking (violations), polish (missed opportunities)\n"
    assert severity_values(text) == ["non-blocking", "polish"]


def test_severity_parser_ignores_commas_inside_notes() -> None:
    text = "Severity: polish (for X, Y)\n"
    assert severity_values(text) == ["polish"]


def test_severity_parser_rejects_unknown_label() -> None:
    labels = severity_values("Severity: SHOULD_FIX\n")
    assert set(labels) - contract_dispositions() == {"SHOULD_FIX"}
