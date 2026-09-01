"""Pins the Issue #5210 decision for investigation-claim-backstop.yml.

Issue #5210 found that pr-validation.yml called post_issue_comment.py without
--update-if-exists, so a fixed PR kept showing its first failing verdict
forever. The issue named a second caller of the same script,
investigation-claim-backstop.yml, and required it be "explicitly decided,
either flagged as intentionally write-once with a comment saying so, or given
the flag" rather than silently left ambiguous.

This repo decided write-once is correct there: unlike pr-validation.yml,
the "Post Warning on Violations" step only runs `if: failure()` and never
re-posts once the PR is fixed, so there is no stale-PASS-shown-as-FAIL
failure mode to correct. These tests pin that decision so a future edit
cannot silently drop the explanation or add the flag without updating this
test to match.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "investigation-claim-backstop.yml"

_STEP_NAME = "Post Warning on Violations"


def _post_warning_step() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["validate-claims"]["steps"]
    matching = [step for step in steps if step.get("name") == _STEP_NAME]
    assert len(matching) == 1, "expected exactly one 'Post Warning on Violations' step"
    return matching[0]


def _extract_step_block(text: str, step_name: str) -> str:
    """Return the raw YAML text spanning only the named list-item step.

    ``yaml.safe_load`` strips comments, so a rationale comment above a step's
    ``run:`` key is invisible to the parsed structure. This finds the step by
    its ``- name:`` line and its list-item indentation, then cuts the block
    off at the next sibling ``- name:`` at the same indentation (or end of
    text), so a check against the result proves content sits with THIS step
    and not merely somewhere else in the document.
    """
    start_match = re.search(
        rf"^([ \t]*)- name: {re.escape(step_name)}\s*$", text, flags=re.MULTILINE
    )
    assert start_match is not None, f"could not locate the {step_name!r} step"
    indent = start_match.group(1)
    next_sibling = re.search(
        rf"^{re.escape(indent)}- name:", text[start_match.end() :], flags=re.MULTILINE
    )
    end = start_match.end() + next_sibling.start() if next_sibling else len(text)
    return text[start_match.start() : end]


def _post_warning_step_raw_block() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    return _extract_step_block(text, _STEP_NAME)


def test_the_write_once_decision_is_intentional_not_an_oversight() -> None:
    """Positive: the step must not silently gain --update-if-exists.

    If a future change adds the flag here, it should be a deliberate
    decision (with this test updated to match), not a drive-by copy from
    pr-validation.yml's fix.
    """
    run = _post_warning_step().get("run", "")
    assert "post_issue_comment.py" in run
    assert "--marker \"INVESTIGATION-CLAIM-BACKSTOP\"" in run
    assert "--update-if-exists" not in run


def test_the_decision_is_documented_next_to_the_step() -> None:
    """Positive: the rationale must be readable at the call site, not only
    in the issue tracker, per Issue #5210's acceptance criteria.

    Scoped to this step's own raw text block, not the whole workflow file:
    a whole-file substring check would still pass if the comment moved to an
    unrelated job or a stray comment elsewhere, which would not prove the
    rationale sits next to THIS step as its name and this test's docstring
    both claim.
    """
    step_block = _post_warning_step_raw_block()
    assert "Intentionally write-once" in step_block
    assert "#5210" in step_block


def test_step_block_extraction_stops_at_the_next_sibling_step() -> None:
    """Negative control on ``_extract_step_block`` itself, via synthetic YAML.

    ``Post Warning on Violations`` is the last step in the real workflow, so
    there is no real sibling after it to prove scoping against. Without this
    control, an unbounded extraction (grabs to end of text) would look
    identical to a correctly bounded one on the real file, and the positive
    test above would pass for the wrong reason. This drives the extractor on
    a two-step fixture where content belongs unambiguously to one step or
    the other.
    """
    text = (
        "    steps:\n"
        "      - name: Post Warning on Violations\n"
        "        # Intentionally write-once, decided per Issue #5210.\n"
        "        run: echo one\n"
        "      - name: Set Job Summary\n"
        "        run: echo two\n"
    )
    block = _extract_step_block(text, "Post Warning on Violations")
    assert "Intentionally write-once" in block
    assert "#5210" in block
    assert "Set Job Summary" not in block
    assert "echo two" not in block


def test_step_block_extraction_finds_content_between_two_steps() -> None:
    """Positive companion to the control above: the middle step is not lost.

    Guards against an over-correction (e.g. stopping at ANY ``- name:``,
    including one nested inside the target step) that would make the
    extractor return an empty or truncated block for a step sandwiched
    between two siblings.
    """
    text = (
        "    steps:\n"
        "      - name: First\n"
        "        run: echo first\n"
        "      - name: Post Warning on Violations\n"
        "        # Intentionally write-once, decided per Issue #5210.\n"
        "        run: echo middle\n"
        "      - name: Set Job Summary\n"
        "        run: echo last\n"
    )
    block = _extract_step_block(text, "Post Warning on Violations")
    assert "echo middle" in block
    assert "echo first" not in block
    assert "echo last" not in block


def test_the_step_only_fires_on_failure() -> None:
    """Edge: the decision's justification depends on this condition holding.

    Write-once is safe here only because the step never re-posts on a
    passing re-run. If this step ever stops being failure-gated, it inherits
    the same stale-verdict bug pr-validation.yml had, and the write-once
    decision above must be revisited.
    """
    condition = _post_warning_step().get("if")
    assert condition is not None and "failure()" in condition


def test_the_step_does_not_fire_on_an_earlier_setup_failure() -> None:
    """Edge: a bare `failure()` also fires when checkout or setup fails.

    A job-wide `failure()` posts a false investigation-claim violation
    comment for what is really an infrastructure failure (checkout, env
    setup, or the git-log step) with no violation to report. Scoping to the
    validator step's own outcome is what makes the "point-in-time violation
    alert" framing in the comment above the step (and in the posted comment
    body) actually true.
    """
    condition = _post_warning_step().get("if")
    assert condition == "failure() && steps.validate.outcome == 'failure'"


def test_the_step_exports_the_pr_head_sha() -> None:
    """Positive: the posted comment needs the triggering commit available.

    Without `HEAD_SHA` in the step's `env:`, the `printf` call below has
    nothing to interpolate and the "As of commit ..." wording (pinned by
    ``test_the_comment_self_identifies_as_a_point_in_time_record`` below)
    could not exist.
    """
    env = _post_warning_step().get("env", {})
    assert env.get("HEAD_SHA") == "${{ github.event.pull_request.head.sha }}"


def test_the_comment_self_identifies_as_a_point_in_time_record() -> None:
    """Positive: pins the fix for the present-tense-staleness review finding.

    Reverting the `printf`/`HEAD_SHA` hunk while keeping the surrounding
    heredoc would leave this suite green on every other test here (the
    write-once decision, the failure-scoping, and the rationale comment all
    still hold), silently reintroducing the exact defect a reviewer flagged:
    a warning that reads as current status long after the PR was fixed. This
    test is what actually breaks if that hunk disappears.
    """
    step_block = _post_warning_step_raw_block()
    assert 'HEAD_SHA:0:12' in step_block
    assert "As of commit `%s`, this PR contained" in step_block
    # The old present-tense claim, unqualified by a commit reference, must
    # not survive: that exact phrasing is what made the comment read as a
    # live status instead of a point-in-time record.
    assert "This PR contains session logs" not in step_block


def test_the_sha_interpolation_uses_printf_not_the_heredoc() -> None:
    """Edge: pins the shell-injection fix, not just its visible symptom.

    The vulnerable shape (`cat <<EOF`, unquoted, with `$HEAD_SHA` inside a
    markdown body full of backticks) would satisfy the two tests above too,
    since the rendered text can look identical until the shell actually
    tries to expand it. Assert on the mechanism: the interpolation happens
    in a `printf` call, and the static markdown heredoc stays quoted.
    """
    step_block = _post_warning_step_raw_block()
    assert re.search(r"printf\s+'[^']*%s[^']*'\s+\"\$\{HEAD_SHA:0:12\}\"", step_block)
    # Every actual heredoc redirect must be the quoted form. An unquoted
    # `<<EOF` would shell-expand the markdown body, including every
    # backtick-wrapped code span in it. Scanned line-by-line, skipping `#`
    # comment lines: this rationale comment's own prose mentions the bare
    # `<<EOF` syntax in quotes, which would otherwise false-positive.
    code_lines = [
        line for line in step_block.splitlines() if not line.strip().startswith("#")
    ]
    heredoc_redirects = re.findall(r"<<-?'?\"?EOF'?\"?", "\n".join(code_lines))
    assert heredoc_redirects, "expected at least one heredoc redirect in the step"
    assert all(redirect in ("<<'EOF'", '<<"EOF"') for redirect in heredoc_redirects)
