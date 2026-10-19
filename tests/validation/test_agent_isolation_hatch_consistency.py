"""Real-template consistency for the isolation_required escape hatch (#5810).

The discriminator scores ``templates/agents/*.shared.md`` as an agent file in
its own right (ADR-036). A platform template that declares the hatch while its
shared sibling does not gives one agent two verdicts, depending on which file a
change touches. These tests pin the two sources to the same declaration.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_agent_skill_discriminator.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("agent_skill_disc_hatch", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()

AGENT_TEMPLATES = REPO_ROOT / "templates" / "agents"


def _hatch_declared(path: Path) -> bool:
    """True when the file's frontmatter declares the hatch.

    Platform templates close their frontmatter inside a ``{{> <name>-intro}}``
    partial, so the closing delimiter is not in the file. Read up to the first
    partial or closing delimiter instead of using ``split_frontmatter``.
    """
    head: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip() == "---" or line.startswith("{{>"):
            break
        head.append(line)
    return mod.has_isolation_required("\n".join(head))


def _agents_declaring_hatch_in_claude_template() -> list[str]:
    return sorted(
        path.name.removesuffix(".claude.md.tmpl")
        for path in AGENT_TEMPLATES.glob("*.claude.md.tmpl")
        if _hatch_declared(path)
    )


def test_claude_template_hatch_agents_are_discovered() -> None:
    """Guard the parametrization below: an empty list would pass vacuously."""
    names = _agents_declaring_hatch_in_claude_template()
    assert {"architect", "qa", "implementer", "security"} <= set(names)


def test_shared_template_declares_hatch_when_claude_template_does() -> None:
    """The shared template is scored on its own, so it must carry the hatch."""
    missing = [
        name
        for name in _agents_declaring_hatch_in_claude_template()
        if not _hatch_declared(AGENT_TEMPLATES / f"{name}.shared.md")
    ]
    assert missing == [], f"shared templates missing isolation_required: {missing}"


def test_copilot_template_matches_shared_template_hatch() -> None:
    """build_all renders Copilot from the Copilot template, generate_agents from shared.

    Both generators must emit the same bytes, so the two sources must agree.
    """
    mismatched = [
        path.name.removesuffix(".shared.md")
        for path in sorted(AGENT_TEMPLATES.glob("*.shared.md"))
        if (AGENT_TEMPLATES / path.name.replace(".shared.md", ".copilot.md.tmpl")).exists()
        and _hatch_declared(path)
        != _hatch_declared(AGENT_TEMPLATES / path.name.replace(".shared.md", ".copilot.md.tmpl"))
    ]
    assert mismatched == [], (
        f"shared and copilot templates disagree on isolation_required: {mismatched}"
    )


def test_real_shared_templates_with_hatch_pass_the_gate() -> None:
    """End to end on the repo: architect and qa shared edits exit 0."""
    for name in ("architect", "qa"):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=REPO_ROOT,
            env={
                **os.environ,
                "CHANGED_FILES": f"templates/agents/{name}.shared.md",
            },
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "isolation_required=yes" in proc.stdout
