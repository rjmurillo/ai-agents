# taste-lint: ignore file-size
"""Every subprocess spawn that inherits stdout flushes the parent buffer first.

Python block-buffers ``sys.stdout`` whenever it is not a tty. A child process
that inherits file descriptor 1 writes straight to the descriptor, so its
output lands ahead of whatever the parent has queued but not yet flushed. The
parent's text then appears after the child's, and the log reads as though the
parent never spoke before the spawn.

Measured, not assumed. Two runs of the same four-line script, stdout piped:

    print("PARENT-BEFORE"); subprocess.run([...])   -> CHILD, PARENT-BEFORE
    print("PARENT-BEFORE"); flush; subprocess.run() -> PARENT-BEFORE, CHILD

``test_unflushed_spawn_reorders_output`` runs both halves as the isolating
negative control, so this guard cannot outlive the defect it describes.

Issue #3742 reported the symptom as destroyed bytes: a PR-creation failure
whose ``gh`` error was missing from the captured log entirely. That diagnosis
was wrong, and the correction matters for anyone reading this guard later.
Both runs above emit the same 33 bytes. Nothing is lost. The reporter's
reproduction ended in ``tail -4``, and reordering had moved the ``gh`` error
above that window. The defect is real, the fix is the same, and the cost is
real: a transient ``Head ref must be a branch`` error was misread as a failed
push because of it. But it is reordering, not destruction.

The rule enforced here is unconditional: flush before *every* fd-inheriting
spawn, whether or not a preceding write to stdout is visible at the call site.
Two earlier scans tried the conditional rule and disagreed with each other.
One walked ``print`` calls and missed output emitted through a helper such as
``_color_print``. The other scoped to the enclosing function and missed a
caller that printed before invoking the callee that spawns. Neither is a bug
in the scan; "has anything reached stdout by now" is not decidable from a call
site. Flushing an empty buffer costs nothing, so the unconditional rule is
both cheaper to obey and the only one a guard can actually verify.

Only ``sys.stdout`` is flushed. ``sys.stderr`` is line-buffered even when
piped (``sys.stderr.line_buffering`` is ``True`` while ``sys.stdout``'s is
``False``), so it holds at most a partial trailing line and needs no help.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Trees this repository authors. Generated mirrors are excluded because their
# source is checked here and a duplicate failure names the wrong file to edit.
_SCANNED_DIRS = (
    ".claude/skills",
    ".claude-mem/scripts",
    ".codeql/scripts",
    ".github/scripts",
    "scripts",
)

_SPAWN_ATTRS = frozenset({"run", "call", "check_call", "check_output", "Popen"})

# Deliberately vulnerable fixtures for the security benchmarks. They exist to
# be scanned by the CWE detectors, and editing them changes what those
# detectors are measured against.
_ALLOWLIST = frozenset(
    {
        ".agents/security/benchmarks/vulnerable_samples/cwe77_command_injection.py",
    }
)


def _subprocess_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Collect module aliases and directly imported spawn names.

    ``import subprocess as sp`` and ``from subprocess import run`` are both
    ordinary Python, and an owner check that only knows the literal word
    ``subprocess`` misses each of them.
    """
    modules = {"subprocess"}
    functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SPAWN_ATTRS:
                    functions.add(alias.asname or alias.name)
    return modules, functions


def _is_spawn(call: ast.Call, modules: set[str], functions: set[str]) -> bool:
    """Report whether *call* starts a child process."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return func.value.id in modules and func.attr in _SPAWN_ATTRS
    return isinstance(func, ast.Name) and func.id in functions


def _redirects_stdout(kw: ast.keyword) -> bool:
    """Report whether one keyword proves the child's stdout is redirected.

    Only two keywords can redirect descriptor 1, and each has a spelling that
    is written explicitly yet still inherits:

    * ``capture_output=False`` is the documented default, not a redirect.
    * ``stdout=None`` is likewise the inheriting default.

    ``stderr`` never redirects stdout. ``stderr=subprocess.STDOUT`` points the
    child's stderr AT the inherited descriptor, so it strengthens the case for
    a flush rather than removing it.

    Anything non-literal (``stdout=target``) counts as a redirect. That keeps
    the guard reporting only spawns it can prove inherit.
    """
    if kw.arg == "capture_output":
        return not (isinstance(kw.value, ast.Constant) and kw.value.value is False)
    if kw.arg == "stdout":
        return not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
    return False


def _inherits_stdout(call: ast.Call) -> bool:
    """Report whether the child writes to the parent's own descriptor 1."""
    return not any(_redirects_stdout(kw) for kw in call.keywords)


