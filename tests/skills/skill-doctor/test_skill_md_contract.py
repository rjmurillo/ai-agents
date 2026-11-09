"""Verify canonical template and generated entry points remain synchronized."""

from tests.skills._template_contract import REPO_ROOT, skill_templates


def test_skill_doctor_template_contract() -> None:
    template = REPO_ROOT / "templates" / "skills" / "skill-doctor.SKILL.md.tmpl"
    expected = skill_templates.render(template, template.parent / "partials")
    for path in (
        REPO_ROOT / "src" / "claude" / "skills" / "skill-doctor" / "SKILL.md",
        REPO_ROOT / ".claude" / "skills" / "skill-doctor" / "SKILL.md",
    ):
        assert path.read_text(encoding="utf-8", newline="") == expected
    mirror = REPO_ROOT / "src" / "copilot-cli" / "skills" / "skill-doctor" / "SKILL.md"
    assert "{{" not in mirror.read_text(encoding="utf-8")
