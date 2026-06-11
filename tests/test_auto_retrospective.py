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
        """Should generate retro when session has work items."""
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

                    # Retro file created
                    retro_dir = tmp_path / ".agents" / "retrospective"
                    retros = list(retro_dir.glob(f"{today}*.md"))
                    self.assertEqual(len(retros), 1)
                    content = retros[0].read_text()
                    self.assertIn("Implemented feature X", content)

                    # INDEX.md updated
                    index = tmp_path / "docs" / "retros" / "INDEX.md"
                    self.assertTrue(index.exists())
                    self.assertIn(today, index.read_text())

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
        """Existing retro without INDEX row triggers index recovery on next run."""
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
                    self.assertTrue(index.exists())
                    self.assertIn(f"{today}-auto-retro.md", index.read_text())

    def test_index_update_idempotent_on_repeat(self):
        """update_retro_index does not duplicate a row already present."""
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
            content = index.read_text()
            # One data row for the filename. Count the date cell, not the
            # filename: since #2229 each row links the filename twice (link
            # text + relative URL), so counting the filename overcounts.
            self.assertEqual(content.count("| 2026-04-20 |"), 1)

    def test_index_row_links_to_retro_file_location(self):
        """Regression #2229: INDEX rows must link to the actual retro file.

        INDEX.md lives in docs/retros/ but retro files live in
        .agents/retrospective/. A bare filename resolves against docs/retros/
        (a dead link); the row must use a relative path that resolves.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            today = "2026-04-20"
            filename = "2026-04-20-auto-retro.md"
            invoke_auto_retrospective.update_retro_index(tmp_path, today, filename)
            content = (tmp_path / "docs" / "retros" / "INDEX.md").read_text()
            self.assertIn(
                f"[{filename}](../../.agents/retrospective/{filename})", content
            )

    def test_index_update_upgrades_bare_filename_row(self):
        """Regression #2229: old bare filename rows are repaired in place."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            today = "2026-04-20"
            filename = "2026-04-20-auto-retro.md"
            index = tmp_path / "docs" / "retros" / "INDEX.md"
            index.parent.mkdir(parents=True)
            index.write_text(
                "# Retrospective Index\n\n"
                "| Date | File | Summary |\n"
                "|------|------|---------|\n"
                f"| {today} | {filename} | Auto-generated session retro |\n",
                encoding="utf-8",
            )

            invoke_auto_retrospective.update_retro_index(tmp_path, today, filename)

            content = index.read_text(encoding="utf-8")
            self.assertIn(
                f"[{filename}](../../.agents/retrospective/{filename})", content
            )
            self.assertEqual(content.count(f"| {today} |"), 1)

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


class TestRetroSkeletonText(unittest.TestCase):
    """Issue #2079: the emitted skeleton must be an honest unfilled prompt."""

    def _generate(self, tmp_path: Path, today: str) -> str:
        retro_path = invoke_auto_retrospective.generate_retrospective(tmp_path, today)
        if retro_path is None:
            self.fail("generate_retrospective returned None")
        return retro_path.read_text(encoding="utf-8")

    def test_skeleton_carries_fill_instruction(self):
        """Each placeholder section tells the reader to run the retrospective agent."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            self.assertIn("Run the retrospective agent to populate this section", content)
            # One instruction per placeholder section (4 sections total).
            self.assertEqual(
                content.count("Run the retrospective agent to populate this section"), 4
            )

    def test_skeleton_marked_unfilled_in_banner(self):
        """The header banner flags the file as an unfilled skeleton, not a result."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            self.assertIn("UNFILLED SKELETON", content)
            self.assertIn("not a completed retrospective", content)

    def test_skeleton_does_not_imply_human_review(self):
        """The old wording implied a human already reviewed; it must be gone."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            self.assertNotIn("To be filled by reviewing agent or human", content)
            self.assertNotIn("Auto-generated by invoke_auto_retrospective.py", content)

    def test_skeleton_preserves_section_headings(self):
        """Behavior-preserving: the four retro sections still render."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            for heading in (
                "## What Went Well",
                "## What Could Improve",
                "## Key Learnings",
                "## Failure Patterns",
            ):
                self.assertIn(heading, content)

    def test_failure_patterns_reference_points_at_existing_path(self):
        """Issue #2550: the Failure Patterns placeholder must reference a path
        that actually exists in the repo, not a dead directory.

        Regression guard: prior to the fix the skeleton pointed at
        ``.agents/failure-modes/`` which does not exist. The canonical location
        is ``.agents/governance/FAILURE-MODES.md``. Pinning the exact reference
        keeps the placeholder honest and prevents future regenerated skeletons
        from carrying dead references.
        """
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            # Positive: the new, canonical reference is present.
            self.assertIn(".agents/governance/FAILURE-MODES.md", content)

            # Negative: the dead reference must be gone.
            self.assertNotIn(".agents/failure-modes/", content)

            # Repo-truth check: the referenced path actually exists in the
            # checkout this test runs from. This catches future renames on
            # either side (the skeleton OR the governance file) without a
            # mirrored update.
            repo_root = Path(__file__).resolve().parent.parent
            self.assertTrue(
                (repo_root / ".agents" / "governance" / "FAILURE-MODES.md").exists(),
                "skeleton references .agents/governance/FAILURE-MODES.md but the "
                "file is missing from the repo; either the file was moved or the "
                "skeleton reference drifted.",
            )

    def test_module_docstring_describes_skeleton(self):
        """The module docstring no longer claims it generates a retrospective."""
        doc = invoke_auto_retrospective.__doc__ or ""
        self.assertIn("placeholder retrospective skeleton", doc)
        self.assertNotIn("Auto-generates retrospective on session end", doc)


