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

import os
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


def test_a_row_without_a_tab_is_an_error_not_a_skip() -> None:
    """Skipping it would turn a broken scan into `0 violations` and exit 0.

    git emits nothing like this today. If it ever does, the parser has stopped
    understanding the producer, and a checker that reports clean when it can no
    longer read its input is worse than one that fails (ci-scripts.md MUST-12).
    """
    with pytest.raises(RuntimeError, match="no tab"):
        checker.parse_violations("i/crlf w/crlf attr/text eol=lf\n")


def test_a_row_with_too_few_fields_is_an_error_not_a_skip() -> None:
    with pytest.raises(RuntimeError, match="field"):
        checker.parse_violations("i/crlf\tdocs/a.md\n")


def test_a_malformed_row_reaches_the_gate_as_a_failure(monkeypatch) -> None:
    """The raise has to arrive somewhere that blocks, not somewhere that logs."""
    monkeypatch.setattr(checker, "_ls_files_eol", lambda *_a, **_k: "garbage\0")

    assert checker.validate_index_line_endings(REPO_ROOT) is False
    assert checker.main(["--repo-root", str(REPO_ROOT)]) == 2


def test_empty_output_is_clean() -> None:
    """A repository with nothing tracked is the one legitimate empty result."""
    assert checker.parse_violations("") == ([], 0)


def test_the_trailing_empty_record_of_z_output_is_not_malformed() -> None:
    """`-z` terminates rather than separates, so the split always leaves one.

    Treating it as malformed would make every real scan raise.
    """
    violations, examined = checker.parse_violations(
        "i/lf  w/lf  attr/text eol=lf     \tdocs/a.md\0"
    )

    assert (violations, examined) == ([], 1)


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
    assert "git add --renormalize -- docs/a.md" in out


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
    assert "git add --renormalize -- 'a handoff.md'" in out


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


# The two blobs this incident was about. Named explicitly, not just covered by
# the whole-tree guard above, so a reintroduction of these exact paths fails
# with the incident's own name attached rather than as an anonymous count.
INCIDENT_PATHS = (
    ".agents/sessions/handoffs/2026-09-01-4789-handoff.md",
    ".agents/sessions/handoffs/2026-09-01-5361-handoff.md",
)


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


# --- --fix mode (review thread on the advertised command, CWE-78) ----------


def test_fix_mode_renormalizes_without_building_a_shell_string(
    tmp_path: Path, monkeypatch
) -> None:
    """A filename carrying shell syntax must be inert, not executed.

    `--fix` passes paths to git as argv entries, so the quoting of the printed
    command is never load-bearing for anyone who uses it.
    """
    repo = _repo_with_crlf_blob(tmp_path, name="a;$(touch pwned).md")
    _commit(repo, "plant a CRLF blob under a hostile name")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    assert not (repo / "pwned").exists()
    violations, _ = checker.check_repository(repo)
    assert [v.scope for v in violations] == ["HEAD"]  # index fixed, HEAD awaits commit


def test_fix_mode_then_commit_clears_the_gate(tmp_path: Path, monkeypatch) -> None:
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1
    _commit(repo, "renormalize")

    assert checker.main(["--repo-root", str(repo)]) == 0


def test_fix_mode_on_a_clean_repository_is_a_no_op(tmp_path: Path, monkeypatch) -> None:
    repo = _repo_with_crlf_blob(tmp_path)
    _git(repo, "add", "--renormalize", "handoff.md")
    _commit(repo, "clean from the start")
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 0


# --- NUL-terminated parsing (review thread on core.quotePath) --------------


def test_nul_terminated_records_are_parsed() -> None:
    output = (
        "i/crlf  w/crlf  attr/text eol=lf     \tdocs/a.md\0"
        "i/lf  w/lf  attr/text eol=lf     \tdocs/b.md\0"
    )

    violations, examined = checker.parse_violations(output)

    assert [v.path for v in violations] == ["docs/a.md"]
    assert examined == 2


def test_a_path_containing_a_newline_survives_nul_parsing() -> None:
    """The exact case `core.quotePath` would have mangled without -z."""
    output = "i/crlf  w/crlf  attr/text eol=lf     \tdocs/we\nird.md\0"

    violations, _ = checker.parse_violations(output)

    assert [v.path for v in violations] == ["docs/we\nird.md"]


def test_non_ascii_paths_are_reported_raw_not_c_quoted(tmp_path: Path) -> None:
    """Under core.quotePath git would print \\346..., naming a nonexistent file."""
    repo = _repo_with_crlf_blob(tmp_path, name="ハンドオフ.md")
    _git(repo, "config", "core.quotePath", "true")

    violations, _ = checker.check_repository(repo)

    assert [v.path for v in violations] == ["ハンドオフ.md"]


