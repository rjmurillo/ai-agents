"""Phase 3 resolves fields and properties an example type declares, in scope.

A member's own declaration is not a use. A bare use resolves only inside the
body of the type that declares it, and an access resolves only through a
proven receiver, so the same name elsewhere stays checkable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scope_helpers import mod, run_cli, unresolved

_ORDER = "class Order { public int Total; }\n"

# --- Positive: declared members ------------------------------------------------


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        (_ORDER + "var o = new Order();\nvar t = o.Total;\n", "csharp"),
        (_ORDER, "csharp"),
        (
            "class Order { public decimal Total { get; set; } }\n"
            "void Run(Order o) { var t = o.Total; }\n",
            "csharp",
        ),
        (
            "class Order {\n    public int Total => 1;\n"
            "    public int Twice() { return Total * 2; }\n}\n",
            "csharp",
        ),
        (
            "public class Order {\n    private static readonly int Limit = 3;\n}\n"
            "var l = Order.Limit;\n",
            "csharp",
        ),
        (
            "class Order { public List<int> Items { get; } }\n"
            "var o = new Order();\nvar n = o.Items;\n",
            "csharp",
        ),
        (
            "struct Point { public int Left; public int Top; }\n"
            "var p = new Point();\nvar s = p.Left + p.Top;\n",
            "csharp",
        ),
        ("class Cart {\n  Total = 0;\n  add() { this.Total += 1; }\n}\n", "typescript"),
        (
            "interface Order { Total: number }\nconst o: Order = load();\nconst t = o.Total;\n",
            "typescript",
        ),
    ],
)
def test_declared_fields_and_properties_are_not_flagged(code: str, lang: str) -> None:
    assert unresolved(code, lang) == set()


# --- Negative: scope isolation and unproven receivers --------------------------


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        (_ORDER + "var t = ghost.Total;\n", "csharp"),
        (_ORDER + "var t = Total;\n", "csharp"),
        (_ORDER + "var b = Make();\nvar t = b.Total;\n", "csharp"),
        ("class A { public int Total; }\nclass B { int F() { return Total; } }\n", "csharp"),
        ("class A { int F() { return Total; } }\n", "csharp"),
        ("class A { void F() { int Total = 1; } int G() { return Total; } }\n", "csharp"),
        ("class A { public int Total; \n", "csharp"),
        ("interface Order { Total: number }\nconst t = other.Total;\n", "typescript"),
    ],
)
def test_out_of_scope_or_unproven_member_uses_stay_flagged(code: str, lang: str) -> None:
    assert "Total" in unresolved(code, lang)


def test_member_scopes_track_declaring_body_and_depth() -> None:
    view = "class A { public int Total; void F() { int Local = 1; } }\nclass B { int Count => 2; }"
    scopes = mod._type_member_scopes(view, "csharp")
    assert [members for _, _, members in scopes] == [{"Total"}, {"Count"}]
    assert view[scopes[0][0] : scopes[0][1]].strip().startswith("public int Total;")


# --- Real CLI -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "exit_code", "expected"),
    [
        (_ORDER + "var o = new Order();\nvar t = o.Total;", 0, set()),
        (_ORDER + "var t = ghost.Total;", 10, {("unresolved_symbol", "Total")}),
    ],
)
def test_cli_declared_members(
    tmp_path: Path, code: str, exit_code: int, expected: set[tuple[str, str]]
) -> None:
    assert run_cli(tmp_path, "csharp", code) == (exit_code, expected)
