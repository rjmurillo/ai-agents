"""ADR-108 template contract for requirements-interview; see _template_contract.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _template_contract import assert_template_owned_contract
from audit_paths import SKILL_DIR


def test_skill_md_matches_its_template() -> None:
    assert_template_owned_contract("requirements-interview")


def test_skill_md_documents_audit_mode() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for needle in (
        "## Mode Selection",
        "## Ambiguity Audit Mode",
        "## Scripts",
        "NO MATERIAL GAPS",
        "scripts/spec_audit.py",
        "references/ambiguity-audit.md",
        "Owner decision, no evidence-backed recommendation",
    ):
        assert needle in skill, needle


def test_skill_md_documents_every_exit_code() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "Exit codes: `0` ok, `1` invalid ledger" in skill
    assert "`2` unreadable file or missing `decision-question` engine" in skill


def test_reference_names_every_coverage_category() -> None:
    from audit_check import CATEGORIES

    reference = (SKILL_DIR / "references" / "ambiguity-audit.md").read_text(encoding="utf-8")
    assert all(f'"{name}"' in reference for name in CATEGORIES)


def test_reference_does_not_use_the_unsupported_claim_as_evidence() -> None:
    reference = (SKILL_DIR / "references" / "ambiguity-audit.md").read_text(encoding="utf-8")
    assert "is not ground truth" in reference
