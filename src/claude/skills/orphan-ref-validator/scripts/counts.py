#!/usr/bin/env python3
"""orphan-ref-validator skill catalog enumeration.

Enumerates the live skill catalog at ``.claude/skills/<name>/SKILL.md`` so
``scan`` can decide whether a backticked kebab reference resolves to a real
skill. A subdirectory without a ``SKILL.md`` is a partial or in-progress
skill that cannot legally be referenced, so it is excluded.

Also enumerates the *sibling* artifact namespaces (agents, slash commands,
review axes, Serena memories). ``SKILL_REF_RE`` matches any backticked
kebab-case token, so a prose mention of an artifact that is not a skill
(the ``issue-feature-review`` agent, the ``decision-rigor`` review axis, the
``testing-002-test-first-development`` memory) is indistinguishable from a
reference to a deleted skill. Resolving against these namespaces is what
separates "names a real thing that is not a skill" from "names nothing".

Accepted trade-off: when a skill is deleted and its name also exists in a
sibling namespace, a *bare* mention of the name no longer flags. Measured on
2026-07-26, 7 of 96 skills share a name with a sibling (``merge-resolver``,
``negotiation``, ``pr-comment-responder`` and ``retrospective`` ship as both
a skill and an agent; ``observability`` is also a review axis;
``chestertons-fence`` and ``threat-modeling`` also name memories). A bare
mention still resolves to a live artifact, so passing it is correct. Prose
that explicitly calls the token a skill is held to REQ-009 AC-2 and resolves
against the catalog alone, so the deletion is still caught. ``test_scan.py``
pins both halves.
"""

from __future__ import annotations

from pathlib import Path

# Directories whose ``*.md`` stems are legal, non-skill reference targets.
# Each entry is a (relative directory, recursive) pair.
_SIBLING_FILE_NAMESPACES: tuple[tuple[tuple[str, ...], bool], ...] = (
    ((".claude", "agents"), False),
    ((".claude", "commands"), False),
    ((".serena", "memories"), True),
)

# Reference documents bundled inside a skill (``.claude/skills/<skill>/
# references/<name>.md``). The review axes live here and are cited by bare
# name throughout the specs.
_SKILL_REFERENCE_DIR = "references"


def skills_dir(repo_root: Path) -> Path:
    """Return the skill catalog directory inside ``repo_root``.

    Single source of truth for the catalog location. ``repo_root`` is the
    scanned repository (the consumer's cwd), never this script's own install
    root, so the path stays correct in a vendored plugin.
    """
    return repo_root / ".claude" / "skills"


def enumerate_skills(repo_root: Path) -> set[str] | None:
    """Return the set of skill names found at ``.claude/skills/<name>/SKILL.md``.

    Returns ``None`` when ``.claude/skills/`` is absent or is not a
    directory so callers can distinguish "no directory" (undeterminable)
    from "directory with zero skills" (deterministic count of zero).
    """
    catalog = skills_dir(repo_root)
    if not catalog.exists() or not catalog.is_dir():
        return None
    return {
        d.name
        for d in catalog.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def enumerate_sibling_artifacts(repo_root: Path) -> frozenset[str]:
    """Return names of non-skill artifacts a backticked token may legally name.

    Covers agents, slash commands, Serena memories, and skill-bundled
    reference documents (the review axes). A token that resolves here names a
    real artifact in this repository, so it is a valid reference and not an
    orphaned skill reference.

    Returns an empty set when none of the namespaces exist (a vendored
    install), which leaves the caller's behavior unchanged.
    """
    names: set[str] = set()
    for parts, recursive in _SIBLING_FILE_NAMESPACES:
        directory = repo_root.joinpath(*parts)
        if not directory.is_dir():
            continue
        globber = directory.rglob if recursive else directory.glob
        names.update(p.stem for p in globber("*.md") if p.is_file())

    catalog = skills_dir(repo_root)
    if catalog.is_dir():
        for skill_dir in catalog.iterdir():
            references = skill_dir / _SKILL_REFERENCE_DIR
            if not references.is_dir():
                continue
            names.update(p.stem for p in references.glob("*.md") if p.is_file())

    return frozenset(names)
