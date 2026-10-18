"""Tests for `artifacts.rules.repoOnlyOutputDirs` in validate_templates_schema.py (ADR-119)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_templates_schema as vts  # noqa: E402


def _write(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "platform.yaml"
    target.write_text(body, encoding="utf-8")
    return target


def _repo_only_config(repo_only_yaml: str) -> str:
    return f"""\
schemaVersion: "1.0"
provider: "copilot-cli"
artifacts:
  rules:
    sourceDir: ".claude/rules"
    outputDirs:
      - ".github/instructions"
      - "src/copilot-cli/instructions"
    {repo_only_yaml}
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
    frontmatterRemap:
      paths: applyTo
"""


def test_repo_only_output_dirs_valid(tmp_path: Path) -> None:
    target = _write(
        tmp_path, _repo_only_config('repoOnlyOutputDirs:\n      - ".github/instructions"')
    )
    errors, _ = vts.validate_file(target)
    assert errors == [], f"unexpected errors: {errors}"


def test_repo_only_output_dirs_not_a_list_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, _repo_only_config('repoOnlyOutputDirs: ".github/instructions"'))
    errors, _ = vts.validate_file(target)
    assert any("repoOnlyOutputDirs" in e and "must be a list" in e for e in errors), errors


def test_repo_only_output_dirs_not_in_outputdirs_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, _repo_only_config('repoOnlyOutputDirs:\n      - "elsewhere"'))
    errors, _ = vts.validate_file(target)
    assert any("not one of the declared output dirs" in e for e in errors), errors


def test_repo_only_output_dirs_non_string_entry_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, _repo_only_config("repoOnlyOutputDirs:\n      - 42"))
    errors, _ = vts.validate_file(target)
    assert any("repoOnlyOutputDirs[0]" in e for e in errors), errors
