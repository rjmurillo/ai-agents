"""Shared plumbing for gates that scan a rendered agent tree.

``check_agent_delegation.py``, ``check_agent_success_criterion.py``, and
``check_orchestrator_vocabulary.py`` all list an agent tree and expose the
same ADR-035 CLI. This module holds that code once.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def agent_markdown_files(repo_root: Path, tree: Path) -> list[Path]:
    """Return the sorted ``*.md`` files directly under ``repo_root / tree``.

    Raises ``FileNotFoundError`` when the tree is absent or empty: a silently
    empty scan is a passing scan that proves nothing.
    """
    folder = repo_root / tree
    if not folder.is_dir():
        raise FileNotFoundError(f"agent tree not found: {folder}")
    files = sorted(folder.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"agent tree yields no Markdown files: {folder}")
    return files


def run_repo_gate(
    argv: Sequence[str] | None,
    validate: Callable[[Path], bool],
    required_tree: Path | None = None,
) -> int:
    """Run ``validate`` on the root named by ``argv[0]`` or this repository.

    Returns an ADR-035 exit code: 0 when ``validate`` passes, 1 when it fails,
    and 2 when the root is invalid or ``required_tree`` is missing under it.
    """
    args = list(argv) if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else _REPO_ROOT
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if required_tree is not None and not (repo_root / required_tree).is_dir():
        print(f"[FAIL] Missing agent tree: {repo_root / required_tree}", file=sys.stderr)
        return 2
    return 0 if validate(repo_root) else 1
