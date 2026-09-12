#!/usr/bin/env python3
"""Load ``templates/platforms/binplace.yaml`` and binplace plugin trees.

ADR-109 (Template-First Plugin Distribution) adds a second output hop no
other template class needed before it: templates render into a PLUGIN tree
(``src/claude/``, ``src/copilot-cli/``), and a separate binplace step then
copies each plugin tree into its INSTALL tree (``.claude/``, ``.github/``).
Per ``.agents/specs/design/DESIGN-025-template-first-compiler-and-binplace.md``,
"Binplace manifest schema" section, the mapping from one hop to the other is
data, not code: one YAML file, ``templates/platforms/binplace.yaml``, read
by this module and by ``build/scripts/build_all.py``'s ``_binplace`` step.

Schema, quoted verbatim from DESIGN-025 (the two rows B1 ships; later
records add more):

    ```yaml
    rows:
      - class: agents
        source: templates/agents
        # .claude.md.tmpl / .copilot.md.tmpl pairs, per agent_templates.py
        plugin_tree: src/claude/agents
        install_tree: .claude/agents
      - class: skills
        source: templates/skills        # existing ADR-108 tree, unchanged by this row's addition
        plugin_tree: null
        # B1: no plugin-tree hop yet; B3 repoints this to src/claude/skills
        install_tree: .claude/skills
        compile: skill_templates
        # delegates to skill_templates.owned_targets, not a class-wide prefix
    ```

    "A row with ``plugin_tree: null`` skips the plugin-tree render hop and
    copies straight from ``source`` to ``install_tree``."

Public API:
    ``load(repo_root) -> list[Row]``
        Every row, validated per-path: relative, no ``..``, resolves inside
        the repository, no symlink at the resolved path (CWE-22/CWE-59,
        mirroring ``skill_templates._name_validation_error``'s shape), and
        ``install_tree`` starts with ``.claude/`` or ``.github/``. Raises
        :class:`BinplaceConfigError` (exit 2) on the first violation, per
        DESIGN-025's failure-modes table: "Manifest row pointing outside the
        repository ... Exit 2 at manifest load, before any class's compile
        runs." An absent manifest file yields an empty list, not an error
        (mirrors every other compile module's "class not present yet" state).
    ``claude_allowlist(repo_root) -> set[Path]``
        The write allowlist ``build_all.assert_no_claude_writes`` accepts,
        computed by unioning every ``.claude/``-rooted row's owned paths
        (DESIGN-025, "How ``assert_no_claude_writes`` derives its
        allowlist"). The ``skills`` row still delegates to
        ``skill_templates.owned_targets`` rather than walking a plugin tree,
        because that row's ``plugin_tree`` stays ``null`` until B3.
    ``binplace(repo_root, *, check) -> BinplaceResult``
        For every row with a non-``null`` ``plugin_tree``: copies each file
        under it to the same relative path under ``install_tree``,
        byte-for-byte, using the same no-symlink-follow write helpers
        ``build_all.py`` uses for its own restore step (CWE-59); in
        ``check=True`` mode nothing is written and a byte mismatch is
        reported as drift instead. A file under ``install_tree`` with no
        counterpart under ``plugin_tree`` is left untouched and reported as
        ``unowned``, never deleted.

Stricter/looser/different than canonical (``skill_templates.py``):

- Same: the CWE-22 (repo-containment) and CWE-59 (no-symlink-follow write)
  defenses mirror ``skill_templates._name_validation_error`` and
  ``build_all.py``'s restore helpers one-for-one.
- Different: validation happens once, at manifest ``load()`` time, over a
  small, owner-reviewed (CODEOWNERS) set of rows, not per-discovered-name
  at compile time over a large, contributor-editable set of skill names.
  DESIGN-025's failure-modes table draws this distinction explicitly:
  "Exit 2 at manifest load, before any class's compile runs."

EXIT CODES (``0=ok|1=logic|2=config`` per ``AGENTS.md`` Standards; callers
fold ``BinplaceResult.exit_code`` into their own aggregate the same way they
already do for ``skill_templates.CompileResult``):
  0 - the manifest has no rows with a non-null ``plugin_tree`` yet, or every
      such row's plugin tree matches its install tree
  2 - a byte mismatch between a plugin-tree file and its install-tree
      counterpart, in ``check=True`` mode only (in write mode a mismatch is
      corrected, not reported as an error); a malformed or malicious
      manifest row is always exit 2, in either mode, at ``load()`` time
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import skill_templates  # noqa: E402
from atomic_write import (  # noqa: E402
    publish_bytes_atomically,
    read_bytes_no_redirect,
)
from yaml_loader import ConfigError, load_platform_config, validate_relative_path  # noqa: E402

_MANIFEST_REL = Path("templates") / "platforms" / "binplace.yaml"
_SKILLS_COMPILE_DELEGATE = "skill_templates"


class BinplaceConfigError(Exception):
    """A manifest row fails path validation, or the manifest is malformed. Exit 2."""


@dataclass(frozen=True)
class Row:
    """One binplace manifest row: source, optional plugin-tree hop, install target."""

    class_name: str
    source: Path
    plugin_tree: Path | None
    install_tree: Path
    compile: str | None = None


@dataclass
class BinplaceResult:
    """Outcome of one :func:`binplace` run across every manifest row."""

    written: list[str] = field(default_factory=list)
    unowned: list[str] = field(default_factory=list)
    drifted: list[str] = field(default_factory=list)
    exit_code: int = 0


def _validate_path_field(repo_root: Path, label: str, value: str) -> Path:
    """Validate one manifest path field; return it resolved against ``repo_root``.

    Reuses ``yaml_loader.validate_relative_path`` for the relative-path and
    ``..``-traversal check (DRY: the same check every other platform YAML
    field already gets), then adds the containment and no-symlink checks
    ``skill_templates._name_validation_error`` performs for its own class
    (CWE-22/CWE-59): the resolved path MUST lie inside the resolved
    repository root, and the path itself (its final component, unresolved)
    MUST NOT be a symlink. Both checks tolerate a path that does not exist
    yet, since ``install_tree`` targets are often created by this module's
    own :func:`binplace` on first run.
    """
    errors = validate_relative_path(label, value)
    if errors:
        raise BinplaceConfigError("; ".join(errors))
    candidate = repo_root / value
    resolved_repo = repo_root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_repo):
        raise BinplaceConfigError(
            f"{label} {value!r} resolves to {resolved}, outside the repository root {resolved_repo}"
        )
    if candidate.is_symlink():
        raise BinplaceConfigError(f"{label} {value!r} is a symlink, not a real path")
    return candidate


def _validate_install_tree_prefix(label: str, value: str) -> None:
    """Reject an ``install_tree`` that does not name a ``.claude/`` or ``.github/`` path.

    Every row's ``install_tree`` is a write target this manifest legitimizes
    (DESIGN-025: "Each row's ``install_tree`` value is a path prefix under
    ``.claude/`` or ``.github/``"); a row naming anything else would widen
    ``claude_allowlist``'s and ``binplace``'s reach past the two plugin
    install roots this record governs.
    """
    if value in (".claude", ".github"):
        return
    if value.startswith(".claude/") or value.startswith(".github/"):
        return
    raise BinplaceConfigError(f"{label} {value!r} must be under .claude/ or .github/")


def load(repo_root: Path) -> list[Row]:
    """Load and validate every row in ``templates/platforms/binplace.yaml``.

    An absent manifest file returns an empty list rather than raising: no
    class has a binplace row yet is a valid state (mirrors every other
    compile module's "absent template directory yields an empty mapping"
    rule), not a configuration error.
    """
    manifest_path = repo_root / _MANIFEST_REL
    if not manifest_path.is_file():
        return []

    try:
        doc = load_platform_config(manifest_path)
    except ConfigError as exc:
        raise BinplaceConfigError(str(exc)) from exc

    raw_rows = doc.get("rows")
    if not isinstance(raw_rows, list):
        raise BinplaceConfigError(f"{manifest_path}: missing or malformed `rows` list")

    rows: list[Row] = []
    seen_classes: set[str] = set()
    for entry in raw_rows:
        rows.append(_load_one_row(repo_root, manifest_path, entry, seen_classes))
    return rows


def _load_one_row(
    repo_root: Path,
    manifest_path: Path,
    entry: object,
    seen_classes: set[str],
) -> Row:
    """Validate one raw manifest entry and return its :class:`Row`.

    Extracted out of :func:`load`'s loop body to hold that function's
    cyclomatic complexity down, the same reason ``skill_templates.py``
    and ``agent_templates.py`` split their own per-candidate validation
    into a dedicated helper.
    """
    if not isinstance(entry, dict):
        raise BinplaceConfigError(f"{manifest_path}: each row must be a mapping")

    class_name = str(entry.get("class") or "")
    if not class_name:
        raise BinplaceConfigError(f"{manifest_path}: a row is missing `class`")
    if class_name in seen_classes:
        raise BinplaceConfigError(f"{manifest_path}: duplicate class {class_name!r}")
    seen_classes.add(class_name)

    source_raw = str(entry.get("source") or "")
    source = _validate_path_field(repo_root, f"rows[{class_name}].source", source_raw)

    plugin_tree_raw = entry.get("plugin_tree")
    plugin_tree: Path | None = None
    if plugin_tree_raw is not None:
        plugin_tree = _validate_path_field(
            repo_root, f"rows[{class_name}].plugin_tree", str(plugin_tree_raw)
        )

    install_tree_str = str(entry.get("install_tree") or "")
    install_tree = _validate_path_field(
        repo_root, f"rows[{class_name}].install_tree", install_tree_str
    )
    _validate_install_tree_prefix(f"rows[{class_name}].install_tree", install_tree_str)

    compile_raw = entry.get("compile")
    compile_name = str(compile_raw) if compile_raw is not None else None

    return Row(class_name, source, plugin_tree, install_tree, compile_name)


def claude_allowlist(repo_root: Path) -> set[Path]:
    """Return the write allowlist ``build_all.assert_no_claude_writes`` accepts.

    Union over every row whose ``install_tree`` is under ``.claude/``
    (DESIGN-025, "How ``assert_no_claude_writes`` derives its allowlist"):
    the ``skills`` row (identified by ``compile: skill_templates``)
    delegates to :func:`skill_templates.owned_targets` unchanged, since that
    row's allowlist is scoped per skill directory, not by walking a plugin
    tree, until a later record gives skills its own ``src/claude/skills``
    plugin tree. Every other ``.claude/``-rooted row with a non-``null``
    ``plugin_tree`` contributes each file under it, mapped onto its
    ``install_tree`` counterpart path.
    """
    allow: set[Path] = set()
    for row in load(repo_root):
        if not _is_claude_rooted(row.install_tree, repo_root):
            continue
        if row.compile == _SKILLS_COMPILE_DELEGATE:
            allow |= skill_templates.owned_targets(repo_root)
            continue
        if row.plugin_tree is None:
            continue
        allow |= _plugin_tree_install_paths(row.plugin_tree, row.install_tree)
    return allow


def _is_claude_rooted(install_tree: Path, repo_root: Path) -> bool:
    try:
        relative = install_tree.relative_to(repo_root)
    except ValueError:
        return False
    return relative.parts[:1] == (".claude",)


def _plugin_tree_install_paths(plugin_tree: Path, install_tree: Path) -> set[Path]:
    """Return each file under ``plugin_tree``, mapped onto ``install_tree``."""
    if not plugin_tree.is_dir():
        return set()
    paths: set[Path] = set()
    for src_path in plugin_tree.rglob("*"):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(plugin_tree)
        paths.add(install_tree / rel)
    return paths


def binplace(repo_root: Path, *, check: bool) -> BinplaceResult:
    """Copy each row's plugin tree into its install tree, byte for byte.

    Rows with ``plugin_tree: null`` are skipped entirely: nothing under
    ``source`` is copied by this function for them (DESIGN-025: the
    ``skills`` row's target is written directly by
    ``skill_templates.compile_all``, not by this step, until a later record
    gives it a plugin tree). ``check=True`` never writes: a byte mismatch is
    recorded as drift and the install tree is left exactly as it was, the
    same read-only contract ``build_all.py --check`` already gives every
    other class. A file under ``install_tree`` with no counterpart under
    ``plugin_tree`` is reported as ``unowned`` and left untouched, never
    deleted: this class does not own it.
    """
    result = BinplaceResult()
    for row in load(repo_root):
        if row.plugin_tree is None:
            continue
        _binplace_one_row(row.plugin_tree, row.install_tree, check=check, result=result)
    return result


def _binplace_one_row(
    plugin_tree: Path, install_tree: Path, *, check: bool, result: BinplaceResult
) -> None:
    """Binplace one row's plugin tree, folding written/drifted/unowned into ``result``.

    Extracted out of :func:`binplace`'s loop body to hold that function's
    cyclomatic complexity down.
    """
    if not plugin_tree.is_dir():
        return
    owned_relatives: set[Path] = set()
    for src_path in sorted(plugin_tree.rglob("*")):
        if src_path.is_dir():
            continue
        rel = src_path.relative_to(plugin_tree)
        owned_relatives.add(rel)
        _binplace_one_file(src_path, install_tree / rel, check=check, result=result)

    if not install_tree.is_dir():
        return
    for existing in sorted(install_tree.rglob("*")):
        if existing.is_dir():
            continue
        rel = existing.relative_to(install_tree)
        if rel not in owned_relatives:
            result.unowned.append(str(existing))


def _current_bytes(dst_path: Path) -> bytes | None:
    """Read ``dst_path``'s bytes with no-symlink-follow, or ``None`` when absent/redirecting.

    A symlink or Windows junction at ``dst_path`` is treated as "does not
    match" rather than raising: :func:`_binplace_one_file` then either
    reports it as drift (check mode) or replaces it via
    ``publish_bytes_atomically``, which itself never writes through a link
    (CWE-59).
    """
    if not (dst_path.is_file() or dst_path.is_symlink()):
        return None
    try:
        data: bytes = read_bytes_no_redirect(dst_path)
    except OSError:
        return None
    return data


def _binplace_one_file(
    src_path: Path, dst_path: Path, *, check: bool, result: BinplaceResult
) -> None:
    """Compare one plugin-tree file to its install-tree counterpart and act."""
    content = src_path.read_bytes()
    if _current_bytes(dst_path) == content:
        return
    if check:
        result.drifted.append(str(dst_path))
        result.exit_code = max(result.exit_code, 2)
        return
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    publish_bytes_atomically(dst_path, content)
    result.written.append(str(dst_path))
