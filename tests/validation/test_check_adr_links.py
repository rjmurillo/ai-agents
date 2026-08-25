# taste-lint: ignore file-size -- ten-plus rounds of ADR-review fixes (issue
# #5192, #5199) each added a small regression test to the existing file rather
# than a new module, pushing it well past the 500-line limit with no single
# round crossing the ratchet baseline on its own. A split into cohesive
# modules (violation-class tests, exemption tests, CLI exit-code tests) is
# real work tracked separately; each review round only reconciles the current
# finding and should not also refactor test structure. See PR #5230.
"""Tests for the ADR markdown link checker.

Covers the four violation classes (unresolved, absolute, number-mismatch,
malformed), the exemptions (historical roots, fenced code, non-markdown files,
baseline entries), and the CLI exit-code contract.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.validation.check_adr_links as check_adr_links
import scripts.validation.stale_script_refs as stale_script_refs
from scripts.validation.check_adr_links import (
    Finding,
    adr_number,
    base_allowances_for_run,
    baseline_entries_at_ref,
    find_broken_adr_links,
    git_ls_markdown,
    is_adr_target,
    is_historical_path,
    main,
    normalize_label,
    resolve_base_ref,
    scan_file,
    split_destination,
    text_adr_number,
    validate_adr_links,
)
from scripts.validation.check_adr_links import (
    _has_adr_corpus as has_adr_corpus,
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


# Reference-style links (CommonMark full, collapsed, and shortcut forms)


def test_reference_style_link_to_a_tracked_target_passes(tmp_path: Path) -> None:
    """Positive: a reference-style link whose definition resolves is clean."""
    target = write(tmp_path, "adr/ADR-005-powershell-only-scripting.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "See [ADR-005][decision] for detail.\n\n"
        "[decision]: ./ADR-005-powershell-only-scripting.md\n",
    )

    assert (
        find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset({target}))
        == []
    )


def test_reference_style_link_with_a_broken_target_is_reported(tmp_path: Path) -> None:
    """Negative: the exact gap the review named.

    ``LINK`` matches only the inline ``[text](dest)`` form, so
    ``[ADR-005][decision]`` with ``[decision]: ./ADR-006-wrong.md`` presented
    the scanner with neither a link text nor a destination it could see, and
    an unresolved target written in this legal CommonMark syntax passed the
    repo-wide gate (Copilot, PR #5209 round-11 review).
    """
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "See [Decision Record][decision].\n\n[decision]: ./ADR-006-wrong.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-006-wrong.md"
    assert findings[0].line == 1, "reported at the reference, not at the definition"


def test_reference_style_number_mismatch_is_reported(tmp_path: Path) -> None:
    """Negative: the link text names one ADR, the definition names another."""
    target = write(tmp_path, "adr/ADR-006-wrong.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/ADR-032-ears.md",
        "See [ADR-005][decision].\n\n[decision]: ./ADR-006-wrong.md\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({target})
    )

    assert kinds(findings) == ["number-mismatch"]
    assert findings[0].detail == "text says ADR-005, target is ADR-006"


def test_reference_style_absolute_target_is_reported(tmp_path: Path) -> None:
    target = write(tmp_path, "critique/ADR-023-debate-log.md", "# log\n")
    doc = write(
        tmp_path,
        "architecture/ADR-023-quality-gate.md",
        "See [Debate Log][log].\n\n[log]: /.agents/critique/ADR-023-debate-log.md\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({target})
    )

    assert kinds(findings) == ["absolute"]


def test_collapsed_reference_link_uses_its_text_as_the_label(tmp_path: Path) -> None:
    """Edge: ``[label][]`` is a collapsed reference; the text is the label."""
    doc = write(
        tmp_path,
        "adr/index.md",
        "See [ADR-005][].\n\n[ADR-005]: ./ADR-005-gone.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-005-gone.md"


def test_shortcut_reference_link_is_resolved_against_its_definition(tmp_path: Path) -> None:
    """Edge: ``[label]`` is a link only because a definition for it exists."""
    doc = write(
        tmp_path,
        "adr/index.md",
        "See [ADR-005].\n\n[ADR-005]: ./ADR-005-gone.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]


def test_bracketed_text_without_a_definition_is_not_a_link(tmp_path: Path) -> None:
    """Edge: an undefined label renders as literal text, so it is not a defect.

    Without this, every ``[ADR-005]`` written as plain emphasis in prose
    would become a finding with no link behind it to repair.
    """
    doc = write(tmp_path, "adr/index.md", "Prose mentioning [ADR-005] and [nope][missing].\n")

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_reference_label_matching_is_case_insensitive(tmp_path: Path) -> None:
    """Edge: CommonMark normalizes labels with a Unicode case fold.

    ``[Decision Record]`` and ``[  decision   record ]`` are the same label
    (spec.commonmark.org/0.31.2/#matches), so a renderer resolves this link
    and this gate must too, or a broken destination hides behind a spelling
    difference in the label.
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        "See [ADR-005][Decision   Record].\n\n[  decision record ]: ./ADR-005-gone.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]


def test_a_reused_reference_label_resolves_to_the_first_definition(tmp_path: Path) -> None:
    """Edge: "If there are several matching definitions, the first one takes
    precedence" (spec.commonmark.org/0.31.2/#link-reference-definition).

    Taking the last definition instead would report the wrong destination,
    and would clear a genuinely broken first definition whenever a later
    duplicate happens to resolve.
    """
    target = write(tmp_path, "adr/ADR-005-real.md", "# target\n")
    doc = write(
        tmp_path,
        "adr/index.md",
        "See [ADR-005][decision].\n\n"
        "[decision]: ./ADR-005-gone.md\n"
        "[decision]: ./ADR-005-real.md\n",
    )

    findings = find_broken_adr_links(
        tmp_path, files=[doc], baseline=set(), tracked=frozenset({target})
    )

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-005-gone.md"


def test_a_definition_that_precedes_nothing_still_resolves_a_later_reference(
    tmp_path: Path,
) -> None:
    """Edge: definitions are collected file-wide before any line is scanned.

    CommonMark places no ordering constraint between a reference and its
    definition, so a definition at the bottom of a long document resolves a
    reference at the top. Scanning line by line without a definitions pass
    would miss every such link.
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        "See [ADR-005][decision].\n" + ("filler\n" * 20) + "[decision]: ./ADR-005-gone.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].line == 1


def test_a_definition_inside_a_fence_is_an_illustration_not_a_definition(
    tmp_path: Path,
) -> None:
    """Edge: fenced content is example text, so a definition there defines nothing."""
    doc = write(
        tmp_path,
        "docs/example.md",
        "See [ADR-005][decision].\n\n```\n[decision]: ./ADR-005-gone.md\n```\n",
    )

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_an_unreferenced_definition_produces_no_finding(tmp_path: Path) -> None:
    """Edge: a renderer drops an unreferenced definition, so it is not a link."""
    doc = write(tmp_path, "adr/index.md", "Prose only.\n\n[decision]: ./ADR-005-gone.md\n")

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_a_full_reference_is_not_also_counted_as_a_shortcut(tmp_path: Path) -> None:
    """Edge: ``[ADR-005][ADR-005]``'s second bracket is the label, not a link.

    Both brackets carry a defined label here, so a shortcut pass that did not
    exclude spans already consumed by the full-reference pass would report the
    one broken link twice and require two baseline entries to silence one
    defect.
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        "See [ADR-005][ADR-005].\n\n[ADR-005]: ./ADR-005-gone.md\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]


def test_a_task_list_checkbox_is_not_a_shortcut_reference(tmp_path: Path) -> None:
    """Edge: ``- [ ]`` normalizes to an empty label, which CommonMark forbids.

    "A link label must contain at least one character that is not a space,
    tab, or line ending" (spec.commonmark.org/0.31.2/#link-label), so an
    empty-normalizing label must match no definition even when a
    whitespace-only definition is present.
    """
    doc = write(tmp_path, "adr/index.md", "- [ ] todo\n\n[ ]: ./ADR-005-gone.md\n")

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


def test_a_reference_link_to_a_non_adr_target_is_ignored(tmp_path: Path) -> None:
    """Edge: the ADR-basename filter applies to the reference path too.

    Without it, every reference-style link in the corpus would be resolved
    and reported, not just the ADR ones this gate owns.
    """
    doc = write(tmp_path, "adr/index.md", "See [the readme][r].\n\n[r]: ./README-gone.md\n")

    assert find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset()) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("decision", "decision"),
        ("Decision", "decision"),
        ("  decision   record ", "decision record"),
        ("DECISION\tRECORD", "decision record"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_label(raw: str, expected: str) -> None:
    assert normalize_label(raw) == expected


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


def test_a_shorter_run_of_the_same_fence_character_does_not_close_it(tmp_path: Path) -> None:
    """CommonMark requires the closing run to be at least as long as the
    opener. A four-backtick fence containing a three-backtick line (a
    transcript illustrating a ```` ``` ```` example) must not be closed by
    that shorter run: only a run of four or more backticks closes it. Tracking
    only the fence character, not its length, gets this backwards the same
    way a same-character/different-length pair always does: it reports the
    still-fenced ADR-999 as broken and skips the real ADR-998 defect past the
    true close, because the three-backtick line flips the scanner out of the
    fence early and the real four-backtick close flips it back in (Copilot,
    PR #5209 round-7 review).
    """
    doc = write(
        tmp_path,
        "docs/example.md",
        "````\n"
        "```\n"
        "[ADR-999](./ADR-999-does-not-exist.md)\n"
        "````\n"
        "[ADR-998](./ADR-998-nope.md)\n",
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


def test_a_fence_shaped_line_with_trailing_text_does_not_close_it(tmp_path: Path) -> None:
    """CommonMark's closing fence takes no info string: only spaces or tabs
    may follow the marker. A ```` ```python ```` line inside an already-open
    ``` block is content (an inner example showing a fenced code sample), not
    a close, even though its character and length match the opener. Treating
    any matching fence-shaped line as a close regardless of trailing text
    gets this backwards on both ends: it closes on the inner ```` ```python
    ```` line, so the still-fenced ADR-999 example is scanned as broken (false
    positive), and it then reopens on the real closing fence, swallowing the
    live ADR-998 link that follows into a fence that never closes (false
    negative), (Copilot, PR #5209 round-9 review).
    """
    doc = write(
        tmp_path,
        "docs/example.md",
        "```\n"
        "```python\n"
        "[ADR-999](./ADR-999-does-not-exist.md)\n"
        "```\n"
        "[ADR-998](./ADR-998-nope.md)\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-998-nope.md"


def test_a_four_space_indented_fence_marker_does_not_open_a_fence(tmp_path: Path) -> None:
    """CommonMark caps fence indentation at three spaces; a four-space-indented
    marker is an indented code block, not a fence opener (spec.commonmark.org/
    0.31.2/#fenced-code-blocks: "preceded by up to three spaces of
    indentation"; the spec's own example 134 states "Four spaces of
    indentation is too many"). Before this fix, `FENCE`'s unbounded `\\s*`
    matched the four-space-indented marker anyway, putting the scanner into
    fence mode and silently hiding the broken ADR-999 link that follows in
    what CommonMark actually treats as live prose (Copilot, PR #5209
    round-10 review).
    """
    doc = write(
        tmp_path,
        "docs/example.md",
        "    ```\n"
        "[ADR-999](./ADR-999-does-not-exist.md)\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-999-does-not-exist.md"


def test_a_three_space_indented_fence_marker_still_opens_a_fence(tmp_path: Path) -> None:
    """The three-space boundary is inclusive: CommonMark allows up to three
    spaces of indentation on a fence, so a three-space-indented marker still
    opens one and content inside is still skipped.
    """
    doc = write(
        tmp_path,
        "docs/example.md",
        "   ```\n"
        "[ADR-999](./ADR-999-does-not-exist.md)\n"
        "   ```\n",
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert findings == []


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


def test_scan_file_raises_on_invalid_utf8_content(tmp_path: Path) -> None:
    """A malformed byte inside a tracked file is a defect to surface, not paper over.

    ``errors="replace"`` on this read (removed) would silently substitute
    U+FFFD for the bad byte and scan the file as if it were valid text,
    which can hide exactly the byte that broke a link's destination, or turn
    a genuinely broken link into one that happens to re-parse as resolvable
    (Copilot, PR #5209 round-6 review). This is a plain file read, not one of
    the ``subprocess`` text-capture calls issue #4261's convention binds
    (``check_subprocess_encoding.py`` scans only ``subprocess`` module
    calls), so strict decoding is the correct default here, and `main()`
    already has a `UnicodeDecodeError` handler (exit 2) for exactly this.
    """
    path = tmp_path / "adr" / "index.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"[ADR-005](\xffADR-005-gone.md)\n")

    with pytest.raises(UnicodeDecodeError):
        scan_file(tmp_path, "adr/index.md", frozenset())


def test_main_returns_two_when_a_file_has_invalid_utf8_content(tmp_path: Path, capsys) -> None:
    path = tmp_path / "adr" / "index.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"[ADR-005](\xffADR-005-gone.md)\n")
    write(tmp_path, "adr/ADR-006-present.md", "# present\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "check_adr_links:" in err
    assert "codec can't decode" in err, (
        "must reach the UnicodeDecodeError handler, not the _has_adr_corpus guard "
        "(both exit 2 with a check_adr_links: prefix; Cursor Bugbot, PR #5209 round-11 review)"
    )


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


def test_stale_allowance_is_reported_on_a_full_corpus_scan(tmp_path: Path) -> None:
    """An unused baseline entry surfaces as its own finding, not silence.

    A full-corpus scan (``files=None``, the shape ``main()`` always uses) that
    never matches a baseline entry means the defect it once allowed is
    already fixed. Leaving the entry in place is not neutral: the next
    unrelated regression that happens to produce the identical
    ``kind:file:target`` key is silently suppressed by an allowance nobody
    remembers granting (Copilot, PR #5209).
    """
    key = "unresolved:adr/index.md:ADR-005-gone.md"

    findings = find_broken_adr_links(tmp_path, baseline={key}, tracked=frozenset())

    assert len(findings) == 1
    finding = findings[0]
    assert finding.kind == "stale-allowance"
    assert finding.file == "adr/index.md"
    assert finding.target == "ADR-005-gone.md"


def test_stale_allowance_is_not_reported_on_a_narrowed_scan(tmp_path: Path) -> None:
    """A caller that explicitly narrows ``files`` is not claiming full coverage.

    Passing ``files=[...]`` scopes the scan to a subset. A baseline entry the
    scan never had a chance to visit is not evidence the entry is stale, only
    that this run did not look there; flagging it here would make every
    scoped, per-file lint run (e.g. a pre-commit hook checking staged files
    only) fail on baseline entries that belong to files outside the diff.
    """
    doc = write(tmp_path, "adr/other.md", "no links here\n")
    key = "unresolved:adr/index.md:ADR-005-gone.md"

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline={key}, tracked=frozenset())

    assert findings == []


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


def test_a_consumed_allowance_does_not_count_as_unused(tmp_path: Path) -> None:
    """Positive control: a matched entry passes a full scan with no findings at all."""
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    baseline = {"unresolved:adr/index.md:ADR-005-gone.md"}

    findings = find_broken_adr_links(
        tmp_path, baseline=baseline, tracked=frozenset({"adr/index.md"})
    )

    assert findings == []


def test_main_returns_one_on_a_stale_baseline_entry(tmp_path: Path, capsys) -> None:
    """A stale-allowance finding is a regular violation (exit 1), not a config error."""
    write(tmp_path, "adr/ADR-005-x.md", "# target\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-x.md)\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("unresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])

    assert exit_code == 1
    assert "stale-allowance" in capsys.readouterr().out


# Baseline provenance: entries must already exist at the base ref


def test_an_entry_absent_at_the_base_ref_is_rejected(tmp_path: Path) -> None:
    """The exemption set must not be fully branch-controlled.

    The baseline file's own header says "MUST NOT add an entry to clear a
    link the current change introduced" and nothing enforced it, so a branch
    could clear its own new defect by writing one line into the file it also
    controls (Copilot, PR #5209).
    """
    doc = write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    key = "unresolved:adr/index.md:ADR-005-gone.md"

    with pytest.raises(ValueError, match="this branch added"):
        find_broken_adr_links(
            tmp_path,
            files=[doc],
            baseline={key},
            tracked=frozenset(),
            base_allowances=set(),
        )


def test_an_entry_present_at_the_base_ref_is_honored(tmp_path: Path) -> None:
    """Positive control: a pre-existing allowance still suppresses its finding."""
    doc = write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    key = "unresolved:adr/index.md:ADR-005-gone.md"

    findings = find_broken_adr_links(
        tmp_path,
        files=[doc],
        baseline={key},
        tracked=frozenset(),
        base_allowances={key},
    )

    assert findings == []


def test_removing_an_entry_relative_to_the_base_ref_is_allowed(tmp_path: Path) -> None:
    """The ratchet is one-directional: repairing a link and deleting its entry
    must stay possible, or the baseline could never shrink.
    """
    doc = write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")

    findings = find_broken_adr_links(
        tmp_path,
        files=[doc],
        baseline=set(),
        tracked=frozenset(),
        base_allowances={"unresolved:other/file.md:ADR-006-gone.md"},
    )

    assert kinds(findings) == ["unresolved"]


def test_base_allowances_of_none_skips_the_provenance_check(tmp_path: Path) -> None:
    doc = write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    key = "unresolved:adr/index.md:ADR-005-gone.md"

    assert (
        find_broken_adr_links(
            tmp_path, files=[doc], baseline={key}, tracked=frozenset(), base_allowances=None
        )
        == []
    )


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
        ('<./ADR-005-x.md> "Title"', "./ADR-005-x.md"),
        ("./ADR-005-x.md#anchor", "./ADR-005-x.md"),
        ("   ", ""),
        ("<>", ""),
    ],
)
def test_split_destination(raw: str, expected: str) -> None:
    assert split_destination(raw) == expected


def test_angle_bracket_destination_with_title_is_checked_for_a_broken_target(
    tmp_path: Path,
) -> None:
    """A pointy-bracket destination followed by a title is legal CommonMark.

    ``dest.endswith(">")`` was false for this form (the title text trails
    the closing bracket), so the brackets were never stripped and the
    unstripped ``<./ADR-999-does-not-exist.md>`` failed `is_adr_target()`'s
    basename match, letting a broken link written this way bypass the gate
    entirely (Copilot, PR #5209 round-10 review).
    """
    doc = write(
        tmp_path,
        "adr/index.md",
        'See [ADR-999](<./ADR-999-does-not-exist.md> "Title").\n',
    )

    findings = find_broken_adr_links(tmp_path, files=[doc], baseline=set(), tracked=frozenset())

    assert kinds(findings) == ["unresolved"]
    assert findings[0].target == "./ADR-999-does-not-exist.md"


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
        # RFC 3986 section 3.1 defines "scheme" by shape (ALPHA followed by
        # ALPHA/DIGIT/"+"/"-"/"."), not by enumeration; a scheme outside the
        # old four-entry list must still be recognized as external rather
        # than falling through to the ADR-basename check (Copilot, PR #5209
        # round-8 review).
        ("ssh://example.invalid/ADR-005-x.md", False),
        ("git://example.invalid/ADR-005-x.md", False),
        ("SSH://example.invalid/ADR-005-x.md", False),
        # RFC 3986 section 4.2: a reference starting with two slashes is a
        # network-path reference, naming a host, not a repository path.
        ("//example.invalid/ADR-005-x.md", False),
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


def _commit_all(root: Path, message: str) -> None:
    """Stage everything under root and record one commit.

    Identity is passed with ``-c`` rather than written to the repository
    config so the commit works on a runner with no global git identity, and
    ``--no-verify`` is absent because a tmp_path repo has no hooks installed
    to bypass.
    """
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=check-adr-links-test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=root,
        check=True,
    )


def _repo_with_base(root: Path, baseline_body: str) -> Path:
    """Return a repo whose ``main`` branch carries ``baseline_body``.

    Gives the base-ref tests a real prior revision to read the baseline
    from, which is the only way to exercise ``git show`` against it.

    Includes one ADR-shaped file so ``main()``/``validate_adr_links``'s
    ``_has_adr_corpus`` guard does not reject these fixtures as "no ADR
    records found" before the base-ref logic these tests exist to exercise
    ever runs.
    """
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "baseline.txt").write_text(baseline_body, encoding="utf-8")
    write(root, "adr/index.md", "# placeholder\n")
    write(root, "adr/ADR-001-placeholder.md", "# placeholder\n")
    _commit_all(root, "base")
    return root


def test_git_ls_markdown_returns_tracked_markdown_only(tmp_path: Path) -> None:
    write(tmp_path, "docs/a.md", "# a\n")
    write(tmp_path, "docs/b.py", "x = 1\n")
    _init_repo(tmp_path)

    assert git_ls_markdown(tmp_path) == ["docs/a.md"]


@pytest.mark.skipif(
    sys.platform != "linux",
    reason=(
        "requires a filesystem that accepts arbitrary bytes in a filename; "
        "ext4 does, APFS (macOS) and NTFS (Windows) validate UTF-8 or reject "
        "the byte at create time (Cursor Bugbot, PR #5209 round-6 review)"
    ),
)
def test_git_ls_markdown_raises_on_a_non_utf8_tracked_filename(tmp_path: Path) -> None:
    """A tracked filename with an invalid UTF-8 byte must not vanish silently.

    ``git ls-files -z`` emits raw filesystem bytes; decoding them with
    ``errors="replace"`` (kept here because ``check_subprocess_encoding.py``
    mandates it for every ``subprocess.run(text=True, encoding="utf-8", ...)``
    call, issue #4261) turns the invalid byte into U+FFFD. Left unchecked,
    ``scan_file()`` builds ``repo_root / file`` from that corrupted name,
    ``Path.is_file()`` returns False for it (the real file on disk still has
    the original byte, not the replacement), and the file is scanned as zero
    findings, indistinguishable from a file that was never tracked at all
    (Copilot, PR #5209 round-6 review). Raising here instead means ``main()``
    reports the corrupted name and exits 2 rather than silently undercounting
    the scanned corpus.

    The filename byte cannot be written through ``pathlib.Path`` (it is not
    valid UTF-8, so the surrogate-escaped str round-trips through the
    filesystem but not through ordinary path construction); built as raw
    bytes instead, which ext4 accepts. This repo's own CI only runs this
    file's suite on ``ubuntu-latest``/``ubuntu-24.04-arm``
    (`.github/workflows/pytest.yml`); the Windows job filters to
    `@pytest.mark.windows_path` only, so this test was never exercised there.
    The skip guard is for local runs on other filesystems, not a CI fix.
    """
    bad_path = os.fsencode(str(tmp_path)) + b"/ADR-005-\xffgone.md"
    with open(bad_path, "wb") as handle:
        handle.write(b"# x\n")
    _init_repo(tmp_path)

    with pytest.raises(ValueError, match="non-UTF-8 byte"):
        git_ls_markdown(tmp_path)


def test_main_returns_zero_when_the_tree_is_clean(tmp_path: Path, capsys) -> None:
    write(tmp_path, "adr/ADR-005-x.md", "# target\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-x.md)\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    assert exit_code == 0
    assert "0 violation(s)" in capsys.readouterr().out


def test_main_reports_the_examined_file_count(tmp_path: Path, capsys) -> None:
    """A clean "0 violation(s)" must be distinguishable from an empty scan.

    Without the examined count, a `git_ls_markdown` regression that only
    sees a handful of tracked files (or an accidentally narrowed scope)
    prints the identical success line as a complete scan of the real corpus
    (Copilot, PR #5209 round-8 review).
    """
    write(tmp_path, "adr/ADR-005-x.md", "# target\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-x.md)\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    assert exit_code == 0
    assert "0 violation(s) across 2 tracked markdown file(s)" in capsys.readouterr().out


def test_main_fails_closed_on_a_valid_repo_with_no_tracked_markdown(
    tmp_path: Path, capsys
) -> None:
    """A wrong-but-valid repository root must not manufacture a green result.

    `repo_root` pointing at a real git repository that happens to track zero
    markdown files makes `git ls-files` succeed with empty output, so an
    unguarded scan would find nothing and print the same "0 violation(s)" a
    genuinely clean full-corpus scan prints. That is a different failure
    shape than "not a git repository at all," which the
    `subprocess.CalledProcessError` handler already covers (Copilot,
    PR #5209 round-9 review).
    """
    write(tmp_path, "not_markdown.py", "x = 1\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    err = capsys.readouterr().err
    assert exit_code == 2
    assert "no tracked markdown files found" in err


def test_validate_adr_links_fails_closed_on_a_valid_repo_with_no_tracked_markdown(
    tmp_path: Path, capsys
) -> None:
    write(tmp_path, "not_markdown.py", "x = 1\n")
    _init_repo(tmp_path)

    result = validate_adr_links(tmp_path)

    err = capsys.readouterr().err
    assert result is False
    assert "no tracked markdown files found" in err


def test_has_adr_corpus_true_when_a_scanned_file_is_adr_shaped() -> None:
    assert has_adr_corpus(["adr/ADR-005-x.md"]) is True


def test_has_adr_corpus_false_when_no_scanned_file_is_adr_shaped() -> None:
    assert has_adr_corpus(["README.md", "docs/index.md"]) is False


def test_has_adr_corpus_false_on_an_empty_scan() -> None:
    assert has_adr_corpus([]) is False


def test_has_adr_corpus_matches_regardless_of_directory_depth() -> None:
    """The sentinel is a basename check, not a path check.

    `check_adr_links.py` scans tracked markdown repo-wide (see the module
    docstring's four violation classes), so a real ADR record can sit
    anywhere a rename or reorganization left it. Anchoring the sentinel to a
    directory would reject a real corpus the moment its layout changed.
    """
    assert has_adr_corpus(["nested/deeply/here/ADR-100-x.md"]) is True


def test_main_fails_closed_on_a_valid_repo_with_markdown_but_no_adr_corpus(
    tmp_path: Path, capsys
) -> None:
    """A wrong-but-plausible repository root must not manufacture a green result.

    The round-9 guard alone only rejects zero tracked markdown files of any
    kind, so an unrelated-yet-valid git repository containing a bare
    `README.md` still passed it with a manufactured "0 violation(s)"
    (Copilot, PR #5209 round-11 review).
    """
    write(tmp_path, "README.md", "# Some other project\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    err = capsys.readouterr().err
    assert exit_code == 2
    assert "no ADR records found" in err


def test_validate_adr_links_fails_closed_on_a_valid_repo_with_markdown_but_no_adr_corpus(
    tmp_path: Path, capsys
) -> None:
    write(tmp_path, "README.md", "# Some other project\n")
    _init_repo(tmp_path)

    result = validate_adr_links(tmp_path)

    err = capsys.readouterr().err
    assert result is False
    assert "no ADR records found" in err


def test_validate_adr_links_reports_the_examined_file_count(tmp_path: Path, capsys) -> None:
    write(tmp_path, "adr/ADR-005-x.md", "# target\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-x.md)\n")
    _init_repo(tmp_path)

    result = validate_adr_links(tmp_path)

    assert result is True
    assert "0 violation(s) across 2 tracked markdown file(s)" in capsys.readouterr().out


def test_main_returns_one_when_a_link_is_broken(tmp_path: Path, capsys) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    write(tmp_path, "adr/ADR-006-present.md", "# present\n")
    _init_repo(tmp_path)

    exit_code = main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "none.txt")])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "adr/index.md:1: unresolved: ADR-005-gone.md" in out
    assert "1 violation(s)" in out


def test_main_honors_a_baseline_file(tmp_path: Path) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    write(tmp_path, "adr/ADR-006-present.md", "# present\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# reason\nunresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8")
    _init_repo(tmp_path)

    assert main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 0


def test_main_resolves_a_relative_baseline_against_the_repo_root(tmp_path: Path) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    write(tmp_path, "adr/ADR-006-present.md", "# present\n")
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


def test_resolve_base_ref_returns_none_when_no_candidate_resolves(tmp_path: Path) -> None:
    """A repo with no commits has no ``main`` and no remote, so nothing resolves."""
    _init_repo(tmp_path)

    assert resolve_base_ref(tmp_path) is None


def test_resolve_base_ref_finds_the_local_default_branch(tmp_path: Path) -> None:
    _repo_with_base(tmp_path, "")

    assert resolve_base_ref(tmp_path) == "main"


def test_baseline_entries_at_ref_reads_the_committed_baseline(tmp_path: Path) -> None:
    _repo_with_base(tmp_path, "# comment\nunresolved:adr/index.md:ADR-005-gone.md\n\n")

    entries = baseline_entries_at_ref(tmp_path, "main", tmp_path / "baseline.txt")

    assert entries == {"unresolved:adr/index.md:ADR-005-gone.md"}


def test_baseline_entries_at_ref_returns_none_when_the_file_is_new(tmp_path: Path) -> None:
    """A branch that introduces the baseline has nothing to ratchet against.

    That case must stay distinguishable from an unreadable baseline, which
    raises: returning ``None`` for both would let a genuine read failure
    silently disable the provenance check.
    """
    _repo_with_base(tmp_path, "")

    assert baseline_entries_at_ref(tmp_path, "main", tmp_path / "absent.txt") is None


def test_baseline_entries_at_ref_raises_when_the_blob_exists_but_cannot_be_read(
    tmp_path: Path, monkeypatch
) -> None:
    """A baseline this gate cannot read is a config error, not a free pass.

    ``git cat-file -e`` already said the blob is there, so a failing
    ``git show`` is a real read failure (a corrupt object, a pack error).
    Returning ``None`` there instead would silently disable the provenance
    check on exactly the runs where the evidence is missing. The git
    boundary is stubbed because no reachable repository state makes
    ``cat-file`` succeed and ``show`` fail on the same revision.
    """
    _repo_with_base(tmp_path, "unresolved:adr/index.md:ADR-005-gone.md\n")
    real_run_git = check_adr_links._run_git

    def failing_show(repo_root: Path, args: list[str]):
        if args and args[0] == "show":
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad object")
        return real_run_git(repo_root, args)

    monkeypatch.setattr(check_adr_links, "_run_git", failing_show)

    with pytest.raises(ValueError, match="fatal: bad object"):
        baseline_entries_at_ref(tmp_path, "main", tmp_path / "baseline.txt")


def test_baseline_entries_at_ref_rejects_a_path_outside_the_repository(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_base(repo, "")

    with pytest.raises(ValueError, match="outside the repository root"):
        baseline_entries_at_ref(repo, "main", tmp_path / "elsewhere.txt")


def test_base_allowances_for_run_disables_on_none(tmp_path: Path) -> None:
    _repo_with_base(tmp_path, "unresolved:adr/index.md:ADR-005-gone.md\n")

    assert base_allowances_for_run(tmp_path, tmp_path / "baseline.txt", "none") is None


def test_base_allowances_for_run_auto_resolves_the_default_branch(tmp_path: Path) -> None:
    _repo_with_base(tmp_path, "unresolved:adr/index.md:ADR-005-gone.md\n")

    entries = base_allowances_for_run(tmp_path, tmp_path / "baseline.txt", "auto")

    assert entries == {"unresolved:adr/index.md:ADR-005-gone.md"}


def test_base_allowances_for_run_says_so_when_no_base_ref_resolves(
    tmp_path: Path, capsys
) -> None:
    """Silence here would read as "ratcheted and clean". It is not."""
    _init_repo(tmp_path)

    assert base_allowances_for_run(tmp_path, tmp_path / "baseline.txt", "auto") is None
    assert "no base ref resolved" in capsys.readouterr().err


def test_base_allowances_for_run_says_so_when_the_baseline_is_new(
    tmp_path: Path, capsys
) -> None:
    _repo_with_base(tmp_path, "")

    assert base_allowances_for_run(tmp_path, tmp_path / "absent.txt", "auto") is None
    assert "does not exist at main" in capsys.readouterr().err


def test_main_returns_two_when_this_branch_added_a_baseline_entry(
    tmp_path: Path, capsys
) -> None:
    """End to end: a branch cannot clear its own new defect with a new entry."""
    _repo_with_base(tmp_path, "# no entries yet\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    (tmp_path / "baseline.txt").write_text(
        "unresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    exit_code = main(
        ["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "baseline.txt")]
    )

    assert exit_code == 2
    assert "this branch added" in capsys.readouterr().err


def test_main_honors_an_entry_the_base_ref_already_carried(tmp_path: Path) -> None:
    """Positive control: the same entry, committed at the base ref, still works."""
    _repo_with_base(tmp_path, "unresolved:adr/index.md:ADR-005-gone.md\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    assert (
        main(["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "baseline.txt")]) == 0
    )


def test_main_base_ref_none_disables_the_provenance_check(tmp_path: Path) -> None:
    _repo_with_base(tmp_path, "# no entries yet\n")
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    (tmp_path / "baseline.txt").write_text(
        "unresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--baseline",
            str(tmp_path / "baseline.txt"),
            "--base-ref",
            "none",
        ]
    )

    assert exit_code == 0


def test_validate_adr_links_ratchets_against_the_base_ref(tmp_path: Path, capsys) -> None:
    """``pre_pr.py``'s entry point runs the provenance check, not just the CLI.

    A guard reachable only through a flag no gate passes is not a guard;
    ``validate_adr_links`` is what ``pre_pr.py`` calls.
    """
    default_baseline = tmp_path / check_adr_links.DEFAULT_BASELINE
    default_baseline.parent.mkdir(parents=True, exist_ok=True)
    default_baseline.write_text("# no entries yet\n", encoding="utf-8")
    _repo_with_base(tmp_path, "")

    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    default_baseline.write_text("unresolved:adr/index.md:ADR-005-gone.md\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    with pytest.raises(ValueError, match="this branch added"):
        validate_adr_links(tmp_path)

    capsys.readouterr()


def test_validate_adr_links_reports_a_bool(tmp_path: Path) -> None:
    write(tmp_path, "adr/index.md", "[ADR-005](ADR-005-gone.md)\n")
    write(tmp_path, "adr/ADR-006-present.md", "# present\n")
    _init_repo(tmp_path)

    assert validate_adr_links(tmp_path) is False


# Corpus: the gate must pass against the real tree (ci-scripts.md MUST 13)


def test_gate_passes_against_the_repository_corpus() -> None:
    findings = find_broken_adr_links(REPO_ROOT)

    assert findings == [], "\n".join(finding.format() for finding in findings)


def test_baseline_header_counts_match_the_live_file() -> None:
    """The baseline file's own header comment must not drift from its content.

    Round 5 removed a stale ``absolute`` entry (the fixed
    ``docs/search-dont-load.md`` link) but left the header comment's "twenty
    entries, three absolute" claim unchanged, dropping the real counts to
    19 and 2 without anyone noticing (Copilot, PR #5209 round-6 review).
    Asserting the counts directly against the file, rather than re-reading
    the comment and trusting it, means a future edit that changes the entry
    count without updating the header fails this test instead of drifting
    silently again.
    """
    baseline_path = REPO_ROOT / check_adr_links.DEFAULT_BASELINE
    lines = baseline_path.read_text(encoding="utf-8").splitlines()
    entries = [line for line in (raw.strip() for raw in lines) if line and not line.startswith("#")]
    absolute_entries = [entry for entry in entries if entry.startswith("absolute:")]

    header = "\n".join(lines[:20])
    assert f"{len(absolute_entries)} of the {len(entries)} entries" in header, (
        f"baseline has {len(entries)} entries ({len(absolute_entries)} absolute), "
        "but the header comment does not say so; update the comment to match"
    )
