"""Regression tests for the issue #5420 legacy-write gate."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(VALIDATION) not in sys.path:
    sys.path.insert(0, str(VALIDATION))

import check_agents_write_targets as checker


@pytest.mark.parametrize(
    "text",
    [
        "Save to: `.agents/qa/report.md`\n",
        "Generate the map at `.agents/pr-comments/PR-1/comments.md`.\n",
        "## Output\n\nWrite report to `.agents/retrospective/today.md`.\n",
    ],
)
def test_obvious_text_write_contracts_fail(text: str) -> None:
    assert checker.scan_text(".claude/agents/example.md", text)


@pytest.mark.parametrize(
    "text",
    [
        "Read `.agents/governance/TESTING-RIGOR.md` before testing.\n",
        "See [ADR](.agents/architecture/ADR-073.md).\n",
        "The old instruction said save to `.agents/qa/x.md`. "
        "agents-write-target: historical -- incident evidence\n",
    ],
)
def test_reads_and_reasoned_history_pass(text: str) -> None:
    assert checker.scan_text(".claude/rules/example.md", text) == []


def test_historical_marker_without_reason_does_not_suppress() -> None:
    text = "Save to `.agents/qa/x.md`. agents-write-target: historical\n"
    assert checker.scan_text("docs/example.md", text)


@pytest.mark.parametrize(
    "source",
    [
        "from pathlib import Path\n(Path('.agents') / 'qa').mkdir()\n",
        "from pathlib import Path\n(Path('.agents') / 'qa' / 'x').write_text('x')\n",
        "from pathlib import Path\nopen(Path('.agents') / 'x', 'w')\n",
        "import os\nos.makedirs('.agents/qa')\n",
        "import shutil\nshutil.copy('x', '.agents/qa/x')\n",
    ],
)
def test_obvious_python_writes_fail(source: str) -> None:
    assert checker.scan_python("scripts/example.py", source)


def test_python_read_passes() -> None:
    assert checker.scan_python("scripts/example.py", "open('.agents/governance/x', 'r')\n") == []


def test_findings_are_located_and_sorted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "b.md").write_text("Save to `.agents/b`.\n", encoding="utf-8")
    (tmp_path / "docs" / "a.md").write_text("Save to `.agents/a`.\n", encoding="utf-8")
    monkeypatch.setattr(checker, "_tracked_files", lambda _root: ["docs/b.md", "docs/a.md"])
    findings, examined = checker.check_repository(tmp_path)
    assert examined == 2
    assert [(item.path, item.line) for item in findings] == [("docs/a.md", 1), ("docs/b.md", 1)]


def test_main_returns_two_outside_git_repo(tmp_path: Path) -> None:
    assert checker.main(["--repo-root", str(tmp_path)]) == 2


def test_validator_fails_closed_on_inventory_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail(_root: Path) -> list[str]:
        raise RuntimeError("inventory failed")

    monkeypatch.setattr(checker, "_tracked_files", fail)
    assert checker.validate_agents_write_targets(tmp_path) is False
