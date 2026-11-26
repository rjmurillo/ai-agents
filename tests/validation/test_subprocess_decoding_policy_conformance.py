"""Pin how the three subprocess decoding checks handle the same source."""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from scripts.validation import check_subprocess_encoding, io_portability_rules


@pytest.fixture(scope="module")
def encoding_guard() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "test_subprocess_text_encoding.py"
    spec = importlib.util.spec_from_file_location("_decoding_conformance_guard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("codec", "expected"),
    [
        ("utf-8", True),
        ("UTF8", True),
        ("utf_8", True),
        ("u8", True),
        ("utf-8-sig", False),
        ("latin-1", False),
        ("bogus", False),
    ],
)
def test_utf8_codec_predicates(encoding_guard: ModuleType, codec: str, expected: bool) -> None:
    call = ast.parse(f"subprocess.run(cmd, encoding={codec!r})", mode="eval").body
    assert isinstance(call, ast.Call)
    assert check_subprocess_encoding._is_utf8_literal(call.keywords[0].value) is expected
    assert encoding_guard._pins_utf8(call) is expected


_CAPTURE = "text=True, capture_output=True"
_UTF8 = f'{_CAPTURE}, encoding="utf-8"'


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (f"subprocess.run(cmd, {_CAPTURE})", ([], [2], [2])),
        (f"subprocess.run(cmd, {_UTF8})", ([2], [], [])),
        (f'subprocess.run(cmd, {_UTF8}, errors="replace")', ([], [], [])),
        (f'subprocess.run(cmd, {_UTF8}, errors="strict")', ([2], [], [])),
        (
            f'subprocess.run(cmd, {_UTF8}, errors="strict")  '
            "# subprocess-encoding: strict-ok invalid bytes must fail",
            ([], [], []),
        ),
        (f'subprocess.run(cmd, {_CAPTURE}, encoding="UTF8", errors="replace")', ([], [], [])),
        (f'subprocess.run(cmd, {_CAPTURE}, encoding="utf-8-sig")', ([], [2], [])),
        # C checks only that an encoding was supplied, so latin-1 passes.
        (f'subprocess.run(cmd, {_CAPTURE}, encoding="latin-1")', ([], [2], [])),
        ("subprocess.check_output(cmd, text=True)", ([], [2], [2])),
        ('subprocess.check_output(cmd, encoding="utf-8")', ([2], [], [])),
        ("subprocess.getoutput(command)", ([], [2], [])),
        ("os.popen(command)", ([], [2], [])),
        ("def run(kw):\n    subprocess.run(cmd, **kw)", ([3], [3], [])),
        (f"functools.partial(subprocess.run, {_CAPTURE})", ([], [2], [])),
        ("functools.partial(subprocess.run, text=True)", ([], [2], [])),
        (f'run = getattr(subprocess, "run")\nrun(cmd, {_CAPTURE})', ([], [3], [])),
        ("subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)", ([], [2], [2])),
        # Known union gap: the literal True checks miss the captured text=1 form.
        ('subprocess.run(cmd, capture_output=1, text=1, encoding="utf-8")', ([], [], [])),
        # C-only text-mode gap: B intentionally accepts non-False truthy text values.
        ("subprocess.run(cmd, text=1)", ([], [], [])),
        # Entry-point and text-flag differences, descriptive rather than prescriptive.
        (
            'subprocess.check_call(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8")',
            ([2], [], []),
        ),
        (
            'subprocess.call(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8")',
            ([], [], []),
        ),
        ("subprocess.check_call(cmd, stdout=subprocess.PIPE, text=True)", ([], [], [2])),
        ("subprocess.call(cmd, stdout=subprocess.PIPE, text=True)", ([], [], [2])),
        ("subprocess.run(cmd, capture_output=True, universal_newlines=True)", ([], [2], [2])),
        # Known gaps: the union misses the absent errors handler through these aliases.
        (f"functools.partial(subprocess.run, {_UTF8})", ([], [], [])),
        (f'run = getattr(subprocess, "run")\nrun(cmd, {_UTF8})', ([], [], [])),
        (f'ops = {{"run": subprocess.run}}\nops["run"](cmd, {_UTF8})', ([], [], [])),
        # Positive differential: A resolves the class-scope alias while B and C do not.
        (f"class Runner:\n    run = subprocess.run\n    run(cmd, {_UTF8})", ([4], [], [])),
        ('subprocess.run(cmd, text=True, encoding="utf-8")', ([2], [], [])),
        ("subprocess.run(cmd, text=True, encoding=None)", ([], [], [2])),
        ("run = subprocess.run\nrun(cmd, text=True)", ([], [], [])),
        ('subprocess.run(cmd, capture_output=True, errors="ignore")', ([], [2], [])),
        # Negative control: a UTF-8 pin satisfies B even when A flags the handler.
        (f'subprocess.run(cmd, {_UTF8}, errors="ignore")', ([2], [], [])),
    ],
)
def test_decoding_verdicts(
    encoding_guard: ModuleType, body: str, expected: tuple[list[int], list[int], list[int]]
) -> None:
    source = f"import functools, os, subprocess\n{body}\n"
    errors_lines = check_subprocess_encoding.find_violations(source)
    encoding_lines = encoding_guard.unpinned_lines(source)
    portability_lines = [
        finding.line
        for finding in io_portability_rules.scan_source("probe.py", source)
        if finding.rule == "subprocess-text-encoding"
    ]
    assert (errors_lines, encoding_lines, portability_lines) == expected
