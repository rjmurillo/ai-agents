#!/usr/bin/env python3
"""Tests for invoke_auto_retrospective.py (Stop hook)."""

import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / ".claude" / "hooks" / "Stop"))

import invoke_auto_retrospective


class TestAutoRetrospective(unittest.TestCase):
    """Test Stop auto-retrospective hook."""

    def test_tty_stdin_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("sys.stdin") as mock_stdin:
                mock_stdin.isatty.return_value = True
                with patch.object(
                    invoke_auto_retrospective,
                    "get_project_directory",
                    return_value=tmp_path,
                ):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)

    def test_bypass_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            with patch.dict("os.environ", {"SKIP_AUTO_RETRO": "true"}):
                with patch("sys.stdin", StringIO("")):
                    with patch.object(
                        invoke_auto_retrospective,
                        "get_project_directory",
                        return_value=tmp_path,
                    ):
                        result = invoke_auto_retrospective.main()
                        self.assertEqual(result, 0)

    def test_skips_if_retro_exists_today(self):
        """Should not create duplicate retros."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            retro_dir = tmp_path / ".agents" / "retrospective"
            retro_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            existing = retro_dir / f"{today}-manual-retro.md"
            existing.write_text("# Already exists")

            with patch("sys.stdin", StringIO("")):
                with patch.object(
                    invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
                ):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)
                    # No new file created
                    files = list(retro_dir.glob("*.md"))
                    self.assertEqual(len(files), 1)

    def test_skips_trivial_sessions(self):
        """Should not generate retro for trivial sessions."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({"work": [], "outcomes": []}))

            with patch("sys.stdin", StringIO("")):
                with patch.object(
                    invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
                ):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)

    def test_generates_retro_for_nontrivial_session(self):
        """Nontrivial session: main() exits 0 and writes nothing (mechanism removed #2531)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({
                "work": ["Implemented feature X"],
                "outcomes": ["PR created"]
            }))

            with patch("sys.stdin", StringIO("")):
                with patch.object(
                    invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
                ):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)

                    # No retro file created (mechanism removed per #2531)
                    retro_dir = tmp_path / ".agents" / "retrospective"
                    retros = (
                        list(retro_dir.glob(f"{today}*.md")) if retro_dir.exists() else []
                    )
                    self.assertEqual(len(retros), 0)

                    # No INDEX.md created
                    index = tmp_path / "docs" / "retros" / "INDEX.md"
                    self.assertFalse(index.exists())

    def test_fail_open_on_os_error(self):
        """OSError should not crash the hook."""
        with patch("sys.stdin", StringIO("")):
            with patch.object(
                invoke_auto_retrospective,
                "get_project_directory",
                return_value=Path("/nonexistent/path"),
            ):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

    def test_index_repaired_when_retro_already_exists(self):
        """Existing retro today: main() skips and does NOT create INDEX.md (#2531)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            retro_dir = tmp_path / ".agents" / "retrospective"
            retro_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            existing = retro_dir / f"{today}-auto-retro.md"
            existing.write_text("# Prior retro")
            # docs/retros/INDEX.md intentionally missing

            with patch("sys.stdin", StringIO("")):
                with patch.object(
                    invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
                ):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)
                    index = tmp_path / "docs" / "retros" / "INDEX.md"
                    self.assertFalse(index.exists())

    def test_index_update_idempotent_on_repeat(self):
        """update_retro_index is a no-op after #2531; no INDEX.md written."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            today = "2026-04-20"
            invoke_auto_retrospective.update_retro_index(
                tmp_path, today, "2026-04-20-auto-retro.md"
            )
            invoke_auto_retrospective.update_retro_index(
                tmp_path, today, "2026-04-20-auto-retro.md"
            )
            index = tmp_path / "docs" / "retros" / "INDEX.md"
            self.assertFalse(index.exists())

    def test_index_row_links_to_retro_file_location(self):
        """update_retro_index is a no-op after #2531; no INDEX.md written."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            today = "2026-04-20"
            filename = "2026-04-20-auto-retro.md"
            invoke_auto_retrospective.update_retro_index(tmp_path, today, filename)
            self.assertFalse((tmp_path / "docs" / "retros" / "INDEX.md").exists())

    def test_index_update_upgrades_bare_filename_row(self):
        """update_retro_index is a no-op after #2531; pre-existing INDEX.md is unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            today = "2026-04-20"
            filename = "2026-04-20-auto-retro.md"
            index = tmp_path / "docs" / "retros" / "INDEX.md"
            index.parent.mkdir(parents=True)
            original = (
                "# Retrospective Index\n\n"
                "| Date | File | Summary |\n"
                "|------|------|---------|\n"
                f"| {today} | {filename} | Auto-generated session retro |\n"
            )
            index.write_text(original, encoding="utf-8")

            invoke_auto_retrospective.update_retro_index(tmp_path, today, filename)

            # File is untouched
            self.assertEqual(index.read_text(encoding="utf-8"), original)

    def test_pick_same_day_retro_returns_none_when_empty(self):
        """No same-day candidates yields None."""
        with tempfile.TemporaryDirectory() as tmp:
            retro_dir = Path(tmp)
            result = invoke_auto_retrospective._pick_same_day_retro(retro_dir, "2026-04-20")
            self.assertIsNone(result)

    def test_pick_same_day_retro_picks_newest_by_mtime(self):
        """Multiple same-day retros: newest mtime wins."""
        with tempfile.TemporaryDirectory() as tmp:
            retro_dir = Path(tmp)
            today = "2026-04-20"
            older = retro_dir / f"{today}-auto-retro.md"
            newer = retro_dir / f"{today}-manual-retro.md"
            older.write_text("old")
            newer.write_text("new")
            import os
            os.utime(older, (1_000_000, 1_000_000))
            os.utime(newer, (2_000_000, 2_000_000))

            result = invoke_auto_retrospective._pick_same_day_retro(retro_dir, today)
            self.assertEqual(result, newer)

    def test_pick_same_day_retro_is_deterministic(self):
        """Same directory contents pick the same file on every call."""
        with tempfile.TemporaryDirectory() as tmp:
            retro_dir = Path(tmp)
            today = "2026-04-20"
            for name in ("a", "b", "c"):
                (retro_dir / f"{today}-{name}-retro.md").write_text(name)

            first = invoke_auto_retrospective._pick_same_day_retro(retro_dir, today)
            second = invoke_auto_retrospective._pick_same_day_retro(retro_dir, today)
            third = invoke_auto_retrospective._pick_same_day_retro(retro_dir, today)
            self.assertEqual(first, second)
            self.assertEqual(second, third)


class TestRemovedSkeletonMechanism(unittest.TestCase):
    """Issue #2531: skeleton writer is removed; hook must be inert."""

    def _make_project_with_nontrivial_session(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        session = sessions_dir / f"{today}-session-1.json"
        session.write_text(
            json.dumps({
                "work": ["Implemented feature X", "Fixed bug Y"],
                "outcomes": ["PR #42 opened", "CI green"],
            }),
            encoding="utf-8",
        )

    def test_no_skeleton_written_on_stop(self):
        """main() must not create any file under .agents/retrospective/."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._make_project_with_nontrivial_session(tmp_path)

            with patch("sys.stdin") as mock_stdin, patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                mock_stdin.isatty.return_value = False
                mock_stdin.read.return_value = "{}"
                result = invoke_auto_retrospective.main()

            self.assertEqual(result, 0)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            retro_dir = tmp_path / ".agents" / "retrospective"
            created = (
                list(retro_dir.glob(f"{today}-auto-retro.md"))
                if retro_dir.exists()
                else []
            )
            self.assertEqual(created, [], "No auto-retro file should be written")
            index = tmp_path / "docs" / "retros" / "INDEX.md"
            self.assertFalse(index.exists(), "INDEX.md must not be created")

    def test_no_index_row_appended_when_index_exists(self):
        """Pre-existing INDEX.md must be byte-for-byte unchanged after main()."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._make_project_with_nontrivial_session(tmp_path)
            index_dir = tmp_path / "docs" / "retros"
            index_dir.mkdir(parents=True)
            index = index_dir / "INDEX.md"
            original_content = (
                "# Retrospective Index\n\n"
                "| Date | File | Summary |\n"
                "|------|------|---------|\n"
                "| 2026-01-01 | [2026-01-01-auto-retro.md]"
                "(../../.agents/retrospective/2026-01-01-auto-retro.md)"
                " | Auto-generated session retro |\n"
            )
            index.write_bytes(original_content.encode("utf-8"))

            with patch("sys.stdin") as mock_stdin, patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                mock_stdin.isatty.return_value = False
                mock_stdin.read.return_value = "{}"
                invoke_auto_retrospective.main()

            self.assertEqual(
                index.read_bytes(),
                original_content.encode("utf-8"),
                "INDEX.md must be byte-for-byte unchanged",
            )

    def test_existing_legacy_skeleton_not_renagged(self):
        """A legacy skeleton on disk does not affect main()'s return code."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._make_project_with_nontrivial_session(tmp_path)
            retro_dir = tmp_path / ".agents" / "retrospective"
            retro_dir.mkdir(parents=True)
            legacy = retro_dir / "2026-06-01-auto-retro.md"
            legacy.write_text(
                invoke_auto_retrospective.RETRO_STATE_MARKER + "\n# Old skeleton\n",
                encoding="utf-8",
            )
            original_mtime = legacy.stat().st_mtime

            with patch("sys.stdin") as mock_stdin, patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                mock_stdin.isatty.return_value = False
                mock_stdin.read.return_value = "{}"
                result = invoke_auto_retrospective.main()

            self.assertEqual(result, 0)
            self.assertEqual(
                legacy.stat().st_mtime,
                original_mtime,
                "Legacy skeleton file must not be touched",
            )


class TestAutoRetrospectiveDocstring(unittest.TestCase):
    """Module docstring reflects no-op status after #2531."""

    def test_module_docstring_describes_noop(self):
        """The module docstring describes the no-op status, not skeleton creation."""
        doc = invoke_auto_retrospective.__doc__ or ""
        self.assertIn("No-op", doc)
        self.assertIn("#2531", doc)



class TestAutoRetroSuppressionSentinel(unittest.TestCase):
    """Issue #2327: a suppression sentinel makes the Stop hook tree-neutral."""

    def _sentinel(self, project_dir: Path) -> Path:
        path = (
            project_dir
            / ".agents"
            / ".hook-state"
            / invoke_auto_retrospective.AUTO_RETRO_SUPPRESS_SENTINEL
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def test_is_suppressed_true_when_sentinel_present(self):
        """Positive: the predicate reports True when the sentinel exists."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._sentinel(tmp_path)
            self.assertTrue(
                invoke_auto_retrospective.is_auto_retro_suppressed(tmp_path)
            )

    def test_is_suppressed_false_when_absent(self):
        """Negative: no sentinel means no suppression."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            self.assertFalse(
                invoke_auto_retrospective.is_auto_retro_suppressed(tmp_path)
            )

    def test_suppressed_run_leaves_worktree_clean(self):
        """Negative path: with the sentinel set, a non-trivial session writes nothing.

        Regression for #2327: no auto-retro file under .agents/retrospective/
        and no docs/retros/INDEX.md created, even though the session is
        non-trivial and would normally generate a skeleton.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(
                json.dumps({
                    "work": ["Real work that would normally trigger a retro"],
                    "outcomes": ["PR opened"],
                }),
                encoding="utf-8",
            )
            self._sentinel(tmp_path)

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

            retro_dir = tmp_path / ".agents" / "retrospective"
            self.assertEqual(list(retro_dir.glob("*.md")) if retro_dir.exists() else [], [])
            self.assertFalse((tmp_path / "docs" / "retros" / "INDEX.md").exists())

    def test_suppressed_run_audits_skip_reason(self):
        """Edge: the suppressed run records a 'skipped' audit citing the sentinel."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(
                json.dumps({"work": ["x"], "outcomes": ["y"]}),
                encoding="utf-8",
            )
            self._sentinel(tmp_path)

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                invoke_auto_retrospective.main()

            audit_file = (
                tmp_path
                / ".agents"
                / ".hook-state"
                / "auto-retrospective"
                / f"{today}.jsonl"
            )
            records = [
                json.loads(line)
                for line in audit_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "skipped")
            self.assertEqual(records[0]["skip_reason"], "suppress sentinel present")

    def test_no_sentinel_still_generates(self):
        """Without sentinel, mechanism removed means nothing is written (#2531)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(
                json.dumps({"work": ["real work"], "outcomes": ["done"]}),
                encoding="utf-8",
            )

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                invoke_auto_retrospective.main()

            retro_dir = tmp_path / ".agents" / "retrospective"
            self.assertEqual(
                list(retro_dir.glob(f"{today}*.md")) if retro_dir.exists() else [], []
            )


class TestAutoRetrospectiveAudit(unittest.TestCase):
    """Audit-trail JSONL coverage for Issue #2062."""

    @staticmethod
    def _read_audit_records(project_dir: Path) -> list[dict[str, Any]]:
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        audit_file = (
            project_dir / ".agents" / ".hook-state" / "auto-retrospective" / f"{today}.jsonl"
        )
        if not audit_file.exists():
            return []
        records = []
        for line in audit_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
        return records

    def _assert_record_shape(self, record: dict[str, Any]) -> None:
        """Audit records carry every field the acceptance criteria requires."""
        self.assertIn("timestamp", record)
        self.assertIn("status", record)
        self.assertIn("retro_filename", record)
        self.assertIn("skip_reason", record)
        self.assertEqual(record.get("hook"), "invoke_auto_retrospective")
        self.assertEqual(record.get("schema"), 1)
        # Timestamp is a valid ISO 8601 string.
        datetime.fromisoformat(record["timestamp"])

    def test_audit_created_path(self):
        """A nontrivial session now emits 'skipped/mechanism removed' (#2531)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({
                "work": ["Implemented audit trail"],
                "outcomes": ["Audit log emitted"],
            }))

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

            records = self._read_audit_records(tmp_path)
            self.assertEqual(len(records), 1)
            self._assert_record_shape(records[0])
            self.assertEqual(records[0]["status"], "skipped")
            self.assertIn("#2531", records[0]["skip_reason"])
            self.assertEqual(records[0]["retro_filename"], "")

    def test_audit_skipped_trivial_session(self):
        """A trivial session emits a 'skipped' record with skip_reason."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({"work": [], "outcomes": []}))

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

            records = self._read_audit_records(tmp_path)
            self.assertEqual(len(records), 1)
            self._assert_record_shape(records[0])
            self.assertEqual(records[0]["status"], "skipped")
            self.assertEqual(records[0]["skip_reason"], "trivial session")
            self.assertEqual(records[0]["retro_filename"], "")

    def test_audit_skipped_existing_retro(self):
        """An existing retro emits a 'skipped' record naming the existing file."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            retro_dir = tmp_path / ".agents" / "retrospective"
            retro_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            existing = retro_dir / f"{today}-manual-retro.md"
            existing.write_text("# Already exists")

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

            records = self._read_audit_records(tmp_path)
            self.assertEqual(len(records), 1)
            self._assert_record_shape(records[0])
            self.assertEqual(records[0]["status"], "skipped")
            self.assertEqual(records[0]["skip_reason"], "retro already exists today")
            self.assertEqual(records[0]["retro_filename"], existing.name)

    def test_audit_skipped_bypass_env(self):
        """SKIP_AUTO_RETRO=true emits a 'skipped' record citing the env var."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()

            with patch.dict("os.environ", {"SKIP_AUTO_RETRO": "true"}):
                with patch("sys.stdin", StringIO("")), patch.object(
                    invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
                ):
                    result = invoke_auto_retrospective.main()
                    self.assertEqual(result, 0)

            records = self._read_audit_records(tmp_path)
            self.assertEqual(len(records), 1)
            self._assert_record_shape(records[0])
            self.assertEqual(records[0]["status"], "skipped")
            self.assertEqual(records[0]["skip_reason"], "SKIP_AUTO_RETRO=true")

    def test_audit_failed_path_replaced_by_mechanism_removed(self):
        """After #2531 the 'failed' status is unreachable; nontrivial session gets 'skipped'."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()
            sessions_dir = tmp_path / ".agents" / "sessions"
            sessions_dir.mkdir(parents=True)
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            session = sessions_dir / f"{today}-session-01.json"
            session.write_text(json.dumps({
                "work": ["force-failure"],
                "outcomes": ["ok"],
            }))

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ):
                result = invoke_auto_retrospective.main()
                self.assertEqual(result, 0)

            records = self._read_audit_records(tmp_path)
            self.assertEqual(len(records), 1)
            self._assert_record_shape(records[0])
            self.assertEqual(records[0]["status"], "skipped")
            self.assertIn("#2531", records[0]["skip_reason"])

    def test_audit_write_tolerates_missing_agents_dir(self):
        """write_audit_log silently no-ops when .agents/ is absent (consumer repo)."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # Intentionally do NOT create .agents/.
            invoke_auto_retrospective.write_audit_log(
                tmp_path, "skipped", skip_reason="consumer repo guard"
            )
            self.assertFalse((tmp_path / ".agents").exists())

    def test_audit_write_tolerates_unwritable_audit_dir(self):
        """write_audit_log swallows OSError and never propagates to the hook."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()

            def _raise_oserror(*_args, **_kwargs):
                raise OSError("simulated read-only filesystem")

            # Patch Path.mkdir to simulate an unwritable .hook-state directory.
            with patch("pathlib.Path.mkdir", side_effect=_raise_oserror):
                # Must not raise; the hook's fail-open contract depends on this.
                invoke_auto_retrospective.write_audit_log(
                    tmp_path, "created", retro_filename="x.md"
                )

    def test_audit_record_is_valid_jsonl(self):
        """Every audit line is valid JSON; lines are newline-delimited."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / ".agents").mkdir()

            # Write three records back-to-back.
            for i in range(3):
                invoke_auto_retrospective.write_audit_log(
                    tmp_path, "skipped", skip_reason=f"run {i}"
                )

            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            audit_file = (
                tmp_path / ".agents" / ".hook-state" / "auto-retrospective" / f"{today}.jsonl"
            )
            self.assertTrue(audit_file.exists())
            lines = audit_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            for i, line in enumerate(lines):
                record = json.loads(line)  # must parse
                self.assertEqual(record["status"], "skipped")
                self.assertEqual(record["skip_reason"], f"run {i}")


if __name__ == "__main__":
    unittest.main()
