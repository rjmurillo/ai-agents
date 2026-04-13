#!/usr/bin/env python3
"""Tests for doc_accuracy module."""

from __future__ import annotations

import json
import sys
from pathlib import Path

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy",
)
SourceSymbol = mod.SourceSymbol
DocFile = mod.DocFile
Claim = mod.Claim
Finding = mod.Finding
run_assessment = mod.run_assessment
run_claim_extraction = mod.run_claim_extraction
run_compilability_check = mod.run_compilability_check
check_gate = mod.check_gate
generate_markdown_report = mod.generate_markdown_report
main = mod.main
_should_exclude = mod._should_exclude
_detect_language = mod._detect_language
_extract_identifiers = mod._extract_identifiers
_extract_quantitative_claims = mod._extract_quantitative_claims
_extract_python_symbols = mod._extract_python_symbols
_extract_csharp_symbols = mod._extract_csharp_symbols
_count_code_blocks = mod._count_code_blocks


class TestShouldExclude:
    def test_excludes_git(self) -> None:
        assert _should_exclude(Path(".git/config"))

    def test_excludes_node_modules(self) -> None:
        assert _should_exclude(Path("node_modules/pkg/index.js"))

    def test_allows_normal_path(self) -> None:
        assert not _should_exclude(Path("src/main.py"))

    def test_excludes_doc_accuracy_output(self) -> None:
        assert _should_exclude(Path(".doc-accuracy/report.json"))


class TestDetectLanguage:
    def test_python(self) -> None:
        assert _detect_language("python") == "python"

    def test_py_alias(self) -> None:
        assert _detect_language("py") == "python"

    def test_csharp(self) -> None:
        assert _detect_language("csharp") == "csharp"

    def test_cs_alias(self) -> None:
        assert _detect_language("cs") == "csharp"

    def test_empty_string(self) -> None:
        assert _detect_language("") == ""

    def test_unknown_returns_token(self) -> None:
        assert _detect_language("fortran") == "fortran"


class TestExtractIdentifiers:
    def test_camel_case(self) -> None:
        result = _extract_identifiers("var x = MyClass.DoSomething();")
        assert "MyClass" in result
        assert "DoSomething" in result

    def test_method_calls(self) -> None:
        result = _extract_identifiers("obj.process(data)")
        assert "process" in result

    def test_named_params(self) -> None:
        result = _extract_identifiers("Foo(name: value)")
        assert "name" in result


class TestExtractQuantitativeClaims:
    def test_percentage(self) -> None:
        result = _extract_quantitative_claims("Achieves 95.5% accuracy")
        assert any("95.5%" in c for c in result)

    def test_timing(self) -> None:
        result = _extract_quantitative_claims("Response time is 100ms")
        assert any("100ms" in c for c in result)

    def test_no_claims(self) -> None:
        assert _extract_quantitative_claims("No numbers here") == []

    def test_comparison(self) -> None:
        result = _extract_quantitative_claims("Latency <5%")
        assert len(result) > 0


class TestCountCodeBlocks:
    def test_counts_fenced_blocks(self) -> None:
        md = "```python\ncode\n```\n\n```js\nmore\n```\n"
        # Counts both opening and closing fence lines matching the pattern
        assert _count_code_blocks(md) == 4

    def test_no_blocks(self) -> None:
        assert _count_code_blocks("Just text") == 0


class TestExtractPythonSymbols:
    def test_extracts_class(self) -> None:
        code = "class MyClass:\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 1
        assert symbols[0].name == "MyClass"
        assert symbols[0].kind == "class"

    def test_extracts_function(self) -> None:
        code = "def process_data(x):\n    return x\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 1
        assert symbols[0].name == "process_data"
        assert symbols[0].kind == "function"

    def test_skips_private(self) -> None:
        code = "def _private():\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert len(symbols) == 0

    def test_records_line_number(self) -> None:
        code = "\n\ndef foo():\n    pass\n"
        symbols = _extract_python_symbols(code, "test.py")
        assert symbols[0].line == 3


class TestExtractCsharpSymbols:
    def test_extracts_class(self) -> None:
        code = "    public class Foo\n    {\n    }\n"
        symbols = _extract_csharp_symbols(code, "Foo.cs")
        assert len(symbols) == 1
        assert symbols[0].name == "Foo"
        assert symbols[0].kind == "class"

    def test_extracts_method(self) -> None:
        code = "    public void DoWork(int x)\n    {\n    }\n"
        symbols = _extract_csharp_symbols(code, "Bar.cs")
        assert len(symbols) == 1
        assert symbols[0].name == "DoWork"
        assert symbols[0].kind == "method"


class TestSourceSymbol:
    def test_to_dict(self) -> None:
        sym = SourceSymbol(
            name="Foo", kind="class", file="a.py", line=1,
            signature="class Foo:",
        )
        d = sym.to_dict()
        assert d["name"] == "Foo"
        assert d["visibility"] == "public"


