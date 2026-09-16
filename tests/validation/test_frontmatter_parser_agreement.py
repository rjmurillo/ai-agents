#!/usr/bin/env python3
r"""The cross-parser agreement issue #5275 asks for, as a standing gate.

Acceptance criterion 2 of that issue: "A regression test proving the specific
case above (a closing fence with exactly one trailing space) behaves identically
across `check_adr_lifecycle.py`, `detect_adr_changes.py`, and
`generate_adr_index.py`."

This is that test, widened to the ten fence shapes the buy-vs-build evaluation
measured (`.agents/analysis/frontmatter-parser-build-vs-buy.md`). Before the
migration the three disagreed on six of them.

It spans a packaging boundary on purpose. `detect_adr_changes.py` ships inside a
plugin root and may import only the standard library and yaml
(`.claude/rules/plugin-self-containment.md`), so it mirrors
`python-frontmatter`'s boundary rather than importing it, while the other two
delegate to `scripts/validation/frontmatter_contract.py`. Two implementations,
one contract. This test is what proves they agree; the parity test in
`tests/skills/adr-review/test_detect_adr_changes.py` is what proves the mirrored
pattern has not drifted. Neither substitutes for the other: a pattern can match
and the surrounding logic still differ.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (str(REPO_ROOT), str(REPO_ROOT / "build" / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _load(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relative)
    if spec is None or spec.loader is None:  # pragma: no cover - import plumbing
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adr_index = importlib.import_module("generate_adr_index")
lifecycle = _load("_agree_lifecycle", "scripts/validation/check_adr_lifecycle.py")
detect = _load("_agree_detect", ".claude/skills/adr-review/scripts/detect_adr_changes.py")

FRONTMATTER = "id: ADR-999\nstatus: accepted"

# (label, text, block is readable)
CASES: list[tuple[str, str, bool]] = [
    ("clean", f"---\n{FRONTMATTER}\n---\nBody.\n", True),
    # Issue #5275's headline case: this passed the lifecycle gate and crashed
    # the index build.
    ("closing fence with one trailing space", f"---\n{FRONTMATTER}\n--- \nBody.\n", True),
    ("closing fence with a tab", f"---\n{FRONTMATTER}\n---\t\nBody.\n", True),
    ("four dashes", f"---\n{FRONTMATTER}\n----\nBody.\n", True),
    ("opening fence padded", f"--- \n{FRONTMATTER}\n---\nBody.\n", True),
    ("crlf", f"---\r\n{FRONTMATTER}\r\n---\r\nBody.\r\n", True),
    ("closing fence at EOF", f"---\n{FRONTMATTER}\n---", True),
    ("trailing text after fence", f"---\n{FRONTMATTER}\n--- nope\nBody.\n", False),
    ("no closing fence", f"---\n{FRONTMATTER}\nBody.\n", False),
    ("BOM before opening fence", f"﻿---\n{FRONTMATTER}\n---\nBody.\n", False),
]


def _index_reads_block(text: str) -> bool:
    try:
        mapping, _body = adr_index.parse_frontmatter(text, Path("ADR-999-x.md"))
    except adr_index.AdrIndexError:
        return False
    return bool(mapping)


def _lifecycle_reads_block(text: str) -> bool:
    raw, _body = lifecycle._split_frontmatter(text)
    return bool(raw)


def _detect_reads_block(text: str) -> bool:
    raw, _body = detect._split_frontmatter(text)
    return bool(raw)


@pytest.mark.parametrize(("label", "text", "readable"), CASES, ids=[c[0] for c in CASES])
def test_all_three_parsers_agree(label: str, text: str, readable: bool) -> None:
    """Every ADR-adjacent parser reaches the same verdict on the same bytes."""
    verdicts = {
        "generate_adr_index": _index_reads_block(text),
        "check_adr_lifecycle": _lifecycle_reads_block(text),
        "detect_adr_changes": _detect_reads_block(text),
    }
    assert len(set(verdicts.values())) == 1, f"{label}: parsers disagree: {verdicts}"
    assert all(v is readable for v in verdicts.values()), f"{label}: expected {readable}"


def test_the_exact_issue_5275_input_no_longer_splits_the_gates() -> None:
    """Named separately so a failure cites the issue rather than a parametrised id.

    The report: "the same corpus can pass the lifecycle gate while breaking the
    generated index build, on a change a human author would not obviously notice
    (one trailing space)."
    """
    text = "---\nid: ADR-999\nstatus: accepted\n--- \nBody text here.\n"

    mapping, _body = adr_index.parse_frontmatter(text, Path("ADR-999-x.md"))
    assert mapping == {"id": "ADR-999", "status": "accepted"}

    raw, _ = lifecycle._split_frontmatter(text)
    assert raw is not None and "status: accepted" in raw

    detected, _ = detect._split_frontmatter(text)
    assert "status: accepted" in detected


def test_the_parsers_still_agree_on_rejecting_a_forged_close() -> None:
    """Loosening the fence must not have made every line a close.

    `--- nope` is the one slip that signals a real authoring mistake rather than
    an editor artifact, and all three still refuse to read it as a fence.
    """
    text = f"---\n{FRONTMATTER}\n--- nope\nBody.\n"
    assert _index_reads_block(text) is False
    assert _lifecycle_reads_block(text) is False
    assert _detect_reads_block(text) is False
