"""Issue 7460: names a code example declares are not unresolved symbols."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from diff_scope_helpers import FENCE, by_symbol, make_repo, mod, run_gate

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
        ("csharp", 'var s = @"\nclass Ghost\n";\nvar g = new Ghost();'),
        ("csharp", 'var s = $@"\n{x} ""q"" class Ghost\n";\nvar g = new Ghost();'),
        ("csharp", 'var s = """\nclass Ghost\n""";\nvar g = new Ghost();'),
        ("csharp", 'var s = """"\n""" class Ghost """\n"""";\nvar g = new Ghost();'),
        ("typescript", "// class Ghost\nconst g = new Ghost();"),
        ("typescript", "const s = `type Ghost`;\nconst g = new Ghost();"),
        ("python", "# class Ghost\ng = Ghost()"),
        ("python", 'doc = """\nclass Ghost:\n"""\ng = Ghost()'),
    ],
    ids=[
        "cs-line",
        "cs-block",
        "cs-string",
        "cs-verbatim",
        "cs-interp-verbatim",
        "cs-raw",
        "cs-raw4",
        "ts-line",
        "ts-template",
        "py-comment",
        "py-doc",
    ],
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


def test_constructor_excerpt_still_flags_its_type(tmp_path: Path) -> None:
    """A constructor with no class line is a claim that the type exists."""
    block = f"{FENCE}csharp\npublic Ghost(int id)\n{{\n    Id = id;\n}}\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + block})

    code, data = run_gate(repo, tmp_path)

    assert code == 10
    assert "Ghost" in by_symbol(data)
    assert data["declared_name_suppressed"] == {}


def test_plain_uses_without_declaration_still_flag(tmp_path: Path) -> None:
    block = f"{FENCE}csharp\nvar o = new Order();\nreturn Customer;\n{FENCE}\n"
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + block})

    code, data = run_gate(repo, tmp_path)

    assert code == 10
    assert {"Order", "Customer"} <= set(by_symbol(data))


@pytest.mark.parametrize(
    ("lang", "code", "expected"),
    [
        ("csharp", "namespace Foo.Bar\n{\n    internal sealed class A {}\n}", {"Foo", "Bar", "A"}),
        # Declarations count only at the start of a statement.
        ("csharp", 'var s = $"{format("class Ghost")}";\nvar g = new Ghost();', set()),
        ("typescript", "const pattern = /class Ghost/;\nconst g = new Ghost();", set()),
        (
            "typescript",
            "export default class Widget {}\nexport abstract class Base {}",
            {"Widget", "Base"},
        ),
        # A conversion operator never declares its target, whatever separates them.
        ("csharp", "public static implicit operator  Ghost(Order o) => new();", set()),
        ("csharp", "public static implicit operator /* target */ Ghost(Order o) => new();", set()),
        ("csharp", "public static implicit operator \t Ghost(Order o) => new();", set()),
        ("csharp", "public int Run(int x) { }", {"Run"}),
        ("csharp", "var o = new Order();", set()),
        ("csharp", "void F<T>() where T : class\nGhost x;", set()),
        ("csharp", "public static implicit operator Ghost(Order o) => new();", set()),
        # A constructor names a type it does not declare.
        ("csharp", "public Order(int id) { }", set()),
        ("csharp", "public Order (int id) { }", set()),
        ("csharp", "internal Ghost(string s) : base(s) { }", set()),
        ("csharp", "protected internal override string ToString() { }", {"ToString"}),
        ("csharp", "public static explicit operator\tGhost(Order o) => new();", set()),
        ("csharp", "public Cooperator Hire(int id) { }", {"Hire"}),
        ("csharp", "public int Id\n{\n    get;\n}", {"Id"}),
        ("javascript", "function\nGhost()", set()),
        ("python", "class A:\n    async def go(self): ...\nx = B()", {"A", "go"}),
        ("typescript", "interface I {}\ntype T = 1\nconst z = new Q()", {"I", "T"}),
        ("typescript", "export type T = 1\ndeclare type U = 2", {"T", "U"}),
        ("typescript", 'import type Ghost from "./g"\nimport { type Spook } from "./s"', set()),
        ("typescript", 'import {\n  type Ghost,\n  type Spook as S,\n} from "./g"', set()),
        ("typescript", 'export {\n  type Ghost,\n} from "./g"', set()),
        ("typescript", "type Pair<T> = [T, T]", {"Pair"}),
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
        ("csharp", "public " * 20000),
        ("csharp", "aaaa " * 20000),
        ("typescript", "export " * 20000),
        ("csharp", '"' + '\\"' * 20000 + "\\"),
        ("csharp", '@"' + '""' * 20000),
        ("csharp", '"""' * 20000),
        ("csharp", '"' * 100000 + "a" + '"' * 99999 + "a"),
        ("typescript", "`" + "\\`" * 20000 + "\\"),
        ("python", "\n" * 40000 + "x"),
    ],
    ids=[
        "cs-modifiers",
        "cs-one-line-modifiers",
        "cs-one-line-tokens",
        "ts-one-line-exports",
        "cs-escaped-quotes",
        "cs-verbatim-quotes",
        "cs-raw-openers",
        "cs-raw-long-runs",
        "ts-template",
        "py-blank-lines",
    ],
)
def test_declared_names_stays_linear_on_crafted_blocks(lang: str, code: str) -> None:
    """A PR-controlled block must not stall the gate (quadratic took 14s at 6000 lines)."""
    start = time.perf_counter()

    mod._declared_names(code, lang)

    assert time.perf_counter() - start < 2.0


def test_summary_and_markdown_reports_name_declared_skips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path, {"doc.md": "# T\n\n" + ORDER_SAMPLE})
    out = tmp_path / "out"
    base = ["--target", str(repo), "--output-dir", str(out)]

    assert mod.main([*base, "--format", "summary"]) == 0
    summary = capsys.readouterr().out
    assert mod.main([*base, "--format", "markdown"]) == 0
    report = (out / "report.md").read_text(encoding="utf-8")

    line = "doc.md: 4 unresolved_symbol skipped because the same code example declares them"
    assert f"Example-declared names: {line}" in summary
    assert "## Example-declared names" in report
    assert f"- {line}" in report
