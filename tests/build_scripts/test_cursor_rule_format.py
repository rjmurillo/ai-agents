"""Cursor ``.mdc`` rule output: ``artifacts.rules.outputFormat`` (ADR-115 Decision 2).

Covers the frontmatter builder, the generator's cursor-mdc path, the format
validator, and the pin that the default Copilot output is byte-identical.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_rules  # noqa: E402
import validate_templates_schema as vts  # noqa: E402
from cursor_rule_format import build_mdc_frontmatter, format_mdc_frontmatter  # noqa: E402

COPILOT_CONFIG = REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"
CURSOR_CONFIG = REPO_ROOT / "templates" / "platforms" / "cursor.yaml"


# Frontmatter builder ---------------------------------------------------------


def test_universal_scope_becomes_always_apply() -> None:
    assert build_mdc_frontmatter({"applyTo": "**"}) == {"alwaysApply": True}


def test_universal_entry_among_others_still_always_applies() -> None:
    assert build_mdc_frontmatter({"applyTo": "**/*.py,**"}) == {"alwaysApply": True}


def test_scoped_rule_gets_comma_joined_globs_and_always_apply_false() -> None:
    result = build_mdc_frontmatter({"applyTo": "**/*.py,**/pyproject.toml"})
    assert result == {"globs": "**/*.py, **/pyproject.toml", "alwaysApply": False}


def test_recursive_extension_glob_is_scoped_not_universal() -> None:
    assert build_mdc_frontmatter({"applyTo": "**/*.py"})["alwaysApply"] is False


def test_description_is_kept_and_priority_is_not_emitted() -> None:
    result = build_mdc_frontmatter({"applyTo": "*.md", "description": "Docs", "priority": "high"})
    assert result == {"description": "Docs", "globs": "*.md", "alwaysApply": False}


def test_missing_scope_defaults_to_always_apply() -> None:
    assert build_mdc_frontmatter({}) == {"alwaysApply": True}


def test_whitespace_and_empty_entries_are_ignored() -> None:
    result = build_mdc_frontmatter({"applyTo": " a/** , ,b/** "})
    assert result["globs"] == "a/**, b/**"


def test_format_orders_keys_and_quotes_strings() -> None:
    text = format_mdc_frontmatter(
        {"alwaysApply": False, "globs": "*.env*, a: b", "description": "Why: because"}
    )
    assert text == 'description: "Why: because"\nglobs: "*.env*, a: b"\nalwaysApply: false\n'


def test_format_output_parses_back_to_the_same_mapping() -> None:
    data = {"description": 'He said "hi"', "globs": "**/Auth/**, *.env*", "alwaysApply": False}
    assert yaml.safe_load(format_mdc_frontmatter(data)) == data


def test_format_emits_bare_true() -> None:
    assert format_mdc_frontmatter({"alwaysApply": True}) == "alwaysApply: true\n"


# Generator -------------------------------------------------------------------


def _write_config(tmp_path: Path, extra: str = "") -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDir: "out"
    sourceSuffix: ".md"
    outputSuffix: ".mdc"
    frontmatterRemap:
      paths: applyTo
    frontmatterDrop:
      - alwaysApply
      - priority
{extra}""",
        encoding="utf-8",
    )
    return cfg


def _rule(tmp_path: Path, name: str, frontmatter: str, body: str = "Body.\n") -> None:
    rules = tmp_path / "rules_src"
    rules.mkdir(exist_ok=True)
    (rules / f"{name}.md").write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")


def _generate(tmp_path: Path, extra: str = "    outputFormat: cursor-mdc\n") -> int:
    rc, _ = generate_rules.generate_rules(_write_config(tmp_path, extra), tmp_path)
    return rc


def test_generator_writes_always_apply_for_universal_rule(tmp_path: Path) -> None:
    _rule(tmp_path, "universal", 'paths: ["**"]\npriority: critical\n', "# Universal\n")
    assert _generate(tmp_path) == 0
    assert (tmp_path / "out" / "universal.mdc").read_text(encoding="utf-8") == (
        "---\nalwaysApply: true\n---\n# Universal\n"
    )


def test_generator_writes_globs_for_scoped_rule(tmp_path: Path) -> None:
    _rule(tmp_path, "py", 'description: Python\npaths: ["**/*.py", "**/pyproject.toml"]\n')
    assert _generate(tmp_path) == 0
    text = (tmp_path / "out" / "py.mdc").read_text(encoding="utf-8")
    assert text.startswith(
        '---\ndescription: "Python"\nglobs: "**/*.py, **/pyproject.toml"\nalwaysApply: false\n---\n'
    )
    assert "priority" not in text
    assert "applyTo" not in text


def test_generator_filters_internal_only_globs(tmp_path: Path) -> None:
    _rule(tmp_path, "mixed", 'paths: [".claude/rules/x.md", "src/**"]\n')
    assert _generate(tmp_path) == 0
    text = (tmp_path / "out" / "mixed.mdc").read_text(encoding="utf-8")
    assert 'globs: "src/**"' in text
    assert ".claude" not in text


