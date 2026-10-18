# taste-lint: ignore file-size, one suite owns the temp-repo fixtures for both subcommands.
"""Tests for bootstrap_mine.py: candidate mining and the claims checker."""

from __future__ import annotations

import importlib.util
import json
import runpy
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from bootstrap_helpers import run_git, symlink_or_skip, write

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
    / "bootstrap_mine.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bootstrap_mine", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bootstrap_mine"] = module
    spec.loader.exec_module(module)
    return module


mine = _load()
Result = tuple[int, dict[str, Any]]


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> Result:
    """Call main() in process; return the exit code and the parsed JSON on stdout."""
    code = mine.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def commit(repo: Path, subject: str, files: dict[str, str] | None = None, body: str | None = None):
    for rel, text in (files or {}).items():
        write(repo, rel, text)
    run_git(repo, "add", "-A")
    extra = ["-m", body] if body else []
    run_git(repo, "commit", "-q", "--allow-empty", "-m", subject, *extra)


def cand(capsys, repo: Path, *extra: str) -> Result:
    return run(capsys, "candidates", "--repo", str(repo), *extra)


def churn_of(payload: dict[str, Any]) -> dict[str, int]:
    return {row["path"]: row["commits"] for row in payload["churn"]}


def todos_of(payload: dict[str, Any]) -> dict[str, int]:
    return {row["path"]: row["todos"] for row in payload["todo_hotspots"]}


# ------------------------------------------------------------------ reverts


def test_revert_subject_rule_alone(capsys, repo):
    commit(repo, 'Revert "feat: add widget"')

    code, payload = cand(capsys, repo)

    assert code == 0
    assert [r["rule"] for r in payload["reverts"]] == [["subject"]]
    assert payload["reverts"][0]["reverted"] == []


def test_revert_conventional_rule_alone_with_scope_bang_and_case(capsys, repo):
    commit(repo, "FIX(api)!: Revert the bad merge")

    _, payload = cand(capsys, repo)

    assert [r["rule"] for r in payload["reverts"]] == [["conventional"]]


def test_revert_conventional_rule_without_scope(capsys, repo):
    commit(repo, "chore: revert dependency bump")

    _, payload = cand(capsys, repo)

    assert [r["rule"] for r in payload["reverts"]] == [["conventional"]]


def test_revert_body_rule_alone_lists_full_reverted_sha(capsys, repo):
    full = "ab" * 20
    commit(repo, "chore: undo the thing", body=f"Why\nThis reverts commit {full}.")

    _, payload = cand(capsys, repo)

    assert [r["rule"] for r in payload["reverts"]] == [["body"]]
    assert payload["reverts"][0]["reverted"] == [full]


def test_revert_body_rule_accepts_seven_hex_and_lowercases(capsys, repo):
    commit(repo, "chore: undo", body="This reverts commit ABCDEF1")

    _, payload = cand(capsys, repo)

    assert payload["reverts"][0]["reverted"] == ["abcdef1"]


def test_revert_rules_combine(capsys, repo):
    commit(repo, 'Revert "x"', body="This reverts commit abcdef1234")

    _, payload = cand(capsys, repo)

    assert payload["reverts"][0]["rule"] == ["subject", "body"]


@pytest.mark.parametrize(
    "subject",
    [
        "feat: add revert button",
        "Reverted flag handling",
        "fix: reverted the flag",
        "docs: explain how to revert",
        "chore: prevent regressions",
    ],
)
def test_subject_with_revert_elsewhere_is_not_a_revert(capsys, repo, subject):
    commit(repo, subject)

    _, payload = cand(capsys, repo)

    assert payload["reverts"] == []


@pytest.mark.parametrize(
    "body",
    [
        "This reverts commit abcdef",
        f"This reverts commit {'a' * 65}",
        "Note: This reverts commit abcdef1234",
        "this reverts commit abcdef1234",
    ],
)
def test_body_that_does_not_match_the_revert_line_is_ignored(capsys, repo, body):
    commit(repo, "chore: tidy", body=body)

    _, payload = cand(capsys, repo)

    assert payload["reverts"] == []


def test_revert_item_has_full_sha_short_and_iso_date(capsys, repo):
    commit(repo, 'Revert "y"')

    _, payload = cand(capsys, repo)

    item = payload["reverts"][0]
    assert item["sha"] == run_git(repo, "rev-parse", "HEAD").strip()
    assert item["short"] == item["sha"][:9]
    assert item["subject"] == 'Revert "y"'
    datetime.fromisoformat(item["date"])


def test_max_commits_bounds_reverts_and_examined(capsys, repo):
    commit(repo, 'Revert "old"')
    commit(repo, "feat: one")
    commit(repo, "feat: two")

    _, payload = cand(capsys, repo, "--max-commits", "2")

    assert payload["reverts"] == []
    assert payload["examined"]["commits"] == 2


def test_no_reverts_reports_empty_list_and_commit_count(capsys, repo):
    code, payload = cand(capsys, repo)

    assert code == 0
    assert payload["reverts"] == []
    assert payload["examined"]["commits"] == 1


def test_rev_names_the_history_that_is_read(capsys, repo):
    commit(repo, 'Revert "later"')

    _, payload = cand(capsys, repo, "--rev", "HEAD~1")

    assert payload["reverts"] == []
    assert payload["sha"] == run_git(repo, "rev-parse", "HEAD~1").strip()


def test_other_branch_history_is_not_read(capsys, repo):
    main_branch = run_git(repo, "branch", "--show-current").strip()
    run_git(repo, "checkout", "-q", "-b", "side")
    commit(repo, 'Revert "on side"')
    run_git(repo, "checkout", "-q", main_branch)

    _, payload = cand(capsys, repo)

    assert payload["reverts"] == []


# ------------------------------------------------------------------ churn

BASELINE = ("--exclude", "README.md", "--exclude", ".claude/")


