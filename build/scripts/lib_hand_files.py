"""Hand-maintained ``src/claude/lib`` modules that other lib trees byte-copy (issue #7221).

``paths.py`` has no ``scripts/`` source. Skill scripts in every harness tree
import it (``from paths import artifact_dir``), so each tree that ships those
scripts must ship the module too. ``lib_mirror.compile_all`` copies the Claude
file into the Codex, Cursor and Muse lib trees. Those skill scripts are byte
copies of the Claude ones and write under ``.project-toolkit/``, so the Claude
content is the right one.

``ptk_run.py`` is the ADR-121 resolver that the shell locator of a shipped
command runs. It reads no repo state, so every tree gets the same bytes.

Copilot is not a copy target. Its ``paths.py`` hand copy differs on purpose: the
consumer side root is ``.agents`` (``surface-parity.yaml``, ``lib-copilot-modules``).
Its ``ptk_run.py`` is a byte-identical hand copy that the same row pins.
The Hermes packs get the Claude copy from ``lib_render.render_lib_files``,
which reads :data:`PLUGIN_LIB_FILES` from here.
"""

from __future__ import annotations

PLUGIN_LIB_SOURCE_DIR = "src/claude/lib"
PLUGIN_LIB_FILES: tuple[str, ...] = ("paths.py", "ptk_run.py")
PLUGIN_LIB_COPY_ROOTS: tuple[str, ...] = (
    "src/codex/lib",
    "src/cursor/lib",
    "src/muse/lib",
)

# (source file, destination file) for every byte copy, relative to the repo root.
PLUGIN_LIB_COPIES: tuple[tuple[str, str], ...] = tuple(
    (f"{PLUGIN_LIB_SOURCE_DIR}/{name}", f"{root}/{name}")
    for name in PLUGIN_LIB_FILES
    for root in PLUGIN_LIB_COPY_ROOTS
)
