"""Index blobs whose line endings contradict their gitattributes (#5475).

Two blobs reached `main` holding CRLF under `* text=auto eol=lf`. With
`core.autocrlf=input` the clean filter rewrites CRLF to LF on read, so the
checked-out copy never matched its own blob, and every merge that touched
either path aborted in a worktree nobody had edited. Both arrived through the
GraphQL `createCommitOnBranch` API, which uploads bytes verbatim and runs
neither the clean filter nor any local hook, so only the stored blob shows the
defect.

This module covers the parser and the reporting contract: which rows are
violations, which rows are malformed, what `render` says, and the ADR-035 exit
codes. Real-repository behavior lives in
`test_check_index_line_endings_repo.py`; `--fix` and path encoding live in
`test_check_index_line_endings_fix.py`; their shared repository builders live
in `index_line_endings_helpers.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_index_line_endings as checker
from tests.validation.index_line_endings_helpers import REPO_ROOT

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


@pytest.mark.parametrize("attribute", ["eol=lfx", "eol=lfoo", "xeol=lf", "noeol=lf"])
def test_a_near_miss_attribute_is_not_an_lf_promise(attribute: str) -> None:
    """`eol=lf` is matched as a whole token, never as a substring.

    A substring test reports a violation for an attribute the repository never
    declared, which blocks a push over a promise nobody made.
    """
    output = f"i/crlf  w/crlf  attr/text {attribute}     \tdocs/a.md\n"

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


def test_a_row_with_an_empty_path_is_an_error_not_a_skip() -> None:
    """Git cannot track an empty path, so such a row is malformed by definition.

    It parsed as one examined file and zero violations, which is a clean
    verdict over a row the parser could not read.
    """
    with pytest.raises(RuntimeError, match="an empty path"):
        checker.parse_violations("i/lf w/lf attr/text eol=lf\t\0")


@pytest.mark.parametrize(
    ("output", "position"),
    [
        ("\0", 0),
        ("\0i/crlf w/crlf attr/text eol=lf\tdocs/a.md\0", 0),
        ("i/lf w/lf attr/text\tdocs/a.md\0\0i/crlf w/crlf attr/text eol=lf\tb.md\0", 1),
    ],
)
def test_an_empty_record_that_is_not_the_terminator_is_an_error(
    output: str, position: int
) -> None:
    """`-z` terminates, so exactly one empty record is legitimate: the last.

    Passing over the others turns malformed producer output into a clean scan.
    `parse_violations("\\0")` used to return zero violations in zero files,
    which is what an empty repository returns.
    """
    with pytest.raises(RuntimeError, match=f"empty record at position {position}"):
        checker.parse_violations(output)


@pytest.mark.parametrize(
    "row",
    [
        "x/crlf w/crlf attr/text eol=lf\tdocs/a.md",
        "i/crlf y/crlf attr/text eol=lf\tdocs/a.md",
        "i/crlf w/crlf z/text eol=lf\tdocs/a.md",
    ],
)
def test_a_row_with_a_wrong_field_prefix_is_an_error_not_a_skip(row: str) -> None:
    """Three fields is not the contract. `i/ w/ attr/` is.

    A row that is counted but not read passes the length check, then fails to
    match `_BAD_INDEX_STATES` and is passed over as clean. That is the same
    silent pass the tab and length checks exist to stop, one layer further in.
    """
    with pytest.raises(RuntimeError, match="does not start with"):
        checker.parse_violations(f"{row}\0")


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
    """The operator gets a runnable fix, not just a diagnosis.

    Both scopes are stubbed. The command covers only paths the index scope
    still reports, because those are the ones `git add --renormalize` can act
    on, so a report test has to say what each scope saw.
    """
    staged = [
        checker.Violation(
            path="docs/a.md",
            index_state="i/crlf",
            attributes="attr/text eol=lf",
            scope="index",
        )
    ]
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
    monkeypatch.setattr(checker, "index_violations", lambda _root: (staged, 1))

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
