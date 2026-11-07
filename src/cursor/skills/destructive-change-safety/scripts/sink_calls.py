"""AST helpers that read HTTP DELETE and git argv sinks (destructive-change-safety).

Split from ``sink_scan`` to keep that module under the file-size limit. These
helpers inspect one ``ast.Call`` and return a label, or an empty string.
"""

from __future__ import annotations

import ast

SUBPROCESS_CALLS = {"run", "call", "check_call", "check_output", "Popen", "system"}

# HTTP clients whose ``delete`` function removes a remote resource.
HTTP_DELETE_CALLS = {"requests.delete", "httpx.delete", "aiohttp.delete"}
HTTP_REQUEST_CALLS = {"requests.request", "httpx.request", "urllib.request.Request", "Request"}


def dotted_name(node: ast.AST) -> str:
    """Return ``a.b.c`` for a Name or Attribute chain, else an empty string."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def callee_name(node: ast.Call) -> str:
    """Return the simple name a call resolves to in the name-based graph."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def is_delete_literal(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.upper() == "DELETE"
    )


def http_delete_sink(node: ast.Call) -> str:
    """Return a label when a call issues an HTTP DELETE (requests, httpx, urllib)."""
    dotted = dotted_name(node.func)
    if dotted in HTTP_DELETE_CALLS:
        return f"{dotted}()"
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "delete"
        and isinstance(node.func.value, ast.Call | ast.Name | ast.Attribute)
    ):
        return ".delete()"
    method_args = [node.args[0]] if node.args else []
    method_args += [k.value for k in node.keywords if k.arg == "method"]
    if dotted in HTTP_REQUEST_CALLS or callee_name(node) == "request":
        if any(is_delete_literal(a) for a in method_args):
            return f"{dotted or callee_name(node)}(DELETE)"
    return ""


def leftmost_operand(node: ast.AST) -> ast.AST:
    """Return the leftmost operand of a ``a + b + c`` chain, else the node itself."""
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        node = node.left
    return node


def is_git_wrapper(node: ast.Call) -> bool:
    """True for a call to a function named for git, or ``subprocess`` run on ``git``."""
    name = callee_name(node).lower()
    if name == "git" or name.startswith("git_") or name.endswith("_git") or "_git_" in name:
        return True
    first = leftmost_operand(node.args[0]) if node.args else None
    return (
        dotted_name(node.func).split(".")[-1] in SUBPROCESS_CALLS
        and isinstance(first, ast.List | ast.Tuple)
        and bool(first.elts)
        and isinstance(first.elts[0], ast.Constant)
        and first.elts[0].value == "git"
    )


def variable_git_argv_sink(node: ast.Call) -> str:
    """Return a label when a git wrapper receives an argv the scan cannot read.

    A variable list (``run_git(args)``), a starred argument (``run_git(*args)``),
    any other non-literal expression (an attribute, a call, an f-string,
    a concatenation), a starred element (``["push", *rest]``), a non-literal subcommand, or a
    ``push`` with a non-literal argument (a variable refspec can be ``+main``)
    hides what git will run, so the scan fails closed and reports it for review.
    """
    if not node.args or not is_git_wrapper(node):
        return ""
    first = node.args[0]
    if isinstance(first, ast.BinOp):
        return "git argv built by concatenation"
    if isinstance(first, ast.Name):
        return "git argv from variable"
    if isinstance(first, ast.Starred):
        return "git argv from starred argument"
    if not isinstance(first, ast.List | ast.Tuple | ast.Constant):
        return "git argv from non-literal expression"
    if isinstance(first, ast.List | ast.Tuple):
        elts = first.elts
        if any(isinstance(e, ast.Starred) for e in elts):
            return "git argv with starred elements"
        head = 1 if elts and isinstance(elts[0], ast.Constant) and elts[0].value == "git" else 0
        if len(elts) > head and not isinstance(elts[head], ast.Constant):
            return "git argv with non-literal subcommand"
        sub = elts[head] if len(elts) > head else None
        if (
            isinstance(sub, ast.Constant)
            and sub.value == "push"
            and any(not isinstance(e, ast.Constant) for e in elts[head + 1 :])
        ):
            return "git push argv with non-literal refspec"
    return ""
