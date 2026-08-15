"""Regeneration must not flatten milestone-to-commit causal edges (issue #4071).

``_dedupe_events`` used to overwrite every event timestamp with the session
date at midnight, including commit events that carry a real committer date.
``_event_order_relation`` then saw a tie between a commit and a milestone,
returned None per the #3464 incomparability rule, and dropped the edge.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import extract_session_episode

SESSION_ID = "2026-07-30-session-4071"
MIDNIGHT = "2026-07-30T00:00:00+00:00"
COMMIT_TIME = "2026-07-30T22:16:53+00:00"
SHA = "0456c2748fa1b2c3d4e5f60718293a4b5c6d7e8f"


def _event(event_id, event_type, content, timestamp=MIDNIGHT):
    return {
        "id": event_id,
        "type": event_type,
        "content": content,
        "timestamp": timestamp,
        "caused_by": [],
        "leads_to": [],
    }


def _flat_episode(commit_timestamp=MIDNIGHT):
    """The damaged shape: milestones and a commit all stamped at midnight."""
    return {
        "id": f"episode-{SESSION_ID}",
        "session": SESSION_ID,
        "timestamp": MIDNIGHT,
        "outcome": "success",
        "task": "reduce eval noise",
        "decisions": [],
        "events": [
            _event("e001", "milestone", "Filed the issue"),
            _event("e002", "milestone", "Reproduced the flatten"),
            _event("e003", "milestone", "Wrote the regression test"),
            _event("e004", "commit", f"Commit: {SHA}", commit_timestamp),
        ],
        "lessons": [],
        "metrics": {},
    }


def _regenerate(existing, monkeypatch, git_timestamp):
    """Run the preserve path with git resolution mocked at the process boundary."""
    monkeypatch.setattr(
        extract_session_episode, "_git_commit_timestamp", lambda sha: git_timestamp
    )
    fresh = _flat_episode()
    merged = extract_session_episode.merge_preserving(fresh, existing, session_id=SESSION_ID)
    extract_session_episode._renumber_events(merged["events"])
    extract_session_episode._link_sequential_events(merged["events"])
    return merged


def _by_type(events, event_type):
    return [evt for evt in events if evt["type"] == event_type]


class TestPreserveKeepsCausalEdges:
    """Positive: real-timestamped milestones keep edges; midnight ones do not.

    Issue #4071 required that regeneration not flatten edges when the commit
    has a real timestamp.  Issue #4847 refined this: milestones at synthetic
    midnight are incomparable to commits because their true time is unknown.
    Only milestones with real (non-midnight) timestamps produce edges.
    """

    def test_preserve_drops_midnight_milestone_to_commit_edges(self, tmp_path, monkeypatch):
        """Milestones at midnight are incomparable to commits (issue #4847)."""
        merged = _regenerate(_flat_episode(), monkeypatch, COMMIT_TIME)

        commit = _by_type(merged["events"], "commit")[0]
        milestones = _by_type(merged["events"], "milestone")

        assert commit["timestamp"] == COMMIT_TIME
        # Midnight milestones have no edge to the commit (issue #4847).
        assert all(commit["id"] not in m.get("leads_to", []) for m in milestones)
        assert commit.get("caused_by", []) == []

    def test_preserve_keeps_real_timestamped_milestone_edges(self, monkeypatch):
        """Milestones with real timestamps still produce causal edges."""
        real_milestone_time = "2026-07-30T21:00:00+00:00"
        episode = _flat_episode()
        # Give the first milestone a real timestamp
        episode["events"][0]["timestamp"] = real_milestone_time

        merged = _regenerate(episode, monkeypatch, COMMIT_TIME)

        commit = _by_type(merged["events"], "commit")[0]
        first_milestone = merged["events"][0]

        # Real-timestamped milestone (21:00) is before commit (22:16), edge exists
        assert commit["id"] in first_milestone.get("leads_to", [])

    def test_preserve_restores_commit_edges_lost_by_an_earlier_run(self, monkeypatch):
        damaged = _flat_episode()
        before = extract_session_episode._total_causal_edges(damaged["events"])

        merged = _regenerate(damaged, monkeypatch, COMMIT_TIME)

        assert before == 0
        # Midnight milestones on the same date are incomparable to commits
        # (issue #4847), so no edges are created between them.
        assert extract_session_episode._total_causal_edges(merged["events"]) == 0


class TestPreserveFailsClosed:
    """Negative: no git evidence means no invented ordering."""

    def test_leaves_milestone_unlinked_when_git_cannot_resolve_sha(self, monkeypatch):
        merged = _regenerate(_flat_episode(), monkeypatch, None)

        commit = _by_type(merged["events"], "commit")[0]

        assert commit["timestamp"] == MIDNIGHT
        assert commit["caused_by"] == []
        assert all(m["leads_to"] == [] for m in _by_type(merged["events"], "milestone"))

    def test_does_not_stamp_non_commit_events(self, monkeypatch):
        existing = _flat_episode()
        existing["events"][0]["content"] = f"Referenced {SHA} in the issue body"

        merged = _regenerate(existing, monkeypatch, COMMIT_TIME)

        assert all(m["timestamp"] == MIDNIGHT for m in _by_type(merged["events"], "milestone"))


class TestPreserveEdgeCases:
    """Edge: idempotence and the git-less fallback."""

    def test_preserve_commit_timestamp_is_idempotent(self, monkeypatch):
        once = _regenerate(_flat_episode(), monkeypatch, COMMIT_TIME)
        twice = _regenerate(once, monkeypatch, COMMIT_TIME)

        assert json.dumps(twice, indent=2) == json.dumps(once, indent=2)

    def test_keeps_stored_real_timestamp_when_git_unavailable(self, monkeypatch):
        already_correct = _flat_episode(commit_timestamp=COMMIT_TIME)

        merged = _regenerate(already_correct, monkeypatch, None)

        commit = _by_type(merged["events"], "commit")[0]
        assert commit["timestamp"] == COMMIT_TIME
        # Midnight milestones are incomparable to commits (issue #4847),
        # so no causal edges are created between them.
        assert extract_session_episode._total_causal_edges(merged["events"]) == 0


class TestTotalCausalEdges:
    """The counter behind the regression warning."""

    @pytest.mark.parametrize(
        ("events", "expected"),
        [
            (None, 0),
            ([], 0),
            ([{"leads_to": None}], 0),
            (["not a dict"], 0),
            ([{"leads_to": ["e002", "e003"]}, {"leads_to": []}], 2),
        ],
    )
    def test_counts_leads_to_entries(self, events, expected):
        assert extract_session_episode._total_causal_edges(events) == expected


class TestPreserveCliEdgeWarning:
    """CLI: exit code stays 0, and a drop is reported on stderr."""

    @staticmethod
    def _write_log(tmp_path):
        log = tmp_path / f"{SESSION_ID}.json"
        log.write_text(
            json.dumps(
                {
                    "session": {"date": "2026-07-30"},
                    "workLog": [{"task": "fresh extraction milestone"}],
                    "endingCommit": SHA,
                }
            ),
            encoding="utf-8",
        )
        return log

    @staticmethod
    def _write_episode(tmp_path, episode):
        out = tmp_path / "episodes"
        out.mkdir(exist_ok=True)
        (out / f"episode-{SESSION_ID}.json").write_text(
            json.dumps(episode), encoding="utf-8"
        )
        return out

    def test_preserve_cli_exits_zero_and_does_not_reduce_edges(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            extract_session_episode, "_git_commit_timestamp", lambda sha: COMMIT_TIME
        )
        out = self._write_episode(tmp_path, _flat_episode())
        log = self._write_log(tmp_path)

        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])

        written = json.loads((out / f"episode-{SESSION_ID}.json").read_text(encoding="utf-8"))
        assert rc == 0
        # Midnight milestones are incomparable to commits (issue #4847),
        # so no false causal edges are created.
        assert extract_session_episode._total_causal_edges(written["events"]) == 0
        assert "causal edge count decreased" not in capsys.readouterr().err

    def test_preserve_cli_warns_on_stderr_when_edge_count_drops(
        self, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(
            extract_session_episode, "_git_commit_timestamp", lambda sha: None
        )
        inflated = _flat_episode()
        inflated["events"][0]["leads_to"] = ["e004"]
        inflated["events"][3]["caused_by"] = ["e001"]
        out = self._write_episode(tmp_path, inflated)
        log = self._write_log(tmp_path)

        rc = extract_session_episode.main([str(log), "--output-path", str(out), "--preserve"])

        assert rc == 0
        assert "WARNING: causal edge count decreased: 1 -> 0" in capsys.readouterr().err
