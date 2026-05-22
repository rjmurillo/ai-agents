"""Tests for ``scripts/validation/check_build_gates.py``.

Lock the contract that ``.claude/commands/build.md`` keeps the three
mandatory exit-gate skill invocations and the ``Mandatory Exit Gates``
section heading. PR #1887's retrospective documents the failure mode the
script defends against.

Most tests use temporary file trees so the result does not depend on
whether someone has just edited build.md. ``test_real_repo_build_md_passes``
is the deliberate exception: it runs against the real
``.claude/commands/build.md`` to guard against regressions in the
file itself, complementing the synthetic fixtures.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_build_gates.py"


def _load_module():
    """Load the script as a module under a stable name."""
    spec = importlib.util.spec_from_file_location(
        "check_build_gates",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cbg = _load_module()


# --- Fixtures --------------------------------------------------------------

_VALID_BUILD_MD = """\
---
description: Build incrementally.
---

## Complexity Assessment

Some text.

## Pre-Mortem (Risk Identification)

Before any code changes, invoke Skill(skill="pre-mortem").

## Agent

Some text.

## Quality Signals

Some text.

## Mandatory Exit Gates

Run, in order:

1. Skill(skill="code-qualities-assessment") with `--changed-only`.
2. Skill(skill="taste-lints") against the changed files.
3. Skill(skill="doc-accuracy") with `--diff-base main`.

## Guardrails