def _flushes_stdout(node: ast.stmt) -> bool:
    """Report whether *node* flushes stdout.

    Two spellings count. ``sys.stdout.flush()`` is the explicit form. A
    ``print(..., flush=True)`` immediately before the spawn empties the same
    buffer and is already used at ``scripts/ci/install_locked_deps.py``.
    """
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    call = node.value
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "flush":
        return ast.unparse(func).endswith("stdout.flush")
    if isinstance(func, ast.Name) and func.id == "print":
        return any(
            kw.arg == "flush" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            for kw in call.keywords
        )
    return False


def _owning_statement(tree: ast.Module, call: ast.Call) -> ast.stmt | None:
    """Return the innermost statement whose own expressions contain *call*."""
    owner: ast.stmt | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        nested = {
            id(inner)
            for child in ast.iter_child_nodes(node)
            if isinstance(child, ast.stmt)
            for inner in ast.walk(child)
        }
        # Body-bearing statements enclose their children's calls too, so a
        # match only counts when the call is not inside a nested statement.
        if any(id(sub) == id(call) for sub in ast.walk(node)) and id(call) not in nested:
            if owner is None or node.lineno > owner.lineno:
                owner = node
    return owner


def _statement_blocks(tree: ast.AST) -> list[list[ast.stmt]]:
    """Every statement list in the tree, so a predecessor lookup is one pass."""
    blocks: list[list[ast.stmt]] = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and all(isinstance(s, ast.stmt) for s in block):
                blocks.append(block)
    return blocks


def _preceded_by_flush(blocks: list[list[ast.stmt]], owner: ast.stmt) -> bool:
    """True when ``owner``'s immediate predecessor flushes stdout."""
    for block in blocks:
        for index, statement in enumerate(block):
            if statement is owner and index > 0 and _flushes_stdout(block[index - 1]):
                return True
    return False


def _earlier_flush_info(
    blocks: list[list[ast.stmt]], owner: ast.stmt
) -> tuple[int, list[int]] | None:
    """Return (flush_line, intervening_lines) when a non-immediate flush precedes owner.

    Scans backward through the block that contains *owner*. If a stdout flush
    is found before the immediate predecessor, returns the flush's line number
    and the line numbers of every statement between the flush and *owner*.
    Returns ``None`` if no earlier flush exists or if the immediate predecessor
    already flushes stdout (in which case the spawn would have been accepted).
    """
    for block in blocks:
        for index, statement in enumerate(block):
            if statement is not owner:
                continue
            if index == 0:
                return None
            # Skip if the immediate predecessor already flushes (not our case).
            if _flushes_stdout(block[index - 1]):
                return None
            # Scan backward for a flush that is not the immediate predecessor.
            for j in range(index - 2, -1, -1):
                if _flushes_stdout(block[j]):
                    intervening = [block[k].lineno for k in range(j + 1, index)]
                    return (block[j].lineno, intervening)
            return None
    return None


def unflushed_spawn_lines(source: str) -> list[int]:
    """Return line numbers of fd-inheriting spawns with no preceding flush."""
    tree = ast.parse(source)
    modules, functions = _subprocess_names(tree)
    blocks = _statement_blocks(tree)
    offenders: list[int] = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not _is_spawn(call, modules, functions):
            continue
        if not _inherits_stdout(call):
            continue
        owner = _owning_statement(tree, call)
        if owner is None or not _preceded_by_flush(blocks, owner):
            offenders.append(call.lineno)
    return sorted(offenders)


def unflushed_spawn_diagnostics(source: str) -> list[tuple[int, str]]:
    """Return (line, message) pairs for every offending spawn.

    When a stdout flush exists but is not the spawn's immediate predecessor,
    the message names the flush line and every intervening statement so the
    developer knows exactly what to move rather than hunting for the flush.
    """
    tree = ast.parse(source)
    modules, functions = _subprocess_names(tree)
    blocks = _statement_blocks(tree)
    results: list[tuple[int, str]] = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or not _is_spawn(call, modules, functions):
            continue
        if not _inherits_stdout(call):
            continue
        owner = _owning_statement(tree, call)
        if owner is None or not _preceded_by_flush(blocks, owner):
            hint = _earlier_flush_info(blocks, owner) if owner is not None else None
            if hint is not None:
                flush_line, between = hint
                between_str = ", ".join(str(ln) for ln in between)
                msg = (
                    f"line {call.lineno}: flushes stdout at line {flush_line} but "
                    f"line(s) {between_str} run between the flush and the spawn; "
                    f"move sys.stdout.flush() to immediately before line {call.lineno}"
                )
            else:
                msg = f"line {call.lineno}: no preceding sys.stdout.flush() found"
            results.append((call.lineno, msg))
    return sorted(results)


