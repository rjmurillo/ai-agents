"""Tests for the import-linter contracts in pyproject.toml.

The contracts protect boundaries other files define, so these tests tie each
module list to its source and pin the ignore list. The fixture tests copy the
real `[tool.importlinter]` table into a small tree and prove each contract
fails on the import it forbids. The tree check runs `lint-imports` against
this repository and asserts its exit code. A grimp scan checks that the
shipped lib packages import only the standard library, and a parity test keeps
the pre-push job and the workflow step on one command.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import redirect_stdout
from importlib.metadata import packages_distributions
from pathlib import Path
from typing import Any

import pytest
import tomllib
import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BUILD_SCRIPTS = _REPO_ROOT / "build" / "scripts"
_VALIDATION_SCRIPTS = _REPO_ROOT / "scripts" / "validation"
for _path in (_BUILD_SCRIPTS, _VALIDATION_SCRIPTS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import checks_ci_parity  # noqa: E402
import lib_mirror  # noqa: E402

_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# The shrink-only ceiling for ignore_imports across every contract. Lower it in
# the change that deletes an entry. Raising it is the edit a reviewer must see.
IGNORE_IMPORTS_BASELINE = 3

_SHIPPED_LIB_CONTRACTS = (
    "shipped-lib-independence",
    "shipped-lib-self-contained",
    "shipped-lib-no-runtime-dependencies",
)

_LINT_IMPORTS = checks_ci_parity._LINT_IMPORTS_PROGRAM


def _load_pyproject() -> dict[str, Any]:
    with _PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _importlinter() -> dict[str, Any]:
    table: dict[str, Any] = _load_pyproject()["tool"]["importlinter"]
    return table


def _contracts() -> dict[str, dict[str, Any]]:
    return {contract["id"]: contract for contract in _importlinter()["contracts"]}


def _run_lint_imports(cwd: Path, config: Path) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-c", _LINT_IMPORTS, "--config", str(config), "--no-cache"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {value!r}")


def _write_config(path: Path, table: dict[str, Any]) -> None:
    lines = ["[tool.importlinter]"]
    lines += [f"{key} = {_toml_value(value)}" for key, value in table.items() if key != "contracts"]
    for contract in table["contracts"]:
        lines += ["", "[[tool.importlinter.contracts]]"]
        lines += [f"{key} = {_toml_value(value)}" for key, value in contract.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_module(root: Path, dotted: str, body: str = "") -> None:
    parts = dotted.split(".")
    for depth in range(1, len(parts)):
        init = root.joinpath(*parts[:depth], "__init__.py")
        init.parent.mkdir(parents=True, exist_ok=True)
        if not init.exists():
            init.write_text("", encoding="utf-8")
    path = root.joinpath(*parts[:-1], f"{parts[-1]}.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Path:
    """A tree the real contracts accept, with every ignored import present."""
    for package in lib_mirror.PACKAGES:
        _write_module(tmp_path, f"scripts.{package}.__init__")
        _write_module(tmp_path, f"scripts.{package}.core", "import json\n")
    _write_module(tmp_path, "scripts.utils.__init__")
    _write_module(tmp_path, "scripts.utils.helper", "import scripts.github_core.core\n")
    _write_module(tmp_path, "memory_enhancement.__init__")
    _write_module(tmp_path, "tests.__init__")
    _write_module(tmp_path, "tests.helper", "import scripts.utils.helper\n")
    for contract in _importlinter()["contracts"]:
        for entry in contract.get("ignore_imports", []):
            importer, imported = (part.strip() for part in entry.split("->"))
            _write_module(tmp_path, importer, f"import {imported}\n")
    _write_config(tmp_path / "pyproject.toml", _importlinter())
    return tmp_path


def test_repository_tree_keeps_every_contract() -> None:
    result = _run_lint_imports(_REPO_ROOT, _PYPROJECT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 broken" in result.stdout


def test_every_contract_is_registered() -> None:
    assert sorted(_contracts()) == sorted(
        [*_SHIPPED_LIB_CONTRACTS, "production-does-not-import-tests"]
    )


@pytest.mark.parametrize("contract_id", _SHIPPED_LIB_CONTRACTS)
def test_shipped_lib_contracts_name_every_mirrored_package(contract_id: str) -> None:
    contract = _contracts()[contract_id]
    modules = contract.get("modules") or contract["source_modules"]
    assert sorted(modules) == sorted(f"scripts.{package}" for package in lib_mirror.PACKAGES)


def test_runtime_dependency_contract_names_every_project_dependency() -> None:
    by_distribution: dict[str, set[str]] = {}
    for module, distributions in packages_distributions().items():
        for distribution in distributions:
            by_distribution.setdefault(canonicalize_name(distribution), set()).add(module)
    forbidden = set(_contracts()["shipped-lib-no-runtime-dependencies"]["forbidden_modules"])
    owned: set[str] = set()
    uncovered: list[str] = []
    for requirement in _load_pyproject()["project"]["dependencies"]:
        name = canonicalize_name(Requirement(requirement).name)
        modules = by_distribution.get(name, set())
        assert modules, f"no import name found for installed distribution {name}"
        owned |= modules
        # A distribution can install extra top-level names (tiktoken also
        # installs the tiktoken_ext plugin namespace); naming one is enough.
        if not modules & forbidden:
            uncovered.append(name)
    assert uncovered == []
    assert sorted(forbidden - owned) == []


def _ignore_entries() -> list[str]:
    contracts = _importlinter()["contracts"]
    return [entry for contract in contracts for entry in contract.get("ignore_imports", [])]


def test_ignore_imports_stay_within_the_baseline() -> None:
    entries = _ignore_entries()
    assert len(entries) == IGNORE_IMPORTS_BASELINE, entries


def test_every_ignore_entry_carries_a_comment() -> None:
    lines = _PYPROJECT.read_text(encoding="utf-8").splitlines()
    inside = False
    previous = ""
    commented = 0
    uncommented: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("ignore_imports = ["):
            # A one-line array has no room for a comment per entry.
            if stripped != "ignore_imports = [":
                uncommented.append(stripped)
            else:
                inside = True
        elif inside and stripped == "]":
            inside = False
        elif inside and stripped.startswith('"'):
            if previous.startswith("#"):
                commented += 1
            else:
                uncommented.append(stripped)
        previous = stripped
    assert uncommented == []
    assert commented == len(_ignore_entries())


def test_shipped_lib_imports_only_the_standard_library() -> None:
    # The forbidden contract names only the [project] dependencies. This closes
    # the rest of plugin-self-containment.md MUST 4: any other third-party
    # import, such as a dev tool, also fails under bare python3.
    import grimp

    graph = grimp.build_graph("scripts", include_external_packages=True, cache_dir=None)
    shipped = {f"scripts.{package}" for package in lib_mirror.PACKAGES}
    ignored = {tuple(part.strip() for part in entry.split("->")) for entry in _ignore_entries()}
    found: set[tuple[str, str]] = set()
    for package in shipped:
        for importer in graph.find_descendants(package) | {package}:
            for imported in graph.find_modules_directly_imported_by(importer):
                root = imported.split(".")[0]
                if root in sys.stdlib_module_names or root == "__future__":
                    continue
                if any(imported == own or imported.startswith(f"{own}.") for own in shipped):
                    continue
                found.add((importer, imported))
    assert sorted(found - ignored) == []


def _lefthook_job(name: str) -> dict[str, Any]:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    def walk(jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
        for job in jobs:
            if job.get("name") == name:
                return job
            nested = walk(job.get("group", {}).get("jobs", []))
            if nested is not None:
                return nested
        return None

    job = walk(config["pre-push"]["jobs"])
    assert job is not None, f"pre-push job {name!r} is missing"
    return job


def _workflow_step(name: str) -> dict[str, Any]:
    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    )
    steps = [
        step
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name") == name
    ]
    assert len(steps) == 1, f"expected one pytest.yml step named {name!r}"
    return steps[0]


def test_hook_and_workflow_run_the_same_command() -> None:
    hook = _lefthook_job("import-boundaries")
    step = _workflow_step("Check import boundaries (lint-imports)")
    assert hook["run"] == step["run"] == "uv run --frozen --extra dev lint-imports --no-cache"
    assert "glob" not in hook


def test_fixture_tree_keeps_every_contract(fixture_tree: Path) -> None:
    result = _run_lint_imports(fixture_tree, fixture_tree / "pyproject.toml")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("importer", "body", "contract_name"),
    [
        (
            "scripts.github_core.cross",
            "import scripts.hook_utilities.core\n",
            "Shipped lib packages do not import each other",
        ),
        (
            "scripts.github_core.reach",
            "import scripts.utils.helper\n",
            "Shipped lib packages import nothing else from the repository",
        ),
        (
            "scripts.ai_review_common.load",
            "import yaml\n",
            "Shipped lib packages do not import the project's third-party dependencies",
        ),
        (
            "scripts.utils.uses_tests",
            "import tests.helper\n",
            "Production code does not import tests",
        ),
    ],
)
def test_each_contract_breaks_on_the_import_it_forbids(
    fixture_tree: Path, importer: str, body: str, contract_name: str
) -> None:
    _write_module(fixture_tree, importer, body)
    result = _run_lint_imports(fixture_tree, fixture_tree / "pyproject.toml")
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{contract_name} BROKEN" in result.stdout


def test_a_stale_ignore_entry_fails(fixture_tree: Path) -> None:
    _write_module(fixture_tree, "scripts.github_core.workflow_provenance", "import json\n")
    result = _run_lint_imports(fixture_tree, fixture_tree / "pyproject.toml")
    assert result.returncode != 0
    assert "scripts.github_core.workflow_provenance -> yaml" in result.stdout + result.stderr


def test_pre_pr_gate_prints_the_offending_import_from_real_output(fixture_tree: Path) -> None:
    """Drive the gate over real lint-imports output, not a one-line fake."""
    _write_module(fixture_tree, "scripts.github_core.cross", "import scripts.hook_utilities.core\n")
    with redirect_stdout(io.StringIO()) as captured:
        passed = checks_ci_parity.validate_import_boundaries(fixture_tree)
    shown = captured.getvalue()
    assert passed is False
    assert "scripts.github_core.cross -> scripts.hook_utilities.core (l.1)" in shown
    assert "Contracts: 2 kept, 2 broken." in shown


def test_pre_pr_gate_passes_on_the_fixture_tree(fixture_tree: Path) -> None:
    with redirect_stdout(io.StringIO()) as captured:
        assert checks_ci_parity.validate_import_boundaries(fixture_tree) is True
    assert "Contracts: 4 kept, 0 broken." in captured.getvalue()
