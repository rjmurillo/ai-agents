"""Enforcement messages must not tell their reader to apply a human-only label.

Issue #4782: the pre-push needs-split gate printed ``use commit-limit-bypass to
override the ceiling entirely``. That label is reserved for a human maintainer,
so the gate was instructing whoever tripped it to grant themselves a permission
they do not hold, and it arrived from the enforcement mechanism itself, which is
what makes an agent read it as sanctioned remediation. One did: an agent working
PR #4735 applied the label to that PR on 2026-08-08 after hitting this gate.

Canonical authority: ``CONTRIBUTING.md``. Two lines, quoted verbatim:

  1. A human maintainer MUST add the `commit-limit-bypass` label
  1. A human maintainer MUST add the `description-validation-bypass` label (case-insensitive match)

They sit under the headings ``#### Bypassing the Limit`` and
``#### Bypassing Description Validation``, which are the sections the three
enforcement messages cite by name. ``test_contributing_declares_both_labels_
human_only`` pins both the declarations and the headings, so a rename in
``CONTRIBUTING.md`` fails here rather than leaving three dangling citations.

The two surfaces pinned below are the complete set of runtime messages in the
tree that name either label, measured with
``grep -rn "commit-limit-bypass\\|description-validation-bypass" --include=*.py
scripts/``: the CI blocker and the description validator. The local pre-push
gate (`scripts/validation/git_hook_policy.py:_check_commit_limit`) no longer
names or defers to either label at all; per ADR-100 ("retire the pull request
size ceilings") it was demoted to a report that never blocks, so it has
nothing left to guide a reader toward and dropped out of this file's scope
(issue #5232). The remaining hits in that grep are comments and
``pr_commit_count.py`` (which defers enforcement without naming a remedy).

Stricter than canonical: ``CONTRIBUTING.md`` states who may add the label.
These messages additionally state who may NOT, because the load-bearing half for
an autonomous reader is the prohibition, not the permission.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.validation.pr_description import DEFAULT_BYPASS_LABEL, validate_pr_description

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"
GOTCHAS = REPO_ROOT / ".agents" / "governance" / "GOTCHAS.md"

# An instruction to the reader: an imperative verb followed, inside the same
# sentence, by the label name. `[^.]` cannot cross a sentence boundary, so a
# message that names the label in a fresh sentence ("... . The 'X' label lifts
# the ceiling, but ...") does not match, while every pre-#4782 message does:
#   "use commit-limit-bypass to override the ceiling entirely"
#   "Add 'commit-limit-bypass' label to override or split this PR."
#   "For unrecoverable cases, apply the 'description-validation-bypass' label"
_SELF_SERVICE_INSTRUCTION = re.compile(
    r"(?i)\b(?:use|add|apply|set)\b[^.]{0,30}?"
    r"(?:commit-limit-bypass|description-validation-bypass)"
)


def _assert_defers_to_a_maintainer(message: str, label: str, sanctioned_action: str) -> None:
    """Assert one enforcement message states the constraint, not the bypass.

    Four properties, all of which the pre-#4782 wording failed on at least one
    surface: the message names a sanctioned action the reader may take, names
    the label's authority, forbids self-application in words, and never reads as
    an instruction to apply the label.
    """
    assert sanctioned_action.lower() in message.lower(), f"no sanctioned action offered: {message}"
    assert "human maintainer" in message, f"authority not named: {message}"
    assert "do not apply it yourself" in message, f"prohibition missing: {message}"
    assert label in message, f"label not named at all: {message}"
    match = _SELF_SERVICE_INSTRUCTION.search(message)
    assert match is None, f"reads as an instruction to apply the label: {match} in {message}"


_LABEL_SECTIONS = (
    ("commit-limit-bypass", "#### Bypassing the Limit"),
    ("description-validation-bypass", "#### Bypassing Description Validation"),
)


def _section_body(lines: Sequence[str], heading: str) -> str:
    """Return the lines under `heading`, up to the next heading of any level.

    A markdown heading line starts with one or more `#` characters. Slicing
    to the next such line (or EOF) bounds the section so a caller can assert
    a declaration is *inside* the cited section, not merely present somewhere
    in the whole document.
    """
    start = lines.index(heading) + 1
    for offset, line in enumerate(lines[start:]):
        if line.startswith("#"):
            return "\n".join(lines[start : start + offset])
    return "\n".join(lines[start:])


def test_contributing_declares_both_labels_human_only() -> None:
    """The cited authority still says what the three messages claim it says.

    Scoped to the section named by each message: a declaration existing
    anywhere in the file is not enough, because the runtime messages cite a
    specific section by name. If the declaration moved to a different
    section while the old heading survived elsewhere in the file, an
    unscoped `in text` check would still pass and the message's citation
    would go stale silently.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    for label, heading in _LABEL_SECTIONS:
        assert heading in lines, f"messages cite a section that no longer exists: {heading}"
        section = _section_body(lines, heading)
        assert f"A human maintainer MUST add the `{label}` label" in section, (
            f"CONTRIBUTING.md's {heading!r} section no longer declares {label} "
            "human-only; the enforcement messages citing that section are now wrong"
        )


