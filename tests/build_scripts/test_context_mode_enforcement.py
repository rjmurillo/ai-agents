"""CONTEXT_MODE enforcement contract tests (issue #1981).

AI-REVIEW-MODEL-POLICY.md ("CONTEXT_MODE Header (REQUIRED)") forbids a PASS
verdict when the reviewer model did not receive the full diff. The control has
three load-bearing surfaces, each pinned here:

1. Canonical refs: every `.claude/skills/review/references/{role}.md` carries a
   "Context Mode Enforcement" section that forbids PASS when mode is not full.
2. Copilot twins: every `src/copilot-cli/skills/review/references/{role}.md` is
   byte-identical to its canonical (the generator mirror, not a hand-edit).
3. Committed CI prompts: every `.github/prompts/pr-quality-gate-{role}.md`
   carries both the CONTEXT_MODE header line and the enforcement section.

Surfaces 1 and 3 gate the SHIPPED artifact, not just the generator, so a manual
edit that drops the control is caught (generated-artifacts.md: gate the
artifact, not only the generator). Surface 2 is the canonical-source-mirror
parity check.

Refs #1981, AI-REVIEW-MODEL-POLICY.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_DIR = REPO_ROOT / ".claude" / "skills" / "review" / "references"
TWIN_DIR = REPO_ROOT / "src" / "copilot-cli" / "skills" / "review" / "references"
PROMPTS_DIR = REPO_ROOT / ".github" / "prompts"

# The contract phrases the prompt body MUST carry. Kept in one place so the
# tests stay aligned if the wording is revised.
_SECTION_HEADER = "## Context Mode Enforcement (REQUIRED)"
_FORBID_PASS = "you MUST NOT emit `PASS`"
_HEADER_LINE_PREFIX = "<!-- CONTEXT_MODE: ${CONTEXT_MODE}"


def _canonical_roles() -> list[str]:
    """Role stems present in the canonical references dir."""
    return sorted(p.stem for p in CANONICAL_DIR.glob("*.md"))


def _prompt_path(role: str) -> Path:
    return PROMPTS_DIR / f"pr-quality-gate-{role}.md"


# ---------------------------------------------------------------------------
# Discovery sanity: the suite must actually iterate over the real roles.
# ---------------------------------------------------------------------------


def test_canonical_dir_has_expected_role_count() -> None:
    """The canonical dir has the 12 axes; a regression that drops one (or a
    test pointed at an empty dir) would silently make every loop below vacuous.
    """
    roles = _canonical_roles()
    assert len(roles) == 12, f"expected 12 canonical axes, found {len(roles)}: {roles}"


# ---------------------------------------------------------------------------
# POSITIVE: every shipped surface carries the control.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", _canonical_roles())
def test_canonical_ref_has_enforcement_section(role: str) -> None:
    text = (CANONICAL_DIR / f"{role}.md").read_text(encoding="utf-8")
    assert _SECTION_HEADER in text, (
        f"{role}.md is missing the Context Mode Enforcement section"
    )
    assert _FORBID_PASS in text, (
        f"{role}.md does not forbid PASS when context is not full"
    )


@pytest.mark.parametrize("role", _canonical_roles())
def test_committed_prompt_has_header_and_section(role: str) -> None:
    """Gate the shipped artifact (generated-artifacts.md): the committed CI
    prompt itself must carry the CONTEXT_MODE header line and the enforcement
    section. A hand-edit that strips either is a control regression.
    """
    prompt = _prompt_path(role)
    assert prompt.is_file(), f"missing generated prompt for role {role}"
    text = prompt.read_text(encoding="utf-8")
    assert _HEADER_LINE_PREFIX in text, (
        f"{prompt.name} is missing the CONTEXT_MODE header line"
    )
    assert _SECTION_HEADER in text, (
        f"{prompt.name} is missing the Context Mode Enforcement section"
    )
    assert _FORBID_PASS in text, (
        f"{prompt.name} does not forbid PASS when context is not full"
    )


# ---------------------------------------------------------------------------
# PARITY: copilot twins are byte-identical mirrors of canonical.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", _canonical_roles())
def test_copilot_twin_matches_canonical(role: str) -> None:
    """The twin under src/copilot-cli is a generator mirror, not a hand-edit.
    It must be byte-identical to the canonical so the control is consistent
    across both shipped plugins (canonical-source-mirror.md).
    """
    canonical = (CANONICAL_DIR / f"{role}.md").read_text(encoding="utf-8")
    twin_path = TWIN_DIR / f"{role}.md"
    assert twin_path.is_file(), f"missing copilot twin for role {role}"
    twin = twin_path.read_text(encoding="utf-8")
    assert twin == canonical, (
        f"copilot twin {role}.md drifted from canonical; regenerate via "
        f"build/scripts/generate_skills.py"
    )


# ---------------------------------------------------------------------------
# NEGATIVE: a prompt without the section must be detectable by the same checks.
# ---------------------------------------------------------------------------


def test_section_absence_is_detected(tmp_path: Path) -> None:
    """Guard against a vacuous positive test: a prompt that drops the section
    must fail the membership check the positive tests rely on.
    """
    stale = tmp_path / "pr-quality-gate-fake.md"
    stale.write_text(
        "<!-- GENERATED -- DO NOT EDIT -->\n\n# Fake\n\nNo enforcement here.\n",
        encoding="utf-8",
    )
    text = stale.read_text(encoding="utf-8")
    assert _SECTION_HEADER not in text
    assert _HEADER_LINE_PREFIX not in text
    assert _FORBID_PASS not in text


# ---------------------------------------------------------------------------
# EDGE: the enforcement text treats a missing/unknown mode as not-full.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", _canonical_roles())
def test_enforcement_handles_missing_mode(role: str) -> None:
    """The control must not have a hole when CONTEXT_MODE is absent or
    unrecognized: that case routes to the restrictive (not-full) branch.
    """
    text = (CANONICAL_DIR / f"{role}.md").read_text(encoding="utf-8")
    assert "missing or unrecognized `CONTEXT_MODE`" in text, (
        f"{role}.md does not pin the missing/unknown-mode behavior to not-full"
    )
