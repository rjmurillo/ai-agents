"""Import scripts/eval modules for the third-party gap tests without leaking state.

The eval scripts import their siblings by bare name, so they need
``scripts/eval`` on ``sys.path`` while they load. These helpers put it there
only for the import and restore ``sys.path`` and the loaded script's
``sys.modules`` entry afterwards, so no later test inherits either.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import cast

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"


@contextmanager
def eval_path() -> Iterator[None]:
    """Put ``scripts/eval`` on ``sys.path`` for the imports inside the block only."""
    saved_path = list(sys.path)
    sys.path.insert(0, str(EVAL_DIR))
    try:
        yield
    finally:
        sys.path[:] = saved_path


def load_script(stem: str) -> ModuleType:
    """Run ``scripts/eval/<stem>.py`` as a fresh module and restore the import state.

    The script's own ``sys.path`` inserts are undone, and a prior
    ``sys.modules[stem]`` binding comes back, so each call is independent.
    """
    spec = importlib.util.spec_from_file_location(stem, EVAL_DIR / f"{stem}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    saved_path = list(sys.path)
    # An entry bound to None blocks an import, so "absent" is tracked apart from it.
    had_entry = stem in sys.modules
    saved_module = sys.modules.get(stem)
    sys.modules[stem] = module
    sys.path.insert(0, str(EVAL_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved_path
        if not had_entry:
            sys.modules.pop(stem, None)
        else:
            sys.modules[stem] = cast(ModuleType, saved_module)
    return module
