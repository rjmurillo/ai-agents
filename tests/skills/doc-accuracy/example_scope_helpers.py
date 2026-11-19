"""Shared helpers for the literal and local-binding Phase 3 tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy_example_scope",
)

_KNOWN = {
    "name": "ExistingWidget",
    "kind": "class",
    "file": "a.py",
    "line": 1,
    "signature": "class ExistingWidget:",
    "visibility": "public",
}


def unresolved(code: str, lang: str) -> set[str]:
    """Symbols Phase 3 reports as unresolved for one fenced example."""
    claim: dict[str, Any] = {
        "id": "claim-0001",
        "file": "doc.md",
        "line": 3,
        "type": "code_example",
        "language": lang,
        "content": code,
        "mapped_source": "",
        "symbols_referenced": mod._extract_identifiers(code, lang),
    }
    result = mod.run_compilability_check({"source_symbols": [_KNOWN]}, {"claims": [claim]})
    return {
        f["evidence"]["symbol"] for f in result["findings"] if f["category"] == "unresolved_symbol"
    }


def run_cli(tmp_path: Path, lang: str, code: str) -> tuple[int, set[tuple[str, str]]]:
    """Run the real CLI over one fenced example; return exit code and findings."""
    (tmp_path / "widget.cs").write_text(
        "public class ExistingWidget {\n    public void Configure(int timeout) { }\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(f"```{lang}\n{code}\n```\n", encoding="utf-8")
    output = tmp_path / ".doc-accuracy"
    exit_code = mod.main(["--target", str(tmp_path), "--output-dir", str(output)])
    report = (output / "compilability-findings.json").read_text(encoding="utf-8")
    findings = json.loads(report)["findings"]
    pairs = {(f["category"], f["evidence"].get("symbol", "")) for f in findings}
    return exit_code, pairs
