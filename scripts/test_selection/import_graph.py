"""Build and cache the repository import graph for test selection.

The forward graph maps each in-repo Python file to the in-repo files it
imports. Inverting it answers the question test selection needs: given a set of
changed files, which files (transitively) import them, and which of those are
pytest files.

Building the graph parses every Python file with ``ast`` (about 9.7s on a
2,100-file tree), so the result is cached to ``.cache/test_import_graph.json``.
The cache is rebuilt whenever any tracked ``.py`` file or ``pyproject.toml`` is
newer than the cache, so a stale graph can never hide a new edge.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

CACHE_VERSION = 3

# Directory names that never contribute import edges. Path-relative so an agent
# worktree nested under one of these names does not hide the whole checkout.
_SKIP_PARTS = frozenset(
    {"__pycache__", ".venv", ".cache", "worktrees", "node_modules", ".git", ".mypy_cache"}
)


@dataclass(frozen=True)
class ImportGraphData:
    """Forward graph plus files whose dynamic imports depend on every module."""

    graph: dict[str, frozenset[str]]
    wildcard_dependents: frozenset[str]


def find_repo_root() -> Path:
    """Repo root, resolved from this file's location (scripts/test_selection)."""
    return Path(__file__).resolve().parents[2]


def _cache_path(repo_root: Path) -> Path:
    return repo_root / ".cache" / "test_import_graph.json"


def python_files(repo_root: Path) -> list[Path]:
    """Every tracked Python source under ``repo_root``, skipping caches."""
    files: list[Path] = []
    for path in repo_root.rglob("*.py"):
        parts = path.relative_to(repo_root).parts
        if any(part in _SKIP_PARTS for part in parts):
            continue
        files.append(path)
    return files


def _module_name(rel: str) -> str:
    module = rel[: -len(".py")].replace("/", ".")
    return module.removesuffix(".__init__")


def _package_name(rel: str) -> str:
    module = _module_name(rel)
    return module if rel.endswith("/__init__.py") else module.rpartition(".")[0]


