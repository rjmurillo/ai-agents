"""Structure test for this skill, mirroring the prose-self-check tests pattern."""

import re
from pathlib import Path

SKILL_DIR = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "ai-agents-architecture-contract"
)
SKILL_MD = SKILL_DIR / "SKILL.md"


def _text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def test_skill_md_exists():
    assert SKILL_MD.is_file()


def test_frontmatter_required_fields():
    text = _text()
    assert text.startswith("---\n")
    fm = text.split("---", 2)[1]
    assert re.search(r"^name: ai-agents-architecture-contract$", fm, re.M)
    assert re.search(r"^version: ", fm, re.M)
    assert re.search(r"^description: ", fm, re.M)


def test_body_structure():
    text = _text()
    assert re.search(r"^# ", text, re.M), "H1 title required"
    assert "## Triggers" in text
    assert re.search(r"^## Process|^### Phase \d", text, re.M)
    assert len(re.findall(r"- \[ \]", text)) >= 2, "verification checkboxes required"
    assert "## Provenance" in text


def test_no_em_or_en_dashes():
    for ch in ("\u2014", "\u2013"):
        assert ch not in _text()


def test_size_cap():
    assert len(_text().splitlines()) <= 500


REPO_ROOT = Path(__file__).resolve().parents[3]
ADR_DIR = REPO_ROOT / ".project-toolkit" / "architecture"


REFS = SKILL_DIR / "references"


def _row(prefix: str, ref: str = "SKILL.md") -> str:
    """Return the single row starting with prefix in SKILL.md or a references/ file."""
    path = SKILL_MD if ref == "SKILL.md" else REFS / ref
    rows = [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith(prefix)
    ]
    assert len(rows) == 1, f"expected exactly one row starting {prefix!r}, got {len(rows)}"
    return rows[0]


def _adr_status(adr_glob: str) -> str:
    adr = next(ADR_DIR.glob(adr_glob))
    match = re.search(r"^status: (\S+)$", adr.read_text(encoding="utf-8"), re.M)
    assert match, f"{adr.name} has no status frontmatter"
    return match.group(1)


def test_adr_052_row_follows_its_frontmatter_status():
    assert _adr_status("ADR-052-*.md") == "superseded"
    row = _row("| Claude-first template strategy", "adr-decisions.md")
    assert "Superseded by ADR-109" in row
    assert "Accepted (2026-08-25)" not in row


def test_adr_036_row_follows_its_frontmatter_status():
    assert _adr_status("ADR-036-*.md") == "superseded"
    row = _row("| Two-source agent templates", "adr-decisions.md")
    assert "ADR-052" in row
    assert "ADR-109" in row
    assert "procedure still operative" not in row


def test_adr_109_decision_row_present_and_accepted():
    assert _adr_status("ADR-109-*.md") == "accepted"
    row = _row("| Template-first plugin distribution", "adr-decisions.md")
    assert "ADR-109" in row
    assert "Superseded" not in row


def test_claude_agents_row_names_templates_as_canonical():
    row = _row("| Agents (Claude Code)", "source-of-truth.md")
    assert "templates/agents/<stem>.claude.md.tmpl" in row
    assert "hand-written" not in row
    assert "hand-maintained" not in row


def test_no_unimplemented_generator_claims_survive():
    text = _text()
    assert "all three outputs" not in text
    assert "unimplemented in ADR-052" not in text
    assert "ADR-052 unimplemented" not in text
    assert "is itself canonical, hand-written" not in text


def test_copilot_and_vscode_agent_rows_name_distinct_sources():
    copilot = _row("| Agents (Copilot CLI)", "source-of-truth.md")
    vscode = _row("| Agents (VS Code)", "source-of-truth.md")
    assert "<stem>.copilot.md.tmpl" in copilot
    assert "*.shared.md" not in copilot
    assert "*.shared.md" in vscode


def test_rules_skills_hooks_rows_name_templates_as_canonical():
    assert "templates/rules/" in _row("| Rules |", "source-of-truth.md")
    assert "templates/skills/" in _row("| Skills |", "source-of-truth.md")
    assert "templates/hooks/" in _row("| Hooks |", "source-of-truth.md")


def test_no_claude_canonical_claim_for_template_classes():
    text = _text()
    assert "`.claude/` itself is canonical" not in text
    assert "They NEVER write `.claude/`" not in text
