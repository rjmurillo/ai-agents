"""Render the shared lib packages in memory (ADR-115 Hermes packs).

``lib_mirror.compile_all`` writes ``scripts/{hook_utilities,github_core,
ai_review_common}/`` and ``bootstrap.py`` into two fixed plugin trees. A Hermes
pack owns its whole directory, so ``hermes_packs.py`` needs the expected bytes up
front, to count files and sizes and to compare against disk, instead of letting
``sync_pair`` write them piecemeal. This module reads the same registrations
(``PACKAGES``, ``SYNC_FILE_NAMES``) and applies the same import rewrite
(``_transform_file``), so the two cannot name different files.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from atomic_write import read_bytes_no_redirect  # noqa: E402
from lib_mirror import PACKAGES, SYNC_FILE_NAMES, _transform_file  # noqa: E402

# Hand-maintained modules with no scripts/ source that live in the Claude
# plugin's lib/ (ADR-119: skill scripts import paths.py from there). Byte copies.
PLUGIN_LIB_FILES: tuple[str, ...] = ("paths.py",)


class LibRenderError(Exception):
    """A registered lib source is missing or unreadable."""


def render_lib_files(repo_root: Path) -> dict[str, bytes]:
    """Return every lib file as ``{path under a lib root: bytes}``, without writing.

    Each ``.py`` file of a :data:`PACKAGES` source goes through the import
    rewrite, and each :data:`SYNC_FILE_NAMES` and :data:`PLUGIN_LIB_FILES`
    source is a byte copy.
    ``tests/build_scripts/test_hermes_packs.py`` pins this result byte for byte
    to the committed ``src/claude/lib/`` tree that ``lib_mirror.compile_all``
    writes.

    Raises :class:`LibRenderError` instead of returning a partial tree.
    """
    files: dict[str, bytes] = {}
    for package in PACKAGES:
        src_dir = repo_root / "scripts" / package
        if not src_dir.is_dir():
            raise LibRenderError(f"Registered source directory missing: scripts/{package}")
        for src_path in sorted(p for p in src_dir.iterdir() if p.suffix == ".py"):
            try:
                files[f"{package}/{src_path.name}"] = _transform_file(src_path)
            except (OSError, UnicodeDecodeError) as exc:
                raise LibRenderError(
                    f"Cannot read scripts/{package}/{src_path.name}: {exc}"
                ) from exc
    for src_rel, file_name in SYNC_FILE_NAMES:
        src_path = repo_root / src_rel
        if not src_path.is_file():
            raise LibRenderError(f"Registered source file missing: {src_rel}")
        try:
            files[file_name] = read_bytes_no_redirect(src_path)
        except OSError as exc:
            raise LibRenderError(f"Cannot read {src_rel}: {exc}") from exc
    for file_name in PLUGIN_LIB_FILES:
        src_path = repo_root / "src" / "claude" / "lib" / file_name
        if not src_path.is_file():
            raise LibRenderError(f"Registered plugin lib file missing: src/claude/lib/{file_name}")
        try:
            files[file_name] = read_bytes_no_redirect(src_path)
        except OSError as exc:
            raise LibRenderError(f"Cannot read src/claude/lib/{file_name}: {exc}") from exc
    return files
