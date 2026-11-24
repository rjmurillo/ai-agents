"""Tripwire for the ADR-122 item 10 coupling admissions (issue #7530).

The code-qualities scanner admits one coupling drop for each of two memory
files because each imports the shared store module. If a later change removes
or replaces that import, the admission records must be removed in the same
pull request: the scanner, the review adapter, and `.qualityrc.json`.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
STORE_IMPORTS = {
    "src/claude/skills/memory/memory_core/memory_router.py": (1, "memory_store"),
    "src/claude/skills/memory/scripts/search_memory.py": (0, "memory_core.memory_store"),
}
CONFIG_KEYS = ("memoryRouterStoreModuleAdmission", "searchMemoryStoreModuleAdmission")


def _imports_store(path: Path, level: int, module: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.ImportFrom) and node.level == level and node.module == module
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize(("relative", "expected"), STORE_IMPORTS.items())
def test_admitted_file_still_imports_the_store_module(
    relative: str, expected: tuple[int, str]
) -> None:
    level, module = expected
    config = json.loads((REPO / ".qualityrc.json").read_text(encoding="utf-8"))
    if not any(key in config for key in CONFIG_KEYS):
        # The admission records have not landed on this base, so nothing can go stale.
        return

    assert _imports_store(REPO / relative, level, module), (
        f"{relative} no longer imports {module}. Remove the ADR-122 item 10 records "
        "from assess.py, scripts/ai_review_common/verdict.py, and .qualityrc.json."
    )
