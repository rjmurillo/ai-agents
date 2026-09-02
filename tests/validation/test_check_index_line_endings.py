"""Index blobs whose line endings contradict their gitattributes.

Two blobs reached `main` holding CRLF under `* text=auto eol=lf`. With
`core.autocrlf=input` the clean filter rewrites CRLF to LF on read, so the
checked-out copy never matched its own blob, and every merge that touched
either path aborted in a worktree nobody had edited. Both arrived through the
GraphQL `createCommitOnBranch` API, which uploads bytes verbatim and runs
neither the clean filter nor any local hook, so only the index shows the
defect.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker

REPO_ROOT = Path(__file__).resolve().parents[2]


# --- parse_violations: which rows are violations --------------------------


def test_crlf_blob_under_eol_lf_is_a_violation() -> None:
    """The exact shape that broke merges on main."""
    output = "i/crlf  w/crlf  attr/text eol=lf     \t.agents/sessions/handoffs/a.md\n"

    violations, examined = checker.parse_violations(output)

    assert examined == 1
    assert len(violations) == 1
    assert violations[0].path == ".agents/sessions/handoffs/a.md"
    assert violations[0].index_state == "i/crlf"


def test_mixed_blob_under_eol_lf_is_a_violation() -> None:
    """A blob holding both endings is broken the same way a pure-CRLF one is."""
    output = "i/mixed  w/mixed  attr/text eol=lf     \tdocs/a.md\n"

    violations, _ = checker.parse_violations(output)

    assert [v.index_state for v in violations] == ["i/mixed"]


def test_lf_blob_under_eol_lf_is_clean() -> None:
    output = "i/lf  w/lf  attr/text eol=lf     \tdocs/a.md\n"

    violations, examined = checker.parse_violations(output)

    assert violations == []
    assert examined == 1


@pytest.mark.parametrize(
    "attributes",
    [
        "attr/-text",           # exempted by declaration
        "attr/text eol=crlf",   # CRLF requested on purpose
        "attr/",                # no attribute at all
        "attr/binary -text",    # binary payload
    ],
)
def test_crlf_blob_without_an_lf_promise_is_not_a_violation(attributes: str) -> None:
    """Only `eol=lf` promises LF in the index; nothing else is contradicted."""
    output = f"i/crlf  w/crlf  {attributes}     \tassets/a.bin\n"

    violations, examined = checker.parse_violations(output)

    assert violations == []
    assert examined == 1


def test_worktree_state_alone_never_triggers_a_violation() -> None:
    """A CRLF worktree copy over an LF blob is local noise, not a tracked defect.

    Only the index blob travels to other clones, so `w/crlf` on its own must
    not fail a push for someone whose editor writes CRLF locally.
    """
    output = "i/lf  w/crlf  attr/text eol=lf     \tdocs/a.md\n"

    violations, _ = checker.parse_violations(output)

    assert violations == []


# --- parse_violations: parsing edges --------------------------------------


def test_path_containing_spaces_is_not_truncated() -> None:
    """Splitting on whitespace would drop the tail and hide a real violation."""
    output = "i/crlf  w/crlf  attr/text eol=lf     \tdocs/a file with spaces.md\n"

    violations, _ = checker.parse_violations(output)

    assert violations[0].path == "docs/a file with spaces.md"


def test_multi_valued_attributes_are_reported_whole() -> None:
    output = "i/crlf  w/crlf  attr/text eol=lf diff=markdown     \tdocs/a.md\n"

    violations, _ = checker.parse_violations(output)

    assert "diff=markdown" in violations[0].attributes


def test_rows_without_a_tab_are_skipped() -> None:
    """git emits nothing like this, but a partial read must not crash."""
    violations, examined = checker.parse_violations("i/crlf w/crlf attr/text eol=lf\n")

    assert violations == []
    assert examined == 0


def test_short_rows_are_skipped() -> None:
    violations, examined = checker.parse_violations("i/crlf\tdocs/a.md\n")

    assert violations == []
    assert examined == 0


def test_empty_output_is_clean() -> None:
    assert checker.parse_violations("") == ([], 0)


def test_examined_counts_every_row_not_just_violations() -> None:
    output = (
        "i/lf  w/lf  attr/text eol=lf     \tdocs/a.md\n"
        "i/crlf  w/crlf  attr/text eol=lf     \tdocs/b.md\n"
        "i/lf  w/lf  attr/text eol=lf     \tdocs/c.md\n"
    )

    violations, examined = checker.parse_violations(output)

    assert len(violations) == 1
    assert examined == 3


# --- render: the message an operator acts on ------------------------------


def test_render_names_the_path_and_both_sides_of_the_contradiction() -> None:
    violation = checker.Violation(
        path="docs/a.md", index_state="i/crlf", attributes="attr/text eol=lf"
    )

    rendered = violation.render()

    assert "docs/a.md" in rendered
    assert "i/crlf" in rendered
    assert "attr/text eol=lf" in rendered


# --- validate_index_line_endings: the pre-PR gate contract ----------------


def test_validate_returns_false_when_git_fails(tmp_path: Path) -> None:
    """A directory with no git repo must fail, never pass by accident."""
    assert checker.validate_index_line_endings(tmp_path) is False


def test_validate_prints_the_renormalize_command(monkeypatch, capsys) -> None:
    """The operator gets a runnable fix, not just a diagnosis."""
    monkeypatch.setattr(
        checker,
        "check_repository",
        lambda _root: (
            [
                checker.Violation(
                    path="docs/a.md",
                    index_state="i/crlf",
                    attributes="attr/text eol=lf",
                )
            ],
            1,
        ),
    )

    assert checker.validate_index_line_endings(REPO_ROOT) is False
    out = capsys.readouterr().out
    assert "git add --renormalize docs/a.md" in out


def test_validate_passes_on_a_clean_repository(monkeypatch) -> None:
    monkeypatch.setattr(checker, "check_repository", lambda _root: ([], 9679))

    assert checker.validate_index_line_endings(REPO_ROOT) is True


# --- main: ADR-035 exit codes ---------------------------------------------


def test_main_exits_2_when_git_is_unavailable(tmp_path: Path) -> None:
    """A broken probe is a config error, not a clean line-ending verdict.

    Collapsing this into exit 1 would report "line endings are wrong" when
    git never ran.
    """
    assert checker.main(["--repo-root", str(tmp_path)]) == 2


def test_main_exits_1_on_violations(monkeypatch) -> None:
    monkeypatch.setattr(
        checker,
        "check_repository",
        lambda _root: (
            [
                checker.Violation(
                    path="docs/a.md",
                    index_state="i/crlf",
                    attributes="attr/text eol=lf",
                )
            ],
            1,
        ),
    )

    assert checker.main(["--repo-root", str(REPO_ROOT)]) == 1


def test_main_exits_0_when_clean(monkeypatch) -> None:
    monkeypatch.setattr(checker, "check_repository", lambda _root: ([], 1))

    assert checker.main(["--repo-root", str(REPO_ROOT)]) == 0


# --- the live repository --------------------------------------------------


def test_this_repository_has_no_contradicting_blobs() -> None:
    """The regression guard: main must never carry one of these again."""
    violations, examined = checker.check_repository(REPO_ROOT)

    assert violations == [], [v.render() for v in violations]
    assert examined > 0


def test_git_ls_files_eol_still_emits_the_parsed_shape() -> None:
    """Pin the producer's format so a git change cannot silently blind the check."""
    result = subprocess.run(
        ["git", "ls-files", "--eol", "--", "README.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )

    line = result.stdout.splitlines()[0]
    assert "\t" in line
    head = line.split("\t", 1)[0].split()
    assert head[0].startswith("i/")
    assert head[1].startswith("w/")
    assert head[2].startswith("attr/")
