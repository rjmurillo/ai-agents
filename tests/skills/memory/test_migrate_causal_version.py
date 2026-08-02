"""Tests for migrate_causal_version.py.

Issue #3598: existing episodes pre-date #3464. An absent causal_order_version
means the edges came from the legacy ordering rule and must not be read as
trusted v2 evidence. This migration script stamps the version on episodes
whose edges are already v2-equivalent, and rebuilds edges where the rebuild
improves the topology without dropping any edge.
"""

import copy
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import migrate_causal_version  # noqa: I001


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evt(eid, etype="milestone", content="x", *, ts="2026-07-01T10:00:00+00:00",
         leads_to=(), caused_by=()):
    return {
        "id": eid,
        "timestamp": ts,
        "type": etype,
        "content": content,
        "caused_by": list(caused_by),
        "leads_to": list(leads_to),
    }


def _write(path: Path, events: list, *, version=None, **extra) -> Path:
    payload: dict = {"id": "episode-s1", "session": "s1", "events": events}
    if version is not None:
        payload["causal_order_version"] = version
    payload.update(extra)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Positive: stamp_only
# ---------------------------------------------------------------------------

class TestStampOnly:
    """Episodes whose v2 rebuild produces the same edge topology are stamp-only."""

    def test_stamp_only_adds_causal_order_version(self, tmp_path):
        # Two events at distinct timestamps: v2 would link e001->e002.
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T11:00:00+00:00", caused_by=["e001"]),
        ]
        path = _write(tmp_path / "ep.json", events)

        outcome, reason = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        assert outcome == "stamp_only"
        data = _read(path)
        assert data["causal_order_version"] == 2

    def test_stamp_only_leaves_events_unchanged(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T11:00:00+00:00", caused_by=["e001"]),
        ]
        original_events = copy.deepcopy(events)
        path = _write(tmp_path / "ep.json", events)

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")

        data = _read(path)
        assert data["events"] == original_events

    def test_stamp_only_adds_migration_note(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T11:00:00+00:00", caused_by=["e001"]),
        ]
        path = _write(tmp_path / "ep.json", events)

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")

        data = _read(path)
        assert "migration_note" in data
        assert "stamp_only" in data["migration_note"]
        assert "2026-08-01" in data["migration_note"]

    def test_stamp_only_preserves_all_non_event_fields(self, tmp_path):
        events = [_evt("e001", ts="2026-07-01T10:00:00+00:00")]
        path = _write(
            tmp_path / "ep.json", events,
            outcome="success", task="do a thing", metrics={"commits": 1}
        )

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")

        data = _read(path)
        assert data["outcome"] == "success"
        assert data["task"] == "do a thing"
        assert data["metrics"] == {"commits": 1}


# ---------------------------------------------------------------------------
# Positive: relinked
# ---------------------------------------------------------------------------

