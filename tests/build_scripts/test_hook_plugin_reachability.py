"""Every file in the Claude plugin hooks tree is reachable from ``hooks.json``.

ADR-109 amendment 2026-11-11 (issue #7231): repo-only hooks render straight to
``.claude/hooks/`` and never enter ``src/claude/hooks/``. This test keeps the
plugin tree honest in two directions, both walked from ``hooks.json``:

1. Every file under ``src/claude/hooks/`` is the dispatcher, its manifest, a
   shim of a group that ``hooks.json`` registers, or a module such a file
   imports. An unregistered file is dead weight shipped to every consumer.
2. Every shim of every registered group exists under ``src/claude/hooks/``.

Imports are found by parsing each reachable ``.py`` and resolving each
top-level module name against the importer's own directory and the hooks root.
Anything that resolves elsewhere (the plugin ``lib/`` tree, the stdlib) is out
of scope.

It also pins the surface-parity ``hooks-claude-repo-only`` include list to the
files under the ``repo_only`` entries of the ``hooks`` binplace row, the one
fact those two lists must agree on.
"""

from __future__ import annotations

import ast
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "build" / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "build" / "scripts"))

import binplace_manifest  # noqa: E402
from generate_hooks_expand import _DISPATCH_COMMAND_RE  # noqa: E402

PLUGIN_HOOKS = _REPO_ROOT / "src" / "claude" / "hooks"
SURFACE_PARITY = _REPO_ROOT / "templates" / "platforms" / "surface-parity.yaml"
REPO_ONLY_SURFACE_ID = "hooks-claude-repo-only"
SEED_NAMES = ("hooks.json", "dispatch_groups.json", "invoke_dispatch_claude.py")


def _tree_files(hooks_root: Path) -> set[str]:
    """POSIX paths of every non-bytecode file under ``hooks_root``."""
    return {
        path.relative_to(hooks_root).as_posix()
        for path in hooks_root.rglob("*")
        if path.is_file()
        and not binplace_manifest.is_bytecode_artifact(path.relative_to(hooks_root))
    }


def _command_strings(node: object) -> list[str]:
    """Every ``command`` string nested anywhere in a parsed ``hooks.json``."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "command" and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_command_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_command_strings(item))
    return found


def registered_groups(hooks_root: Path) -> list[str]:
    """Group ids named by a ``--group`` flag in a ``hooks.json`` dispatcher command."""
    doc = json.loads((hooks_root / "hooks.json").read_text(encoding="utf-8"))
    groups: list[str] = []
    for command in _command_strings(doc):
        match = _DISPATCH_COMMAND_RE.search(command)
        if match is not None:
            groups.append(match.group(1))
    return groups


def group_shims(hooks_root: Path) -> dict[str, list[str]]:
    """Map every registered group id to its shim paths; ``None`` shims mean an unknown group."""
    manifest = json.loads((hooks_root / "dispatch_groups.json").read_text(encoding="utf-8"))
    known = manifest.get("groups", {})
    result: dict[str, list[str]] = {}
    for group in registered_groups(hooks_root):
        shims = known.get(group, {}).get("shims", [])
        result[group] = [shim["file"] for shim in shims]
    return result


def _imported_module_names(source: str) -> set[str]:
    """Top-level module names imported by ``source``, at any nesting depth."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
            elif node.level > 0:
                names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and _is_import_module_call(node):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value.split(".")[0])
    return names


def _is_import_module_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "import_module" and bool(node.args)
    return isinstance(func, ast.Name) and func.id == "import_module" and bool(node.args)


