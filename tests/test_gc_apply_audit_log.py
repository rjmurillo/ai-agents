"""Tests for the durable gc_worktrees removal audit log (issue #4790).

``_gc_apply._append_removal_record`` is the one place that writes the
append-only JSONL record for a worktree ``apply_removals`` actually removed,
distinct from the human-readable or ``--json`` stdout report. These tests
exercise it directly (schema, append semantics, missing-directory creation)
and through ``apply_removals`` (written only for a successful removal, never
for a dry-run, a skipped candidate, or a failed removal).

The root ``tests/conftest.py`` fixture ``_isolate_gc_worktree_audit_log``
patches ``_gc_apply.audit_log_path_for`` for every test in the suite, so a
call that omits ``audit_log_path`` never writes under a real checkout. Tests
of the resolver itself use the original, captured at import time below.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from scripts.maintenance import _gc_apply
from scripts.maintenance._gc_apply import audit_log_path_for as _real_audit_log_path_for
from scripts.maintenance.gc_worktrees import Decision, GcReport
from tests.gc_worktree_fixtures import (  # noqa: F401
    checkout_is_present,
    no_reflog_only_work,
)

_MAIN = "/repo"
_BASE = "origin/main"
_STUB_HEAD = "f" * 40


def _agrees(report: GcReport):
    return lambda: report


def _forbidden_git(*_args: str) -> str:
    raise AssertionError("apply_removals reached real git in a mocked test")


@pytest.fixture(autouse=True)
def _stub_pre_removal_head():
    with patch("scripts.maintenance._gc_apply._head_of", return_value=_STUB_HEAD):
        yield


class TestAppendRemovalRecord:
    """Direct tests of the audit-log writer."""

    def test_writes_one_json_line_with_the_full_schema(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"

        _gc_apply._append_removal_record(
            "/repo/wt-a", "feat/a", _STUB_HEAD, "merged to base", log_path=log_path
        )

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["schemaVersion"] == 1
        assert record["path"] == "/repo/wt-a"
        assert record["branch"] == "feat/a"
        assert record["head"] == _STUB_HEAD
        assert record["reason"] == "merged to base"
        assert isinstance(record["ts"], str) and record["ts"]

    def test_second_call_appends_rather_than_overwrites(self, tmp_path):
        log_path = tmp_path / "audit.jsonl"

        _gc_apply._append_removal_record(
            "/repo/wt-a", "feat/a", _STUB_HEAD, "merged to base", log_path=log_path
        )
        _gc_apply._append_removal_record(
            "/repo/wt-b", "feat/b", _STUB_HEAD, "fully pushed", log_path=log_path
        )

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["path"] == "/repo/wt-a"
        assert json.loads(lines[1])["path"] == "/repo/wt-b"

    def test_creates_missing_parent_directories(self, tmp_path):
        log_path = tmp_path / "nested" / "does-not-exist-yet" / "audit.jsonl"
        assert not log_path.parent.exists()

        _gc_apply._append_removal_record(
            "/repo/wt-a", "feat/a", _STUB_HEAD, "merged to base", log_path=log_path
        )

        assert log_path.exists()
        assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1

    def test_handles_a_worktree_with_no_branch_or_head(self, tmp_path):
        """A detached-HEAD or unreadable-HEAD worktree still gets a record."""
        log_path = tmp_path / "audit.jsonl"

        _gc_apply._append_removal_record(
            "/repo/wt-detached", None, None, "merged to base", log_path=log_path
        )

        record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert record["branch"] is None
        assert record["head"] is None


class TestApplyRemovalsAuditIntegration:
    """``apply_removals`` writes the audit record only for a removal it commits."""

    def test_successful_removal_is_recorded(self, tmp_path):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision(
                    "/repo/a", "feat/a", remove=True, reason="merged to base", head=_STUB_HEAD
                ),
            ],
        )
        log_path = tmp_path / "audit.jsonl"
        with patch("scripts.maintenance.gc_worktrees._gc_apply.remove_worktree"):
            _gc_apply.apply_removals(
                report, revalidate=_agrees(report), run_git=_forbidden_git, audit_log_path=log_path
            )

        record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert record == {
            "schemaVersion": 1,
            "ts": record["ts"],
            "path": "/repo/a",
            "branch": "feat/a",
            "head": _STUB_HEAD,
            "reason": "merged to base",
        }

    def test_failed_removal_is_not_recorded(self, tmp_path):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision(
                    "/repo/a", "feat/a", remove=True, reason="merged to base", head=_STUB_HEAD
                ),
            ],
        )
        log_path = tmp_path / "audit.jsonl"

        def _raise(_path: str, _run_git: object) -> None:
            raise RuntimeError("locked by index")

        with patch(
            "scripts.maintenance.gc_worktrees._gc_apply.remove_worktree", side_effect=_raise
        ):
            _gc_apply.apply_removals(
                report, revalidate=_agrees(report), run_git=_forbidden_git, audit_log_path=log_path
            )

        assert not log_path.exists()

    def test_kept_candidate_is_not_recorded(self, tmp_path):
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision("/repo/a", "feat/a", remove=False, reason="locked"),
            ],
        )
        log_path = tmp_path / "audit.jsonl"
        with patch("scripts.maintenance.gc_worktrees._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(
                report, revalidate=_agrees(report), run_git=_forbidden_git, audit_log_path=log_path
            )

        remove.assert_not_called()
        assert not log_path.exists()

    def test_no_audit_log_path_uses_the_resolver_for_the_main_worktree(self, tmp_path, monkeypatch):
        """Omitting ``audit_log_path`` resolves the log from the plan's main worktree."""
        seen: list[str] = []
        log_path = tmp_path / "resolved.jsonl"

        def _resolver(main_worktree: str):
            seen.append(main_worktree)
            return log_path

        monkeypatch.setattr("scripts.maintenance._gc_apply.audit_log_path_for", _resolver)
        report = _one_candidate_report()
        with patch("scripts.maintenance.gc_worktrees._gc_apply.remove_worktree"):
            _gc_apply.apply_removals(report, revalidate=_agrees(report), run_git=_forbidden_git)

        assert seen == [_MAIN]
        record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        assert record["path"] == "/repo/a"

    def test_unwritable_log_records_an_error_and_keeps_removing(self, tmp_path):
        """A failed audit write neither crashes the run nor hides the removal."""
        blocker = tmp_path / "not-a-directory"
        blocker.write_text("", encoding="utf-8")
        log_path = blocker / "audit.jsonl"
        report = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision("/repo/a", "feat/a", remove=True, reason="merged", head=_STUB_HEAD),
                Decision("/repo/b", "feat/b", remove=True, reason="merged", head=_STUB_HEAD),
            ],
        )
        with patch("scripts.maintenance.gc_worktrees._gc_apply.remove_worktree") as remove:
            _gc_apply.apply_removals(
                report, revalidate=_agrees(report), run_git=_forbidden_git, audit_log_path=log_path
            )

        assert remove.call_count == 2
        assert report.removed == ["/repo/a", "/repo/b"]
        assert len(report.remove_errors) == 2
        assert all("audit record was not written" in err for err in report.remove_errors)

    def test_removal_after_a_skipped_candidate_is_recorded(self, tmp_path):
        """A candidate the recheck drops is skipped; later removals still log."""
        planned = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision("/repo/a", "feat/a", remove=True, reason="merged", head=_STUB_HEAD),
                Decision("/repo/b", "feat/b", remove=True, reason="merged", head=_STUB_HEAD),
            ],
        )
        fresh = GcReport(
            timestamp="t",
            base_ref=_BASE,
            apply=True,
            main_worktree=_MAIN,
            decisions=[
                Decision("/repo/a", "feat/a", remove=False, reason="new commit"),
                Decision("/repo/b", "feat/b", remove=True, reason="merged", head=_STUB_HEAD),
            ],
        )
        log_path = tmp_path / "audit.jsonl"
        with patch("scripts.maintenance.gc_worktrees._gc_apply.remove_worktree"):
            _gc_apply.apply_removals(
                planned, revalidate=_agrees(fresh), run_git=_forbidden_git, audit_log_path=log_path
            )

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["path"] for line in lines] == ["/repo/b"]


