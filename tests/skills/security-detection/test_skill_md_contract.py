"""ADR-108 template contract for security-detection; see _template_contract.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _template_contract import assert_template_owned_contract

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_skill_md_matches_its_template() -> None:
    assert_template_owned_contract("security-detection")


def test_security_detection_uses_the_literal_brace_escape() -> None:
    """security-detection templates its GitHub Actions env block through the escape.

    security-detection's SKILL.md carries two ``${{ github.* }}`` example
    lines, so its template writes each literal ``{{`` as ``\\{{`` (ADR-108
    amended 2026-09-14). Positive control mirroring
    tests/build_scripts/test_rule_templates_lossless.py's
    ``test_testing_rule_uses_the_literal_brace_escape``.
    """
    template = (
        _REPO_ROOT / "templates" / "skills" / "security-detection.SKILL.md.tmpl"
    ).read_text(encoding="utf-8")
    rendered = (
        _REPO_ROOT / ".claude" / "skills" / "security-detection" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert template.count("\\{{") == 2
    assert rendered.count("${{") == 2
    assert "\\{{" not in rendered
