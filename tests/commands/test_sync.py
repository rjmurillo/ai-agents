"""Tests for the /sync drift detector (scripts/sync/detect_spec_drift.py, issue #1997).

Covers positive (drift present), negative (no drift), and edge cases (empty
file, missing target tier, ignore directive, wildcard reference, directory
reference), plus the CLI argv/exit-code contract and the error envelope.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "sync"
sys.path.insert(0, str(_SCRIPT_DIR))

import detect_spec_drift as dsd  # noqa: E402


def _make_repo(tmp_path: Path) -> Path:
    """Build a minimal repo: .agents/specs/requirements plus a real code file."""
    (tmp_path / ".agents" / "specs" / "requirements").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "real.py").write_text("# present\n", encoding="utf-8")
    return tmp_path


def _write_req(repo_root: Path, name: str, body: str) -> Path:
    req = repo_root / ".agents" / "specs" / "requirements" / name
    req.write_text(body, encoding="utf-8")
    return req


# --- positive: drift present ------------------------------------------------


def test_detects_reference_to_absent_script(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-001.md", "AC1 lives in `scripts/gone.py` on disk.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.verdict == "DRIFT"
    assert len(result.findings) == 1
    assert result.findings[0].referenced_path == "scripts/gone.py"
    assert result.findings[0].line == 1


def test_reports_each_absent_reference_on_its_line(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    body = "line one\nrefers to `.claude/skills/ghost/SKILL.md`\nand `scripts/gone.py`\n"
    _write_req(repo, "REQ-002.md", body)

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    lines = sorted(f.line for f in result.findings)
    assert lines == [2, 3]


# --- negative: no drift -----------------------------------------------------


def test_present_reference_is_not_drift(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-003.md", "The code is `scripts/real.py` and it exists.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.verdict == "PASS"
    assert result.findings == []
    assert result.refs_checked == 1


def test_prose_without_path_root_is_ignored(tmp_path: Path) -> None:
    # Arrange: backticked tokens that are not anchored to a code root.
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-004.md", "We use `the spec` and `some-skill` here.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.refs_checked == 0
    assert result.verdict == "PASS"


def test_directory_reference_present_is_not_drift(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    (repo / ".claude" / "skills" / "live").mkdir(parents=True)
    _write_req(repo, "REQ-005.md", "It ships at `.claude/skills/live/`.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.verdict == "PASS"


# --- edge cases -------------------------------------------------------------


def test_empty_spec_file_yields_no_findings(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-006.md", "")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.files_scanned == 1
    assert result.refs_checked == 0
    assert result.verdict == "PASS"


def test_missing_target_tier_is_skipped_not_raised(tmp_path: Path) -> None:
    # Arrange: only .agents exists; the design and tasks tiers are absent.
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-007.md", "Uses `scripts/real.py`.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.files_scanned == 1
    assert result.verdict == "PASS"


def test_ignore_directive_suppresses_finding(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    body = "Planned path `scripts/future.py` <!-- sync-drift-ignore -->\n"
    _write_req(repo, "REQ-008.md", body)

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.verdict == "PASS"
    assert result.refs_checked == 0


def test_wildcard_reference_matches_when_one_exists(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    (repo / ".claude" / "skills" / "alpha").mkdir(parents=True)
    (repo / ".claude" / "skills" / "alpha" / "SKILL.md").write_text("x", encoding="utf-8")
    _write_req(repo, "REQ-009.md", "All at `.claude/skills/*/SKILL.md` ship.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.verdict == "PASS"


def test_wildcard_reference_with_no_match_is_drift(tmp_path: Path) -> None:
    # Arrange: no skills directory at all.
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-010.md", "All at `.claude/skills/*/SKILL.md` ship.\n")

    # Act
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Assert
    assert result.verdict == "DRIFT"


def test_unreadable_file_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    spec = _write_req(repo, "REQ-011.md", "Uses `scripts/gone.py`.\n")

    def boom(*_args: object, **_kwargs: object) -> str:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", boom)

    # Act
    findings, refs = dsd.scan_spec_file(spec, repo)

    # Assert
    assert findings == []
    assert refs == 0


# --- repo-root discovery ----------------------------------------------------


def test_find_repo_root_locates_agents_dir(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    nested = repo / ".agents" / "specs" / "requirements"

    # Act
    found = dsd.find_repo_root(nested)

    # Assert
    assert found == repo.resolve()


def test_find_repo_root_returns_none_without_agents(tmp_path: Path) -> None:
    # Act
    found = dsd.find_repo_root(tmp_path)

    # Assert
    assert found is None


def test_relative_falls_back_to_str_for_unrelated_path(tmp_path: Path) -> None:
    # Arrange: a path that is not under repo_root cannot be made relative.
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside" / "file.md"

    # Act
    rendered = dsd._relative(repo, outside)

    # Assert
    assert rendered == str(outside)


# --- envelope rendering -----------------------------------------------------


def test_json_envelope_has_adr056_shape_on_drift(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-012.md", "Uses `scripts/gone.py`.\n")
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Act
    rendered = dsd.render_envelope(result, "json")
    payload, verdict_line = rendered.rsplit("\n", 1)
    envelope = json.loads(payload)

    # Assert
    assert set(envelope) == {"Success", "Data", "Error", "Metadata"}
    assert envelope["Success"] is True
    assert envelope["Error"] is None
    assert envelope["Data"]["verdict"] == "DRIFT"
    assert envelope["Data"]["counts"]["drift"] == 1
    assert verdict_line == "VERDICT: DRIFT"


def test_human_envelope_reports_drift_lines(tmp_path: Path) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-013.md", "Uses `scripts/gone.py`.\n")
    result = dsd.detect_drift(repo, dsd.DEFAULT_SPEC_TARGETS)

    # Act
    rendered = dsd.render_envelope(result, "human")

    # Assert
    assert "DRIFT" in rendered
    assert "scripts/gone.py" in rendered
    assert rendered.endswith("VERDICT: DRIFT")


def test_error_envelope_has_code_two(tmp_path: Path) -> None:
    # Act
    rendered = dsd.render_error_envelope("repo root not found", "json")
    payload, verdict_line = rendered.rsplit("\n", 1)
    envelope = json.loads(payload)

    # Assert
    assert envelope["Success"] is False
    assert envelope["Error"]["Code"] == 2
    assert verdict_line == "VERDICT: ERROR"


def test_error_envelope_human_shape() -> None:
    # Act
    rendered = dsd.render_error_envelope("bad config", "human")

    # Assert
    assert "ERROR: bad config" in rendered
    assert rendered.endswith("VERDICT: ERROR")


# --- CLI argv / exit-code contract ------------------------------------------


def test_main_exits_one_on_drift(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-014.md", "Uses `scripts/gone.py`.\n")

    # Act
    code = dsd.main(["--repo-root", str(repo)])

    # Assert
    assert code == 1
    assert "VERDICT: DRIFT" in capsys.readouterr().out


def test_main_exits_zero_on_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-015.md", "Uses `scripts/real.py`.\n")

    # Act
    code = dsd.main(["--repo-root", str(repo)])

    # Assert
    assert code == 0
    assert "VERDICT: PASS" in capsys.readouterr().out


def test_main_exits_two_when_repo_root_absent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: a directory with no .agents anywhere above it.
    bare = tmp_path / "bare"
    bare.mkdir()

    # Act
    code = dsd.main(["--repo-root", str(bare)])

    # Assert
    assert code == 2
    assert "VERDICT: ERROR" in capsys.readouterr().out


def test_main_honors_custom_target(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Arrange: drift lives only in the design tier; scan just that tier.
    repo = _make_repo(tmp_path)
    (repo / ".agents" / "specs" / "design").mkdir(parents=True)
    (repo / ".agents" / "specs" / "design" / "DESIGN-001.md").write_text(
        "Uses `scripts/gone.py`.\n", encoding="utf-8"
    )

    # Act
    code = dsd.main(
        ["--repo-root", str(repo), "--target", ".agents/specs/design"]
    )

    # Assert
    assert code == 1
    assert "VERDICT: DRIFT" in capsys.readouterr().out


def test_main_human_output_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Arrange
    repo = _make_repo(tmp_path)
    _write_req(repo, "REQ-016.md", "Uses `scripts/real.py`.\n")

    # Act
    code = dsd.main(["--repo-root", str(repo), "--output-format", "human"])

    # Assert
    assert code == 0
    out = capsys.readouterr().out
    assert out.startswith("detect_spec_drift")
