"""Scans that cover what grimp, and so import-linter, cannot see.

grimp walks only directories that hold an ``__init__.py``. On 2026-11-05 at
this branch, seven ``scripts/`` directories have none (``eval``, ``ci``,
``testing``, ``memory``, ``security``, ``workflows``, ``dev``), which leaves 284
of 719 Python files out of the graph. The ``production-does-not-import-tests``
contract therefore cannot see an import of ``tests`` there. An AST scan of every
file closes that gap.

The yaml tests close a second gap: an ``ignore_imports`` entry removes one edge,
but every module that imports the ignored module still fails without PyYAML.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import tomllib

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _path in (_REPO_ROOT / "build" / "scripts", _REPO_ROOT / "scripts" / "validation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import checks_ci_parity  # noqa: E402
import lib_mirror  # noqa: E402

_PRODUCTION_ROOTS = ("scripts", "memory_enhancement")

# Modules that fail to import under bare python3 without PyYAML. Two import it at
# the top level (the ignored edges in pyproject.toml). The other four import one of
# those two. bot_config also imports yaml, but behind `except ImportError`.
_FAIL_WITHOUT_YAML = {
    "scripts.github_core.workflow_event_subscriptions",
    "scripts.github_core.workflow_provenance",
    "scripts.github_core.recovery_manifest",
    "scripts.github_core.workflow_runs",
    "scripts.github_core.runs_file",
    "scripts.github_core.pull_request_targets",
}
_GUARDED_YAML_IMPORTERS = {"scripts.github_core.bot_config"}


def tests_imports(source: str) -> list[str]:
    """Return each absolute import of the ``tests`` package in ``source``."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name.split(".")[0] == "tests"]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] == "tests":
                found.append(node.module)
    return found


