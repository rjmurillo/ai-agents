"""Tests for scripts.validation.sha_pinning module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.sha_pinning import (
    Violation,
    find_workflow_files,
    format_console,
    format_json,
    format_markdown,
    main,
    scan_all,
    scan_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_violation(tmp_path: Path) -> Violation:
    """Create a standard test violation."""
    return Violation(
        file="a.yml",
        full_path=str(tmp_path / "a.yml"),
        line=7,
        action="actions/checkout",
        tag="v4",
        content="uses: actions/checkout@v4",
    )


def _create_workflow(
    tmp_path: Path,
    content: str,
    filename: str = "test.yml",
    subdir: str = "workflows",
) -> Path:
    """Create a workflow YAML file under .github/<subdir>/."""
    workflow_dir = tmp_path / ".github" / subdir
    workflow_dir.mkdir(parents=True, exist_ok=True)
    file_path = workflow_dir / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


_SHA_PINNED = """\
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
"""

_VERSION_TAG = """\
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

_LOCAL_ACTION = """\
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/my-action
"""


# ---------------------------------------------------------------------------
# find_workflow_files
# ---------------------------------------------------------------------------


class TestFindWorkflowFiles:
    def test_finds_workflow_yml(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED, "ci.yml")
        files = find_workflow_files(tmp_path)
        assert len(files) == 1
        assert files[0].name == "ci.yml"

    def test_finds_workflow_yaml(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED, "ci.yaml")
        files = find_workflow_files(tmp_path)
        assert len(files) == 1

    def test_finds_action_files_recursively(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED, "action.yml", subdir="actions/my-action")
        files = find_workflow_files(tmp_path)
        assert len(files) == 1

    def test_returns_empty_for_no_github_dir(self, tmp_path: Path) -> None:
        files = find_workflow_files(tmp_path)
        assert files == []

    def test_returns_sorted(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED, "z.yml")
        _create_workflow(tmp_path, _SHA_PINNED, "a.yml")
        files = find_workflow_files(tmp_path)
        assert files[0].name == "a.yml"
        assert files[1].name == "z.yml"


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_detects_version_tag(self, tmp_path: Path) -> None:
        path = _create_workflow(tmp_path, _VERSION_TAG)
        violations = scan_file(path)
        assert len(violations) == 1
        assert violations[0].action == "actions/checkout"
        assert violations[0].tag == "v4"

    def test_passes_sha_pinned(self, tmp_path: Path) -> None:
        path = _create_workflow(tmp_path, _SHA_PINNED)
        violations = scan_file(path)
        assert len(violations) == 0

    def test_ignores_local_actions(self, tmp_path: Path) -> None:
        path = _create_workflow(tmp_path, _LOCAL_ACTION)
        violations = scan_file(path)
        assert len(violations) == 0

    def test_detects_minor_version(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v2.1")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1
        assert violations[0].tag == "v2.1"

    def test_detects_patch_version(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v3.2.1")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1
        assert violations[0].tag == "v3.2.1"

    def test_detects_alpha_prerelease(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v1.0.0-alpha")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1
        assert violations[0].tag == "v1.0.0-alpha"

    def test_detects_alpha_numeric_prerelease(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v1.0.0-alpha.1")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1

    def test_detects_dotted_prerelease(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v1.0.0-0.3.7")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1

    def test_detects_complex_prerelease(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v1.0.0-x.7.z.92")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1

    def test_detects_build_metadata(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v1.0.0+20130313144700")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1

    def test_detects_prerelease_plus_build(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v1.0.0-beta+exp.sha.5114f85")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1

    def test_detects_rc_prerelease(self, tmp_path: Path) -> None:
        content = _VERSION_TAG.replace("@v4", "@v2.0.0-rc1")
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 1

    def test_sha_with_version_comment_passes(self, tmp_path: Path) -> None:
        content = """\
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.1.0
      - uses: actions/cache@5a3ec84eff668545956fd18022155c47e93e2684 # v4.2.1-beta
"""
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 0

    def test_reports_correct_line_number(self, tmp_path: Path) -> None:
        path = _create_workflow(tmp_path, _VERSION_TAG)
        violations = scan_file(path)
        assert violations[0].line == 7

    def test_multiple_violations_in_one_file(self, tmp_path: Path) -> None:
        content = """\
name: Test
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v3
"""
        path = _create_workflow(tmp_path, content)
        violations = scan_file(path)
        assert len(violations) == 2


# ---------------------------------------------------------------------------
# scan_all
# ---------------------------------------------------------------------------


class TestScanAll:
    def test_scans_multiple_files(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _VERSION_TAG, "a.yml")
        _create_workflow(tmp_path, _SHA_PINNED, "b.yml")
        files, violations = scan_all(tmp_path)
        assert len(files) == 2
        assert len(violations) == 1

    def test_empty_when_no_files(self, tmp_path: Path) -> None:
        files, violations = scan_all(tmp_path)
        assert len(files) == 0
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# format_console
# ---------------------------------------------------------------------------


class TestFormatConsole:
    def test_pass_output(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.yml"]
        output, code = format_console(files, [])
        assert "SHA-pinned" in output
        assert code == 0

    def test_fail_output(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.yml"]
        v = _make_violation(tmp_path)
        output, code = format_console(files, [v])
        assert "MUST be pinned" in output
        assert "a.yml:7" in output
        assert code == 1


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    def test_pass_output(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.yml"]
        output, code = format_markdown(files, [])
        assert "PASS" in output
        assert code == 0

    def test_fail_output(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.yml"]
        v = _make_violation(tmp_path)
        output, code = format_markdown(files, [v])
        assert "FAIL" in output
        assert "| a.yml |" in output
        assert code == 1


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestFormatJSON:
    def test_pass_output(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.yml"]
        output, code = format_json(files, [])
        data = json.loads(output)
        assert data["status"] == "pass"
        assert data["filesScanned"] == 1
        assert code == 0

    def test_fail_output(self, tmp_path: Path) -> None:
        files = [tmp_path / "a.yml"]
        v = _make_violation(tmp_path)
        output, code = format_json(files, [v])
        data = json.loads(output)
        assert data["status"] == "fail"
        assert data["violationCount"] == 1
        assert len(data["violations"]) == 1
        assert code == 1


# ---------------------------------------------------------------------------
# main (integration-style)
# ---------------------------------------------------------------------------


class TestMain:
    def test_pass_returns_zero(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED)
        code = main(["--path", str(tmp_path)])
        assert code == 0

    def test_violations_without_ci_returns_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CI", raising=False)
        _create_workflow(tmp_path, _VERSION_TAG)
        code = main(["--path", str(tmp_path)])
        assert code == 0

    def test_violations_with_ci_returns_one(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _VERSION_TAG)
        code = main(["--path", str(tmp_path), "--ci"])
        assert code == 1

    def test_no_workflow_dir_returns_zero(self, tmp_path: Path) -> None:
        code = main(["--path", str(tmp_path)])
        assert code == 0

    def test_invalid_path_returns_two(self, tmp_path: Path) -> None:
        code = main(["--path", str(tmp_path / "nonexistent")])
        assert code == 2

    def test_json_format(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED)
        code = main(["--path", str(tmp_path), "--format", "json"])
        assert code == 0

    def test_markdown_format(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _SHA_PINNED)
        code = main(["--path", str(tmp_path), "--format", "markdown"])
        assert code == 0

    def test_json_skipped_no_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["--path", str(tmp_path), "--format", "json"])
        assert code == 0
        data = json.loads(capsys.readouterr().out)
        assert data["status"] == "skipped"

    def test_local_action_only_passes(self, tmp_path: Path) -> None:
        _create_workflow(tmp_path, _LOCAL_ACTION)
        code = main(["--path", str(tmp_path)])
        assert code == 0