def _resolve_import(hooks_root: Path, importer: str, name: str) -> str | None:
    """Return the in-tree path ``name`` resolves to for ``importer``, else ``None``."""
    candidates = (
        (hooks_root / importer).parent / f"{name}.py",
        hooks_root / f"{name}.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.relative_to(hooks_root).as_posix()
    return None


def reachable_files(hooks_root: Path) -> set[str]:
    """Seeds plus the import closure of every reachable ``.py``, iterated to a fixpoint."""
    reachable = {name for name in SEED_NAMES if (hooks_root / name).is_file()}
    for shims in group_shims(hooks_root).values():
        reachable.update(shim for shim in shims if (hooks_root / shim).is_file())
    pending = [rel for rel in reachable if rel.endswith(".py")]
    while pending:
        importer = pending.pop()
        source = (hooks_root / importer).read_text(encoding="utf-8")
        for name in _imported_module_names(source):
            resolved = _resolve_import(hooks_root, importer, name)
            if resolved is not None and resolved not in reachable:
                reachable.add(resolved)
                pending.append(resolved)
    return reachable


def unreachable_files(hooks_root: Path) -> set[str]:
    """Files under ``hooks_root`` that nothing registered reaches."""
    return _tree_files(hooks_root) - reachable_files(hooks_root)


def missing_shims(hooks_root: Path) -> set[str]:
    """Shim paths of registered groups (or group ids with none) absent from the tree."""
    missing: set[str] = set()
    for group, shims in group_shims(hooks_root).items():
        if not shims:
            missing.add(f"<no shims for group {group}>")
        missing.update(shim for shim in shims if not (hooks_root / shim).is_file())
    return missing


def parity_gap(include: set[str], template_files: set[str]) -> set[str]:
    """Symmetric difference between the surface include list and the template files."""
    return include ^ template_files


def _repo_only_files() -> set[str]:
    rows = {row.class_name: row for row in binplace_manifest.load(_REPO_ROOT)}
    return set(binplace_manifest.repo_only_template_files(rows["hooks"]))


def _surface_include() -> set[str]:
    doc = yaml.safe_load(SURFACE_PARITY.read_text(encoding="utf-8"))
    surfaces = {surface["id"]: surface for surface in doc["surfaces"]}
    return set(surfaces[REPO_ONLY_SURFACE_ID]["include"])


@pytest.fixture
def hooks_copy(tmp_path: Path) -> Path:
    """A scratch copy of the plugin hooks tree for negative controls."""
    target = tmp_path / "hooks"
    shutil.copytree(PLUGIN_HOOKS, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return target


def test_every_plugin_hooks_file_is_reachable_from_hooks_json() -> None:
    unreachable = unreachable_files(PLUGIN_HOOKS)

    assert not unreachable, f"unregistered files ship to every consumer: {sorted(unreachable)}"
    assert _tree_files(PLUGIN_HOOKS)  # a vacuous walk would pass for an empty tree


def test_every_registered_shim_exists_in_the_plugin_tree() -> None:
    shims = group_shims(PLUGIN_HOOKS)

    assert shims, "hooks.json registers no dispatcher group"
    assert not missing_shims(PLUGIN_HOOKS)


def test_walk_reaches_a_helper_module_through_a_shim_import() -> None:
    """Pins the import-closure direction: Stop/_reflect_nudge_state.py is only imported."""
    assert "Stop/_reflect_nudge_state.py" in reachable_files(PLUGIN_HOOKS)


def test_negative_control_unregistered_file_fails(hooks_copy: Path) -> None:
    (hooks_copy / "SessionStart").mkdir()
    (hooks_copy / "SessionStart" / "invoke_unregistered.py").write_text("x = 1\n", "utf-8")

    assert unreachable_files(hooks_copy) == {"SessionStart/invoke_unregistered.py"}


def test_negative_control_removed_shim_fails(hooks_copy: Path) -> None:
    (hooks_copy / "Stop" / "invoke_reflect_nudge.py").unlink()

    assert missing_shims(hooks_copy) == {"Stop/invoke_reflect_nudge.py"}


def test_negative_control_orphan_helper_fails(hooks_copy: Path) -> None:
    (hooks_copy / "Stop" / "_orphan_helper.py").write_text("x = 1\n", "utf-8")

    assert unreachable_files(hooks_copy) == {"Stop/_orphan_helper.py"}


def test_positive_control_imported_helper_is_reachable(hooks_copy: Path) -> None:
    """An added helper that a shim imports is reachable, so the walk does not over-fire."""
    (hooks_copy / "Stop" / "_new_helper.py").write_text("x = 1\n", "utf-8")
    shim = hooks_copy / "Stop" / "invoke_reflect_nudge.py"
    shim.write_text(
        shim.read_text("utf-8") + "\ntry:\n    import _new_helper\nexcept ImportError:\n    pass\n",
        "utf-8",
    )

    assert not unreachable_files(hooks_copy)


def test_import_module_literal_counts_as_an_import(hooks_copy: Path) -> None:
    (hooks_copy / "Stop" / "_lazy_helper.py").write_text("x = 1\n", "utf-8")
    shim = hooks_copy / "Stop" / "invoke_reflect_nudge.py"
    shim.write_text(
        shim.read_text("utf-8") + '\nimport importlib\nimportlib.import_module("_lazy_helper")\n',
        "utf-8",
    )

    assert not unreachable_files(hooks_copy)


def test_bytecode_in_the_tree_is_not_an_unreachable_file(hooks_copy: Path) -> None:
    cache = hooks_copy / "Stop" / "__pycache__"
    cache.mkdir()
    (cache / "invoke_reflect_nudge.cpython-314.pyc").write_bytes(b"\x00")

    assert not unreachable_files(hooks_copy)


def test_surface_include_equals_files_under_repo_only_entries() -> None:
    files = _repo_only_files()

    assert files, "the hooks row lists no repo-only files"
    assert parity_gap(_surface_include(), files) == set()


def test_negative_control_name_added_to_surface_side_only_fails() -> None:
    files = _repo_only_files()

    assert parity_gap(_surface_include() | {"SessionStart/invented.py"}, files) == {
        "SessionStart/invented.py"
    }


def test_negative_control_name_added_to_template_side_only_fails() -> None:
    files = _repo_only_files() | {"SessionStart/stray.py"}

    assert parity_gap(_surface_include(), files) == {"SessionStart/stray.py"}
