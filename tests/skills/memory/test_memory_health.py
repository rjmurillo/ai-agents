"""Tests for test_memory_health.py."""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import test_memory_health


class TestSerenaAvailable:
    """Tests for test_serena_available function."""

    def test_available_with_files(self, tmp_path):
        # Source expects the serena_path directly (the memories directory)
        memories = tmp_path / "memories"
        memories.mkdir(parents=True)
        (memories / "test.md").write_text("# Test")

        result = test_memory_health.test_serena_available(memories)
        assert result["available"] is True
        assert result["count"] == 1

    def test_unavailable_when_missing(self, tmp_path):
        result = test_memory_health.test_serena_available(tmp_path / "nonexistent")
        assert result["available"] is False
        assert result["count"] == 0


class TestRetiredBackendProbe:
    """Negative control: the second store's probe is gone with the store."""

    def test_probe_function_is_absent(self):
        """The health check must not report a store that does not exist.

        Named explicitly rather than deleted so a reintroduced probe fails
        here instead of silently re-adding a tier the report cannot back.
        """
        probes = [
            name
            for name in dir(test_memory_health)
            if name.startswith("test_") and name.endswith("_available")
        ]
        assert sorted(probes) == [
            "test_episodes_available",
            "test_modules_available",
            "test_serena_available",
        ]


class TestEpisodesAvailable:
    """Tests for test_episodes_available function."""

    def test_available_with_episodes(self, tmp_path):
        # Source expects the episodes directory path directly
        episodes = tmp_path / "episodes"
        episodes.mkdir(parents=True)
        (episodes / "episode-2026-01-01-session-1.json").write_text("{}")

        result = test_memory_health.test_episodes_available(episodes)
        assert result["available"] is True
        assert result["count"] == 1

    def test_unavailable_when_missing(self, tmp_path):
        result = test_memory_health.test_episodes_available(tmp_path / "nonexistent")
        assert result["available"] is False


class TestModulesAvailable:
    """Tests for test_modules_available function."""

    def test_checks_module_files(self, tmp_path):
        # Source checks for memory_core/memory_router.py and memory_core/reflexion_memory.py
        result = test_memory_health.test_modules_available(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 2
        names = [m["name"] for m in result]
        assert "memory_router" in names
        assert "reflexion_memory" in names

    def test_existing_modules(self, tmp_path):
        core_dir = tmp_path / "memory_core"
        core_dir.mkdir()
        (core_dir / "memory_router.py").write_text("# module")
        result = test_memory_health.test_modules_available(tmp_path)
        router = [m for m in result if m["name"] == "memory_router"][0]
        assert router["available"] is True
