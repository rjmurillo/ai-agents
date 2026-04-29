"""Tests for build/scripts/validate_templates_schema.py.

Covers REQ-003-002 schema validation and the seven conditions of
ADR-006 Amendment 2026-04-28 (config-data exception for build pipelines).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_templates_schema as vts  # noqa: E402


# Minimum valid documents -----------------------------------------------------

MINIMAL_VALID = """\
schemaVersion: "1.0"
provider: "test-provider"
"""

FULL_VALID = """\
schemaVersion: "1.0"
provider: "copilot-cli"
artifacts:
  agents:
    sourceDir: ".claude/agents"
    outputDir: "src/copilot-cli/agents"
    sourceSuffix: ".md"
    outputSuffix: ".agent.md"
    excludeFilenames: ["AGENTS.md", "CLAUDE.md"]
  skills:
    sourceDir: ".claude/skills"
    outputDir: "src/copilot-cli/skills"
    mode: "directory-copy"
  commands:
    sourceDir: ".claude/commands"
    outputDir: "src/copilot-cli/skills"
    transform: "command-to-skill"
    appendFrontmatter:
      user-invocable: true
  rules:
    sourceDir: ".claude/rules"
    outputDir: ".github/instructions"
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
    frontmatterRemap:
      paths: applyTo
    frontmatterDrop:
      - alwaysApply
      - priority
  hooks:
    settingsSource: ".claude/settings.json"
    scriptSource: ".claude/hooks"
    outputConfig: "src/copilot-cli/hooks/hooks.json"
    outputScripts: "src/copilot-cli/hooks"
    eventRemap:
      PreToolUse: preToolUse
      PostToolUse: postToolUse
    eventDrop:
      - SubagentStop
      - PreCompact
    matcherPolicy: "inline-script-shim"
    versionField: 1
auditPolicy:
  pathBlocklist:
    - "^/home/"
    - "GITHUB_TOKEN"
  output:
    file: "build/audit/GENERATION-AUDIT.md"
    stdoutFormat: "json"
