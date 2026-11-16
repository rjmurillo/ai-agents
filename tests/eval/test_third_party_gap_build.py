"""Tests for scripts/eval/_third_party_gap_build.py and build_third_party_gap_corpus.py.

The git seam is a callable over an argv tuple, dispatched on the command.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _third_party_gap_build as build  # noqa: E402
import _third_party_review_findings as findings  # noqa: E402

REVIEWED, FIX, BASE, MB = "a" * 40, "f" * 40, "b" * 40, "c" * 40


def comment(login: str, body: str = "x") -> dict[str, Any]:
    return {
        "author": {"login": login},
        "body": body,
        "originalCommit": {"oid": REVIEWED},
        "url": "u",
    }


def thread(*comments: dict[str, Any], resolved: bool = True) -> dict[str, Any]:
    return {"path": "a.py", "originalLine": 4, "isResolved": resolved, "comments": list(comments)}


class TestText:
    def test_clean_drops_comments_details_and_tags(self) -> None:
        body = "<!-- id -->**Bug**\n\n\n<details>long</details><b>x</b> &amp; y"

        assert build.clean(body) == "**Bug**\nx & y"

    def test_learned_rule_is_read_up_to_reviewed_by(self) -> None:
        body = "text\nTriggered by learned rule: Tests using symlinks must skip\nReviewed by Bugbot"

        assert build.learned_rule(body) == "Tests using symlinks must skip"

    def test_no_learned_rule_is_none(self) -> None:
        assert build.learned_rule("plain finding") is None


class TestDisposition:
    @pytest.mark.parametrize(
        ("body", "replies", "resolved", "expected"),
        [
            ("b", ["Fixed in abc1234."], False, "accepted"),
            ("b", ["Agreed, done."], False, "accepted"),
            ("✅ Addressed in commit abc", [], False, "accepted"),
            ("b", ["False positive: generated copy."], True, "rejected"),
            ("b", [], True, "resolved-silent"),
            ("b", [], False, "unclear"),
            ("b", ["Thanks, looking."], True, "unclear"),
        ],
    )
    def test_reply_shapes(
        self, body: str, replies: list[str], resolved: bool, expected: str
    ) -> None:
        assert build.disposition(body, replies, resolved) == expected


class TestBotThreads:
    def test_ids_count_only_bot_opened_threads_and_bot_replies_are_ignored(self) -> None:
        prs = [
            {
                "number": 9,
                "reviewThreads": [
                    thread(comment("rjmurillo")),
                    thread(
                        comment("cursor"),
                        comment("coderabbitai"),
                        comment("rjmurillo", "Fixed in abc1234"),
                    ),
                    thread(comment("semgrep-code-acme")),
                ],
            }
        ]

        rows = build.bot_threads(prs)

        assert [(r["id"], r["bot"]) for r in rows] == [("T0001", "cursor"), ("T0002", "semgrep")]
        assert rows[0]["first_reply"] == "Fixed in abc1234"
        assert rows[0]["disposition"] == "accepted"


class TestFindingsBotNames:
    @pytest.mark.parametrize(
        ("login", "name"),
        [("semgrep-code-rjmurillo", "semgrep"), ("github-advanced-security[bot]", "codeql")],
    )
    def test_scanner_logins_map(self, login: str, name: str) -> None:
        assert findings.bot_name(login) == name


def fake_git(touched: str = "a.py", ancestor: bool = True, resolves: bool = True) -> Any:
    def git(args: tuple[str, ...]) -> str | None:
        match args:
            case ("rev-parse", *_):
                return FIX + "\n" if resolves else None
            case ("cat-file", *_):
                return ""
            case ("show", "--format=", "--name-only", _):
                return touched + "\n"
            case ("merge-base", "--is-ancestor", *_):
                return "" if ancestor else None
            case ("merge-base", *_):
                return MB + "\n"
            case ("diff", "--name-only", *_):
                return "a.py\n"
            case ("diff", *_):
                return "diff text"
        raise AssertionError(f"unexpected git call {args}")

    return git


def row(reply: str = "Fixed in abc1234.") -> dict[str, Any]:
    return {
        "id": "T0001",
        "pr": 5,
        "path": "a.py",
        "line": 4,
        "commit": REVIEWED,
        "first_reply": reply,
    }


class TestAdmit:
    def test_admitted_row_carries_fix_merge_base_and_diff_facts(self) -> None:
        outcome, kept = build.admit(row(), BASE, fake_git())

        assert outcome == "admitted"
        assert kept is not None
        assert (kept["fix"], kept["merge_base"], kept["path_in_diff"]) == (FIX, MB, True)
        assert kept["diff_chars_all"] == len("diff text")

    @pytest.mark.parametrize(
        ("reply", "git", "outcome"),
        [
            ("Looks right to me", fake_git(), "no_sha"),
            ("Fixed in abc1234", fake_git(resolves=False), "fix_unresolved"),
            ("Fixed in abc1234", fake_git(touched="b.py"), "fix_misses_path"),
            ("Fixed in abc1234", fake_git(ancestor=False), "fix_not_descendant"),
        ],
    )
    def test_each_refusal(self, reply: str, git: Any, outcome: str) -> None:
        assert build.admit(row(reply), BASE, git) == (outcome, None)


class TestSplitAndCorpora:
    def test_cutoff_puts_the_newest_share_in_heldout(self) -> None:
        assert build.heldout_cutoff([1, 1, 2, 3, 4, 5, 6, 7, 8, 9]) == 6

    def test_cutoff_refuses_an_empty_set(self) -> None:
        with pytest.raises(ValueError, match="no admitted"):
            build.heldout_cutoff([])

    def test_finding_rows_need_a_label_for_every_row(self) -> None:
        with pytest.raises(ValueError, match="no label"):
            build.finding_rows([{"id": "T0001", "pr": 1}], {})

    def test_finding_rows_sort_by_pr_then_id(self) -> None:
        admitted = [{"id": "T0002", "pr": 2}, {"id": "T0003", "pr": 1}]
        labels = {"T0002": {"theme": "a"}, "T0003": {"theme": "b"}}

        rows = build.finding_rows(admitted, labels)

        assert [r["id"] for r in rows] == ["T0003", "T0002"]
        assert list(rows[0]) == list(build.FINDING_KEYS)

    def test_replay_groups_by_revision_filters_and_excludes(self) -> None:
        base = {
            "bot": "devin", "path": "a.py", "fix": FIX, "defect_class": "logic-error",
            "theme": "t", "context_needed": "diff-local", "summary": "s", "split": "derive",
            "merge_base": MB, "path_in_diff": True, "diff_chars_all": 10, "line": 3,
        }  # fmt: skip
        rows = [
            {**base, "id": "T0001", "pr": 1, "commit": REVIEWED},
            {**base, "id": "T0002", "pr": 1, "commit": REVIEWED},
            {**base, "id": "T0003", "pr": 2, "commit": REVIEWED, "path_in_diff": False},
            {**base, "id": "T0004", "pr": 3, "commit": REVIEWED, "diff_chars_all": 10**6},
            {**base, "id": "T0005", "pr": 4, "commit": REVIEWED},
        ]

        revisions = build.replay_revisions(rows, {1: "one"}, {"TG002"})

        assert [(r["id"], len(r["defects"]), r["title"]) for r in revisions] == [
            ("TG001", 2, "one")
        ]

    def test_io_rows_keep_the_three_rules_and_fixed_or_silent_threads(self) -> None:
        threads = [
            {"id": "T1", "pr": 5, "learned_rule": "Tests using symlinks must skip",
             "disposition": "accepted", "line": 4, "commit": REVIEWED, "path": "t.py", "url": "u"},
            {"id": "T2", "pr": 5, "learned_rule": "Tests using symlinks must skip",
             "disposition": "rejected", "line": 4, "commit": REVIEWED, "path": "t.py", "url": "u"},
            {"id": "T3", "pr": 5, "learned_rule": "Some other rule",
             "disposition": "accepted", "line": 4, "commit": REVIEWED, "path": "t.py", "url": "u"},
        ]  # fmt: skip

        rows = build.io_rows(threads, {5: "h" * 40}, {5: BASE}, 5, fake_git())

        assert [(r["thread"], r["rule"], r["split"], r["merge_base"]) for r in rows] == [
            ("T1", "unguarded-symlink", "heldout", MB)
        ]


def _load_cli() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_third_party_gap_corpus", EVAL_DIR / "build_third_party_gap_corpus.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestCli:
    def test_one_record_per_line_round_trips(self) -> None:
        cli = _load_cli()
        obj = {"schema_version": 1, "selection": {"rule": "r"}, "rows": [{"a": 1}, {"b": "é"}]}

        text = cli.one_record_per_line(obj, "rows")

        assert json.loads(text) == obj
        assert len(text.splitlines()) == 8

    def test_dump_with_no_admitted_finding_exits_2(self, tmp_path: Path) -> None:
        cli = _load_cli()
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")

        assert cli.main(["--dump", str(dump), "--labels", str(labels), "--check"]) == 2

    def test_unreadable_dump_exits_2(self, tmp_path: Path) -> None:
        assert _load_cli().main(["--dump", str(tmp_path / "none.json")]) == 2

    def test_check_reports_a_differing_file_with_exit_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cli = _load_cli()
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
        monkeypatch.setattr(cli, "build_all", lambda _d, _l: {})
        monkeypatch.setattr(cli, "render", lambda _b: {"findings.jsonl": "new\n"})
        (tmp_path / "findings.jsonl").write_text("old\n", encoding="utf-8")
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")
        argv = ["--dump", str(dump), "--labels", str(labels), "--out-dir", str(tmp_path), "--check"]

        assert cli.main(argv) == 1
        assert (tmp_path / "findings.jsonl").read_text(encoding="utf-8") == "old\n"

    def test_check_with_matching_files_exits_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cli = _load_cli()
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
        monkeypatch.setattr(cli, "build_all", lambda _d, _l: {})
        monkeypatch.setattr(cli, "render", lambda _b: {"findings.jsonl": "same\n"})
        (tmp_path / "findings.jsonl").write_text("same\n", encoding="utf-8")
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")
        argv = ["--dump", str(dump), "--labels", str(labels), "--out-dir", str(tmp_path), "--check"]

        assert cli.main(argv) == 0
