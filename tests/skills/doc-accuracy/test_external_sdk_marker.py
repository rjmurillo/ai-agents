"""The external-sdk marker silences unresolved_symbol for one file (issue #7420)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/doc-accuracy/scripts/doc_accuracy.py",
    module_name="doc_accuracy_external_sdk",
)

MARKER = "<!-- doc-accuracy: external-sdk Aspire -- vendored from microsoft/aspire.dev -->"
FOREIGN_SYMBOLS = {"AddProject", "AddRedis", "CreateBuilder", "DistributedApplication", "Projects"}
FOREIGN_FENCE = (
    "```csharp\n"
    "var builder = DistributedApplication.CreateBuilder(args);\n"
    'var redis = builder.AddRedis("cache");\n'
    'builder.AddProject<Projects.Api>("api").WithReference(redis);\n'
    "```\n"
)
REAL_FENCE = "```csharp\nvar svc = new RealService();\nsvc.Run();\n```\n"


def _scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], doc: str
) -> tuple[int, list[dict[str, Any]]]:
    """Run the CLI on a one-doc repo and return (exit code, compilability findings)."""
    (tmp_path / ".git").write_text("gitdir: missing\n", encoding="utf-8")
    (tmp_path / "RealService.cs").write_text(
        "public class RealService\n{\n    public void Run() { }\n}\n", encoding="utf-8"
    )
    (tmp_path / "doc.md").write_text(doc, encoding="utf-8")
    code = mod.main(
        ["--target", str(tmp_path), "--output-dir", str(tmp_path / "out"), "--format", "gate"]
    )
    payload = json.loads(capsys.readouterr().out)
    return code, payload["compilability_data"]["findings"]


def _by_category(findings: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    return [f for f in findings if f["category"] == category]


def test_marker_suppresses_foreign_symbols_and_gate_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, findings = _scan(tmp_path, capsys, f"# Aspire\n\n{MARKER}\n\n{FOREIGN_FENCE}")

    assert code == 0
    assert findings == []


def test_same_file_without_marker_still_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative control: proves the positive test can fail."""
    code, findings = _scan(tmp_path, capsys, f"# Aspire\n\n{FOREIGN_FENCE}")

    flagged = {f["evidence"]["symbol"] for f in _by_category(findings, "unresolved_symbol")}
    assert code == 10
    assert FOREIGN_SYMBOLS <= flagged


@pytest.mark.parametrize(
    "bare",
    [
        "<!-- doc-accuracy: external-sdk -->",
        "<!-- doc-accuracy: external-sdk   -->",
        "<!-- doc-accuracy: external-sdk -- reason but no name -->",
    ],
)
def test_bare_marker_is_reported_and_suppresses_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], bare: str
) -> None:
    code, findings = _scan(tmp_path, capsys, f"# Aspire\n{bare}\n\n{FOREIGN_FENCE}")

    invalid = _by_category(findings, "invalid_external_sdk_marker")
    flagged = {f["evidence"]["symbol"] for f in _by_category(findings, "unresolved_symbol")}
    assert code == 10
    assert [(f["line"], f["severity"]) for f in invalid] == [(2, "high")]
    assert FOREIGN_SYMBOLS <= flagged


def test_unterminated_marker_does_not_suppress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = f"# Aspire\n<!-- doc-accuracy: external-sdk Aspire -- never closed\n\n{FOREIGN_FENCE}"
    code, findings = _scan(tmp_path, capsys, doc)

    assert code == 10
    assert _by_category(findings, "unresolved_symbol")


@pytest.mark.parametrize(
    ("fence", "closer"),
    [("```text", "```"), ("````markdown", "````"), ("~~~", "~~~")],
)
def test_marker_inside_code_fence_does_not_suppress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fence: str, closer: str
) -> None:
    doc = f"# Aspire\n\n{fence}\n{MARKER}\n{closer}\n\n{FOREIGN_FENCE}"
    code, findings = _scan(tmp_path, capsys, doc)

    assert code == 10
    assert _by_category(findings, "unresolved_symbol")
    assert _by_category(findings, "invalid_external_sdk_marker") == []


