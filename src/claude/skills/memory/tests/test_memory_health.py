#!/usr/bin/env python3
"""Tests for test_memory_health.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ..scripts.test_memory_health import (
    main,
)
from ..scripts.test_memory_health import (
    test_episodes_available as check_episodes,
)
from ..scripts.test_memory_health import (
    test_modules_available as check_modules,
)
from ..scripts.test_memory_health import (
    test_serena_available as check_serena,
)


class TestSerenaAvailable:
    """Tests for Serena availability check."""

    def test_available(self, tmp_path: Path) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()
        (serena / "test.md").write_text("content")

        result = check_serena(serena)
        assert result["available"] is True
        assert result["count"] == 1

    def test_missing_directory(self, tmp_path: Path) -> None:
        result = check_serena(tmp_path / "missing")
        assert result["available"] is False
        assert result["count"] == 0

    def test_empty_directory(self, tmp_path: Path) -> None:
        serena = tmp_path / "memories"
        serena.mkdir()

        result = check_serena(serena)
        assert result["available"] is True
        assert result["count"] == 0


class TestEpisodesAvailable:
    """Tests for episodic memory availability."""

    def test_available_with_episodes(self, tmp_path: Path) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()
        (ep_dir / "episode-test.json").write_text("{}")

        result = check_episodes(ep_dir)
        assert result["available"] is True
        assert result["count"] == 1

    def test_missing_directory(self, tmp_path: Path) -> None:
        result = check_episodes(tmp_path / "missing")
        assert result["available"] is False

    def test_empty_directory(self, tmp_path: Path) -> None:
        ep_dir = tmp_path / "episodes"
        ep_dir.mkdir()

        result = check_episodes(ep_dir)
        assert result["available"] is True
        assert result["count"] == 0


class TestModulesAvailable:
    """Tests for module availability check."""

    def test_modules_present(self, tmp_path: Path) -> None:
        core = tmp_path / "memory_core"
        core.mkdir()
        (core / "memory_router.py").write_text("# module")
        (core / "reflexion_memory.py").write_text("# module")

        results = check_modules(tmp_path)
        assert len(results) == 2
        assert all(m["available"] for m in results)

    def test_modules_missing(self, tmp_path: Path) -> None:
        results = check_modules(tmp_path)
        assert len(results) == 2
        assert not any(m["available"] for m in results)


class TestMainFunction:
    """Tests for the main CLI entry point."""

    def test_json_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        base = tmp_path / "project"
        base.mkdir()
        (base / ".serena" / "memories").mkdir(parents=True)
        (base / ".agents" / "memory" / "episodes").mkdir(parents=True)

        with patch("socket.create_connection", side_effect=OSError("refused")):
            result = main(["--base-path", str(base)])

        assert result == 0
        captured = capsys.readouterr()
        health = json.loads(captured.out)
        assert "tiers" in health
        assert "overall" in health

    def test_table_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        base = tmp_path / "project"
        base.mkdir()
        (base / ".serena" / "memories").mkdir(parents=True)
        (base / ".agents" / "memory" / "episodes").mkdir(parents=True)

        with patch("socket.create_connection", side_effect=OSError("refused")):
            result = main(["--format", "table", "--base-path", str(base)])

        assert result == 0
        captured = capsys.readouterr()
        assert "Memory System Health Check" in captured.out

    def test_degraded_when_modules_missing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        base = tmp_path / "project"
        base.mkdir()
        (base / ".serena" / "memories").mkdir(parents=True)
        (base / ".agents" / "memory" / "episodes").mkdir(parents=True)
        # Create .claude/skills/memory/ but NOT memory_core/
        (base / ".claude" / "skills" / "memory").mkdir(parents=True)

        with patch("socket.create_connection", side_effect=OSError("refused")):
            result = main(["--base-path", str(base)])

        assert result == 0
        captured = capsys.readouterr()
        health = json.loads(captured.out)
        assert health["overall"] in ("degraded", "unhealthy")

    def test_healthy_with_all_components(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        base = tmp_path / "project"
        base.mkdir()
        serena = base / ".serena" / "memories"
        serena.mkdir(parents=True)
        (serena / "test.md").write_text("content")
        (base / ".agents" / "memory" / "episodes").mkdir(parents=True)

        # Create memory_core modules
        mem_root = base / ".claude" / "skills" / "memory"
        core = mem_root / "memory_core"
        core.mkdir(parents=True)
        (core / "memory_router.py").write_text("# module")
        (core / "reflexion_memory.py").write_text("# module")

        with patch("socket.create_connection", side_effect=OSError("refused")):
            result = main(["--base-path", str(base)])

        assert result == 0
        captured = capsys.readouterr()
        health = json.loads(captured.out)
        assert health["overall"] in ("healthy", "degraded")

    def test_recommendations_generated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture,
    ) -> None:
        base = tmp_path / "project"
        base.mkdir()
        (base / ".serena" / "memories").mkdir(parents=True)
        (base / ".agents" / "memory" / "episodes").mkdir(parents=True)

        with patch("socket.create_connection", side_effect=OSError("refused")):
            result = main(["--base-path", str(base)])

        assert result == 0
        captured = capsys.readouterr()
        health = json.loads(captured.out)
        assert len(health["recommendations"]) >= 1
