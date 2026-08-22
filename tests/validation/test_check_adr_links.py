"""Tests for the ADR markdown link checker.

Covers the four violation classes (unresolved, absolute, number-mismatch,
malformed), the exemptions (historical roots, fenced code, non-markdown files,
baseline entries), and the CLI exit-code contract.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.validation.check_adr_links as check_adr_links
import scripts.validation.stale_script_refs as stale_script_refs
from scripts.validation.check_adr_links import (
    Finding,
    adr_number,
    find_broken_adr_links,
    git_ls_markdown,
    is_adr_target,
    is_historical_path,
    main,
    scan_file,
    split_destination,
    text_adr_number,
    validate_adr_links,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def write(root: Path, relative: str, body: str) -> str:
    """Write a file under root and return its repo-relative path."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return relative


def kinds(findings: list[Finding]) -> list[str]:
    """Return the violation kinds in order."""
    return [finding.kind for finding in findings]


# Positive: well-formed links produce no findings


def test_resolvable_adr_link_passes(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-005-powershell-only-scripting.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "See [ADR-005: PowerShell](ADR-005-powershell-only-scripting.md) for detail.\n",
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_relative_hop_out_of_directory_resolves(tmp_path: Path) -> None:
    target = write(tmp_path, "critique/ADR-045-debate-log.md", "# log\n")
    doc = write(
        tmp_path,
        "architecture/ADR-045-framework.md",
        "- [6-Agent Review Debate Log](../critique/ADR-045-debate-log.md)\n",
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_anchor_suffix_is_stripped_before_resolution(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-035-exit-code-standardization.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-033-gates.md",
        "See [ADR-035](./ADR-035-exit-code-standardization.md#contract).\n",
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_link_title_suffix_is_stripped_before_resolution(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-035-exit-code-standardization.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-033-gates.md",
        'See [ADR-035](./ADR-035-exit-code-standardization.md "Exit codes").\n',
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_angle_bracket_destination_resolves(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-035-exit-code-standardization.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-033-gates.md",
        "See [ADR-035](<./ADR-035-exit-code-standardization.md>).\n",
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_zero_padding_difference_is_not_a_mismatch(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-080-model-pin.md", "# target\n")
    doc = write(tmp_path, "adr/index.md", "See [ADR-80](ADR-080-model-pin.md).\n")

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


# Negative: each violation class fires


def test_unresolved_target_is_reported(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "- [ADR-005: PowerShell](ADR-005-powershell-only.md) - stale slug\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "ADR-005-powershell-only.md"
    assert findings[0].line == 1


def test_untracked_file_on_disk_still_reports_unresolved(tmp_path: Path) -> None:
    """An untracked target file must not make a broken link pass locally.

    ``check_adr_links.py`` used ``Path.exists()`` before this fix, so a target
    written to disk but never ``git add``-ed passed here while the identical
    commit failed in a clean checkout (PR #5209 review). Writing the file and
    passing an empty ``tracked`` set reproduces exactly that gap: the file is
    real on this filesystem and absent from the tracked inventory.
    """
    write(tmp_path, "adr/ADR-005-powershell-only-scripting.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "See [ADR-005: PowerShell](ADR-005-powershell-only-scripting.md) for detail.\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]


def test_target_outside_the_repository_root_is_rejected(tmp_path: Path) -> None:
    """A relative climb past the repository root must never resolve.

    Even a ``tracked`` set that happens to contain a same-named entry must not
    match: ``../../etc/passwd``-shaped traversal is rejected before the
    membership check runs, per the review's "reject paths outside the
    repository" requirement.
    """
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "- [Escape](../../../ADR-999-quirk.md)\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({"ADR-999-quirk.md"})
    )

    assert kinds(findings) == ["unresolved"]


def test_absolute_target_is_reported(tmp_path: Path) -> None:
    target = write(tmp_path, "critique/ADR-023-debate-log.md", "# log\n")
    doc = write(
        tmp_path,
        "architecture/ADR-023-quality-gate.md",
        "- [Debate Log](/.agents/critique/ADR-023-debate-log.md)\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({target})
    )

    assert kinds(findings) == ["absolute"]
    assert "does not resolve" in findings[0].detail


def test_number_mismatch_is_reported_when_target_resolves(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-035-exit-code-standardization.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-033-gates.md",
        "differ from [ADR-032 Exit Code Standardization]"
        "(./ADR-035-exit-code-standardization.md).\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({target})
    )

    assert kinds(findings) == ["number-mismatch"]
    assert findings[0].detail == "text says ADR-032, target is ADR-035"


def test_number_mismatch_and_unresolved_are_reported_together(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "adr/ADR-033-gates.md",
        "see [ADR-032](./ADR-035-exit-code-standardization.md)\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["number-mismatch", "unresolved"]


def test_malformed_bracket_inside_destination_is_reported(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "adr/ADR-040-skill.md",
        "by [ADR-080](./ADR-080-model-pin-justification-policy.md]) here\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["malformed"]
    assert findings[0].detail == "bracket inside destination"


def test_malformed_unterminated_destination_is_reported(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "docs/SKILL-AUTHORING.md",
        "by [ADR-080](./ADR-080-model-pin-justification-policy.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["malformed"]
    assert findings[0].detail == "destination never closed"


def test_missing_leading_dot_directory_is_reported(tmp_path: Path) -> None:
    target = write(tmp_path, ".agents/architecture/ADR-036-two-source.md", "# target\n")
    doc = write(
        tmp_path,
        "templates/AGENTS.md",
        "See [ADR-036](../agents/architecture/ADR-036-two-source.md).\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({target})
    )
    assert kinds(findings) == ["unresolved"]


# Edge: things that must NOT be reported


@pytest.mark.parametrize("fence", ["```", "```markdown", "~~~"])
def test_link_inside_fenced_block_is_ignored(tmp_path: Path, fence: str) -> None:
    doc = write(
        tmp_path,
        "docs/example.md",
        f"{fence}\n[ADR-999](./ADR-999-does-not-exist.md)\n```\n",
    )

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_link_after_a_closed_fence_is_still_scanned(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "docs/example.md",
        "```\n[ADR-999](./ADR-999-nope.md)\n```\n[ADR-998](./ADR-998-nope.md)\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-998-nope.md"


def test_a_different_fence_character_inside_a_block_does_not_close_it(tmp_path: Path) -> None:
    """CommonMark closes a fence only with its own character. A ``~~~`` block
    containing a line that opens with backticks (a transcript illustrating a
    ```` ``` ```` example, say) must not be closed by that line: only a
    matching ``~~~`` closes it. A bare open/close toggle over any fence-shaped
    line gets this backwards on both ends: it would report the still-fenced
    ADR-999 as broken (false positive on illustration content) and skip the
    real ADR-998 defect just past the true close (false negative), because the
    stray backtick line flips it out of the fence early and the real closing
    ``~~~`` flips it back in (PR #5209 review).
    """
    doc = write(
        tmp_path,
        "docs/example.md",
        "~~~\n"
        "```\n"
        "[ADR-999](./ADR-999-does-not-exist.md)\n"
        "~~~\n"
        "[ADR-998](./ADR-998-nope.md)\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-998-nope.md"


@pytest.mark.parametrize(
    "root",
    [
        ".agents/archive/",
        ".agents/sessions/",
        ".agents/critique/",
        ".serena/",
        ".claude-mem/",
    ],
)
def test_historical_roots_are_exempt(tmp_path: Path, root: str) -> None:
    doc = write(tmp_path, f"{root}note.md", "[ADR-005](ADR-005-gone.md)\n")

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_non_markdown_files_are_never_scanned(tmp_path: Path) -> None:
    """The ADR-999 and ADR-099 fixtures in issue #5197 live in .py files."""
    write(tmp_path, "tests/fixture.py", 'BAD = "[ADR-999](ADR-999.md)"\n')

    tracked = git_ls_markdown(_init_repo(tmp_path))

    assert tracked == []


def test_external_url_containing_an_adr_filename_is_ignored(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "docs/example.md",
        "[ADR-005](https://example.invalid/ADR-005-powershell-only.md)\n",
    )

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_non_adr_markdown_link_is_ignored(tmp_path: Path) -> None:
    doc = write(tmp_path, "docs/example.md", "[readme](./README-gone.md)\n")

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_link_text_without_an_adr_number_skips_the_number_rule(tmp_path: Path) -> None:
    target = write(tmp_path, "adr/ADR-045-debate-log.md", "# log\n")
    doc = write(
        tmp_path,
        "adr/index.md",
        "[6-Agent Review Debate Log](ADR-045-debate-log.md)\n",
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_missing_file_on_disk_yields_no_findings(tmp_path: Path) -> None:
    assert scan_file(tmp_path, "docs/never-written.md", frozenset()) == []


# Baseline behavior


def test_baseline_entry_suppresses_the_matching_finding(tmp_path: Path) -> None:
    doc = write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    key = "unresolved:adr/index.md:ADR-005-gone.md"

    assert find_broken_adr_links(tmp_path, files=[doc], baseline={key}, tracked=frozenset()) == []


def test_a_second_identical_finding_is_not_covered_by_one_allowance(tmp_path: Path) -> None:
    """One baseline entry allows one match, not every match sharing its key.

    ``Finding.key()`` is ``kind:file:target`` with no line number, so the same
    broken link cited twice in one file produces two findings with an
    identical key. A plain ``in`` membership check against the baseline set
    would suppress both from a single entry, meaning a second, later-added
    occurrence of an already-baselined dead link stays invisible forever.
    The real corpus had exactly this shape: ``docs/search-dont-load.md``
    cited the same absolute ADR-007 link on two lines under one baseline
    entry (Copilot, PR #5209); both are now fixed rather than double-baselined.
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        "[ADR-005](ADR-005-gone.md)\nSee also [ADR-005 again](ADR-005-gone.md)\n",
    )
    baseline = {"unresolved:adr/index.md:ADR-005-gone.md"}

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=baseline, tracked=frozenset())

    assert [finding.line for finding in findings] == [2]


def test_whole_file_baseline_entry_is_rejected_as_malformed(tmp_path: Path) -> None:
    """A bare filename must not become a silent, unbounded wildcard.

    Before this fix, ``{"adr/index.md"}`` in the baseline suppressed every
    finding in that file, current and future, through a ``finding.file in
    allowed`` branch this gate used to carry. The baseline file's own header
    requires ``<kind>:<file>:<target>`` and forbids anything looser; a
    file-only entry now fails loudly at load time instead of silently
    exempting the whole file (Copilot, PR #5209).
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        "[ADR-005](ADR-005-gone.md)\n[ADR-006](ADR-006-gone.md)\n",
    )

    with pytest.raises(ValueError, match="adr/index.md"):
        find_broken_adr_links(tmp_path, files=[doc], baseline={"adr/index.md"}, tracked=frozenset())


def test_baseline_does_not_suppress_a_different_target_in_the_same_file(tmp_path: Path) -> None:
    doc = write(
        tmp_path,
        "adr/index.md",
        "[ADR-005](ADR-005-gone.md)\n[ADR-006](ADR-006-gone.md)\n",
    )
    baseline = {"unresolved:adr/index.md:ADR-005-gone.md"}

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=baseline, tracked=frozenset())

    assert [finding.target for finding in findings] == ["ADR-006-gone.md"]


def test_baseline_does_not_suppress_a_different_kind_on_the_same_pair(tmp_path: Path) -> None:
    """The exact conflation the review named: kind must be part of the key.

    An ``unresolved`` allowance for one (file, target) pair must not also
    hide a ``number-mismatch`` that names the identical pair, or a baseline
    entry silently widens from "this specific known-broken link" to "any
    finding, of any kind, on this path" (PR #5209 review,
    discussion_r3831835196).
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        "[ADR-032](./ADR-035-exit-code-standardization.md)\n",
    )
    baseline = {"unresolved:adr/index.md:./ADR-035-exit-code-standardization.md"}

    findings = find_broken_adr_links(
        tmp_path,
        files=[doc],
        baseline=baseline,
        tracked=frozenset({"adr/ADR-035-exit-code-standardization.md"}),
    )

    assert kinds(findings) == ["number-mismatch"]


@pytest.mark.parametrize(
    "entry",
    [
        "unresolved:adr/index.md:ADR-005-gone.md",
        "absolute:docs/x.md:/ADR-007-x.md",
        "malformed:adr/index.md:ADR-005-x.md",
        "number-mismatch:adr/index.md:ADR-005-x.md",
    ],
)
def test_malformed_baseline_entries_accepts_well_formed_lines(entry: str) -> None:
    assert check_adr_links._malformed_baseline_entries({entry}) == []


@pytest.mark.parametrize(
    "entry",
    [
        "adr/index.md",  # the file-only wildcard the review flagged
        "ADR-005-gone.md",  # a bare target, no kind or file
        "not-a-kind:adr/index.md:ADR-005-gone.md",  # unrecognized kind
        "unresolved:adr/index.md",  # missing target
        "unresolved::ADR-005-gone.md",  # empty file segment
        "",
    ],
)
def test_malformed_baseline_entries_rejects_the_rest(entry: str) -> None:
    assert entry in check_adr_links._malformed_baseline_entries({entry})


def test_find_broken_adr_links_rejects_a_malformed_baseline_before_scanning(
    tmp_path: Path,
) -> None:
    """A config error, not a silently-empty result.

    ``find_broken_adr_links`` must fail loudly on a malformed baseline rather
    than returning ``[]`` (which reads identically to "no violations, and
    every finding this run would have caught").
    """
    doc = write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")

    with pytest.raises(ValueError, match="not-a-kind"):
        find_broken_adr_links(
            tmp_path,
            files=[doc],
            baseline={"not-a-kind:adr/index.md:ADR-005-gone.md"},
            tracked=frozenset(),
        )


# Helper units


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("./ADR-005-x.md", "./ADR-005-x.md"),
        ('./ADR-005-x.md "Title"', "./ADR-005-x.md"),
        ("<./ADR-005-x.md>", "./ADR-005-x.md"),
        ("./ADR-005-x.md#anchor", "./ADR-005-x.md"),
        ("   ", ""),
        ("<>", ""),
    ],
)
def test_split_destination(raw: str, expected: str) -> None:
    assert split_destination(raw) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("ADR-005-x.md", True),
        ("adr/adr-005-x.md", True),
        ("", False),
        ("README.md", False),
        ("ADR-005-x.txt", False),
        ("https://example.invalid/ADR-005-x.md", False),
        ("mailto:a@example.invalid/ADR-005-x.md", False),
        # URI schemes are case-insensitive (RFC 3986 section 3.1); a
        # case-varied scheme must not be mistaken for a repository-relative
        # ADR path (Copilot, PR #5209).
        ("HTTPS://example.invalid/ADR-005-x.md", False),
        ("Http://example.invalid/ADR-005-x.md", False),
    ],
)
def test_is_adr_target(path: str, expected: bool) -> None:
    assert is_adr_target(path) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("ADR-035-exit.md", 35), ("adr-007-x.md", 7), ("debate-ADR-035.md", None), ("", None)],
)
def test_adr_number(value: str, expected: int | None) -> None:
    assert adr_number(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ADR-032 Exit Code Standardization", 32),
        ("ADR 32", 32),
        ("adr-007", 7),
        ("Debate Log", None),
        ("EPIC #265", None),
    ],
)
def test_text_adr_number(text: str, expected: int | None) -> None:
    assert text_adr_number(text) == expected


def test_finding_format_includes_kind_and_detail() -> None:
    finding = Finding("a.md", 7, "unresolved", "ADR-005-x.md")

    assert finding.format() == "a.md:7: unresolved: ADR-005-x.md"
    assert finding.key() == "unresolved:a.md:ADR-005-x.md"


def test_finding_format_appends_detail_when_present() -> None:
    finding = Finding("a.md", 7, "absolute", "/x/ADR-005-x.md", "does not resolve from this file")

    assert finding.format().endswith("(does not resolve from this file)")


def test_historical_roots_are_reused_from_stale_script_refs() -> None:
    """The exemption list is imported, not copied, so one edit covers both gates.

    Identity is not assertable: ``check_adr_links`` imports the sibling flat
    (``from stale_script_refs import ...``, the ``pre_pr.py`` convention) while
    the test imports it by package path, so the interpreter holds two module
    objects. Equality plus a source check that no root literal was duplicated is
    what actually proves reuse.
    """
    source = (check_adr_links.__file__ and Path(check_adr_links.__file__).read_text("utf-8")) or ""

    assert check_adr_links.HISTORICAL_ROOTS == stale_script_refs.HISTORICAL_ROOTS
    assert "from stale_script_refs import HISTORICAL_ROOTS" in source
    for root in stale_script_refs.HISTORICAL_ROOTS:
        assert f'"{root}"' not in source, f"copied {root} instead of importing it"
    assert is_historical_path(".agents/archive/x.md") is True
    assert is_historical_path("docs/x.md") is False


# CLI contract


def _init_repo(root: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def test_git_ls_markdown_returns_tracked_markdown_only(tmp_path: Path) -> None:
    write(tmp_path, "docs/a.md", "# a\n")
    write(tmp_path, "docs/b.py", "x = 1\n")
    _init_repo(tmp_path)

    assert git_ls_markdown(tmp_path) == ["docs/a.md"]


def test_main_returns_zero_when_the_tree_is_clean(tmp_path: Path, capsys) -> None:
    write(tmp_path, "adr/ADR-005-x.md", "# target\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-x.md)\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    assert exit_code == 0
    assert "0 violation(s)" in capsys.readouterr().out


def test_main_returns_one_when_a_link_is_broken(tmp_path: Path, capsys) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "adr/index.md:1: unresolved: ADR-005-gone.md" in out
    assert "1 violation(s)" in out


def test_main_honors_a_baseline_file(tmp_path: Path) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# reason\nunresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8")
    _init_repo(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 0


def test_main_resolves_a_relative_baseline_against_the_repo_root(tmp_path: Path) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    (tmp_path / "baseline.txt").write_text(
        "unresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8"
    )
    _init_repo(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--baseline", "baseline.txt"]) == 0


def test_main_returns_two_when_git_is_unavailable(tmp_path: Path, capsys) -> None:
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    exit_code = main(["--repo-root", str(not_a_repo), "--baseline", str(tmp_path / "none.txt")])

    assert exit_code == 2
    assert "check_adr_links:" in capsys.readouterr().err


def test_validate_adr_links_reports_a_bool(tmp_path: Path) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    _init_repo(tmp_path)

    assert validate_adr_links(tmp_path) is False


# Corpus: the gate must pass against the real tree (ci-scripts.md MUST 13)


def test_gate_passes_against_the_repository_corpus() -> None:
    findings = find_broken_adr_links(REPO_ROOT)

    assert findings == [], "\n".join(finding.format() for finding in findings)
