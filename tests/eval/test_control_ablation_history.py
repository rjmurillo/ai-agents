"""Tests for schema_version 2 historical issue-to-fix tasks (issue #6814)."""

from __future__ import annotations

import copy
import io
import sys
import tarfile
from pathlib import Path

import pytest

from tests.eval._control_ablation_history_support import (
    BUGGY,
    FIXED,
    WITHHELD_PATH,
    WITHHELD_TEST,
    HistoryRepo,
    git,
    make_historical_document,
    make_historical_task,
    make_history_repo,
    write_document,
)
from tests.eval._control_ablation_test_support import (
    ablation_tasks,
    dry_run,
    make_task_document,
)

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _control_ablation_history as history  # noqa: E402

PY = "/opt/py/bin/python"


@pytest.fixture
def repo(tmp_path: Path) -> HistoryRepo:
    return make_history_repo(tmp_path / "repo")


def _load(repo: HistoryRepo, *tasks: dict[str, object]) -> history.HistoricalCorpus:
    return history.load_historical_tasks(make_historical_document(repo, *tasks), repo.root, PY)


def test_setup_files_come_from_the_base_commit_and_withheld_from_the_fix(
    repo: HistoryRepo,
) -> None:
    task = _load(repo).tasks[0]

    assert task.setup_files == {"calc.py": BUGGY, "tests/__init__.py": "", **_visible(task)}
    assert task.followup_files == {WITHHELD_PATH: WITHHELD_TEST}
    assert task.case == history.CASE


def _visible(task: ablation_tasks.Task) -> dict[str, str]:
    return {"tests/test_calc.py": task.setup_files["tests/test_calc.py"]}


def test_the_base_seed_holds_no_fixed_code_and_no_control_file(repo: HistoryRepo) -> None:
    task = _load(repo).tasks[0]

    assert FIXED not in task.setup_files.values()
    assert not any(path.startswith(".claude") for path in task.setup_files)


def test_python_token_is_replaced_only_where_it_is_a_whole_argument(repo: HistoryRepo) -> None:
    raw = make_historical_task(repo, acceptance=["{python}", "-c", "print('{python}x')"])

    task = _load(repo, raw).tasks[0]

    assert task.acceptance == (PY, "-c", "print('{python}x')")
    assert task.followup[0] == PY


def test_known_good_reads_the_fix_and_known_bad_edits_the_base(repo: HistoryRepo) -> None:
    task = _load(repo).tasks[0]

    assert task.controls["known_good"].files == {"calc.py": FIXED}
    assert task.controls["known_bad"].files == {"calc.py": BUGGY.replace("n // 2", "round(n / 2)")}


def test_the_source_is_returned_by_task_id(repo: HistoryRepo) -> None:
    corpus = _load(repo)

    source = corpus.sources["half-odd"]
    assert (source.base_sha, source.fix_sha, source.issue, source.fix_pr) == (
        repo.base_sha,
        repo.fix_sha,
        7,
        8,
    )
    assert corpus.base_sha == repo.base_sha


@pytest.mark.parametrize("old", ["not in the file", "n"])
def test_a_known_bad_edit_whose_old_text_is_absent_or_repeated_refuses(
    repo: HistoryRepo, old: str
) -> None:
    raw = make_historical_task(repo)
    raw["controls"]["known_bad"]["edits"][0]["old"] = old

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="occurs"):
        _load(repo, raw)


def test_a_known_bad_edit_of_an_unseeded_path_refuses(repo: HistoryRepo) -> None:
    raw = make_historical_task(repo)
    raw["controls"]["known_bad"]["edits"][0]["path"] = "AGENTS.md"

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="not a seeded file"):
        _load(repo, raw)


def test_a_missing_commit_refuses_and_names_the_shallow_clone_remedy(repo: HistoryRepo) -> None:
    raw = make_historical_task(repo)
    raw["source"]["fix_sha"] = "0" * 40

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="git fetch"):
        _load(repo, raw)


@pytest.mark.parametrize(
    ("where", "key"),
    [("task", "setup_files"), ("source", "branch"), ("control", "files")],
)
def test_an_unknown_key_refuses(repo: HistoryRepo, where: str, key: str) -> None:
    raw = make_historical_task(repo)
    target = {
        "task": raw,
        "source": raw["source"],
        "control": raw["controls"]["known_good"],
    }[where]
    target[key] = {}

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="unknown key"):
        _load(repo, raw)


def test_a_v1_case_is_refused_in_a_historical_document(repo: HistoryRepo) -> None:
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="case is unknown"):
        _load(repo, make_historical_task(repo, case="hidden_regression"))


def test_tasks_on_different_base_commits_refuse(repo: HistoryRepo) -> None:
    other = make_historical_task(repo, id="other")
    other["source"] = {**other["source"], "base_sha": repo.fix_sha}
    other["controls"]["known_bad"]["edits"][0]["old"] = "n / 2"  # the fix tree's text

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="share one base_sha"):
        _load(repo, make_historical_task(repo), other)


def test_a_duplicate_task_id_refuses(repo: HistoryRepo) -> None:
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="duplicate"):
        _load(repo, make_historical_task(repo), make_historical_task(repo))


