"""The one ``.agents/`` install root ADR-119 reopens, and who may name it.

Issue #5421 retired ``.agents/skills``. ADR-119 decision 7 reuses it as
Codex's repository skill directory, holding binplace links to
``src/codex/skills``. It is not a KEEP subtree in
``check_agents_write_targets.py`` (rule (b) would then forbid the binplace
write), and not a general exception: only the files that define the install
root may name it. Anywhere else it is still the retired #5421 path.
"""

from __future__ import annotations

CODEX_SKILLS_ROOT = ".agents/skills"
CODEX_SKILLS_ROOT_OWNERS = frozenset(
    {
        "build/scripts/binplace_manifest.py",
        "scripts/validation/agents_install_roots.py",
        "templates/platforms/binplace.yaml",
        "templates/platforms/surface-parity.yaml",
    }
)


def names_codex_skills_root(path: str, target: str) -> bool:
    """Whether ``path`` is an install-root owner and ``target`` is exactly the root."""
    return path in CODEX_SKILLS_ROOT_OWNERS and target.rstrip("/\\") == CODEX_SKILLS_ROOT
