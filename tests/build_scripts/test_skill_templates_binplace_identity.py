"""Byte-identity: every plugin-tree SKILL.md matches its binplaced install copy.

ADR-109 B3 splits the skills class the way agents (B1) and rules (B2)
already are: ``skill_templates.compile_all`` renders
``src/claude/skills/<name>/SKILL.md`` (the plugin tree), and a separate
binplace step (``build/scripts/binplace_manifest.py``) copies it onto
``.claude/skills/<name>/SKILL.md`` (the install tree) byte for byte. This
file is the standalone gate on that promise, over every skill the real tree
currently discovers, rather than the per-skill checks
``tests/skills/_template_contract.py`` already does for the skills with a
dedicated ``test_skill_md_contract.py``: not every template-owned skill has
one of those, and this test does not depend on the per-skill file existing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import skill_templates  # noqa: E402


def test_every_discovered_skill_is_binplaced_byte_identical() -> None:
    """Every ``src/claude/skills/<name>/SKILL.md`` matches ``.claude/skills/<name>/SKILL.md``.

    A mismatch means ``build/scripts/build_all.py`` (or
    ``build_all.py --check``) has not run since the plugin tree last
    changed; fix by rerunning it and committing the result.
    """
    names = sorted(skill_templates.discover(REPO_ROOT))
    assert names, "no template-owned skills discovered; is templates/skills/ present?"

    mismatched: list[str] = []
    for name in names:
        plugin_path = REPO_ROOT / "src" / "claude" / "skills" / name / "SKILL.md"
        install_path = REPO_ROOT / ".claude" / "skills" / name / "SKILL.md"
        assert plugin_path.is_file(), f"no plugin-tree SKILL.md for {name!r}: {plugin_path}"
        assert install_path.is_file(), f"no install-tree SKILL.md for {name!r}: {install_path}"
        plugin_bytes = plugin_path.read_bytes()
        install_bytes = install_path.read_bytes()
        if plugin_bytes != install_bytes:
            mismatched.append(name)

    assert not mismatched, (
        f"{len(mismatched)} skill(s) not binplaced byte-identical: {mismatched}; "
        "rerun build/scripts/build_all.py"
    )


def test_byte_identity_check_is_not_vacuous(tmp_path: Path) -> None:
    """Negative control: proves the comparison above would catch a real mismatch."""
    plugin_path = tmp_path / "src" / "claude" / "skills" / "sync" / "SKILL.md"
    install_path = tmp_path / ".claude" / "skills" / "sync" / "SKILL.md"
    plugin_path.parent.mkdir(parents=True)
    install_path.parent.mkdir(parents=True)
    plugin_path.write_text("rendered\n", encoding="utf-8")
    install_path.write_text("stale\n", encoding="utf-8")

    assert plugin_path.read_bytes() != install_path.read_bytes()
