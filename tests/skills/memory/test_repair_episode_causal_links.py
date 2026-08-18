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
from datetime import datetime, timezone
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
    def test_flat_episode_regains_edges_when_dates_differ(self, tmp_path):
        """Cross-date milestones and commits have known ordering (issue #4847).

        The milestones are dated 2026-07-30 (midnight) and the commit gets a
        real timestamp from git (today). Different dates mean the ordering is
        not ambiguous, so edges are created.
        """
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 0, result.stderr
        assert _summary(result)["Repaired"] == 1
        events = json.loads(path.read_text(encoding="utf-8"))["events"]
        assert events[0]["leads_to"] == ["e003"]
        assert events[2]["caused_by"] == ["e001", "e002"]

    @pytest.mark.unit
    def test_repaired_episode_is_rewritten(self, tmp_path):
        """A repaired episode gets its commit timestamp from git."""
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))
        before = path.read_bytes()

        _run("--episodes-dir", str(episodes))

        assert path.read_bytes() != before

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


class TestFalseEdgeRemoval:
    """The valid-edge-set guard permits removing the #4847 false edge.

    The raw-count guard (`after_edges <= before_edges` refuses to write)
    preserved the exact milestone-to-commit edge this tool exists to remove,
    because removing it makes the count go down (PR #5058 review). The
    discriminating input is an episode already carrying that false edge.
    """

    def test_false_milestone_to_commit_edge_is_removed(self, tmp_path):
        # The milestone sits at synthetic midnight on the SAME UTC date as
        # the commit's real committer date, so after restamping the pair is
        # incomparable (issue #4847) and the flattened-stamp edge between
        # them is exactly the false edge. The old guard refused this write;
        # the rebuilt file must not carry the edge. The date is derived from
        # the commit so the fixture cannot drift cross-date and turn the
        # pair comparable again.
        sha = _resolvable_sha()
        commit_timestamp = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", "-s", "--format=%cI", sha],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout.strip()
        commit_date = (
            datetime.fromisoformat(commit_timestamp)
            .astimezone(timezone.utc)
            .date()
            .isoformat()
        )
        midnight = f"{commit_date}T00:00:00+00:00"
        episode = _flat_episode(sha)
        for evt in episode["events"]:
            evt["timestamp"] = midnight
        episode["timestamp"] = midnight
        episode["events"][1]["leads_to"] = ["e003"]
        episode["events"][2]["caused_by"] = ["e002"]
        path = _write_episode(tmp_path, "false-edge.json", episode)

        result = _run("--episodes-dir", str(tmp_path))

        assert result.returncode == 0, result.stderr
        rewritten = json.loads(path.read_text(encoding="utf-8"))
        by_id = {evt["id"]: evt for evt in rewritten["events"]}
        assert "e003" not in by_id["e002"]["leads_to"], (
            "the false milestone-to-commit edge survived the repair"
        )
        assert "e002" not in by_id["e003"]["caused_by"]

    def test_curated_edge_between_comparable_events_refuses_the_write(
        self, tmp_path
    ):
        # Control: a hand-authored skip-level edge joins two milestones the
        # order relation still ranks (distinct real timestamps). The rebuild
        # would drop it, so the guard must refuse and leave the file
        # byte-identical; without this control the test above would pass
        # against a guard that allows every removal.
        sha = _resolvable_sha()
        episode = _flat_episode(sha)
        episode["events"][0]["timestamp"] = "2026-07-30T01:00:00+00:00"
        episode["events"][1]["timestamp"] = "2026-07-30T02:00:00+00:00"
        episode["events"][0]["leads_to"] = ["e003"]
        episode["events"][2]["caused_by"] = ["e001"]
        path = _write_episode(tmp_path, "curated-edge.json", episode)
        before = path.read_text(encoding="utf-8")

        result = _run("--episodes-dir", str(tmp_path))

        assert result.returncode == 0, result.stderr
        assert path.read_text(encoding="utf-8") == before, (
            "the guard rewrote a file whose removed edge was still comparable"
        )


class TestCliContract:
    """Exit codes follow the repository contract: 0 ok, 1 logic, 2 config."""

    @pytest.mark.unit
    def test_check_mode_reports_without_writing(self, tmp_path):
        episodes = tmp_path / "episodes"
        path = _write_episode(episodes, "flat.json", _flat_episode(_resolvable_sha()))
        before = path.read_bytes()

        result = _run("--episodes-dir", str(episodes), "--check")

        assert result.returncode == 0, result.stderr
        # Cross-date milestones are comparable, so the episode is repaired.
        assert _summary(result)["Repaired"] == 1
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
        # The "good" episode has cross-date milestones, so it IS repaired
        assert summary["Repaired"] == 1
        assert json.loads(good.read_text(encoding="utf-8"))["events"][0]["leads_to"] == ["e003"]

    @pytest.mark.unit
    def test_unreadable_json_is_reported_not_raised(self, tmp_path):
        episodes = tmp_path / "episodes"
        episodes.mkdir()
        (episodes / "bad.json").write_text("{not json", encoding="utf-8")

        result = _run("--episodes-dir", str(episodes))

        assert result.returncode == 1
        assert len(_summary(result)["Invalid"]) == 1