def test_marker_inside_inline_code_does_not_suppress(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = f"# Aspire\n\nWrite `{MARKER}` to opt out.\n\n{FOREIGN_FENCE}"
    code, findings = _scan(tmp_path, capsys, doc)

    assert code == 10
    assert _by_category(findings, "unresolved_symbol")


def test_marker_after_a_closed_fence_still_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = f"# Aspire\n\n```text\nexample\n```\n\n{MARKER}\n\n{FOREIGN_FENCE}"
    code, findings = _scan(tmp_path, capsys, doc)

    assert code == 0
    assert findings == []


def test_marker_scope_is_one_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "other.md").write_text(f"# Other\n\n{FOREIGN_FENCE}", encoding="utf-8")
    code, findings = _scan(tmp_path, capsys, f"# Aspire\n\n{MARKER}\n\n{FOREIGN_FENCE}")

    assert code == 10
    assert {f["file"] for f in _by_category(findings, "unresolved_symbol")} == {"other.md"}


def test_symbol_that_resolves_is_still_checked_in_a_marked_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A named parameter that RealService.Run lacks is still a phantom_parameter."""
    doc = f"# Aspire\n\n{MARKER}\n\n```csharp\nsvc.Run(bogus: 1);\n```\n\n{FOREIGN_FENCE}"
    code, findings = _scan(tmp_path, capsys, doc)

    phantom = _by_category(findings, "phantom_parameter")
    assert code == 10
    assert len(phantom) == 1
    assert "bogus" in phantom[0]["description"]
    assert _by_category(findings, "unresolved_symbol") == []


def test_resolving_example_in_marked_file_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, findings = _scan(tmp_path, capsys, f"# Mixed\n\n{MARKER}\n\n{REAL_FENCE}{FOREIGN_FENCE}")

    assert code == 0
    assert findings == []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (" Aspire -- reason ", ("Aspire", "reason")),
        (" Aspire ", ("Aspire", "")),
        (" Aspire SDK -- reason -- more ", ("Aspire SDK", "reason -- more")),
        (" Aspire --", ("Aspire", "")),
        ("", ("", "")),
        (" -- reason", ("", "")),
        ("   ", ("", "")),
    ],
)
def test_parse_sdk_marker_body(body: str, expected: tuple[str, str]) -> None:
    assert mod._parse_sdk_marker_body(body) == expected


def test_find_markers_reports_every_honored_marker_with_line_and_reason() -> None:
    lines = [
        "# T",
        "<!-- doc-accuracy: external-sdk A -- r -->",
        "```",
        "<!-- doc-accuracy: external-sdk Hidden -- r -->",
        "```",
        "<!-- doc-accuracy: external-sdk -->",
    ]

    assert mod._find_external_sdk_markers(lines) == [(2, "A", "r"), (6, "", "")]


@pytest.mark.parametrize(
    "hidden",
    [
        pytest.param(f"1. Step\n\n    ```text\n{MARKER}\n    ```\n", id="list-item-fence"),
        pytest.param(f"- Step\n\n  ```text\n{MARKER}\n  ```\n", id="two-space-list-fence"),
        pytest.param(f"- ```text\n{MARKER}\n  ```\n", id="fence-on-list-marker-line"),
        pytest.param(f"> ```text\n> {MARKER}\n> ```\n", id="blockquote-fence"),
        pytest.param(f"> ```text\n{MARKER}\n> ```\n", id="blockquote-fence-lazy-line"),
        pytest.param(f"    {MARKER}\n", id="indented-code-block"),
        pytest.param(f" {MARKER}\n", id="leading-space-marker"),
        pytest.param(f"\t{MARKER}\n", id="leading-tab-marker"),
        pytest.param(f"> {MARKER}\n", id="blockquote-marker"),
    ],
)
def test_marker_in_nested_or_prefixed_context_is_never_honored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], hidden: str
) -> None:
    code, findings = _scan(tmp_path, capsys, f"# Aspire\n\n{hidden}\n{FOREIGN_FENCE}")

    flagged = {f["evidence"]["symbol"] for f in _by_category(findings, "unresolved_symbol")}
    assert code == 10
    assert FOREIGN_SYMBOLS <= flagged
    assert _by_category(findings, "invalid_external_sdk_marker") == []


def test_inline_code_scan_is_linear_on_backtick_runs() -> None:
    line = "x " + "`" * 5000

    start = time.perf_counter()
    result = mod._find_external_sdk_markers([line])
    elapsed = time.perf_counter() - start

    assert result == []
    assert elapsed < 1.0


def test_two_valid_markers_first_wins_without_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = "<!-- doc-accuracy: external-sdk Other -- second -->"
    code, findings = _scan(tmp_path, capsys, f"# A\n{MARKER}\n\n{second}\n\n{FOREIGN_FENCE}")
    claims = json.loads((tmp_path / "out" / "claims.json").read_text(encoding="utf-8"))

    assert code == 0
    assert findings == []
    assert claims["external_sdk_files"]["doc.md"]["sdk"] == "Aspire"
    assert claims["external_sdk_files"]["doc.md"]["line"] == 2


def test_bare_marker_beside_valid_one_is_still_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = "<!-- doc-accuracy: external-sdk -->"
    code, findings = _scan(tmp_path, capsys, f"# A\n{MARKER}\n{bare}\n\n{FOREIGN_FENCE}")

    invalid = _by_category(findings, "invalid_external_sdk_marker")
    assert code == 10
    assert [f["line"] for f in invalid] == [3]
    assert _by_category(findings, "unresolved_symbol") == []


def test_exemption_is_recorded_with_reason_and_suppressed_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _scan(tmp_path, capsys, f"# A\n{MARKER}\n\n{FOREIGN_FENCE}")
    out = tmp_path / "out"
    claims = json.loads((out / "claims.json").read_text(encoding="utf-8"))
    phase3 = json.loads((out / "compilability-findings.json").read_text(encoding="utf-8"))

    assert claims["external_sdk_files"] == {
        "doc.md": {"sdk": "Aspire", "reason": "vendored from microsoft/aspire.dev", "line": 2}
    }
    assert phase3["external_sdk_suppressed"]["doc.md"] >= len(FOREIGN_SYMBOLS)


def test_marker_without_reason_is_valid_and_records_empty_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _scan(
        tmp_path, capsys, f"# A\n<!-- doc-accuracy: external-sdk Aspire -->\n\n{FOREIGN_FENCE}"
    )
    claims = json.loads((tmp_path / "out" / "claims.json").read_text(encoding="utf-8"))

    assert code == 0
    assert claims["external_sdk_files"]["doc.md"]["reason"] == ""


def test_summary_and_markdown_formats_show_the_exemption(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").write_text("gitdir: missing\n", encoding="utf-8")
    (tmp_path / "RealService.cs").write_text("public class RealService { }\n", encoding="utf-8")
    (tmp_path / "doc.md").write_text(f"# A\n{MARKER}\n\n{FOREIGN_FENCE}", encoding="utf-8")
    out = tmp_path / "out"
    base = ["--target", str(tmp_path), "--output-dir", str(out)]

    assert mod.main([*base, "--format", "summary"]) == 0
    summary = capsys.readouterr().out
    assert mod.main([*base, "--format", "markdown"]) == 0
    report = (out / "report.md").read_text(encoding="utf-8")

    expected = "External SDK exemption: doc.md (SDK Aspire, marker line 2)"
    assert expected in summary
    assert "vendored from microsoft/aspire.dev" in summary
    assert "unresolved_symbol suppressed" in summary
    assert "## External SDK exemptions" in report
    assert expected in report
