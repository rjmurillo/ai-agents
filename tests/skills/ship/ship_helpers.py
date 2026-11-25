"""Call helpers shared by the ship script tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "ship" / "scripts"


_ORDER = ("_ship_common", "ship_detect", "ship_preflight", "ship_pr")


def load_scripts():
    """Load the ship scripts from the source tree; return (common, detect, preflight, pr).

    A script not yet in the tree loads as None, so each slice's tests run alone.
    """
    loaded = []
    for name in _ORDER:
        path = SCRIPTS / f"{name}.py"
        if name not in sys.modules and path.is_file():
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        loaded.append(sys.modules.get(name))
    return tuple(loaded)


def invoke(module, argv: list[str], capsys) -> tuple[int, list[str]]:
    """Run ``module.main`` in human format; return the exit code and stdout lines."""
    code = module.main(
        [*argv, "--output-format", "human"] if "--output-format" not in argv else argv
    )
    lines = capsys.readouterr().out.splitlines()
    return code, lines


def values(lines: list[str], key: str) -> list[str]:
    prefix = f"{key}: "
    return [line[len(prefix) :] for line in lines if line.startswith(prefix)]
