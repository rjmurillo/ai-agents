"""Every subprocess call that captures text under ``scripts/`` pins its codec.

``subprocess`` with ``text=True`` and no explicit ``encoding`` decodes captured
bytes with ``locale.getpreferredencoding(False)``. That is UTF-8 on the Linux
runners and something else on the Windows runner in this repo's CI matrix.

The tools we shell out to emit raw UTF-8, not escaped ASCII. ``gh`` writes
non-ASCII straight into JSON string values, and ``git`` hands back filesystem
paths, branch names, and commit messages as raw bytes. Decoding those under a
legacy codec does not raise: cp1252 maps almost every byte, so the call
succeeds and returns different characters than the tool wrote. ``json.loads``
accepts the result, so the corruption reaches the caller silently.

This module is the standing guard. It walks the AST rather than the text so a
reformatted call site cannot slip past.

It checks ``encoding`` only. ``errors`` is deliberately left to each call site:
the default is ``strict``, which fails loudly, and a lenient handler would
reintroduce the silent corruption this guard exists to prevent.

The checks below are deliberately conservative, because a guard meant to hold
forever is worth more than any single call site it protects. An adversarial
review found five ways to write a genuinely locale-decoding call that an
earlier, looser version waved through: ``encoding=None``, an aliased or
directly imported ``run``, a non-literal ``text`` or ``capture_output`` flag,
``getoutput`` and its siblings, and ``utf-8-sig``. Each has a case in
``test_detector_closes_the_evasions``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _REPO_ROOT / "scripts"

_CAPTURING_ATTRS = frozenset({"run", "check_output", "Popen"})

# getoutput and getstatusoutput take no capture or text flags. They always
# return decoded text, and their encoding parameter defaults to None.
_ALWAYS_TEXT_ATTRS = frozenset({"getoutput", "getstatusoutput"})

_SUBPROCESS_ATTRS = _CAPTURING_ATTRS | _ALWAYS_TEXT_ATTRS

_PINNED_CODEC = "utf-8"


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    """Return the value node for keyword *name*, or ``None`` when absent."""
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _is_literal_false(node: ast.expr | None) -> bool:
    """Report whether *node* is the literal ``False``."""
    return isinstance(node, ast.Constant) and node.value is False


def _subprocess_names(tree: ast.Module) -> tuple[set[str], dict[str, str]]:
    """Collect the module aliases and directly imported names for subprocess.

    ``import subprocess as sp`` and ``from subprocess import run`` are both
    ordinary Python, and an owner-name check that only knows the literal word
    ``subprocess`` misses each of them.
    """
    modules = {"subprocess"}
    functions: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_ATTRS:
                    functions[alias.asname or alias.name] = alias.name
    return modules, functions


def _target(call: ast.Call, modules: set[str], functions: dict[str, str]) -> str | None:
    """Return the subprocess entry point *call* reaches, or ``None``."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        owner, attr = func.value.id, func.attr
        if owner in modules and attr in _SUBPROCESS_ATTRS:
            return attr
        if owner == "os" and attr == "popen":
            return "os.popen"
    if isinstance(func, ast.Name) and func.id in functions:
        return functions[func.id]
    return None


def _captures_text(call: ast.Call) -> bool:
    """Report whether *call* may decode captured output into ``str``.

    Deliberately conservative. Anything other than a literal ``False`` counts,
    because ``text=1`` and ``capture_output=flag`` both decode at runtime while
    reading as compliant to a check that only recognises ``True``.
    """
    text = _keyword(call, "text")
    legacy = _keyword(call, "universal_newlines")
    if (text is None or _is_literal_false(text)) and (
        legacy is None or _is_literal_false(legacy)
    ):
        return False
    capture = _keyword(call, "capture_output")
    if capture is not None and not _is_literal_false(capture):
        return True
    return _keyword(call, "stdout") is not None or _keyword(call, "stderr") is not None


def _pins_utf8(call: ast.Call) -> bool:
    """Report whether *call* proves its codec is UTF-8 at the call site.

    ``encoding=None`` is an explicit request for the locale codec, a name or
    attribute cannot be resolved statically, and ``utf-8-sig`` quietly strips a
    byte order mark, so only the literal string counts.
    """
    encoding = _keyword(call, "encoding")
    if encoding is None:
        return False
    return isinstance(encoding, ast.Constant) and encoding.value == _PINNED_CODEC


