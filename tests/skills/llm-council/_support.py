"""Load llm-council scripts without leaving a trace on ``sys.path``.

The scripts import their siblings by bare name (``from council_core import ...``),
so their directory must be importable while a script loads. ``load_script`` puts it
there, runs the import, then restores ``sys.path`` exactly. Pytest runs with
``--import-mode=importlib``, so test files load this module by file path:

    spec = importlib.util.spec_from_file_location("llm_council_support", path)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = REPO_ROOT / ".claude" / "skills" / "llm-council" / "scripts"


def load_module(path: Path, module_name: str, extra_path: Path | None = None) -> ModuleType:
    """Import ``path`` as ``module_name``; ``sys.path`` is identical before and after."""
    saved = list(sys.path)
    if extra_path is not None:
        sys.path.insert(0, str(extra_path))
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create spec for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved
    return module


def load_script(filename: str, module_name: str) -> ModuleType:
    """Import ``scripts/<filename>`` with its sibling modules importable during the load."""
    return load_module(SCRIPTS_DIR / filename, module_name, extra_path=SCRIPTS_DIR)
