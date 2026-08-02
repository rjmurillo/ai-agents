"""Find tracked Python scripts launched through ``sys.executable``."""

from __future__ import annotations

import ast
from collections.abc import Iterator

_SUBPROCESS_CALLS = {"call", "check_call", "check_output", "Popen", "run"}
_FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_sys_executable(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "executable"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _tracked_suffix(parts: list[str], tracked_py: set[str]) -> str | None:
    if not parts:
        return None
    candidate = "/".join(part.strip("/") for part in parts)
    matches = [path for path in tracked_py if path == candidate or path.endswith(f"/{candidate}")]
    return matches[0] if len(matches) == 1 else None


def _path_expression(node: ast.AST, tracked_py: set[str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _tracked_suffix([node.value], tracked_py)
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr != "join":
        return None
    parts = [
        arg.value
        for arg in node.args
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
    ]
    return _tracked_suffix(parts, tracked_py)


def _executable_nodes(body: list[ast.stmt]) -> Iterator[ast.AST]:
    """Yield nodes that run when this statement body runs."""
    pending: list[ast.AST] = list(reversed(body))
    while pending:
        node = pending.pop()
        if isinstance(node, _FUNCTION_NODES):
            continue
        yield node
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _called_local_functions(
    body: list[ast.stmt], functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef]
) -> set[str]:
    return {
        node.func.id
        for node in _executable_nodes(body)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in functions
    }


def _reachable_scopes(tree: ast.Module) -> list[list[ast.stmt]]:
    """Return module and local-function bodies reachable from module execution."""
    functions = {node.name: node for node in tree.body if isinstance(node, _FUNCTION_NODES)}
    scopes = [tree.body]
    pending = list(_called_local_functions(tree.body, functions))
    reached: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        body = functions[name].body
        scopes.append(body)
        pending.extend(_called_local_functions(body, functions) - reached)
    return scopes


def _python_subprocess_command(node: ast.AST) -> ast.List | ast.Tuple | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr not in _SUBPROCESS_CALLS or not node.args:
        return None
    if not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
        return None
    command = node.args[0]
    if not isinstance(command, (ast.List, ast.Tuple)) or len(command.elts) < 2:
        return None
    return command if _is_sys_executable(command.elts[0]) else None


def _path_assignment(node: ast.AST, tracked_py: set[str]) -> tuple[str, str] | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    path = _path_expression(node.value, tracked_py)
    return (target.id, path) if isinstance(target, ast.Name) and path else None


def _scope_targets(body: list[ast.stmt], tracked_py: set[str]) -> set[str]:
    assigned_paths: dict[str, str] = {}
    targets: set[str] = set()
    for node in _executable_nodes(body):
        assignment = _path_assignment(node, tracked_py)
        if assignment:
            assigned_paths[assignment[0]] = assignment[1]
            continue
        command = _python_subprocess_command(node)
        if command is None:
            continue
        script = command.elts[1]
        path = (
            assigned_paths.get(script.id)
            if isinstance(script, ast.Name)
            else _path_expression(script, tracked_py)
        )
        if path:
            targets.add(path)
    return targets


def python_subprocess_targets(tree: ast.Module, tracked_py: set[str]) -> set[str]:
    """Return tracked scripts launched through reachable local subprocess calls."""
    targets: set[str] = set()
    for body in _reachable_scopes(tree):
        targets |= _scope_targets(body, tracked_py)
    return targets
