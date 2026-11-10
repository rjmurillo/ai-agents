"""Pure detectors for rules 4 and 5 of check_plugin_root_interpreter.py.

``.claude/rules/plugin-self-containment.md`` MUST 4 has two halves. The
checker's rules 1 to 3 cover the invocation form and the named target. These
two cover what an invocation scan cannot see:

* **Rule 4 (single-root).** A file that names ``CLAUDE_PLUGIN_ROOT`` without
  ``COPILOT_PLUGIN_ROOT`` resolves only under Claude Code. The Copilot CLI sets
  ``COPILOT_PLUGIN_ROOT``; the canonical command form is
  ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}``. Source:
  ``src/claude/skills/agent-harness-reference/references/official-hook-contracts.md``,
  "Plugin-root variables".
* **Rule 5 (import-time).** A shipped skill or lib module whose import closure
  reaches a third-party package fails with ``ModuleNotFoundError`` under a
  consumer's bare ``python3`` before it can report anything.

Both functions take text or source and return findings. They read no files and
call no git, so tests drive them directly.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterator

CLAUDE_VAR = "CLAUDE_PLUGIN_ROOT"
COPILOT_VAR = "COPILOT_PLUGIN_ROOT"

# The default-chain expansion is the form a command actually runs. It must pair
# with the Copilot variable on the same logical line: `${COPILOT_PLUGIN_ROOT:-}`
# and `${CLAUDE_PLUGIN_ROOT:-}` are list entries joined by `\` continuations, and
# the nested form carries both.
_DEFAULT_CHAIN = re.compile(r"\$\{" + CLAUDE_VAR + r":-")

# Any other mention (prose, an `os.environ.get("CLAUDE_PLUGIN_ROOT")` read, a
# wrapped docstring) pairs with the Copilot variable within this many lines.
# Looser than the default chain on purpose: a resolver reads the two variables on
# adjacent lines and prose wraps. Known limit: a bare `$CLAUDE_PLUGIN_ROOT/...`
# next to a sentence that names both passes.
NAME_PAIRING_WINDOW = 3


def single_root_lines(logical_lines: list[str], line_maps: list[list[int]]) -> list[int]:
    """Return the 1-indexed source lines where ``CLAUDE_PLUGIN_ROOT`` stands alone.

    ``logical_lines`` and ``line_maps`` come from the checker's
    ``_join_continuations`` (backslash-newline collapsed, each character mapped
    to its source line), so a multi-line ``for root in \\`` list counts as one
    statement.
    """
    physical = _physical_lines(logical_lines, line_maps)
    found: list[int] = []
    for logical, char_map in zip(logical_lines, line_maps, strict=True):
        if CLAUDE_VAR not in logical or COPILOT_VAR in logical:
            continue
        lineno = char_map[logical.index(CLAUDE_VAR)]
        if _DEFAULT_CHAIN.search(logical) or not _copilot_nearby(physical, lineno):
            found.append(lineno)
    return found


def _physical_lines(logical_lines: list[str], line_maps: list[list[int]]) -> dict[int, str]:
    """Rebuild source lines by number, so the pairing window reads what a reader sees."""
    physical: dict[int, list[str]] = {}
    for logical, char_map in zip(logical_lines, line_maps, strict=True):
        for char, lineno in zip(logical, char_map, strict=True):
            physical.setdefault(lineno, []).append(char)
    return {lineno: "".join(chars) for lineno, chars in physical.items()}


def _copilot_nearby(physical: dict[int, str], lineno: int) -> bool:
    low, high = lineno - NAME_PAIRING_WINDOW, lineno + NAME_PAIRING_WINDOW
    return any(COPILOT_VAR in text for number, text in physical.items() if low <= number <= high)


_FALLBACK_CATCHES = frozenset({"ImportError", "ModuleNotFoundError", "Exception", "BaseException"})
_EXIT_CALLS = frozenset({"exit", "quit", "_exit"})


def _caught_names(handler: ast.ExceptHandler) -> set[str]:
    caught = handler.type
    if caught is None:
        return {"BaseException"}
    members = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return {m.id if isinstance(m, ast.Name) else getattr(m, "attr", "") for m in members}


def _handler_gives_up(handler: ast.ExceptHandler) -> bool:
    """Return whether a handler re-raises or exits, so the guard guards nothing."""
    for node in ast.walk(handler):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if name in _EXIT_CALLS:
                return True
    return False


def _provides_fallback(node: ast.Try) -> bool:
    """Return whether an ImportError in the try body is survivable.

    A handler must catch the import failure and neither re-raise nor exit. What
    the fallback does afterwards is the module's business: ``bot_config`` parses
    with a vendored reader, ``detect_adr_changes`` fails closed.
    """
    return any(
        _caught_names(handler) & _FALLBACK_CATCHES and not _handler_gives_up(handler)
        for handler in node.handlers
    )


def _is_type_checking(test: ast.expr) -> bool:
    name = getattr(test, "id", getattr(test, "attr", ""))
    return name == "TYPE_CHECKING"


def _import_time_imports(body: list[ast.stmt], guarded: bool) -> Iterator[tuple[ast.stmt, bool]]:
    """Yield ``(import node, guarded)`` for every import that runs at import time.

    Function bodies are skipped: their imports run when called. An ``if
    TYPE_CHECKING`` body is skipped: it never runs. A ``try`` body is guarded when
    a handler survives the import failing; its handlers and ``else`` and
    ``finally`` blocks keep the surrounding state.
    """
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if isinstance(node, ast.Import | ast.ImportFrom):
            yield node, guarded
        elif isinstance(node, ast.Try | ast.TryStar):
            yield from _import_time_imports(node.body, guarded or _provides_fallback(node))
            for handler in node.handlers:
                yield from _import_time_imports(handler.body, guarded)
            yield from _import_time_imports(node.orelse, guarded)
            yield from _import_time_imports(node.finalbody, guarded)
        elif isinstance(node, ast.If) and _is_type_checking(node.test):
            yield from _import_time_imports(node.orelse, guarded)
        else:
            for field in ("body", "orelse", "finalbody"):
                nested = getattr(node, field, None)
                if isinstance(nested, list):
                    yield from _import_time_imports(nested, guarded)


def _imported_roots(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def unguarded_third_party_imports(
    source: str, is_repo_module: Callable[[str], bool]
) -> list[tuple[int, str]]:
    """Return ``(line, module)`` for each import-time third-party import with no fallback.

    ``is_repo_module`` says whether a name resolves to a tracked repository
    module. Standard library names and ``__future__`` never count.

    Stricter/looser/different than ``check_doc_interpreter_portability``'s
    ``third_party_imports``: that function counts a guarded ``try``/``except
    ImportError`` import as a dependency, because it answers "can a bare
    interpreter run this exact script". This one reads a guarded import as
    compliant, which matches ``CONTRIBUTING.md`` ("A guarded import that
    complies with MUST 4, such as `bot_config -> yaml`") and the
    ``shipped-lib-no-runtime-dependencies`` contract in ``pyproject.toml``. It
    is also per file, not transitive: every shipped module is scanned itself.
    Raises ``SyntaxError`` for source that does not parse.
    """
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []
    for node, guarded in _import_time_imports(tree.body, guarded=False):
        if guarded:
            continue
        for name in _imported_roots(node):
            if name in sys.stdlib_module_names or name == "__future__" or is_repo_module(name):
                continue
            found.append((node.lineno, name))
    return found
