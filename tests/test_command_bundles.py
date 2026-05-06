"""Static-parser tests for the SPEC-005 BundleRegistry.

Each test verifies that the corresponding command markdown file at
``.claude/commands/<file>`` contains both:

1. The literal ``Skill(skill="<name>")`` invocation, and
2. An adjacent ``BUNDLE: <command-base> -> <name>`` marker.

These are static contract checks. The tests do NOT execute the
commands; they parse the markdown text only. Rows for not-yet-edited
commands carry ``@pytest.mark.xfail`` so CI stays GREEN throughout
M1 and M2 (per the SPEC-005 implementation plan §"M1 Stays Green").

The xfail marks are removed milestone-by-milestone:

- M2 closing commits remove xfail for spec.md, ship.md, plan.md,
  pr-review.md, research.md.
- M3 closing commit removes xfail for build.md, test.md, review.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Anchor the import to the repo root so pytest discovery works
# regardless of the CWD it is invoked from (mitigates plan F4).
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "validation"))

from bundle_registry import (  # noqa: E402
    BUNDLE_REGISTRY,
    expected_bundle_marker,
    expected_skill_invocation,
)

COMMANDS_DIR = _REPO_ROOT / ".claude" / "commands"


# Rows for commands that have NOT yet been edited to invoke their
# bundled skill. These are expected to fail until the matching M2 or
# M3 implementation lands.
PENDING_ROWS: set[tuple[str, str]] = set(BUNDLE_REGISTRY)


def _xfail_or_pass_param(row: tuple[str, str]):
    file_, skill = row
    if row in PENDING_ROWS:
        return pytest.param(
            file_,
            skill,
            marks=pytest.mark.xfail(
                reason=(
                    f"awaits M2/M3 command edit: {file_} not yet bundled with {skill}"
                ),
                strict=False,
            ),
            id=f"{file_}-{skill}",
        )
    return pytest.param(file_, skill, id=f"{file_}-{skill}")


@pytest.mark.parametrize(
    ("command_file", "skill"),
    [_xfail_or_pass_param(row) for row in BUNDLE_REGISTRY],
)
def test_bundle_invocation_present(command_file: str, skill: str) -> None:
    """The command file contains the literal ``Skill(skill="...")`` call."""
    path = COMMANDS_DIR / command_file
    assert path.exists(), f"Command file not found: {path}"
    text = path.read_text(encoding="utf-8")
    invocation = expected_skill_invocation(skill)
    assert invocation in text, (
        f"{command_file} missing required invocation '{invocation}'. "
        f"Per SPEC-005 BundleRegistry, this skill must be bundled into "
        f"this command."
    )


@pytest.mark.parametrize(
    ("command_file", "skill"),
    [_xfail_or_pass_param(row) for row in BUNDLE_REGISTRY],
)
def test_bundle_marker_present(command_file: str, skill: str) -> None:
    """The command file contains the adjacent ``BUNDLE:`` marker text."""
    path = COMMANDS_DIR / command_file
    assert path.exists(), f"Command file not found: {path}"
    text = path.read_text(encoding="utf-8")
    marker = expected_bundle_marker(command_file, skill)
    assert marker in text, (
        f"{command_file} missing required marker '{marker}'. "
        f"Per SPEC-005 DESIGN-005 §BUNDLE Marker Format, every bundled "
        f"invocation must have an adjacent BUNDLE: marker."
    )


def test_registry_has_expected_size() -> None:
    """Sanity check on registry size; catches accidental row removal."""
    assert len(BUNDLE_REGISTRY) == 15, (
        f"BUNDLE_REGISTRY has {len(BUNDLE_REGISTRY)} entries; "
        f"SPEC-005 requires exactly 15 invocations across 13 unique "
        f"skills. Update this expectation only when amending the spec."
    )


def test_registry_unique_skill_count() -> None:
    """Verify the registry has 13 unique skills as documented in REQ-005."""
    unique_skills = {skill for _, skill in BUNDLE_REGISTRY}
    assert len(unique_skills) == 13, (
        f"BUNDLE_REGISTRY has {len(unique_skills)} unique skills; "
        f"SPEC-005 REQ-005 documents 13."
    )


def test_cwe78_path_quoting_in_build_md() -> None:
    """build.md must quote file paths in git log commands (CWE-78).

    This check uses an independent regex grep, NOT the bundle parser
    above, per pre-mortem F5: sharing the parser between the production
    artifact and its CWE test would create a single-defect surface.
    """
    path = COMMANDS_DIR / "build.md"
    if not path.exists():
        pytest.skip("build.md not yet present; M3 introduces it")
    text = path.read_text(encoding="utf-8")
    # Skip if file does not yet have the chestertons-fence guard
    if "chestertons-fence" not in text or "git log" not in text:
        pytest.skip("build.md does not yet contain a chestertons-fence git log guard")
    # Independent regex (not using bundle_registry.py): every `git log`
    # invocation operating on a file path must use double-quoted form.
    import re

    unquoted = re.findall(r"git log[^\n]*-- (?!\")(\S+)", text)
    assert not unquoted, (
        f"build.md has unquoted git log paths (CWE-78 risk): {unquoted}"
    )


def test_cwe78_path_quoting_in_review_md() -> None:
    """review.md must quote file paths in git log commands (CWE-78).

    Independent regex check; see ``test_cwe78_path_quoting_in_build_md``.
    """
    path = COMMANDS_DIR / "review.md"
    if not path.exists():
        pytest.skip("review.md not yet present; M3 introduces it")
    text = path.read_text(encoding="utf-8")
    if "chestertons-fence" not in text or "git log" not in text:
        pytest.skip("review.md does not yet contain a chestertons-fence git log guard")
    import re

    unquoted = re.findall(r"git log[^\n]*-- (?!\")(\S+)", text)
    assert not unquoted, (
        f"review.md has unquoted git log paths (CWE-78 risk): {unquoted}"
    )