def _source_index(rels: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Map every module name to the source paths that define it."""
    index: dict[str, list[str]] = {}
    for rel in rels:
        index.setdefault(_module_name(rel), []).append(rel)
    return {module: tuple(paths) for module, paths in index.items()}


def _imported_modules(tree: ast.AST, caller: str) -> set[str]:
    """Resolve import statements in ``tree`` to candidate in-repo module names."""
    modules: set[str] = set()
    package = _package_name(caller)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split(".") if package else []
                keep = max(0, len(parts) - node.level + 1)
                prefix = ".".join(parts[:keep])
                base = ".".join(part for part in (prefix, node.module or "") if part)
            else:
                base = node.module or ""
            if base:
                modules.add(base)
            for alias in node.names:
                if alias.name != "*":
                    modules.add(".".join(part for part in (base, alias.name) if part))
    return modules


def _call_arg(node: ast.Call, position: int, keyword_name: str) -> ast.AST | None:
    if len(node.args) > position:
        return node.args[position]
    for keyword in node.keywords:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _normalize_dynamic_module(module: str, package: str | None) -> str | None:
    if not module:
        return None
    if not module.startswith("."):
        return module
    if not package:
        return None
    parts = package.split(".") if package else []
    dots = len(module) - len(module.lstrip("."))
    if dots > len(parts) + 1:
        return None
    keep = len(parts) - dots + 1
    prefix = ".".join(parts[:keep])
    suffix = module.lstrip(".")
    resolved = ".".join(part for part in (prefix, suffix) if part)
    return resolved or None


def _dynamic_imported_modules(tree: ast.AST, caller: str) -> tuple[set[str], bool]:
    """Resolve dynamic import calls to module names and wildcard dependents."""
    modules: set[str] = set()
    wildcard = False
    package = _package_name(caller)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "__import__":
            module_node = _call_arg(node, 0, "name")
            module = _literal_string(module_node)
            if module is None:
                wildcard = True
                continue
            normalized = _normalize_dynamic_module(module, package)
            if normalized is not None:
                modules.add(normalized)
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
        ):
            module_node = _call_arg(node, 0, "name")
            module = _literal_string(module_node)
            if module is None:
                wildcard = True
                continue
            package_node = _call_arg(node, 1, "package")
            normalized = _normalize_dynamic_module(module, _literal_string(package_node) or package)
            if normalized is not None:
                modules.add(normalized)
    return modules, wildcard


def _resolve_import(
    index: dict[str, tuple[str, ...]],
    module: str,
    caller: str,
) -> tuple[str, ...]:
    """Resolve a module name to source paths: exact, sibling, then unique bare name."""
    if module in index:
        return index[module]
    package = _module_name(caller).rpartition(".")[0]
    sibling = ".".join(part for part in (package, module) if part)
    if sibling in index:
        return index[sibling]
    if "." in module:
        return ()
    matches = [
        paths for name, paths in index.items() if name == module or name.endswith(f".{module}")
    ]
    return matches[0] if len(matches) == 1 else ()


def build_graph_data(repo_root: Path) -> ImportGraphData:
    """Map every in-repo Python source to its imports and wildcard dependents.

    Raises:
        RuntimeError: a source file cannot be read or parsed. Callers treat any
            build failure as a signal to run the full suite.
    """
    files = python_files(repo_root)
    rels = [path.relative_to(repo_root).as_posix() for path in files]
    index = _source_index(rels)
    graph: dict[str, frozenset[str]] = {}
    wildcard_dependents: set[str] = set()
    for path, rel in zip(files, rels, strict=True):
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            # Listed by rglob but deleted before this read. A vanished file
            # cannot add an edge, so skip it rather than fail the whole build.
            continue
        except (OSError, UnicodeError) as exc:
            raise RuntimeError(f"Cannot read Python source {rel}: {exc}") from exc
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise RuntimeError(f"Cannot parse Python source {rel}: {exc}") from exc
        reached: set[str] = set()
        for module in _imported_modules(tree, rel):
            reached.update(_resolve_import(index, module, rel))
        dynamic_modules, wildcard = _dynamic_imported_modules(tree, rel)
        for module in dynamic_modules:
            reached.update(_resolve_import(index, module, rel))
        if wildcard:
            wildcard_dependents.add(rel)
        graph[rel] = frozenset(reached - {rel})
    return ImportGraphData(graph=graph, wildcard_dependents=frozenset(wildcard_dependents))


def build_graph(repo_root: Path) -> dict[str, frozenset[str]]:
    """Compatibility wrapper that returns only the forward import graph."""
    return build_graph_data(repo_root).graph


def _newest_source_mtime(repo_root: Path) -> float:
    """Latest mtime across Python sources and pyproject.toml.

    pyproject.toml is included because it defines the package layout that import
    resolution depends on; a layout change must invalidate the graph.
    """
    newest = 0.0
    for path in python_files(repo_root):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        newest = max(newest, mtime)
    pyproject = repo_root / "pyproject.toml"
    if pyproject.is_file():
        newest = max(newest, pyproject.stat().st_mtime)
    return newest


def is_cache_fresh(repo_root: Path, cache_path: Path | None = None) -> bool:
    """True when the cache exists and no source is newer than it."""
    cache = cache_path if cache_path is not None else _cache_path(repo_root)
    if not cache.is_file():
        return False
    try:
        cache_mtime = cache.stat().st_mtime
    except OSError:
        return False
    return _newest_source_mtime(repo_root) <= cache_mtime


def _read_cache(cache_path: Path) -> ImportGraphData | None:
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        return None
    raw_graph = payload.get("graph")
    raw_wildcards = payload.get("wildcard_dependents", [])
    if not isinstance(raw_graph, dict) or not isinstance(raw_wildcards, list):
        return None
    return ImportGraphData(
        graph={key: frozenset(value) for key, value in raw_graph.items()},
        wildcard_dependents=frozenset(raw_wildcards),
    )


def _write_cache(cache_path: Path, graph_data: ImportGraphData) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "graph": {key: sorted(value) for key, value in sorted(graph_data.graph.items())},
        "wildcard_dependents": sorted(graph_data.wildcard_dependents),
    }
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


def load_or_build_data(
    repo_root: Path,
    cache_path: Path | None = None,
) -> ImportGraphData:
    """Return graph data, rebuilding and caching it when stale.

    Raises:
        RuntimeError: the graph is stale and cannot be rebuilt (propagated from
            ``build_graph_data``). Callers fall back to the full suite.
    """
    cache = cache_path if cache_path is not None else _cache_path(repo_root)
    if is_cache_fresh(repo_root, cache):
        cached = _read_cache(cache)
        if cached is not None:
            return cached
    graph_data = build_graph_data(repo_root)
    try:
        _write_cache(cache, graph_data)
    except OSError:
        # A read-only or racing cache directory must not fail selection; the
        # freshly built graph is still correct for this invocation.
        pass
    return graph_data


def load_or_build(
    repo_root: Path,
    cache_path: Path | None = None,
) -> dict[str, frozenset[str]]:
    """Compatibility wrapper that returns only the forward import graph."""
    return load_or_build_data(repo_root, cache_path).graph


def reverse_graph(graph: dict[str, frozenset[str]]) -> dict[str, set[str]]:
    """Invert the forward graph: importer edges keyed by the imported file."""
    reverse: dict[str, set[str]] = {}
    for importer, imported in graph.items():
        for target in imported:
            reverse.setdefault(target, set()).add(importer)
    return reverse


def affected_closure(
    changed: Iterable[str],
    reverse: dict[str, set[str]],
) -> set[str]:
    """All files that transitively import any changed file, plus the changed files."""
    seen: set[str] = set()
    stack = list(changed)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(reverse.get(current, ()))
    return seen
