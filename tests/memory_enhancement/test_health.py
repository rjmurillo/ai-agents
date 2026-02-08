"""Tests for the memory health reporting module."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from memory_enhancement.health import (
    HealthReport,
    HealthStatus,
    MemoryHealthEntry,
    check_all_health,
    check_memory_health,
)
from memory_enhancement.models import Citation, Memory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def healthy_memory(repo_root: Path) -> Memory:
    """A memory whose citations are all valid."""
    return Memory(
        id="healthy-mem",
        subject="Healthy Memory",
        path=repo_root / ".serena" / "memories" / "healthy-mem.md",
        content="content",
        citations=[
            Citation(path="src/example.py", line=2, snippet="def hello"),
        ],
        confidence=0.9,
    )


@pytest.fixture()
def stale_memory(repo_root: Path) -> Memory:
    """A memory with a citation pointing to a nonexistent file."""
    return Memory(
        id="stale-mem",
        subject="Stale Memory",
        path=repo_root / ".serena" / "memories" / "stale-mem.md",
        content="content",
        citations=[
            Citation(path="src/nonexistent.py", line=1, snippet="nope"),
        ],
        confidence=0.7,
    )


@pytest.fixture()
def exempt_memory(repo_root: Path) -> Memory:
    """A memory marked as exempt from health checks."""
    return Memory(
        id="exempt-mem",
        subject="Exempt Memory",
        path=repo_root / ".serena" / "memories" / "exempt-mem.md",
        content="content",
        citations=[
            Citation(path="src/deleted.py", line=1),
        ],
        confidence=0.6,
        exempt=True,
    )


@pytest.fixture()
def no_citation_memory(repo_root: Path) -> Memory:
    """A memory with no citations at all."""
    return Memory(
        id="no-cite-mem",
        subject="No Citations",
        path=repo_root / ".serena" / "memories" / "no-cite-mem.md",
        content="content",
        citations=[],
        confidence=0.5,
    )


@pytest.fixture()
def health_memories_dir(memories_dir: Path, repo_root: Path) -> Path:
    """Write memory files covering all health statuses."""
    # Healthy memory (valid citation)
    (memories_dir / "healthy-mem.md").write_text(
        "---\n"
        "id: healthy-mem\n"
        "subject: Healthy\n"
        "citations:\n"
        "  - path: src/example.py\n"
        "    line: 2\n"
        '    snippet: "def hello"\n'
        "confidence: 0.9\n"
        "---\n"
        "Healthy content.\n",
        encoding="utf-8",
    )

    # Stale memory (file does not exist)
    (memories_dir / "stale-mem.md").write_text(
        "---\n"
        "id: stale-mem\n"
        "subject: Stale\n"
        "citations:\n"
        "  - path: src/nonexistent.py\n"
        "    line: 1\n"
        "    snippet: nope\n"
        "confidence: 0.7\n"
        "---\n"
        "Stale content.\n",
        encoding="utf-8",
    )

    # Exempt memory
    (memories_dir / "exempt-mem.md").write_text(
        "---\n"
        "id: exempt-mem\n"
        "subject: Exempt\n"
        "exempt: true\n"
        "citations:\n"
        "  - path: src/deleted.py\n"
        "    line: 1\n"
        "confidence: 0.6\n"
        "---\n"
        "Exempt content.\n",
        encoding="utf-8",
    )

    # No citations memory
    (memories_dir / "no-cite-mem.md").write_text(
        "---\n"
        "id: no-cite-mem\n"
        "subject: No Citations\n"
        "confidence: 0.5\n"
        "---\n"
        "No citations here.\n",
        encoding="utf-8",
    )

    # Malformed memory (will cause parse error)
    (memories_dir / "bad-mem.md").write_text(
        "---\n"
        "id: bad-mem\n"
        "subject: Bad\n"
        "citations: not-a-list\n"
        "---\n"
        "Bad content.\n",
        encoding="utf-8",
    )

    return memories_dir


# ---------------------------------------------------------------------------
# HealthStatus enum tests
# ---------------------------------------------------------------------------


class TestHealthStatus:
    """Tests for HealthStatus enum values."""

    def test_all_status_values_exist(self) -> None:
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.STALE.value == "stale"
        assert HealthStatus.EXEMPT.value == "exempt"
        assert HealthStatus.ERROR.value == "error"


# ---------------------------------------------------------------------------
# MemoryHealthEntry tests
# ---------------------------------------------------------------------------


class TestMemoryHealthEntry:
    """Tests for MemoryHealthEntry dataclass."""

    def test_default_values(self) -> None:
        entry = MemoryHealthEntry(
            memory_id="test", status=HealthStatus.HEALTHY
        )
        assert entry.citation_count == 0
        assert entry.valid_count == 0
        assert entry.confidence == 0.5
        assert entry.stale_citations == []
        assert entry.error_message is None

    def test_stale_entry_with_details(self) -> None:
        entry = MemoryHealthEntry(
            memory_id="stale",
            status=HealthStatus.STALE,
            citation_count=3,
            valid_count=1,
            confidence=0.33,
            stale_citations=[
                {"path": "src/a.py", "line": 10, "mismatch_reason": "File not found"},
            ],
        )
        assert entry.status == HealthStatus.STALE
        assert len(entry.stale_citations) == 1


# ---------------------------------------------------------------------------
# HealthReport tests
# ---------------------------------------------------------------------------


class TestHealthReport:
    """Tests for HealthReport aggregate properties."""

    def test_empty_report(self) -> None:
        report = HealthReport()
        assert report.total == 0
        assert report.healthy_count == 0
        assert report.stale_count == 0
        assert report.exempt_count == 0
        assert report.error_count == 0
        assert report.has_stale is False

    def test_mixed_report_counts(self) -> None:
        report = HealthReport(entries=[
            MemoryHealthEntry(memory_id="a", status=HealthStatus.HEALTHY),
            MemoryHealthEntry(memory_id="b", status=HealthStatus.HEALTHY),
            MemoryHealthEntry(memory_id="c", status=HealthStatus.STALE),
            MemoryHealthEntry(memory_id="d", status=HealthStatus.EXEMPT),
            MemoryHealthEntry(memory_id="e", status=HealthStatus.ERROR),
        ])
        assert report.total == 5
        assert report.healthy_count == 2
        assert report.stale_count == 1
        assert report.exempt_count == 1
        assert report.error_count == 1
        assert report.has_stale is True

    def test_all_healthy_report(self) -> None:
        report = HealthReport(entries=[
            MemoryHealthEntry(memory_id="a", status=HealthStatus.HEALTHY),
            MemoryHealthEntry(memory_id="b", status=HealthStatus.HEALTHY),
        ])
        assert report.has_stale is False

    def test_to_dict_structure(self) -> None:
        report = HealthReport(entries=[
            MemoryHealthEntry(
                memory_id="test",
                status=HealthStatus.HEALTHY,
                citation_count=2,
                valid_count=2,
                confidence=1.0,
            ),
        ])
        data = report.to_dict()
        assert "checked_at" in data
        assert data["summary"]["total"] == 1
        assert data["summary"]["healthy"] == 1
        assert len(data["entries"]) == 1
        assert data["entries"][0]["memory_id"] == "test"
        assert data["entries"][0]["status"] == "healthy"

    def test_to_dict_is_json_serializable(self) -> None:
        report = HealthReport(entries=[
            MemoryHealthEntry(
                memory_id="a",
                status=HealthStatus.STALE,
                stale_citations=[{"path": "x.py", "line": 1}],
            ),
        ])
        serialized = json.dumps(report.to_dict())
        parsed = json.loads(serialized)
        assert parsed["summary"]["stale"] == 1

    def test_to_markdown_empty(self) -> None:
        report = HealthReport()
        md = report.to_markdown()
        assert "No memories with citations found" in md

    def test_to_markdown_healthy(self) -> None:
        report = HealthReport(entries=[
            MemoryHealthEntry(
                memory_id="good",
                status=HealthStatus.HEALTHY,
                citation_count=3,
                valid_count=3,
                confidence=1.0,
            ),
        ])
        md = report.to_markdown()
        assert "[PASS]" in md
        assert "good" in md
        assert "1/1" in md  # 1/1 memories healthy
        assert "Stale Citations" not in md

    def test_to_markdown_with_stale(self) -> None:
        report = HealthReport(entries=[
            MemoryHealthEntry(
                memory_id="bad",
                status=HealthStatus.STALE,
                citation_count=2,
                valid_count=1,
                confidence=0.5,
                stale_citations=[
                    {"path": "src/gone.py", "line": 42, "mismatch_reason": "File not found"},
                ],
            ),
        ])
        md = report.to_markdown()
        assert "[WARN]" in md
        assert "Stale Citations" in md
        assert "src/gone.py:42" in md
        assert "File not found" in md


# ---------------------------------------------------------------------------
# check_memory_health tests
# ---------------------------------------------------------------------------


class TestCheckMemoryHealth:
    """Tests for the single-memory health check function."""

    def test_healthy_memory(self, healthy_memory: Memory, repo_root: Path) -> None:
        entry = check_memory_health(healthy_memory, repo_root)
        assert entry.status == HealthStatus.HEALTHY
        assert entry.valid_count == 1
        assert entry.citation_count == 1
        assert entry.confidence == 1.0
        assert entry.stale_citations == []

    def test_stale_memory(self, stale_memory: Memory, repo_root: Path) -> None:
        entry = check_memory_health(stale_memory, repo_root)
        assert entry.status == HealthStatus.STALE
        assert entry.valid_count == 0
        assert entry.citation_count == 1
        assert len(entry.stale_citations) == 1

    def test_exempt_memory(self, exempt_memory: Memory, repo_root: Path) -> None:
        entry = check_memory_health(exempt_memory, repo_root)
        assert entry.status == HealthStatus.EXEMPT
        assert entry.confidence == 0.6

    def test_no_citations(self, no_citation_memory: Memory, repo_root: Path) -> None:
        entry = check_memory_health(no_citation_memory, repo_root)
        assert entry.status == HealthStatus.HEALTHY
        assert entry.citation_count == 0
        assert entry.confidence == 0.5


# ---------------------------------------------------------------------------
# check_all_health tests
# ---------------------------------------------------------------------------


class TestCheckAllHealth:
    """Tests for batch health checking."""

    def test_batch_health_check(
        self, health_memories_dir: Path, repo_root: Path
    ) -> None:
        report = check_all_health(health_memories_dir, repo_root)

        # Should have entries for all 5 files
        assert report.total == 5

        status_map = {e.memory_id: e.status for e in report.entries}
        assert status_map["healthy-mem"] == HealthStatus.HEALTHY
        assert status_map["stale-mem"] == HealthStatus.STALE
        assert status_map["exempt-mem"] == HealthStatus.EXEMPT
        assert status_map["no-cite-mem"] == HealthStatus.HEALTHY
        # bad-mem should be ERROR (malformed YAML)
        assert status_map["bad-mem"] == HealthStatus.ERROR

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        report = check_all_health(tmp_path / "nonexistent", tmp_path)
        assert report.total == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "empty_memories"
        empty_dir.mkdir()
        report = check_all_health(empty_dir, tmp_path)
        assert report.total == 0

    def test_all_exempt(self, memories_dir: Path, repo_root: Path) -> None:
        (memories_dir / "ex1.md").write_text(
            "---\nid: ex1\nsubject: Ex1\nexempt: true\n"
            "citations:\n  - path: src/gone.py\n---\nContent.\n",
            encoding="utf-8",
        )
        (memories_dir / "ex2.md").write_text(
            "---\nid: ex2\nsubject: Ex2\nexempt: true\n"
            "citations:\n  - path: src/gone.py\n---\nContent.\n",
            encoding="utf-8",
        )
        report = check_all_health(memories_dir, repo_root)
        assert report.exempt_count == 2
        assert report.has_stale is False

    def test_report_has_stale_true(
        self, health_memories_dir: Path, repo_root: Path
    ) -> None:
        report = check_all_health(health_memories_dir, repo_root)
        assert report.has_stale is True
        assert report.stale_count == 1


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestHealthCLI:
    """Tests for the health CLI subcommand."""

    def test_health_json_output(
        self, health_memories_dir: Path, repo_root: Path
    ) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "memory_enhancement", "health",
                "--json",
                "--dir", str(health_memories_dir),
                "--repo-root", str(repo_root),
            ],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": str(
                    Path(__file__).resolve().parents[2]
                    / ".claude" / "skills" / "memory-enhancement" / "src"
                ),
                "PATH": "/usr/bin:/usr/local/bin",
            },
        )
        data = json.loads(result.stdout)
        assert "summary" in data
        assert "entries" in data
        assert data["summary"]["total"] == 5

    def test_health_markdown_output(
        self, health_memories_dir: Path, repo_root: Path
    ) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "memory_enhancement", "health",
                "--markdown",
                "--dir", str(health_memories_dir),
                "--repo-root", str(repo_root),
            ],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": str(
                    Path(__file__).resolve().parents[2]
                    / ".claude" / "skills" / "memory-enhancement" / "src"
                ),
                "PATH": "/usr/bin:/usr/local/bin",
            },
        )
        assert "Memory Health Report" in result.stdout

    def test_health_summary_output(
        self, health_memories_dir: Path, repo_root: Path
    ) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "memory_enhancement", "health",
                "--summary",
                "--dir", str(health_memories_dir),
                "--repo-root", str(repo_root),
            ],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": str(
                    Path(__file__).resolve().parents[2]
                    / ".claude" / "skills" / "memory-enhancement" / "src"
                ),
                "PATH": "/usr/bin:/usr/local/bin",
            },
        )
        assert "WARN" in result.stdout or "PASS" in result.stdout

    def test_health_exit_code_stale(
        self, health_memories_dir: Path, repo_root: Path
    ) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "memory_enhancement", "health",
                "--json",
                "--dir", str(health_memories_dir),
                "--repo-root", str(repo_root),
            ],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": str(
                    Path(__file__).resolve().parents[2]
                    / ".claude" / "skills" / "memory-enhancement" / "src"
                ),
                "PATH": "/usr/bin:/usr/local/bin",
            },
        )
        # health_memories_dir has a stale memory, so exit code should be 1
        assert result.returncode == 1

    def test_health_exit_code_all_healthy(
        self, memories_dir: Path, repo_root: Path
    ) -> None:
        # Write only a healthy memory
        (memories_dir / "ok.md").write_text(
            "---\n"
            "id: ok\n"
            "subject: OK\n"
            "citations:\n"
            "  - path: src/example.py\n"
            "    line: 2\n"
            '    snippet: "def hello"\n'
            "---\n"
            "OK.\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                sys.executable, "-m", "memory_enhancement", "health",
                "--json",
                "--dir", str(memories_dir),
                "--repo-root", str(repo_root),
            ],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": str(
                    Path(__file__).resolve().parents[2]
                    / ".claude" / "skills" / "memory-enhancement" / "src"
                ),
                "PATH": "/usr/bin:/usr/local/bin",
            },
        )
        assert result.returncode == 0

    def test_health_nonexistent_dir(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [
                sys.executable, "-m", "memory_enhancement", "health",
                "--dir", str(tmp_path / "nonexistent"),
                "--repo-root", str(tmp_path),
            ],
            capture_output=True,
            text=True,
            env={
                "PYTHONPATH": str(
                    Path(__file__).resolve().parents[2]
                    / ".claude" / "skills" / "memory-enhancement" / "src"
                ),
                "PATH": "/usr/bin:/usr/local/bin",
            },
        )
        assert result.returncode == 2


# ---------------------------------------------------------------------------
# Model exemption tests
# ---------------------------------------------------------------------------


class TestExemptionParsing:
    """Tests for Memory.from_file with exempt field."""

    def test_exempt_true_parsed(self, memories_dir: Path) -> None:
        path = memories_dir / "exempt-test.md"
        path.write_text(
            "---\nid: exempt-test\nsubject: Test\nexempt: true\n---\nContent.\n",
            encoding="utf-8",
        )
        memory = Memory.from_file(path)
        assert memory.exempt is True

    def test_exempt_false_by_default(self, memories_dir: Path) -> None:
        path = memories_dir / "default-test.md"
        path.write_text(
            "---\nid: default-test\nsubject: Test\n---\nContent.\n",
            encoding="utf-8",
        )
        memory = Memory.from_file(path)
        assert memory.exempt is False

    def test_exempt_false_explicit(self, memories_dir: Path) -> None:
        path = memories_dir / "explicit-false.md"
        path.write_text(
            "---\nid: explicit-false\nsubject: Test\nexempt: false\n---\nContent.\n",
            encoding="utf-8",
        )
        memory = Memory.from_file(path)
        assert memory.exempt is False
