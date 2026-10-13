"""Render the Hermes plugin packs under ``src/hermes/`` (ADR-115 Decision 6).

Hermes refuses a plugin over 400 files or 10 MB, and the shipped skills hold
more than that, so the tree is a set of packs. Each pack is a portable Agent
Plugins v1 package::

    src/hermes/project-toolkit-<key>/
        plugin.json
        skills/<name>/...      from src/claude/skills/<name>/
        lib/...                the shared Python packages, one copy per pack

``templates/platforms/hermes.yaml`` (``artifacts.skills`` with mode
``hermes-packs``) holds the hand-maintained ``packs`` and ``excluded`` tables.
The pack is the unit a skill's scripts resolve ``lib/`` against, so a skill may
only refer to skills in its own pack (``hermes_pack_checks``).

The generator owns the whole ``src/hermes/`` directory, ``lib/`` included. It
builds each pack in memory, runs every check, and only then writes or compares.
A failing check writes nothing.

EXIT CODES (ADR-035)
  0 - rendered, or ``check`` found no drift
  1 - ``check`` found drift, or a file could not be written
  2 - the stanza or the build is invalid (a rule in ADR-115 Decision 6 failed)
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from atomic_write import publish_bytes_atomically, read_bytes_no_redirect  # noqa: E402
from frontmatter_key_drop import drop_keys_from_skill_md  # noqa: E402
from hermes_pack_checks import (  # noqa: E402
    PackFile,
    check_assignment,
    check_pack_limits,
    check_references,
    discover_skills,
    find_references,
    skill_files,
)
from hermes_pack_config import (  # noqa: E402
    PLUGIN_SCHEMA_URL,
    HermesConfig,
    HermesPackError,
    PackSpec,
    parse_stanza,
)
from lib_mirror import LibRenderError, render_lib_files  # noqa: E402
from yaml_loader import validate_relative_path  # noqa: E402

INDEX_NAME = "README.md"
_PLAIN_FILE_MODE = 0o644
_EXECUTABLE_FILE_MODE = 0o755
_SKILL_MD = "SKILL.md"


def _plugin_json(pack: PackSpec) -> bytes:
    manifest = {
        "$schema": PLUGIN_SCHEMA_URL,
        "name": pack.dir_name,
        "description": pack.description,
        "author": {"name": "rjmurillo"},
        "license": "MIT",
    }
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _git_mode(path: Path) -> int:
    """Return 0o755 for an owner-executable file, else 0o644.

    Git records only those two modes. Copying the raw bits would make the
    rendered tree depend on the umask of whoever ran the build.
    """
    executable = stat.S_IMODE(path.stat().st_mode) & stat.S_IXUSR
    return _EXECUTABLE_FILE_MODE if executable else _PLAIN_FILE_MODE


def _skill_pack_files(source_root: Path, skill: str, config: HermesConfig) -> dict[str, PackFile]:
    files: dict[str, PackFile] = {}
    skill_dir = source_root / skill
    for path in skill_files(skill_dir):
        rel = path.relative_to(skill_dir).as_posix()
        data = read_bytes_no_redirect(path)
        mode = _git_mode(path)
        if rel == _SKILL_MD:
            try:
                text = drop_keys_from_skill_md(data.decode("utf-8"), config.frontmatter_drop)
            except (ValueError, UnicodeDecodeError) as exc:
                raise HermesPackError([f"{skill}/{_SKILL_MD}: {exc}"]) from exc
            data = text.encode("utf-8")
        files[f"skills/{skill}/{rel}"] = PackFile(data, mode)
    return files


def build_pack(
    source_root: Path, pack: PackSpec, config: HermesConfig, lib: dict[str, bytes]
) -> dict[str, PackFile]:
    """Return one pack's files as ``{path under the pack: PackFile}``."""
    files = {"plugin.json": PackFile(_plugin_json(pack), _PLAIN_FILE_MODE)}
    for skill in pack.skills:
        files.update(_skill_pack_files(source_root, skill, config))
    for rel, data in lib.items():
        files[f"lib/{rel}"] = PackFile(data, _PLAIN_FILE_MODE)
    return files


def render_index(config: HermesConfig) -> bytes:
    """Return ``README.md``: each pack with its skills, then each excluded skill and why."""
    lines = [
        "# Hermes plugin packs",
        "",
        "Each folder below is a portable Agent Plugins v1 package for Hermes.",
        "A pack holds the skills listed under it and one copy of `lib/`.",
        "Skills in one pack never refer to skills in another pack.",
        "",
    ]
    for pack in config.packs:
        lines += [f"## {pack.dir_name}", "", pack.description, ""]
        lines += [f"- `{skill}`" for skill in sorted(pack.skills)]
        lines.append("")
    lines += ["## Excluded skills", ""]
    if config.excluded:
        lines += ["These skills ship in no pack.", ""]
        lines += [f"- `{name}`: {reason}" for name, reason in sorted(config.excluded.items())]
    else:
        lines.append("No skill is excluded.")
    lines.append("")
    return "\n".join(lines).encode("utf-8")


