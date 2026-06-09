"""Tests for build/scripts/generate_rules.py (REQ-003-006, M4-T2).

Coverage matrix:
- positive: scoped rules emit; paths -> applyTo; alwaysApply/priority dropped
- negative severity branches: high/medium/low without scope
- governance keyword scan (unset severity + body keyword)
- NO-REGEN sentinel honored
- configuration errors (missing stanza, traversal, etc.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import generate_rules  # noqa: E402

# Helpers --------------------------------------------------------------------


def _write_rule(
    rules_dir: Path,
    name: str,
    *,
    frontmatter: str | None = None,
    body: str = "Rule body.\n",
) -> Path:
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"{name}.md"
    if frontmatter is not None:
        content = f"---\n{frontmatter}---\n{body}"
    else:
        content = body
    path.write_text(content, encoding="utf-8")
    return path


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDir: "instr_out"
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
    frontmatterRemap:
      paths: applyTo
    frontmatterDrop:
      - alwaysApply
      - priority
    skipIfNoPathScope: true
"""
    )
    return cfg


def _read_output(tmp_path: Path, name: str) -> str:
    return (tmp_path / "instr_out" / f"{name}.instructions.md").read_text(encoding="utf-8")


# Positive: scoped rules emit ------------------------------------------------


def test_scoped_rule_with_paths_remaps_to_applyTo(tmp_path: Path) -> None:
    """`paths:` must be renamed to `applyTo:` with value preserved."""
    _write_rule(
        tmp_path / "rules_src",
        "ci-scripts",
        frontmatter='paths: "scripts/**,build/**"\ndescription: "CI scripts"\n',
        body="# CI Scripts\n",
    )
    cfg = _write_config(tmp_path)

    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0

    out = _read_output(tmp_path, "ci-scripts")
    assert "applyTo:" in out
    assert "scripts/**,build/**" in out
    assert "paths:" not in out.split("---")[1]  # only check frontmatter section
    assert "description:" in out


def test_scoped_rule_with_applyTo_preserved(tmp_path: Path) -> None:
    """`applyTo:` already in source must round-trip unchanged."""
    _write_rule(
        tmp_path / "rules_src",
        "testing",
        frontmatter='applyTo: "tests/**"\npriority: high\n',
        body="# Testing\n",
    )
    cfg = _write_config(tmp_path)
    assert generate_rules.generate_rules(cfg, tmp_path)[0] == 0

    out = _read_output(tmp_path, "testing")
    assert "applyTo: tests/**" in out
    assert "priority:" not in out.split("---")[1]


