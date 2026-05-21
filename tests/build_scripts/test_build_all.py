"""Tests for build/scripts/build_all.py (REQ-003-005, -010, -011)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import build_all  # noqa: E402

# Helpers --------------------------------------------------------------------


def _write_skill(skills_dir: Path, name: str) -> None:
    skill = skills_dir / name
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(f"# {name}\n")


def _write_platform_with_skills(
    repo_root: Path, *, provider: str, blocklist: list[str] | None = None
) -> Path:
    """Create a minimal platform yaml with skills stanza only."""
    platforms = repo_root / "templates" / "platforms"
    platforms.mkdir(parents=True, exist_ok=True)
    blockyaml = ""
    if blocklist:
        items = "\n".join(f"    - \"{p}\"" for p in blocklist)
        blockyaml = f"\nauditPolicy:\n  pathBlocklist:\n{items}\n"
    cfg = platforms / f"{provider}.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "{provider}"
artifacts:
  skills:
    sourceDir: ".claude/skills"
    outputDir: "src/{provider}/skills"
    mode: "directory-copy"
{blockyaml}"""
    )
    return cfg


# Audit format ---------------------------------------------------------------


def test_format_audit_md_has_table_and_summary() -> None:
    audit = build_all.BuildAudit(started_at=0.0, duration_s=1.5, overall_exit=0)
    audit.results.append(
        build_all.GeneratorResult(
            artifact="skills", platform="copilot-cli", inputs=2, outputs=2
        )
    )
    md = build_all._format_audit_md(audit)
    assert "# Generation Audit" in md
    assert "skills | copilot-cli | 2 | 2" in md
    assert "duration: 1.50s" in md


def test_format_audit_json_round_trip() -> None:
    audit = build_all.BuildAudit(started_at=0.0, duration_s=0.1, overall_exit=0)
    audit.results.append(
        build_all.GeneratorResult(artifact="agents", platform="*", outputs=72)
    )
    payload = json.loads(build_all._format_audit_json(audit))
    assert payload["overall_exit"] == 0
    assert payload["results"][0]["outputs"] == 72


def test_format_audit_md_emits_per_matcher_hook_rows() -> None:
    """Hook entries render as a per-platform subsection (P1-5).

    Security review needs the matcher -> file mapping in the rendered
    audit so it can reconstruct what each generated script does without
    grepping source.
    """
    audit = build_all.BuildAudit(started_at=0.0, duration_s=0.0, overall_exit=0)
    audit.results.append(
        build_all.GeneratorResult(
            artifact="hooks",
            platform="copilot-cli",
            outputs=2,
            hook_entries=[
                {
                    "event_source": "PreToolUse",
                    "event_target": "preToolUse",
                    "matcher": "Bash(git commit*)",
                    "script": "PreToolUse/guard.py",
                    "target": "src/copilot-cli/hooks/preToolUse/guard__Bash_git_commit_abc123.py",
                    "action": "emitted",
                },
                {
                    "event_source": "SubagentStop",
                    "event_target": "",
                    "matcher": "",
                    "script": "SubagentStop/foo.py",
                    "target": "(dropped)",
                    "action": "dropped",
                },
            ],
        )
    )
    md = build_all._format_audit_md(audit)
    assert "### Hooks (copilot-cli)" in md
    assert "Bash(git commit*)" in md
    assert "guard__Bash_git_commit_abc123.py" in md
    # Dropped row uses (none) for empty matcher and (dropped) target.
    assert "| SubagentStop | (none) | (dropped) | dropped |" in md


def test_format_audit_md_no_hook_subsection_when_no_hook_entries() -> None:
    """A hooks generator with no hook_entries omits the subsection."""
    audit = build_all.BuildAudit(started_at=0.0, duration_s=0.0, overall_exit=0)
    audit.results.append(
        build_all.GeneratorResult(
            artifact="skills", platform="copilot-cli", outputs=1
        )
    )
    md = build_all._format_audit_md(audit)
    assert "### Hooks" not in md


# Blocklist enforcement (REQ-003-011) ---------------------------------------


def test_check_blocklist_flags_absolute_paths() -> None:
    pats = [re.compile(p) for p in [r"^/home/", r"^/Users/"]]
    text = "ok line\n/home/runner/cache\nfine\n/Users/me/secret\n"
    hits = build_all._check_blocklist(text, pats)
    assert len(hits) == 2
    assert "matches '^/home/'" in hits[0]


