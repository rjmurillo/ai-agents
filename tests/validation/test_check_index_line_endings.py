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
        errors="replace",
        timeout=60,
        check=True,
    )

    line = result.stdout.splitlines()[0]
    assert "\t" in line
    head = line.split("\t", 1)[0].split()
    assert head[0].startswith("i/")
    assert head[1].startswith("w/")
    assert head[2].startswith("attr/")


# --- negative control: a real repository carrying the defect ---------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )


def _repo_with_crlf_blob(tmp_path: Path, name: str = "handoff.md") -> Path:
    """Build a repo holding a CRLF blob under `eol=lf`, as the API produces one.

    `git add` would clean the CRLF away, which is the whole reason the defect
    needs a hook-free path to exist. `git hash-object -w` writes the blob
    without the filter and `update-index --cacheinfo` stages it, reproducing
    what `createCommitOnBranch` uploads.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    # `*.md text` matches this repository: an explicit `text` always applies
    # the clean filter, while `text=auto` alone leaves an already-CRLF blob
    # untouched and the defect never surfaces.
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\n", newline="\n"
    )
    _git(repo, "add", ".gitattributes")

    crlf = repo / name
    crlf.write_bytes(b"line one\r\nline two\r\n")
    blob = _git(repo, "hash-object", "-w", "--no-filters", str(crlf)).stdout.strip()
    _git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}")
    return repo


def test_negative_control_gate_fails_on_a_real_crlf_blob(tmp_path: Path) -> None:
    """The control the manual pre-fix run stood in for, now executable.

    Without this the suite proves the gate passes on a clean tree and never
    proves it fails on a dirty one, which is the only claim that matters.
    """
    repo = _repo_with_crlf_blob(tmp_path)

    violations, examined = checker.check_repository(repo)

    assert [v.path for v in violations] == ["handoff.md"]
    assert violations[0].index_state == "i/crlf"
    assert examined >= 2
    assert checker.main(["--repo-root", str(repo)]) == 1


def test_negative_control_passes_after_renormalize(tmp_path: Path) -> None:
    """The documented fix must actually clear the gate, not just quiet it."""
    repo = _repo_with_crlf_blob(tmp_path)
    assert checker.main(["--repo-root", str(repo)]) == 1

    _git(repo, "add", "--renormalize", "handoff.md")

    violations, _ = checker.check_repository(repo)
    assert violations == []
    assert checker.main(["--repo-root", str(repo)]) == 0


def test_remediation_command_quotes_paths_with_spaces(tmp_path: Path, capsys) -> None:
    """An unquoted join would print a command that renormalizes the wrong files."""
    repo = _repo_with_crlf_blob(tmp_path, name="a handoff.md")

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "git add --renormalize 'a handoff.md'" in out


def _commit(repo: Path, message: str) -> None:
    _git(
        repo,
        "-c", "user.email=test@example.invalid",
        "-c", "user.name=Test",
        "commit", "--quiet", "--no-verify", "-m", message,
    )


def _porcelain(worktree: Path) -> str:
    return _git(worktree, "status", "--porcelain").stdout.strip()


def test_a_crlf_blob_reports_a_modification_nobody_made(tmp_path: Path) -> None:
    """The operator-visible symptom, reproduced and then shown fixed.

    A fresh checkout of the CRLF blob reads back through the clean filter as
    LF, so its hash never matches its own blob and git reports a modification
    nobody made. That is what aborts a merge touching the path. Renormalizing
    removes it, and the checkout stays clean even after the file is touched.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _git(repo, "config", "core.autocrlf", "input")
    _commit(repo, "plant a CRLF blob the way the API does")

    before = tmp_path / "before"
    _git(repo, "worktree", "add", "--detach", "--quiet", str(before), "HEAD")
    (before / "handoff.md").touch()
    assert "handoff.md" in _porcelain(before)

    _git(repo, "add", "--renormalize", "handoff.md")
    _commit(repo, "renormalize")

    after = tmp_path / "after"
    _git(repo, "worktree", "add", "--detach", "--quiet", str(after), "HEAD")
    assert _porcelain(after) == ""
    (after / "handoff.md").touch()
    assert _porcelain(after) == ""