def test_generator_skips_rule_whose_globs_are_all_internal(tmp_path: Path) -> None:
    _rule(tmp_path, "internal", 'paths: [".claude/**", ".serena/**"]\n')
    assert _generate(tmp_path) == 0
    assert not (tmp_path / "out" / "internal.mdc").exists()


def test_generator_gives_unscoped_rule_always_apply(tmp_path: Path) -> None:
    _rule(tmp_path, "bare", "description: No scope\n")
    assert _generate(tmp_path) == 0
    text = (tmp_path / "out" / "bare.mdc").read_text(encoding="utf-8")
    assert "alwaysApply: true" in text


def test_generator_prunes_orphan_mdc(tmp_path: Path) -> None:
    _rule(tmp_path, "keep", 'paths: ["**"]\n')
    (tmp_path / "out").mkdir()
    orphan = tmp_path / "out" / "gone.mdc"
    orphan.write_text("stale", encoding="utf-8")
    assert _generate(tmp_path) == 0
    assert not orphan.exists()


@pytest.mark.parametrize("bad", ["cursor", "MDC", "''", "[cursor-mdc]", "5"])
def test_generator_rejects_unknown_output_format(tmp_path: Path, bad: str) -> None:
    _rule(tmp_path, "r", 'paths: ["**"]\n')
    assert _generate(tmp_path, f"    outputFormat: {bad}\n") == 2
    assert not (tmp_path / "out").exists()


# Copilot output stays byte-identical (ADR-115 Decision 2) ----------------------


def _render_copilot(tmp_path: Path, extra_stanza: dict[str, object]) -> Path:
    """Render the real Copilot rules stanza from the real rules into tmp_path."""
    shutil.copytree(REPO_ROOT / "src" / "claude" / "rules", tmp_path / "src" / "claude" / "rules")
    # ADR-119: repo-only rules are real files beside the links in .claude/rules.
    repo_only = tmp_path / ".claude" / "rules"
    repo_only.mkdir(parents=True)
    for path in (REPO_ROOT / ".claude" / "rules").glob("*.md"):
        if not path.is_symlink():
            shutil.copy2(path, repo_only / path.name)
    cfg = yaml.safe_load(COPILOT_CONFIG.read_text(encoding="utf-8"))
    stanza = cfg["artifacts"]["rules"]
    stanza.update(extra_stanza)
    stanza["outputDirs"] = ["gh/instructions", "src/copilot-cli/instructions"]
    stanza["keepInternalGlobsFor"] = ["gh/instructions"]
    stanza["repoOnlyOutputDirs"] = ["gh/instructions"]
    config = tmp_path / "copilot.yaml"
    config.write_text(yaml.safe_dump({**cfg, "artifacts": {"rules": stanza}}), encoding="utf-8")
    rc, _ = generate_rules.generate_rules(config, tmp_path)
    assert rc == 0
    return tmp_path


@pytest.mark.parametrize("extra", [{}, {"outputFormat": "instructions"}])
def test_copilot_plugin_instructions_are_byte_identical_to_committed(
    tmp_path: Path, extra: dict[str, object]
) -> None:
    rendered = _render_copilot(tmp_path, extra) / "src" / "copilot-cli" / "instructions"
    committed = REPO_ROOT / "src" / "copilot-cli" / "instructions"
    names = sorted(p.name for p in committed.glob("*.instructions.md"))
    assert names, "no committed Copilot instructions to compare"
    assert sorted(p.name for p in rendered.glob("*.instructions.md")) == names
    for name in names:
        assert (rendered / name).read_bytes() == (committed / name).read_bytes(), name


def test_copilot_github_instructions_are_byte_identical_to_committed(tmp_path: Path) -> None:
    """The repo-only renders equal the real files; every other entry is a link."""
    rendered = _render_copilot(tmp_path, {}) / "gh" / "instructions"
    committed = REPO_ROOT / ".github" / "instructions"
    real = sorted(p.name for p in committed.glob("*.instructions.md") if not p.is_symlink())
    assert real, "no repo-only instructions to compare"
    assert sorted(p.name for p in rendered.glob("*.instructions.md")) == real
    for name in real:
        assert (rendered / name).read_bytes() == (committed / name).read_bytes(), name


def test_copilot_config_does_not_opt_in_to_cursor_format() -> None:
    cfg = yaml.safe_load(COPILOT_CONFIG.read_text(encoding="utf-8"))
    assert "outputFormat" not in cfg["artifacts"]["rules"]


# Cursor config ---------------------------------------------------------------


def test_cursor_config_selects_mdc_and_validates() -> None:
    cfg = yaml.safe_load(CURSOR_CONFIG.read_text(encoding="utf-8"))
    stanza = cfg["artifacts"]["rules"]
    assert stanza["outputFormat"] == "cursor-mdc"
    assert stanza["outputSuffix"] == ".mdc"
    assert "keepInternalGlobsFor" not in stanza
    assert vts.validate_file(CURSOR_CONFIG) == ([], False)
