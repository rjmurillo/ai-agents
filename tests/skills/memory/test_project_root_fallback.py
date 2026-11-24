"""Memory maintenance scripts must not treat their own install tree as the project.

When git cannot name a project root, three scripts walked up from their own
file location. From an installed plugin copy that walk found the plugin's
checkout and rewrote its memories instead of failing.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "memory" / "scripts"
sys.path.insert(0, str(SCRIPTS))

MODULES = [
    "improve_memory_graph_density",
    "convert_index_table_links",
    "convert_memory_references",
]


def _git_fails(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=128, stdout="", stderr="")


@pytest.mark.parametrize("module_name", MODULES)
def test_no_git_and_no_checkout_fails_instead_of_using_the_script_tree(
    module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(module_name)
    monkeypatch.setattr(module.subprocess, "run", _git_fails)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        module._find_project_root()


@pytest.mark.parametrize("module_name", MODULES)
def test_no_git_walks_up_from_the_current_directory(
    module_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(module_name)
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.setattr(module.subprocess, "run", _git_fails)
    monkeypatch.chdir(nested)

    assert module._find_project_root() == tmp_path.resolve()