def _scanned_files() -> list[Path]:
    """Every authored Python file in the scanned trees, allowlist removed."""
    found: list[Path] = []
    for directory in _SCANNED_DIRS:
        for path in sorted((_REPO_ROOT / directory).rglob("*.py")):
            relative = path.relative_to(_REPO_ROOT).as_posix()
            if relative in _ALLOWLIST or "/lib/github_core/" in f"/{relative}":
                continue
            found.append(path)
    return found


def test_every_inheriting_spawn_flushes_stdout_first() -> None:
    """No authored spawn may inherit stdout with the parent buffer unflushed."""
    offenders: list[str] = []
    for path in _scanned_files():
        relative = path.relative_to(_REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        for _line, msg in unflushed_spawn_diagnostics(source):
            offenders.append(f"{relative}: {msg}")
    assert offenders == [], (
        "These spawns do not have sys.stdout.flush() immediately before them, "
        "so the child's output may appear ahead of the parent's in any piped "
        "or redirected log. Fix each:\n  " + "\n  ".join(offenders)
    )


def test_the_scan_reaches_the_files_it_claims_to_cover() -> None:
    """A guard over an empty file set passes for the wrong reason."""
    files = _scanned_files()
    assert len(files) > 100, f"expected the authored trees, scanned {len(files)}"
    covered = {p.relative_to(_REPO_ROOT).as_posix() for p in files}
    # One representative per scanned tree, so a mistyped prefix cannot pass.
    for expected in (
        ".claude/skills/github/scripts/pr/new_pr.py",
        ".claude-mem/scripts/export_claude_mem_direct.py",
        ".codeql/scripts/install_codeql_integration.py",
        ".github/scripts/run_with_retry.py",
        "scripts/quality_gate/run_pytest.py",
    ):
        assert expected in covered, f"{expected} escaped the scan"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("import subprocess\nsubprocess.run(['x'])\n", [2], id="bare-inheriting-run"),
        pytest.param(
            "import subprocess, sys\nsys.stdout.flush()\nsubprocess.run(['x'])\n",
            [],
            id="explicit-flush",
        ),
        pytest.param(
            "import subprocess\nprint('hi', flush=True)\nsubprocess.run(['x'])\n",
            [],
            id="print-flush-true",
        ),
        pytest.param(
            "import subprocess\nprint('hi')\nsubprocess.run(['x'])\n",
            [3],
            id="print-without-flush",
        ),
        pytest.param(
            "import subprocess\nprint('hi', flush=False)\nsubprocess.run(['x'])\n",
            [3],
            id="print-flush-false",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], capture_output=True)\n",
            [],
            id="capture-output-redirects",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], capture_output=False)\n",
            [2],
            id="capture-output-false-still-inherits",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], stdout=None)\n",
            [2],
            id="stdout-none-still-inherits",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], stderr=subprocess.PIPE)\n",
            [2],
            id="stderr-redirect-leaves-stdout-inherited",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], stderr=subprocess.STDOUT)\n",
            [2],
            id="stderr-into-stdout-still-inherits",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], capture_output=flag)\n",
            [],
            id="non-literal-capture-output-is-conservative",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], stdout=target)\n",
            [],
            id="non-literal-stdout-is-conservative",
        ),
        pytest.param(
            "import subprocess\nsubprocess.run(['x'], stdout=subprocess.PIPE)\n",
            [],
            id="stdout-redirects",
        ),
        pytest.param("import subprocess as sp\nsp.run(['x'])\n", [2], id="aliased-module"),
        pytest.param("from subprocess import run\nrun(['x'])\n", [2], id="direct-import"),
        pytest.param("from subprocess import run as go\ngo(['x'])\n", [2], id="aliased-function"),
        pytest.param(
            "import subprocess, sys\nsys.stdout.flush()\nx = 1\nsubprocess.run(['y'])\n",
            [4],
            id="flush-not-immediately-before",
        ),
        pytest.param(
            "import subprocess, sys\nsys.stderr.flush()\nsubprocess.run(['x'])\n",
            [3],
            id="stderr-flush-does-not-count",
        ),
        pytest.param(
            "import subprocess, sys\n"
            "def f():\n    sys.stdout.flush()\n    r = subprocess.run(['x'])\n",
            [],
            id="assignment-target-inside-function",
        ),
        pytest.param(
            "import subprocess, sys\nif True:\n    sys.stdout.flush()\n    subprocess.run(['x'])\n",
            [],
            id="inside-if-body",
        ),
        pytest.param(
            "import subprocess\nfor _ in range(2):\n    subprocess.run(['x'])\n",
            [3],
            id="loop-body-unflushed",
        ),
        pytest.param(
            "import subprocess, sys\nsys.stdout.flush()\nsubprocess.Popen(['x'])\n",
            [],
            id="popen-flushed",
        ),
        pytest.param("import subprocess\nsubprocess.Popen(['x'])\n", [2], id="popen-bare"),
    ],
)
def test_detector_recognises_each_shape(source: str, expected: list[int]) -> None:
    """The detector's positive, negative, and evasion cases."""
    assert unflushed_spawn_lines(textwrap.dedent(source)) == expected