class TestRetroSkeletonMarker(unittest.TestCase):
    """Issue #2079 AC1: the skeleton carries a stable RETRO-STATE marker."""

    def _generate(self, tmp_path: Path, today: str) -> str:
        retro_path = invoke_auto_retrospective.generate_retrospective(tmp_path, today)
        if retro_path is None:
            self.fail("generate_retrospective returned None")
        return retro_path.read_text(encoding="utf-8")

    def test_skeleton_contains_marker_constant(self):
        """Positive: a freshly written skeleton carries the marker verbatim."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            self.assertIn(invoke_auto_retrospective.RETRO_STATE_MARKER, content)

    def test_marker_is_the_exact_contract_string(self):
        """The marker matches the literal the SessionStart reader scans for.

        Canonical contract (Issue #2079 body): ``<!-- RETRO-STATE:
        skeleton-pending-fill -->``. The reader mirrors this exact string; a
        drift here silently breaks the pending-retro reminder.
        """
        self.assertEqual(
            invoke_auto_retrospective.RETRO_STATE_MARKER,
            "<!-- RETRO-STATE: skeleton-pending-fill -->",
        )

    def test_marker_leads_the_file(self):
        """Edge: the marker is the first line so a head-only read still finds it."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            first_line = content.splitlines()[0]
            self.assertEqual(first_line, invoke_auto_retrospective.RETRO_STATE_MARKER)

    def test_banner_points_at_retro_fill_command(self):
        """The banner tells the reader to run /retro fill <date> (Issue #2079)."""
        with tempfile.TemporaryDirectory() as tmp:
            content = self._generate(Path(tmp), "2026-04-20")

            self.assertIn("/retro fill 2026-04-20", content)


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
        """Positive baseline: without the sentinel, a non-trivial session writes the retro.

        Guards against the suppression guard accidentally disabling the hook on
        the normal path.
        """
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
            self.assertEqual(len(list(retro_dir.glob(f"{today}*.md"))), 1)


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
        """A nontrivial session writes a 'created' audit record with filename."""
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
            self.assertEqual(records[0]["status"], "created")
            self.assertTrue(records[0]["retro_filename"].endswith("-auto-retro.md"))
            self.assertIn(today, records[0]["retro_filename"])
            self.assertEqual(records[0]["skip_reason"], "")

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

    def test_audit_failed_path(self):
        """An exception during generation emits a 'failed' record."""
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

            def _explode(*_args, **_kwargs):
                raise RuntimeError("synthetic failure")

            with patch("sys.stdin", StringIO("")), patch.object(
                invoke_auto_retrospective, "get_project_directory", return_value=tmp_path
            ), patch.object(
                invoke_auto_retrospective, "generate_retrospective", side_effect=_explode
            ):
                result = invoke_auto_retrospective.main()
                # Fail-open: still returns 0 even though generation threw.
                self.assertEqual(result, 0)

            records = self._read_audit_records(tmp_path)
            self.assertEqual(len(records), 1)
            self._assert_record_shape(records[0])
            self.assertEqual(records[0]["status"], "failed")
            self.assertIn("RuntimeError", records[0]["skip_reason"])
            self.assertIn("synthetic failure", records[0]["skip_reason"])

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
