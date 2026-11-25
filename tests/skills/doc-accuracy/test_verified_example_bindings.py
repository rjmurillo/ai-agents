"""D14 regression cases for actual declarations and literal boundaries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scope_helpers import run_cli, unresolved


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "public class Cache<TKey, TValue> { public TValue Get(TKey key) => default; }",
            set(),
        ),
        (
            "class Cache<TKey> : Store<TKey> where TKey : MissingConstraint {"
            " TKey Fetch(TKey key) => Other.Fetch(key); }\nTKey Outside;",
            {"Store", "MissingConstraint", "Other", "Fetch", "TKey", "Outside"},
        ),
        (
            "Task<TResult> WithRetry<TResult>(Func<Task<TResult>> op) "
            "where TResult : struct { return op(); }\nWithRetry();",
            set(),
        ),
        (
            "class Worker { TResult Run<TResult>() => default; "
            "MissingType Check() => default; TResult Later() => default; }\nRun();",
            {"MissingType", "TResult", "Run"},
        ),
        ("interface IWorkable { void Work(); }", set()),
        (
            "interface IWorkable { void Work(); }\nclass Other { void Run() { Work(); } }",
            {"Work"},
        ),
        (
            "class Outer { void Work() { } class Nested { void Run() { Work(); } } }",
            {"Work"},
        ),
        ("void Work() { }\nvar variable = new Work();", {"Work"}),
        ("public TValue Get(TKey key)", {"TValue", "TKey"}),
        ("public Task<TResult> Build<TResult>(TResult value)", set()),
        ("public void Dispose() { resource.Dispose(); }", {"Dispose"}),
        ("private const int CompletedStatus = 3;\nif (status == CompletedStatus) { }", set()),
        ("const int Initial = 1, FinalStatus = 2;\nvar x = Initial + FinalStatus;", set()),
        ("const int Status = 3;\nclass Worker { int Run() => Status; }", {"Status"}),
        (
            "if (ready) { const int CompletedStatus = 3; }\nCheck(CompletedStatus);",
            {"Check", "CompletedStatus"},
        ),
        (
            "const int CompletedStatus = UnknownStatus;\nghost.CompletedStatus();",
            {"UnknownStatus", "CompletedStatus"},
        ),
        (
            'var psi = new ProcessStartInfo { FileName = "git", UseShellExecute = false };',
            {"ProcessStartInfo"},
        ),
        (
            "var x = new Factory.Options<ItemType>(Make()) {"
            " Inner = { Name = MissingValue }, Callback = () => { FakeKey = Ghost; } };",
            {"Factory", "Options", "ItemType", "Make", "MissingValue", "FakeKey", "Ghost"},
        ),
        (
            "var x = new Unresolved { Name = Ghost.Name, Member = new Member() };",
            {"Unresolved", "Ghost", "Name", "Member"},
        ),
        ("if (ready) { FileName = Value; }", {"FileName", "Value"}),
        (
            "void Configure<TType>() where TType : IExisting, new() { FakeKey = Ghost; }",
            {"IExisting", "FakeKey", "Ghost"},
        ),
        (
            "var buffer = ArrayPool<byte>.Shared.Rent(16); Interlocked.Increment(ref n);",
            {"ArrayPool", "Shared", "Rent", "Interlocked", "Increment"},
        ),
        ("foreach (var item in items) { var s = item.ToString(); }", {"ToString"}),
    ],
)
def test_csharp_example_bindings(code: str, expected: set[str]) -> None:
    assert unresolved(code, "csharp") == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("const rules = [{ pattern: /design|ADR/i }];", set()),
        (r"const pattern = /[A-Z/]+\/GhostWidget/g; MissingWidget();", {"MissingWidget"}),
        (
            "const ratio = Numerator / /* Comment */ Divisor / Factor;",
            {"Numerator", "Divisor", "Factor"},
        ),
        ("const ratio = 'Text' / Divisor / Factor;", {"Divisor", "Factor"}),
        ("const ratio = total /* comment */ / Divisor / Factor;", {"Divisor", "Factor"}),
        (
            "interface Result { return: number }; declare const value: Result;\n"
            "const ratio = value.return / Divisor / Factor;",
            {"Divisor", "Factor"},
        ),
        ("const ratio = of / Divisor / Factor;", {"Divisor", "Factor"}),
        ("const ratio = value! / Divisor / Factor;", {"Divisor", "Factor"}),
        ("const found = /* comment */ /Pattern/.test(input) && Neighbor();", {"Neighbor"}),
        ("if (ready) /Pattern/.test(input); Neighbor();", {"Neighbor"}),
        ("const half = (total + 1) / Divisor / Factor;", {"Divisor", "Factor"}),
        ("const pattern = /Unterminated\nNeighbor();", {"Unterminated", "Neighbor"}),
        ("const rx = /class HiddenType/; new HiddenType();", {"HiddenType"}),
        ("const handler = make(); export { handler as GET, handler as POST };", set()),
        ("export { MissingHandler as GET }; GET();", {"MissingHandler", "GET"}),
        ("const data = { GET: Handler }; export { data as GET };", {"GET", "Handler"}),
        ("import { make as Builder } from './tools'; Builder();", set()),
        ("import { make as Builder } from './tools'; export { Builder as GET };", set()),
        (
            "import { make as Builder } from './tools'; export { Builder as GET } from './other';",
            {"Builder"},
        ),
        ("import { make as Builder } from\nBuilder();", {"Builder"}),
        ("import { make as Builder } from './tools'; new Builder();", {"Builder"}),
        ("import { make as Builder } from './tools'; Builder.Run();", {"Run"}),
        (
            "import { RealFactory as Builder } from 'external'; ghost.Builder();",
            {"RealFactory", "Builder"},
        ),
        (
            "import type { Heading } from 'mdast'; function f(node: Heading) { return node; }",
            {"Heading"},
        ),
    ],
)
def test_typescript_example_bindings(code: str, expected: set[str]) -> None:
    assert unresolved(code, "typescript") == expected


def test_cli_keeps_constructor_and_exports_only_real_references(tmp_path: Path) -> None:
    assert run_cli(
        tmp_path, "csharp", "var x = new MissingOptions { FileName = UnresolvedValue };"
    ) == (10, {("unresolved_symbol", "MissingOptions"), ("unresolved_symbol", "UnresolvedValue")})
    assert run_cli(
        tmp_path, "typescript", "const handler = make(); export { handler as GET }; /Pattern/;"
    ) == (0, set())


def test_cli_repo_type_only_import(tmp_path: Path) -> None:
    (tmp_path / "types.ts").write_text(
        "export interface Heading { title: string }\n", encoding="utf-8"
    )
    assert run_cli(
        tmp_path, "typescript", "import type { Heading } from './types'; const x: Heading = load();"
    ) == (0, set())


def test_cli_csharp_method_declaration_does_not_resolve_another_fence(tmp_path: Path) -> None:
    code = (
        "public void Process() { }\n```\n\n```csharp\n"
        "void Run(UnresolvedInterface payment) { payment.Process(); }"
    )
    assert run_cli(tmp_path, "csharp", code) == (
        10,
        {("unresolved_symbol", "UnresolvedInterface"), ("unresolved_symbol", "Process")},
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("from modes import Level\nvalue = Level.FAST", set()),
        ("from modes import (\n    Level as Setting,\n)\nvalue = Setting.FAST", set()),
        ("from modes import Level as Setting\nvalue = Setting.UNKNOWN", {"UNKNOWN"}),
        ("from missing import Level as Setting\nvalue = Setting.FAST", {"Setting", "FAST"}),
        (
            "from modes import Missing as Setting\nvalue = Setting.FAST",
            {"Missing", "Setting", "FAST"},
        ),
        ("from modes import Level\nLevel = object()\nvalue = Level.FAST", {"FAST"}),
        ("from modes import Level\nimport missing as Level\nvalue = Level.FAST", {"FAST"}),
        ("from modes import Level\nfrom missing import *\nvalue = Level.FAST", {"FAST"}),
        ("from modes import Level\ndef f(Level):\n    return Level.FAST", {"FAST"}),
        ("from modes import Level\ndef f():\n    return Level.FAST", set()),
        ("from modes import Level\nvalue = (Level.FAST, ghost.FAST)", {"FAST"}),
        ("from modes import Level\nvalue = Level.FAST.OTHER", {"OTHER"}),
        ("from modes import Level\nvalue = Level.CONDITIONAL", {"CONDITIONAL"}),
        (
            "if enabled:\n    from modes import Level as Setting\nvalue = Setting.FAST",
            {"Setting", "FAST"},
        ),
        ("from modes import NotAClass\nvalue = NotAClass.FAST", {"FAST"}),
        ("value = Level.FAST", {"FAST"}),
        ("value = re.MULTILINE", {"MULTILINE"}),
    ],
)
def test_cli_python_class_import_bindings(tmp_path: Path, code: str, expected: set[str]) -> None:
    (tmp_path / "modes.py").write_text(
        "from enum import Enum\n\n"
        "class Level(Enum):\n"
        "    FAST = 'fast'\n"
        "    if enabled:\n"
        "        CONDITIONAL = 'conditional'\n\n"
        "def NotAClass():\n"
        "    return Level\n",
        encoding="utf-8",
    )
    assert run_cli(tmp_path, "python", code) == (
        10 if expected else 0,
        {("unresolved_symbol", name) for name in expected},
    )


def test_cli_python_resolves_the_qualified_module(tmp_path: Path) -> None:
    package = tmp_path / "src" / "config"
    package.mkdir(parents=True)
    (package / "modes.py").write_text("class Options:\n    StartMode = 'on'\n", encoding="utf-8")
    (tmp_path / "modes.py").write_text("class Options:\n    StopMode = 'off'\n", encoding="utf-8")
    code = "from config.modes import Options as Settings\nvalue = Settings.StartMode"
    assert run_cli(tmp_path, "python", code) == (0, set())
    assert run_cli(tmp_path, "python", code.replace("StartMode", "StopMode")) == (
        10,
        {("unresolved_symbol", "StopMode")},
    )
