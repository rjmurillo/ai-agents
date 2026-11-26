"""Phase 3 must not flag names examples resolve without the repo.

Covers three false-positive classes found in the full documentation scan:
Python plain stdlib imports used through attribute chains, typing names,
and example-local type declarations plus member accesses in C# and
TypeScript snippets.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy_example_locals",
)


def _flagged(
    code: str, lang: str = "python", extra_claims: list[dict[str, Any]] | None = None
) -> set[str]:
    symbol = {
        "name": "ExistingWidget",
        "kind": "class",
        "file": "a.py",
        "line": 1,
        "signature": "class ExistingWidget:",
        "visibility": "public",
    }
    claim: dict[str, Any] = {
        "id": "claim-0001",
        "file": "doc.md",
        "line": 7,
        "type": "code_example",
        "language": lang,
        "content": code,
        "mapped_source": "",
        "symbols_referenced": mod._extract_identifiers(code, lang),
    }
    claims = [claim, *(extra_claims or [])]
    result = mod.run_compilability_check({"source_symbols": [symbol]}, {"claims": claims})
    return {
        f["evidence"]["symbol"] for f in result["findings"] if f["category"] == "unresolved_symbol"
    }


# --- Python: plain stdlib imports and typing names ----------------------------


@pytest.mark.parametrize(
    "code",
    [
        'import argparse\nparser = argparse.ArgumentParser(description="x")\n',
        'import json\ntry:\n    json.loads("x")\nexcept json.JSONDecodeError:\n    pass\n',
        "import xml.etree.ElementTree as ET\ntree = ET.ElementTree()\n",
        "import os, sys\npath = os.PathLike\nprint(sys.maxsize)\n",
        "import argparse as ap\nparser = ap.ArgumentParser()\n",
        "import datetime\nnow = datetime.datetime.now(tz=datetime.UTC)\n",
        "def f(payload: Any) -> Optional[str]:\n    return None\n",
        "from pathlib import Path\nimport typing\nx: typing.ClassVar[int] = 1\n",
    ],
)
def test_stdlib_attribute_chains_and_typing_names_not_flagged(code: str) -> None:
    assert _flagged(code) == set()


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("import mypkg\nx = mypkg.GhostWidget\n", {"GhostWidget"}),
        ("import requests\nr = requests.Response()\n", {"Response"}),
    ],
)
def test_non_stdlib_attribute_names_still_flagged(code: str, expected: set[str]) -> None:
    assert _flagged(code) == expected


def test_stdlib_module_contents_are_not_repo_checked() -> None:
    """The gate checks the repo index, not the stdlib, so chains stay trusted."""
    assert _flagged("import argparse\nx = argparse.GhostParser\n") == set()


def test_stdlib_chain_blanking_is_column_preserving() -> None:
    code = "import json\njson.JSONDecodeError\n"
    blanked = mod._blank_stdlib_attribute_chains(code)
    assert len(blanked) == len(code)
    assert "JSONDecodeError" not in mod._extract_identifiers(code, "python")


# --- C#: example-local declarations and member accesses -----------------------


@pytest.mark.parametrize(
    "code",
    [
        (
            "public class Order { }\n"
            "public class OrderProcessor {\n"
            "    public void Process(Order order) { order.Validate(); }\n"
            "}\n"
        ),
        "class Order { }\nvar order = new Order();\nvar n = order.Items.Count;\n",
        (
            "void Check(IEnumerable<int> input) {\n"
            '    if (input.Any(c => c > 0)) { Console.WriteLine("y"); }\n}\n'
        ),
        'throw new ArgumentException("bad");\n',
        "// Good: denylist\nvar blocked = new[] { '<' };\n// Poor: bypass\n",
        'record Customer(string Name);\nvar c = new Customer("x");\n',
    ],
)
def test_csharp_example_locals_and_member_access_not_flagged(code: str) -> None:
    assert _flagged(code, "csharp") == set()


def test_csharp_declaration_in_another_fence_resolves(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(
        "```csharp\npublic class Order { }\n```\n"
        "Text between fences.\n"
        "```csharp\nvar processor = new OrderProcessor();\n"
        "processor.Process(new Order());\n```\n",
        encoding="utf-8",
    )
    assessment = {
        "documentation_files": [{"path": "doc.md", "mapped_source_files": []}],
        "source_symbols": [],
    }
    claims = mod.run_claim_extraction(tmp_path, assessment)
    by_content = [c for c in claims["claims"] if "OrderProcessor" in c["content"]]
    assert by_content and "Order" not in by_content[0]["symbols_referenced"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("var s = new GhostThing();\n", {"GhostThing"}),
        ("public void Run(MissingType item) { }\n", {"MissingType"}),
    ],
)
def test_csharp_undeclared_types_still_flagged(code: str, expected: set[str]) -> None:
    assert _flagged(code, "csharp") == expected


# --- TypeScript and JavaScript -------------------------------------------------


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        (
            "// Good: validate first\ninterface User { id: string }\nconst u: User = load();\n",
            "typescript",
        ),
        ("class PaymentProcessor { }\nconst p = new PaymentProcessor();\n", "typescript"),
        (
            'type UserFormData = { name: string };\nconst d: UserFormData = { name: "x" };\n',
            "typescript",
        ),
        ("const now = new Date();\nconst m = new Map();\n", "typescript"),
        (
            "interface User { save(): void; name: string }\n"
            "declare const user: User;\nuser.save();\nconst n = user.name;\n",
            "typescript",
        ),
        ("/* If the cache is Concrete */\nfunction Handler() { }\nHandler();\n", "javascript"),
        ("enum Level { High }\nconst l = Level.High;\n", "typescript"),
    ],
)
def test_ts_example_locals_comments_and_builtins_not_flagged(code: str, lang: str) -> None:
    assert _flagged(code, lang) == set()


@pytest.mark.parametrize(
    ("code", "lang", "expected"),
    [
        ("const g = new GhostWidget();\n", "typescript", {"GhostWidget"}),
        ("const h = new GhostGadget();\n", "javascript", {"GhostGadget"}),
    ],
)
def test_ts_undeclared_types_still_flagged(code: str, lang: str, expected: set[str]) -> None:
    assert _flagged(code, lang) == expected


@pytest.mark.parametrize("lang", ["csharp", "typescript", "javascript"])
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("MissingFactory();\n", {"MissingFactory"}),
        ("var item = obj.GhostWidget;\nnew GhostWidget();\n", {"GhostWidget"}),
        ('var text = "class GhostWidget";\nnew GhostWidget();\n', {"GhostWidget"}),
    ],
)
def test_example_filters_preserve_unresolved_bare_references(
    lang: str, code: str, expected: set[str]
) -> None:
    assert _flagged(code, lang) == expected


def test_doc_declarations_do_not_cross_language_boundaries(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text(
        "```csharp\nclass GhostWidget { }\n```\n```python\nGhostWidget()\n```\n",
        encoding="utf-8",
    )
    assessment = {
        "documentation_files": [{"path": "doc.md", "mapped_source_files": []}],
        "source_symbols": [],
    }
    claims = mod.run_claim_extraction(tmp_path, assessment)
    python_claim = next(c for c in claims["claims"] if c["language"] == "python")
    assert python_claim["symbols_referenced"] == ["GhostWidget"]


@pytest.mark.parametrize(
    ("lang", "code", "exit_code", "category"),
    [
        ("python", "import argparse\nargparse.ArgumentParser()", 0, ""),
        ("python", "import third_party\nthird_party.GhostWidget()", 10, "unresolved_symbol"),
        ("csharp", "class LocalWidget { }\nnew LocalWidget();", 0, ""),
        ("csharp", "MissingFactory();", 10, "unresolved_symbol"),
        (
            "csharp",
            "var widget = new ExistingWidget();\nwidget.Configure(wrong: 1);",
            10,
            "phantom_parameter",
        ),
        ("csharp", "new company.GhostWidget();", 10, "unresolved_symbol"),
        ("typescript", "enum Level { High = MissingFactory() }", 10, "unresolved_symbol"),
    ],
)
def test_cli_resolves_example_names_without_hiding_errors(
    tmp_path: Path, lang: str, code: str, exit_code: int, category: str
) -> None:
    import json

    (tmp_path / "widget.cs").write_text(
        "public class ExistingWidget {\n    public void Configure(int timeout) { }\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(f"```{lang}\n{code}\n```\n", encoding="utf-8")
    output = tmp_path / ".doc-accuracy"
    assert mod.main(["--target", str(tmp_path), "--output-dir", str(output)]) == exit_code
    report = (output / "compilability-findings.json").read_text(encoding="utf-8")
    findings = json.loads(report)["findings"]
    assert {finding["category"] for finding in findings} == ({category} if category else set())
