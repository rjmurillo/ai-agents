#!/usr/bin/env python3
"""Copy a skill directory tree; reconcile the Claude plugin tree with repo-local skills.

Split out of ``generate_skills.py`` (taste-lint file-size ceiling; ADR-109
B3's support-file follow-up pushed that file over it), the same reason
``skill_templates.py`` split ``skill_template_grammar.py`` out of itself: this
module holds the filesystem primitive (:func:`_copy_skill_tree`, used by both
the Copilot mirror in ``generate_skills.py``) and the Claude-tree
reconcile (:func:`prune_stale_claude_skill_support`). ``generate_skills.py`` imports
every public and private name it still needs from here and re-exports them,
so every existing caller and test that reaches them through
``generate_skills.<name>`` keeps working unchanged.

A shipped skill's support files are hand-maintained in
``src/claude/skills/<name>/``, and ``.claude/skills/<name>`` is a symlink to
that directory, so no Claude-side copy exists to sync. ``SKILL.md`` is
rendered separately by ``skill_templates.compile_all``; this module never
writes it.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from atomic_write import (  # noqa: E402
    publish_bytes_atomically,
    publish_bytes_preserving_mode,
)
from binplace_manifest import is_bytecode_artifact  # noqa: E402
from copilot_support_translation import (  # noqa: E402
    SupportTranslationError,
    translated_text,
)
from regen_guard import detect_reason as regen_detect_reason  # noqa: E402
from skill_copy_compare import copy_matches, text_matches, tree_sources  # noqa: E402
from skill_distribution import SkillDistributionError, repo_local_names  # noqa: E402
from skill_md_rewrite import GenerateSkillsError, rewrite_skill_md  # noqa: E402

_DEFAULT_EXCLUDES = ("AGENTS.md", "CLAUDE.md")

# A shipped skill lives in src/claude/skills/<name>/ and .claude/skills/<name>
# links to it; a repo-local skill lives only in .claude/skills/<name>/.
_CLAUDE_INSTALL_REL = Path(".claude") / "skills"
_CLAUDE_PLUGIN_REL = Path("src") / "claude" / "skills"


class SkillSupportSyncError(GenerateSkillsError):
    """A skill's support-file mirror hit a condition it refuses to handle.

    Raised for a symlink found anywhere under a skill directory (CWE-22/59:
    a linked file or directory could point outside the skill, and this
    mirror copies byte-for-byte with no containment check of its own beyond
    refusing to follow the link at all) or for a stale target file this
    mirror cannot safely remove (an ``OSError`` from the removal itself,
    e.g. a permission problem).
    """


def _iter_skill_sources(
    source_dir: Path,
    excludes: set[str],
    skip_names: frozenset[str] = frozenset(),
    templated: frozenset[str] = frozenset(),
) -> list[Path]:
    """Return immediate subdirectories that contain a SKILL.md file.

    Excludes top-level files (AGENTS.md / CLAUDE.md). The check is by
    presence of a SKILL.md inside the immediate child directory; nested
    skill-like layouts are not recursed. ``skip_names`` drops skills flagged
    ``distribution: repo-local`` (``skill_distribution.repo_local_names``):
    they stay under ``.claude/skills/`` and reach no vendor plugin tree.

    ``templated`` names skills that own a ``templates/skills/<name>.SKILL.md.tmpl``
    (``skill_templates.discover``). Such a skill counts as present even when
    its install-tree ``SKILL.md`` is absent: a new skill has none until the
    binplace step, which runs after every generator, writes it. Requiring the
    file made a new skill's support files wait for a second build run
    (issue #6537).
    """
    if not source_dir.is_dir():
        raise GenerateSkillsError(f"sourceDir not found: {source_dir}")
    skills: list[Path] = []
    for child in sorted(source_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in excludes or child.name in skip_names:
            continue
        if child.name not in templated and not (child / "SKILL.md").is_file():
            continue
        skills.append(child)
    return skills


def _copy_skill_tree(
    source: Path,
    target: Path,
    *,
    what_if: bool,
    check: bool = False,
    skills_output_dir: Path | None = None,
    plugin_skill_md: Path | None = None,
    skip_filenames: frozenset[Path] = frozenset(),
    frontmatter_drop: frozenset[str] = frozenset(),
    frontmatter_keep: frozenset[str] | None = None,
) -> tuple[int, int]:
    """Copy a single skill directory into ``target``.

    Returns ``(written, skipped)`` counts; skipped reflects NO-REGEN
    protections per file. Existing files are overwritten unless protected.
    A destination that already has the source's bytes (and, for the plain
    copy branch, its permission bits) is left untouched and not counted
    in ``written``: without this a clean, no-op run still reported every
    file as written, which both wastes I/O on every invocation and makes
    "N written" useless as a signal of what actually changed.

    When ``skills_output_dir`` is provided (Copilot CLI target), the
    top-level ``SKILL.md`` body and every ``references/*.md`` are translated
    from Claude Code conventions to Copilot CLI equivalents (issues #2743,
    #5657) instead of copied verbatim. Every other file is copied
    byte-for-byte, straight from ``source`` (``.claude/skills/<name>/``);
    scripts and tests are hand-maintained there and never rendered by a
    template, so this path is unchanged by ADR-109 B3.

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
    plugin-tree support-file mirror (:func:`prune_stale_claude_skill_support`),
    whose SKILL.md is owned exclusively by ``skill_templates.compile_all``
    and must never be touched by a plain byte-for-byte copy.

    ``frontmatter_drop`` names top-level ``SKILL.md`` frontmatter keys the
    translated copy omits (the platform config's ``frontmatterDrop``). It only
    applies with ``skills_output_dir``, the translate branch (ADR-111). Without
    it, a non-empty list still drops those keys and keeps the body (ADR-115).

    ``frontmatter_keep`` (ADR-115 Decision 2) is Cursor's allow-list cut of the
    top-level ``SKILL.md`` frontmatter; see ``skill_md_rewrite.py``.

    ``check``, when set, never writes either, but (unlike ``what_if``)
    counts every mismatch into ``written``: a caller running a staleness
    gate needs a number to escalate on, not just a printed intention. A
    mismatch a git-diff-based staleness check would miss (an uncommitted
    hand edit, or a file that was never committed at all) is caught here
    directly, by comparing the destination's current bytes against the
    source, the same way ``binplace_manifest.binplace(check=True)``
    compares a plugin-tree file to its install-tree counterpart for the
    classes that go through the binplace manifest. Mutually exclusive with
    ``what_if``; ``check`` wins if both are set.
    """
    written = 0
    skipped = 0
    renders_skill_md = (
        skills_output_dir is not None or frontmatter_keep is not None or bool(frontmatter_drop)
    )
    for src_path in tree_sources(source, plugin_skill_md if renders_skill_md else None):
        if src_path.is_dir():
            continue
        # Skip Python cache artifacts; they're build-time noise that
        # belongs in .gitignore, not in a customer-facing plugin install.
        rel = src_path.relative_to(source)
        if is_bytecode_artifact(rel):
            continue
        if rel in skip_filenames:
            continue
        dst_path = target / rel

        reason = regen_detect_reason(dst_path)
        if reason is not None:
            print(f"  NOTICE: skipped {dst_path} (NO-REGEN: {reason})")
            skipped += 1
            continue

        try:
            skill_text = rewrite_skill_md(
                src_path,
                rel,
                skills_output_dir=skills_output_dir,
                plugin_skill_md=plugin_skill_md,
                frontmatter_drop=frontmatter_drop,
                frontmatter_keep=frontmatter_keep,
            )
            if skill_text is None:
                # Copilot also translates references/*.md (issue #5657).
                skill_text = translated_text(
                    rel, src_path, plugin_skill_md, skills_output_dir, frontmatter_drop
                )
        except SupportTranslationError as exc:
            raise GenerateSkillsError(str(exc)) from exc
        if skill_text is not None:
            if text_matches(dst_path, skill_text):
                continue
            if check:
                print(f"  DRIFT: {dst_path} differs from {src_path}")
                written += 1
                continue
            if what_if:
                print(f"  Would copy: {src_path} -> {dst_path}")
                continue
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            publish_bytes_preserving_mode(dst_path, skill_text.encode("utf-8"))
        else:
            if copy_matches(dst_path, src_path):
                continue
            if check:
                print(f"  DRIFT: {dst_path} differs from {src_path}")
                written += 1
                continue
            if what_if:
                print(f"  Would copy: {src_path} -> {dst_path}")
                continue
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            publish_bytes_atomically(
                dst_path,
                src_path.read_bytes(),
                mode=stat.S_IMODE(src_path.stat().st_mode),
            )
        written += 1
    return written, skipped


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


def prune_repo_local_vendor_copies(
    tree_root: Path, names: frozenset[str], *, check: bool = False, what_if: bool = False
) -> tuple[int, list[str]]:
    """Remove ``tree_root/<name>/`` for each repo-local skill name still present there.

    A skill that becomes ``distribution: repo-local`` in an existing checkout
    leaves its old vendor copy behind, and binplace never deletes. This
    reconciles ``src/claude/skills`` and ``src/copilot-cli/skills`` (the two
    callers' ``tree_root``) with the flag. It touches only ``tree_root/<name>``
    for the given names, so a shipped skill is never affected. A symlinked
    skill directory, or a symlink anywhere inside it, is refused as an error
    (CWE-22/59) and left in place, like :func:`_iter_support_relpaths`.

    ``check`` and ``what_if`` delete nothing: each file that would go is
    reported and counted. Returns ``(files removed or reported, errors)``.
    """
    removed = 0
    errors: list[str] = []
    for name in sorted(names):
        skill_dir = tree_root / name
        if Path(name).name != name or not (skill_dir.is_symlink() or skill_dir.is_dir()):
            continue
        try:
            files = _vendor_copy_files(skill_dir)
        except SkillSupportSyncError as exc:
            errors.append(str(exc))
            continue
        for path in files:
            if check or what_if:
                print(f"  {'DRIFT' if check else 'Would remove'}: {path} (repo-local skill)")
                removed += 1
                continue
            try:
                path.unlink()
                removed += 1
            except OSError as exc:
                errors.append(f"{path}: could not remove repo-local vendor copy: {exc}")
        if not (check or what_if):
            _prune_empty_dirs(skill_dir)
            if skill_dir.is_dir() and not any(skill_dir.iterdir()):
                skill_dir.rmdir()
    return removed, errors


def _vendor_copy_files(skill_dir: Path) -> list[Path]:
    """Return every file under ``skill_dir``; raise on any symlink, including ``skill_dir``."""
    if skill_dir.is_symlink():
        raise SkillSupportSyncError(f"{skill_dir}: symlinked skill directory refused")
    files: list[Path] = []
    for path in sorted(skill_dir.rglob("*")):
        if path.is_symlink():
            raise SkillSupportSyncError(f"{path}: symlink inside a skill directory refused")
        if not path.is_dir():
            files.append(path)
    return files


def prune_stale_claude_skill_support(
    repo_root: Path, *, what_if: bool = False, check: bool = False
) -> tuple[int, int, int, list[str]]:
    """Reconcile ``src/claude/skills`` with each skill's distribution flag.

    Formerly ``sync_claude_plugin_skill_support``, when it mirrored support
    files from ``.claude/skills`` into the plugin tree. ADR-109 and ADR-110
    still use the old name; ADR-119 retired the mirror and kept only the prune.

    A shipped skill needs no mirror. ``.claude/skills/<name>`` is a relative
    symlink to ``src/claude/skills/<name>`` (binplace ``link`` row,
    ``binplace_links.py``), so the plugin tree holds the only copy of every
    support file and is edited in place. What remains is the repo-local
    case: a skill that became ``distribution: repo-local`` leaves its old
    ``src/claude/skills/<name>/`` copy behind, and this removes it.

    Removal is refused, as an error, while ``.claude/skills/<name>`` is still
    a symlink: the plugin copy is then the skill's only copy. Replace the
    link with a real directory holding the files first.

    Returns ``(written, removed, skipped, errors)`` for the caller's existing
    report shape; ``written`` and ``skipped`` are always 0. ``check`` and
    ``what_if`` delete nothing and count what would go.
    """
    try:
        repo_local = repo_local_names(repo_root)
    except SkillDistributionError as exc:
        return (0, 0, 0, [str(exc)])
    install_dir = repo_root / _CLAUDE_INSTALL_REL
    still_linked = sorted(name for name in repo_local if (install_dir / name).is_symlink())
    errors = [
        f"{install_dir / name}: repo-local skill is still a symlink into the plugin tree; "
        "replace it with a real directory before the plugin copy is removed"
        for name in still_linked
    ]
    removed, prune_errors = prune_repo_local_vendor_copies(
        repo_root / _CLAUDE_PLUGIN_REL,
        repo_local - frozenset(still_linked),
        check=check,
        what_if=what_if,
    )
    return (0, removed, 0, errors + prune_errors)
