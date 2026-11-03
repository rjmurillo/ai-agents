"""Bundle directories: whole-directory sha256 and a symlink-refusing copy.

A bundle is a skill directory: SKILL.md plus any scripts, references, or
fixtures beside it. A candidate that changes `scripts/` is a different artifact
from its incumbent even when SKILL.md is byte-identical, so identity has to
cover the whole tree.

The digest covers every regular file under the root, ordered by relative POSIX
path, as the path plus the sha256 of the file bytes. It does not cover empty
directories, file modes, or timestamps, so it is stable across platforms and
checkouts. `__pycache__` directories are skipped because running Python writes
them. A symlink anywhere in the tree is refused: a link can point outside the
bundle, so the digest would not describe what a command can reach.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from _skillopt_buffer import file_sha256
from _skillopt_patching import SkillOptError

BUNDLE_DOC = "SKILL.md"
IGNORED_DIR_NAMES = frozenset({"__pycache__"})


def list_bundle_files(root: Path) -> list[Path]:
    """Relative paths of every regular file under root, sorted by POSIX path.

    Raises SkillOptError for a symlink, a non-regular file, or a non-directory.
    """
    if root.is_symlink() or not root.is_dir():
        raise SkillOptError(f"bundle {root} is not a real directory")
    found: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        for entry in current.iterdir():
            rel = entry.relative_to(root)
            if entry.is_symlink():
                raise SkillOptError(f"bundle {root} contains a symlink: {rel.as_posix()}")
            if entry.is_dir():
                if entry.name not in IGNORED_DIR_NAMES:
                    stack.append(entry)
            elif entry.is_file():
                found.append(rel)
            else:
                raise SkillOptError(f"bundle {root} contains a non-regular file: {rel.as_posix()}")
    return sorted(found, key=lambda rel: rel.as_posix())


def bundle_sha256(root: Path) -> str:
    """Hex sha256 over (relative path, file sha256) pairs in sorted path order."""
    digest = hashlib.sha256()
    for rel in list_bundle_files(root):
        digest.update(rel.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(root / rel).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def path_sha256(path: Path | str) -> str:
    """sha256 of a file's bytes, or of a whole bundle when path is a directory."""
    target = Path(path)
    if target.is_dir():
        return bundle_sha256(target)
    return file_sha256(target)


def overlaps(a: Path, b: Path) -> bool:
    """True if either resolved path is the same as, or inside, the other."""
    left, right = a.resolve(), b.resolve()
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def is_inside(child: Path, parent: Path) -> bool:
    """True if child resolves to parent or to a path below it."""
    return child.resolve().is_relative_to(parent.resolve())


def copy_bundle(src: Path, dst: Path, replace: dict[str, bytes] | None = None) -> None:
    """Copy a bundle to a new directory, all or nothing.

    `replace` maps a relative POSIX path to the bytes to write in place of the
    source file. Refuses a missing dst parent, an existing dst, any symlink in
    src, and overlapping paths. The copy lands in a sibling staging directory
    that is renamed into place, so a failure never leaves a partial candidate
    bundle at dst.
    """
    files = list_bundle_files(src)
    if dst.exists() or dst.is_symlink():
        raise SkillOptError(f"{dst} already exists; write the candidate bundle to a new path")
    if not dst.parent.is_dir():
        raise SkillOptError(f"{dst.parent} does not exist")
    if overlaps(src, dst):
        raise SkillOptError("candidate bundle path must not sit inside or contain the incumbent")
    replacements = replace or {}
    staging = dst.parent / f".{dst.name}.staging-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    try:
        for rel in files:
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel.as_posix() in replacements:
                target.write_bytes(replacements[rel.as_posix()])
            else:
                shutil.copy(src / rel, target)
        staging.rename(dst)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
