"""Tests for scripts/eval/_third_party_gap_build.py and build_third_party_gap_corpus.py.

The git seam is a callable over an argv tuple, dispatched on the command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.eval._third_party_gap_test_support import eval_path, load_script

with eval_path():
    import _third_party_gap_build as build
    import _third_party_review_findings as findings

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
            ("b", ["Confirmed false positive: this is intentional."], True, "rejected"),
            ("✅ Addressed in commit abc", ["Not changed in this PR."], True, "rejected"),
            ("b", ["Fixed in abc1234; the other path already had it."], True, "accepted"),
            ("b", ["Applied in abc1234; the other path already had it."], True, "accepted"),
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
                "author": {"login": "rjmurillo"},
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

    def test_a_reply_from_someone_other_than_the_author_does_not_accept(self) -> None:
        prs = [
            {
                "number": 9,
                "author": {"login": "rjmurillo"},
                "reviewThreads": [
                    thread(comment("cursor"), comment("someone-else", "Fixed in abc1234"))
                ],
            }
        ]

        (row,) = build.bot_threads(prs)

        assert (row["first_reply"], row["disposition"]) == ("", "unclear")

    def test_a_rejection_from_someone_other_than_the_author_still_rejects(self) -> None:
        prs = [
            {
                "number": 9,
                "author": {"login": "rjmurillo"},
                "reviewThreads": [
                    thread(comment("cursor"), comment("someone-else", "This is a false positive"))
                ],
            }
        ]

        (row,) = build.bot_threads(prs)

        assert row["disposition"] == "rejected"


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
            case ("show", "--format=", "--name-only", "-z", _):
                return touched + "\0"
            case ("merge-base", "--is-ancestor", *_):
                return "" if ancestor else None
            case ("merge-base", *_):
                return MB + "\n"
            case ("diff", "--name-only", "-z", *_):
                return touched + "\0"
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

    @pytest.mark.parametrize("failing", [("show", "--format="), ("diff", "--name-only"), ("diff",)])
    def test_a_failed_git_read_on_existing_commits_raises(self, failing: tuple[str, ...]) -> None:
        inner = fake_git()

        def git(args: tuple[str, ...]) -> str | None:
            # Fail only the read named by `failing`; "diff" alone means the patch read.
            hit = args[: len(failing)] == failing and (failing != ("diff",) or "-z" not in args)
            return None if hit else inner(args)

        with pytest.raises(RuntimeError, match="failed on commits that exist"):
            build.admit(row(), BASE, git)

    def test_a_path_with_a_space_is_matched_whole(self) -> None:
        spaced = row() | {"path": "scripts/my tool.py"}

        outcome, kept = build.admit(spaced, BASE, fake_git(touched="scripts/my tool.py"))

        assert outcome == "admitted"
        assert kept is not None and kept["path_in_diff"]


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
        admitted = [{"id": "T0002", "pr": 2, "url": "u2"}, {"id": "T0003", "pr": 1, "url": "u3"}]
        labels = {"T0002": {"theme": "a", "url": "u2"}, "T0003": {"theme": "b", "url": "u3"}}

        rows = build.finding_rows(admitted, labels)

        assert [r["id"] for r in rows] == ["T0003", "T0002"]
        assert list(rows[0]) == list(build.FINDING_KEYS)

    @pytest.mark.parametrize(
        ("thread_url", "label_url"), [("u2", "u-other"), ("u2", None), (None, None), ("", "")]
    )
    def test_a_label_not_bound_to_its_thread_is_refused(
        self, thread_url: str | None, label_url: str | None
    ) -> None:
        admitted = [{"id": "T0002", "pr": 2, "url": thread_url}]
        labels = {"T0002": {"theme": "a", "url": label_url}}

        with pytest.raises(ValueError, match="another thread"):
            build.finding_rows(admitted, labels)

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

        revisions, excluded = build.replay_revisions(rows, {1: "one"}, frozenset({(4, REVIEWED)}))

        assert [(r["id"], len(r["defects"]), r["title"]) for r in revisions] == [
            ("TG001", 2, "one")
        ]
        assert excluded == ["TG002"]

    def test_an_exclusion_that_matches_no_revision_raises(self) -> None:
        row = {
            "bot": "devin", "path": "a.py", "fix": FIX, "defect_class": "logic-error",
            "theme": "t", "context_needed": "diff-local", "summary": "s", "split": "derive",
            "merge_base": MB, "path_in_diff": True, "diff_chars_all": 10, "line": 3,
            "id": "T0001", "pr": 1, "commit": REVIEWED,
        }  # fmt: skip

        with pytest.raises(ValueError, match="not in the replay set"):
            build.replay_revisions([row], {}, frozenset({(9, REVIEWED)}))

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
    return load_script("build_third_party_gap_corpus")


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


class TestCliGitFailures:
    @pytest.fixture
    def cli(self) -> Any:
        return _load_cli()

    def test_stats_exits_3_when_git_log_fails(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
        built = {"threads": [], "findings": [{"merge_base": "a" * 40, "commit": "b" * 40}]}
        monkeypatch.setattr(cli, "build_all", lambda _d, _l: built)
        monkeypatch.setattr(cli, "render", lambda _b: {})
        monkeypatch.setattr(cli, "git_run", lambda _args: None)
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")

        code = cli.main(["--dump", str(dump), "--labels", str(labels), "--stats"])

        assert code == 3

    def test_precision_raises_when_a_listed_path_cannot_be_read(
        self, cli: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def git(args: tuple[str, ...]) -> str | None:
            return None if args[0] == "show" else "c" * 40 + "\n"

        monkeypatch.setattr(cli, "git_run", git)
        monkeypatch.setattr(cli.io_check, "added_line_numbers", lambda _r, _b, _h: {"a.py": {1}})
        prs = [{"number": 9, "state": "MERGED", "headRefOid": "h" * 40, "baseRefOid": "b" * 40}]

        with pytest.raises(ValueError, match="failed for a path the diff listed"):
            cli.precision(prs, 1)

    def test_git_run_raises_when_git_times_out(
        self, cli: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        def stalled(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired("git", 120)

        monkeypatch.setattr(subprocess, "run", stalled)

        with pytest.raises(RuntimeError, match="could not run"):
            cli.git_run(("log",))

    def test_stats_exits_3_when_merge_base_times_out(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import subprocess

        pr = {"number": 9, "state": "MERGED", "headRefOid": "h" * 40, "baseRefOid": "b" * 40}
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": [pr]}), encoding="utf-8")
        built = {"threads": [], "findings": [], "funnel": {}, "cutoff": 1}
        monkeypatch.setattr(cli, "build_all", lambda _d, _l: built)
        monkeypatch.setattr(cli, "render", lambda _b: {})

        def stalled(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired("git", 120)

        monkeypatch.setattr(subprocess, "run", stalled)
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")

        code = cli.main(["--dump", str(dump), "--labels", str(labels), "--stats"])

        assert code == 3

    def test_build_that_cannot_run_git_exits_3(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fail(_d: object, _l: object) -> None:
            raise RuntimeError("git cat-file could not run")

        monkeypatch.setattr(cli, "build_all", fail)
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")

        assert cli.main(["--dump", str(dump), "--labels", str(labels)]) == 3

    def test_stats_alone_writes_nothing(
        self, cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dump = tmp_path / "dump.json"
        dump.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
        monkeypatch.setattr(cli, "build_all", lambda _d, _l: {})
        monkeypatch.setattr(cli, "render", lambda _b: {"findings.jsonl": "new\n"})
        monkeypatch.setattr(cli, "stats", lambda _d, _b: {})
        labels = tmp_path / "labels.jsonl"
        labels.write_text("", encoding="utf-8")
        argv = ["--dump", str(dump), "--labels", str(labels), "--out-dir", str(tmp_path), "--stats"]

        code = cli.main(argv)

        assert code == 0
        assert not (tmp_path / "findings.jsonl").exists()


class TestWriteGuard:
    def test_write_under_the_checkout_from_outside_it_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cli = _load_cli()
        out = cli.REPO_ROOT / "evals" / "does-not-exist"
        monkeypatch.chdir(tmp_path)

        code = cli.write({"findings.jsonl": "x\n"}, out, {})

        assert code == 2
        assert not out.exists()

    def test_write_to_a_directory_outside_the_checkout_is_allowed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cli = _load_cli()
        monkeypatch.chdir(tmp_path)

        code = cli.write({"findings.jsonl": "x\n"}, tmp_path, {})

        assert code == 0
        assert (tmp_path / "findings.jsonl").read_text(encoding="utf-8") == "x\n"

    def test_write_under_the_checkout_from_inside_it_is_allowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil
        import uuid

        cli = _load_cli()
        out = cli.REPO_ROOT / ".pytest_tmp" / f"corpus-write-{uuid.uuid4().hex}"
        out.mkdir(parents=True)
        monkeypatch.chdir(cli.REPO_ROOT)
        try:
            code = cli.write({"findings.jsonl": "x\n"}, out, {})

            assert code == 0
            assert (out / "findings.jsonl").read_text(encoding="utf-8") == "x\n"
        finally:
            shutil.rmtree(out)
