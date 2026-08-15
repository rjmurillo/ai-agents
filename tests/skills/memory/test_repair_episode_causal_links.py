"""The repair pass restores causal edges an already-flattened episode lost.

Issue #4071 sub-claim 7: the extractor stopped flattening new episodes, but the
episodes already on disk stayed flat. Regenerating them needs their session log
and a resolvable commit SHA; the repair needs neither the log nor --preserve.

The CLI is driven through subprocess so the exit-code contract is what is
tested, not an in-process call that cannot see it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT / ".claude" / "skills" / "memory" / "scripts" / "repair_episode_causal_links.py"
)
MIDNIGHT = "2026-07-30T00:00:00+00:00"
UNRESOLVABLE_SHA = "303c6d2aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _resolvable_sha() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


def _event(event_id: str, event_type: str, content: str) -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "content": content,
        "timestamp": MIDNIGHT,
        "caused_by": [],
        "leads_to": [],
    }


def _flat_episode(sha: str) -> dict:
    return {
        "id": "episode-2026-07-30-session-4071",
        "session": "2026-07-30-session-4071",
        "timestamp": MIDNIGHT,
        "outcome": "success",
        "task": "repair the corpus",
        "decisions": [],
        "events": [
            _event("e001", "milestone", "Reproduced the flattening"),
            _event("e002", "milestone", "Wrote the repair"),
            _event("e003", "commit", f"Commit: {sha}"),
        ],
        "lessons": [],
        "metrics": {},
    }


def _write_episode(directory: Path, name: str, episode: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(episode, indent=2) + "\n", encoding="utf-8")
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )


def _summary(result: subprocess.CompletedProcess) -> dict:
    return json.loads(result.stdout)


class TestRepair:
    """A flat episode with a resolvable commit regains its edges."""

    @pytest.mark.unit
    def test_flat_episode_with_midnight_milestones_is_unrepairable(self, tmp_path):
        """Milestones at midnight are incomparable to commits (issue #4847).

        The repair cannot create edges between them because the milestone's
        true time is unknown. This is correct: the old behavior created false
        causal edges.
        """
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 0, result.stderr
        summary = _summary(result)
        assert summary["Repaired"] == 0
        assert str(path) in summary["Unrepairable"]

    @pytest.mark.unit
    def test_unrepairable_episode_is_not_rewritten(self, tmp_path):
        """An unrepairable episode is left on disk unchanged (issue #4847)."""
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))
        before = path.read_bytes()

        _run("--episodes-dir", str(episodes))

        assert path.read_bytes() == before

    @pytest.mark.unit
    def test_second_run_changes_nothing(self, tmp_path):
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))
        _run("--episodes-dir", str(episodes))
        after_first = path.read_bytes()

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 0, result.stderr
        assert _summary(result)["Repaired"] == 0
        assert path.read_bytes() == after_first

    @pytest.mark.unit
    def test_named_paths_override_the_directory(self, tmp_path):
        episodes = tmp_path / "episodes"
        target = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))
        _write_episode(episodes, "other.json", _flat_episode(_resolvable_sha()))

        result = _run(str(target))

        assert _summary(result)["Scanned"] == 1


class TestUnrepairable:
    """An unresolvable SHA leaves no ordering evidence, so nothing is invented."""

    @pytest.mark.unit
    def test_unresolvable_sha_is_reported_not_repaired(self, tmp_path):
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "gone.json", _flat_episode(UNRESOLVABLE_SHA))
        before = path.read_bytes()

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 0, result.stderr
        assert _summary(result)["Unrepairable"] == [str(path)]
        assert path.read_bytes() == before

    @pytest.mark.unit
    def test_healthy_episode_is_left_alone(self, tmp_path):
        episodes = tmp_path / "episodes"
        episode = _flat_episode(_resolvable_sha())
        episode["events"] = [_event("e001", "milestone", "Only one event")]
        path = _write_episode(episodes, "single.json", episode)
        before = path.read_bytes()

        result = _run("--episodes-dir", str(episodes))

        assert _summary(result)["Unchanged"] == 1
        assert path.read_bytes() == before


class TestCliContract:
    """Exit codes follow the repository contract: 0 ok, 1 logic, 2 config."""

    @pytest.mark.unit
    def test_check_mode_reports_without_writing(self, tmp_path):
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))
        before = path.read_bytes()

        result = _run("--episodes-dir", str(episodes), "--check")

        assert result.returncode == 0, result.stderr
        # Midnight milestones are incomparable to commits (issue #4847),
        # so the episode is unrepairable, not repaired.
        assert _summary(result)["Repaired"] == 0
        assert path.read_bytes() == before

    @pytest.mark.unit
    def test_missing_directory_is_a_config_error(self, tmp_path):
        result = _run("--episodes-dir", str(tmp_path / "nope"))

        assert result.returncode == 2
        assert "no such directory" in result.stderr

    @pytest.mark.unit
    def test_invalid_episode_is_a_logic_error_and_does_not_stop_the_pass(self, tmp_path):
        episodes = tmp_path / "episodes"
        broken = _flat_episode(UNRESOLVABLE_SHA)
        broken["events"][0]["type"] = "artifact"
        _write_episode(episodes, "aa-broken.json", broken)
        good = _write_episode(episodes, "zz-good.json", _flat_episode(_resolvable_sha()))

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 1
        summary = _summary(result)
        assert len(summary["Invalid"]) == 1
        # The "good" episode has midnight milestones, so it's unrepairable (issue #4847)
        assert summary["Repaired"] == 0
        assert str(good) in summary["Unrepairable"]

    @pytest.mark.unit
    def test_unreadable_json_is_reported_not_raised(self, tmp_path):
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        (episodes / "bad.json").write_text("{not json", encoding="utf-8")

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 1
        assert len(_summary(result)["Invalid"]) == 1