def ranked_repo(repo: Path) -> None:
    commit(repo, "c1", {"a": "1", "b": "1", "c": "1", "d": "1"})
    commit(repo, "c2", {"a": "2", "b": "2", "c": "2"})
    commit(repo, "c3", {"a": "3"})


def test_churn_counts_commits_per_file_sorted(capsys, repo):
    ranked_repo(repo)

    _, payload = cand(capsys, repo, *BASELINE)

    assert list(churn_of(payload).items()) == [("a", 3), ("b", 2), ("c", 2), ("d", 1)]


def test_churn_includes_files_tied_with_the_last_kept_count(capsys, repo):
    ranked_repo(repo)

    _, payload = cand(capsys, repo, *BASELINE, "--top", "2")

    assert list(churn_of(payload)) == ["a", "b", "c"]
    assert payload["churn_tie_at_cutoff"] is True


def test_churn_no_tie_flag_when_the_cutoff_is_clean(capsys, repo):
    ranked_repo(repo)

    _, payload = cand(capsys, repo, *BASELINE, "--top", "3")

    assert list(churn_of(payload)) == ["a", "b", "c"]
    assert payload["churn_tie_at_cutoff"] is False


def test_churn_top_larger_than_files_returns_all_without_tie(capsys, repo):
    ranked_repo(repo)

    _, payload = cand(capsys, repo, *BASELINE, "--top", "50")

    assert len(payload["churn"]) == 4
    assert payload["churn_tie_at_cutoff"] is False


def test_churn_window_limits_to_recent_commits(capsys, repo):
    ranked_repo(repo)

    _, payload = cand(capsys, repo, *BASELINE, "--churn-window", "1")

    assert churn_of(payload) == {"a": 1}
    assert payload["examined"]["churn_commits"] == 1


def test_churn_exclude_prefixes_drop_paths(capsys, repo):
    commit(repo, "c1", {"src/x.py": "1", "src/y.py": "1", "lib/z.py": "1"})

    _, payload = cand(capsys, repo, *BASELINE, "--exclude", "src/")

    assert churn_of(payload) == {"lib/z.py": 1}


def test_churn_counts_empty_commits_as_examined(capsys, repo):
    commit(repo, "empty")

    _, payload = cand(capsys, repo)

    assert payload["examined"]["churn_commits"] == 2


def test_everything_excluded_prints_zero_counts(capsys, repo):
    code, payload = cand(capsys, repo, "--exclude", "")

    assert code == 0
    assert payload["churn"] == []
    assert payload["todo_hotspots"] == []
    assert payload["examined"]["files_grepped"] == 0
    assert payload["examined"]["churn_commits"] == 1


def test_paths_with_spaces_survive_churn(capsys, repo):
    commit(repo, "c1", {"dir/a b.txt": "1"})

    _, payload = cand(capsys, repo)

    assert churn_of(payload)["dir/a b.txt"] == 1


# ------------------------------------------------------------------ todos


def todo_repo(repo: Path) -> None:
    write(repo, "src/a.py", "TODO one\nFIXME two\nboth TODO FIXME\nXXX\nplain\nHACK\n")
    write(repo, "src/b.py", "x = 1  # FIXME\n")
    write(repo, "src/c.py", "TODOS and XXXL and unhacked\n")
    write(repo, "vendor/v.py", "TODO\n" * 9)
    Path(repo / "bin.dat").write_bytes(b"\0TODO\nTODO\n")
    commit(repo, "add todo files")


def test_todo_counts_matching_lines_with_word_boundaries(capsys, repo):
    todo_repo(repo)

    _, payload = cand(capsys, repo, "--exclude", "vendor/")

    assert todos_of(payload) == {"src/a.py": 5, "src/b.py": 1}


def test_todo_ignores_binary_files(capsys, repo):
    todo_repo(repo)

    _, payload = cand(capsys, repo)

    assert "bin.dat" not in todos_of(payload)


def test_todo_exclude_removes_files_and_shrinks_files_grepped(capsys, repo):
    todo_repo(repo)
    _, full = cand(capsys, repo)

    _, trimmed = cand(capsys, repo, "--exclude", "vendor/")

    assert "vendor/v.py" in todos_of(full)
    assert "vendor/v.py" not in todos_of(trimmed)
    assert trimmed["examined"]["files_grepped"] == full["examined"]["files_grepped"] - 1


def test_todo_ties_included_and_flagged(capsys, repo):
    commit(repo, "t", {"a": "TODO\nTODO\n", "b": "FIXME\nFIXME\n", "c": "TODO\n"})

    _, payload = cand(capsys, repo, "--top", "1")

    assert todos_of(payload) == {"a": 2, "b": 2}
    assert payload["todo_tie_at_cutoff"] is True


def test_todo_clean_cutoff_has_no_tie_flag(capsys, repo):
    commit(repo, "t", {"a": "TODO\nTODO\n", "b": "FIXME\n"})

    _, payload = cand(capsys, repo, "--top", "1")

    assert todos_of(payload) == {"a": 2}
    assert payload["todo_tie_at_cutoff"] is False


def test_todo_reads_the_named_rev_not_the_working_tree(capsys, repo):
    commit(repo, "t", {"a": "TODO\n"})
    write(repo, "a", "TODO\nTODO\nTODO\n")
    write(repo, "untracked.txt", "TODO\n")

    _, payload = cand(capsys, repo)
    _, older = cand(capsys, repo, "--rev", "HEAD~1")

    assert todos_of(payload) == {"a": 1}
    assert todos_of(older) == {}


def test_no_todos_prints_zero_hotspots_and_files_grepped(capsys, repo):
    code, payload = cand(capsys, repo)

    assert code == 0
    assert payload["todo_hotspots"] == []
    assert payload["examined"]["files_grepped"] == 2


