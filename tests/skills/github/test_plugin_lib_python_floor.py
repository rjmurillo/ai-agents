"""The bundled library must import on the host's ambient interpreter.

Skill scripts launch with bare `python3`, so the whole import closure of
`github_core.api` has to work at the portability floor, currently 3.10. A
syntax-level check cannot see this: a 3.11-only stdlib API parses clean at
3.10 and fails on import.

Two rounds of review found two separate instances of exactly that
(`datetime.UTC` in `output.py`, `enum.StrEnum` in `review_threads.py`), and
both times the scope was assessed by hand and got it wrong. This scans the
real closure instead (Copilot review on PR #5509).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[3]
_LIB = _project_root / ".claude" / "lib"
_COPILOT_LIB = _project_root / "src" / "copilot-cli" / "lib"

# Runtime stdlib names newer than the 3.10 floor. Names, not syntax: the floor
# gate already covers syntax, and every name below parses clean at 3.10.
#
# Split in two because precision differs by shape. A `from <module> import
# <name>` names its own module, so the pair is unambiguous and the table can
# hold ordinary words. A bare `Self` or an `x.timeout` attribute does not, so
# the second table holds only names distinctive enough that a false positive is
# implausible; `timeout`, `walk`, and `override` are deliberately absent from
# it because each is a plausible local in code that is already floor-clean, and
# a gate that fails a push for the wrong reason teaches people to bypass it.
_TOO_NEW_FROM_IMPORT = {
    "datetime": {"UTC": "3.11"},
    "enum": {"StrEnum": "3.11", "ReprEnum": "3.11"},
    "typing": {
        "Self": "3.11",
        "Never": "3.11",
        "LiteralString": "3.11",
        "assert_never": "3.11",
        "override": "3.12",
        "TypeAliasType": "3.12",
    },
    "asyncio": {"TaskGroup": "3.11", "timeout": "3.11"},
    "itertools": {"batched": "3.12"},
    "hashlib": {"file_digest": "3.11"},
}

_TOO_NEW = {
    "StrEnum": "3.11",
    "ReprEnum": "3.11",
    "ExceptionGroup": "3.11",
    "BaseExceptionGroup": "3.11",
    "tomllib": "3.11",
    "TaskGroup": "3.11",
    "Self": "3.11",
    "LiteralString": "3.11",
    "assert_never": "3.11",
    "TypeAliasType": "3.12",
}


def _closure_files(lib_root: Path) -> list[Path]:
    """Every github_core module reachable from the preflight's entry import.

    Walked statically from the source rather than from ``sys.modules``. An
    earlier version read the live module table, which made the result depend
    on what the rest of the suite had already imported and on which path those
    imports resolved through, so it passed alone and failed in a full run. A
    test that reports on collection order cannot report on the floor.
    """
    root = lib_root / "github_core"
    seen: set[str] = set()
    pending = ["api"]
    files: list[Path] = []
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        path = root / f"{name}.py"
        if not path.is_file():
            continue
        files.append(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                pending += [
                    alias.name.split(".", 1)[1]
                    for alias in node.names
                    if alias.name.startswith("github_core.")
                ]
                continue
            if not isinstance(node, ast.ImportFrom):
                continue
            # The mirrors rewrite siblings to relative imports, so absolute
            # matching alone walked exactly one module and proved nothing.
            if node.level and node.module:
                pending.append(node.module)
            elif node.module and node.module.startswith("github_core."):
                pending.append(node.module.split(".", 1)[1])
            elif node.module and node.module.startswith("scripts.github_core."):
                pending.append(node.module.split(".", 2)[2])
    return files


# Whole modules that do not exist at the floor. `import tomllib` binds the name,
# so bare-name usage is caught by the ast.Name arm below, but an aliased import
# (`import tomllib as t`) binds a different name and was invisible to every arm
# (Copilot review on PR #5509).
_TOO_NEW_MODULES = {
    "tomllib": "3.11",
    "asyncio.taskgroups": "3.11",
}


def _module_bindings(tree: ast.AST) -> dict[str, str]:
    """Local name -> module, for every plain ``import`` in the file.

    `import datetime` binds `datetime`; `import datetime as dt` binds `dt`.
    Requiring a binding is what keeps the qualified arm below precise: an
    `x.timeout` on some local object reaches no entry here, so the gate cannot
    fail a push for a name that merely looks like a stdlib API.
    """
    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import):
            continue
        for alias in node.names:
            if alias.asname:
                bindings[alias.asname] = alias.name
            else:
                top = alias.name.split(".")[0]
                bindings[top] = top
    return bindings


def _attribute_violation(
    path: Path, node: ast.Attribute, bindings: dict[str, str]
) -> list[str]:
    """Report a too-new name reached as ``<module>.<attr>``.

    `from datetime import UTC` was the only shape either table saw, so
    `import datetime` followed by `datetime.UTC` passed, and so did the
    aliased form and the qualified `asyncio.timeout`, `itertools.batched`,
    and `hashlib.file_digest`. Each is the same runtime ImportError one
    import style over (Copilot review on PR #5509).
    """
    module = bindings.get(node.value.id) if isinstance(node.value, ast.Name) else None
    table = _TOO_NEW_FROM_IMPORT.get(module, {}) if module else {}
    if node.attr in table:
        return [f"{path.name}: {module}.{node.attr} ({table[node.attr]})"]
    if node.attr in _TOO_NEW:
        return [f"{path.name}: {node.attr} ({_TOO_NEW[node.attr]})"]
    return []


def _violations(path: Path) -> list[str]:
    found = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bindings = _module_bindings(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [
                f"{path.name}: import {alias.name} ({_TOO_NEW_MODULES[alias.name]})"
                for alias in node.names
                if alias.name in _TOO_NEW_MODULES
            ]
        if isinstance(node, ast.ImportFrom) and node.module in _TOO_NEW_MODULES:
            found.append(
                f"{path.name}: from {node.module} ({_TOO_NEW_MODULES[node.module]})"
            )
        if isinstance(node, ast.ImportFrom) and node.module in _TOO_NEW_FROM_IMPORT:
            table = _TOO_NEW_FROM_IMPORT[node.module]
            found += [
                f"{path.name}: {node.module}.{alias.name} ({table[alias.name]})"
                for alias in node.names
                if alias.name in table
            ]
        if isinstance(node, ast.Attribute):
            found += _attribute_violation(path, node, bindings)
        if isinstance(node, ast.Name) and node.id in _TOO_NEW:
            found.append(f"{path.name}: {node.id} ({_TOO_NEW[node.id]})")
    return found


class TestBundledLibStaysAtTheFloor:
    def test_the_preflight_import_closure_is_floor_clean(self):
        files = _closure_files(_LIB)
        assert len(files) > 5, (
            f"closure walk found only {len(files)} modules; the scan is inert"
        )
        offenders = sorted({v for f in files for v in _violations(f)})
        assert not offenders, (
            "3.11-only stdlib in the bundled import closure; a 3.10 host "
            f"cannot run any bundled skill script: {offenders}"
        )

    @pytest.mark.parametrize("lib", [_LIB, _COPILOT_LIB])
    def test_both_shipped_mirrors_are_floor_clean(self, lib):
        """The mirrors are what consumers actually install."""
        offenders = sorted(
            {v for f in lib.rglob("github_core/*.py") for v in _violations(f)}
        )
        assert not offenders, f"{lib.name} mirror is not floor-clean: {offenders}"

    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("import enum\n\n\nclass X(enum.StrEnum):\n    A = 'a'\n", "StrEnum"),
            ("from datetime import UTC\n", "datetime.UTC"),
            ("from typing import Self\n", "typing.Self"),
            ("from asyncio import timeout\n", "asyncio.timeout"),
            ("import tomllib\n", "import tomllib"),
            # The alias is the case no arm saw: it binds `t`, so the bare-name
            # arm that catches plain `import tomllib` never fires.
            ("import tomllib as t\n", "import tomllib"),
            ("from tomllib import loads\n", "from tomllib"),
            # Qualified access on a plainly imported module. Every one of these
            # passed before the binding-aware arm: the anywhere-table holds no
            # `UTC`, `batched`, or `file_digest`, and the from-import table only
            # ever saw an ImportFrom.
            ("import datetime\nx = datetime.UTC\n", "datetime.UTC"),
            ("import datetime as dt\nx = dt.UTC\n", "datetime.UTC"),
            ("import itertools\nx = itertools.batched(y, 2)\n", "itertools.batched"),
            (
                "import hashlib\nx = hashlib.file_digest(f, 'sha256')\n",
                "hashlib.file_digest",
            ),
            ("import asyncio\nx = asyncio.timeout\n", "asyncio.timeout"),
        ],
    )
    def test_the_scan_detects_a_planted_violation(self, tmp_path, source, expected):
        """Negative control: a scan that cannot fail proves nothing.

        Written under tmp_path, not into the repository. An earlier version
        planted the probe beside this file, which leaves a stray module in the
        working tree whenever the assertion fails before the unlink
        (`.claude/rules/testing.md` MUST NOT 4).

        `asyncio.timeout` is the case the anywhere-table deliberately cannot
        see, so it also proves the from-import table is doing work of its own.
        """
        planted = tmp_path / "floor_probe.py"
        planted.write_text(source, encoding="utf-8")
        assert any(expected in v for v in _violations(planted)), (
            f"the scan missed a planted {expected}"
        )

    def test_the_scan_passes_a_floor_clean_module(self):
        """Inverted control: the scan must not fail on everything it reads.

        Without it, a defect that reports a violation unconditionally reads as
        a clean sweep of the parametrized cases above.
        """
        clean = _LIB / "github_core" / "api.py"
        assert clean.is_file()
        assert not _violations(clean)

    @pytest.mark.parametrize(
        "source",
        [
            # No import binds `session`, so this attribute names a local object
            # rather than the stdlib module. The binding requirement is the
            # whole reason the qualified arm can hold ordinary words like
            # `timeout` and `batched` without failing a floor-clean push.
            "def f(session):\n    return session.timeout\n",
            "import datetime\n\n\ndef f(row):\n    return row.batched\n",
            # A module the tables do not cover, accessed the same way.
            "import os\nx = os.timeout\n",
        ],
    )
    def test_a_qualified_name_without_a_module_binding_is_not_reported(
        self, tmp_path, source
    ):
        """Control on the qualified arm: precision, not just recall.

        A gate that fails a push for the wrong reason teaches people to bypass
        it, which is the cost these cases exist to keep at zero.
        """
        planted = tmp_path / "floor_precision.py"
        planted.write_text(source, encoding="utf-8")
        assert not _violations(planted)
