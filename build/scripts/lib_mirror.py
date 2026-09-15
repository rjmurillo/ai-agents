#!/usr/bin/env python3
"""Compile ``scripts/{hook_utilities,github_core,ai_review_common}/`` into
the lib plugin trees (ADR-109 B5, TASK-035).

Absorbs `scripts/sync_plugin_lib.py`'s copy logic (its `SYNC_PAIRS`,
`SYNC_FILE_PAIRS`, and `IMPORT_CONVERSIONS`, unchanged) so `build_all.py`
performs the whole scripts/ -> plugin tree -> install tree chain in one
run, instead of a separately invoked script whose order relative to
`build_all.py` mattered (issue #2613, `.claude/rules/generated-artifacts.md`
"Generator order: sync before build", removed by this change).

Two destinations per source, per `templates/platforms/binplace.yaml`'s
`lib-*` and `lib-*-copilot` rows:

    scripts/<pkg>/*.py  --IMPORT_CONVERSIONS-->  src/claude/lib/<pkg>/*.py
    scripts/<pkg>/*.py  --IMPORT_CONVERSIONS-->  src/copilot-cli/lib/<pkg>/*.py

`binplace_manifest.binplace()` then copies `src/claude/lib/<pkg>/` onto its
`.claude/lib/<pkg>/` install-tree counterpart; `src/copilot-cli/lib/<pkg>/`
has no further hop (it IS the Copilot plugin's own lib tree). The two
`SYNC_FILE_PAIRS` entries (`bootstrap.py`, `validate_review_marker.py`) get
the same two-destination treatment, file-shaped (DESIGN-025 "lib-bootstrap"
and "skills-sidecar" rows).

`.claude/lib/` also carries hand-maintained files this module never touches
(`claude_hook_dispatch.py`, `paths.py`, `qa_report.py`, and siblings; two
`CLAUDE.md` sidecars under `hook_utilities/` and `github_core/`): they have
no `scripts/` canonical source, sync_plugin_lib.py never copied them either
(its directory sync only ever looked at `.py` files inside its three
registered destinations), and this module does not delete or overwrite
anything outside the paths it explicitly owns (see `_remove_stale_files`).
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from atomic_write import publish_bytes_atomically, read_bytes_no_redirect  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration (moved unchanged from scripts/sync_plugin_lib.py)
# ---------------------------------------------------------------------------

# Package name -> canonical scripts/ source. Each package lands at
# "<plugin_root>/<package>" under every root in PLUGIN_ROOTS.
PACKAGES: tuple[str, ...] = ("hook_utilities", "github_core", "ai_review_common")

# Every plugin tree a package (or a SYNC_FILE_PAIRS-equivalent single file)
# is rendered into. `.claude/lib/` is never a render target here: it is an
# install tree, reached only via `binplace_manifest.binplace()` copying
# `src/claude/lib/` onto it (templates/platforms/binplace.yaml `lib-*` rows).
PLUGIN_ROOTS: tuple[str, ...] = ("src/claude/lib", "src/copilot-cli/lib")

# Individual file copies: (source file, destination file name under each
# PLUGIN_ROOTS entry). Byte-for-byte copies of a single module that lives at
# the top level of the destination lib tree so `from bootstrap import ...`
# resolves when the lib root is on sys.path. The source MUST be
# import-self-contained (no `scripts` package imports) because a top-level
# module cannot use the package-relative rewrite (see `_imports_scripts_package`).
SYNC_FILE_NAMES: tuple[tuple[str, str], ...] = (
    ("scripts/hook_utilities/bootstrap.py", "bootstrap.py"),
)

# The one SYNC_FILE_PAIRS entry with no plugin-tree hop: it lands directly
# under `.claude/skills/review/scripts/`, outside every `lib` row's prefix
# and outside the `skills` row's per-skill-directory allowlist (DESIGN-025
# "The lib copy absorbing scripts/sync_plugin_lib.py"). Its own manifest row
# (`skills-sidecar`) still gives it a `src/claude/skills/review/scripts/`
# plugin tree, so this module writes only the two destinations that row and
# its `binplace()` counterpart expect.
SKILLS_SIDECAR_SOURCE = "scripts/validation/validate_review_marker.py"
SKILLS_SIDECAR_PLUGIN_TREE = "src/claude/skills/review/scripts/validate_review_marker.py"
SKILLS_SIDECAR_INSTALL_TREE = ".claude/skills/review/scripts/validate_review_marker.py"

# Read by scripts/validation/validate_sync_registry.py (single source of
# truth for "which scripts/ packages are registered for lib distribution").
# Shape preserved from scripts/sync_plugin_lib.py's original SYNC_PAIRS so
# that read-only provenance gate needs no change.
SYNC_PAIRS: list[tuple[str, str]] = [
    (f"scripts/{pkg}", f".claude/lib/{pkg}") for pkg in PACKAGES
]

IMPORT_CONVERSIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"from scripts\.github_core\.(\w+) import"), r"from .\1 import"),
    (re.compile(r"from scripts\.hook_utilities\.(\w+) import"), r"from .\1 import"),
    (re.compile(r"from scripts\.ai_review_common\.(\w+) import"), r"from .\1 import"),
    (re.compile(r"from scripts\.github_core import"), "from . import"),
    (re.compile(r"from scripts\.hook_utilities import"), "from . import"),
    (re.compile(r"from scripts\.ai_review_common import"), "from . import"),
]

# Files that exist only in a destination package dir and must not be
# deleted during sync (moved unchanged from sync_plugin_lib.py; empty today).
LIB_ONLY_FILES: set[str] = set()


@dataclass
class LibMirrorResult:
    """Outcome of one :func:`compile_all` run."""

    changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    inputs: int = 0
    outputs: int = 0

    @property
    def had_errors(self) -> bool:
        return bool(self.errors)


# ---------------------------------------------------------------------------
# Directory sync (SYNC_PAIRS), moved from scripts/sync_plugin_lib.py
# ---------------------------------------------------------------------------


def _convert_imports(content: str) -> str:
    """Replace absolute imports with relative imports."""
    for pattern, replacement in IMPORT_CONVERSIONS:
        content = pattern.sub(replacement, content)
    return content


def _transform_file(src_path: Path) -> bytes:
    """Read a source file and return its plugin-ready bytes."""
    content = read_bytes_no_redirect(src_path).decode("utf-8")
    return _convert_imports(content).encode("utf-8")


def _resolve_pair(repo_root: Path, src_rel: str, dst_rel: str) -> tuple[Path, Path, list[str]]:
    """Validate and resolve one source/destination pair, containment-checked."""
    src_dir = (repo_root / src_rel).resolve()
    dst_dir = (repo_root / dst_rel).resolve()
    repo_root_resolved = repo_root.resolve()
    errors: list[str] = []
    if not src_dir.is_relative_to(repo_root_resolved):
        errors.append(f"[ERROR] Source path escapes repo root: {src_rel}")
    if not dst_dir.is_relative_to(repo_root_resolved):
        errors.append(f"[ERROR] Destination path escapes repo root: {dst_rel}")
    return src_dir, dst_dir, errors


def sync_pair(
    repo_root: Path,
    src_rel: str,
    dst_rel: str,
    *,
    check_only: bool,
) -> tuple[list[str], bool]:
    """Sync one source directory's `.py` files to its lib counterpart.

    Returns (change descriptions, had_errors). Non-`.py` files already
    present at the destination (a hand-maintained `CLAUDE.md` sidecar, for
    example) are left untouched: only `.py` files are ever read from the
    source or removed as stale, matching `scripts/sync_plugin_lib.py`'s
    original scope exactly.
    """
    src_dir, dst_dir, errors = _resolve_pair(repo_root, src_rel, dst_rel)
    if errors:
        return errors, True
    if not src_dir.is_dir():
        return [f"[WARNING] Source directory missing: {src_rel}"], False

    changes: list[str] = []
    had_errors = False

    try:
        src_files = {f.name for f in src_dir.iterdir() if f.suffix == ".py"}
    except OSError as exc:
        return [f"[ERROR] Cannot list source directory {src_rel}: {exc}"], True

    for name in sorted(src_files):
        src_path = src_dir / name
        dst_path = dst_dir / name
        try:
            expected = _transform_file(src_path)
        except (OSError, UnicodeDecodeError) as exc:
            changes.append(f"  [ERROR] Cannot read {src_rel}/{name}: {exc}")
            had_errors = True
            continue

        current = None
        if dst_path.is_file() or dst_path.is_symlink():
            try:
                current = read_bytes_no_redirect(dst_path)
            except OSError as exc:
                changes.append(f"  [ERROR] Cannot read {dst_rel}/{name}: {exc}")
                had_errors = True
                continue
        if current == expected:
            continue

        changes.append(f"  {'updated' if current is not None else 'created'}: {dst_rel}/{name}")
        if not check_only:
            try:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                publish_bytes_atomically(dst_path, expected)
            except OSError as exc:
                changes.append(f"  [ERROR] Cannot write {dst_rel}/{name}: {exc}")
                had_errors = True

    stale_changes, stale_errors = _remove_stale_files(
        dst_dir, dst_rel, src_files, check_only=check_only
    )
    changes.extend(stale_changes)
    had_errors = had_errors or stale_errors
    return changes, had_errors


def _remove_stale_files(
    dst_dir: Path,
    dst_rel: str,
    src_files: set[str],
    *,
    check_only: bool,
) -> tuple[list[str], bool]:
    """Remove destination `.py` files not present in the source. Never touches non-`.py` files."""
    if not dst_dir.is_dir():
        return [], False
    changes: list[str] = []
    had_errors = False
    try:
        dst_entries = sorted(dst_dir.iterdir())
    except OSError as exc:
        return [f"[ERROR] Cannot list destination directory {dst_rel}: {exc}"], True

    for dst_file in dst_entries:
        if dst_file.suffix != ".py" or dst_file.name in LIB_ONLY_FILES:
            continue
        if dst_file.name not in src_files:
            changes.append(f"  removed: {dst_rel}/{dst_file.name}")
            if not check_only:
                try:
                    dst_file.unlink()
                except OSError as exc:
                    changes.append(f"  [ERROR] Cannot remove {dst_rel}/{dst_file.name}: {exc}")
                    had_errors = True
    return changes, had_errors


# ---------------------------------------------------------------------------
# Single-file sync (SYNC_FILE_PAIRS), moved from scripts/sync_plugin_lib.py
# ---------------------------------------------------------------------------


def _imports_scripts_package(tree: ast.Module) -> bool:
    """Return True if the module imports the top-level ``scripts`` package.

    See `scripts/sync_plugin_lib.py`'s original docstring (moved verbatim):
    covers bare/dotted/aliased/comma-list/backslash-continued imports and
    literal-string dynamic imports (`__import__`, `importlib.import_module`).
    A dynamic import computed at runtime cannot be detected statically;
    registered sources are small, self-contained modules where that does
    not occur.
    """

    def _is_scripts(name: str | None) -> bool:
        return name is not None and (name == "scripts" or name.startswith("scripts."))

    def _dynamic_import_target(node: ast.Call) -> str | None:
        target = node.func
        is_dynamic = (
            isinstance(target, ast.Name) and target.id in {"__import__", "import_module"}
        ) or (isinstance(target, ast.Attribute) and target.attr in {"import_module", "__import__"})
        if not is_dynamic:
            return None
        if node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value
        for keyword in node.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                value = keyword.value.value
                if isinstance(value, str):
                    return value
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0 and _is_scripts(node.module):
                return True
        elif isinstance(node, ast.Import):
            if any(_is_scripts(alias.name) for alias in node.names):
                return True
        elif isinstance(node, ast.Call):
            if _is_scripts(_dynamic_import_target(node)):
                return True
    return False


def sync_file(
    repo_root: Path,
    src_rel: str,
    dst_rel: str,
    *,
    check_only: bool,
) -> tuple[list[str], bool]:
    """Byte-copy a single source module to a top-level lib destination.

    No import rewriting: the destination is not a package, so
    package-relative imports would not resolve. The source must be
    import-self-contained; a `scripts` package import is rejected because a
    byte copy cannot rewrite it. Comparison and copy both operate on raw
    bytes so CRLF/LF differences are treated as drift, not normalized away.
    """
    src_path, dst_path, errors = _resolve_pair(repo_root, src_rel, dst_rel)
    if errors:
        return errors, True
    if not src_path.is_file():
        return [f"[ERROR] Registered source file missing: {src_rel}"], True

    try:
        expected_bytes = read_bytes_no_redirect(src_path)
    except OSError as exc:
        return [f"[ERROR] Cannot read {src_rel}: {exc}"], True

    try:
        source_text = expected_bytes.decode("utf-8")
        tree = ast.parse(source_text, filename=src_rel)
    except UnicodeDecodeError as exc:
        return [f"[ERROR] Cannot decode {src_rel} as utf-8: {exc}"], True
    except SyntaxError as exc:
        return [f"[ERROR] Cannot parse {src_rel}: {exc}"], True

    if _imports_scripts_package(tree):
        return [
            f"[ERROR] {src_rel} imports the scripts package and cannot be "
            "byte-copied to a top-level lib file. Make it self-contained or "
            "register it as a package via PACKAGES.",
        ], True

    current_bytes = None
    if dst_path.is_file() or dst_path.is_symlink():
        try:
            current_bytes = read_bytes_no_redirect(dst_path)
        except OSError as exc:
            return [f"[ERROR] Cannot read {dst_rel}: {exc}"], True
    if current_bytes == expected_bytes:
        return [], False

    changes = [f"  {'updated' if current_bytes is not None else 'created'}: {dst_rel}"]
    if not check_only:
        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            publish_bytes_atomically(dst_path, expected_bytes)
        except OSError as exc:
            return [f"  [ERROR] Cannot write {dst_rel}: {exc}"], True
    return changes, False


# ---------------------------------------------------------------------------
# Orchestrator: every package and file pair, into every plugin root
# ---------------------------------------------------------------------------


def compile_all(repo_root: Path, *, check: bool = False) -> LibMirrorResult:
    """Render every package and file pair into both lib plugin trees.

    `install_tree` (the `.claude/lib/...` and
    `.claude/skills/review/scripts/validate_review_marker.py` copies) is
    never written here: `binplace_manifest.binplace()` propagates each
    `src/claude/lib/...` plugin-tree file onto its install-tree counterpart
    in the same `build_all.py` run, per the `lib-*` and `skills-sidecar`
    manifest rows.
    """
    result = LibMirrorResult()

    for package in PACKAGES:
        src_rel = f"scripts/{package}"
        for plugin_root in PLUGIN_ROOTS:
            dst_rel = f"{plugin_root}/{package}"
            changes, had_errors = sync_pair(repo_root, src_rel, dst_rel, check_only=check)
            _fold(result, src_rel, dst_rel, changes, had_errors)

    for src_rel, file_name in SYNC_FILE_NAMES:
        for plugin_root in PLUGIN_ROOTS:
            dst_rel = f"{plugin_root}/{file_name}"
            changes, had_errors = sync_file(repo_root, src_rel, dst_rel, check_only=check)
            _fold(result, src_rel, dst_rel, changes, had_errors)

    changes, had_errors = sync_file(
        repo_root, SKILLS_SIDECAR_SOURCE, SKILLS_SIDECAR_PLUGIN_TREE, check_only=check
    )
    _fold(result, SKILLS_SIDECAR_SOURCE, SKILLS_SIDECAR_PLUGIN_TREE, changes, had_errors)

    result.inputs = len(PACKAGES) * len(PLUGIN_ROOTS) + len(SYNC_FILE_NAMES) * len(PLUGIN_ROOTS) + 1
    result.outputs = len([c for c in result.changes if not c.strip().startswith("[")])
    return result


def _fold(
    result: LibMirrorResult,
    src_rel: str,
    dst_rel: str,
    changes: list[str],
    had_errors: bool,
) -> None:
    """Fold one sync's changes into the accumulating :class:`LibMirrorResult`."""
    if had_errors:
        result.errors.extend(c for c in changes if c.strip())
    if changes:
        result.changes.append(f"{src_rel} -> {dst_rel}:")
        result.changes.extend(changes)