"""


def _write(tmp_path: Path, body: str, name: str = "platform.yaml") -> Path:
    target = tmp_path / name
    target.write_text(body, encoding="utf-8")
    return target


# --- Positive cases ---------------------------------------------------------


def test_minimal_valid_doc(tmp_path: Path) -> None:
    target = _write(tmp_path, MINIMAL_VALID)
    errors, is_config = vts.validate_file(target)
    assert errors == []
    assert is_config is False


def test_full_valid_doc(tmp_path: Path) -> None:
    target = _write(tmp_path, FULL_VALID)
    errors, is_config = vts.validate_file(target)
    assert errors == [], f"unexpected errors: {errors}"
    assert is_config is False


def test_legacy_block_accepted(tmp_path: Path) -> None:
    body = MINIMAL_VALID + 'legacy:\n  outputDir: "src/whatever"\n'
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert errors == []


def test_repo_copilot_cli_validates() -> None:
    """The actual copilot-cli.yaml in the repo MUST validate."""
    target = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"
    errors, is_config = vts.validate_file(target)
    assert errors == [], f"repo copilot-cli.yaml is invalid: {errors}"
    assert is_config is False


def test_repo_visual_studio_validates() -> None:
    target = REPO_ROOT / "templates" / "platforms" / "visual-studio.yaml"
    errors, _ = vts.validate_file(target)
    assert errors == [], f"repo visual-studio.yaml is invalid: {errors}"


def test_repo_vscode_validates() -> None:
    target = REPO_ROOT / "templates" / "platforms" / "vscode.yaml"
    errors, _ = vts.validate_file(target)
    assert errors == [], f"repo vscode.yaml is invalid: {errors}"


# --- Negative: structural ---------------------------------------------------


def test_top_level_not_mapping(tmp_path: Path) -> None:
    target = _write(tmp_path, "- a\n- b\n")
    errors, is_config = vts.validate_file(target)
    assert any("must be a mapping" in e.lower() for e in errors)
    assert is_config is True


def test_unknown_top_level_key_rejected(tmp_path: Path) -> None:
    body = MINIMAL_VALID + "bogus: true\n"
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("Unknown top-level keys" in e for e in errors)


def test_missing_schema_version_exits_two(tmp_path: Path) -> None:
    target = _write(tmp_path, 'provider: "x"\n')
    errors, is_config = vts.validate_file(target)
    assert any("schemaVersion" in e for e in errors)
    assert is_config is True


def test_missing_provider_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, 'schemaVersion: "1.0"\n')
    errors, is_config = vts.validate_file(target)
    assert any("provider" in e.lower() for e in errors)
    assert is_config is True


def test_schema_version_major_two_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, 'schemaVersion: "2.0"\nprovider: "x"\n')
    errors, is_config = vts.validate_file(target)
    assert any("major version 2" in e for e in errors)
    assert is_config is True


def test_schema_version_not_semver_rejected(tmp_path: Path) -> None:
    target = _write(tmp_path, 'schemaVersion: "abc"\nprovider: "x"\n')
    errors, is_config = vts.validate_file(target)
    assert any("SemVer" in e for e in errors)
    assert is_config is True


def test_unknown_artifact_type_rejected(tmp_path: Path) -> None:
    body = MINIMAL_VALID + "artifacts:\n  bogus:\n    sourceDir: a\n"
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("unknown artifact type" in e.lower() for e in errors)


def test_unknown_artifact_key_rejected(tmp_path: Path) -> None:
    body = (
        MINIMAL_VALID
        + "artifacts:\n  agents:\n    sourceDir: a\n    bogus: true\n"
    )
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("unknown keys" in e.lower() for e in errors)


# --- Negative: path safety (REQ-003-009) ------------------------------------


def test_path_with_traversal_rejected(tmp_path: Path) -> None:
    body = MINIMAL_VALID + 'artifacts:\n  agents:\n    sourceDir: "../etc"\n'
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("'..'" in e for e in errors)


def test_absolute_path_rejected(tmp_path: Path) -> None:
    body = MINIMAL_VALID + 'artifacts:\n  agents:\n    sourceDir: "/etc/passwd"\n'
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("absolute path" in e.lower() for e in errors)


def test_empty_path_rejected(tmp_path: Path) -> None:
    body = MINIMAL_VALID + 'artifacts:\n  agents:\n    sourceDir: ""\n'
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("must not be empty" in e for e in errors)


# --- Negative: structural complexity (ADR-006 Amendment) --------------------


def test_list_of_objects_with_too_many_keys_rejected(tmp_path: Path) -> None:
    body = (
        MINIMAL_VALID
        + "artifacts:\n  agents:\n    sourceDir: a\n"
        + "    excludeFilenames:\n      - {a: 1, b: 2, c: 3}\n"
    )
    target = _write(tmp_path, body)
    errors, _ = vts.validate_file(target)
    assert any("limited to" in e for e in errors)


def test_file_over_size_limit_rejected(tmp_path: Path) -> None:
    body = MINIMAL_VALID + "\n".join(f"# filler line {i}" for i in range(220)) + "\n"
    target = _write(tmp_path, body)
    errors, is_config = vts.validate_file(target)
    assert any("limit is" in e and "lines" in e for e in errors)
    assert is_config is True


# --- Negative: YAML safety ---------------------------------------------------


def test_yaml_anchor_rejected(tmp_path: Path) -> None:
    body = (
        'schemaVersion: "1.0"\n'
        'provider: "x"\n'
        "artifacts:\n"
        "  agents: &shared\n"
        "    sourceDir: a\n"
        "  skills: *shared\n"
    )
    target = _write(tmp_path, body)
    errors, is_config = vts.validate_file(target)
    assert any("anchor" in e.lower() for e in errors)
    assert is_config is True


def test_yaml_python_tag_rejected(tmp_path: Path) -> None:
    """safe_load rejects unknown Python tags (CWE-502 surface).

    Use !!python/name (a tag safe_load refuses) rather than a tag whose
    payload would name a sensitive builtin module by string.
    """
    body = 'schemaVersion: "1.0"\nprovider: !!python/name:builtins.print\n'
    target = _write(tmp_path, body)
    errors, is_config = vts.validate_file(target)
    assert any("parse error" in e.lower() for e in errors)
    assert is_config is True


# --- File errors ------------------------------------------------------------


def test_missing_file_returns_clean_message(tmp_path: Path) -> None:
    errors, is_config = vts.validate_file(tmp_path / "nope.yaml")
    assert any("missing" in e.lower() or "no such file" in e.lower() for e in errors)
    assert is_config is True


def test_invalid_utf8_returns_decode_error(tmp_path: Path) -> None:
    target = tmp_path / "bad.yaml"
    target.write_bytes(b"\xff\xfe\x00\x00not utf8")
    errors, is_config = vts.validate_file(target)
    assert errors  # any error is fine; decode or parse
    assert is_config is True


# --- CLI entry --------------------------------------------------------------


def test_main_returns_zero_on_repo(capsys: pytest.CaptureFixture[str]) -> None:
    """Discovery against the actual repo passes."""
    rc = vts.main(["--root", str(REPO_ROOT)])
    assert rc == 0


def test_main_returns_two_on_invalid_schema_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = _write(tmp_path, 'schemaVersion: "9.0"\nprovider: "x"\n')
    rc = vts.main(["--platform", str(bad)])
    assert rc == 2


def test_main_returns_one_on_logic_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Schema-valid doc with a non-config-error problem returns 1.

    Currently every error pathway flagged as critical is a config error
    (exit 2). To assert exit 1 isolation, build a doc that fails only
    on a non-config-flagged validator: an unknown artifact key is a
    schema-validation failure but not a parse/version/path/anchor failure.
    """
    body = (
        MINIMAL_VALID
        + "artifacts:\n  agents:\n    sourceDir: a\n    bogus: true\n"
    )
    bad = _write(tmp_path, body)
    rc = vts.main(["--platform", str(bad)])
    assert rc == 1


def test_main_no_files_returns_two(tmp_path: Path) -> None:
    """Empty platforms dir returns exit 2 (config error)."""
    (tmp_path / "templates" / "platforms").mkdir(parents=True)
    rc = vts.main(["--root", str(tmp_path)])
    assert rc == 2