# --- review round 2: parsing, attribute source, write target ---------------


@pytest.mark.parametrize(
    "path",
    ["\ndocs/leading.md", "docs/trailing.md\n", "\ndocs/both.md\n"],
)
def test_a_nul_record_keeps_leading_and_trailing_newlines(path: str) -> None:
    """`-z` exists so these survive; stripping them invents a missing file.

    The gate would report, and hand `--fix`, a path git does not know.
    """
    output = f"i/crlf  w/crlf  attr/text eol=lf     \t{path}\0"

    violations, _ = checker.parse_violations(output)

    assert [v.path for v in violations] == [path]


def test_newline_split_fallback_still_trims_its_own_terminator() -> None:
    """The non-`-z` path must not grow a stray newline in the reported path."""
    output = "i/crlf  w/crlf  attr/text eol=lf     \tdocs/a.md\n"

    violations, _ = checker.parse_violations(output)

    assert [v.path for v in violations] == ["docs/a.md"]


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


def test_fix_refuses_to_write_a_repo_the_process_is_not_inside(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """ci-scripts.md MUST-7: confirm cwd is inside the root before writing.

    Otherwise a mistyped --repo-root stages changes in a checkout nobody was
    looking at and leaves them for someone else to find.
    """
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 2

    assert "Refusing to renormalize" in capsys.readouterr().err
    # The refusal must happen before the first write, not after a partial one.
    violations, _ = checker.check_repository(repo)
    assert [v.scope for v in violations] == ["HEAD"]


def test_read_only_mode_still_works_from_outside_the_repo(tmp_path: Path, monkeypatch) -> None:
    """The guard covers --fix only; reporting from anywhere stays allowed."""
    repo = _repo_with_crlf_blob(tmp_path)
    _commit(repo, "plant a CRLF blob")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert checker.main(["--repo-root", str(repo)]) == 1


# --- a pathname is bytes, and some byte sequences are not text -------------


def _repo_with_undecodable_crlf_blob(tmp_path: Path) -> tuple[Path, bytes]:
    """Track a CRLF blob under a filename that is not valid UTF-8.

    Git stores pathnames as bytes and imposes no encoding, so `b"bad\\xff.md"`
    is a legal tracked name on POSIX. It is the case a lossy decode destroys.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n*.md text\n", newline="\n")
    _git(repo, "add", ".gitattributes")

    raw_name = b"bad\xff.md"
    (repo / os.fsdecode(raw_name)).write_bytes(b"line one\r\nline two\r\n")
    blob = _git(
        repo, "hash-object", "-w", "--no-filters", os.fsdecode(raw_name)
    ).stdout.strip()
    _git(
        repo,
        "update-index",
        "--add",
        "--cacheinfo",
        f"100644,{blob},{os.fsdecode(raw_name)}",
    )
    return repo, raw_name


def test_an_undecodable_filename_is_reported_as_the_byte_sequence_git_gave(
    tmp_path: Path,
) -> None:
    """`errors="replace"` would map the bad byte to U+FFFD, irreversibly.

    The gate would then name a file the repository does not hold. Decoding the
    path stream with `surrogateescape` keeps the bytes recoverable, which is
    what lets the reported path still identify the tracked file.
    """
    repo, raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    violations, _ = checker.check_repository(repo)

    assert len(violations) == 1
    assert violations[0].path.encode("utf-8", "surrogateescape") == raw_name
    assert "�" not in violations[0].path


def test_an_undecodable_filename_is_still_printable(tmp_path: Path, capsys) -> None:
    """Surrogates cannot be written to a UTF-8 stream; the report must not raise.

    Reporting is the gate's whole output path, so a crash here turns a
    detected violation into an unhandled traceback.
    """
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)

    assert checker.validate_index_line_endings(repo) is False

    out = capsys.readouterr().out
    assert "bad\\xff.md" in out
    assert "git add --renormalize --" in out


def test_fix_renormalizes_an_undecodable_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end the display escaping must not reach: what git actually receives.

    `--fix` passes the surrogate-escaped path, and Python re-encodes argv with
    `os.fsencode`, so git gets the original bytes back. A displayed
    `bad\\xff.md` handed to git would name nothing and the violation would
    survive its own remediation.
    """
    repo, _raw_name = _repo_with_undecodable_crlf_blob(tmp_path)
    monkeypatch.chdir(repo)

    assert checker.main(["--repo-root", str(repo), "--fix"]) == 1

    violations, _ = checker.check_repository(repo)
    assert violations == []


def test_display_path_leaves_ordinary_names_alone() -> None:
    """Control: escaping applies to bytes with no text spelling, nothing else."""
    assert checker.display_path("docs/café.md") == "docs/café.md"
    assert checker.display_path("a;$(id).md") == "a;$(id).md"
