"""Phase 3 CLI regressions for symbols hidden by an unrelated binding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scope_helpers import mod


def _scan(tmp_path: Path, lang: str, code: str) -> tuple[int, list[tuple[str, str]]]:
    (tmp_path / "validator.cs").write_text(
        "public class Validator {\n    public void Validate(int timeout) { }\n}\n"
        "public class OtherValidator { }\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(f"```{lang}\n{code}\n```\n", encoding="utf-8")
    output = tmp_path / ".doc-accuracy"
    exit_code = mod.main(["--target", str(tmp_path), "--output-dir", str(output)])
    report = json.loads((output / "compilability-findings.json").read_text(encoding="utf-8"))
    return exit_code, [
        (finding["category"], finding["evidence"].get("symbol", ""))
        for finding in report["findings"]
    ]


@pytest.mark.parametrize(
    ("lang", "bound", "unbound", "symbol"),
    [
        (
            "csharp",
            'string text = "";\ntext.ToString();',
            'dynamic other = "";\nother.ToString();',
            "ToString",
        ),
        (
            "csharp",
            "void First(string value) { value.ToString(); }",
            "void Second(dynamic value) { value.ToString(); }",
            "ToString",
        ),
        (
            "csharp",
            'string text = "";\ntext.ToString();',
            "dynamic other = new Object();\nother.ToString();",
            "ToString",
        ),
        (
            "typescript",
            "const date = new Date();\ndate.getTime();",
            "declare const other: any;\nother.getTime();",
            "getTime",
        ),
        (
            "typescript",
            "function first(value: Date) { value.getTime(); }",
            "function second(value: any) { value.getTime(); }",
            "getTime",
        ),
        (
            "typescript",
            "const date = new Date();\ndate.getTime();",
            "other.missingProperty;",
            "missingProperty",
        ),
        (
            "python",
            "import argparse as ap\nap.ArgumentParser()",
            "def parse(ap):\n    return ap.ArgumentParser()",
            "ArgumentParser",
        ),
        (
            "python",
            "import argparse as ap\nap.ArgumentParser()",
            "ap = object()\nap.ArgumentParser()",
            "ArgumentParser",
        ),
        (
            "csharp",
            "var validator = new Validator();\nvalidator.Validate(timeout: 1);",
            "receiver.Validate();",
            "Validate",
        ),
        (
            "csharp",
            "var validator = new Validator();\nvalidator.Validate(timeout: 1);",
            "var receiver = new OtherValidator();\nreceiver.Validate(wrong: 1);",
            "Validate",
        ),
    ],
    ids=[
        "csharp-dynamic",
        "csharp-scoped-dynamic",
        "csharp-constructed-dynamic",
        "typescript-any",
        "typescript-scoped-any",
        "typescript-property",
        "python-shadowed-alias",
        "python-reassigned-alias",
        "csharp-repo-name",
        "csharp-wrong-repo-owner",
    ],
)
def test_only_unbound_use_fails(
    tmp_path: Path, lang: str, bound: str, unbound: str, symbol: str
) -> None:
    assert _scan(tmp_path, lang, bound) == (0, [])
    assert _scan(tmp_path, lang, f"{bound}\n{unbound}") == (
        10,
        [("unresolved_symbol", symbol)],
    )


def test_bound_repo_call_checks_named_parameter(tmp_path: Path) -> None:
    assert _scan(
        tmp_path, "csharp", "var validator = new Validator();\nvalidator.Validate(wrong: 1);"
    ) == (10, [("phantom_parameter", "")])


@pytest.mark.parametrize("namespace", ["", "namespace First;\n", "namespace Other;\n"])
def test_partial_repository_type_keeps_only_unambiguous_members(
    tmp_path: Path, namespace: str
) -> None:
    (tmp_path / "part.cs").write_text(
        f"{namespace}public partial class Validator {{\n    public void Reset() {{ }}\n}}\n",
        encoding="utf-8",
    )
    (tmp_path / "validator.cs").write_text(
        "namespace First;\npublic partial class Validator { }\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        "```csharp\nvar validator = new Validator();\nvalidator.Reset();\n```\n", encoding="utf-8"
    )

    code = mod.main(["--target", str(tmp_path), "--output-dir", str(tmp_path / "out")])

    assert code == (0 if namespace == "namespace First;\n" else 10)


@pytest.mark.parametrize(("parameter", "expected"), [("timeout", 0), ("Validator", 10)])
def test_named_argument_must_match_a_parameter_declaration(
    tmp_path: Path, parameter: str, expected: int
) -> None:
    (tmp_path / "validator.cs").write_text(
        "public class Validator {\n"
        "    public Validator Validate(\n"
        "        Dictionary<string, int> values,\n"
        "        int timeout = 1) => this;\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "```csharp\nvar validator = new Validator();\n"
        f"validator.Validate(null, {parameter}: 1);\n```\n",
        encoding="utf-8",
    )

    assert mod.main(["--target", str(tmp_path), "--output-dir", str(tmp_path / "out")]) == expected
