"""Helper to import skill scripts that lack __init__.py packages.

Usage:
    from claude_skills_import import import_skill_script
    mod = import_skill_script(".claude/skills/some-skill/scripts/script.py")
    func = mod.some_function
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def import_skill_script(relative_path: str, module_name: str | None = None) -> object:
    """Import a Python script by relative path from project root.

    Returns the module object.
    """
    full_path = PROJECT_ROOT / relative_path
    if not full_path.exists():
        raise FileNotFoundError(f"Script not found: {full_path}")

    if module_name is None:
        module_name = full_path.stem

    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {full_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