Some text.
"""


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """Create the directory tree the script inspects."""
    (tmp_path / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_build_md(repo: Path, content: str) -> Path:
    target = repo / ".claude" / "commands" / "build.md"
    target.write_text(content, encoding="utf-8")
    return target


# --- Positive cases (should NOT flag) --------------------------------------


def test_complete_build_md_passes(fake_repo: Path) -> None:
    """A build.md with all three gates and the section heading passes."""
    _write_build_md(fake_repo, _VALID_BUILD_MD)
    violations = cbg.collect_violations(fake_repo)
    assert violations == []


def test_single_quoted_skill_invocations_pass(fake_repo: Path) -> None:
    """The regex tolerates single-quoted skill names."""
    content = _VALID_BUILD_MD.replace('skill="', "skill='").replace(
        '")', "')"
    )
    _write_build_md(fake_repo, content)
    violations = cbg.collect_violations(fake_repo)
    assert violations == []


def test_extra_whitespace_in_invocation_is_tolerated(fake_repo: Path) -> None:
    """Whitespace around the `=` in `Skill(skill="...")` is allowed."""
    content = _VALID_BUILD_MD.replace(
        'Skill(skill="code-qualities-assessment")',
        'Skill( skill = "code-qualities-assessment" )',
    )
    _write_build_md(fake_repo, content)
    violations = cbg.collect_violations(fake_repo)
    assert violations == []


def test_real_repo_build_md_passes() -> None:
    """The actual ``.claude/commands/build.md`` in this repo must pass.

    This test guards against regressions in the file itself, complementing
    the synthetic fixtures above. If someone edits build.md to drop a
    gate, this fails alongside the pre-PR validator.
    """
    violations = cbg.collect_violations(REPO_ROOT)
    assert violations == [], f"unexpected violations: {violations}"


# --- Negative cases (should flag) ------------------------------------------


def test_missing_section_heading_flagged(fake_repo: Path) -> None:
    """Removing the 'Mandatory Exit Gates' heading is a violation."""
    bad = _VALID_BUILD_MD.replace(
        "## Mandatory Exit Gates", "## Optional Exit Gates"
    )
    _write_build_md(fake_repo, bad)
    violations = cbg.collect_violations(fake_repo)
    assert any(v.kind == "section" for v in violations)


def test_missing_code_qualities_assessment_flagged(fake_repo: Path) -> None:
    """Dropping code-qualities-assessment is a violation."""
    bad = _VALID_BUILD_MD.replace(
        'Skill(skill="code-qualities-assessment") with `--changed-only`.',
        "(skipped).",
    )
    _write_build_md(fake_repo, bad)
    violations = cbg.collect_violations(fake_repo)
    skill_names = {v.name for v in violations if v.kind == "skill"}
    assert "code-qualities-assessment" in skill_names


def test_missing_taste_lints_flagged(fake_repo: Path) -> None:
    """Dropping taste-lints is a violation."""
    bad = _VALID_BUILD_MD.replace(
        'Skill(skill="taste-lints") against the changed files.',
        "(skipped).",
    )
    _write_build_md(fake_repo, bad)
    violations = cbg.collect_violations(fake_repo)
    skill_names = {v.name for v in violations if v.kind == "skill"}
    assert "taste-lints" in skill_names


def test_missing_doc_accuracy_flagged(fake_repo: Path) -> None:
    """Dropping doc-accuracy is a violation."""
    bad = _VALID_BUILD_MD.replace(
        'Skill(skill="doc-accuracy") with `--diff-base main`.',
        "(skipped).",
    )
    _write_build_md(fake_repo, bad)
    violations = cbg.collect_violations(fake_repo)
    skill_names = {v.name for v in violations if v.kind == "skill"}
    assert "doc-accuracy" in skill_names


def test_skill_mention_in_prose_does_not_satisfy(fake_repo: Path) -> None:
    """A bare reference to the skill name in prose is not a real invocation.

    The regex anchors to the literal ``Skill(skill=`` token so a sentence
    like "we used to invoke code-qualities-assessment here" cannot
    satisfy the contract.
    """
    bad = _VALID_BUILD_MD.replace(
        'Skill(skill="code-qualities-assessment") with `--changed-only`.',
        "We previously ran code-qualities-assessment manually.",
    )
    _write_build_md(fake_repo, bad)
    violations = cbg.collect_violations(fake_repo)
    skill_names = {v.name for v in violations if v.kind == "skill"}
    assert "code-qualities-assessment" in skill_names


def test_all_gates_missing_reports_three_violations(fake_repo: Path) -> None:
    """When every gate is gone, every gate is reported."""
    bad = """\
---
description: Build.
---

## Quality Signals

Some text.

## Guardrails

Some text.
"""
    _write_build_md(fake_repo, bad)
    violations = cbg.collect_violations(fake_repo)
    skill_names = {v.name for v in violations if v.kind == "skill"}
    assert skill_names == {
        "code-qualities-assessment",
        "taste-lints",
        "doc-accuracy",
    }


# --- Edge cases ------------------------------------------------------------


def test_missing_build_md_raises(fake_repo: Path) -> None:
    """A missing build.md is a config error, not a logic violation."""
    # Intentionally do not write build.md.
    with pytest.raises(FileNotFoundError):
        cbg.collect_violations(fake_repo)


def test_main_returns_zero_on_pass(fake_repo: Path) -> None:
    """CLI ``main`` returns 0 when build.md passes."""
    _write_build_md(fake_repo, _VALID_BUILD_MD)
    rc = cbg.main(["--repo-root", str(fake_repo)])
    assert rc == 0


def test_main_returns_one_on_violations(fake_repo: Path) -> None:
    """CLI ``main`` returns 1 when build.md has violations."""
    _write_build_md(
        fake_repo,
        _VALID_BUILD_MD.replace("## Mandatory Exit Gates", "## Optional Gates"),
    )
    rc = cbg.main(["--repo-root", str(fake_repo)])
    assert rc == 1


def test_main_returns_two_on_missing_file(fake_repo: Path) -> None:
    """CLI ``main`` returns 2 when build.md is absent."""
    rc = cbg.main(["--repo-root", str(fake_repo)])
    assert rc == 2


def test_main_returns_two_on_invalid_repo_root(tmp_path: Path) -> None:
    """CLI ``main`` returns 2 when --repo-root is not a directory."""
    not_a_dir = tmp_path / "does-not-exist"
    rc = cbg.main(["--repo-root", str(not_a_dir)])
    assert rc == 2
