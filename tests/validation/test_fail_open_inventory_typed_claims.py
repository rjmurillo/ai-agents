"""A fail-open inventory row cannot claim ``TYPED`` unless its script emits the typed result.

Issue #5636 acceptance criterion: "Every non-blocking path emits an explicit
WARNING, BLOCKED, or SKIP result and a machine-readable reason." The inventory's
``Contract`` column says which rows do. Its own definition reads:

    `TYPED` if the path reports through `scripts/validation/evidence.py`,
    `BOOLEAN` otherwise, `N/A` for workflow YAML.

Before this test, that column was prose. A row could say ``TYPED`` while its
function still returned ``True`` on every path, and nothing failed. This test
resolves each ``TYPED`` row to source and checks the claim statically.

Two resolution levels, because the tables differ:

* A table with a ``Function`` column names the function, so the test parses the
  script and requires that function to be annotated as returning
  ``CheckOutcome`` or ``GateResult``, or (for an exit-code function) to build a
  ``CheckOutcome`` itself or through one helper.
* A table without one (the hook jobs) names only the script, so the test
  requires the script to import ``CheckOutcome`` from the evidence module, or,
  for a self-contained skill script that cannot import the repository package,
  to define the module-level ``TYPED_RESULT_VOCABULARY`` mirror that
  ``tests/skills/security-detection/test_typed_vocabulary_parity.py`` checks
  against ``evidence.py``.

This is a static check. It proves the function is declared to return, or builds,
the typed contract; the behavioral tests beside each converted gate prove each
path returns the right state.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / ".agents/governance/FAIL-OPEN-INVENTORY.md"
SEARCH_ROOTS = ("scripts", ".github/scripts", ".claude/skills")
# GatePolicy is here for one row: ``default_pre_pr_policy`` builds the licences
# that keep a typed BLOCKED or FAIL from blocking, and is part of the same
# evidence.py contract even though it returns the policy, not an outcome.
TYPED_ANNOTATIONS = ("CheckOutcome", "GateResult", "GatePolicy")
UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
TRAILING_COMMENT = re.compile(r"\s*<!--.*-->\s*$")
PY_FILE = re.compile(r"`([A-Za-z0-9_./-]+\.py)(?::[0-9,-]+)?`")
EVIDENCE_IMPORT = re.compile(
    r"from\s+(?:scripts\.validation\.)?evidence\s+import[^#]*?\bCheckOutcome\b", re.S
)


MIRROR_NAME = "TYPED_RESULT_VOCABULARY"


class TypedClaim(NamedTuple):
    path_cell: str
    function: str


def _cells(line: str) -> list[str]:
    return [c.strip() for c in UNESCAPED_PIPE.split(TRAILING_COMMENT.sub("", line))[1:-1]]


def _first_code_span(cell: str) -> str:
    match = re.search(r"`([^`]+)`", cell)
    return match.group(1) if match else ""


def typed_claims(text: str) -> list[TypedClaim]:
    """Return every table row whose ``Contract`` cell is exactly ``TYPED``."""
    claims: list[TypedClaim] = []
    header: list[str] = []
    for raw in text.splitlines():
        if not raw.startswith("|"):
            header = []
            continue
        cells = _cells(raw)
        if cells and cells[0] == "Path":
            header = cells
            continue
        if not header or raw.startswith("|---") or "Contract" not in header:
            continue
        if len(cells) != len(header) or cells[header.index("Contract")] != "TYPED":
            continue
        function = _first_code_span(cells[header.index("Function")]) if "Function" in header else ""
        claims.append(TypedClaim(cells[0], function))
    return claims


def _script_paths(path_cell: str, root: Path) -> list[Path]:
    found: list[Path] = []
    for name in PY_FILE.findall(path_cell):
        base = Path(name).name
        for search_root in SEARCH_ROOTS:
            found.extend(sorted((root / search_root).rglob(base)))
    return found


def _functions(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Module-level functions only, so a same-named method cannot stand in for a helper."""
    return {
        node.name: node
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _builds_check_outcome(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True when the body calls ``CheckOutcome.<constructor>(...)``.

    A parameter or return annotation that names the type does not count, so a
    function that only accepts an outcome cannot back a TYPED claim.
    """
    return any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "CheckOutcome"
        for statement in node.body
        for n in ast.walk(statement)
    )


def _defines_vocabulary_mirror(source: str) -> bool:
    """True when the module assigns ``TYPED_RESULT_VOCABULARY`` and then reads it.

    A declared constant nothing reads proves no typed output, so the claim also
    needs a load of the name outside its own assignment.
    """
    tree = ast.parse(source)
    defined = False
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        defined = defined or any(isinstance(t, ast.Name) and t.id == MIRROR_NAME for t in targets)
    loaded = any(
        isinstance(n, ast.Name) and n.id == MIRROR_NAME and isinstance(n.ctx, ast.Load)
        for n in ast.walk(tree)
    )
    return defined and loaded


def _function_returns_typed(source: str, function: str) -> bool:
    """True when ``function`` is annotated typed, or builds a ``CheckOutcome`` itself.

    The second clause is for an exit-code function (``-> int``) that reports its
    non-pass paths as typed result lines. It counts a direct use of
    ``CheckOutcome`` constructor in the body, or a call to one module-level helper
    that does.
    One hop only, so a claim cannot ride on a distant call chain.
    """
    functions = _functions(source)
    node = functions.get(function)
    if node is None:
        return False
    if node.returns is not None:
        annotation = ast.unparse(node.returns)
        if any(typed in annotation for typed in TYPED_ANNOTATIONS):
            return True
    if _builds_check_outcome(node):
        return True
    calls = (n for n in ast.walk(node) if isinstance(n, ast.Call))
    called = {n.func.id for n in calls if isinstance(n.func, ast.Name)}
    return any(_builds_check_outcome(functions[name]) for name in called if name in functions)


def unproven_claims(claims: list[TypedClaim], root: Path) -> list[str]:
    """Return the path cell of every claim its script does not back."""
    bad: list[str] = []
    for claim in claims:
        scripts = _script_paths(claim.path_cell, root)
        if not scripts:
            bad.append(f"{claim.path_cell}: no checked-in Python script resolved")
            continue
        for script in scripts:
            source = script.read_text(encoding="utf-8")
            backed = (
                _function_returns_typed(source, claim.function)
                if claim.function
                else bool(EVIDENCE_IMPORT.search(source) or _defines_vocabulary_mirror(source))
            )
            if not backed:
                bad.append(f"{claim.path_cell}: {script.relative_to(root)} does not emit it")
    return bad


def test_the_inventory_has_typed_rows() -> None:
    """Negative control: a parser that finds no TYPED row would pass every test below."""
    assert len(typed_claims(INVENTORY.read_text(encoding="utf-8"))) >= 2


def test_every_typed_row_is_backed_by_a_script_that_emits_the_typed_result() -> None:
    claims = typed_claims(INVENTORY.read_text(encoding="utf-8"))

    assert unproven_claims(claims, ROOT) == []


def _table(function_cell: str, contract: str, path: str = "`gate.py:1`") -> str:
    return (
        "| Path | Function | Contract |\n|---|---|---|\n"
        f"| {path} | `{function_cell}` | {contract} |\n"
    )


def _fake_repo(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "scripts" / "validation"
    target.mkdir(parents=True)
    (target / "gate.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_a_typed_claim_on_a_function_that_returns_bool_is_flagged(tmp_path: Path) -> None:
    root = _fake_repo(tmp_path, "def validate_x(repo_root) -> bool:\n    return True\n")
    claims = typed_claims(_table("validate_x", "TYPED"))

    assert len(unproven_claims(claims, root)) == 1


def test_a_typed_claim_on_a_function_annotated_as_typed_is_accepted(tmp_path: Path) -> None:
    body = "def validate_x(repo_root) -> CheckOutcome:\n    ...\n"
    claims = typed_claims(_table("validate_x", "TYPED"))

    assert unproven_claims(claims, _fake_repo(tmp_path, body)) == []


def test_a_gate_result_annotation_also_counts_as_typed(tmp_path: Path) -> None:
    body = "def validate_x(repo_root) -> GateResult:\n    ...\n"
    claims = typed_claims(_table("validate_x", "TYPED"))

    assert unproven_claims(claims, _fake_repo(tmp_path, body)) == []


def test_a_boolean_row_is_not_a_claim() -> None:
    assert typed_claims(_table("validate_x", "BOOLEAN")) == []


def test_a_typed_claim_naming_a_missing_function_is_flagged(tmp_path: Path) -> None:
    body = "def other(repo_root) -> CheckOutcome:\n    ...\n"
    claims = typed_claims(_table("validate_x", "TYPED"))

    assert len(unproven_claims(claims, _fake_repo(tmp_path, body))) == 1


def test_a_typed_claim_with_no_resolvable_script_is_flagged(tmp_path: Path) -> None:
    claims = typed_claims(_table("validate_x", "TYPED", path="`ghost.py:1`"))

    assert "no checked-in Python script resolved" in unproven_claims(claims, tmp_path)[0]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from scripts.validation.evidence import CheckOutcome\n", True),
        ("from scripts.validation.evidence import (\n    REASON_X,\n    CheckOutcome,\n)\n", True),
        ("import json\n", False),
        ("# CheckOutcome is mentioned in a comment only\n", False),
    ],
)
def test_a_functionless_table_requires_the_evidence_import(
    tmp_path: Path, source: str, expected: bool
) -> None:
    table = "| Path | Contract |\n|---|---|\n| `gate.py:1` | TYPED |\n"
    claims = typed_claims(table)

    assert (unproven_claims(claims, _fake_repo(tmp_path, source)) == []) is expected


def test_a_functionless_table_accepts_the_portable_vocabulary_mirror(tmp_path: Path) -> None:
    table = "| Path | Contract |\n|---|---|\n| `gate.py:1` | TYPED |\n"
    claims = typed_claims(table)
    body = 'TYPED_RESULT_VOCABULARY = {"PASS": "PASS"}\n_V = TYPED_RESULT_VOCABULARY\n'

    assert unproven_claims(claims, _fake_repo(tmp_path, body)) == []


def test_a_vocabulary_mirror_that_nothing_reads_does_not_back_the_claim(tmp_path: Path) -> None:
    table = "| Path | Contract |\n|---|---|\n| `gate.py:1` | TYPED |\n"
    claims = typed_claims(table)
    body = 'TYPED_RESULT_VOCABULARY = {"PASS": "PASS"}\n'

    assert len(unproven_claims(claims, _fake_repo(tmp_path, body))) == 1


@pytest.mark.parametrize(
    "source",
    [
        "# TYPED_RESULT_VOCABULARY is mentioned in a comment only\n",
        "def f():\n    TYPED_RESULT_VOCABULARY = {}\n",
        "OTHER_VOCABULARY = {}\n",
    ],
)
def test_a_functionless_table_rejects_a_mirror_that_is_not_module_level(
    tmp_path: Path, source: str
) -> None:
    table = "| Path | Contract |\n|---|---|\n| `gate.py:1` | TYPED |\n"
    claims = typed_claims(table)

    assert len(unproven_claims(claims, _fake_repo(tmp_path, source))) == 1


def test_an_exit_code_function_that_builds_a_check_outcome_is_accepted(tmp_path: Path) -> None:
    body = (
        "def run_job() -> int:\n"
        "    print(CheckOutcome.skipped('j', reason='r').summary_line())\n"
        "    return 0\n"
    )
    claims = typed_claims(_table("run_job", "TYPED"))

    assert unproven_claims(claims, _fake_repo(tmp_path, body)) == []


def test_an_exit_code_function_that_calls_a_typed_helper_is_accepted(tmp_path: Path) -> None:
    body = (
        "def _emit():\n"
        "    return CheckOutcome.skipped('j', reason='r')\n"
        "def run_job() -> int:\n"
        "    _emit()\n"
        "    return 0\n"
    )
    claims = typed_claims(_table("run_job", "TYPED"))

    assert unproven_claims(claims, _fake_repo(tmp_path, body)) == []


def test_an_exit_code_function_with_no_typed_use_is_flagged(tmp_path: Path) -> None:
    body = "def run_job() -> int:\n    print('WARNING: skipped')\n    return 0\n"
    claims = typed_claims(_table("run_job", "TYPED"))

    assert len(unproven_claims(claims, _fake_repo(tmp_path, body))) == 1


def test_a_helper_two_hops_away_does_not_back_the_claim(tmp_path: Path) -> None:
    body = (
        "def _leaf():\n"
        "    return CheckOutcome.skipped('j', reason='r')\n"
        "def _mid():\n"
        "    return _leaf()\n"
        "def run_job() -> int:\n"
        "    _mid()\n"
        "    return 0\n"
    )
    claims = typed_claims(_table("run_job", "TYPED"))

    assert len(unproven_claims(claims, _fake_repo(tmp_path, body))) == 1


def test_a_class_method_with_the_same_name_does_not_back_the_claim(tmp_path: Path) -> None:
    body = (
        "def _emit():\n"
        "    pass\n"
        "def run_job() -> int:\n"
        "    _emit()\n"
        "    return 0\n"
        "class Unrelated:\n"
        "    def _emit(self):\n"
        "        return CheckOutcome.skipped('j', reason='r')\n"
    )
    claims = typed_claims(_table("run_job", "TYPED"))

    assert len(unproven_claims(claims, _fake_repo(tmp_path, body))) == 1


def test_an_annotation_that_only_names_the_type_does_not_back_the_claim(tmp_path: Path) -> None:
    body = "def run_job(outcome: CheckOutcome) -> int:\n    return 0\n"
    claims = typed_claims(_table("run_job", "TYPED"))

    assert len(unproven_claims(claims, _fake_repo(tmp_path, body))) == 1