def unpinned_lines(source: str) -> list[int]:
    """Return the line numbers of text-capturing calls that do not pin UTF-8."""
    tree = ast.parse(source)
    modules, functions = _subprocess_names(tree)
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _target(node, modules, functions)
        if target is None:
            continue
        if target == "os.popen":
            # os.popen has no encoding parameter at all, so the only compliant
            # move is to not use it.
            offenders.append(node.lineno)
            continue
        if target not in _ALWAYS_TEXT_ATTRS and not _captures_text(node):
            continue
        if not _pins_utf8(node):
            offenders.append(node.lineno)
    return sorted(offenders)


def _python_sources() -> list[Path]:
    """Return every Python file under ``scripts/``, skipping caches."""
    return [
        path
        for path in sorted(_SCRIPTS_DIR.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]


def test_every_capturing_call_under_scripts_pins_utf8() -> None:
    """No text-capturing subprocess call may inherit the locale's codec."""
    offenders: list[str] = []
    for path in _python_sources():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        offenders.extend(f"{rel}:{line}" for line in unpinned_lines(path.read_text("utf-8")))
    assert offenders == [], (
        "text-capturing subprocess calls must pass encoding=\"utf-8\": "
        + ", ".join(offenders)
    )


def test_the_scan_actually_reaches_files() -> None:
    """Guard the guard: an empty file list would make the policy test vacuous."""
    sources = _python_sources()
    assert len(sources) > 50, f"only found {len(sources)} sources under scripts/"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=True)",
            "capture_output plus text",
        ),
        (
            "import subprocess\nsubprocess.run(['x'], stdout=subprocess.PIPE, text=True)",
            "an explicit stdout pipe",
        ),
        (
            "import subprocess\nsubprocess.check_output(['x'], text=True, stderr=None)",
            "check_output",
        ),
        (
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, universal_newlines=True)",
            "the legacy universal_newlines spelling",
        ),
    ],
)
def test_detector_flags_an_unpinned_call(source: str, why: str) -> None:
    """A detector that never fires would let the policy test pass on anything."""
    assert unpinned_lines(source) == [2], f"missed {why}"


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf-8")',
            "a pinned call is compliant",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True)',
            "no text means bytes, so nothing is decoded",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], text=True)',
            "nothing captured means nothing to decode",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, text=False)',
            "text=False is an explicit bytes request",
        ),
        (
            'import shutil\nshutil.run(["x"], capture_output=True, text=True)',
            "a same-named method on another module is not ours",
        ),
    ],
)
def test_detector_stays_quiet(source: str, why: str) -> None:
    """The guard must not fire on calls that decode nothing."""
    assert unpinned_lines(source) == [], f"false positive on {why}"


def test_detector_reports_every_offender_in_one_file() -> None:
    """A file with several bad calls must surface all of them, not just the first."""
    source = (
        "import subprocess\n"
        "subprocess.run(['a'], capture_output=True, text=True)\n"
        'subprocess.run(["b"], capture_output=True, text=True, encoding="utf-8")\n'
        "subprocess.run(['c'], capture_output=True, text=True)\n"
    )
    assert unpinned_lines(source) == [2, 4]


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding=None)',
            "encoding=None is an explicit request for the locale codec",
        ),
        (
            'from subprocess import run\nrun(["x"], capture_output=True, text=True)',
            "a direct import evades an owner-name check",
        ),
        (
            'import subprocess as sp\nsp.run(["x"], capture_output=True, text=True)',
            "a module alias evades an owner-name check",
        ),
        (
            'from subprocess import check_output as co\nco(["x"], text=True, stdout=1)',
            "a renamed import evades a function-name check",
        ),
        (
            'import subprocess\nsubprocess.getoutput("x")',
            "getoutput always decodes and defaults to encoding=None",
        ),
        (
            'import subprocess\nsubprocess.getstatusoutput("x")',
            "getstatusoutput has the same default",
        ),
        (
            'import os\nos.popen("x")',
            "os.popen decodes with no way to pin a codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding="utf-8-sig")',
            "utf-8-sig silently strips a BOM, so it is not the pinned codec",
        ),
        (
            'import subprocess\n'
            'subprocess.run(["x"], capture_output=True, text=True, encoding=CODEC)',
            "a non-literal encoding cannot be proven to be utf-8",
        ),
        (
            'import subprocess\ncapture = True\n'
            'subprocess.run(["x"], capture_output=capture, text=True)',
            "a variable capture flag still captures",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, text=1)',
            "a truthy non-True literal still selects text mode",
        ),
        (
            'import subprocess\nsubprocess.run(["x"], capture_output=True, text=True, **kw)',
            "splatted keywords cannot prove the codec is pinned",
        ),
    ],
)
def test_detector_closes_the_evasions(source: str, why: str) -> None:
    """Holes found by adversarial review. Each one decodes under the locale codec."""
    assert unpinned_lines(source) != [], f"missed {why}"
