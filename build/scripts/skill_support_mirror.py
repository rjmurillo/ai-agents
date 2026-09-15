#!/usr/bin/env python3
"""Copy a skill directory tree; mirror support files into the Claude plugin tree.

Split out of ``generate_skills.py`` (taste-lint file-size ceiling; ADR-109
B3's support-file follow-up pushed that file over it), the same reason
``skill_templates.py`` split ``skill_template_grammar.py`` out of itself: this
module holds the filesystem primitive (:func:`_copy_skill_tree`, used by both
the Copilot mirror in ``generate_skills.py`` and the Claude mirror below) and
everything specific to the Claude-tree support-file sync
(:func:`sync_claude_plugin_skill_support`). ``generate_skills.py`` imports
every public and private name it still needs from here and re-exports them,
so every existing caller and test that reaches them through
``generate_skills.<name>`` keeps working unchanged.

``.claude/skills/<name>/`` stays the canonical, hand-maintained source for
every skill file except ``SKILL.md`` (rendered separately by
``skill_templates.compile_all``); this module never writes ``SKILL.md``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from copilot_body_translation import translate_skill_file  # noqa: E402
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402

_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")

# ADR-109 B3 follow-up: every skill's non-SKILL.md files (scripts/,
# references/, tests/, and any other support file) stay hand-maintained
# under .claude/skills/<name>/; SKILL.md itself is the only file rendered
# from a template into src/claude/skills/<name>/ (skill_templates.compile_all).
# This mirror copies everything else so the plugin tree binplace ships from
# (src/claude/skills) is complete, the same way _copy_skill_tree already
# mirrors .claude/skills/ into src/copilot-cli/skills/ for the Copilot
# target. Unlike the Copilot mirror, this one does NOT exclude
# merge-resolver: that skill ships in the Claude plugin, just not the
# publicly-shipping Copilot toolkit (see templates/platforms/copilot-cli.yaml).
_CLAUDE_SUPPORT_SOURCE_REL = Path(".claude") / "skills"
_CLAUDE_SUPPORT_TARGET_REL = Path("src") / "claude" / "skills"
_SKILL_MD = Path("SKILL.md")


class GenerateSkillsError(Exception):
    """Domain error for skill generation. Wraps copy/load issues."""


class SkillSupportSyncError(GenerateSkillsError):
    """A skill's support-file mirror hit a condition it refuses to handle.

    Raised for a symlink found anywhere under a skill directory (CWE-22/59:
    a linked file or directory could point outside the skill, and this
    mirror copies byte-for-byte with no containment check of its own beyond
    refusing to follow the link at all) or for a stale target file this
    mirror cannot safely remove (an ``OSError`` from the removal itself,
    e.g. a permission problem).
    """


def _iter_skill_sources(source_dir: Path, excludes: set[str]) -> list[Path]:
    """Return immediate subdirectories that contain a SKILL.md file.

    Excludes top-level files (AGENTS.md / CLAUDE.md). The check is by
    presence of a SKILL.md inside the immediate child directory; nested
    skill-like layouts are not recursed.
    """
    if not source_dir.is_dir():
        raise GenerateSkillsError(f"sourceDir not found: {source_dir}")
    skills: list[Path] = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in excludes:
            continue
        if not (child / "SKILL.md").is_file():
            continue
        skills.append(child)
    return skills


def _copy_skill_tree(
    source: Path,
    target: Path,
    *,
    what_if: bool,
    skills_output_dir: Path | None = None,
    plugin_skill_md: Path | None = None,
    skip_filenames: frozenset[Path] = frozenset(),
) -> tuple[int, int]:
    """Copy a single skill directory into ``target``.

    Returns ``(written, skipped)`` counts; skipped reflects NO-REGEN
    protections per file. Existing files are overwritten unless protected.

    When ``skills_output_dir`` is provided (Copilot CLI target), the
    top-level ``SKILL.md`` body is translated from Claude Code conventions
    to Copilot CLI equivalents (issue #2743) instead of copied verbatim.
    Every other file is copied byte-for-byte, straight from ``source``
    (``.claude/skills/<name>/``); scripts, references, and tests are
    hand-maintained there and never rendered by a template, so this path is
    unchanged by ADR-109 B3.

    ``plugin_skill_md`` (ADR-109 B3), when given and present on disk, is
    read for the ``SKILL.md`` body instead of ``source / "SKILL.md"``. It
    names the skill's plugin-tree render target,
    ``src/claude/skills/<name>/SKILL.md``, written by
    ``skill_templates.compile_all`` immediately before this copy loop runs
    (``generate_skills.generate_skills``). The install-tree copy,
    ``.claude/skills/<name>/SKILL.md``, is only refreshed later, by the
    binplace step that runs after every platform's copy loop
    (``build_all._run_binplace``), so reading it here during THIS run would
    risk translating yesterday's rendered content into the Copilot mirror.
    A skill with no template (``plugin_skill_md`` is ``None``, or the path
    does not exist yet) falls back to ``source / "SKILL.md"`` unchanged.

    ``skip_filenames``, when given, names relative paths (typically just
    ``SKILL.md``) this call must never write, at all: used by the Claude
    plugin-tree support-file mirror (:func:`sync_claude_plugin_skill_support`),
    whose SKILL.md is owned exclusively by ``skill_templates.compile_all``
    and must never be touched by a plain byte-for-byte copy.
    """
    written = 0
    skipped = 0
    for src_path in source.rglob("*"):
        if src_path.is_dir():
            continue
        # Skip Python cache artifacts; they're build-time noise that
        # belongs in .gitignore, not in a customer-facing plugin install.
        if "__pycache__" in src_path.parts or src_path.suffix in (".pyc", ".pyo"):
            continue
        rel = src_path.relative_to(source)
        if rel in skip_filenames:
            continue
        dst_path = target / rel

        reason = regen_detect_reason(dst_path)
        if reason is not None:
            print(f"  NOTICE: skipped {dst_path} (NO-REGEN: {reason})")
            skipped += 1
            continue

        if what_if:
            print(f"  Would copy: {src_path} -> {dst_path}")
            continue

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if skills_output_dir is not None and rel == Path("SKILL.md"):
            content_source = src_path
            if plugin_skill_md is not None and plugin_skill_md.is_file():
                content_source = plugin_skill_md
            content = content_source.read_text(encoding="utf-8")
            dst_path.write_text(translate_skill_file(content, skills_output_dir), encoding="utf-8")
        else:
            shutil.copy2(src_path, dst_path)
        written += 1
    return written, skipped


def _iter_support_relpaths(skill_dir: Path) -> set[Path]:
    """Return every non-``SKILL.md`` file under ``skill_dir``, as relative paths.

    Skips ``__pycache__``/``.pyc``/``.pyo`` (same build-time noise
    :func:`_copy_skill_tree` excludes). Raises :class:`SkillSupportSyncError`
    on the first symlink found anywhere in the tree, file or directory: this
    mirror copies byte-for-byte with no per-path containment check, so a
    linked entry (or a linked ancestor directory, which ``rglob`` would
    otherwise silently descend into and copy through) could point outside
    the skill directory (CWE-22/59). The check runs before ``is_dir()``
    short-circuits so a symlinked directory is caught before anything
    reached through it is ever read.
    """
    rels: set[Path] = set()
    for src_path in skill_dir.rglob("*"):
        if src_path.is_symlink():
            raise SkillSupportSyncError(f"{src_path}: symlink inside a skill directory refused")
        if src_path.is_dir():
            continue
        if "__pycache__" in src_path.parts or src_path.suffix in (".pyc", ".pyo"):
            continue
        rel = src_path.relative_to(skill_dir)
        if rel == _SKILL_MD:
            continue
        rels.add(rel)
    return rels


def _prune_empty_dirs(root: Path) -> None:
    """Remove now-empty directories left behind by :func:`_prune_stale_support_files`."""
    if not root.is_dir():
        return
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            next(directory.iterdir())
        except StopIteration:
            directory.rmdir()
        except OSError:
            pass


def _prune_stale_support_files(target_dir: Path, wanted: set[Path]) -> tuple[int, list[str]]:
    """Delete files under ``target_dir`` (excluding ``SKILL.md``) not in ``wanted``.

    A NO-REGEN-protected extra is left in place (NOTICE, not an error): the
    same declared-divergence exemption every other file in this class
    honors. A removal that raises ``OSError`` is recorded as an error and
    left in place rather than crashing the run; the caller folds it into a
    nonzero exit code.
    """
    removed = 0
    errors: list[str] = []
    if not target_dir.is_dir():
        return removed, errors
    for existing in sorted(target_dir.rglob("*")):
        if existing.is_dir():
            continue
        if "__pycache__" in existing.parts or existing.suffix in (".pyc", ".pyo"):
            continue
        if existing.name.endswith(".noregen"):
            # A NO-REGEN sidecar (regen_guard.py) is a hand-placed
            # protection marker for its sibling, checked via
            # regen_detect_reason below; it is never itself a mirrored
            # support file, so it is never a deletion candidate on its own.
            continue
        rel = existing.relative_to(target_dir)
        if rel == _SKILL_MD or rel in wanted:
            continue
        reason = regen_detect_reason(existing)
        if reason is not None:
            print(f"  NOTICE: kept stale {existing} (NO-REGEN: {reason})")
            continue
        try:
            existing.unlink()
            removed += 1
        except OSError as exc:
            errors.append(f"{existing}: could not remove stale mirror file: {exc}")
    _prune_empty_dirs(target_dir)
    return removed, errors


def sync_claude_plugin_skill_support(
    repo_root: Path, *, what_if: bool = False
) -> tuple[int, int, int, list[str]]:
    """Mirror every skill's non-``SKILL.md`` files into the Claude plugin tree.

    ``.claude/skills/<name>/`` stays the canonical, hand-maintained source
    for scripts, references, tests, and any other support file (ADR-109's
    lib exception applies the same pattern here: imported/hand-written code
    stays at its existing location, and the build owns the copy).
    ``src/claude/skills/<name>/SKILL.md`` is rendered separately by
    ``skill_templates.compile_all`` and is never touched here (``SKILL.md``
    is always excluded, via ``_copy_skill_tree``'s ``skip_filenames``).

    Unlike the Copilot mirror (``_iter_skill_sources`` called with
    ``copilot-cli.yaml``'s ``excludeFilenames``), this walk uses only the
    module default excludes (``AGENTS.md``, ``CLAUDE.md``): merge-resolver
    ships in the Claude plugin even though it is excluded from the
    publicly-shipping Copilot toolkit.

    Returns ``(written, removed, skipped, errors)``. ``written`` and
    ``skipped`` come from :func:`_copy_skill_tree` (skipped counts
    NO-REGEN-protected copy targets); ``removed`` counts stale mirror files
    deleted because their source no longer exists; ``errors`` collects one
    message per skill this run refused (a symlink) or could not fully prune
    (a removal that raised ``OSError``) -- a non-empty list means the
    caller should report failure, but every OTHER skill still mirrors
    normally rather than the whole run aborting on one bad skill.

    An absent ``.claude/skills/`` (a synthetic test fixture with its own,
    unrelated ``sourceDir``) is a silent no-op: this mirror always reads
    the real, repo-global source tree, never the caller's platform config,
    the same way ``skill_templates.compile_all`` always reads
    ``templates/skills/`` regardless of which platform triggered the call.
    """
    source_dir = repo_root / _CLAUDE_SUPPORT_SOURCE_REL
    target_dir = repo_root / _CLAUDE_SUPPORT_TARGET_REL
    try:
        skills = _iter_skill_sources(source_dir, set(_DEFAULT_EXCLUDES))
    except GenerateSkillsError:
        return (0, 0, 0, [])

    total_written = 0
    total_removed = 0
    total_skipped = 0
    errors: list[str] = []
    for src in skills:
        try:
            wanted = _iter_support_relpaths(src)
        except SkillSupportSyncError as exc:
            errors.append(str(exc))
            continue
        target = target_dir / src.name
        written, skipped = _copy_skill_tree(
            src, target, what_if=what_if, skip_filenames=frozenset({_SKILL_MD})
        )
        total_written += written
        total_skipped += skipped
        if not what_if:
            removed, prune_errors = _prune_stale_support_files(target, wanted)
            total_removed += removed
            errors.extend(prune_errors)
    return total_written, total_removed, total_skipped, errors
