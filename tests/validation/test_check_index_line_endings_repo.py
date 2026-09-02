"""The gate measured against real git repositories (issue #5475).

Everything here builds or reads a real repository, so it exercises what
`git ls-files --eol` actually emits rather than a string the test wrote.
`index_line_endings_helpers.py` carries the roster of what the other modules
cover.

Covered here: the negative control on a planted CRLF blob, the historical one
against the commit the incident shipped, the operator-visible phantom
modification and its disappearance, the two incident paths by name, and the
HEAD and index scopes with their precedence.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker
from scripts.validation import index_line_endings_git as gitmod
from tests.validation.index_line_endings_helpers import (
    INCIDENT_PATHS,
    REPO_ROOT,
    _commit,
    _git,
    _porcelain,
    _repo_with_crlf_blob,
)

# --- the live repository --------------------------------------------------


def test_this_repository_has_no_contradicting_blobs() -> None:
    """The regression guard: main must never carry one of these again."""
    violations, examined = checker.check_repository(REPO_ROOT)

    assert violations == [], [v.render() for v in violations]
    assert examined > 0


def test_this_repository_holds_no_crlf_blob_at_all() -> None:
    """Stronger than the gate, and true of this repository today.

    The gate reports a contradiction: a CRLF blob whose attributes promise LF.
    A `-text` or `eol=crlf` path is exempt by declaration and the gate leaves
    it alone, which is deliberate and is why a contributor whose editor writes
    CRLF locally does not get their push failed.

    This repository declares `* text=auto eol=lf` and stores no CRLF blob
    under any attribute: measured over the tracked tree, the index states are
    `i/lf` (9629), `i/none` (34), `i/-text` (26) and one empty. So the
    stronger claim is assertable here, and it catches a CRLF blob arriving
    under an exemption the gate would pass.
    """
    output = subprocess.run(
        ["git", "ls-files", "--eol"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
    ).stdout

    crlf = [line for line in output.split("\n") if line.startswith(("i/crlf", "i/mixed"))]

    assert crlf == []


@pytest.mark.parametrize("path", INCIDENT_PATHS)
def test_touching_an_incident_path_reports_no_modification(path: str) -> None:
    """The operator-visible symptom, asserted on the paths that had it.

    `test_a_crlf_blob_reports_a_modification_nobody_made` proves the mechanism
    in a built repository. This proves it is gone from the two files it
    actually happened to. `touch` changes only the modification time, so the
    check is non-destructive: git re-reads the file and compares content.
    """
    (REPO_ROOT / path).touch()

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
    ).stdout

    assert status.strip() == ""


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


# The last commit before this branch renormalized the two handoff blobs. It is
# on `main`, so it survives however this PR merges, and it is the only tree in
# the repository's history that still carries the defect the gate exists for.
PRE_FIX_COMMIT = "12bea5f5990086f9d1a83dce5bc1ed57757f00c7"


def _violations_at(revision: str) -> list[checker.Violation]:
    """Scan one historical commit the way the HEAD scope scans HEAD.

    An isolated index holds that commit's blobs and `GIT_ATTR_SOURCE` pins its
    attributes, so the answer is about that tree and nothing else in the
    checkout.
    """
    env = gitmod.git_environment()
    with tempfile.TemporaryDirectory() as scratch:
        env["GIT_INDEX_FILE"] = str(Path(scratch) / "pinned.index")
        env["GIT_ATTR_SOURCE"] = revision
        gitmod.run_git(REPO_ROOT, ["read-tree", revision], env=env)
        output = checker._ls_files_eol(REPO_ROOT, env=env)
    violations, _ = checker.parse_violations(output, scope=revision)
    return violations


def test_the_gate_fails_on_the_commit_the_incident_shipped() -> None:
    """The historical negative control, not a synthetic stand-in.

    `test_this_repository_has_no_contradicting_blobs` proves the gate passes on
    a clean tree and `test_negative_control_gate_fails_on_a_real_crlf_blob`
    proves it fails on a built one. Neither proves it would have caught the
    blobs that actually broke every worktree. This scans the commit that
    carried them.
    """
    if (
        subprocess.run(
            ["git", "cat-file", "-e", f"{PRE_FIX_COMMIT}^{{commit}}"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=60,
            check=False,
            env={k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")},
        ).returncode
        != 0
    ):
        pytest.skip(f"{PRE_FIX_COMMIT} is not in this clone (shallow checkout)")

    violations = _violations_at(PRE_FIX_COMMIT)

    assert sorted(v.path for v in violations) == sorted(INCIDENT_PATHS)
    assert {v.index_state for v in violations} == {"i/crlf"}


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


@pytest.mark.parametrize("path", INCIDENT_PATHS)
def test_the_two_incident_handoffs_hold_lf_index_blobs(path: str) -> None:
    """Pin the exact paths that aborted merges, on this repository."""
    result = subprocess.run(
        ["git", "ls-files", "--eol", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=True,
    )

    rows = result.stdout.splitlines()
    # An archived or renamed handoff is not a regression, but a tracked one
    # holding CRLF is exactly the defect, so only assert when it is present.
    if not rows:
        pytest.skip(f"{path} is no longer tracked")
    assert rows[0].split()[0] == "i/lf", rows[0]


# --- HEAD vs index scope (review thread on check_index_line_endings.py:65) --


def test_head_blob_is_reported_even_when_the_index_is_already_clean(
    tmp_path: Path,
) -> None:
    """Staging a fix does not make the pushed tree clean.

    `git ls-files` reads the mutable index. After `git add --renormalize` but
    before committing, the index says LF while HEAD still carries the CRLF blob
    that a push transmits, so an index-only scan would call this clean.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    _git(repo, "add", "--renormalize", "handoff.md")

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]
    assert checker.main(["--repo-root", str(repo)]) == 1


def test_staged_blob_is_reported_when_head_is_clean(tmp_path: Path) -> None:
    """The index scope still matters: it is what the next commit will store."""
    repo = _repo_with_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "index")]


def test_a_path_bad_in_both_scopes_is_reported_once(tmp_path: Path) -> None:
    """One remediation fixes both, so two rows would be noise."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]


def test_an_unborn_branch_scans_the_index_without_crashing(tmp_path: Path) -> None:
    """A repo with no commits has no HEAD to read; the index still counts."""
    repo = _repo_with_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert [v.scope for v in violations] == ["index"]


def test_head_scope_uses_head_attributes_not_the_working_tree(
    tmp_path: Path,
) -> None:
    """An uncommitted `-text` edit must not hide a committed violation.

    GIT_INDEX_FILE isolates the blobs, but git reads `.gitattributes` from the
    working tree unless GIT_ATTR_SOURCE pins it, so without that the HEAD scope
    would be judged by rules HEAD does not carry.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")

    # Locally exempt the path without committing the exemption.
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )

    violations, _ = checker.check_repository(repo)

    assert [(v.path, v.scope) for v in violations] == [("handoff.md", "HEAD")]


def test_head_scope_honours_a_committed_exemption(tmp_path: Path) -> None:
    """The control for the test above: a committed `-text` really does exempt."""
    repo = _repo_with_crlf_blob(tmp_path)
    (repo / ".gitattributes").write_text(
        "* text=auto eol=lf\n*.md text\nhandoff.md -text\n", newline="\n"
    )
    _git(repo, "add", ".gitattributes")
    _commit(repo, "plant a CRLF blob under a committed exemption")

    violations, _ = checker.check_repository(repo)

    assert violations == []