def _buffered_python_env() -> dict[str, str]:
    """Return an env where child Python uses ordinary stdio buffering."""
    env = os.environ.copy()
    env.pop("PYTHONUNBUFFERED", None)
    return env


def _run_ordering_probe(flush: bool) -> str:
    """Run a parent that prints then spawns, with stdout piped, and return it."""
    guard = "sys.stdout.flush()\n" if flush else ""
    program = (
        "import subprocess, sys\n"
        "print('PARENT-BEFORE')\n"
        f"{guard}"
        "subprocess.run([sys.executable, '-c', \"print('CHILD')\"], check=False)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_buffered_python_env(),
        timeout=60,
        check=True,
    )
    return completed.stdout


@pytest.mark.parametrize(
    ("source", "spawn_line", "fragment"),
    [
        pytest.param(
            # stdout flush exists but stderr flush is sandwiched between it and
            # the spawn.  Issue 3937: message must name the flush line and the
            # intervening statement.
            "import subprocess, sys\n"
            "sys.stdout.flush()\n"
            "sys.stderr.flush()\n"
            "subprocess.run(['x'])\n",
            4,
            "flushes stdout at line 2 but line(s) 3 run between the flush and the spawn",
            id="stderr-flush-between-stdout-flush-and-spawn",
        ),
        pytest.param(
            # A plain assignment sits between the flush and the spawn.
            "import subprocess, sys\nsys.stdout.flush()\nx = 1\nsubprocess.run(['y'])\n",
            4,
            "flushes stdout at line 2 but line(s) 3 run between the flush and the spawn",
            id="assignment-between-flush-and-spawn",
        ),
        pytest.param(
            # No flush at all: message uses the fallback wording.
            "import subprocess\nsubprocess.run(['x'])\n",
            2,
            "no preceding sys.stdout.flush() found",
            id="no-flush-at-all",
        ),
    ],
)
def test_diagnostic_message_names_intervening_statements(
    source: str, spawn_line: int, fragment: str
) -> None:
    """unflushed_spawn_diagnostics returns a message with actionable context.

    The spawn line must be in the results and the message for that line must
    contain the expected text fragment.  This is the acceptance criterion for
    issue 3937: a flush that is not the spawn's immediate predecessor must not
    produce a generic 'no flush found' message.
    """
    diagnostics = unflushed_spawn_diagnostics(textwrap.dedent(source))
    lines = [ln for ln, _ in diagnostics]
    assert spawn_line in lines, f"expected spawn at line {spawn_line}, got {lines}"
    msgs = [msg for ln, msg in diagnostics if ln == spawn_line]
    assert any(fragment in msg for msg in msgs), (
        f"expected fragment {fragment!r} in diagnostic for line {spawn_line}; got {msgs}"
    )


def test_unflushed_spawn_reorders_output() -> None:
    """The isolating negative control for the whole guard.

    Without the flush the child's line precedes the parent's. With it the
    order is the one a reader expects. Both runs emit the same bytes, which is
    the evidence that the defect is reordering and not loss.
    """
    broken = _run_ordering_probe(flush=False)
    fixed = _run_ordering_probe(flush=True)

    assert broken.split() == ["CHILD", "PARENT-BEFORE"]
    assert fixed.split() == ["PARENT-BEFORE", "CHILD"]
    assert len(broken) == len(fixed), "reordering must not change the byte count"


def test_stdout_is_the_only_stream_that_needs_flushing() -> None:
    """stderr is line-buffered when piped, so the guard's stdout scope holds."""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; print(sys.stdout.line_buffering, sys.stderr.line_buffering)",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=_buffered_python_env(),
        timeout=60,
        check=True,
    )
    assert completed.stdout.split() == ["False", "True"]
