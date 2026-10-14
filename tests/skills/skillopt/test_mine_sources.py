"""Tests for Copilot ingestion, source discovery, and no-source degradation."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import _mine_sources as msrc
import mine_sessions as ms
import pytest
from skillopt_helpers import (
    Capture,
    make_copilot_db,
    skill_use,
    write_handoff,
    write_jsonl,
)


class TestPathHelpers:
    def test_default_roots(self, home: Path) -> None:
        assert msrc._default_roots() == [home / ".claude" / "projects"]

    def test_default_copilot_path(self, home: Path) -> None:
        assert msrc._default_copilot_path() == home / ".copilot" / "session-store.db"

    def test_gather_paths_file_and_dir(self, tmp_path: Path) -> None:
        f = tmp_path / "a.jsonl"
        f.write_text("{}", encoding="utf-8")
        sub = tmp_path / "d"
        sub.mkdir()
        (sub / "b.jsonl").write_text("{}", encoding="utf-8")
        got = msrc._gather_paths([f, sub, tmp_path / "missing"])
        assert {p.name for p in got} == {"a.jsonl", "b.jsonl"}

    def test_repo_skills(self, tmp_path: Path) -> None:
        (tmp_path / "s1").mkdir()
        (tmp_path / "s2").mkdir()
        (tmp_path / "file.md").write_text("x", encoding="utf-8")
        assert msrc._repo_skills(tmp_path) == {"s1", "s2"}

    def test_repo_skills_missing_dir(self, tmp_path: Path) -> None:
        assert msrc._repo_skills(tmp_path / "nope") == set()


class TestCopilotIngestion:
    def test_user_and_skill_records(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(
            db,
            [
                (1, 0, "optimize build", "sure, running skill(build) now"),
                (1, 1, "that's wrong", "fixing"),
            ],
        )
        recs = list(ms.iter_copilot_records(db))
        assert ms.user_text(recs[0]) == "optimize build"
        assert ms.extract_skill_invocations(recs[1]) == ["build"]
        assert ms.user_text(recs[2]) == "that's wrong"

    def test_turn_order_follows_session_and_index(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 1, "second", None), (1, 0, "first", None)])
        assert [ms.user_text(r) for r in ms.iter_copilot_records(db)] == ["first", "second"]

    def test_boundary_when_session_id_changes(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        rows = [(1, 0, "a1", None), (1, 1, "a2", None), (2, 0, "b1", None)]
        make_copilot_db(db, rows)
        types = [r["type"] for r in ms.iter_copilot_records(db)]
        assert types == ["user", "user", "session-boundary", "user"]

    def test_correction_does_not_cross_copilot_sessions(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "go", "skill(ship)"), (2, 0, "that's wrong", "ok")])
        stats = ms.aggregate(ms.iter_copilot_records(db), window=5)
        assert stats["ship"] == {"invocations": 1, "corrections": 0}

    def test_aggregate_over_copilot(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "do it", "skill(ship) running"), (1, 1, "that's wrong", "ok")])
        assert ms.aggregate(ms.iter_copilot_records(db))["ship"] == {
            "invocations": 1,
            "corrections": 1,
        }

    def test_empty_or_blank_messages_skipped(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "   ", "no skill here"), (1, 1, None, None)])
        assert list(ms.iter_copilot_records(db)) == []

    def test_missing_db_yields_nothing_and_is_not_created(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.db"
        assert list(ms.iter_copilot_records(missing)) == []
        assert not missing.exists()

    def test_directory_path_yields_nothing(self, tmp_path: Path) -> None:
        assert list(ms.iter_copilot_records(tmp_path)) == []

    def test_db_without_turns_table_yields_nothing(self, tmp_path: Path) -> None:
        db = tmp_path / "bad.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE other (x INT)")
        con.commit()
        con.close()
        assert list(ms.iter_copilot_records(db)) == []

    def test_non_sqlite_file_yields_nothing(self, tmp_path: Path) -> None:
        db = tmp_path / "garbage.db"
        db.write_bytes(b"this is not a database" * 50)
        assert list(ms.iter_copilot_records(db)) == []

    def test_connect_error_yields_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = tmp_path / "s.db"
        db.write_bytes(b"x")

        def boom(*_a: object, **_k: object) -> None:
            raise sqlite3.OperationalError("locked")

        monkeypatch.setattr(sqlite3, "connect", boom)
        assert list(ms.iter_copilot_records(db)) == []

    def test_uri_is_built_with_as_uri_for_awkward_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        awkward = tmp_path / "my dir #1 ?x"
        awkward.mkdir()
        db = awkward / "s.db"
        make_copilot_db(db, [(1, 0, "hello", "skill(qa)")])
        seen: list[str] = []
        real_connect = sqlite3.connect

        def spy(target: str, **kwargs: Any) -> sqlite3.Connection:
            seen.append(target)
            return real_connect(target, **kwargs)

        monkeypatch.setattr(sqlite3, "connect", spy)
        recs = list(ms.iter_copilot_records(db))
        assert seen == [db.resolve().as_uri() + "?mode=ro"]
        assert seen[0].startswith("file:///")
        assert " " not in seen[0]
        assert ms.user_text(recs[0]) == "hello"

    def test_connection_is_read_only(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "hello", None)])
        before = db.read_bytes()
        list(ms.iter_copilot_records(db))
        assert db.read_bytes() == before


class TestSources:
    def test_sources_lists_defaults_unavailable(self, home: Path, capsys: Capture) -> None:
        assert ms.main(["sources"]) == 0
        rows = json.loads(capsys.readouterr().out)
        assert rows == [
            {
                "source": "claude",
                "path": str((home / ".claude" / "projects").resolve()),
                "available": False,
            },
            {
                "source": "copilot",
                "path": str((home / ".copilot" / "session-store.db").resolve()),
                "available": False,
            },
        ]

    def test_sources_reports_available_defaults(self, home: Path, capsys: Capture) -> None:
        (home / ".claude" / "projects").mkdir(parents=True)
        (home / ".copilot").mkdir()
        (home / ".copilot" / "session-store.db").write_bytes(b"x")
        assert ms.main(["sources"]) == 0
        assert [r["available"] for r in json.loads(capsys.readouterr().out)] == [True, True]

    def test_sources_honors_overrides_and_repeatable_root(
        self, home: Path, tmp_path: Path, capsys: Capture
    ) -> None:
        a = tmp_path / "a.jsonl"
        a.write_text("{}", encoding="utf-8")
        d = tmp_path / "dir"
        d.mkdir()
        db = tmp_path / "x.db"
        argv = [
            "sources",
            "--root",
            str(a),
            "--root",
            str(d),
            "--root",
            str(tmp_path / "gone"),
            "--copilot",
            str(db),
        ]
        assert ms.main(argv) == 0
        rows = json.loads(capsys.readouterr().out)
        assert [(r["source"], r["available"]) for r in rows] == [
            ("claude", True),
            ("claude", True),
            ("claude", False),
            ("copilot", False),
        ]
        assert rows[-1]["path"] == str(db.resolve())

    def test_unavailable_source_is_skipped_not_an_error(self, home: Path, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("review")])
        ns = argparse.Namespace(no_claude=False, no_copilot=False, copilot=None, root=[str(f)])
        assert "review" in ms.aggregate(msrc._source_records(ns))

    def test_source_records_no_claude_only_copilot(self, tmp_path: Path) -> None:
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "go", "skill(qa) running")])
        ns = argparse.Namespace(no_claude=True, no_copilot=False, copilot=str(db), root=None)
        assert "qa" in ms.aggregate(msrc._source_records(ns))

    def test_source_records_no_copilot_only_claude(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("review")])
        ns = argparse.Namespace(no_claude=False, no_copilot=True, copilot=None, root=[str(f)])
        assert "review" in ms.aggregate(msrc._source_records(ns))

    def test_both_sources_pooled(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("review")])
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "go", "skill(qa)")])
        ns = argparse.Namespace(no_claude=False, no_copilot=False, copilot=str(db), root=[str(f)])
        assert set(ms.aggregate(msrc._source_records(ns))) == {"review", "qa"}

    def test_sources_are_separated_by_a_boundary(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("review")])
        db = tmp_path / "s.db"
        make_copilot_db(db, [(1, 0, "that's wrong", None)])
        ns = argparse.Namespace(no_claude=False, no_copilot=False, copilot=str(db), root=[str(f)])
        stats = ms.aggregate(msrc._source_records(ns), window=5)
        assert stats["review"]["corrections"] == 0


class TestNoSourceDegradation:
    def test_rank_empty_with_note(self, home: Path, capsys: Capture) -> None:
        assert ms.main(["rank"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []
        assert "no session source available" in captured.err

    def test_tasks_empty_with_note(self, home: Path, capsys: Capture) -> None:
        assert ms.main(["tasks", "--skill", "x"]) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"skill": "x", "count": 0, "tasks": []}
        assert "no session source available" in captured.err

    def test_collect_empty_with_note(self, home: Path, tmp_path: Path, capsys: Capture) -> None:
        out = tmp_path / "base.json"
        assert ms.main(["collect", "--out", str(out), "--host", "h"]) == 0
        assert "no session source available" in capsys.readouterr().err
        doc = json.loads(out.read_text(encoding="utf-8"))
        assert doc == {"host": "h", "skill_count": 0, "stats": {}}

    def test_both_no_flags_means_no_source(self, home: Path, capsys: Capture) -> None:
        assert ms.main(["rank", "--no-claude", "--no-copilot"]) == 0
        assert "no session source available" in capsys.readouterr().err

    def test_available_source_prints_no_note(
        self, home: Path, tmp_path: Path, capsys: Capture
    ) -> None:
        f = tmp_path / "t.jsonl"
        write_jsonl(f, [skill_use("a")])
        assert ms.main(["rank", "--root", str(f)]) == 0
        assert "no session source" not in capsys.readouterr().err

    def test_patterns_bypass_the_note(self, home: Path, tmp_path: Path, capsys: Capture) -> None:
        handoff = tmp_path / "p.json"
        write_handoff(handoff)
        assert ms.main(["rank", "--patterns", str(handoff)]) == 0
        assert "no session source" not in capsys.readouterr().err
