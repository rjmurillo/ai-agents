"""Tests for explicit ``sys.path`` insertion in import_closure.py (issue #7221).

Shipped skill scripts bootstrap shared modules with one uniform idiom::

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from skill_bootstrap import ensure_plugin_paths

The insert runs before the import, so the module in the inserted directory
resolves at runtime. The closure gate models that exact idiom. Anything else
(a variable, a literal, ``os.getcwd()``, the wrong ``dirname`` depth, or an
insert that runs after the import) stays unresolved, so genuinely missing
modules still fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import import_closure  # noqa: E402

SCRIPT = "src/codex/skills/demo/scripts/issue/tool.py"
BOOTSTRAP = "src/codex/skills/demo/scripts/skill_bootstrap.py"
SCRIPT_DIR = "os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"


def _put(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _modules(root: Path) -> list[str]:
    return [f.detail.split("'")[1] for f in import_closure.check_import_closure(root)]


def _script(root: Path, body: str, rel: str = SCRIPT) -> Path:
    return _put(root, rel, body)


def _bootstrap(root: Path) -> None:
    _put(root, BOOTSTRAP, "def ensure_plugin_paths():\n    pass\n")


def _import_after_path_call(root: Path, call: str) -> None:
    _bootstrap(root)
    _script(
        root,
        f"import os\nimport sys\nsys.path.{call}\n"
        "from skill_bootstrap import ensure_plugin_paths\n",
    )


# --- positive: the modeled idiom ---------------------------------------------


@pytest.mark.parametrize("call", [f"insert(0, {SCRIPT_DIR})", f"append({SCRIPT_DIR})"])
def test_dirname_chain_resolves_module_in_the_inserted_directory(tmp_path: Path, call: str) -> None:
    _import_after_path_call(tmp_path, call)

    assert import_closure.check_import_closure(tmp_path) == []


def test_deeper_chain_resolves_from_a_deeper_script(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    _script(
        tmp_path,
        "import os\nimport sys\n"
        "sys.path.insert(\n"
        "    0,\n"
        "    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),\n"
        ")\n"
        "from skill_bootstrap import ensure_plugin_paths\n",
        "src/codex/skills/demo/scripts/issue/sub/tool.py",
    )

    assert import_closure.check_import_closure(tmp_path) == []


def test_call_time_import_inside_a_function_is_covered(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    _script(
        tmp_path,
        "import os\nimport sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "def run():\n"
        "    from skill_bootstrap import ensure_plugin_paths\n"
        "    return ensure_plugin_paths\n",
    )

    assert import_closure.check_import_closure(tmp_path) == []


# --- negative: shapes that must stay unresolved -------------------------------


@pytest.mark.parametrize(
    "call",
    [
        f"insert(0, os.path.dirname({SCRIPT_DIR}))",
        'insert(0, "/opt/shared")',
        "insert(0, os.getcwd())",
        "insert(0, os.path.abspath(__file__))",
        f"insert({SCRIPT_DIR})",
        f"insert('zero', {SCRIPT_DIR})",
        f"insert(0, {SCRIPT_DIR}, extra=True)",
        f"append(0, {SCRIPT_DIR})",
        "append(os.path.dirname(os.path.dirname(os.path.abspath(__file__, extra=True))))",
    ],
)
def test_unsupported_path_mutation_stays_unresolved(tmp_path: Path, call: str) -> None:
    _import_after_path_call(tmp_path, call)

    assert _modules(tmp_path) == ["skill_bootstrap"]


def test_cannot_import_from_another_harness_tree(tmp_path: Path) -> None:
    _put(tmp_path, "src/skill_bootstrap.py")
    directory = "os.path.dirname(" * 6 + "os.path.abspath(__file__)" + ")" * 6
    _script(
        tmp_path,
        f"import os\nimport sys\nsys.path.insert(0, {directory})\nimport skill_bootstrap\n",
    )

    assert _modules(tmp_path) == ["skill_bootstrap"]


def test_insert_after_the_import_still_fails(tmp_path: Path) -> None:
    """The runtime import would crash before the insert runs, so the gate flags it."""
    _bootstrap(tmp_path)
    _script(
        tmp_path,
        "import os\nimport sys\n"
        "from skill_bootstrap import ensure_plugin_paths\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n",
    )

    assert _modules(tmp_path) == ["skill_bootstrap"]


def test_insert_inside_a_function_is_not_modeled(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    _script(
        tmp_path,
        "import os\nimport sys\n"
        "def setup():\n"
        "    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "setup()\n"
        "from skill_bootstrap import ensure_plugin_paths\n",
    )

    assert _modules(tmp_path) == ["skill_bootstrap"]


# --- edge: the model stays per-file ------------------------------------------


def test_one_files_insert_does_not_cover_another_file(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    _script(
        tmp_path,
        "import os\nimport sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "from skill_bootstrap import ensure_plugin_paths\n",
    )
    _script(
        tmp_path,
        "from skill_bootstrap import ensure_plugin_paths\n",
        "src/codex/skills/demo/scripts/issue/other.py",
    )

    findings = import_closure.check_import_closure(tmp_path)

    assert [f.path for f in findings] == ["src/codex/skills/demo/scripts/issue/other.py:1"]


def test_insert_covers_only_modules_actually_in_the_inserted_directory(tmp_path: Path) -> None:
    _bootstrap(tmp_path)
    _script(
        tmp_path,
        "import os\nimport sys\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "from skill_bootstrap import ensure_plugin_paths\n"
        "import ghost_module\n",
    )

    assert _modules(tmp_path) == ["ghost_module"]
