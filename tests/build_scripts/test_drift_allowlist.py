"""Tests for build/drift_allowlist.py and its wiring into generate_agents --validate.

Issue #5636 replaced the ``[skip-drift-check]`` commit marker with a committed
allowlist. These tests cover the intended exception (a listed file with a
reason passes) and the forbidden silent pass (an unlisted file, an entry with no
reason, a malformed file, and a glob all fail).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build"))
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import drift_allowlist  # noqa: E402
import generate_agents  # noqa: E402
from drift_allowlist import (  # noqa: E402
    AllowedDivergence,
    AllowlistError,
    load_allowlist,
    parse_allowlist,
    split_differences,
)

WORKFLOW = REPO_ROOT / ".github/workflows/agent-drift-detection.yml"
COMMITTED_ALLOWLIST = REPO_ROOT / ".agents/governance/drift-allowlist.json"
TARGET = "src/copilot-cli/agents/analyst.agent.md"


def _doc(*entries: object) -> dict[str, object]:
    return {"schema_version": "1", "entries": list(entries)}


def _write(root: Path, document: object) -> None:
    path = root / drift_allowlist.ALLOWLIST_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


# parse_allowlist ------------------------------------------------------------


def test_parse_accepts_entry_with_path_and_reason() -> None:
    result = parse_allowlist(_doc({"path": TARGET, "reason": " hotfix "}))
    assert result == [AllowedDivergence(TARGET, "hotfix")]


def test_parse_accepts_empty_entries() -> None:
    assert parse_allowlist(_doc()) == []


@pytest.mark.parametrize(
    "entry",
    [
        {"path": TARGET},
        {"path": TARGET, "reason": ""},
        {"path": TARGET, "reason": "   "},
        {"path": TARGET, "reason": None},
        {"path": TARGET, "reason": 7},
        {"reason": "why"},
        {"path": "", "reason": "why"},
        {"path": "   ", "reason": "why"},
        {"path": 3, "reason": "why"},
        {"path": " a/b.md", "reason": "why"},
        {"path": "/abs/file.md", "reason": "why"},
        {"path": "a/../b.md", "reason": "why"},
        {"path": "a\\b.md", "reason": "why"},
        {"path": "src/**/*.md", "reason": "why"},
        {"path": "src/[ab].md", "reason": "why"},
        {"path": "src/dir/", "reason": "why"},
        {"path": TARGET, "reason": "why", "extra": 1},
        {"path": TARGET, "reason": "why\n::error::forged"},
        {"path": TARGET, "reason": "why\rmore"},
        {"path": TARGET, "reason": "tab\there"},
        {"path": TARGET, "reason": "nul\x00byte"},
        {"path": TARGET, "reason": "del\x7fbyte"},
        {"path": "src/a\nb.md", "reason": "why"},
        "not-an-object",
        None,
    ],
)
def test_parse_rejects_invalid_entry(entry: object) -> None:
    with pytest.raises(AllowlistError, match=r"entries\[0\]"):
        parse_allowlist(_doc(entry))


def test_parse_rejects_duplicate_path() -> None:
    entry = {"path": TARGET, "reason": "why"}
    with pytest.raises(AllowlistError, match="duplicate"):
        parse_allowlist(_doc(entry, dict(entry)))


def test_parse_reports_every_bad_entry() -> None:
    with pytest.raises(AllowlistError) as caught:
        parse_allowlist(_doc({"path": TARGET}, {"reason": "why"}))
    message = str(caught.value)
    assert "entries[0]" in message
    assert "entries[1]" in message


@pytest.mark.parametrize(
    "document",
    [
        [],
        "text",
        {"entries": []},
        {"schema_version": "2", "entries": []},
        {"schema_version": "1"},
        {"schema_version": "1", "entries": {}},
    ],
)
def test_parse_rejects_bad_document_shape(document: object) -> None:
    with pytest.raises(AllowlistError):
        parse_allowlist(document)


# load_allowlist -------------------------------------------------------------


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_allowlist(tmp_path) == []


def test_load_reads_valid_file(tmp_path: Path) -> None:
    _write(tmp_path, _doc({"path": TARGET, "reason": "why"}))
    assert load_allowlist(tmp_path) == [AllowedDivergence(TARGET, "why")]


def test_load_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / drift_allowlist.ALLOWLIST_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AllowlistError, match="cannot read"):
        load_allowlist(tmp_path)


def test_load_rejects_non_utf8(tmp_path: Path) -> None:
    path = tmp_path / drift_allowlist.ALLOWLIST_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(AllowlistError, match="cannot read"):
        load_allowlist(tmp_path)


def test_committed_allowlist_is_valid() -> None:
    assert isinstance(load_allowlist(REPO_ROOT), list)
    assert COMMITTED_ALLOWLIST.is_file()


# split_differences ----------------------------------------------------------


def test_split_allows_listed_file_and_blocks_the_rest(tmp_path: Path) -> None:
    listed = str(tmp_path / TARGET)
    other = str(tmp_path / "src/copilot-cli/agents/qa.agent.md")
    allowlist = [AllowedDivergence(TARGET, "why")]
    blocking, allowed, unused = split_differences([listed, other], allowlist, tmp_path)
    assert blocking == [other]
    assert allowed == [(listed, "why")]
    assert unused == []


def test_split_reports_unused_entry(tmp_path: Path) -> None:
    _, _, unused = split_differences([], [AllowedDivergence(TARGET, "why")], tmp_path)
    assert unused == [TARGET]


def test_split_blocks_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = str(tmp_path / "elsewhere" / TARGET)
    blocking, allowed, _ = split_differences([outside], [AllowedDivergence(TARGET, "why")], root)
    assert blocking == [outside]
    assert allowed == []


# generate_agents --validate wiring ------------------------------------------


@pytest.fixture
def staged(tmp_path: Path) -> Path:
    repo = tmp_path / "stage"
    (repo / "templates").mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "templates" / "agents", repo / "templates" / "agents")
    shutil.copytree(REPO_ROOT / "templates" / "platforms", repo / "templates" / "platforms")
    shutil.copy2(REPO_ROOT / "templates" / "toolsets.yaml", repo / "templates" / "toolsets.yaml")
    rc = generate_agents.generate_agents(
        templates_path=repo / "templates", output_root=repo / "src", repo_root=repo
    )
    assert rc == 0
    return repo


def _validate(repo: Path) -> int:
    return generate_agents.generate_agents(
        templates_path=repo / "templates",
        output_root=repo / "src",
        repo_root=repo,
        validate=True,
    )


def _drift(repo: Path) -> None:
    target = repo / TARGET
    target.write_text(target.read_text(encoding="utf-8") + "\nhand edit\n", encoding="utf-8")


def test_validate_passes_with_no_drift(staged: Path) -> None:
    assert _validate(staged) == 0


def test_validate_fails_on_unlisted_drift(staged: Path) -> None:
    _drift(staged)
    assert _validate(staged) == 1


def test_validate_passes_on_listed_drift_and_prints_reason(
    staged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _drift(staged)
    _write(staged, _doc({"path": TARGET, "reason": "vendor hotfix"}))
    assert _validate(staged) == 0
    out = capsys.readouterr().out
    assert "ALLOWED DIVERGENCE" in out
    assert "vendor hotfix" in out


def test_validate_fails_when_only_another_file_is_listed(staged: Path) -> None:
    _drift(staged)
    _write(staged, _doc({"path": "src/copilot-cli/agents/qa.agent.md", "reason": "x"}))
    assert _validate(staged) == 1


def test_validate_exits_2_on_entry_missing_reason(
    staged: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _drift(staged)
    _write(staged, _doc({"path": TARGET}))
    assert _validate(staged) == 2
    assert "reason" in capsys.readouterr().err


def test_validate_warns_on_stale_entry(staged: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(staged, _doc({"path": TARGET, "reason": "no longer needed"}))
    assert _validate(staged) == 0
    assert "[WARNING] Allowlist entry matched no drift" in capsys.readouterr().out


def test_generate_mode_ignores_invalid_allowlist(staged: Path) -> None:
    """Only --validate reads the allowlist; generation must not depend on it."""
    _write(staged, _doc({"path": TARGET}))
    rc = generate_agents.generate_agents(
        templates_path=staged / "templates", output_root=staged / "src", repo_root=staged
    )
    assert rc == 0


# workflow -------------------------------------------------------------------


def test_workflow_has_no_commit_marker_bypass() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    assert "bypass-warning" not in document["jobs"]
    executable = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    assert "skip-drift-check" not in executable
    assert "bypass-requested" not in executable


def test_workflow_filter_covers_allowlist_file() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert ".agents/governance/drift-allowlist.json" in text
    assert "build/drift_allowlist.py" in text


SKILL_TEMPLATES = REPO_ROOT / "templates" / "skills"
RETIRED_MARKER = "skip-drift-check"


class TestNoRetiredMarkerInSkillTemplates:
    """Live skill templates must describe the allowlist, not the retired marker."""

    def test_no_skill_template_names_the_retired_marker(self) -> None:
        offenders = sorted(
            path.name
            for path in SKILL_TEMPLATES.glob("*.tmpl")
            if RETIRED_MARKER in path.read_text(encoding="utf-8")
        )
        assert offenders == [], f"templates still name the retired marker: {offenders}"

    def test_config_catalog_template_names_the_allowlist_file(self) -> None:
        text = (SKILL_TEMPLATES / "ai-agents-config-catalog.SKILL.md.tmpl").read_text(
            encoding="utf-8"
        )
        assert ".agents/governance/drift-allowlist.json" in text

    def test_guard_detects_an_injected_marker(self, tmp_path: Path) -> None:
        """Negative: the same substring check flags a template that names the marker."""
        template = tmp_path / "x.SKILL.md.tmpl"
        template.write_text("Use `[skip-drift-check]` to bypass.", encoding="utf-8")
        assert RETIRED_MARKER in template.read_text(encoding="utf-8")
