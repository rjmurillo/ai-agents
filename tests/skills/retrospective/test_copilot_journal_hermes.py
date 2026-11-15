"""The committed Hermes copy of the retrospective skill, run as Hermes would (issue #7357).

Hermes ships no skill-doctor, so ``copilot_journal.py`` is excluded from that
pack (``excludedFiles`` in ``templates/platforms/hermes.yaml``). These tests
execute the committed pack copy of ``extract_evidence.py`` in a subprocess from a
directory outside the pack, and use the canonical copy as the negative control:
the same journal yields receipts there, so the Hermes result comes from the
missing file and not from a bad journal.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_HERMES_SKILL = _ROOT / "src/hermes/project-toolkit-knowledge/skills/retrospective"
_CANONICAL_SKILL = _ROOT / "src/claude/skills/retrospective"
_HERMES_PACK = _ROOT / "src/hermes/project-toolkit-knowledge"


def _run(skill: Path, cwd: Path, repo: Path, journal: Path) -> tuple[int, dict]:
    script = skill / "scripts" / "extract_evidence.py"
    done = subprocess.run(
        [
            sys.executable,
            "-I",
            str(script),
            "--project-dir",
            str(repo),
            "--journal",
            str(journal),
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return done.returncode, json.loads(done.stdout)


@pytest.fixture
def journal(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    rows = [
        {"type": "session.start", "timestamp": "t", "data": {"context": {"cwd": str(repo)}}},
        {
            "type": "tool.execution_start",
            "timestamp": "t",
            "data": {"toolCallId": "c1", "toolName": "bash"},
        },
        {"type": "tool.execution_complete", "timestamp": "t", "data": {"toolCallId": "c1"}},
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return repo, elsewhere, path


def test_hermes_pack_ships_no_journal_reader_and_no_skill_doctor() -> None:
    assert (_HERMES_SKILL / "scripts" / "extract_evidence.py").is_file()
    assert not (_HERMES_SKILL / "scripts" / "copilot_journal.py").exists()
    assert not (_HERMES_PACK / "skills" / "skill-doctor").exists()


def test_hermes_copy_reports_the_journal_unavailable_and_exits_zero(
    journal: tuple[Path, Path, Path],
) -> None:
    repo, elsewhere, path = journal

    code, payload = _run(_HERMES_SKILL, elsewhere, repo, path)

    assert code == 0
    assert payload["journal"]["available"] is False
    assert payload["journal"]["receipts"] == []
    assert payload["journal"]["reason"].startswith("journal reader unavailable: FileNotFoundError")
    assert any("Copilot journal unavailable" in note for note in payload["notes"])


def test_canonical_copy_reads_the_same_journal(journal: tuple[Path, Path, Path]) -> None:
    repo, elsewhere, path = journal

    code, payload = _run(_CANONICAL_SKILL, elsewhere, repo, path)

    assert code == 0
    assert payload["journal"]["available"] is True
    assert [r["call_id"] for r in payload["journal"]["receipts"]] == ["c1"]
