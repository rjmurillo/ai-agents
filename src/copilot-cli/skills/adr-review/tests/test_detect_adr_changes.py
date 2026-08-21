"""Tests for detect_adr_changes.py."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location(
    "detect_adr_changes",
    _SCRIPT_DIR / "detect_adr_changes.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main
build_parser = _mod.build_parser
_get_adr_status = _mod._get_adr_status
_get_dependent_adrs = _mod._get_dependent_adrs

_DOT_AGENTS = "." + "agents"
_PRIMARY_ADR_DIR = f"{_DOT_AGENTS}/architecture"


def test_declared_adr_locations_are_monitored() -> None:
    assert _mod.ADR_PATTERNS == (
        f"{_PRIMARY_ADR_DIR}/ADR-*.md",
        "docs/adr/ADR-*.md",
        "docs/architecture/ADR-*.md",
        "docs/decisions/ADR-*.md",
        "architecture/decisions/ADR-*.md",
    )
    assert _mod.ADR_DIRECTORIES == (
        _PRIMARY_ADR_DIR,
        "docs/adr",
        "docs/architecture",
        "docs/decisions",
        "architecture/decisions",
    )


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    # Create initial commit
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    return tmp_path


def _primary_adr_dir(root: Path) -> Path:
    return root / _DOT_AGENTS / "architecture"


class TestBuildParser:
    def test_defaults(self) -> None:
        args = build_parser().parse_args([])
        assert args.base_path == "."
        assert args.since_commit == "HEAD~1"
        assert args.include_untracked is False

    def test_custom_args(self) -> None:
        args = build_parser().parse_args([
            "--base-path", "/tmp/repo",
            "--since-commit", "abc123",
            "--include-untracked",
        ])
        assert args.base_path == "/tmp/repo"
        assert args.since_commit == "abc123"
        assert args.include_untracked is True


class TestGetADRStatus:
    """The status is read ONLY from the leading fenced YAML frontmatter block.

    A record that declares no status returns the distinct ``unknown`` sentinel,
    never ``proposed`` (issue #5189).
    """

    def test_missing_file(self, tmp_path: Path) -> None:
        assert _get_adr_status(tmp_path / "nonexistent.md") == "unknown"

    def test_file_with_status(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n---\n# Title\n")
        assert _get_adr_status(adr) == "accepted"

    def test_file_declaring_proposed(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: proposed\n---\n# Title\n")
        assert _get_adr_status(adr) == "proposed"

    def test_file_without_frontmatter(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\nNo frontmatter here\n")
        result = _get_adr_status(adr)
        assert result == "unknown"
        assert result != "proposed"

    def test_frontmatter_without_status_key(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nid: ADR-001\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_invalid_utf8_returns_unknown_not_a_traceback(self, tmp_path: Path) -> None:
        """Bytes that cannot be decoded are an undeclared status, not a crash.

        UnicodeDecodeError subclasses ValueError, not OSError, so the handler
        in _get_adr_status did not catch it and one record with a stray byte
        raised through every caller. Reported by Cursor Bugbot on PR #5209.
        """
        adr = tmp_path / "ADR-001.md"
        adr.write_bytes(b"\xff\xfe not utf-8")
        assert _get_adr_status(adr) == "unknown"

    def test_a_decodable_record_still_reports_its_status(self, tmp_path: Path) -> None:
        """Negative control for the arm above.

        A handler returning ``unknown`` unconditionally would pass the UTF-8
        test and be indistinguishable from a correct one.
        """
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: superseded\n---\n# Title\n")
        assert _get_adr_status(adr) == "superseded"

    def test_dependent_scan_skips_an_undecodable_record(self, tmp_path: Path) -> None:
        """One corrupt record must not abort the scan of the rest.

        This site was not in the bug report; the sweep found it. Fixing only
        the reported handler would have left this one crashing on the same
        input.
        """
        # Path read from the module, never spelled here. A shipped skill test
        # that hard-codes ".agents/architecture" asserts this repository's
        # layout on a consumer who may use any of ADR_DIRECTORIES, and the
        # vendor-portability ratchet (issue #2050) fails the push for it.
        adr_dir = tmp_path / _mod.ADR_DIRECTORIES[0]
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-002-bad.md").write_bytes(b"\xff\xfe not utf-8")
        (adr_dir / "ADR-003-refs.md").write_text("# ADR-003\n\nSee ADR-001.\n")

        found = _get_dependent_adrs("ADR-001", tmp_path)

        assert [Path(p).name for p in found] == ["ADR-003-refs.md"]

    def test_fenced_yaml_example_in_body_does_not_win(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text(
            "---\n"
            "status: proposed\n"
            "---\n"
            "# Title\n\n"
            "```yaml\n"
            "status: accepted\n"
            "```\n"
        )
        assert _get_adr_status(adr) == "proposed"

    def test_bare_body_status_line_does_not_win(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: proposed\n---\n# Title\n\nstatus: accepted\n")
        assert _get_adr_status(adr) == "proposed"

    def test_body_status_line_without_frontmatter_is_ignored(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("# ADR-001\n\nstatus: accepted\n")
        assert _get_adr_status(adr) == "unknown"

    def test_malformed_yaml_returns_unknown_without_raising(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: [unclosed\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_non_mapping_frontmatter_returns_unknown(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\n- just\n- a list\n---\n# Title\n")
        assert _get_adr_status(adr) == "unknown"

    def test_status_is_lowercased_and_stripped(self, tmp_path: Path) -> None:
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus:   DEPRECATED  \n---\n")
        assert _get_adr_status(adr) == "deprecated"


class TestGetDependentADRs:
    def test_finds_dependents(self, tmp_path: Path) -> None:
        adr_dir = _primary_adr_dir(tmp_path)
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001-base.md").write_text("# Base ADR")
        (adr_dir / "ADR-002-child.md").write_text("Supersedes ADR-001-base")
        result = _get_dependent_adrs("ADR-001-base", tmp_path)
        assert len(result) == 1
        assert "ADR-002-child.md" in result[0]

    def test_no_dependents(self, tmp_path: Path) -> None:
        adr_dir = _primary_adr_dir(tmp_path)
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001.md").write_text("# Standalone")
        result = _get_dependent_adrs("ADR-999", tmp_path)
        assert result == []


class TestMain:
    def test_not_a_git_repo(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["--base-path", str(tmp_path)])
        assert exit_code == 1
        assert "Not a git repository" in capsys.readouterr().err

    def test_no_changes(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        # Create ADR directory but no changes since HEAD~1 won't exist on initial commit
        adr_dir = _primary_adr_dir(git_repo)
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add adr"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        exit_code = main(["--base-path", str(git_repo), "--since-commit", "HEAD"])
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["HasChanges"] is False

    def test_created_adr(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        adr_dir = _primary_adr_dir(git_repo)
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-001.md").write_text("# New ADR")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add adr"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        exit_code = main(["--base-path", str(git_repo), "--since-commit", "HEAD~1"])
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["HasChanges"] is True
        assert len(output["Created"]) == 1
        assert output["RecommendedAction"] == "review"

    def test_created_docs_decisions_adr(
        self,
        git_repo: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        adr_dir = git_repo / "docs" / "decisions"
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-002.md").write_text("# Docs Decisions ADR")
        subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add docs decision adr"],
            cwd=git_repo,
            capture_output=True,
            check=True,
        )
        exit_code = main(["--base-path", str(git_repo), "--since-commit", "HEAD~1"])
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["HasChanges"] is True
        assert output["Created"] == ["docs/decisions/ADR-002.md"]
        assert output["RecommendedAction"] == "review"

    def test_include_untracked(self, git_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        adr_dir = _primary_adr_dir(git_repo)
        adr_dir.mkdir(parents=True)
        (adr_dir / "ADR-099.md").write_text("# Untracked")
        exit_code = main([
            "--base-path", str(git_repo),
            "--since-commit", "HEAD",
            "--include-untracked",
        ])
        assert exit_code == 0
        output = json.loads(capsys.readouterr().out)
        assert output["HasChanges"] is True
        assert any("ADR-099" in f for f in output["Created"])

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