class TestRunAssessment:
    def test_scans_directory(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Hello\n`MyFunc`\n")
        (tmp_path / "main.py").write_text("def MyFunc():\n    pass\n")

        result = run_assessment(tmp_path)

        assert len(result["documentation_files"]) >= 1
        assert len(result["source_symbols"]) >= 1
        assert "coverage_summary" in result
        assert result["changed_files"] is None

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = run_assessment(tmp_path)
        assert result["documentation_files"] == []
        assert result["source_symbols"] == []
        assert result["coverage_summary"]["coverage_pct"] == 100.0


class TestRunClaimExtraction:
    def test_extracts_code_example(self, tmp_path: Path) -> None:
        md = "# Doc\n\n```python\nMyClass()\n```\n"
        (tmp_path / "doc.md").write_text(md)

        assessment = {
            "documentation_files": [{
                "path": "doc.md",
                "mapped_source_files": [],
                "referenced_symbols": [],
            }],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        assert len(result["claims"]) >= 1
        assert result["claims"][0]["type"] == "code_example"
        assert result["claims"][0]["language"] == "python"

    def test_extracts_quantitative_claim(self, tmp_path: Path) -> None:
        md = "Performance is 99.9% uptime.\n"
        (tmp_path / "perf.md").write_text(md)

        assessment = {
            "documentation_files": [{
                "path": "perf.md",
                "mapped_source_files": [],
                "referenced_symbols": [],
            }],
            "source_symbols": [],
        }
        result = run_claim_extraction(tmp_path, assessment)
        quant = [c for c in result["claims"] if c["type"] == "quantitative"]
        assert len(quant) >= 1


class TestRunCompilabilityCheck:
    def test_no_findings_when_symbol_exists(self) -> None:
        assessment = {
            "source_symbols": [{
                "name": "MyClass", "kind": "class",
                "file": "a.py", "line": 1,
                "signature": "class MyClass:", "visibility": "public",
            }],
        }
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "code_example", "language": "python",
                "content": "x = MyClass()",
                "symbols_referenced": ["MyClass"],
                "mapped_source": "a.py",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []

    def test_finds_unresolved_symbol(self) -> None:
        assessment = {"source_symbols": []}
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "method_signature", "language": "",
                "content": "MyWidget does things",
                "symbols_referenced": ["MyWidget"],
                "mapped_source": "",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["category"] == "unresolved_symbol"

    def test_skips_framework_types(self) -> None:
        assessment = {"source_symbols": []}
        claims = {
            "claims": [{
                "id": "claim-0001", "file": "doc.md", "line": 1,
                "type": "method_signature", "language": "",
                "content": "Returns a List",
                "symbols_referenced": ["List"],
                "mapped_source": "",
            }],
        }
        result = run_compilability_check(assessment, claims)
        assert result["findings"] == []


class TestCheckGate:
    def test_pass_no_findings(self) -> None:
        result = check_gate({"findings": []}, "high")
        assert result["verdict"] == "PASS"
        assert result["blocking_findings"] == 0

    def test_pass_none(self) -> None:
        result = check_gate(None, "high")
        assert result["verdict"] == "PASS"

    def test_fail_critical(self) -> None:
        findings = {"findings": [{
            "severity": "critical", "id": "f1",
        }]}
        result = check_gate(findings, "high")
        assert result["verdict"] == "FAIL"
        assert result["blocking_findings"] == 1

    def test_pass_below_threshold(self) -> None:
        findings = {"findings": [{
            "severity": "low", "id": "f1",
        }]}
        result = check_gate(findings, "high")
        assert result["verdict"] == "PASS"

    def test_severity_counts(self) -> None:
        findings = {"findings": [
            {"severity": "critical", "id": "f1"},
            {"severity": "critical", "id": "f2"},
            {"severity": "medium", "id": "f3"},
        ]}
        result = check_gate(findings, "critical")
        assert result["by_severity"]["critical"] == 2
        assert result["by_severity"]["medium"] == 1
        assert result["total_findings"] == 3


class TestGenerateMarkdownReport:
    def test_writes_report(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "PASS", "threshold": "high",
            "blocking_findings": 0, "total_findings": 0,
            "by_severity": {},
        }
        report_path = tmp_path / "report.md"
        generate_markdown_report(None, None, None, gate, report_path)

        content = report_path.read_text()
        assert "# Documentation Accuracy Report" in content
        assert "PASS" in content

    def test_includes_findings(self, tmp_path: Path) -> None:
        gate = {
            "verdict": "FAIL", "threshold": "high",
            "blocking_findings": 1, "total_findings": 1,
            "by_severity": {"critical": 1},
        }
        comp = {"findings": [{
            "severity": "critical", "file": "doc.md",
            "line": 10, "description": "Bad symbol reference",
        }]}
        report_path = tmp_path / "report.md"
        generate_markdown_report(None, None, comp, gate, report_path)

        content = report_path.read_text()
        assert "Bad symbol reference" in content
        assert "FAIL" in content


class TestMain:
    def test_invalid_target(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope"
        rc = main(["--target", str(nonexistent)])
        assert rc == 1

    def test_scan_empty_repo(self, tmp_path: Path) -> None:
        rc = main(["--target", str(tmp_path)])
        assert rc == 0
        # Check gate-result.json was written
        gate_path = tmp_path / ".doc-accuracy" / "gate-result.json"
        assert gate_path.exists()
        gate = json.loads(gate_path.read_text())
        assert gate["verdict"] == "PASS"

    def test_markdown_format(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Test\n")
        rc = main(["--target", str(tmp_path), "--format", "markdown"])
        assert rc == 0
        report = tmp_path / ".doc-accuracy" / "report.md"
        assert report.exists()
        assert "Documentation Accuracy Report" in report.read_text()

    def test_summary_format(self, tmp_path: Path, capsys) -> None:
        rc = main(["--target", str(tmp_path), "--format", "summary"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Gate: PASS" in captured.out

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "custom-output"
        rc = main([
            "--target", str(tmp_path),
            "--output-dir", str(out),
        ])
        assert rc == 0
        assert (out / "gate-result.json").exists()

    def test_phases_selection(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("# Hi\n")
        rc = main(["--target", str(tmp_path), "--phases", "1"])
        assert rc == 0
        assert (tmp_path / ".doc-accuracy" / "assessment.json").exists()
        # claims.json should not exist when only phase 1 runs
        assert not (tmp_path / ".doc-accuracy" / "claims.json").exists()
