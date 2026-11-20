"""Issue 7460: balanced fence edits and self-declared types must not gate."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import (
    FENCE,
    by_symbol,
    edit_and_commit,
    example,
    gate_diff,
    make_repo,
    mod,
    run_gate,
)

BALANCED_BLOCK = f"new text\n\n{FENCE}bash\necho hi\n{FENCE}\n\n"
BASE_DOC = "# T\n\nintro\n\n" + example("Ghost")
MARKER = "<!-- doc-accuracy: external-sdk Foo -- vendored -->\n"

ORDER_SAMPLE = f"""{FENCE}csharp
namespace Demo;

internal partial class Order
{{
    public int Id {{ get; init; }}
}}

internal partial class Order
{{
    public string? Customer {{ get; init; }}
}}
{FENCE}
"""


def _insert_above_example(doc: str, text: str) -> str:
    return doc.replace("intro\n\n", "intro\n\n" + text, 1)


def test_balanced_block_above_untouched_example_stays_info(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": BASE_DOC})
    edit_and_commit(repo, "doc.md", _insert_above_example(BASE_DOC, BALANCED_BLOCK))

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 0
    assert ghost["severity"] == "info"
    assert ghost["in_diff"] is False


def test_single_added_fence_above_example_still_blocks(tmp_path: Path) -> None:
    # The lone fence re-pairs the file: prose once inside the skipped bash
    # block becomes a claim, and it is not on a changed line.
    base = f"# T\n\n{FENCE}bash\necho hi\nmethod accepts `Ghost`\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("# T\n\n", f"# T\n\n{FENCE}\n", 1))

    code, data = gate_diff(repo, tmp_path)

    assert code == 10
    assert by_symbol(data)["Ghost"]["in_diff"] is True


def test_balanced_block_above_honored_marker_keeps_findings_in_scope(tmp_path: Path) -> None:
    base = "# T\n" + MARKER + "\n" + example("Ghost")
    head = base.replace("# T\n", "# T\n\n" + BALANCED_BLOCK, 1)
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", head)

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 10
    assert ghost["in_diff"] is True
    assert ghost["scope_reason"] == "ignored_external_sdk_marker"
    assert ghost["scope_marker_line"] == head.split("\n").index(MARKER.rstrip("\n")) + 1


def test_prose_edit_above_already_ignored_marker_stays_info(tmp_path: Path) -> None:
    """A marker below a fence was ignored at the base too; prose cannot flip it."""
    base = f"# T\n\nintro\n\n{FENCE}bash\necho hi\n{FENCE}\n\n" + MARKER + "\n" + example("Ghost")
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("intro", "intro two", 1))

    code, data = gate_diff(repo, tmp_path)

    ghost = by_symbol(data)["Ghost"]
    assert code == 0
    assert ghost["in_diff"] is False
    assert "scope_reason" not in ghost


def test_edited_stop_line_above_ignored_marker_keeps_findings_in_scope(tmp_path: Path) -> None:
    """Editing the first fence-like line above the marker can flip its status."""
    base = f"# T\n\nuse {FENCE} here\n\n" + MARKER + "\n" + example("Ghost")
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace(f"use {FENCE} here", f"use {FENCE} there", 1))

    code, data = gate_diff(repo, tmp_path)

    assert code == 10
    assert by_symbol(data)["Ghost"]["scope_reason"] == "ignored_external_sdk_marker"


def test_prose_edit_below_example_keeps_marker_honored(tmp_path: Path) -> None:
    base = "# T\n" + MARKER + "\n" + example("Ghost") + "\ntail\n"
    repo = make_repo(tmp_path, {"doc.md": base})
    edit_and_commit(repo, "doc.md", base.replace("tail", "tail two"))

    code, data = gate_diff(repo, tmp_path)

    assert code == 0
    assert not [f for f in data["findings"] if f["severity"] != "info"]


def test_sample_declaring_its_own_types_has_no_unresolved_symbols(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + ORDER_SAMPLE})

    code, data = run_gate(repo, tmp_path)

    assert code == 0
    assert [f for f in data["findings"] if f["category"] == "unresolved_symbol"] == []
    # Demo, Order, Id, and Customer: every skip is counted, not silent.
    assert data["declared_name_suppressed"] == {"doc.md": 4}


@pytest.mark.parametrize(
    ("lang", "block"),
    [
        ("csharp", "// this class Ghost is from the repo\nvar g = new Ghost();"),
        ("csharp", "/* interface Ghost */\nvar g = new Ghost();"),
        ("csharp", 'var s = "class Ghost";\nvar g = new Ghost();'),
        ("typescript", "// class Ghost\nconst g = new Ghost();"),
        ("typescript", "const s = `type Ghost`;\nconst g = new Ghost();"),
        ("python", "# class Ghost\ng = Ghost()"),
        ("python", 'doc = """\nclass Ghost:\n"""\ng = Ghost()'),
    ],
    ids=["cs-line", "cs-block", "cs-string", "ts-line", "ts-template", "py-comment", "py-doc"],
)
def test_declaration_keyword_in_comment_or_string_declares_nothing(
    tmp_path: Path, lang: str, block: str
) -> None:
    doc = f"# T\n\n{FENCE}{lang}\n{block}\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": doc})

    code, data = run_gate(repo, tmp_path)

    assert code == 10
    assert "Ghost" in by_symbol(data)
    assert data["declared_name_suppressed"] == {}


def test_undeclared_symbol_in_declaring_block_still_flags(tmp_path: Path) -> None:
    block = (
        f"{FENCE}csharp\nclass Order\n{{\n    void Run() {{ var g = new Ghost(); }}\n}}\n{FENCE}\n"
    )
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + block})

    code, data = run_gate(repo, tmp_path)

    assert code == 10
    assert "Ghost" in by_symbol(data)
    assert "Order" not in by_symbol(data)


def test_plain_uses_without_declaration_still_flag(tmp_path: Path) -> None:
    block = f"{FENCE}csharp\nvar o = new Order();\nreturn Customer;\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + block})

    code, data = run_gate(repo, tmp_path)

    assert code == 10
    assert {"Order", "Customer"} <= set(by_symbol(data))


@pytest.mark.parametrize(
    ("lang", "code", "expected"),
    [
        ("csharp", "namespace Foo.Bar { class A {} }", {"Foo", "Bar", "A"}),
        ("csharp", "public int Run(int x) { }", {"Run"}),
        ("csharp", "var o = new Order();", set()),
        ("python", "class A:\n    async def go(self): ...\nx = B()", {"A", "go"}),
        ("typescript", "interface I {}\ntype T = 1\nconst z = new Q()", {"I", "T"}),
        ("typescript", "export type T = 1\ndeclare type U = 2", {"T", "U"}),
        ("typescript", 'import type Ghost from "./g"\nimport { type Spook } from "./s"', set()),
        ("bash", "class Foo", set()),
    ],
)
def test_declared_names_per_language(lang: str, code: str, expected: set[str]) -> None:
    assert mod._declared_names(code, lang) == expected


def test_method_signature_claims_ignore_declared_names(tmp_path: Path) -> None:
    doc = "# T\n\nconstructor accepts `Ghost`\n\n" + ORDER_SAMPLE
    repo = make_repo(tmp_path, {"doc.md": doc})

    code, data = run_gate(repo, tmp_path)

    assert code == 10
    assert "Ghost" in by_symbol(data)


@pytest.mark.parametrize(
    ("lang", "code"),
    [
        ("csharp", "public a b c\n" * 20000),
        ("csharp", '"' + '\\"' * 20000 + "\\"),
        ("typescript", "`" + "\\`" * 20000 + "\\"),
        ("python", "\n" * 40000 + "x"),
    ],
    ids=["cs-modifiers", "cs-escaped-quotes", "ts-template", "py-blank-lines"],
)
def test_declared_names_stays_linear_on_crafted_blocks(lang: str, code: str) -> None:
    """A PR-controlled block must not stall the gate (quadratic took 14s at 6000 lines)."""
    start = time.perf_counter()

    mod._declared_names(code, lang)

    assert time.perf_counter() - start < 2.0