def plan_tree(repo_root: Path, config: HermesConfig) -> dict[str, PackFile]:
    """Build every pack and the index in memory; raise on any failed rule.

    The returned keys are paths under ``outputDir``. Nothing is written.
    """
    source_root = repo_root / config.source_dir
    shipped = discover_skills(source_root)
    problems = check_assignment(shipped, config)
    refs = find_references(source_root, shipped)
    problems += check_references(config, refs)
    if problems:
        raise HermesPackError(problems)
    try:
        lib = render_lib_files(repo_root)
    except LibRenderError as exc:
        raise HermesPackError([str(exc)]) from exc
    tree: dict[str, PackFile] = {}
    for pack in config.packs:
        files = build_pack(source_root, pack, config, lib)
        problems += check_pack_limits(pack.dir_name, files, config)
        tree.update({f"{pack.dir_name}/{rel}": packed for rel, packed in files.items()})
    if problems:
        raise HermesPackError(problems)
    tree[INDEX_NAME] = PackFile(render_index(config), _PLAIN_FILE_MODE)
    return tree


def _matches(dst: Path, packed: PackFile) -> bool:
    try:
        info = dst.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return False
    # Only the owner-execute bit is content: git stores 644 or 755, and the
    # group and other bits on disk follow the umask of the checkout.
    if bool(info.st_mode & stat.S_IXUSR) != bool(packed.mode & stat.S_IXUSR):
        return False
    return bool(dst.read_bytes() == packed.data)


def _existing_files(root: Path) -> set[str]:
    if not root.is_dir():
        return set()
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_symlink() or path.is_file()
    }


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def apply_tree(
    output_root: Path, tree: dict[str, PackFile], *, check: bool, what_if: bool
) -> tuple[int, int]:
    """Write ``tree`` under ``output_root``; return ``(written, removed)``.

    A file is written when its bytes or permission bits differ. A file under
    ``output_root`` that ``tree`` does not name is removed. With ``check`` or
    ``what_if`` nothing changes on disk and the counts say what would change.
    """
    changed = [
        rel for rel, packed in sorted(tree.items()) if not _matches(output_root / rel, packed)
    ]
    stale = sorted(_existing_files(output_root) - set(tree))
    for rel in changed:
        print(f"  {'DRIFT' if check else 'Copy'}: {output_root / rel}")
    for rel in stale:
        print(f"  {'DRIFT' if check else 'Remove'} (stale): {output_root / rel}")
    if check or what_if:
        return len(changed), len(stale)
    for rel in changed:
        dst = output_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        publish_bytes_atomically(dst, tree[rel].data, mode=tree[rel].mode)
    for rel in stale:
        (output_root / rel).unlink()
    _prune_empty_dirs(output_root)
    return len(changed), len(stale)


def _output_root(repo_root: Path, config: HermesConfig) -> Path:
    errors = validate_relative_path("outputDir", config.output_dir)
    errors += validate_relative_path("sourceDir", config.source_dir)
    if errors:
        raise HermesPackError(errors)
    root = (repo_root / config.output_dir).resolve()
    if not root.is_relative_to(repo_root.resolve()):
        raise HermesPackError([f"outputDir escapes the repository: {config.output_dir}"])
    return Path(root)


def generate_hermes_packs(
    stanza: dict[str, object], repo_root: Path, *, what_if: bool = False, check: bool = False
) -> int:
    """Render (or, with ``check``, compare) the Hermes tree; return an ADR-035 exit code."""
    try:
        config = parse_stanza(stanza)
        output_root = _output_root(repo_root, config)
        tree = plan_tree(repo_root, config)
    except HermesPackError as exc:
        for problem in exc.problems:
            print(f"Error: {problem}", file=sys.stderr)
        return 2
    try:
        written, removed = apply_tree(output_root, tree, check=check, what_if=what_if)
    except OSError as exc:
        print(f"Error: cannot write the Hermes tree: {exc}", file=sys.stderr)
        return 1
    skills = sum(len(pack.skills) for pack in config.packs)
    print(f"Hermes packs: {len(config.packs)} pack(s), {skills} skill(s), {len(tree)} file(s)")
    print(f"Hermes files {'drifted' if check else 'written'}: {written}, stale: {removed}")
    return 1 if check and (written or removed) else 0
