"""Compare and enumerate skill files for the mirror copy in ``skill_support_mirror``.

Split out of ``skill_support_mirror.py`` (taste-lint file-size ceiling): these
are the pure filesystem predicates and listing the copy loop calls. None of
them writes.
"""

from __future__ import annotations

import stat
from pathlib import Path

SKILL_MD = Path("SKILL.md")


def copy_matches(dst_path: Path, src_path: Path) -> bool:
    """True when ``dst_path`` already has ``src_path``'s bytes and permission bits.

    Mirrors ``binplace_manifest._binplace_one_file``'s own reasoning: byte
    equality alone is not enough, because a file can keep its committed
    content while losing its executable bit (chmod, a re-clone with a
    restrictive umask, an editor save that resets permissions). A missing,
    symlinked, or unreadable destination is never a match, so the caller
    always falls through to a real write for it.
    """
    try:
        dst_stat = dst_path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(dst_stat.st_mode):
        return False
    try:
        if dst_path.read_bytes() != src_path.read_bytes():
            return False
    except OSError:
        return False
    return (dst_stat.st_mode & 0o777) == (src_path.stat().st_mode & 0o777)


def text_matches(dst_path: Path, content: str) -> bool:
    """True when ``dst_path`` already holds ``content`` (UTF-8), byte for byte.

    Used for the SKILL.md/translate branch, which ``write_text`` has never
    mode-preserved (unlike the ``shutil.copy2`` branch ``copy_matches``
    guards), so only content is compared here.
    """
    try:
        return dst_path.read_text(encoding="utf-8") == content
    except OSError:
        return False


def tree_sources(source: Path, plugin_skill_md: Path | None) -> list[Path]:
    """List the paths under ``source`` to mirror, adding a plugin-tree-only ``SKILL.md``.

    A new templated skill has no ``source / "SKILL.md"`` until binplace writes
    it, after every generator, so ``rglob`` alone never yields the file and the
    Copilot mirror would omit the skill's ``SKILL.md`` on the first run. When
    ``plugin_skill_md`` is a file, the render branch reads its bytes, so the
    absent source path only names the file in messages (issue #6537).
    """
    paths = list(source.rglob("*"))
    absent_skill_md = source / SKILL_MD
    if plugin_skill_md is not None and plugin_skill_md.is_file() and not absent_skill_md.exists():
        paths.append(absent_skill_md)
    return paths