def test_non_utf8_seed_content_refuses(tmp_path: Path) -> None:
    repo = make_history_repo(tmp_path / "repo")
    (repo.root / "calc.py").write_bytes(b"\xff\xfe")
    git(repo.root, "commit", "--quiet", "-am", "binary")
    raw = make_historical_task(repo)
    raw["source"] = {**raw["source"], "base_sha": git(repo.root, "rev-parse", "HEAD")}

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="not UTF-8"):
        _load(repo, raw)


def test_a_version_1_document_is_not_historical(repo: HistoryRepo) -> None:
    assert not history.is_historical(make_task_document())
    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="schema_version"):
        history.load_historical_tasks(make_task_document(), repo.root, PY)


def test_load_corpus_reads_controls_from_the_base_tree_for_version_2(
    repo: HistoryRepo, tmp_path: Path
) -> None:
    path = write_document(tmp_path / "t.json", make_historical_document(repo))
    (repo.root / ".claude/rules/voice.md").write_text("working tree edit\n", encoding="utf-8")

    _, tasks, sources, root = history.load_corpus(path, repo.root, tmp_path / "ws", PY)

    assert [task.id for task in tasks] == ["half-odd"]
    assert set(sources) == {"half-odd"}
    assert root != repo.root
    assert (root / "calc.py").read_text(encoding="utf-8") == BUGGY
    assert (root / ".claude/rules/voice.md").read_text(encoding="utf-8").startswith("# voice")


def test_load_corpus_keeps_the_checkout_as_control_root_for_version_1(
    repo: HistoryRepo, tmp_path: Path
) -> None:
    path = write_document(tmp_path / "t.json", make_task_document())

    _, tasks, sources, root = history.load_corpus(path, repo.root, tmp_path / "ws", PY)

    assert len(tasks) == 5
    assert sources == {}
    assert root == repo.root


def test_load_corpus_refuses_unreadable_json(repo: HistoryRepo, tmp_path: Path) -> None:
    path = tmp_path / "t.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="could not read"):
        history.load_corpus(path, repo.root, tmp_path / "ws", PY)


def test_withheld_markers_name_the_hidden_paths_the_fix_commit_and_the_fix_pr(
    repo: HistoryRepo,
) -> None:
    markers = history.withheld_markers(_load(repo).sources, repo.root)

    assert markers == {"half-odd": [WITHHELD_PATH, repo.fix_sha[:7], "/pull/8", str(repo.root)]}


@pytest.mark.parametrize("sha", ["main", "--output=/tmp/x", "abc123", "G" * 40])
def test_a_source_commit_must_be_a_full_hex_sha(repo: HistoryRepo, sha: str) -> None:
    raw = make_historical_task(repo)
    raw["source"]["fix_sha"] = sha

    with pytest.raises(ablation_tasks.ControlAblationConfigError, match="full hex commit SHA"):
        _load(repo, raw)


def test_the_dry_run_proves_the_fix_passes_and_the_plausible_bug_fails(
    repo: HistoryRepo, tmp_path: Path
) -> None:
    tasks = history.load_historical_tasks(
        make_historical_document(repo), repo.root, sys.executable
    ).tasks

    report, ok = dry_run.run_dry_run(tasks, tmp_path / "ws")

    assert ok, report
    verdicts = {run["kind"]: run["verdict"] for run in report["runs"]}
    assert verdicts == {"known_good": "ACCEPTED_DURABLE", "known_bad": "ACCEPTED_NOT_DURABLE"}


def test_the_dry_run_fails_when_the_withheld_check_cannot_tell_them_apart(
    repo: HistoryRepo, tmp_path: Path
) -> None:
    raw = copy.deepcopy(make_historical_task(repo))
    raw["source"]["withheld_files"] = {WITHHELD_PATH: "tests/test_calc.py"}
    raw["source"]["fix_sha"] = repo.base_sha  # the "withheld" test is the visible one
    raw["controls"]["known_good"] = {
        "edits": [{"path": "calc.py", "old": "n // 2", "new": "n / 2"}],
        "response": "Fixed half.",
    }
    tasks = history.load_historical_tasks(
        make_historical_document(repo, raw), repo.root, sys.executable
    ).tasks

    _, ok = dry_run.run_dry_run(tasks, tmp_path / "ws")

    assert not ok


def test_notes_are_accepted_and_change_nothing_graded(repo: HistoryRepo) -> None:
    plain = _load(repo).tasks[0]

    noted = _load(repo, make_historical_task(repo, notes="why the prompt cites old lines")).tasks[0]

    assert noted == plain


def _tar_with(name: str) -> tarfile.TarFile:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = 2
        tar.addfile(info, io.BytesIO(b"x\n"))
    buffer.seek(0)
    return tarfile.open(fileobj=buffer)


def test_extract_refuses_a_member_that_escapes_the_tree(tmp_path: Path) -> None:
    with (
        _tar_with("../escaped.txt") as tar,
        pytest.raises(ablation_tasks.ControlAblationConfigError, match="escapes"),
    ):
        history.extract_regular_files(tar, tmp_path / "tree")

    assert not (tmp_path / "escaped.txt").exists()


def test_extract_writes_a_regular_member_inside_the_tree(tmp_path: Path) -> None:
    with _tar_with("a/b.txt") as tar:
        history.extract_regular_files(tar, tmp_path / "tree")

    assert (tmp_path / "tree" / "a" / "b.txt").read_text(encoding="utf-8") == "x\n"
