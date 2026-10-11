"""Phase 3 must judge Python examples by code tokens, not prose or builtins."""

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
    module_name="doc_accuracy_python_examples",
)
HOOK = (
    '"""Hook for the <EventName> event.\n\nBypass Codes: see ADR. IDs use UTC.\n"""\n'
    "# Hook comment mentioning ADR and UTC\ntry:\n    import json\n"
    "except ImportError:\n    raise SystemExit(0)\n"
)
UNTERMINATED = 'x = """Unterminated Hook text\nmore ADR words\n'
BAD_DEDENT = "if x:\n        a = 1\n    b = 2  # Hook\n"


def _flagged(code: str, lang: str = "python") -> set[str]:
    symbol = {"name": "ExistingWidget", "kind": "class", "file": "a.py",
              "line": 1, "signature": "class ExistingWidget:", "visibility": "public"}
    claim: dict[str, Any] = {
        "id": "claim-0001", "file": "doc.md", "line": 7, "type": "code_example",
        "language": lang, "content": code, "mapped_source": "",
        "symbols_referenced": mod._extract_identifiers(code, lang),
    }
    result = mod.run_compilability_check(
        {"source_symbols": [symbol]}, {"claims": [claim]}
    )
    return {f["evidence"]["symbol"] for f in result["findings"]
            if f["category"] == "unresolved_symbol"}


@pytest.mark.parametrize("code", [
    '"""Hook uses ADR and UTC."""\n# Hook ADR UTC\nx = 1\n',
    HOOK, UNTERMINATED, BAD_DEDENT,
    "try:\n    pass\nexcept ImportError:\n    raise ValueError('x')\n",
    "from datetime import UTC, datetime\nnow = datetime.now(tz=UTC)\n",
    "w = ExistingWidget()\n",
    "from datetime import UTC as Utc\nx = Utc\n",
    "from datetime import (UTC as Utc,\n    datetime as DT)\nx = DT\n",
    'x = "Prose Widget\ny = 1\n',
])
def test_python_prose_builtins_and_stdlib_imports_not_flagged(code: str) -> None:
    assert _flagged(code) == set()


@pytest.mark.parametrize(("code", "lang", "expected"), [
    ("svc = FooBarService()\n", "python", {"FooBarService"}),
    ('"""Hook docs."""\nsvc = FooBarService()\n', "python", {"FooBarService"}),
    ("from mypkg.core import FooBarService\n", "python", {"FooBarService"}),
    ("var s = new MissingThing();", "csharp", {"MissingThing"}),
    ("throw new ImportError();", "csharp", {"ImportError"}),
])
def test_real_undefined_symbols_still_flagged(
    code: str, lang: str, expected: set[str]
) -> None:
    assert _flagged(code, lang) == expected


@pytest.mark.parametrize(("code", "present", "absent"), [
    ('s = "Hook"  # ADR\nFooBar()', "FooBar", "Hook"),
    pytest.param('print(f"Prose {Widget} Text")', "Widget", "Prose",
                 marks=pytest.mark.skipif(sys.version_info < (3, 12),
                                          reason="f-strings are one STRING token")),
    pytest.param('print(t"Prose {Widget} Hook")', "Widget", "Prose",
                 marks=pytest.mark.skipif(sys.version_info < (3, 14),
                                          reason="t-strings need Python 3.14")),
    ("x = 'It\\'s Hook'\nWidget()", "Widget", "Hook"),
    ('s = "from datetime import Widget"\nWidget()\n', "Widget", "Hook"),
    ('x = """open Hook\nFooBarService()\n', "", "FooBarService"),
    ("if x:\n        a = 1\n    FooBarService()  # Hook\n", "FooBarService", "Hook"),
    ("from collections import (OrderedDict as OD,\n    Counter)\n", "", "OrderedDict"),
    ('x = "Prose Widget\nFooBar()\n', "FooBar", "Widget"),
    ("from collections import (OrderedDict,\n    Counter)\n", "", "Counter"),
])
def test_python_identifiers_come_from_code_tokens(
    code: str, present: str, absent: str
) -> None:
    ids = mod._extract_identifiers(code, "python")
    assert present in ids or present == ""
    assert absent not in ids


def test_fallback_blanks_single_line_strings_and_comments() -> None:
    stripped = mod._strip_python_non_code(
        "if x:\n        a = 'Hook' + \"ADR\"\n    b = 2  # UTC\n"
    )
    assert not {"Hook", "ADR", "UTC"} & set(stripped.split())


def test_other_languages_keep_agnostic_extraction() -> None:
    ids = mod._extract_identifiers('var s = "Hook ADR"; // UTC', "csharp")
    assert {"Hook", "ADR", "UTC"} <= set(ids)
    assert mod._extract_identifiers('"""Hook"""') == ["Hook"]