class TestAuditLogPathFor:
    """The log lives under the main worktree, never the running checkout."""

    def test_resolves_under_the_main_worktree(self, tmp_path):
        main = tmp_path / "main"

        resolved = _real_audit_log_path_for(str(main))

        assert resolved == main / ".project-toolkit" / "metrics" / "gc-worktree-removals.jsonl"

    def test_does_not_depend_on_the_module_location(self, tmp_path):
        """Two main worktrees give two logs; the script's own checkout is not used."""
        first = _real_audit_log_path_for(str(tmp_path / "one"))
        second = _real_audit_log_path_for(str(tmp_path / "two"))

        assert first != second
        assert first.is_relative_to(tmp_path / "one")
        assert second.is_relative_to(tmp_path / "two")

    def test_suite_fixture_keeps_the_default_away_from_main(self):
        """The conftest patch never resolves under the report's main worktree."""
        resolved = _gc_apply.audit_log_path_for(_MAIN)

        assert not resolved.is_relative_to(_MAIN)


def _one_candidate_report() -> GcReport:
    return GcReport(
        timestamp="t",
        base_ref=_BASE,
        apply=True,
        main_worktree=_MAIN,
        decisions=[
            Decision("/repo/a", "feat/a", remove=True, reason="merged to base", head=_STUB_HEAD),
        ],
    )