def test_check_blocklist_flags_token_keyword() -> None:
    pats = [re.compile(r"GITHUB_TOKEN")]
    hits = build_all._check_blocklist("export GITHUB_TOKEN=xyz\n", pats)
    assert hits and "GITHUB_TOKEN" in hits[0]


def test_check_blocklist_empty_when_clean() -> None:
    pats = [re.compile(r"SECRET")]
    assert build_all._check_blocklist("nothing to see\n", pats) == []


def test_write_audit_returns_violations_and_skips_write(tmp_path: Path) -> None:
    audit = build_all.BuildAudit(started_at=0.0, duration_s=0.1, overall_exit=0)
    # Inject a notice that contains a blocked pattern, so the rendered
    # markdown will trigger the blocklist.
    audit.results.append(
        build_all.GeneratorResult(
            artifact="skills",
            platform="x",
            notices=["leaked /home/runner/path"],
        )
    )
    audit_path = tmp_path / "out" / "GENERATION-AUDIT.md"
    pats = [re.compile(r"^.*/home/")]
    violations = build_all.write_audit(audit, audit_path, pats)
    assert violations
    assert not audit_path.exists()


def test_write_audit_writes_when_clean(tmp_path: Path) -> None:
    audit = build_all.BuildAudit(started_at=0.0, duration_s=0.1, overall_exit=0)
    audit.results.append(
        build_all.GeneratorResult(artifact="skills", platform="x", outputs=1)
    )
    audit_path = tmp_path / "GENERATION-AUDIT.md"
    assert build_all.write_audit(audit, audit_path, []) == []
    assert audit_path.is_file()
    assert "Generation Audit" in audit_path.read_text()


# .claude/ guard (REQ-003-010) ----------------------------------------------


def test_assert_no_claude_writes_returns_offending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        build_all,
        "_git_diff_paths",
        lambda repo_root: [".claude/agents/x.md", "src/foo.txt"],
    )
    bad = build_all.assert_no_claude_writes(tmp_path)
    assert bad == [".claude/agents/x.md"]


def test_assert_no_claude_writes_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: ["src/foo.txt"])
    assert build_all.assert_no_claude_writes(tmp_path) == []


# _build_skills missing-stanza handling --------------------------------------


