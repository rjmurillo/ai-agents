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
from collections.abc import Iterable
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from atomic_write import (  # noqa: E402
    publish_bytes_atomically,
    read_bytes_no_redirect,
    reject_symlinked_ancestors,
)
from binplace_manifest import is_bytecode_artifact  # noqa: E402
from frontmatter_key_drop import (  # noqa: E402
    drop_keys_from_skill_md,
    split_fenced_frontmatter,
)
from hermes_pack_checks import (  # noqa: E402
    PackFile,
    check_assignment,
    check_excluded_files,
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
from lib_render import LibRenderError, render_lib_files  # noqa: E402
from yaml_loader import validate_relative_path  # noqa: E402

INDEX_NAME = "README.md"
# Stale pruning deletes every file under outputDir that the tree does not name, so
# outputDir must stay inside this directory or a "." would prune the repository.
_OUTPUT_ROOT_LIMIT = "src/hermes"
_PLAIN_FILE_MODE = 0o644
_EXECUTABLE_FILE_MODE = 0o755
_SKILL_MD = "SKILL.md"


def _plugin_json(pack: PackSpec) -> bytes:
    manifest = {
        "$schema": PLUGIN_SCHEMA_URL,
        "name": pack.dir_name,
        "description": pack.description,
        "author": {"name": "rjmurillo"},
        "license": "Apache-2.0",
    }
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _git_mode(path: Path) -> int:
    """Return 0o755 for an owner-executable file, else 0o644.

    Git records only those two modes. Copying the raw bits would make the
    rendered tree depend on the umask of whoever ran the build.
    """
    executable = stat.S_IMODE(path.stat().st_mode) & stat.S_IXUSR
    return _EXECUTABLE_FILE_MODE if executable else _PLAIN_FILE_MODE


def drop_excluded_pointer_lines(text: str, skill: str, excluded_files: Iterable[str]) -> str:
    """Remove SKILL.md lines that point at a file no pack carries.

    An excluded file is absent from every pack, so a line naming it would
    send a Hermes user to nothing. A line counts when it names the excluded
    path relative to its skill, and the file is this skill's own or the line
    also names the owning skill in backticks. Frontmatter is never touched,
    because dropping a wrapped ``description`` line would corrupt it.
    """
    targets: list[tuple[str, str]] = []
    for entry in excluded_files:
        owner, _, rel = entry.partition("/")
        if rel:
            targets.append((owner, rel))
    parts = split_fenced_frontmatter(text)
    frontmatter, body = parts if parts is not None else ("", text)
    kept = [
        line
        for line in body.splitlines(keepends=True)
        if not any(
            rel in line and (owner == skill or f"`{owner}`" in line) for owner, rel in targets
        )
    ]
    return frontmatter + "".join(kept)


def _skill_pack_files(source_root: Path, skill: str, config: HermesConfig) -> dict[str, PackFile]:
    files: dict[str, PackFile] = {}
    skill_dir = source_root / skill
    for path in skill_files(skill_dir):
        rel = path.relative_to(skill_dir).as_posix()
        if f"{skill}/{rel}" in config.excluded_files:
            continue
        data = read_bytes_no_redirect(path)
        mode = _git_mode(path)
        if rel == _SKILL_MD:
            try:
                text = drop_keys_from_skill_md(data.decode("utf-8"), config.frontmatter_drop)
            except (ValueError, UnicodeDecodeError) as exc:
                raise HermesPackError([f"{skill}/{_SKILL_MD}: {exc}"]) from exc
            text = drop_excluded_pointer_lines(text, skill, config.excluded_files)
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
        "No skill links to a script, reference, or other support file in another pack by path.",
        "Some skills name a skill or script from another pack.",
        "Install every pack for the full set.",
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
    if config.excluded_files:
        lines += ["## Excluded files", "", "These files of a shipped skill ship in no pack.", ""]
        lines += [f"- `{path}`: {why}" for path, why in sorted(config.excluded_files.items())]
        lines.append("")
    return "\n".join(lines).encode("utf-8")


def plan_tree(repo_root: Path, config: HermesConfig) -> dict[str, PackFile]:
    """Build every pack and the index in memory; raise on any failed rule.

    The returned keys are paths under ``outputDir``. Nothing is written.
    """
    source_root = repo_root / config.source_dir
    shipped = discover_skills(source_root)
    problems = check_assignment(shipped, config)
    problems += check_excluded_files(source_root, config)
    refs = find_references(source_root, shipped, config.excluded_files)
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
    """Return every file under ``root`` that stale pruning may consider.

    Bytecode is left out (issue #7659). Pytest imports a pack's ``lib/`` and
    skill scripts and writes ``__pycache__`` there; the tree never names those
    files, so without the skip ``--check`` reports them as stale. The rule is
    :func:`binplace_manifest.is_bytecode_artifact`, the one binplace and the
    skill mirrors use, applied to the path relative to ``root``.

    A symlink is never bytecode, whatever its name: CPython writes regular
    files. Skipping a ``__pycache__`` link would leave it on disk, and
    ``_prune_empty_dirs`` would then call ``rmdir`` on it.
    """
    if not root.is_dir():
        return set()
    files: set[str] = set()
    for path in root.rglob("*"):
        if not (path.is_symlink() or path.is_file()):
            continue
        rel = path.relative_to(root)
        if path.is_symlink() or not is_bytecode_artifact(rel):
            files.add(rel.as_posix())
    return files


def _prune_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def _refuse_symlinked_ancestors(output_root: Path, rels: list[str]) -> None:
    """Raise when any path in ``rels`` sits below a symlinked directory of ``output_root``."""
    problems = []
    for rel in rels:
        problem = reject_symlinked_ancestors(output_root, "Hermes output", output_root / rel)
        if problem is not None:
            problems.append(problem)
    if problems:
        raise HermesPackError(problems)


def apply_tree(
    output_root: Path,
    tree: dict[str, PackFile],
    *,
    check: bool,
    what_if: bool,
    report_root: str,
) -> tuple[int, int]:
    """Write ``tree`` under ``output_root``; return ``(written, removed)``.

    A file is written when its bytes or permission bits differ. A file under
    ``output_root`` that ``tree`` does not name is removed, except bytecode,
    which ``_existing_files`` leaves out, so it is neither reported nor removed.
    With ``check`` or ``what_if`` nothing changes on disk and the counts say
    what would change. ``report_root`` is the repo-relative ``outputDir`` that
    ``check`` prefixes to each ``STALENESS DETECTED`` path.
    """
    changed = [
        rel for rel, packed in sorted(tree.items()) if not _matches(output_root / rel, packed)
    ]
    stale = sorted(_existing_files(output_root) - set(tree))
    _refuse_symlinked_ancestors(output_root, [*tree, *stale])
    for rel in changed:
        print(f"  {'DRIFT' if check else 'Copy'}: {output_root / rel}")
    for rel in stale:
        print(f"  {'DRIFT' if check else 'Remove'} (stale): {output_root / rel}")
    if check:
        # The pre-PR gate reads build_all.py's git-diff list, which never names a
        # gitignored stale file, and ``STALENESS DETECTED: <kind>: <path>`` lines
        # (``_STALE_ITEM`` in ``scripts/validation/generated_staleness_report.py``).
        # Paths are repo-relative, so a file both lists name counts once (issue
        # #7659). ``tests/build_scripts/test_hermes_packs_bytecode.py`` feeds this
        # output to that parser.
        for kind, rels in (
            ("differs from its sources", changed),
            ("holds a file no pack names", stale),
        ):
            for rel in rels:
                print(
                    f"STALENESS DETECTED: Hermes pack {kind}: {report_root}/{rel}", file=sys.stderr
                )
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
    # Compare the limit on the path as written: resolving would follow a
    # committed `src/hermes -> ..` link and pass. The ancestor walk then
    # refuses a link at src, src/hermes, or any folder below it.
    if Path(config.output_dir).parts[:2] != Path(_OUTPUT_ROOT_LIMIT).parts:
        raise HermesPackError(
            [f"outputDir must be {_OUTPUT_ROOT_LIMIT} or under it: {config.output_dir}"]
        )
    unresolved = repo_root / config.output_dir
    link_error = reject_symlinked_ancestors(repo_root, "outputDir", unresolved / INDEX_NAME)
    if link_error is not None:
        raise HermesPackError([link_error])
    root = unresolved.resolve()
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
        written, removed = apply_tree(
            output_root,
            tree,
            check=check,
            what_if=what_if,
            report_root=Path(config.output_dir).as_posix(),
        )
    except HermesPackError as exc:
        for problem in exc.problems:
            print(f"Error: {problem}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: cannot write the Hermes tree: {exc}", file=sys.stderr)
        return 1
    skills = sum(len(pack.skills) for pack in config.packs)
    print(f"Hermes packs: {len(config.packs)} pack(s), {skills} skill(s), {len(tree)} file(s)")
    print(f"Hermes files {'drifted' if check else 'written'}: {written}, stale: {removed}")
    return 1 if check and (written or removed) else 0
