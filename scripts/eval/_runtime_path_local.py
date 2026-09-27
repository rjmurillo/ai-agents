"""Path-local fixture install and cwd resolution for parity evals (SPEC-4880 T7).

Split out of `_runtime_harness.py`: the `path_local`/`cwd` support added
there for issue #4880 dropped that module's CQA cohesion score from 4.5 to
2.9 (16 definitions in 315 LOC), because it added two self-contained helpers
that share no state with the harness-install code around them. Those two
helpers move here instead. The dependency runs one way, `_runtime_harness`
onto this module (its `_prepare_claude_workspace`/`_prepare_copilot_workspace`
call `install_path_local`), never the reverse, so there is no import cycle.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from _runtime_parity import safe_workspace_file


def install_path_local(workspace: Path, path_local: Mapping[str, bytes]) -> None:
    """Write `path_local` fixture bytes at their own repository-relative path.

    Unlike `_install_instructions` (Claude-only, renamed to its basename
    under `.claude/rules/`), a `path_local` file installs at the SAME
    relative path for both harnesses (SPEC-4880 T7): Claude Code loads
    `CLAUDE.md` from cwd and its ancestors, and Copilot CLI loads
    `AGENTS.md`/`CLAUDE.md` from cwd up to the git root, so a fixture proving
    that loading behavior needs the file at its real repository path in both
    workspaces, not projected or renamed.
    """
    for relative, content in path_local.items():
        path = safe_workspace_file(workspace, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def resolve_cwd(workspace: Path, cwd: str) -> Path:
    """Resolve a fixture's `cwd` to an absolute path inside `workspace`.

    Both CLIs launch with this directory as the process working directory
    (SPEC-4880 T7): Claude Code loads `CLAUDE.md` from cwd and its ancestors,
    and Copilot CLI loads `AGENTS.md`/`CLAUDE.md` from cwd up to the git
    root, so a realistic `.github/` task needs a matching cwd, not the
    workspace root every fixture used before this field existed.
    """
    return Path(safe_workspace_file(workspace, cwd))