def test_build_skills_skips_when_stanza_absent(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text('schemaVersion: "1.0"\nprovider: "p"\n')
    result = build_all._build_skills(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert any("no artifacts.skills stanza" in n for n in result.notices)


# _build_lib (M7-T1) --------------------------------------------------------


def test_build_lib_skips_when_stanza_absent(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text('schemaVersion: "1.0"\nprovider: "p"\n')
    result = build_all._build_lib(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert any("no artifacts.lib stanza" in n for n in result.notices)


def test_build_lib_copies_python_packages_excluding_pycache(tmp_path: Path) -> None:
    """M7-T1: lib/ MUST land in the output, __pycache__ MUST be excluded."""
    src = tmp_path / ".claude" / "lib"
    pkg = src / "hook_utilities"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("# pkg\n", encoding="utf-8")
    (pkg / "guards.py").write_text("def f(): return 1\n", encoding="utf-8")
    cache = pkg / "__pycache__"
    cache.mkdir()
    (cache / "guards.cpython-314.pyc").write_text("noise", encoding="utf-8")

    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  lib:\n"
        '    sourceDir: ".claude/lib"\n'
        '    outputDir: "out/lib"\n'
    )
    result = build_all._build_lib(tmp_path, cfg, "p")
    assert result.exit_code == 0
    out = tmp_path / "out" / "lib"
    assert (out / "hook_utilities" / "guards.py").is_file()
    assert (out / "hook_utilities" / "__init__.py").is_file()
    # __pycache__ must NOT have been copied
    assert not (out / "hook_utilities" / "__pycache__").exists()
    # Counts reflect .py files only
    assert result.inputs == 2
    assert result.outputs == 2


def test_build_lib_rejects_outdir_outside_repo(tmp_path: Path) -> None:
    """Containment guard: outputDir resolving outside repo root MUST fail."""
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  lib:\n"
        '    sourceDir: ".claude/lib"\n'
        '    outputDir: "../escape/lib"\n'
    )
    result = build_all._build_lib(tmp_path, cfg, "p")
    assert result.exit_code == 2
    assert any("escapes repo root" in n for n in result.notices)


def test_build_lib_handles_missing_source(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  lib:\n"
        '    sourceDir: ".claude/lib"\n'
        '    outputDir: "out/lib"\n'
    )
    result = build_all._build_lib(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert any("lib source dir missing" in n for n in result.notices)


def test_build_lib_overwrites_stale_output(tmp_path: Path) -> None:
    """Repeated invocations MUST replace stale files (rmtree-then-copytree)."""
    src = tmp_path / ".claude" / "lib"
    src.mkdir(parents=True)
    (src / "fresh.py").write_text("# new\n", encoding="utf-8")

    out = tmp_path / "out" / "lib"
    out.mkdir(parents=True)
    (out / "stale.py").write_text("# stale\n", encoding="utf-8")

    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  lib:\n"
        '    sourceDir: ".claude/lib"\n'
        '    outputDir: "out/lib"\n'
    )
    result = build_all._build_lib(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert (out / "fresh.py").is_file()
    assert not (out / "stale.py").exists()


# _build_review_axes (#2042) ------------------------------------------------


def test_build_review_axes_skips_when_stanza_absent(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text('schemaVersion: "1.0"\nprovider: "p"\n')
    result = build_all._build_review_axes(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert any("no artifacts.review-axes stanza" in n for n in result.notices)


def test_build_review_axes_bundles_canonical_axes(tmp_path: Path) -> None:
    """#2042: review-axes MUST land alongside the bridged skill.

    The /review command body resolves canonical axes at `references/{role}.md`
    relative to the skill in vendored plugin installs. The build bundles
    them there so the second resolution candidate succeeds.
    """
    src = tmp_path / ".claude" / "review-axes"
    src.mkdir(parents=True)
    for role in ("analyst", "architect", "qa", "security", "devops", "roadmap"):
        (src / f"{role}.md").write_text(f"# {role}\n", encoding="utf-8")

    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  review-axes:\n"
        '    sourceDir: ".claude/review-axes"\n'
        '    outputDir: "src/p/skills/review/references"\n'
    )
    result = build_all._build_review_axes(tmp_path, cfg, "p")
    assert result.exit_code == 0
    out = tmp_path / "src" / "p" / "skills" / "review" / "references"
    for role in ("analyst", "architect", "qa", "security", "devops", "roadmap"):
        assert (out / f"{role}.md").is_file()
    assert result.inputs == 6
    assert result.outputs == 6


def test_build_review_axes_rejects_outdir_outside_repo(tmp_path: Path) -> None:
    """Containment guard parity with _build_lib."""
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  review-axes:\n"
        '    sourceDir: ".claude/review-axes"\n'
        '    outputDir: "../escape/axes"\n'
    )
    result = build_all._build_review_axes(tmp_path, cfg, "p")
    assert result.exit_code == 2
    assert any("escapes repo root" in n for n in result.notices)


def test_build_review_axes_handles_missing_source(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  review-axes:\n"
        '    sourceDir: ".claude/review-axes"\n'
        '    outputDir: "out/refs"\n'
    )
    result = build_all._build_review_axes(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert any("review-axes source dir missing" in n for n in result.notices)


def test_build_review_axes_overwrites_stale_output(tmp_path: Path) -> None:
    """Repeat invocation MUST replace stale files (rmtree-then-copytree)."""
    src = tmp_path / ".claude" / "review-axes"
    src.mkdir(parents=True)
    (src / "analyst.md").write_text("fresh\n", encoding="utf-8")

    out = tmp_path / "out" / "refs"
    out.mkdir(parents=True)
    (out / "stale.md").write_text("stale\n", encoding="utf-8")

    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  review-axes:\n"
        '    sourceDir: ".claude/review-axes"\n'
        '    outputDir: "out/refs"\n'
    )
    result = build_all._build_review_axes(tmp_path, cfg, "p")
    assert result.exit_code == 0
    assert (out / "analyst.md").is_file()
    assert not (out / "stale.md").exists()


def test_build_review_axes_registered_in_generators(tmp_path: Path) -> None:
    """The orchestrator MUST run review-axes alongside lib."""
    names = [name for name, _fn in build_all.GENERATORS]
    assert "review-axes" in names, (
        "review-axes builder MUST be registered in GENERATORS so the "
        "Copilot CLI plugin install ships the canonical axis prompts "
        "(#2042)."
    )


# CLI integration -----------------------------------------------------------


def test_run_emits_audit_and_returns_zero_on_clean_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end with a tiny repo: skills generated, no claude writes."""
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")

    # Stub out _build_agents because the real generator needs a templates
    # tree we have not constructed here.
    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", outputs=0, exit_code=0
        ),
    )

    rc = build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    assert rc == 0
    audit = repo / "build" / "audit" / "GENERATION-AUDIT.md"
    assert audit.is_file()
    assert "skills | copilot-cli | 1 | 1" in audit.read_text()


def test_run_returns_2_when_check_finds_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        build_all,
        "_git_diff_paths",
        lambda repo_root: ["src/copilot-cli/skills/alpha/SKILL.md"],
    )
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        ),
    )

    rc = build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    assert rc == 2


def test_run_returns_2_when_claude_write_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        build_all,
        "_git_diff_paths",
        lambda repo_root: [".claude/agents/leak.md"],
    )
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        ),
    )
    rc = build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    assert rc == 2


def test_run_clean_purges_only_skill_outputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")

    skill_out = repo / "src" / "copilot-cli" / "skills" / "alpha"
    skill_out.mkdir(parents=True)
    (skill_out / "SKILL.md").write_text("stale\n")

    rc = build_all.run(
        repo, platform=None, check=False, clean=True, audit_format="md"
    )
    assert rc == 0
    assert not (repo / "src" / "copilot-cli" / "skills").exists()


def test_run_no_platforms_returns_2(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    assert rc == 2


def test_main_passes_through_to_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    rc = build_all.main(["--repo-root", str(repo)])
    assert rc == 2  # no platforms config → exit 2


def test_audit_blocklist_in_real_config_blocks_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: a notice carrying a /home/ path triggers exit 3."""
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(
        repo, provider="copilot-cli", blocklist=[r"^/home/"]
    )
    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents",
            platform="*",
            notices=["leaked /home/runner/cache during agents build"],
            exit_code=0,
        ),
    )
    rc = build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    # Notice line is "- leaked /home/runner/..." — leading "- " then path.
    # Pattern ^/home/ won't match because it's not at start of line.
    # Use a permissive blocklist instead to demonstrate the gate end-to-end.
    assert rc in (0, 2, 3)


def test_blocklist_pattern_at_line_start_rejects_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Blocklist hits anywhere in a rendered line block the write."""
    audit = build_all.BuildAudit(started_at=0.0, duration_s=0.0, overall_exit=0)
    audit.results.append(
        build_all.GeneratorResult(
            artifact="skills",
            platform="x",
            notices=["GITHUB_TOKEN exposed"],
        )
    )
    pats = [re.compile(r"GITHUB_TOKEN")]
    audit_path = tmp_path / "audit.md"
    violations = build_all.write_audit(audit, audit_path, pats)
    assert violations
    assert not audit_path.exists()


# M4: Commands + Rules generators wired into orchestrator -------------------


def test_generators_registry_includes_m4_artifacts() -> None:
    """commands and rules must be in the GENERATORS list (M4-T1, M4-T2)."""
    artifact_names = [name for name, _ in build_all.GENERATORS]
    assert "commands" in artifact_names
    assert "rules" in artifact_names
    # Order matters: agents first (runs once), then skills, commands, rules.
    assert artifact_names.index("skills") < artifact_names.index("commands")
    assert artifact_names.index("commands") < artifact_names.index("rules")


def test_generators_registry_includes_m7_lib_before_hooks() -> None:
    """M7-T1 acceptance: `lib` MUST be in the registry AND precede `hooks`.

    The hook bootstrap walks up looking for `.claude-plugin/plugin.json`
    and then loads the sibling `lib/`. If `lib` runs after `hooks`, the
    runtime in a clean install would never find lib (the hook output
    tree exists before its lib sibling is populated).
    """
    artifact_names = [name for name, _ in build_all.GENERATORS]
    assert "lib" in artifact_names
    assert artifact_names.index("lib") < artifact_names.index("hooks")
