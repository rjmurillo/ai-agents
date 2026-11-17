"""The external-sdk marker silences unresolved_symbol for one file (issue #7420)."""

from __future__ import annotations

import json
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
        (" Aspire -- reason ", "Aspire"),
        (" Aspire ", "Aspire"),
        (" Aspire SDK -- reason -- more ", "Aspire SDK"),
        (" Aspire --", "Aspire"),
        ("", ""),
        (" -- reason", ""),
        ("   ", ""),
    ],
)
def test_parse_sdk_marker_body(body: str, expected: str) -> None:
    assert mod._parse_sdk_marker_body(body) == expected


def test_find_markers_reports_every_prose_marker_with_its_line() -> None:
    lines = [
        "# T",
        "<!-- doc-accuracy: external-sdk A -- r -->",
        "```",
        "<!-- doc-accuracy: external-sdk Hidden -- r -->",
        "```",
        "<!-- doc-accuracy: external-sdk -->",
    ]

    assert mod._find_external_sdk_markers(lines) == [(2, "A"), (6, "")]