def scan_for_tests_imports(root: Path, packages: tuple[str, ...]) -> list[str]:
    """List ``path: import`` for each import of ``tests`` under ``packages``.

    A file that does not parse is listed too: an unreadable file is not proof of
    a clean one.
    """
    offenders: list[str] = []
    for package in packages:
        for path in sorted((root / package).rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            try:
                imports = tests_imports(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError) as error:
                offenders.append(f"{relative}: unparseable ({type(error).__name__})")
                continue
            offenders += [f"{relative}: {name}" for name in imports]
    return offenders


def directories_missing_init(package_root: Path) -> list[str]:
    """List directories under ``package_root`` that hold a .py file but no __init__.py."""
    missing: list[str] = []
    for directory in sorted({path.parent for path in package_root.rglob("*.py")}):
        if "__pycache__" in directory.parts:
            continue
        if not (directory / "__init__.py").is_file():
            missing.append(directory.relative_to(package_root.parent).as_posix())
    return missing


def _write(path: Path, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_production_code_imports_nothing_from_tests() -> None:
    assert scan_for_tests_imports(_REPO_ROOT, _PRODUCTION_ROOTS) == []


def test_scan_finds_an_import_in_a_directory_with_no_init(tmp_path: Path) -> None:
    _write(tmp_path / "scripts" / "__init__.py")
    _write(tmp_path / "scripts" / "ci" / "foo.py", "import tests.helper\n")
    assert scan_for_tests_imports(tmp_path, ("scripts",)) == ["scripts/ci/foo.py: tests.helper"]


@pytest.mark.parametrize(
    "body",
    [
        "import tests\n",
        "import os, tests.helper\n",
        "from tests import helper\n",
        "from tests.sub.mod import thing\n",
        "def f():\n    import tests.helper\n",
        "try:\n    import tests.helper\nexcept ImportError:\n    pass\n",
    ],
)
def test_scan_flags_each_form_of_a_tests_import(tmp_path: Path, body: str) -> None:
    _write(tmp_path / "scripts" / "mod.py", body)
    assert len(scan_for_tests_imports(tmp_path, ("scripts",))) == 1


@pytest.mark.parametrize(
    "body",
    [
        "import tests_helper\n",
        "import scripts.tests_util\n",
        "from scripts import tests\n",
        "from . import tests\n",
        "from .tests import helper\n",
        '"""Uses `import tests.helper` as an example."""\n',
        "# import tests.helper\n",
        "name = 'from tests import x'\n",
        "",
    ],
)
def test_scan_ignores_text_and_lookalikes(tmp_path: Path, body: str) -> None:
    _write(tmp_path / "scripts" / "mod.py", body)
    assert scan_for_tests_imports(tmp_path, ("scripts",)) == []


def test_scan_reports_an_unparseable_file(tmp_path: Path) -> None:
    _write(tmp_path / "scripts" / "broken.py", "def (:\n")
    assert scan_for_tests_imports(tmp_path, ("scripts",)) == [
        "scripts/broken.py: unparseable (SyntaxError)"
    ]


def test_scan_reads_every_production_root(tmp_path: Path) -> None:
    _write(tmp_path / "memory_enhancement" / "m.py", "import tests.x\n")
    _write(tmp_path / "scripts" / "s.py", "from tests import y\n")
    assert scan_for_tests_imports(tmp_path, _PRODUCTION_ROOTS) == [
        "scripts/s.py: tests",
        "memory_enhancement/m.py: tests.x",
    ]


def test_scan_of_a_missing_root_finds_nothing(tmp_path: Path) -> None:
    assert scan_for_tests_imports(tmp_path, _PRODUCTION_ROOTS) == []


def test_import_linter_is_blind_to_a_directory_with_no_init(tmp_path: Path) -> None:
    """Pins why the scan exists. If this fails, import-linter sees the file: drop the scan."""
    _write(tmp_path / "scripts" / "__init__.py")
    _write(tmp_path / "scripts" / "ci" / "foo.py", "import tests.helper\n")
    _write(tmp_path / "tests" / "__init__.py")
    _write(tmp_path / "tests" / "helper.py")
    _write(
        tmp_path / "pyproject.toml",
        textwrap.dedent(
            """
            [tool.importlinter]
            root_packages = ["scripts", "tests"]

            [[tool.importlinter.contracts]]
            id = "no-tests"
            name = "no tests"
            type = "forbidden"
            source_modules = ["scripts"]
            forbidden_modules = ["tests"]
            """
        ),
    )
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", checks_ci_parity._LINT_IMPORTS_PROGRAM, "--no-cache"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert scan_for_tests_imports(tmp_path, ("scripts",)) == ["scripts/ci/foo.py: tests.helper"]


@pytest.mark.parametrize("package", lib_mirror.PACKAGES)
def test_shipped_package_has_no_directory_missing_init(package: str) -> None:
    assert directories_missing_init(_REPO_ROOT / "scripts" / package) == []


def test_shipped_package_list_is_not_empty() -> None:
    assert len(lib_mirror.PACKAGES) > 0


def test_missing_init_detector_names_a_gap(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py")
    _write(tmp_path / "pkg" / "ok" / "__init__.py")
    _write(tmp_path / "pkg" / "ok" / "a.py")
    _write(tmp_path / "pkg" / "gap" / "b.py")
    _write(tmp_path / "pkg" / "data" / "note.txt")
    assert directories_missing_init(tmp_path / "pkg") == ["pkg/gap"]


def test_missing_init_detector_accepts_a_complete_package(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "__init__.py")
    assert directories_missing_init(tmp_path / "pkg") == []


def _ignored_importers() -> set[str]:
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    table = tomllib.loads(pyproject)["tool"]["importlinter"]
    return {
        entry.split("->")[0].strip()
        for contract in table["contracts"]
        for entry in contract.get("ignore_imports", [])
    }


def test_modules_that_reach_an_ignored_yaml_import_are_the_known_set() -> None:
    """A new importer of an unguarded yaml module must be reviewed, not slip past the ignore."""
    import grimp

    graph = grimp.build_graph("scripts", include_external_packages=True, cache_dir=None)
    unguarded = _ignored_importers() - _GUARDED_YAML_IMPORTERS
    shipped = {f"scripts.{package}" for package in lib_mirror.PACKAGES}
    reaching = set(unguarded)
    for importer in unguarded:
        reaching |= {
            module
            for module in graph.find_downstream_modules(importer)
            if any(module == own or module.startswith(f"{own}.") for own in shipped)
        }
    assert reaching == _FAIL_WITHOUT_YAML


def test_the_modules_that_need_yaml_are_the_ones_that_fail_without_it() -> None:
    """Import every shipped module with yaml blocked, in one child, and compare."""
    modules = sorted(
        ".".join(path.parent.parts if path.name == "__init__.py" else path.with_suffix("").parts)
        for package in lib_mirror.PACKAGES
        for path in (
            found.relative_to(_REPO_ROOT)
            for found in (_REPO_ROOT / "scripts" / package).rglob("*.py")
            if "__pycache__" not in found.parts
        )
    )
    program = textwrap.dedent(
        """
        import importlib, json, sys
        class Block:
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] == "yaml":
                    raise ModuleNotFoundError("No module named 'yaml'", name="yaml")
        sys.meta_path.insert(0, Block())
        failed = []
        for name in json.loads(sys.argv[1]):
            try:
                importlib.import_module(name)
            except ModuleNotFoundError as error:
                if error.name == "yaml":
                    failed.append(name)
        print(json.dumps(failed))
        """
    )
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", program, json.dumps(modules)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert modules
    assert set(json.loads(result.stdout)) == _FAIL_WITHOUT_YAML
