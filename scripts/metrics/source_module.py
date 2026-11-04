"""Load a Python file as a module from its source text only."""

from __future__ import annotations

import sys
from importlib import util
from pathlib import Path
from types import ModuleType


def load_source_module(name: str, path: Path) -> ModuleType:
    """Exec ``path`` as module ``name`` from source, never from a cached ``.pyc``.

    The default file loader trusts a ``.pyc`` whose recorded size and mtime
    match the source, so a stale one can win. This reads and compiles the text
    instead, and writes no bytecode for the file or for anything it imports.
    """
    spec = util.spec_from_file_location(name, path)
    if spec is None:
        raise ImportError(f"cannot load {path}")
    module = util.module_from_spec(spec)
    code = compile(path.read_text(encoding="utf-8"), str(path), "exec")
    sys.modules.setdefault(name, module)
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        exec(code, module.__dict__)
    finally:
        sys.dont_write_bytecode = saved
    return module