def test_contributing_never_instructs_without_naming_the_authority() -> None:
    """Prose an agent reads before acting carries the same obligation.

    Weaker than the runtime-message rule above, and deliberately so: a
    contributor guide may tell the reader to obtain the label, provided the same
    line says who grants it. What it may not do is pair an imperative with the
    label name and leave the authority to another paragraph, which is how
    CONTRIBUTING.md read before this change ("You MUST either split the PR or
    add the `commit-limit-bypass` label", "apply the
    `description-validation-bypass` label").

    Scope is reported with the finding count per `.claude/rules/testing.md`
    MUST 10: every line of the file is examined, not a subset.
    """
    lines = CONTRIBUTING.read_text(encoding="utf-8").splitlines()
    offenders = [
        (number, line)
        for number, line in enumerate(lines, start=1)
        if _SELF_SERVICE_INSTRUCTION.search(line) and "human maintainer" not in line
    ]
    assert not offenders, (
        f"{len(offenders)} of {len(lines)} CONTRIBUTING.md lines name a "
        f"human-only label as an action without naming who may take it: {offenders}"
    )


_GOTCHAS_BYPASS_HEADING = "## The push blocks at 21 commits, and the check runs at push time"


def test_gotchas_defers_the_commit_limit_bypass_to_a_maintainer() -> None:
    """The commit-limit-bypass entry an agent reads mid-session carries the constraint.

    Direct guard, added because no test in this file previously opened
    `GOTCHAS.md`: an earlier QA report claimed this suite pinned the entry
    while no assertion here read the file. `GOTCHAS.md` names only
    `commit-limit-bypass` (``grep -n "commit-limit-bypass\\|description-
    validation-bypass" .agents/governance/GOTCHAS.md`` returns one hit, at
    line 251), so this guard checks the one label the file actually names,
    scoped to the section that carries it.

    Also pins the fix for a self-contradiction a review caught: the entry
    used to say relief was the label "and nothing else", while its own
    closing sentence and the canonical source it cites
    (``CONTRIBUTING.md:854``: "You MUST split the PR, or ask a human
    maintainer to decide on the `commit-limit-bypass` label") both name
    splitting as an equally sanctioned path. The assertion that
    `"and nothing else"` is absent is a regression guard for that specific
    false-exclusivity claim, not a general style check.
    """
    lines = GOTCHAS.read_text(encoding="utf-8").splitlines()
    assert _GOTCHAS_BYPASS_HEADING in lines, (
        f"GOTCHAS.md renamed or removed the section this guard pins: {_GOTCHAS_BYPASS_HEADING!r}"
    )
    section = _section_body(lines, _GOTCHAS_BYPASS_HEADING)
    assert "human maintainer" in section, (
        "GOTCHAS.md no longer names the maintainer authority for commit-limit-bypass"
    )
    assert "split the PR" in section, "GOTCHAS.md dropped the split-the-PR sanctioned path"
    assert "and nothing else" not in section, (
        "GOTCHAS.md again claims the label is the only relief, contradicting "
        "the split-the-PR path named in the same entry and in CONTRIBUTING.md:854"
    )
    assert "do not apply it yourself" in section, "GOTCHAS.md prohibition missing"
    match = _SELF_SERVICE_INSTRUCTION.search(section)
    assert match is None, f"reads as an instruction to apply the label: {match} in {section}"