# ------------------------------------------------------------------ prs-json


def prs_file(tmp_path: Path, content: Any, raw: bool = False) -> str:
    path = tmp_path / "prs.json"
    path.write_text(content if raw else json.dumps(content), encoding="utf-8")
    return str(path)


def test_prs_json_ranks_by_rounds_from_ints_and_lists(capsys, repo, tmp_path):
    prs = [
        {"number": 5, "review_rounds": 2},
        {"number": 6, "reviews": [1, 2, 3, 4]},
        {"number": 7, "reviews": 9},
        {"number": 4, "review_rounds": 2},
        {"number": 8, "review_rounds": 4, "reviews": 0},
    ]

    code, payload = cand(capsys, repo, "--prs-json", prs_file(tmp_path, prs), "--top", "4")

    assert code == 0
    assert payload["review_rounds"] == [
        {"number": 7, "review_rounds": 9},
        {"number": 6, "review_rounds": 4},
        {"number": 8, "review_rounds": 4},
        {"number": 4, "review_rounds": 2},
    ]
    assert payload["examined"]["prs"] == 5


def test_prs_json_empty_list_is_valid(capsys, repo, tmp_path):
    code, payload = cand(capsys, repo, "--prs-json", prs_file(tmp_path, []))

    assert code == 0
    assert payload["review_rounds"] == []
    assert payload["examined"]["prs"] == 0


def test_review_rounds_key_absent_without_prs_json(capsys, repo):
    _, payload = cand(capsys, repo)

    assert "review_rounds" not in payload
    assert "prs" not in payload["examined"]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"number": 1}',
        '["str"]',
        '[{"review_rounds": 1}]',
        '[{"number": true, "review_rounds": 1}]',
        '[{"number": 1}]',
        '[{"number": 1, "review_rounds": "3"}]',
        '[{"number": 1, "review_rounds": -1}]',
        '[{"number": 1, "reviews": null}]',
    ],
)
def test_prs_json_malformed_exits_2(capsys, repo, tmp_path, content):
    code, payload = cand(capsys, repo, "--prs-json", prs_file(tmp_path, content, raw=True))

    assert code == 2
    assert payload["error"] == "config"


def test_prs_json_missing_file_exits_2(capsys, repo, tmp_path):
    code, payload = cand(capsys, repo, "--prs-json", str(tmp_path / "nope.json"))

    assert code == 2
    assert "--prs-json" in payload["message"]


# ------------------------------------------------------------------ candidate exit codes


def test_repo_that_is_not_a_directory_exits_2(capsys, tmp_path):
    code, payload = cand(capsys, tmp_path / "missing")

    assert code == 2
    assert payload["error"] == "config"


