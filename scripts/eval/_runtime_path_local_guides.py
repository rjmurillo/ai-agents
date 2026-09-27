"""Discoverable-guide check for `path_local` fixture entries (issue #4880).

Split out of `_runtime_parity.py` (bot review: the security restriction
added there pushed that module to 522 lines, over the taste-lints 500-line
ERROR threshold). Holds the one fact both the fixture loader and the
Copilot listing preflight need to agree on: which `path_local` shapes a
harness actually discovers by walking to them.

`install_path_local` (`_runtime_path_local.py`) writes a `path_local` entry
at its own repository-relative path inside the fixture workspace,
unprojected. A fixture-declared entry naming an agent install path (for
example `.claude/agents/parity.md`) would overwrite the agent definition
under test after install, silently changing which agent the eval actually
runs. Both harnesses' path-local loading model discovers only three shapes:
a nested `AGENTS.md` or `CLAUDE.md` (either CLI, walking cwd's ancestors -
see `effective_context_sources.py`'s "nested" layer and
`eval_runtime_parity.py`'s own `_ancestor_dirs`/`_setup_discoverable_sources`)
or the one repository-root `.github/copilot-instructions.md` (Copilot only).

No dependency on `_runtime_parity` here (avoids a circular import: that
module imports `is_discoverable_guide` from this one, so this module raises
nothing itself and returns a plain `bool`, leaving the caller to raise its
own `ParityConfigError` with whatever field name it has in scope).
"""

from __future__ import annotations

from pathlib import Path

# The three shapes either harness's path-local loading model discovers.
ALLOWED_BASENAMES = frozenset({"AGENTS.md", "CLAUDE.md"})
COPILOT_REPO_INSTRUCTIONS_PATH = ".github/copilot-instructions.md"


# `_runtime_harness.prepare_workspace` writes each CLI profile here.
ISOLATED_PROFILE_DIR = ".parity-profile"


def is_discoverable_guide(item: str) -> bool:
    """True when `item` is a file either CLI's path-local loading discovers.

    A basename of `AGENTS.md` or `CLAUDE.md` (any directory), or exactly
    the one repository-root `.github/copilot-instructions.md`. Anything
    else is not a "path-local guide" fixture, for example an agent install
    path (`.claude/agents/parity.md`) or an arbitrary repository file
    (`README.md`), or a guide under the isolated CLI profile, which would
    overwrite its sentinel file.
    """
    parts = Path(item).parts
    if parts and parts[0] == ISOLATED_PROFILE_DIR:
        return False
    return item == COPILOT_REPO_INSTRUCTIONS_PATH or Path(item).name in ALLOWED_BASENAMES