def test_alwaysApply_and_priority_dropped(tmp_path: Path) -> None:
    _write_rule(
        tmp_path / "rules_src",
        "scoped",
        frontmatter=(
            'paths: "src/**"\nalwaysApply: true\npriority: high\n'
            'description: "scoped rule"\n'
        ),
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    assert generate_rules.generate_rules(cfg, tmp_path)[0] == 0

    out = _read_output(tmp_path, "scoped")
    fm = out.split("---")[1]
    assert "alwaysApply" not in fm
    assert "priority" not in fm
    assert "description: scoped rule" in fm
    assert "applyTo: src/**" in fm


def test_globs_treated_as_path_scope(tmp_path: Path) -> None:
    """`globs:` is a recognized scope key; rule should emit without severity gate."""
    _write_rule(
        tmp_path / "rules_src",
        "globsy",
        frontmatter='globs: "**/*.py"\n',
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    assert generate_rules.generate_rules(cfg, tmp_path)[0] == 0
    assert (tmp_path / "instr_out" / "globsy.instructions.md").is_file()


# Round 3 amendment: rules are universal across providers ----------------
# Round 2 severity gate (high/medium/low + governance-keyword scan) was
# removed. Every rule emits; unscoped rules synthesize applyTo: "**".


def test_unscoped_rule_emits_with_universal_apply_to(tmp_path: Path) -> None:
    """Round 3: unscoped rule emits to .github/instructions/ with applyTo: '**'."""
    _write_rule(
        tmp_path / "rules_src",
        "philosophy",
        frontmatter="description: A design rule.\n",
        body="A neutral architectural musing.\n",
    )
    cfg = _write_config(tmp_path)
    rc, result = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert result.written == 1
    out = tmp_path / "instr_out" / "philosophy.instructions.md"
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "applyTo: \"**\"" in content or "applyTo: '**'" in content or "applyTo: **" in content


def test_unscoped_rule_with_governance_keyword_still_ships(tmp_path: Path) -> None:
    """Round 3: governance-keyword scan removed; rule mentioning 'secrets' still ships."""
    _write_rule(
        tmp_path / "rules_src",
        "security_advice",
        frontmatter="description: Security guidance.\n",
        body="Do not commit secrets or credentials.\n",
    )
    cfg = _write_config(tmp_path)
    rc, result = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert result.written == 1


def test_severity_field_in_source_is_passed_through(tmp_path: Path) -> None:
    """Round 3: severity is no longer interpreted by generator; preserved as data."""
    _write_rule(
        tmp_path / "rules_src",
        "any_rule",
        frontmatter="severity: medium\n",
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    rc, result = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert result.written == 1
    out_text = (tmp_path / "instr_out" / "any_rule.instructions.md").read_text(encoding="utf-8")
    assert "severity: medium" in out_text  # preserved verbatim
    assert "applyTo:" in out_text  # universal default synthesized


# M7-T4: vendor-install path filter --------------------------------------


def test_internal_paths_filtered_from_applyTo(tmp_path: Path) -> None:
    """`.agents/`, `.claude/`, `.serena/` globs MUST be dropped from applyTo.

    Source rules under .claude/rules/ reference internal repo paths that
    do not ship in any downstream install. Without filtering, generated
    .github/instructions/*.md files contain dead `applyTo` entries that
    match nothing in a vendor tree (PR #1819 thread 3161395651).
    """
    _write_rule(
        tmp_path / "rules_src",
        "security",
        frontmatter=(
            'paths: ".agents/security/**,**/Auth/**,*.env*,'
            '.github/workflows/**,.claude/rules/security.md"\n'
        ),
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    out = _read_output(tmp_path, "security")
    fm = out.split("---")[1]
    assert ".agents/security/**" not in fm
    assert ".claude/rules/security.md" not in fm
    # Non-internal globs MUST be preserved verbatim
    assert "**/Auth/**" in fm
    assert "*.env*" in fm
    assert ".github/workflows/**" in fm


def test_block_list_paths_flattened_to_applyTo_string(tmp_path: Path) -> None:
    """A `paths:` YAML block list MUST flatten to a comma-separated applyTo.

    Claude Code reads `paths` as a YAML list; the Copilot mirror expects a
    single comma-separated `applyTo` string. The simple frontmatter parser
    turns a block list into an inline-array string, so the generator flattens
    it before emit (no `[`/`]` brackets, no quote chars leak through).
    """
    _write_rule(
        tmp_path / "rules_src",
        "csharp",
        frontmatter='paths:\n  - "**/*.cs"\n  - "**/*.csproj"\ndescription: "C#"\n',
        body="# C#\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    fm = _read_output(tmp_path, "csharp").split("---")[1]
    assert "applyTo:" in fm
    assert "**/*.cs,**/*.csproj" in fm
    assert "[" not in fm and "]" not in fm
    assert "paths:" not in fm

def test_serialized_paths_list_rejects_comma_inside_item() -> None:
    """A comma inside a list item is ambiguous after flattening to applyTo."""
    with pytest.raises(generate_rules.GenerateRulesError, match="cannot contain commas"):
        generate_rules._flatten_serialized_scope_list("['docs/a,b/**', 'src/**']")


def test_serialized_paths_list_uses_python_parser_for_quoted_values() -> None:
    """Serialized lists should preserve quoted values without comma separators."""
    value = generate_rules._flatten_serialized_scope_list(
        "['docs/quoted\\'path/**', 'src/**']"
    )

    assert value == "docs/quoted'path/**,src/**"


def test_serialized_paths_list_falls_back_for_invalid_python_list() -> None:
    """Invalid serialized lists keep the legacy best-effort fallback."""
    value = generate_rules._flatten_serialized_scope_list("['docs/**', invalid]")
    assert value == "docs/**,invalid"


def test_block_list_paths_internal_globs_filtered(tmp_path: Path) -> None:
    """Internal-only globs MUST be dropped even when paths is a block list.

    The internal-glob filter splits on ",", so a block list (parsed into an
    inline-array string) must be flattened first; otherwise the `[`-prefixed
    first item would never match the internal-path prefixes. Regression guard
    for the paths-list flatten in `_remap_frontmatter`.
    """
    _write_rule(
        tmp_path / "rules_src",
        "security",
        frontmatter=(
            'paths:\n'
            '  - ".agents/security/**"\n'
            '  - "**/Auth/**"\n'
            '  - ".claude/rules/security.md"\n'
        ),
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    fm = _read_output(tmp_path, "security").split("---")[1]
    assert ".agents/security/**" not in fm
    assert ".claude/rules/security.md" not in fm
    assert "**/Auth/**" in fm
    assert "[" not in fm and "]" not in fm


def test_all_internal_paths_synthesizes_universal_scope(tmp_path: Path) -> None:
    """When every glob is internal-only, applyTo MUST fall back to '**'.

    Avoids emitting `applyTo: ""` (matches nothing) when a rule scoped
    only to internal paths gets fully filtered.
    """
    _write_rule(
        tmp_path / "rules_src",
        "internal_only",
        frontmatter='paths: ".agents/security/**,.claude/rules/foo.md,.serena/memories/**"\n',
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    out = _read_output(tmp_path, "internal_only")
    assert 'applyTo: "**"' in out or "applyTo: '**'" in out or "applyTo: **" in out


def test_serena_internal_path_filtered(tmp_path: Path) -> None:
    _write_rule(
        tmp_path / "rules_src",
        "memory",
        frontmatter='paths: ".serena/memories/**,docs/**"\n',
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    out = _read_output(tmp_path, "memory")
    fm = out.split("---")[1]
    assert ".serena/memories/**" not in fm
    assert "docs/**" in fm


def test_filter_emits_warning_per_dropped_glob(tmp_path: Path, capsys) -> None:
    """Each dropped internal-only glob MUST emit a stderr warning.

    Plugin authors who write `.agents/foo/**` in `paths` need a visible
    signal that the entry was filtered, not silent disappearance.
    """
    _write_rule(
        tmp_path / "rules_src",
        "noisy",
        frontmatter='paths: ".agents/x/**,docs/**,.claude/y/**"\n',
        body="b\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "WARNING: dropped internal-only glob" in captured.err
    assert ".agents/x/**" in captured.err
    assert ".claude/y/**" in captured.err
    # Surviving entry MUST NOT appear in warnings
    assert "docs/**" not in captured.err.split("WARNING:")[-1].split("\n")[0]


def test_filter_returns_dropped_list_for_caller_audit() -> None:
    """`_filter_internal_globs` returns (filtered, dropped) so callers
    can decide how to surface the audit."""
    filtered, dropped = generate_rules._filter_internal_globs(
        ".agents/a/**, docs/**, .claude/b/**, .serena/c/**"
    )
    assert filtered == "docs/**"
    assert sorted(dropped) == sorted([".agents/a/**", ".claude/b/**", ".serena/c/**"])


def test_filter_returns_empty_dropped_when_nothing_filtered() -> None:
    filtered, dropped = generate_rules._filter_internal_globs("docs/**, src/**")
    assert filtered == "docs/**,src/**"
    assert dropped == []


def test_filter_handles_whitespace_around_commas(tmp_path: Path) -> None:
    """`paths: ".agents/x/**, docs/**"` (note the space) must still filter."""
    _write_rule(
        tmp_path / "rules_src",
        "spaced",
        frontmatter='paths: ".agents/x/**, docs/**, .claude/y/**"\n',
        body="body\n",
    )
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    out = _read_output(tmp_path, "spaced")
    fm = out.split("---")[1]
    assert ".agents/" not in fm
    assert ".claude/" not in fm
    assert "docs/**" in fm


# M7-T4: orphan pruning -----------------------------------------------------


def test_orphan_instruction_file_is_pruned(tmp_path: Path) -> None:
    """An output file with no matching source MUST be deleted on regen.

    Without pruning, source deletions leave behind stale instruction
    files that re-introduce the internal-path leakage M7-T4 was meant
    to fix.
    """
    _write_rule(
        tmp_path / "rules_src", "live", frontmatter='paths: "src/**"\n', body="x\n"
    )
    out_dir = tmp_path / "instr_out"
    out_dir.mkdir(parents=True)
    orphan = out_dir / "deleted-source.instructions.md"
    orphan.write_text("---\napplyTo: .agents/internal/**\n---\nstale\n")
    cfg = _write_config(tmp_path)

    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert (out_dir / "live.instructions.md").is_file()
    assert not orphan.exists(), "orphan instruction file MUST be pruned"


def test_orphan_with_no_regen_sentinel_is_kept(tmp_path: Path) -> None:
    """NO-REGEN sentinel takes precedence: orphan stays untouched."""
    _write_rule(
        tmp_path / "rules_src", "live", frontmatter='paths: "src/**"\n', body="x\n"
    )
    out_dir = tmp_path / "instr_out"
    out_dir.mkdir(parents=True)
    protected = out_dir / "hand-edited.instructions.md"
    protected.write_text("<!-- NO-REGEN -->\nhand-edited do not touch\n")
    cfg = _write_config(tmp_path)

    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert protected.exists()
    assert "hand-edited" in protected.read_text()


# NO-REGEN sentinel ----------------------------------------------------------


def test_sentinel_html_comment_skips_overwrite(tmp_path: Path) -> None:
    _write_rule(
        tmp_path / "rules_src",
        "ci",
        frontmatter='paths: "scripts/**"\n',
        body="generated body\n",
    )
    out_dir = tmp_path / "instr_out"
    out_dir.mkdir(parents=True)
    target = out_dir / "ci.instructions.md"
    target.write_text("<!-- NO-REGEN -->\nhand-edited do not touch\n")

    cfg = _write_config(tmp_path)
    rc, result = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert result.sentinel_skipped == 1
    assert "hand-edited" in target.read_text()


# Configuration errors -------------------------------------------------------


def test_missing_artifacts_rules_returns_2(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text('schemaVersion: "1.0"\nprovider: "x"\n')
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


def test_no_rules_found_returns_1(tmp_path: Path) -> None:
    (tmp_path / "rules_src").mkdir()
    cfg = _write_config(tmp_path)
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 1


def test_absolute_source_dir_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "x"
artifacts:
  rules:
    sourceDir: "/etc/passwd"
    outputDir: "instr_out"
"""
    )
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


# CLI entry point ------------------------------------------------------------


def test_main_invokes_generation(tmp_path: Path) -> None:
    _write_rule(
        tmp_path / "rules_src", "ok", frontmatter='paths: "**"\n', body="ok\n",
    )
    cfg = _write_config(tmp_path)
    rc = generate_rules.main([
        "--config", str(cfg), "--repo-root", str(tmp_path),
    ])
    assert rc == 0


def test_main_missing_config_returns_2(tmp_path: Path) -> None:
    rc = generate_rules.main([
        "--config", str(tmp_path / "nope.yaml"), "--repo-root", str(tmp_path),
    ])
    assert rc == 2


# Multi-output (outputDirs) --------------------------------------------------


def _write_multi_output_config(tmp_path: Path, outputs: list[str]) -> Path:
    cfg = tmp_path / "platform.yaml"
    outputs_yaml = "\n".join(f'      - "{o}"' for o in outputs)
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDirs:
{outputs_yaml}
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
    frontmatterRemap:
      paths: applyTo
    frontmatterDrop:
      - alwaysApply
      - priority
"""
    )
    return cfg


def test_outputDirs_writes_to_every_target(tmp_path: Path) -> None:
    """outputDirs list emits one copy of each rule into every target dir.

    Why it matters: ships rules to .github/instructions/ (repo-internal
    Copilot) AND src/copilot-cli/instructions/ (plugin install tree) in
    a single generator run, so vendor installs via marketplace pick them
    up alongside agents/skills/hooks.
    """
    _write_rule(
        tmp_path / "rules_src",
        "demo",
        frontmatter='paths: "**/*.py"\n',
        body="Body.\n",
    )
    cfg = _write_multi_output_config(tmp_path, ["out_a", "out_b"])
    rc, result = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    assert result.written == 2  # one rule x two targets
    for sub in ("out_a", "out_b"):
        target = tmp_path / sub / "demo.instructions.md"
        assert target.is_file(), f"missing: {target}"
        content = target.read_text(encoding="utf-8")
        assert "applyTo: '**/*.py'" in content
        assert "paths:" not in content
    # Each audit entry must carry its destination so callers (and CI) can
    # tell which output dir an "emitted" or "skipped" outcome refers to.
    destinations = {e.destination for e in result.entries}
    assert destinations == {"out_a", "out_b"}, (
        f"audit entries lost destination info: {destinations}"
    )


def test_outputDirs_and_outputDir_both_set_returns_2(tmp_path: Path) -> None:
    """Setting both keys is a config error. Intent must be unambiguous."""
    _write_rule(tmp_path / "rules_src", "x", frontmatter='paths: "**"\n')
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDir: "single_out"
    outputDirs:
      - "list_out"
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
"""
    )
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


def test_outputDirs_empty_list_returns_2(tmp_path: Path) -> None:
    """Empty outputDirs is a config error (no destination = nothing to do)."""
    _write_rule(tmp_path / "rules_src", "x", frontmatter='paths: "**"\n')
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDirs: []
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
"""
    )
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


def test_neither_outputDir_nor_outputDirs_returns_2(tmp_path: Path) -> None:
    """Missing both keys is a config error."""
    _write_rule(tmp_path / "rules_src", "x", frontmatter='paths: "**"\n')
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
"""
    )
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


def test_outputDir_non_string_returns_2(tmp_path: Path) -> None:
    """A non-string outputDir is a config error; reject before str() coercion."""
    _write_rule(tmp_path / "rules_src", "x", frontmatter='paths: "**"\n')
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDir: 42
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
"""
    )
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


def test_outputDirs_with_non_string_element_returns_2(tmp_path: Path) -> None:
    """A non-string element in outputDirs is a config error."""
    _write_rule(tmp_path / "rules_src", "x", frontmatter='paths: "**"\n')
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        """\
schemaVersion: "1.0"
provider: "test"
artifacts:
  rules:
    sourceDir: "rules_src"
    outputDirs:
      - "valid_out"
      - 42
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
"""
    )
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 2


def test_outputDirs_prunes_orphans_in_every_target(tmp_path: Path) -> None:
    """Orphan pruning runs per output dir. Stale files removed from all targets."""
    _write_rule(tmp_path / "rules_src", "live", frontmatter='paths: "**"\n')
    for sub in ("out_a", "out_b"):
        d = tmp_path / sub
        d.mkdir()
        (d / "stale.instructions.md").write_text("---\napplyTo: \"**\"\n---\nstale\n")
    cfg = _write_multi_output_config(tmp_path, ["out_a", "out_b"])
    rc, _ = generate_rules.generate_rules(cfg, tmp_path)
    assert rc == 0
    for sub in ("out_a", "out_b"):
        assert (tmp_path / sub / "live.instructions.md").is_file()
        assert not (tmp_path / sub / "stale.instructions.md").exists(), (
            f"orphan not pruned in {sub}"
        )