def test_directory_that_is_not_a_repo_exits_2(capsys, tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()

    code, payload = cand(capsys, plain)

    assert code == 2
    assert "not a git repository" in payload["message"]


def test_bad_rev_exits_2(capsys, repo):
    code, payload = cand(capsys, repo, "--rev", "no-such-ref")

    assert code == 2
    assert "no-such-ref" in payload["message"]


def test_rev_that_looks_like_an_option_exits_2(capsys, repo):
    code, _ = cand(capsys, repo, "--rev=--all")

    assert code == 2


def test_repository_with_no_commit_exits_2(capsys, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    run_git(empty, "init", "-q")

    code, _ = cand(capsys, empty)

    assert code == 2


@pytest.mark.parametrize("flag", ["--max-commits", "--churn-window", "--top"])
def test_non_positive_limits_exit_2(capsys, repo, flag):
    code, payload = cand(capsys, repo, flag, "0")

    assert code == 2
    assert flag in payload["message"]


def test_repo_may_be_a_subdirectory_of_the_work_tree(capsys, repo):
    commit(repo, "c", {"sub/x.txt": "TODO\n"})

    code, payload = cand(capsys, repo / "sub", *BASELINE)

    assert code == 0
    assert payload["repo"] == repo.as_posix()
    assert todos_of(payload) == {"sub/x.txt": 1}


def test_git_missing_exits_3(capsys, repo, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent-bin")

    code, payload = cand(capsys, repo)

    assert code == 3
    assert payload["error"] == "git"


def fail_git(monkeypatch, word: str, rc: int = 128) -> None:
    real = mine._run_git

    def fake(repo, *args):
        if word in args:
            return subprocess.CompletedProcess(["git", *args], rc, "", "boom")
        return real(repo, *args)

    monkeypatch.setattr(mine, "_run_git", fake)


@pytest.mark.parametrize(("word", "rc"), [("log", 128), ("grep", 2), ("ls-tree", 128)])
def test_git_command_failure_exits_3(capsys, repo, monkeypatch, word, rc):
    fail_git(monkeypatch, word, rc)

    code, payload = cand(capsys, repo)

    assert code == 3
    assert "boom" in payload["message"]


def test_git_grep_exit_1_means_no_matches_not_failure(capsys, repo):
    code, payload = cand(capsys, repo)

    assert code == 0
    assert payload["todo_hotspots"] == []


# ------------------------------------------------------------------ --out


def test_out_inside_repo_is_refused_and_nothing_is_written(capsys, repo):
    target = repo / "report.json"

    code, payload = cand(capsys, repo, "--out", str(target))

    assert code == 2
    assert "inside the repository" in payload["message"]
    assert not target.exists()
    assert run_git(repo, "status", "--porcelain") == ""


def test_out_equal_to_repo_root_is_refused(capsys, repo):
    code, _ = cand(capsys, repo, "--out", str(repo))

    assert code == 2


def test_out_that_is_a_directory_is_refused(capsys, repo, tmp_path):
    code, payload = cand(capsys, repo, "--out", str(tmp_path))

    assert code == 2
    assert "directory" in payload["message"]


def test_out_outside_repo_gets_the_same_json_as_stdout(capsys, repo, tmp_path):
    target = tmp_path / "nested" / "out.json"

    code = mine.main(["candidates", "--repo", str(repo), "--out", str(target)])

    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert json.loads(target.read_text(encoding="utf-8")) == printed


def test_out_write_failure_exits_3(capsys, repo, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")

    code, payload = cand(capsys, repo, "--out", str(blocker / "out.json"))

    assert code == 3
    assert payload["error"] == "io"


def test_missing_subcommand_is_an_argparse_error():
    with pytest.raises(SystemExit) as info:
        mine.main([])

    assert info.value.code == 2


def test_script_runs_as_main(capsys, repo, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["bootstrap_mine.py", "candidates", "--repo", str(repo)])

    with pytest.raises(SystemExit) as info:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert info.value.code == 0
    assert json.loads(capsys.readouterr().out)["examined"]["commits"] == 1


def test_script_source_has_no_dashes_or_new_syntax():
    text = SCRIPT.read_text(encoding="utf-8")

    assert chr(0x2014) not in text and chr(0x2013) not in text
    compile(text, str(SCRIPT), "exec", flags=0, dont_inherit=True)


# ------------------------------------------------------------------ claims

TOOL = "a\nb\nc\n"


@pytest.fixture
def crepo(repo: Path) -> Path:
    commit(
        repo,
        "claims fixture",
        {
            "scripts/tool.py": TOOL,
            "scripts/sub/deep.py": "x = 1\n",
            "scripts/empty.txt": "",
            "docs/guide.md": "1\n2\n3\n4\n5",
            "pyproject.toml": "[a]\n[b]\n[c]\n[d]\n[e]\n",
        },
    )
    return repo


def md(tmp_path: Path, text: str, name: str = "skill.md") -> Path:
    path = tmp_path / "authored" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def claims(capsys, repo: Path, *targets: Path, extra: tuple[str, ...] = ()) -> Result:
    return run(capsys, "claims", "--repo", str(repo), *extra, *(str(t) for t in targets))


def statuses(payload: dict[str, Any]) -> dict[str, str]:
    return {f["ref"]: f["status"] for f in payload["findings"]}


def test_existing_files_and_dirs_are_ok(capsys, crepo, tmp_path):
    target = md(
        tmp_path,
        "See scripts/tool.py and `scripts/sub/deep.py`.\n"
        "Dir `scripts/` and prefix scripts/sub and .claude/skills/existing-skill/SKILL.md\n",
    )

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"] == []
    assert payload["examined"] == {"files": 1, "references": 5}
    assert payload["summary"] == {"status": {}, "context": {}}


def test_missing_current_reference_exits_1(capsys, crepo, tmp_path):
    target = md(tmp_path, "Run scripts/nope.py now.\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert payload["findings"] == [
        {
            "file": target.as_posix(),
            "line": 1,
            "ref": "scripts/nope.py",
            "path": "scripts/nope.py",
            "status": "missing",
            "context": "current",
        }
    ]
    assert payload["summary"] == {"status": {"missing": 1}, "context": {"current": 1}}


def test_untracked_file_on_disk_is_untracked_not_missing(capsys, crepo, tmp_path):
    write(crepo, "scripts/out.log", "x\n")
    write(crepo, "scratch/new.txt", "x\n")
    target = md(tmp_path, "Output goes to scripts/out.log and scratch/new.txt and scripts/gone\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/out.log": "untracked", "scripts/gone": "missing"}


def test_rev_decides_tracked_state_not_the_working_tree(capsys, crepo, tmp_path):
    commit(crepo, "add file", {".claude/added.txt": "x\n"})
    first = run_git(crepo, "rev-parse", "HEAD~1").strip()
    target = md(tmp_path, ".claude/added.txt\n")

    code, payload = claims(capsys, crepo, target, extra=("--rev", first))

    assert code == 1
    assert statuses(payload) == {".claude/added.txt": "untracked"}


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("scripts/tool.py:3", None),
        ("scripts/tool.py:1-3", None),
        ("scripts/tool.py:4", "line-out-of-range"),
        ("scripts/tool.py:2-9", "line-out-of-range"),
        ("scripts/tool.py:12,40-45", "line-out-of-range"),
        ("scripts/tool.py:1,3", None),
        ("docs/guide.md:5", None),
        ("docs/guide.md:6", "line-out-of-range"),
        ("scripts/empty.txt:1", "line-out-of-range"),
    ],
)
def test_line_specs_are_checked_against_the_blob_line_count(capsys, crepo, tmp_path, ref, expected):
    target = md(tmp_path, f"see `{ref}` here\n")

    _, payload = claims(capsys, crepo, target)

    found = statuses(payload).get(ref)
    assert found == expected
    if expected:
        assert payload["findings"][0]["path"] == ref.split(":")[0]


def test_line_count_uses_the_rev_blob_not_the_disk_copy(capsys, crepo, tmp_path):
    write(crepo, "scripts/tool.py", TOOL * 10)
    target = md(tmp_path, "scripts/tool.py:9\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/tool.py:9": "line-out-of-range"}


def test_node_and_anchor_suffixes_are_dropped(capsys, crepo, tmp_path):
    target = md(
        tmp_path,
        "scripts/tool.py::test_x[param] and scripts/tool.py::Cls::test_y\n"
        "and docs/guide.md#section-one and scripts/nope.py::test_z\n",
    )

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/nope.py::test_z": "missing"}
    assert payload["findings"][0]["path"] == "scripts/nope.py"
    assert payload["examined"]["references"] == 4


def test_trailing_period_and_comma_are_trimmed(capsys, crepo, tmp_path):
    target = md(tmp_path, "Edit scripts/tool.py. Then scripts/nope.py, and scripts/gone.py.\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/nope.py": "missing", "scripts/gone.py": "missing"}


def test_line_spec_after_a_trimmed_period_is_not_parsed(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/tool.py.:99\n")

    code, payload = claims(capsys, crepo, target)

    assert payload["examined"]["references"] == 1
    assert code == 0


@pytest.mark.parametrize(
    "line",
    [
        "scripts/<name>.py",
        "scripts/{a,b}.py",
        "scripts/*.py",
        "scripts/foo?.py",
        "scripts/[a-z].py",
        "scripts/$X",
        "scripts/NAME.py",
        "scripts/SCRIPT.py",
        "docs/ADR-NNN.md",
        "docs/NN-intro.md",
        "docs/YYYY-MM-DD.md",
        ".claude/skills/slug/SKILL.md",
    ],
)
def test_placeholders_are_skipped(capsys, crepo, tmp_path, line):
    target = md(tmp_path, f"Use {line} for this.\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"] == []
    assert payload["examined"]["references"] == 0


def test_placeholder_skip_does_not_hide_a_neighbouring_real_miss(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/<name>.py then scripts/real_miss.py\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/real_miss.py": "missing"}


def test_words_that_only_contain_placeholder_letters_are_real_paths(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/RENAMED.py and scripts/Sluggish/x\n")

    _, payload = claims(capsys, crepo, target)

    assert set(statuses(payload)) == {"scripts/RENAMED.py", "scripts/Sluggish/x"}


def test_markdown_link_brackets_are_not_placeholders(capsys, crepo, tmp_path):
    target = md(tmp_path, "[scripts/tool.py](scripts/tool.py) and [x](docs/gone.md)\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"docs/gone.md": "missing"}
    assert payload["examined"]["references"] == 2


def test_references_preceded_by_a_path_character_are_skipped(capsys, crepo, tmp_path):
    target = md(
        tmp_path,
        "https://example.com/org/repo/blob/main/scripts/nope.py\n"
        "../scripts/nope.py and ~/.claude/nope and mydocs/guide.md\n",
    )

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["examined"]["references"] == 0


def test_dotdot_segments_never_count_as_on_disk(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/../README.md\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/../README.md": "missing"}


def test_tracked_file_written_as_a_directory_is_missing(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/tool.py/\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/tool.py/": "missing"}


def test_directory_reference_with_trailing_slash(capsys, crepo, tmp_path):
    write(crepo, "newdir/x", "x")
    target = md(tmp_path, "scripts/sub/ ok, scripts/ghost/ gone, scripts/ ok\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/ghost/": "missing"}


def test_bare_top_level_file_counts_only_in_backticks(capsys, crepo, tmp_path):
    target = md(
        tmp_path,
        "Plain pyproject.toml is ignored and README.md too.\n"
        "`pyproject.toml` ok, `README.md` ok, `notes.txt` untracked name, `pyproject.toml extra`\n"
        "`pyproject.toml:99` and `pyproject.toml:2` and `pyproject.toml::x` and "
        "`pyproject.toml:2 tail`\n",
    )

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"pyproject.toml:99": "line-out-of-range"}
    assert payload["examined"]["references"] == 5


def test_bare_name_does_not_double_count_with_a_directory_path(capsys, crepo, tmp_path):
    target = md(tmp_path, "`scripts/tool.py`\n")

    _, payload = claims(capsys, crepo, target)

    assert payload["examined"]["references"] == 1


def test_fenced_code_and_plain_text_are_both_scanned(capsys, crepo, tmp_path):
    target = md(
        tmp_path,
        "```bash\npython scripts/fenced_miss.py\n```\nPlain scripts/plain_miss.py text\n",
    )

    _, payload = claims(capsys, crepo, target)

    assert [(f["line"], f["ref"]) for f in payload["findings"]] == [
        (2, "scripts/fenced_miss.py"),
        (4, "scripts/plain_miss.py"),
    ]


@pytest.mark.parametrize(
    "word",
    ["retired", "Deleted", "removed", "formerly", "superseded"]
    + ["no longer", "legacy", "used to"],
)
def test_historical_words_label_the_context(capsys, crepo, tmp_path, word):
    target = md(tmp_path, f"scripts/old.py {word} here\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"][0]["context"] == "historical"
    assert payload["summary"] == {"status": {"missing": 1}, "context": {"historical": 1}}


def test_historical_substring_inside_a_word_does_not_count(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/old.py washes and wasteland\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert payload["findings"][0]["context"] == "current"


def test_mixed_contexts_exit_1_and_summarize(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/a.py was retired\nscripts/b.py is live\nscripts/c.py\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert payload["summary"] == {
        "status": {"missing": 3},
        "context": {"historical": 1, "current": 2},
    }


def test_same_ref_repeated_in_a_file_is_reported_once_at_first_line(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/nope.py\nagain scripts/nope.py and scripts/nope.py\n")

    _, payload = claims(capsys, crepo, target)

    assert [f["line"] for f in payload["findings"]] == [1]
    assert payload["examined"]["references"] == 1


def test_current_use_of_a_ref_overrides_an_earlier_historical_one(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/nope.py was removed\nstill run scripts/nope.py\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert payload["findings"][0]["line"] == 2
    assert payload["findings"][0]["context"] == "current"


def test_historical_repeat_does_not_displace_a_current_finding(capsys, crepo, tmp_path):
    target = md(tmp_path, "run scripts/nope.py\nscripts/nope.py was removed\n")

    _, payload = claims(capsys, crepo, target)

    assert payload["findings"][0]["line"] == 1
    assert payload["findings"][0]["context"] == "current"


def test_same_path_with_different_line_specs_are_distinct_refs(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/tool.py:1 and scripts/tool.py:99\n")

    _, payload = claims(capsys, crepo, target)

    assert payload["examined"]["references"] == 2
    assert statuses(payload) == {"scripts/tool.py:99": "line-out-of-range"}


def test_same_ref_in_two_files_is_reported_per_file(capsys, crepo, tmp_path):
    one = md(tmp_path, "scripts/nope.py\n", "one.md")
    two = md(tmp_path, "scripts/nope.py\n", "two.md")

    _, payload = claims(capsys, crepo, one, two)

    assert [f["file"] for f in payload["findings"]] == [one.as_posix(), two.as_posix()]
    assert payload["examined"]["files"] == 2


def test_directory_target_scans_md_files_sorted_and_recursively(capsys, crepo, tmp_path):
    md(tmp_path, "scripts/b_miss.py\n", "b.md")
    md(tmp_path, "scripts/a_miss.py\n", "a.md")
    md(tmp_path, "scripts/deep_miss.py\n", "sub/c.md")
    md(tmp_path, "scripts/not_markdown_miss.py\n", "notes.txt")

    _, payload = claims(capsys, crepo, tmp_path / "authored")

    assert [Path(f["file"]).name for f in payload["findings"]] == ["a.md", "b.md", "c.md"]
    assert payload["examined"]["files"] == 3


def test_overlapping_targets_are_read_once(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/nope.py\n")

    _, payload = claims(capsys, crepo, target.parent, target)

    assert payload["examined"] == {"files": 1, "references": 1}


def test_non_markdown_file_target_is_accepted(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/tool.py\n", "notes.txt")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["examined"] == {"files": 1, "references": 1}


def test_target_inside_the_repo_is_reported_repo_relative(capsys, crepo):
    write(crepo, "docs/inside.md", "scripts/nope.py\n")

    _, payload = claims(capsys, crepo, crepo / "docs" / "inside.md")

    assert payload["findings"][0]["file"] == "docs/inside.md"


def test_empty_target_and_empty_directory_print_zero_counts(capsys, crepo, tmp_path):
    empty = md(tmp_path, "", "empty.md")
    folder = tmp_path / "folder"
    folder.mkdir()

    code_file, file_payload = claims(capsys, crepo, empty)
    code_dir, dir_payload = claims(capsys, crepo, folder)

    assert (code_file, code_dir) == (0, 0)
    assert file_payload["examined"] == {"files": 1, "references": 0}
    assert dir_payload["examined"] == {"files": 0, "references": 0}


def test_repo_with_no_top_level_directory_still_checks_bare_names(capsys, tmp_path):
    flat = tmp_path / "flat"
    flat.mkdir()
    run_git(flat, "init", "-q")
    run_git(flat, "config", "user.name", "T")
    run_git(flat, "config", "user.email", "t@example.com")
    commit(flat, "flat", {"README.md": "one\n"})
    target = md(tmp_path, "`README.md:5` and scripts/x.py\n")

    _, payload = claims(capsys, flat, target)

    assert statuses(payload) == {"README.md:5": "line-out-of-range"}


def test_top_level_submodule_entry_is_not_a_directory_prefix(capsys, crepo, tmp_path):
    head = run_git(crepo, "rev-parse", "HEAD").strip()
    run_git(crepo, "update-index", "--add", "--cacheinfo", f"160000,{head},subtop")
    run_git(crepo, "commit", "-q", "-m", "add gitlink")
    target = md(tmp_path, "subtop/file.py\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["examined"]["references"] == 0


def test_line_check_on_an_unreadable_blob_exits_3(capsys, crepo, tmp_path):
    absent = "1" * 40
    run_git(crepo, "update-index", "--add", "--cacheinfo", f"160000,{absent},scripts/link")
    run_git(crepo, "commit", "-q", "-m", "add nested gitlink")
    target = md(tmp_path, "scripts/link:3\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 3
    assert payload["error"] == "git"


def test_missing_target_exits_2(capsys, crepo, tmp_path):
    code, payload = claims(capsys, crepo, tmp_path / "nope.md")

    assert code == 2
    assert "TARGET" in payload["message"]


def test_unreadable_target_exits_2(capsys, crepo, tmp_path, monkeypatch):
    target = md(tmp_path, "scripts/tool.py\n")
    real = Path.read_text

    def deny(self, *args, **kwargs):
        if self == target:
            raise PermissionError("denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny)

    code, payload = claims(capsys, crepo, target)

    assert code == 2
    assert "cannot read TARGET" in payload["message"]


def test_claims_bad_rev_exits_2(capsys, crepo, tmp_path):
    code, _ = claims(capsys, crepo, md(tmp_path, "x\n"), extra=("--rev", "nope"))

    assert code == 2


def test_claims_bad_repo_exits_2(capsys, tmp_path):
    code, _ = claims(capsys, tmp_path / "missing", md(tmp_path, "x\n"))

    assert code == 2


def test_claims_git_missing_exits_3(capsys, crepo, tmp_path, monkeypatch):
    target = md(tmp_path, "x\n")
    monkeypatch.setenv("PATH", "/nonexistent-bin")

    code, payload = claims(capsys, crepo, target)

    assert code == 3
    assert payload["error"] == "git"


def test_claims_git_failure_exits_3(capsys, crepo, tmp_path, monkeypatch):
    target = md(tmp_path, "x\n")
    fail_git(monkeypatch, "ls-tree")

    code, _ = claims(capsys, crepo, target)

    assert code == 3


def test_claims_out_inside_repo_refused(capsys, crepo, tmp_path):
    target = md(tmp_path, "x\n")
    out = crepo / "claims.json"

    code, payload = claims(capsys, crepo, target, extra=("--out", str(out)))

    assert code == 2
    assert "inside the repository" in payload["message"]
    assert not out.exists()


def test_claims_out_outside_repo_written(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/nope.py\n")
    out = tmp_path / "elsewhere" / "claims.json"

    code = mine.main(["claims", "--repo", str(crepo), "--out", str(out), str(target)])

    printed = json.loads(capsys.readouterr().out)
    assert code == 1
    assert json.loads(out.read_text(encoding="utf-8")) == printed


def test_claims_leaves_the_repository_untouched(capsys, crepo, tmp_path):
    target = md(tmp_path, "scripts/nope.py scripts/tool.py:2\n")
    before = run_git(crepo, "status", "--porcelain")

    claims(capsys, crepo, target)
    cand(capsys, crepo)

    assert run_git(crepo, "status", "--porcelain") == before


def skill_repo(crepo: Path) -> Path:
    """Commit a skill whose SKILL.md names its own scripts by skill-relative path."""
    commit(
        crepo,
        "add demo skill",
        {
            ".claude/skills/demo/SKILL.md": "x\n",
            ".claude/skills/demo/scripts/run.py": "a\nb\n",
        },
    )
    return crepo / ".claude" / "skills" / "demo" / "SKILL.md"


def test_skill_relative_script_reference_is_ok(capsys, crepo):
    target = skill_repo(crepo)
    target.write_text("Run `scripts/run.py` from this skill.\n", encoding="utf-8")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"] == []


def test_skill_relative_line_reference_past_the_end_is_out_of_range(capsys, crepo):
    target = skill_repo(crepo)
    target.write_text("See `scripts/run.py:9`.\n", encoding="utf-8")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/run.py:9": "line-out-of-range"}


def test_reference_missing_from_root_and_skill_stays_missing(capsys, crepo):
    target = skill_repo(crepo)
    target.write_text("Run `scripts/absent.py`.\n", encoding="utf-8")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert statuses(payload) == {"scripts/absent.py": "missing"}


def test_file_outside_any_skill_resolves_from_the_root_only(capsys, crepo, tmp_path):
    skill_repo(crepo)
    target = md(tmp_path, "Run `scripts/run.py`.\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/run.py": "missing"}


# ------------------------------------------- security review F3: --out writes


def test_out_existing_file_is_refused_and_unchanged(capsys, repo, tmp_path):
    target = tmp_path / "keep.json"
    target.write_text("precious", encoding="utf-8")

    code, payload = cand(capsys, repo, "--out", str(target))

    assert code == 2
    assert "already exists" in payload["message"]
    assert target.read_text(encoding="utf-8") == "precious"


@pytest.mark.parametrize("name", ["out.txt", "out", "out.json.bak", ".json"])
def test_out_without_json_suffix_is_refused(capsys, repo, tmp_path, name):
    target = tmp_path / name

    code, payload = cand(capsys, repo, "--out", str(target))

    assert code == 2
    assert ".json" in payload["message"]
    assert not target.exists()


def test_out_json_suffix_writes_a_new_file(capsys, repo, tmp_path):
    target = tmp_path / "new.json"

    code, payload = cand(capsys, repo, "--out", str(target))

    assert code == 0
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_out_symlink_to_existing_file_is_refused(capsys, repo, tmp_path):
    real = tmp_path / "real.json"
    real.write_text("precious", encoding="utf-8")
    link = tmp_path / "link.json"
    symlink_or_skip(link, real)

    code, _ = cand(capsys, repo, "--out", str(link))

    assert code == 2
    assert real.read_text(encoding="utf-8") == "precious"


def test_out_is_rechecked_right_before_writing(capsys, repo, tmp_path, monkeypatch):
    target = tmp_path / "late.json"
    real_candidates = mine.candidates

    def sneaky(args):
        result = real_candidates(args)
        target.write_text("raced", encoding="utf-8")  # appears after the first check
        return result

    monkeypatch.setattr(mine, "candidates", sneaky)

    code, payload = cand(capsys, repo, "--out", str(target))

    assert code == 2
    assert "already exists" in payload["message"]
    assert target.read_text(encoding="utf-8") == "raced"


def test_out_that_moves_into_the_repo_before_writing_is_refused(capsys, repo, tmp_path):
    with pytest.raises(mine.ConfigError, match="inside the repository"):
        mine._emit({}, repo / "late.json", repo)

    assert not (repo / "late.json").exists()


# ----------------------------------- security review F5b: NUL-framed git log


def test_commit_body_with_record_and_field_separators_does_not_break_parsing(capsys, repo):
    commit(repo, "chore: odd body", body="line\x1e\x1f\x1e more\x1f")
    commit(repo, "Revert the odd thing")

    code, payload = cand(capsys, repo)

    assert code == 0
    assert payload["examined"]["commits"] == 3
    assert payload["examined"]["unparsed_commits"] == 0
    assert [r["subject"] for r in payload["reverts"]] == ["Revert the odd thing"]


def test_unparsed_commits_is_zero_for_a_normal_history(capsys, repo):
    _, payload = cand(capsys, repo)

    assert payload["examined"]["unparsed_commits"] == 0


def test_record_that_does_not_split_into_fields_is_skipped_and_counted():
    sha = "a" * 40
    good = f"{sha}\x1f2026-01-01T00:00:00+00:00\x1fRevert x\x1f"
    raw = "\0".join([good, "garbage with no separators", "zz\x1f1\x1f2\x1f3", ""])

    reverts, commits, unparsed = mine.parse_reverts(raw)

    assert (commits, unparsed) == (1, 2)
    assert [r["sha"] for r in reverts] == [sha]


def test_parse_reverts_tolerates_blank_and_newline_only_records():
    assert mine.parse_reverts("") == ([], 0, 0)
    assert mine.parse_reverts("\n\0\n") == ([], 0, 0)


def test_out_directory_with_json_suffix_is_refused(capsys, repo, tmp_path):
    target = tmp_path / "dir.json"
    target.mkdir()

    code, payload = cand(capsys, repo, "--out", str(target))

    assert code == 2
    assert "is a directory" in payload["message"]


def authored_skill(crepo: Path) -> Path:
    """Write a skill on disk without committing it, as a bootstrap run leaves it."""
    write(crepo, ".claude/skills/fresh/scripts/run.py", "a\nb\n")
    target = crepo / ".claude" / "skills" / "fresh" / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def test_uncommitted_skill_resolves_its_own_files_on_disk(capsys, crepo):
    target = authored_skill(crepo)
    target.write_text(
        "Run `scripts/run.py` or `.claude/skills/fresh/scripts/run.py:2`.\n", encoding="utf-8"
    )

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"] == []


def test_uncommitted_skill_line_past_the_end_is_out_of_range(capsys, crepo):
    target = authored_skill(crepo)
    target.write_text("See `scripts/run.py:3`.\n", encoding="utf-8")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/run.py:3": "line-out-of-range"}


def test_uncommitted_skill_still_reports_a_file_it_did_not_write(capsys, crepo):
    target = authored_skill(crepo)
    target.write_text("Run `scripts/ghost.py`.\n", encoding="utf-8")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert statuses(payload) == {"scripts/ghost.py": "missing"}


def test_untracked_file_outside_the_skill_stays_untracked(capsys, crepo):
    target = authored_skill(crepo)
    write(crepo, "scripts/loose.py", "x\n")
    target.write_text("Run `scripts/loose.py`.\n", encoding="utf-8")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/loose.py": "untracked"}


def test_disk_status_refuses_a_climbing_path(crepo):
    view = mine.RepoView(crepo, mine.resolve_rev(crepo, "HEAD"))

    assert view.disk_status("../outside.py", None) == "missing"


def test_uncommitted_skill_directory_reference_is_ok(capsys, crepo):
    target = authored_skill(crepo)
    write(crepo, ".claude/skills/fresh/references/a.md", "x\n")
    target.write_text("Read `.claude/skills/fresh/references/`.\n", encoding="utf-8")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"] == []


def test_reverts_truncated_when_the_scan_fills_max_commits(capsys, repo):
    commit(repo, "one")
    commit(repo, "two")

    _, payload = cand(capsys, repo, "--max-commits", "1")

    assert payload["reverts_truncated"] is True


def test_reverts_not_truncated_when_history_equals_the_cap(capsys, repo):
    commit(repo, "one")
    count = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip

    _, payload = cand(capsys, repo, "--max-commits", count)

    assert payload["reverts_truncated"] is False


def test_reverts_not_truncated_when_history_is_shorter_than_the_cap(capsys, repo):
    _, payload = cand(capsys, repo, "--max-commits", "1000")

    assert payload["reverts_truncated"] is False


def test_untracked_file_in_a_committed_skill_stays_untracked(capsys, crepo):
    target = skill_repo(crepo)
    write(crepo, ".claude/skills/demo/scripts/new.py", "x\n")
    target.write_text("Run `scripts/new.py`.\n", encoding="utf-8")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert statuses(payload) == {"scripts/new.py": "untracked"}


def test_authored_flag_counts_uncommitted_files_of_an_updated_skill(capsys, crepo):
    target = skill_repo(crepo)
    write(crepo, ".claude/skills/demo/scripts/new.py", "x\n")
    target.write_text("Run `scripts/new.py`.\n", encoding="utf-8")
    skill_dir = target.parent

    code, payload = claims(capsys, crepo, target, extra=("--authored", str(skill_dir)))

    assert code == 0
    assert payload["findings"] == []


def test_authored_flag_still_reports_a_file_the_update_did_not_write(capsys, crepo):
    target = skill_repo(crepo)
    target.write_text("Run `scripts/ghost.py`.\n", encoding="utf-8")

    code, payload = claims(capsys, crepo, target, extra=("--authored", str(target.parent)))

    assert code == 1
    assert statuses(payload) == {"scripts/ghost.py": "missing"}


# ------------------------------------------------- review fixes: timeout, SHA-256, until


def test_git_timeout_exits_3(capsys, repo, monkeypatch):
    def hang(cmd, **kwargs):
        assert kwargs["timeout"] == mine.GIT_TIMEOUT_S
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(mine.subprocess, "run", hang)

    code, payload = cand(capsys, repo)

    assert code == 3
    assert "timed out" in payload["message"]


def test_revert_body_accepts_a_64_hex_sha256(capsys, repo):
    full = "b" * 64
    commit(repo, "chore: undo", body=f"This reverts commit {full}.")

    _, payload = cand(capsys, repo)

    assert payload["reverts"][0]["reverted"] == [full]


def test_until_does_not_make_a_dead_path_historical(capsys, crepo, tmp_path):
    target = md(tmp_path, "Retry until `scripts/no_such_gate.py` exits 0.\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 1
    assert payload["findings"][0]["context"] == "current"


def test_a_real_historical_line_still_does_not_block(capsys, crepo, tmp_path):
    target = md(tmp_path, "`scripts/no_such_gate.py` was removed last year.\n")

    code, payload = claims(capsys, crepo, target)

    assert code == 0
    assert payload["findings"][0]["context"] == "historical"


def test_untracked_symlink_to_outside_the_repo_is_missing_not_untracked(capsys, crepo, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    symlink_or_skip(crepo / "scripts" / "escape.txt", outside)
    target = md(tmp_path, "See scripts/escape.txt\n")

    _, payload = claims(capsys, crepo, target)

    assert statuses(payload) == {"scripts/escape.txt": "missing"}


def test_disk_status_refuses_a_symlink_that_leaves_the_repo(crepo, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    symlink_or_skip(crepo / "scripts" / "escape.txt", outside)
    (crepo / "scripts" / "inside.txt").write_text("ok", encoding="utf-8")
    sha = mine.resolve_rev(crepo, "HEAD")
    view = mine.RepoView(crepo, sha)

    assert view.disk_status("scripts/escape.txt", None) == "missing"
    assert view.disk_status("scripts/inside.txt", None) == "ok"