def _load_enforcer():
    """Load scripts/ci/enforce_pr_validation.py the way its own tests do."""
    path = REPO_ROOT / "scripts" / "ci" / "enforce_pr_validation.py"
    spec = importlib.util.spec_from_file_location("enforce_pr_validation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["enforce_pr_validation"] = module
    spec.loader.exec_module(module)
    return module


def _blocked_ci_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERALL_STATUS", "PASS")
    monkeypatch.setenv("COMMIT_STATUS", "BLOCKED")
    monkeypatch.setenv("COMMIT_COUNT", "21")
    monkeypatch.setenv("COMMIT_LIMIT", "20")
    monkeypatch.setenv("PR_NUMBER", "4735")
    monkeypatch.setenv("GITHUB_REPOSITORY", "rjmurillo/ai-agents")


def test_ci_blocker_defers_the_bypass_to_a_maintainer(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The CI half of the same gate, driven through its CLI entrypoint."""
    enforcer = _load_enforcer()
    _blocked_ci_env(monkeypatch)
    monkeypatch.setattr(enforcer, "_fetch_labels", lambda _repository, _pr: (0, ["bug"]))

    assert enforcer.main() == 1

    stderr = capsys.readouterr().err
    assert "::error::PR has 21 commits (limit: 20)." in stderr
    _assert_defers_to_a_maintainer(stderr, "commit-limit-bypass", "split")
    # A workflow-command annotation is one line; an embedded newline splits it
    # and GitHub renders only the first fragment.
    assert stderr.strip().count("\n") == 0, f"annotation is not a single line: {stderr!r}"


def test_ci_blocker_stays_silent_when_the_bypass_label_is_already_present(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No over-fire: a maintainer's decision already recorded needs no lecture."""
    enforcer = _load_enforcer()
    _blocked_ci_env(monkeypatch)
    monkeypatch.setattr(
        enforcer, "_fetch_labels", lambda _repository, _pr: (0, ["commit-limit-bypass"])
    )

    assert enforcer.main() == 0

    captured = capsys.readouterr()
    assert "do not apply it yourself" not in captured.out + captured.err


def test_description_validator_defers_its_bypass_label_to_a_maintainer() -> None:
    """Same shape, second human-only label (CONTRIBUTING.md:909)."""
    issues = validate_pr_description(
        pr_files=["scripts/validation/pr_description.py"],
        mentioned_files=["docs/not-in-this-diff.md"],
    )

    criticals = [issue for issue in issues if issue.severity == "CRITICAL"]
    assert len(criticals) == 1, f"expected 1 CRITICAL in {len(issues)} issues: {issues}"
    _assert_defers_to_a_maintainer(criticals[0].message, DEFAULT_BYPASS_LABEL, "Move the path")


def test_description_validator_names_no_bypass_when_every_mention_is_in_the_diff() -> None:
    """No over-fire: the passing path never mentions the label."""
    issues = validate_pr_description(
        pr_files=["scripts/validation/pr_description.py"],
        mentioned_files=["scripts/validation/pr_description.py"],
    )

    assert not [issue for issue in issues if DEFAULT_BYPASS_LABEL in issue.message], issues
