"""Phase 3 treats C#, TypeScript, and JavaScript literals and comments as data.

A name that appears only inside an ordinary string, a character literal, or
a comment is not a repository API claim. Interpolation holes are code, so a
name inside one stays checkable. Raw extraction already drops C# string
text; Phase 3 filters every C-family literal and comment again.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scope_helpers import mod, run_cli, unresolved

# --- Positive: names only inside literals or comments are data -----------------


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        ('string message = "GhostWidget";\n', "csharp"),
        ('var path = @"C:\\GhostWidget\\";\n', "csharp"),
        ('var s = @"say ""GhostWidget"" twice";\n', "csharp"),
        ('var json = """\n{ "kind": "GhostWidget" }\n""";\n', "csharp"),
        ("char c = 'G';\nvar s = \"Ghost Widget\";\n", "csharp"),
        ('var s = $"{count} GhostWidget items";\n', "csharp"),
        ('var s = $$"""{ "GhostWidget": {{count}} }""";\n', "csharp"),
        ("/* GhostWidget */\nvar x = 1;\n", "csharp"),
        ('const state: "MUST" | "SHOULD" = "MUST";\n', "typescript"),
        ("const s = 'GhostWidget';\n", "typescript"),
        ("const t = `GhostWidget ${count}`;\n", "typescript"),
        ('const t = `${a ? "GhostWidget" : "Other"}`;\n', "javascript"),
        ("// GhostWidget is mentioned here\nconst x = 1;\n", "javascript"),
    ],
)
def test_literal_and_comment_only_names_are_not_flagged(code: str, lang: str) -> None:
    assert unresolved(code, lang) == set()


def test_raw_extraction_drops_csharp_string_only_mentions() -> None:
    ids = mod._extract_identifiers('var s = "GhostWidget"; var w = new FakeWidget();', "csharp")

    assert "GhostWidget" not in ids
    assert "FakeWidget" in ids


# --- Negative: interpolation holes and real code stay checkable ----------------


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        ('var s = $"{new GhostWidget()}";\n', "csharp"),
        ('var s = $@"C:\\{new GhostWidget()}";\n', "csharp"),
        ('var s = @$"C:\\{new GhostWidget()}";\n', "csharp"),
        ('var s = $"""\n{new GhostWidget()}\n""";\n', "csharp"),
        ('var s = $$"""{ "a": {{new GhostWidget()}} }""";\n', "csharp"),
        ('var s = $"{Make("x")} and {new GhostWidget()}";\n', "csharp"),
        ("const t = `outer ${`inner ${new GhostWidget()}`}`;\n", "typescript"),
        ("const t = `a ${new GhostWidget()} b`;\n", "javascript"),
        ('var text = "GhostWidget";\nnew GhostWidget();\n', "csharp"),
        ('const s = "GhostWidget"; GhostWidget();\n', "typescript"),
    ],
)
def test_names_in_code_or_holes_stay_flagged(code: str, lang: str) -> None:
    assert "GhostWidget" in unresolved(code, lang)


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        ('var s = "unterminated GhostWidget\nvar y = 2;\n', "csharp"),
        ("/* GhostWidget never closes\n", "csharp"),
        ("const s = 'GhostWidget\n", "typescript"),
        ("const t = `GhostWidget ${x\n", "typescript"),
    ],
)
def test_unterminated_literals_stay_visible_as_code(code: str, lang: str) -> None:
    assert "GhostWidget" in unresolved(code, lang)


# --- JavaScript and TypeScript regex literals ------------------------------------


@pytest.mark.parametrize(
    "code",
    [
        'const pattern = /"/; const text = "GhostWidget";\n',
        "const quote = /['\"]/g; const s = 'GhostWidget';\n",
        'const slash = /\\/"/; const s = "GhostWidget";\n',
        'const t = `${/"/.test(s) ? "GhostWidget" : ""}`;\n',
        'const ok = (s) => /"/.test(s) && "GhostWidget";\n',
    ],
)
def test_regex_quotes_do_not_unbalance_later_literals(code: str) -> None:
    assert unresolved(code, "typescript") == set()


@pytest.mark.parametrize(
    "code",
    [
        'const pattern = /"/; GhostWidget(); const text = "ok";\n',
        's.replace(/["/]/g, \'\'); GhostWidget(); const t = "ok";\n',
        'function f(s) { return /"/.test(s) && GhostWidget(); }\n',
        'const t = `${/"/.test(s)} ${new GhostWidget()}`;\n',
        'const half = total / 2; const s = "a/b"; GhostWidget(); const t = "ok";\n',
    ],
)
def test_code_beside_regex_and_division_stays_flagged(code: str) -> None:
    assert "GhostWidget" in unresolved(code, "javascript")


def test_literal_filter_does_not_cross_into_python() -> None:
    assert unresolved('x = "GhostWidget"\nGhostWidget()\n', "python") == {"GhostWidget"}


def test_code_view_preserves_lengths_and_newlines() -> None:
    code = 'var a = $"x{b}y";\n// note\nvar c = @"p\nq";\n'
    view = mod._c_family_code_view(code, "csharp")
    assert len(view) == len(code)
    assert view.count("\n") == code.count("\n")
    hole = code.index("{b}") + 1
    assert view[hole] == "b"
    assert "x" not in view.split("\n")[0]
    assert "note" not in view
    assert "p" not in view.split("\n")[2]


# --- Real CLI -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "code", "exit_code", "expected"),
    [
        ("csharp", 'string message = "GhostWidget";', 0, set()),
        ("typescript", 'const state: "MUST" | "SHOULD" = "MUST";', 0, set()),
        (
            "csharp",
            'var s = $"{new GhostWidget()}";',
            10,
            {("unresolved_symbol", "GhostWidget")},
        ),
        (
            "typescript",
            "const t = `${new GhostWidget()}`;",
            10,
            {("unresolved_symbol", "GhostWidget")},
        ),
        (
            "csharp",
            'var widget = new ExistingWidget();\nwidget.Configure("a: b", wrong: 1);',
            10,
            {("phantom_parameter", "")},
        ),
        ("csharp", 'var widget = new ExistingWidget();\nwidget.Configure("wrong: 1");', 0, set()),
        (
            "javascript",
            'const p = /"/; GhostWidget(); const t = "ok";',
            10,
            {("unresolved_symbol", "GhostWidget")},
        ),
        ("javascript", 'const p = /"/; const t = "GhostWidget";', 0, set()),
    ],
)
def test_cli_gates_on_code_not_literals(
    tmp_path: Path, lang: str, code: str, exit_code: int, expected: set[tuple[str, str]]
) -> None:
    assert run_cli(tmp_path, lang, code) == (exit_code, expected)


# --- Negative: an unreadable snippet stays raw, in bounded time ----------------


@pytest.mark.parametrize(
    "code",
    [
        'x = $"{a\n' * 300 + "var y = 1;\n" * 20000 + 'var s = "class FakeWidget";',
        '$"{' * 2000 + 'var s = "class FakeWidget";' + '}"' * 2000,
    ],
    ids=["unclosed-holes", "deep-nesting"],
)
def test_unreadable_snippet_keeps_raw_text_and_declares_nothing(code: str, caplog) -> None:
    literal_ends: set[int] = set()

    with caplog.at_level("WARNING"):
        view = mod._c_family_code_view(code, "csharp", literal_ends=literal_ends)
        declared = mod._example_declaration_names(code, "csharp")

    assert view == code
    assert literal_ends == set()
    assert "FakeWidget" not in declared
    assert "gave up on the snippet" in caplog.text


def test_readable_snippet_still_declares_its_types() -> None:
    declared = mod._example_declaration_names(
        'class LocalThing {}\nvar s = "class FakeWidget";', "csharp"
    )

    assert "LocalThing" in declared
    assert "FakeWidget" not in declared


def test_open_block_comments_strip_in_linear_time() -> None:
    code = "/* BlockNote */ " + '$"{/*\n' * 40000 + "Real.Go(); // TrailNote"
    started = time.monotonic()

    stripped = mod._strip_csharp_comments(code)

    assert time.monotonic() - started < 2
    assert "BlockNote" not in stripped
    assert stripped.count("/*") == 40000
    assert "Real.Go();" in stripped
    assert "TrailNote" not in stripped


def test_closed_block_comment_and_strings_keep_their_handling() -> None:
    code = 'Keep("/* not */"); /* Gone */ Next(); /*/ open'

    stripped = mod._strip_csharp_comments(code)

    assert '"/* not */"' in stripped
    assert "Gone" not in stripped
    assert "Next();" in stripped
    assert stripped.endswith("/*/ open")
