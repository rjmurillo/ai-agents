"""Ratchet tests for check_memory_placement.py (issue #5828).

Three behaviors, each driven against a real git repository:

* a rename reads its base classification from the OLD path, so a grandfathered
  normative memory survives ``git mv``;
* a file present at the base fails only when its classification rose to
  normative (evidence or suspect to normative);
* ``--changed-since REF`` lists the memories ``REF...HEAD`` changed and judges
  them against the merge base, the server-side leg of the check.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.validation._placement_fixtures import (
    EVIDENCE_INCIDENT,
    NORMATIVE_HEADING,
    SUSPECT_ORDERED_ONLY,
    SUSPECT_TERM_DENSITY,
    VALID_SUPPRESSION,
)
from tests.validation._placement_repo import MEMORIES, commit_all, git, make_repo, write

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_memory_placement as checker
import memory_placement_git as placement_git

OLD = f"{MEMORIES}/old.md"
NEW = f"{MEMORIES}/moved/new.md"
# Suspect text that gains a Constraints heading becomes normative.
SUSPECT_PLUS_HEADING = SUSPECT_ORDERED_ONLY + "\n## Constraints\n\nDo not skip.\n"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    make_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _branch(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "feature")


# --- rename awareness: staged mode -------------------------------------------


def test_staged_git_mv_of_normative_memory_passes(repo, capsys):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered normative memory")
    (repo / NEW).parent.mkdir(parents=True)
    git(repo, "mv", OLD, NEW)

    code = checker.main(["--ci", "--staged", "--base", "HEAD", NEW])

    assert code == 0
    out = capsys.readouterr().out
    assert f"{NEW}: normative:" in out
    assert "[rose" not in out


def test_staged_rename_that_gains_signals_fails(repo, capsys):
    write(repo, OLD, SUSPECT_ORDERED_ONLY)
    commit_all(repo, "suspect memory")
    (repo / NEW).parent.mkdir(parents=True)
    git(repo, "mv", OLD, NEW)
    write(repo, NEW, SUSPECT_PLUS_HEADING)
    git(repo, "add", NEW)

    code = checker.main(["--ci", "--staged", "--base", "HEAD", NEW])

    assert code == 1
    assert "[rose from suspect]" in capsys.readouterr().out


def test_staged_normative_add_without_a_rename_still_fails(repo):
    write(repo, NEW, NORMATIVE_HEADING)
    git(repo, "add", NEW)

    assert checker.main(["--ci", "--staged", "--base", "HEAD", NEW]) == 1


def test_staged_copy_of_a_normative_memory_is_new(repo):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered normative memory")
    write(repo, NEW, NORMATIVE_HEADING)
    git(repo, "add", NEW)

    assert checker.main(["--ci", "--staged", "--base", "HEAD", NEW]) == 1


# --- score-rise rule: three states -------------------------------------------


@pytest.mark.parametrize(
    ("base_text", "head_text", "expected_exit"),
    [
        (EVIDENCE_INCIDENT, NORMATIVE_HEADING, 1),
        (SUSPECT_TERM_DENSITY, NORMATIVE_HEADING, 1),
        (NORMATIVE_HEADING, NORMATIVE_HEADING + "\nMore prose.\n", 0),
        (NORMATIVE_HEADING, SUSPECT_TERM_DENSITY, 0),
        (NORMATIVE_HEADING, EVIDENCE_INCIDENT, 0),
        (SUSPECT_TERM_DENSITY, SUSPECT_TERM_DENSITY + "\nMore prose.\n", 0),
        (EVIDENCE_INCIDENT, SUSPECT_TERM_DENSITY, 0),
        (EVIDENCE_INCIDENT, EVIDENCE_INCIDENT + "\nMore prose.\n", 0),
    ],
    ids=[
        "evidence-to-normative-fails",
        "suspect-to-normative-fails",
        "normative-stays-normative-passes",
        "normative-falls-to-suspect-passes",
        "normative-falls-to-evidence-passes",
        "suspect-stays-suspect-passes",
        "evidence-rises-to-suspect-passes",
        "evidence-stays-evidence-passes",
    ],
)
def test_classification_change_decides_the_exit(repo, base_text, head_text, expected_exit):
    write(repo, OLD, base_text)
    commit_all(repo, "base")
    write(repo, OLD, head_text)
    git(repo, "add", OLD)

    assert checker.main(["--ci", "--staged", "--base", "HEAD", OLD]) == expected_exit


def test_working_tree_edit_that_rises_fails_without_staged(repo, capsys):
    write(repo, OLD, EVIDENCE_INCIDENT)
    commit_all(repo, "base")
    write(repo, OLD, NORMATIVE_HEADING)

    assert checker.main(["--ci", OLD]) == 1
    assert "[rose from evidence]" in capsys.readouterr().out


def test_removing_a_suppression_marker_counts_as_a_rise(repo):
    write(repo, OLD, VALID_SUPPRESSION)
    commit_all(repo, "suppressed normative memory")
    write(repo, OLD, NORMATIVE_HEADING)
    git(repo, "add", OLD)

    assert checker.main(["--ci", "--staged", OLD]) == 1


def test_adding_a_suppression_marker_passes(repo, capsys):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "normative memory")
    write(repo, OLD, VALID_SUPPRESSION)
    git(repo, "add", OLD)

    assert checker.main(["--ci", "--staged", OLD]) == 0
    assert "suppressed" in capsys.readouterr().out


# --- --changed-since ----------------------------------------------------------


def test_changed_since_passes_a_renamed_normative_memory(repo, capsys):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered normative memory")
    _branch(repo)
    (repo / NEW).parent.mkdir(parents=True)
    git(repo, "mv", OLD, NEW)
    commit_all(repo, "move memory")

    code = checker.main(["--ci", "--changed-since", "main"])

    assert code == 0
    out = capsys.readouterr().out
    assert f"{NEW}: normative:" in out
    assert "1 file(s) examined" in out
    assert "0 failing" in out


def test_changed_since_fails_a_new_normative_memory(repo, capsys):
    _branch(repo)
    write(repo, NEW, NORMATIVE_HEADING)
    commit_all(repo, "add normative memory")

    assert checker.main(["--ci", "--changed-since", "main"]) == 1
    assert f"{NEW}: normative:" in capsys.readouterr().out


def test_changed_since_passes_a_new_suspect_memory(repo):
    _branch(repo)
    write(repo, NEW, SUSPECT_TERM_DENSITY)
    commit_all(repo, "add suspect memory")

    assert checker.main(["--ci", "--changed-since", "main"]) == 0


def test_changed_since_fails_an_edit_that_rises_to_normative(repo):
    write(repo, OLD, SUSPECT_TERM_DENSITY)
    commit_all(repo, "suspect memory")
    _branch(repo)
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "make it normative")

    assert checker.main(["--ci", "--changed-since", "main"]) == 1


def test_changed_since_judges_against_the_merge_base_not_the_tip(repo):
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered normative memory")
    _branch(repo)
    git(repo, "checkout", "-q", "main")
    write(repo, OLD, EVIDENCE_INCIDENT)
    commit_all(repo, "main rewrites the memory as evidence")
    git(repo, "checkout", "-q", "feature")
    write(repo, f"{MEMORIES}/unrelated.md", EVIDENCE_INCIDENT)
    commit_all(repo, "feature adds an unrelated evidence memory")

    # The branch never touched OLD. Judged against the tip of main, OLD would
    # read as a rise; the merge base lists only the memory the branch added.
    assert checker.main(["--ci", "--changed-since", "main"]) == 0


def test_changed_since_ignores_other_trees_readmes_indexes_and_deletions(repo, capsys):
    write(repo, OLD, NORMATIVE_HEADING)
    write(repo, "docs/policy.md", NORMATIVE_HEADING)
    commit_all(repo, "base")
    _branch(repo)
    write(repo, "docs/other.md", NORMATIVE_HEADING)
    write(repo, f"{MEMORIES}/README.md", NORMATIVE_HEADING)
    write(repo, f"{MEMORIES}/topic-index.md", NORMATIVE_HEADING)
    git(repo, "rm", "-q", OLD)
    commit_all(repo, "changes the check must not judge")

    assert checker.main(["--ci", "--changed-since", "main"]) == 0
    assert "0 file(s) examined" in capsys.readouterr().out


def test_changed_since_with_no_memory_changes_is_clean(repo, capsys):
    _branch(repo)
    write(repo, "notes.txt", "x\n")
    commit_all(repo, "unrelated")

    assert checker.main(["--ci", "--changed-since", "main"]) == 0
    assert "0 file(s) examined" in capsys.readouterr().out


def test_changed_since_json_reports_the_rise(repo, capsys):
    write(repo, OLD, EVIDENCE_INCIDENT)
    commit_all(repo, "base")
    _branch(repo)
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "rise")

    code = checker.main(["--ci", "--json", "--changed-since", "main"])

    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["failing"] == 1
    finding = report["findings"][0]
    assert finding["rose"] is True
    assert finding["base_label"] == "evidence"
    assert finding["is_new"] is False


def test_changed_since_without_ci_never_fails(repo):
    _branch(repo)
    write(repo, NEW, NORMATIVE_HEADING)
    commit_all(repo, "add normative memory")

    assert checker.main(["--changed-since", "main"]) == 0


# --- --changed-since error paths ----------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [["--staged"], ["--base", "HEAD"], ["--path", MEMORIES], [OLD]],
    ids=["staged", "base", "path", "positional"],
)
def test_changed_since_rejects_competing_scope_options(repo, capsys, extra):
    with pytest.raises(SystemExit) as raised:
        checker.main(["--changed-since", "main", *extra])

    assert raised.value.code == 2
    assert "--changed-since replaces" in capsys.readouterr().err


def test_changed_since_unknown_ref_exits_two(repo, capsys):
    assert checker.main(["--changed-since", "no-such-ref"]) == 2
    assert "git merge-base no-such-ref HEAD failed" in capsys.readouterr().err


def test_changed_since_option_shaped_ref_exits_two(repo, capsys):
    assert checker.main(["--changed-since=--output=x"]) == 2
    assert "invalid --changed-since ref" in capsys.readouterr().err


def test_changed_since_unrelated_history_exits_two(repo, capsys):
    git(repo, "checkout", "-q", "--orphan", "unrelated")
    write(repo, "other.txt", "x\n")
    commit_all(repo, "unrelated root")

    assert checker.main(["--changed-since", "main"]) == 2
    assert "fetch full history" in capsys.readouterr().err


def test_changed_since_outside_a_repository_exits_two(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert checker.main(["--changed-since", "main"]) == 2
    assert "not a git repository" in capsys.readouterr().err


# --- git helpers --------------------------------------------------------------


def test_parse_name_status_reads_every_record_shape():
    out = "A\0a.md\0M\0m.md\0R100\0old.md\0new.md\0C75\0src.md\0copy.md\0"

    assert placement_git.parse_name_status(out) == [
        placement_git.DiffEntry("a.md", None),
        placement_git.DiffEntry("m.md", None),
        placement_git.DiffEntry("new.md", "old.md"),
        placement_git.DiffEntry("copy.md", None),
    ]


def test_parse_name_status_of_empty_output_is_empty():
    assert placement_git.parse_name_status("") == []


def test_parse_name_status_keeps_a_path_with_spaces_and_newlines():
    out = "R090\0old name.md\0new\nname.md\0"

    assert placement_git.parse_name_status(out) == [
        placement_git.DiffEntry("new\nname.md", "old name.md")
    ]


def test_entry_helpers_reject_option_shaped_refs(repo):
    with pytest.raises(placement_git.ConfigError, match="invalid --base ref"):
        placement_git.staged_entries(repo, "--cached")
    with pytest.raises(placement_git.ConfigError, match="invalid --changed-since ref"):
        placement_git.range_entries(repo, "--cached")
    with pytest.raises(placement_git.ConfigError, match="invalid --changed-since ref"):
        placement_git.merge_base(repo, "")


def test_range_entries_failure_is_a_config_error(repo):
    with pytest.raises(placement_git.ConfigError, match="git diff failed"):
        placement_git.range_entries(repo, "no-such-ref")


def test_read_base_blob_failure_is_a_config_error(repo):
    with pytest.raises(placement_git.ConfigError, match="git cat-file"):
        placement_git.read_base_blob(repo, "HEAD", "missing.md")


def test_changed_since_accepts_fetch_head_as_the_workflow_passes_it(repo, tmp_path_factory):
    # The workflow runs `git fetch origin "$BASE_REF"` then `--changed-since FETCH_HEAD`.
    origin = tmp_path_factory.mktemp("origin")
    git(origin, "clone", "-q", "--bare", str(repo), "origin.git")
    git(repo, "remote", "add", "origin", str(origin / "origin.git"))
    write(repo, OLD, NORMATIVE_HEADING)
    commit_all(repo, "grandfathered normative memory")
    git(repo, "push", "-q", "origin", "main")
    _branch(repo)
    write(repo, NEW, NORMATIVE_HEADING)
    commit_all(repo, "add normative memory")
    git(repo, "fetch", "-q", "origin", "main")

    assert checker.main(["--ci", "--changed-since", "FETCH_HEAD"]) == 1


# --- scope resolution errors (moved with the resolver into memory_placement_paths) ---


def test_path_option_naming_a_file_exits_two(repo, capsys):
    write(repo, OLD, EVIDENCE_INCIDENT)

    assert checker.main(["--path", OLD]) == 2
    assert "--path is not a directory" in capsys.readouterr().err


def test_positional_path_outside_the_repository_exits_two(repo, tmp_path_factory, capsys):
    outside = tmp_path_factory.mktemp("outside") / "x.md"
    outside.write_text(EVIDENCE_INCIDENT)

    assert checker.main([str(outside)]) == 2
    assert "outside the repository" in capsys.readouterr().err


def test_staged_path_with_a_merge_conflict_exits_two(repo, capsys):
    write(repo, OLD, EVIDENCE_INCIDENT)
    commit_all(repo, "base")
    _branch(repo)
    write(repo, OLD, "feature side\n")
    commit_all(repo, "feature edit")
    git(repo, "checkout", "-q", "main")
    write(repo, OLD, "main side\n")
    commit_all(repo, "main edit")
    with pytest.raises(subprocess.CalledProcessError):
        git(repo, "merge", "feature")

    assert checker.main(["--staged", OLD]) == 2
    assert "unresolved index entries" in capsys.readouterr().err