class TestRelinked:
    """Episodes where the v2 rebuild adds edges are relinked and stamped."""

    def test_relinked_stamps_causal_order_version(self, tmp_path):
        # e001 and e002 have no edges stored, but v2 would link them.
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        path = _write(tmp_path / "ep.json", events)

        outcome, _ = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        assert outcome == "relinked"
        data = _read(path)
        assert data["causal_order_version"] == 2

    def test_relinked_adds_edges(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        path = _write(tmp_path / "ep.json", events)

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")

        data = _read(path)
        assert "e002" in data["events"][0]["leads_to"]

    def test_relinked_adds_migration_note(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        path = _write(tmp_path / "ep.json", events)

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")

        data = _read(path)
        assert "migration_note" in data
        assert "relinked" in data["migration_note"]

    def test_relinked_preserves_non_event_fields(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        path = _write(tmp_path / "ep.json", events, outcome="partial", metrics={"errors": 2})

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")

        data = _read(path)
        assert data["outcome"] == "partial"
        assert data["metrics"] == {"errors": 2}


# ---------------------------------------------------------------------------
# Negative: already_v2
# ---------------------------------------------------------------------------

class TestAlreadyV2:
    """Episodes already carrying causal_order_version=2 are untouched."""

    def test_already_v2_is_not_rewritten(self, tmp_path):
        events = [_evt("e001", ts="2026-07-01T10:00:00+00:00")]
        path = _write(tmp_path / "ep.json", events, version=2)
        original = path.read_bytes()

        outcome, _ = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        assert outcome == "already_v2"
        assert path.read_bytes() == original


# ---------------------------------------------------------------------------
# Negative: skipped
# ---------------------------------------------------------------------------

class TestSkipped:
    """Migrations that would drop edges, or unreadable files, are skipped."""

    def test_skipped_when_rebuild_drops_edges(self, tmp_path):
        # Store two edges; rebuild with no timestamps would drop them.
        events = [
            _evt("e001", ts="2026-07-01T00:00:00+00:00",
                 leads_to=["e002", "e003"]),
            _evt("e002", ts="2026-07-01T00:00:00+00:00",
                 caused_by=["e001"], leads_to=["e003"]),
            _evt("e003", ts="2026-07-01T00:00:00+00:00",
                 caused_by=["e001", "e002"]),
        ]
        path = _write(tmp_path / "ep.json", events)

        outcome, reason = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        assert outcome == "skipped"
        assert "drop" in reason

    def test_skipped_does_not_write_version(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T00:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T00:00:00+00:00", caused_by=["e001"]),
        ]
        path = _write(tmp_path / "ep.json", events)
        original = path.read_bytes()

        outcome, _ = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        # If skipped (same-timestamp drops edges), file must be unchanged.
        if outcome == "skipped":
            assert path.read_bytes() == original

    def test_skipped_on_unreadable_file(self, tmp_path):
        path = tmp_path / "ep.json"
        path.write_bytes(b"not json {{{")

        outcome, reason = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        assert outcome == "skipped"
        assert "unreadable" in reason

    def test_no_events_returns_no_events(self, tmp_path):
        path = _write(tmp_path / "ep.json", [])

        outcome, _ = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-01"
        )

        assert outcome == "no_events"


# ---------------------------------------------------------------------------
# Edge: idempotency
# ---------------------------------------------------------------------------

class TestIdempotent:
    """Running the migration twice leaves the second run with nothing to do."""

    def test_stamp_only_is_idempotent(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T11:00:00+00:00", caused_by=["e001"]),
        ]
        path = _write(tmp_path / "ep.json", events)

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")
        after_first = path.read_bytes()

        outcome, _ = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-02"
        )

        assert outcome == "already_v2"
        assert path.read_bytes() == after_first

    def test_relinked_is_idempotent(self, tmp_path):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        path = _write(tmp_path / "ep.json", events)

        migrate_causal_version.migrate_episode_file(path, stamp_date="2026-08-01")
        after_first = path.read_bytes()

        outcome, _ = migrate_causal_version.migrate_episode_file(
            path, stamp_date="2026-08-02"
        )

        assert outcome == "already_v2"
        assert path.read_bytes() == after_first


# ---------------------------------------------------------------------------
# main() exit codes
# ---------------------------------------------------------------------------

class TestMainExitCodes:
    """main() exits per ADR-035: 0 on clean, 1 on any skip, 2 on bad args."""

    def test_exits_0_when_directory_has_no_skipped(self, tmp_path, capsys):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T11:00:00+00:00", caused_by=["e001"]),
        ]
        _write(tmp_path / "episode-x.json", events)

        rc = migrate_causal_version.main([str(tmp_path)])

        assert rc == 0

    def test_exits_1_when_any_episode_is_skipped(self, tmp_path, capsys):
        # A file with same-timestamp events drops edges -> skipped.
        events = [
            _evt("e001", ts="2026-07-01T00:00:00+00:00", leads_to=["e002"]),
            _evt("e002", ts="2026-07-01T00:00:00+00:00", caused_by=["e001"]),
        ]
        _write(tmp_path / "episode-x.json", events)

        rc = migrate_causal_version.main([str(tmp_path)])

        assert rc == 1

    def test_exits_2_on_missing_path(self, tmp_path, capsys):
        rc = migrate_causal_version.main([str(tmp_path / "no-such-dir")])

        assert rc == 2

    def test_exits_2_on_traversal_path(self, tmp_path, capsys):
        rc = migrate_causal_version.main([str(tmp_path / ".." / "x")])

        assert rc == 2

    def test_exits_2_on_empty_directory(self, tmp_path, capsys):
        empty = tmp_path / "empty"
        empty.mkdir()

        rc = migrate_causal_version.main([str(empty)])

        assert rc == 2

    def test_dry_run_does_not_write(self, tmp_path, capsys):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        path = _write(tmp_path / "episode-x.json", events)
        original = path.read_bytes()

        migrate_causal_version.main([str(tmp_path), "--dry-run"])

        assert path.read_bytes() == original

    def test_dry_run_reports_counts(self, tmp_path, capsys):
        events = [
            _evt("e001", ts="2026-07-01T10:00:00+00:00"),
            _evt("e002", ts="2026-07-01T11:00:00+00:00"),
        ]
        _write(tmp_path / "episode-x.json", events)

        migrate_causal_version.main([str(tmp_path), "--dry-run"])

        out = capsys.readouterr().out
        summary = json.loads(out)
        assert summary["dry_run"] is True
        assert summary["total"] == 1
