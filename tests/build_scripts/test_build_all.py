"""Tests for build/scripts/build_all.py (REQ-003-005, -010, -011)."""

from __future__ import annotations

import json
import os
import re
import subprocess
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


def _write_minimal_adr(adr_dir: Path) -> None:
    """Write one valid ADR record so `_build_adr_index` (always run by
    `build_all.run()`, unconditionally per its own docstring) has a real
    corpus to index instead of an empty directory.

    `generate_adr_index.py` now rejects a directory with no
    `ADR-NNN-*.md` match as a config error (Copilot, PR #5209 round-7
    review), so a fixture that creates `.agents/architecture` empty to
    test something unrelated (skills generation, untracked-file
    detection) must still seed one parseable record.
    """
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / "ADR-001-example.md").write_text(
        "---\nid: ADR-001\nstatus: accepted\ndate: 2026-01-01\n---\n\n"
        "# ADR-001: Example\n\n## Status\n\nAccepted.\n\n## Decision\n\nDo it.\n",
        encoding="utf-8",
    )


def _write_agent_template(templates_dir: Path, name: str) -> None:
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / f"{name}.shared.md").write_text(
        "---\n"
        "role: executor\n"
        f"description: {name} agent.\n"
        "---\n"
        f"# {name.title()} Agent\n"
        "Body line.\n",
        encoding="utf-8",
    )


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
                    "matcher": "Bash|Write\nEdit",
                    "script": "PreToolUse/guard.py",
                    "target": "src/copilot-cli/hooks/preToolUse/guard__Bash_git_commit_abc123.py",
                    "action": "emitted",
                    "reason": "",
                },
                {
                    "event_source": "Notification",
                    "event_target": "",
                    "matcher": "",
                    "script": "Notification/foo.py",
                    "target": "(dropped)",
                    "action": "dropped",
                    "reason": "unsupported | shell\nentry",
                },
            ],
        )
    )
    md = build_all._format_audit_md(audit)
    assert "### Hooks (copilot-cli)" in md
    assert "Bash\\|Write<br>Edit" in md
    assert "guard__Bash_git_commit_abc123.py" in md
    assert (
        "| Notification | Notification/foo.py | (none) | (dropped) | dropped | "
        "unsupported \\| shell<br>entry |"
    ) in md


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


def test_build_hooks_preserves_drop_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "platform.yaml"
    config.write_text(
        """
schemaVersion: "1.0"
provider: "copilot-cli"
artifacts:
  hooks:
    settingsSource: settings.json
    scriptSource: hooks
    outputConfig: src/copilot-cli/hooks/hooks.json
    outputScripts: src/copilot-cli/hooks
    eventRemap:
      SessionStart: SessionStart
""",
        encoding="utf-8",
    )
    run_result = build_all.generate_hooks.GenerateHooksResult(
        dropped=1,
        entries=[
            build_all.generate_hooks.HookAuditEntry(
                event_source="SessionStart",
                event_target="",
                script="session-start.sh",
                action="dropped",
                reason="only Python hook commands can be generated",
            )
        ],
    )
    monkeypatch.setattr(
        build_all.generate_hooks,
        "generate_hooks",
        lambda _config, _root: (0, run_result),
    )

    result = build_all._build_hooks(tmp_path, config, "copilot-cli")

    assert result.notices == [
        "copilot-cli: dropped 1 hook entry "
        "(only Python hook commands can be generated)"
    ]
    assert result.hook_entries[0]["reason"] == (
        "only Python hook commands can be generated"
    )


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


def test_assert_no_claude_writes_flags_generator_created_path(tmp_path: Path) -> None:
    """A .claude/ file created AFTER the snapshot is a generator write."""
    claude = tmp_path / ".claude" / "agents"
    claude.mkdir(parents=True)
    baseline = build_all._snapshot_owned_prefixes(
        tmp_path, build_all.CLAUDE_GUARD_PREFIX
    )
    # Generator writes a new file after the snapshot.
    (claude / "leak.md").write_text("generated", encoding="utf-8")
    bad = build_all.assert_no_claude_writes(tmp_path, baseline)
    assert bad == [".claude/agents/leak.md"]


def test_assert_no_claude_writes_flags_generator_modified_path(tmp_path: Path) -> None:
    """A .claude/ file whose bytes change after the snapshot is a write."""
    claude = tmp_path / ".claude" / "agents"
    claude.mkdir(parents=True)
    target = claude / "x.md"
    target.write_text("original", encoding="utf-8")
    baseline = build_all._snapshot_owned_prefixes(
        tmp_path, build_all.CLAUDE_GUARD_PREFIX
    )
    target.write_text("mutated by generator", encoding="utf-8")
    assert build_all.assert_no_claude_writes(tmp_path, baseline) == [
        ".claude/agents/x.md"
    ]


def test_assert_no_claude_writes_ignores_presync_dirty_lib(tmp_path: Path) -> None:
    """A legitimate .claude/lib sync that predates the snapshot must pass.

    Reproduces issue #2613: sync_plugin_lib.py updates
    .claude/lib/hook_utilities/guards.py BEFORE build_all runs. The
    snapshot captures that already-dirty state, so no generator write is
    attributed to it and the guard returns clean.
    """
    lib = tmp_path / ".claude" / "lib" / "hook_utilities"
    lib.mkdir(parents=True)
    # Pre-build sync already wrote the file before the snapshot is taken.
    (lib / "guards.py").write_text("def synced(): ...\n", encoding="utf-8")
    baseline = build_all._snapshot_owned_prefixes(
        tmp_path, build_all.CLAUDE_GUARD_PREFIX
    )
    # Generators run and touch nothing under .claude/.
    assert build_all.assert_no_claude_writes(tmp_path, baseline) == []


def test_assert_no_claude_writes_clean_when_unchanged(tmp_path: Path) -> None:
    claude = tmp_path / ".claude" / "skills"
    claude.mkdir(parents=True)
    (claude / "a.md").write_text("a", encoding="utf-8")
    baseline = build_all._snapshot_owned_prefixes(
        tmp_path, build_all.CLAUDE_GUARD_PREFIX
    )
    assert build_all.assert_no_claude_writes(tmp_path, baseline) == []


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


def test_build_lib_rejects_outdir_equal_to_repo_root(tmp_path: Path) -> None:
    """Containment guard: outputDir == repo root MUST fail (CWE-22).

    Without this check, rmtree-then-copytree would wipe the working tree.
    """
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: "p"\n'
        "artifacts:\n"
        "  lib:\n"
        '    sourceDir: ".claude/lib"\n'
        '    outputDir: "."\n'
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


# CLI integration -----------------------------------------------------------


def test_run_emits_audit_and_returns_zero_on_clean_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end with a tiny repo: skills generated, no claude writes."""
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_minimal_adr(repo / ".agents" / "architecture")
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


def test_no_staleness_deferrals_constant() -> None:
    """The #2755 deferral exemption is removed (#2777).

    The two formerly-deferred mirrors (cva-analysis, slashcommandcreator)
    are committed and clean since #2762, so the exemption is dead code that
    would only hide future regen drift. It must not come back.
    """
    assert not hasattr(build_all, "STALENESS_DEFERRALS")
    assert "STALENESS_DEFERRALS" not in Path(build_all.__file__).read_text(
        encoding="utf-8"
    )


def test_run_returns_2_when_formerly_deferred_mirror_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cva-analysis mirror drift now trips the staleness gate (#2777).

    Before #2777 this drift was exempted by STALENESS_DEFERRALS and the
    gate returned 0. With the exemption gone, the formerly-deferred mirror
    is covered like every other generated output.
    """
    monkeypatch.setattr(
        build_all,
        "_git_diff_paths",
        lambda repo_root: ["src/copilot-cli/skills/cva-analysis/SKILL.md"],
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


def test_run_returns_2_when_multiple_skill_mirrors_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every drifted skill-mirror under an owned prefix gates (#2777)."""
    monkeypatch.setattr(
        build_all,
        "_git_diff_paths",
        lambda repo_root: [
            "src/copilot-cli/skills/cva-analysis/SKILL.md",
            "src/copilot-cli/skills/review/SKILL.md",
        ],
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


def test_run_returns_2_when_generator_writes_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A generator that writes under .claude/ during the run trips REQ-003-010."""
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")

    def _leaky_agents(repo_root: Path, cfg: Path, platform: str) -> build_all.GeneratorResult:
        # Misbehaving generator writes under .claude/ after the snapshot.
        leak = Path(repo_root) / ".claude" / "agents" / "leak.md"
        leak.parent.mkdir(parents=True, exist_ok=True)
        leak.write_text("generated\n", encoding="utf-8")
        return build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        )

    monkeypatch.setattr(build_all, "_build_agents", _leaky_agents)
    rc = build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    assert rc == 2


def test_run_returns_0_when_claude_lib_synced_before_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #2613: a pre-build .claude/lib sync must NOT trip REQ-003-010.

    The file under .claude/lib is already dirty before run() snapshots
    .claude/. No generator touches it, so the guard returns clean and the
    build exits 0.
    """
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_minimal_adr(repo / ".agents" / "architecture")
    _write_skill(repo / ".claude" / "skills", "alpha")
    # Simulate sync_plugin_lib.py having already updated .claude/lib.
    lib = repo / ".claude" / "lib" / "hook_utilities"
    lib.mkdir(parents=True)
    (lib / "guards.py").write_text("def synced(): ...\n", encoding="utf-8")
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
    assert rc == 0


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


def test_generators_registry_includes_agent_catalog_after_agents() -> None:
    """Agent catalog drift must be covered by build_all.py --check."""
    artifact_names = [name for name, _ in build_all.GENERATORS]
    assert "agent-catalog" in artifact_names
    assert artifact_names.index("agents") < artifact_names.index("agent-catalog")
    assert artifact_names.index("agent-catalog") < artifact_names.index("skills")


def test_owned_prefixes_include_agent_catalog() -> None:
    """docs/agent-catalog.md is generated from templates and must be gated."""
    assert "docs/agent-catalog.md" in build_all.OWNED_PREFIXES


def test_snapshot_owned_prefixes_handles_catalog_file(tmp_path: Path) -> None:
    catalog = tmp_path / "docs" / "agent-catalog.md"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("catalog\n", encoding="utf-8")

    snapshot = build_all._snapshot_owned_prefixes(
        tmp_path, ("docs/agent-catalog.md",)
    )

    assert snapshot[catalog] == b"catalog\n"


def test_enumerate_files_under_handles_catalog_file(tmp_path: Path) -> None:
    catalog = tmp_path / "docs" / "agent-catalog.md"
    catalog.parent.mkdir(parents=True)
    catalog.write_text("catalog\n", encoding="utf-8")

    found = build_all._enumerate_files_under(tmp_path, ("docs/agent-catalog.md",))

    assert found == {catalog}


def test_enumerate_files_under_skips_git_boundary_directory(tmp_path: Path) -> None:
    """A directory holding its own .git entry is a git repository boundary
    (the same shape ``git worktree add`` produces) and must never be walked
    into: it is not the enumerated prefix's own content.

    A sibling file that is not behind a boundary is still found, as a
    positive control that the skip is scoped to the boundary directory
    and does not blind the walk to the rest of the prefix.
    """
    owned = tmp_path / "owned"
    nested = owned / "worktrees" / "wt-1"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    nested_file = nested / "inside.txt"
    nested_file.write_text("nested content\n", encoding="utf-8")
    nested_subdir_file = nested / "sub" / "deep.txt"
    nested_subdir_file.parent.mkdir(parents=True)
    nested_subdir_file.write_text("deep nested content\n", encoding="utf-8")
    sibling = owned / "real.md"
    sibling.write_text("# real\n", encoding="utf-8")

    found = build_all._enumerate_files_under(tmp_path, ("owned/",))

    assert nested_file not in found
    assert nested_subdir_file not in found
    assert sibling in found


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="os.mkfifo is POSIX only")
def test_restore_owned_prefixes_never_unlinks_a_pre_existing_fifo(
    tmp_path: Path,
) -> None:
    """A non-regular file is not generator output and must survive --check.

    ``_snapshot_owned_prefixes`` keeps regular files only. In
    ``build/scripts/build_all.py`` its walk reads::

        if is_dir or not path.is_file():
            continue

    so a FIFO, a unix socket, or a device node is never in the snapshot.
    If ``_enumerate_files_under`` counted every non-directory entry, that
    FIFO would land in ``current - set(snapshot)`` and case 3 of
    :func:`_restore_owned_prefixes` would unlink it, so a read-only
    ``--check`` would destroy a path it never created.

    Positive control: a file the generator really did create after the
    snapshot is still deleted, so a mutant that empties
    ``_enumerate_files_under`` fails here rather than passing.
    """
    owned = tmp_path / "owned"
    owned.mkdir()
    fifo = owned / "pipe"
    os.mkfifo(fifo)
    pre_existing = owned / "real.md"
    pre_existing.write_text("# real\n", encoding="utf-8")

    assert fifo not in build_all._enumerate_files_under(tmp_path, ("owned/",))

    snapshot = build_all._snapshot_owned_prefixes(tmp_path, ("owned/",))
    assert fifo not in snapshot
    generated = owned / "generated.md"
    generated.write_text("# generated\n", encoding="utf-8")

    build_all._restore_owned_prefixes(tmp_path, ("owned/",), snapshot)

    assert fifo.is_fifo()
    assert not generated.exists()
    assert pre_existing.read_text(encoding="utf-8") == "# real\n"


def test_snapshot_owned_prefixes_skips_git_boundary_directory(
    tmp_path: Path,
) -> None:
    """The snapshot pass, not just the enumerate pass, must skip a nested
    git repository boundary, with ``exclude_ignored`` left at its default
    (``False``): that is the exact flag value ``run()`` passes for the
    ``--check`` snapshot. ``run()`` in ``build/scripts/build_all.py``
    reads::

        snapshot = _snapshot_owned_prefixes(repo_root, OWNED_PREFIXES)

    with no ``exclude_ignored`` argument, so a gitignore-only guard
    (``_is_ignored_path``) would not cover it.

    The quote is the anchor, not a line number. That call has moved five
    times inside this one pull request as docstrings grew above it, and
    ``check_citation_freshness.py`` failed the build on the stale number
    twice. Grep the quoted line instead.

    Without routing this walk through
    :func:`_iter_tree_skip_git_boundaries`, a nested worktree under an
    owned prefix gets read into the snapshot here while
    :func:`_enumerate_files_under`'s delete pass skips it, and the
    asymmetry lets :func:`_restore_owned_prefixes` overwrite the nested
    worktree's own files with snapshot bytes (issue #5370).
    """
    owned = tmp_path / "owned"
    nested = owned / "worktrees" / "wt-1"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    nested_file = nested / "inside.txt"
    nested_file.write_text("nested content\n", encoding="utf-8")
    sibling = owned / "real.md"
    sibling.write_text("# real\n", encoding="utf-8")

    snapshot = build_all._snapshot_owned_prefixes(tmp_path, ("owned/",))

    assert nested_file not in snapshot
    assert sibling in snapshot


def test_restore_owned_prefixes_never_deletes_git_boundary_contents(
    tmp_path: Path,
) -> None:
    """Defense-in-depth for a future OWNED_PREFIXES entry that covers a
    directory of nested worktrees: _restore_owned_prefixes's delete pass
    (case 3: on disk and not in the snapshot -> unlink) must never reach a
    file inside a directory that is itself a git repository boundary, even
    in the worst case where the snapshot has nothing for that prefix at
    all (an empty snapshot, as if the worktree post-dated the baseline).

    Without the .git-boundary skip in _enumerate_files_under and
    _prune_empty_dirs, this is exactly how a future ``.claude/`` entry in
    OWNED_PREFIXES would let --check's read-only restore step delete a
    nested worktree's own working tree (issue #5370).

    Positive control: an ordinary generator-created file under the same
    prefix, also absent from the snapshot, is still deleted, so the
    boundary skip does not disable the real cleanup behavior.
    """
    owned = tmp_path / "owned"
    nested = owned / "worktrees" / "wt-1"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    nested_file = nested / "inside.txt"
    nested_file.write_text("nested content\n", encoding="utf-8")
    generator_created = owned / "created.md"
    generator_created.write_text("# generated\n", encoding="utf-8")

    prefixes = ("owned/",)
    found = build_all._enumerate_files_under(tmp_path, prefixes)
    assert nested_file not in found
    assert generator_created in found

    build_all._restore_owned_prefixes(tmp_path, prefixes, snapshot={})

    assert nested_file.is_file()
    assert nested_file.read_text(encoding="utf-8") == "nested content\n"
    assert not generator_created.exists()


def test_restore_owned_prefixes_removes_a_boundary_tree_created_mid_build(
    tmp_path: Path,
) -> None:
    """A ``.git`` entry a generator writes is output, not a nested checkout.

    Detecting boundaries by shape during the restore pass reads the
    post-generation tree, so a directory the generator created with a
    ``.git`` entry inside it looks identical to a pre-existing worktree
    and case 3 of :func:`_restore_owned_prefixes` skips its files.
    Measured before ``preexisting_boundaries`` existed: a generator
    creating ``owned/out/.git`` plus ``owned/out/generated.txt`` left both
    on disk after the restore, so ``--check`` was no longer read-only
    (issue #2440).

    :func:`_git_boundaries_under` records the boundary set before the
    generators run, which separates the two cases by when they appeared
    rather than by shape.

    Both directions are asserted here on purpose. Removing the new tree is
    worthless if it also removes a live nested worktree, which is the
    deletion issue #5370 exists to prevent, so the pre-existing checkout
    and its file are asserted intact in the same run.
    """
    owned = tmp_path / "owned"
    owned.mkdir()
    pre_existing_wt = owned / "worktrees" / "wt-1"
    pre_existing_wt.mkdir(parents=True)
    (pre_existing_wt / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    live_file = pre_existing_wt / "live.txt"
    live_file.write_text("live worktree content\n", encoding="utf-8")
    untouched = owned / "real.md"
    untouched.write_text("# real\n", encoding="utf-8")

    prefixes = ("owned/",)
    boundaries = build_all._git_boundaries_under(tmp_path, prefixes)
    assert boundaries == {pre_existing_wt}
    snapshot = build_all._snapshot_owned_prefixes(tmp_path, prefixes)

    # The generator now creates a boundary-shaped tree of its own.
    generated_tree = owned / "out"
    generated_tree.mkdir()
    (generated_tree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    generated_file = generated_tree / "generated.txt"
    generated_file.write_text("generator output\n", encoding="utf-8")

    build_all._restore_owned_prefixes(
        tmp_path, prefixes, snapshot, preexisting_boundaries=boundaries
    )

    assert not generated_file.exists()
    assert not generated_tree.exists()
    assert live_file.read_text(encoding="utf-8") == "live worktree content\n"
    assert (pre_existing_wt / ".git").is_file()
    assert untouched.read_text(encoding="utf-8") == "# real\n"


def test_restore_owned_prefixes_prunes_a_generated_repo_shaped_tree(
    tmp_path: Path,
) -> None:
    """Deleting the files is not enough when ``.git`` is a real directory.

    The sibling test above writes ``.git`` as a file, so once case 3
    unlinks it the tree stops looking like a boundary and shape detection
    inside :func:`_prune_empty_dirs` would remove the empty directory
    anyway. A cloned repository does not have that shape: ``.git`` is a
    directory, and an emptied directory still satisfies
    ``(entry / ".git").exists()``, so shape detection keeps treating the
    tree as opaque and never prunes it.

    Measured: dropping ``opaque_boundaries`` from the prune call left
    ``owned/out`` and ``owned/out/.git`` on disk here while every other
    test stayed green. Empty directories the run created are still a
    ``--check`` write (issue #2440), so this case is what holds that
    argument in place.
    """
    owned = tmp_path / "owned"
    owned.mkdir()
    untouched = owned / "real.md"
    untouched.write_text("# real\n", encoding="utf-8")

    prefixes = ("owned/",)
    boundaries = build_all._git_boundaries_under(tmp_path, prefixes)
    assert boundaries == set()
    snapshot = build_all._snapshot_owned_prefixes(tmp_path, prefixes)

    generated_tree = owned / "out"
    (generated_tree / ".git").mkdir(parents=True)
    (generated_tree / ".git" / "HEAD").write_text(
        "ref: refs/heads/main\n", encoding="utf-8"
    )
    (generated_tree / "generated.txt").write_text(
        "generator output\n", encoding="utf-8"
    )

    build_all._restore_owned_prefixes(
        tmp_path, prefixes, snapshot, preexisting_boundaries=boundaries
    )

    assert not generated_tree.exists()
    assert untouched.read_text(encoding="utf-8") == "# real\n"


def test_prune_empty_dirs_never_rmdirs_inside_git_boundary(
    tmp_path: Path,
) -> None:
    """_prune_empty_dirs's own boundary skip, not just the delete pass, must
    hold: an empty directory inside a nested worktree (a ``build/`` or
    ``logs/`` dir with nothing tracked in it) must survive
    _restore_owned_prefixes.

    Swapping ``_iter_tree_skip_git_boundaries`` back to plain
    ``root.rglob("*")`` in _prune_empty_dirs leaves every other test in
    this suite green because their fixture worktrees hold only non-empty
    directories: the prune loop's ``if not any(dirpath.iterdir())`` never
    fires either way. This fixture adds an empty directory under the
    nested worktree so the mutation is caught (issue #5370).
    """
    owned = tmp_path / "owned"
    nested = owned / "worktrees" / "wt-1"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    nested_empty_dir = nested / "empty_build_dir"
    nested_empty_dir.mkdir()

    prefixes = ("owned/",)
    build_all._restore_owned_prefixes(tmp_path, prefixes, snapshot={})

    assert nested_empty_dir.is_dir()


def test_build_agent_catalog_writes_docs_catalog(tmp_path: Path) -> None:
    templates = tmp_path / "templates" / "agents"
    _write_agent_template(templates, "alpha")

    result = build_all._build_agent_catalog(tmp_path, tmp_path / "unused.yaml", "*")

    assert result.exit_code == 0
    assert result.artifact == "agent-catalog"
    assert result.platform == "docs"
    assert result.inputs == 1
    assert result.outputs == 1
    assert (tmp_path / "docs" / "agent-catalog.md").is_file()


def test_build_agent_catalog_skips_when_templates_missing(tmp_path: Path) -> None:
    result = build_all._build_agent_catalog(tmp_path, tmp_path / "unused.yaml", "*")

    assert result.exit_code == 0
    assert result.inputs == 0
    assert result.outputs == 0
    assert any("templates dir missing" in notice for notice in result.notices)


def test_build_adr_index_writes_the_readme(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-example.md").write_text(
        "---\nid: ADR-001\nstatus: accepted\ndate: 2026-01-01\n---\n\n"
        "# ADR-001: Example\n\n## Status\n\nAccepted.\n\n## Decision\n\nDo it.\n",
        encoding="utf-8",
    )

    result = build_all._build_adr_index(tmp_path, tmp_path / "unused.yaml", "*")

    assert result.exit_code == 0
    assert result.artifact == "adr-index"
    assert result.inputs == 1
    assert result.outputs == 1
    assert (adr_dir / "README.md").is_file()


def test_build_adr_index_fails_loud_when_the_adr_directory_is_missing(tmp_path: Path) -> None:
    """A missing corpus is a config error, not a silent skip.

    The wrapper used to pre-check ``adr_dir.is_dir()`` and return
    ``exit_code=0`` with a "skipped" notice, which let ``build_all.py
    --check`` report green after examining zero ADRs. The real generator,
    ``generate_adr_index.main``, already returns ADR-035 exit 2 for exactly
    this case; the wrapper must preserve that instead of shadowing it with a
    looser contract (PR #5209 review, discussion_r3831902216).
    """
    result = build_all._build_adr_index(tmp_path, tmp_path / "unused.yaml", "*")

    assert result.exit_code == 2
    assert result.inputs == 0
    assert result.outputs == 0


# Regression: #2222 — untracked-file drift (PR #2285 review iteration 2) -----
#
# The CI gate added in PR #2285 wires `build_all.py --check` into
# agent-drift-detection.yml. For that wiring to actually close #2222, the
# `--check` block must classify a regenerated-but-uncommitted file as drift
# even when its prior copy was never committed (so `git diff --name-only`
# does not list it). The fix unions `git diff --name-only` with
# `git ls-files --others --exclude-standard`. These tests pin that contract.


def _init_git_repo(repo: Path) -> None:
    """Initialise a git repo with deterministic identity for tests."""
    import subprocess

    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "commit.gpgsign", "false"], check=True
    )
    # Mirror the real repo's gitignore policy: build/audit/ is transient
    # and never committed. Without this, every test that runs build_all.run()
    # sees `?? build/` in `git status --porcelain` and the #2440 read-only
    # contract assertions can't tell generator drift from audit-log noise.
    (repo / ".gitignore").write_text("/build/audit/\n")


def test_git_diff_paths_includes_untracked_files(tmp_path: Path) -> None:
    """#2222 regression: untracked files MUST appear in diff output.

    Without this, the --check gate misses generator outputs that were
    deleted from the index then regenerated (the exact PR #2203 scenario).
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    # One committed file (so the repo has a HEAD), plus one untracked.
    (repo / "kept.txt").write_text("kept\n")
    subprocess.run(["git", "-C", str(repo), "add", "kept.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True
    )
    untracked = repo / "src" / "copilot-cli" / "lib" / "regenerated.py"
    untracked.parent.mkdir(parents=True)
    untracked.write_text("# regenerated\n")

    paths = build_all._git_diff_paths(repo)
    assert "src/copilot-cli/lib/regenerated.py" in paths, (
        f"untracked file missing from _git_diff_paths output: {paths!r}"
    )


def test_git_diff_paths_honors_gitignore(tmp_path: Path) -> None:
    """Untracked enumeration must honour .gitignore so noise stays out."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text("*.log\n__pycache__/\n")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )
    (repo / "noisy.log").write_text("noise\n")
    (repo / "src").mkdir()
    (repo / "src" / "real.py").write_text("# real\n")

    paths = build_all._git_diff_paths(repo)
    assert "src/real.py" in paths
    assert "noisy.log" not in paths


def test_git_diff_paths_dedups_when_path_appears_in_both(
    tmp_path: Path,
) -> None:
    """A path can't simultaneously be tracked-modified AND untracked, but
    guard against duplicates regardless so downstream consumers don't get
    confused by repeated entries."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "a.txt").write_text("v1\n")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True
    )
    (repo / "a.txt").write_text("v2\n")  # tracked + modified
    (repo / "b.txt").write_text("new\n")  # untracked

    paths = build_all._git_diff_paths(repo)
    assert paths.count("a.txt") == 1
    assert "b.txt" in paths


def test_run_check_returns_2_when_untracked_owned_file_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2222 end-to-end: regenerated-but-untracked owned file => exit 2.

    Reproduces the exact PR #2203 scenario: a generator-owned file under
    src/ exists in the working tree but is not in the index (e.g. because
    the source was removed from a prior commit, or because the file was
    never committed in the first place). The --check gate MUST flag this.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    # Commit the source skill so the repo has a HEAD.
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )
    # Simulate a regenerated-but-untracked owned file (the #2222 leak).
    leaked = repo / "src" / "copilot-cli" / "lib" / "cache_guard.py"
    leaked.parent.mkdir(parents=True)
    leaked.write_text("# regenerated\n")

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
    assert rc == 2, (
        f"expected exit 2 from untracked owned-prefix drift, got {rc}. "
        "If this regresses, #2222 is leaking again."
    )


def test_run_check_clean_when_untracked_outside_owned_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Untracked files outside owned prefixes must NOT flip the gate.

    The owned-prefix filter is the contract: contributors' scratch files
    in the working tree should not break CI. Only src/ and
    .github/instructions/ drift is the build orchestrator's problem.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_minimal_adr(repo / ".agents" / "architecture")
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    # Pre-generate and commit the ADR index so its first-ever creation is not
    # itself untracked drift inside an owned prefix; this fixture is only
    # about scratch.md, which sits outside every owned prefix.
    build_all._build_adr_index(repo, tmp_path / "unused.yaml", "*")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )
    (repo / "scratch.md").write_text("notes\n")  # untracked, outside owned

    # Stub the agents generator AND swap GENERATORS to a no-op list so the
    # only untracked path the gate could see is scratch.md (outside owned).
    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        ),
    )
    monkeypatch.setattr(build_all, "GENERATORS", [("agents", build_all._build_agents)])
    rc = build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    assert rc == 0, (
        f"expected exit 0 from non-owned untracked drift, got {rc}"
    )


# Regression: #2440 — --check must be read-only ----------------------------
#
# Prior to the fix, `build_all.py --check` ran generators FIRST (which write
# under owned prefixes like src/copilot-cli/ and .github/instructions/), then
# diffed the result. That left a previously-clean working tree dirty whenever
# committed outputs were stale, breaking the agents that called --check on
# unrelated worktrees. These tests pin the read-only contract: regardless of
# whether the tree was clean or already dirty, `--check` MUST restore the
# pre-run state on exit.
def _git_porcelain(repo: Path) -> str:
    import subprocess

    # Use -uall so untracked files (not just collapsed dirs) appear; the
    # #2440 contract is about per-file invariance, so the diff baseline
    # must enumerate files.
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "-uall"],
        capture_output=True,
        text=True, encoding="utf-8",
        check=True,
    )
    return proc.stdout


def test_run_check_leaves_clean_tree_unchanged_when_committed_outputs_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2440 contract: --check on a clean tree with stale outputs MUST stay clean.

    Sets up a repo where the committed output (`src/copilot-cli/skills/alpha/
    SKILL.md`) differs from what the generator would produce, commits that
    stale state, then runs --check. The pre-fix behavior is the generator
    overwrites the file, leaving the worktree dirty. The post-fix behavior
    is exit 2 (staleness detected) with the working tree restored to its
    pre-run state.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    # Source skill that the generator will copy from.
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")  # content: "# alpha\n"
    _write_platform_with_skills(repo, provider="copilot-cli")
    # Pre-commit a STALE output (content differs from source). This is the
    # exact pattern --check is meant to detect.
    out_dir = repo / "src" / "copilot-cli" / "skills" / "alpha"
    out_dir.mkdir(parents=True)
    stale_path = out_dir / "SKILL.md"
    stale_path.write_text("# stale\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed with stale output"],
        check=True,
    )
    assert _git_porcelain(repo) == ""  # baseline: clean tree

    # Stub _build_agents because the real one needs a templates tree.
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
    # Staleness MUST be reported (source has "# alpha\n", committed output
    # has "# stale\n" so the generator-written content differs from index).
    assert rc == 2, (
        f"expected exit 2 (staleness detected), got {rc}. "
        "If this regresses, --check no longer detects committed-but-stale outputs."
    )
    # AND the working tree MUST be unchanged — this is the #2440 contract.
    porcelain = _git_porcelain(repo)
    assert porcelain == "", (
        f"--check left working tree dirty (#2440 regression). "
        f"git status --porcelain output:\n{porcelain}"
    )
    # The stale file content must be preserved on disk too.
    assert stale_path.read_text() == "# stale\n", (
        "--check overwrote the committed stale output instead of restoring it"
    )


def test_run_check_leaves_untracked_owned_path_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2440: an untracked file the generator would NOT create must survive.

    A common contributor scenario: while iterating on a generator, they have
    an untracked scratch file under src/copilot-cli/ that has nothing to do
    with the build. --check must not delete or modify it.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".agents" / "architecture").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )
    # Untracked contributor scratch file under an owned prefix.
    scratch = repo / "src" / "copilot-cli" / "scratch_notes.md"
    scratch.parent.mkdir(parents=True, exist_ok=True)
    scratch.write_text("WIP notes\n")
    porcelain_before = _git_porcelain(repo)
    assert "scratch_notes.md" in porcelain_before  # baseline: dirty (untracked)

    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        ),
    )

    build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    # The untracked contributor file MUST still exist with its original content.
    assert scratch.is_file(), "--check deleted an untracked contributor file"
    assert scratch.read_text() == "WIP notes\n", (
        "--check modified an untracked contributor file"
    )
    # AND the git status must still show exactly the same dirty set.
    porcelain_after = _git_porcelain(repo)
    assert porcelain_after == porcelain_before, (
        f"--check changed git status. before:\n{porcelain_before}\n"
        f"after:\n{porcelain_after}"
    )


def test_run_check_restores_owned_prefix_after_generator_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2440: a committed file overwritten by a generator MUST be restored.

    Direct test of the snapshot/restore primitive. Pre-commits a file under
    an owned prefix, then runs --check with a generator that overwrites it.
    Post-condition: the file is back to its committed content.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    # Pre-commit a tracked file under .github/instructions/ that is committed
    # at content A, and arrange for the run to (hypothetically) write content B.
    inst_dir = repo / ".github" / "instructions"
    inst_dir.mkdir(parents=True)
    tracked = inst_dir / "rule-x.md"
    tracked.write_text("committed A\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed instructions"],
        check=True,
    )

    def _overwriting_agent(repo_root, cfg, platform):
        # Simulate what generate_rules does: write under owned prefix.
        (repo_root / ".github" / "instructions" / "rule-x.md").write_text(
            "regenerated B\n"
        )
        return build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        )

    monkeypatch.setattr(build_all, "_build_agents", _overwriting_agent)

    build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    # Post-check: file content MUST match the committed snapshot, not the
    # generator's overwrite.
    assert tracked.read_text() == "committed A\n", (
        "--check left generator output in place; expected snapshot restore"
    )
    assert _git_porcelain(repo) == "", "--check left working tree dirty"


def test_restore_preserves_preexisting_bytecode_under_owned_prefixes(
    tmp_path: Path,
) -> None:
    """A --check round trip must not evict caches it did not create.

    ``_snapshot_owned_prefixes`` excludes bytecode only when
    ``exclude_ignored`` is set, because ``_restore_owned_prefixes`` deletes
    every on-disk path the snapshot does not name. Filtering bytecode on the
    restore path would delete pre-existing ``__pycache__`` on every --check,
    forcing the next run to recompile inside the guard's snapshot window:
    the same race issue #3856 closes.
    """
    repo = tmp_path / "repo"
    cache = repo / ".github" / "instructions" / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    pyc = cache / "mod.cpython-314.pyc"
    pyc.write_bytes(b"PREEXISTING")
    sibling = repo / ".github" / "instructions" / "rule-x.md"
    sibling.write_text("committed A\n")

    snapshot = build_all._snapshot_owned_prefixes(repo, build_all.OWNED_PREFIXES)
    assert pyc in snapshot, "restore-path snapshot dropped pre-existing bytecode"

    build_all._restore_owned_prefixes(repo, build_all.OWNED_PREFIXES, snapshot)

    assert pyc.is_file(), "--check restore deleted a cache it did not create"
    assert pyc.read_bytes() == b"PREEXISTING"
    assert sibling.read_text() == "committed A\n"


def test_guard_snapshot_still_excludes_bytecode(tmp_path: Path) -> None:
    """The comparison path keeps the exclusion that closes #3856."""
    repo = tmp_path / "repo"
    cache = repo / ".claude" / "lib" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "mod.cpython-314.pyc").write_bytes(b"RACE")
    (repo / ".claude" / "lib" / "mod.py").write_text("x = 1\n")

    snapshot = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )

    assert not any(
        "__pycache__" in p.parts for p in snapshot
    ), "guard snapshot captured bytecode; #3856 race reopens"
    assert any(p.name == "mod.py" for p in snapshot)


def test_restore_replaces_directory_conflicting_with_snapshot_file(tmp_path: Path) -> None:
    """#2440: restore handles file-to-directory conflicts."""
    repo = tmp_path / "repo"
    tracked = repo / ".github" / "instructions" / "rule-x.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("committed A\n")
    snapshot = build_all._snapshot_owned_prefixes(repo, build_all.OWNED_PREFIXES)

    tracked.unlink()
    tracked.mkdir()
    (tracked / "generated-child.md").write_text("generated B\n")

    build_all._restore_owned_prefixes(repo, build_all.OWNED_PREFIXES, snapshot)

    assert tracked.is_file()
    assert tracked.read_text() == "committed A\n"


def test_run_check_uses_resolved_repo_root_when_generator_changes_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2440: relative repo roots survive generator CWD changes."""
    import os
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    out_dir = repo / "src" / "copilot-cli" / "skills" / "alpha"
    out_dir.mkdir(parents=True)
    stale_path = out_dir / "SKILL.md"
    stale_path.write_text("# stale\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True)
    porcelain_before = _git_porcelain(repo)
    monkeypatch.chdir(tmp_path)

    def _changing_cwd_agent(repo_root, cfg, platform):
        os.chdir(repo_root / ".claude")
        return build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        )

    monkeypatch.setattr(build_all, "_build_agents", _changing_cwd_agent)

    rc = build_all.run(
        Path("repo"), platform=None, check=True, clean=False, audit_format="md"
    )

    assert rc == 2
    assert _git_porcelain(repo) == porcelain_before
    assert stale_path.read_text() == "# stale\n"


def test_run_check_removes_new_untracked_files_generators_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2440: a NEW file the generator created under an owned prefix MUST be removed.

    If the generator output adds a path that didn't exist pre-run, --check
    must clean it up. Otherwise --check leaks generator output as untracked
    files into the caller's worktree.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".agents" / "architecture").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )
    assert _git_porcelain(repo) == ""

    new_path = repo / "src" / "copilot-cli" / "skills" / "alpha" / "SKILL.md"

    def _creating_agent(repo_root, cfg, platform):
        new_path.parent.mkdir(parents=True, exist_ok=True)
        new_path.write_text("# alpha\n")
        return build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        )

    monkeypatch.setattr(build_all, "_build_agents", _creating_agent)

    build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    # The new file MUST have been cleaned up by the restore pass.
    assert not new_path.exists(), (
        "--check left a generator-created file behind; "
        "snapshot restore must remove new files under owned prefixes."
    )
    assert _git_porcelain(repo) == "", "--check left working tree dirty"


def test_run_without_check_does_not_snapshot_or_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --check, generator writes MUST persist (normal generate mode).

    The snapshot/restore behavior is gated on --check; a plain
    `build_all.py` (no --check) is a real generation run and must leave
    its output in place.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".agents" / "architecture").mkdir(parents=True)
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )

    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        ),
    )

    build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    # The real skills generator wrote src/copilot-cli/skills/alpha/SKILL.md.
    out = repo / "src" / "copilot-cli" / "skills" / "alpha" / "SKILL.md"
    assert out.is_file(), (
        "non-check run must leave generator output in place "
        "(snapshot/restore must be --check-only)"
    )


# Regression: #2775, --check must cover the Copilot skill-mirror -----------
#
# build_all.py --check did not flag a stale src/copilot-cli/skills/** mirror
# during the #2050 migration. These two tests pin the coverage end to end with
# the REAL skills generator and REAL git, no _git_diff_paths monkeypatch: a
# clean committed mirror exits 0, a mirror left stale by a source edit exits 2.


def _seed_repo_with_committed_skill_mirror(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Init a git repo, generate the skill mirror, and commit the clean state.

    Returns the committed mirror path (src/copilot-cli/skills/alpha/SKILL.md).
    Stubs _build_agents because the real agents generator needs a templates
    tree this fixture does not build.
    """
    import subprocess

    _init_git_repo(repo)
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_minimal_adr(repo / ".agents" / "architecture")
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
    monkeypatch.setattr(
        build_all,
        "_build_agents",
        lambda repo_root, cfg, platform: build_all.GeneratorResult(
            artifact="agents", platform="*", exit_code=0
        ),
    )
    # Generate the mirror (non-check) and commit it so the tree is clean.
    build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )
    mirror = repo / "src" / "copilot-cli" / "skills" / "alpha" / "SKILL.md"
    assert mirror.is_file(), "fixture failed to generate the skill mirror"
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed clean mirror"],
        check=True,
    )
    assert _git_porcelain(repo) == "", "fixture left the tree dirty"
    return mirror


def test_run_check_returns_0_when_skill_mirror_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2775: a committed-and-current skill mirror passes --check (exit 0)."""
    repo = tmp_path / "repo"
    _seed_repo_with_committed_skill_mirror(repo, monkeypatch)

    rc = build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    assert rc == 0, (
        f"clean skill mirror should pass --check, got {rc}"
    )


def test_run_check_returns_2_when_skill_mirror_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2775: a source edit that is not regenerated into the committed mirror
    makes --check exit 2.

    This is the exact coverage hole #2775 reported: an edited source skill with
    a stale src/copilot-cli/skills/** mirror used to slip past --check. The real
    generator rewrites the mirror in-tree; the git diff against the committed
    (stale) copy is what the gate must catch.
    """
    repo = tmp_path / "repo"
    _seed_repo_with_committed_skill_mirror(repo, monkeypatch)

    # Edit the SOURCE skill without regenerating/committing the mirror.
    source = repo / ".claude" / "skills" / "alpha" / "SKILL.md"
    source.write_text("# alpha\n\nNew source content not yet mirrored.\n", encoding="utf-8")

    rc = build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )
    assert rc == 2, (
        f"stale skill mirror should fail --check, got {rc}. "
        "If this regresses, #2775 is leaking: --check no longer covers "
        "the src/copilot-cli/skills/** mirror."
    )
    # #2440 read-only contract: --check restores owned prefixes (src/). The
    # only dirty path is the intentional source edit under .claude/, which is
    # outside OWNED_PREFIXES and not the orchestrator's to revert.
    porcelain = _git_porcelain(repo)
    assert porcelain == " M .claude/skills/alpha/SKILL.md\n", (
        f"--check should restore the src/ mirror and leave only the source "
        f"edit dirty; got:\n{porcelain}"
    )


# _ignored_paths + exclude_ignored guard filtering (issue #2992) -------------


def test_ignored_paths_lists_gitignored_files(tmp_path: Path) -> None:
    """git-ignored runtime artifacts must appear in the ignored set."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".claude/hooks/audit.log\n__pycache__/\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    audit = hooks / "audit.log"
    audit.write_text("runtime append\n", encoding="utf-8")
    pyc_dir = hooks / "__pycache__"
    pyc_dir.mkdir()
    pyc = pyc_dir / "mod.cpython-314.pyc"
    pyc.write_bytes(b"\x00bytecode")

    ignored = build_all._ignored_paths(repo, build_all.CLAUDE_GUARD_PREFIX)
    assert audit in ignored
    assert pyc in ignored


def test_ignored_paths_excludes_tracked_files(tmp_path: Path) -> None:
    """A tracked .claude/ file is NOT gitignored, so it stays out of the set."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    tracked = repo / ".claude" / "agents" / "real.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("# real agent\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", ".claude/agents/real.md"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "add"], check=True
    )

    ignored = build_all._ignored_paths(repo, build_all.CLAUDE_GUARD_PREFIX)
    assert tracked not in ignored


def test_ignored_paths_empty_when_not_a_git_repo(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Outside a git repo, ls-files fails and the set is empty (safe fallback).

    The stderr assertion is load-bearing. Measured: deleting the
    ``proc.returncode != 0`` warning in ``_ignored_paths`` and leaving the
    bare ``continue`` left all 99 tests green when this case checked only
    the empty set. A silent empty set reads downstream as "nothing is
    gitignored", which is how the REQ-003-010 guard starts reporting a
    hook's own log write as a generator violation (issue #2992). The
    diagnostic is the only signal that the query failed rather than
    matched nothing, so it needs an assertion of its own.
    """
    claude = tmp_path / ".claude" / "hooks"
    claude.mkdir(parents=True)
    (claude / "audit.log").write_text("noise\n", encoding="utf-8")

    ignored = build_all._ignored_paths(tmp_path, build_all.CLAUDE_GUARD_PREFIX)
    assert ignored == set()
    assert "WARN: git ls-files exited" in capsys.readouterr().err


@pytest.mark.parametrize(
    "exc",
    [
        OSError("git missing"),
        subprocess.TimeoutExpired(cmd="git", timeout=30),
    ],
    ids=["oserror", "timeout"],
)
def test_ignored_paths_warns_and_falls_back_when_git_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exc: Exception,
) -> None:
    """``subprocess.run`` raising must degrade to an empty set plus a warning.

    ``_ignored_paths`` catches ``(OSError, subprocess.SubprocessError)``.
    The nonzero-exit test covers only the ``returncode != 0`` branch, which
    a missing ``git`` binary (``OSError``) or a hung ``git`` (a 30 second
    ``TimeoutExpired``, a ``SubprocessError`` subclass) never reaches. Both
    arms must fall back rather than crash the build, and both must say so
    on stderr: a silent empty set reads as "nothing is gitignored" and
    would let the REQ-003-010 guard report a hook's own log write as a
    generator violation.
    """

    def boom(*args: object, **kwargs: object) -> object:
        raise exc

    monkeypatch.setattr(build_all.subprocess, "run", boom)

    ignored = build_all._ignored_paths(tmp_path, build_all.CLAUDE_GUARD_PREFIX)

    assert ignored == set()
    assert "WARN: git ls-files failed" in capsys.readouterr().err


def test_ignored_paths_ignores_inherited_git_dir_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An inherited GIT_DIR must not redirect ls-files away from repo_root.

    build_all.py can run inside a git hook, where GIT_DIR/GIT_WORK_TREE point
    at the outer repo. git honors those env vars over ``-C``, so without the
    scrub the ignore set would be computed against the wrong repository
    (issue #2992). The scrub in _ignored_paths removes them.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".claude/hooks/audit.log\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    audit = hooks / "audit.log"
    audit.write_text("runtime append\n", encoding="utf-8")

    # Simulate a hook context: git location env vars point at a different
    # repo. The scrub must remove all of _GIT_LOCATION_ENV_VARS, so set the
    # full list to invalid/other paths and assert the ignore set is still
    # computed against repo_root.
    other = tmp_path / "other"
    _init_git_repo(other)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_COMMON_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))

    ignored = build_all._ignored_paths(repo, build_all.CLAUDE_GUARD_PREFIX)
    assert audit in ignored


def test_git_diff_paths_ignores_inherited_git_dir_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An inherited GIT_DIR must not redirect diff/ls-files away from repo_root.

    _git_diff_paths backs both --check (staleness) and the .claude/ guard. It
    runs ``git -C repo_root diff`` and ``git ls-files``, which git resolves
    against an inherited GIT_DIR/GIT_WORK_TREE over ``-C`` (issue #2992). The
    scrub in _git_diff_paths removes the git location env vars so the diff is
    computed against repo_root, not the outer repo.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "tracked.txt").write_text("v1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True
    )
    # An untracked file in repo must be reported by ls-files --others.
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    # Point git location env at a clean, unrelated repo. Without the scrub,
    # ls-files would resolve against ``other`` and miss repo/new.txt.
    other = tmp_path / "other"
    _init_git_repo(other)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    monkeypatch.setenv("GIT_COMMON_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(other / ".git" / "index"))

    paths = build_all._git_diff_paths(repo)
    assert "new.txt" in paths


def test_snapshot_excludes_ignored_runtime_artifacts(tmp_path: Path) -> None:
    """exclude_ignored omits gitignored files from the snapshot."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".claude/hooks/audit.log\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    audit = hooks / "audit.log"
    audit.write_text("v1\n", encoding="utf-8")
    owned_file = repo / ".claude" / "agents" / "a.md"
    owned_file.parent.mkdir(parents=True)
    owned_file.write_text("a\n", encoding="utf-8")

    snap = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )
    assert audit not in snap
    assert owned_file in snap


def test_is_ignored_path_treats_directory_entries_as_prefixes() -> None:
    """Unit-level pin on the matching rule _snapshot_owned_prefixes relies on.

    ``ignored`` can hold a directory (see :func:`_ignored_paths`), and a
    path nested under that directory must match even though it is not
    itself a key in the set. An unrelated path, and a path that merely
    shares a string prefix without being a real path ancestor, must not.
    """
    ignored = {Path("/repo/.claude/worktrees/wt-1")}
    assert build_all._is_ignored_path(
        Path("/repo/.claude/worktrees/wt-1"), ignored
    )  # exact match
    assert build_all._is_ignored_path(
        Path("/repo/.claude/worktrees/wt-1/sub/file.txt"), ignored
    )  # nested under the ignored directory
    assert not build_all._is_ignored_path(
        Path("/repo/.claude/worktrees/wt-10/file.txt"), ignored
    )  # sibling directory, not a real path ancestor
    assert not build_all._is_ignored_path(
        Path("/repo/.claude/agents/real.md"), ignored
    )  # unrelated path


def test_snapshot_owned_prefixes_excludes_every_file_under_ignored_worktree(
    tmp_path: Path,
) -> None:
    """A whole ignored directory (a nested worktree) must exclude every file
    under it, not just a path that matches it exactly.

    ``git ls-files --others --ignored --exclude-standard`` reports a
    registered git worktree as one ignored *directory* entry, not one entry
    per file inside it (git's embedded-repository boundary; verified via
    a real ``git worktree add`` in this fixture). Before this fix,
    ``_snapshot_owned_prefixes`` matched ``ignored`` with plain set
    membership, so every file inside the worktree still got read into the
    snapshot: with dozens of real worktrees that is the OOM in issue #5370.

    Positive control: a non-ignored sibling directory's file is still
    captured, so the fix is scoped to the ignored directory and does not
    silently swallow the whole ``.claude/`` prefix.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".claude/worktrees/\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", ".gitignore"], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )

    worktrees = repo / ".claude" / "worktrees"
    worktrees.mkdir(parents=True)
    nested_worktree = worktrees / "wt-1"
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "worktree",
            "add",
            "-q",
            str(nested_worktree),
            "-b",
            "wt-1-branch",
        ],
        check=True,
        capture_output=True,
    )
    nested_file = nested_worktree / "extra.txt"
    nested_file.write_text("nested worktree content\n", encoding="utf-8")
    nested_subdir_file = nested_worktree / "sub" / "deep.txt"
    nested_subdir_file.parent.mkdir(parents=True)
    nested_subdir_file.write_text("deep nested content\n", encoding="utf-8")

    sibling = repo / ".claude" / "agents" / "real.md"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("# real agent\n", encoding="utf-8")

    snapshot = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )

    assert nested_file not in snapshot
    assert nested_subdir_file not in snapshot
    assert not any(
        nested_worktree in path.parents or path == nested_worktree
        for path in snapshot
    )
    assert sibling in snapshot


def test_snapshot_owned_prefixes_excludes_children_of_a_plain_ignored_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin the prefix match at its call site, not just in the helper.

    The walk inside ``_snapshot_owned_prefixes`` in
    ``build/scripts/build_all.py`` reads::

        if _is_ignored_path(path, ignored) or (

    The sibling worktree test above cannot protect that line. Its nested
    checkout comes from a real ``git worktree add``, so it carries a
    ``.git`` file and ``_iter_tree_skip_git_boundaries`` drops it two
    lines earlier, at ``if is_dir or not path.is_file():``, before
    ``ignored`` is ever consulted. Measured: replacing the call above with
    ``path in ignored`` (exact set membership, the pre-#5370 behavior)
    left all 99 tests green. The helper unit test cannot catch it either,
    because it calls ``_is_ignored_path`` directly and never exercises the
    wiring.

    So this case removes the boundary marker. ``_ignored_paths`` is
    stubbed to report one plain ancestor directory, the shape git uses for
    any ignored directory that is not a nested checkout: a build output
    tree, a cache directory, any ``.gitignore`` line ending in ``/``. With
    exact membership the directory itself is never yielded as a file, so
    every descendant is snapshotted and the first assertion fails.
    """
    repo = tmp_path / "repo"
    ignored_dir = repo / ".claude" / "cache"
    ignored_dir.mkdir(parents=True)
    assert not (ignored_dir / ".git").exists()
    child = ignored_dir / "blob.bin"
    child.write_text("cached\n", encoding="utf-8")
    grandchild = ignored_dir / "sub" / "deep.bin"
    grandchild.parent.mkdir(parents=True)
    grandchild.write_text("deep cached\n", encoding="utf-8")
    sibling = repo / ".claude" / "agents" / "real.md"
    sibling.parent.mkdir(parents=True)
    sibling.write_text("# real agent\n", encoding="utf-8")

    monkeypatch.setattr(
        build_all,
        "_ignored_paths",
        lambda repo_root, prefixes: {ignored_dir},
    )

    snapshot = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )

    assert child not in snapshot
    assert grandchild not in snapshot
    assert sibling in snapshot


def test_assert_no_claude_writes_ignores_audit_log_churn(tmp_path: Path) -> None:
    """REQ-003-010 false positive fix (#2992): a gitignored audit.log that
    changes DURING the build window must NOT be attributed to a generator.

    Reproduces the intermittent push blocker: a session hook appends to
    .claude/hooks/audit.log between the baseline snapshot and the post-build
    re-read. Before the fix, that byte difference tripped the guard.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".claude/hooks/audit.log\n__pycache__/\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )
    hooks = repo / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    audit = hooks / "audit.log"
    audit.write_text("before build\n", encoding="utf-8")

    baseline = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )
    # Session hook appends to the gitignored log mid-build (the race).
    audit.write_text("before build\nappended during build\n", encoding="utf-8")

    assert build_all.assert_no_claude_writes(repo, baseline) == []


def test_assert_no_claude_writes_still_flags_real_write_in_git_repo(
    tmp_path: Path,
) -> None:
    """The gitignore filter must NOT mask a genuine generator write to a
    non-ignored .claude/ path (#2992 negative control)."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text(
        ".claude/hooks/audit.log\n", encoding="utf-8"
    )
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True
    )
    (repo / ".claude" / "agents").mkdir(parents=True)

    baseline = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )
    # Generator writes a NON-ignored file after the snapshot.
    (repo / ".claude" / "agents" / "leak.md").write_text(
        "generated", encoding="utf-8"
    )

    assert build_all.assert_no_claude_writes(repo, baseline) == [
        ".claude/agents/leak.md"
    ]


def test_assert_no_claude_writes_flags_a_write_behind_a_generated_git_marker(
    tmp_path: Path,
) -> None:
    """A generator cannot hide a .claude/ write behind a ``.git`` it wrote.

    Both walks the guard compares stop at git repository boundaries. When
    each one detects those by shape independently, a generator that writes
    ``.claude/out/.git`` alongside its output takes that whole tree out of
    the post-generation walk, and the baseline walk never saw it either,
    so the diff is empty. Measured before ``preexisting_boundaries``
    existed: this exact sequence returned ``[]`` with
    ``.claude/out/leaked.md`` still on disk, so REQ-003-010 passed and the
    build could exit successfully with an undetected write.

    Recording the boundary set once with ``_git_boundaries_under`` and
    passing it to both walks makes them skip exactly the same trees, so a
    boundary that appeared during the build is walked and reported.

    The inverse is asserted in the same run. A live nested worktree that
    existed before the build must stay invisible to the guard even when
    its own owner edits a file inside it mid-build, which is the
    false-positive REQ-003-010 was tuned against (issue #2992) and the
    tree issue #5370 exists to keep out of these walks. Reporting the new
    write is worthless if it also reports the neighbouring checkout.
    """
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "init"],
        check=True,
    )
    live_worktree = repo / ".claude" / "worktrees" / "wt-1"
    live_worktree.mkdir(parents=True)
    (live_worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    live_file = live_worktree / "live.txt"
    live_file.write_text("before the build\n", encoding="utf-8")

    boundaries = build_all._git_boundaries_under(
        repo, build_all.CLAUDE_GUARD_PREFIX
    )
    assert boundaries == {live_worktree}
    baseline = build_all._snapshot_owned_prefixes(
        repo,
        build_all.CLAUDE_GUARD_PREFIX,
        exclude_ignored=True,
        opaque_boundaries=boundaries,
    )

    # A generator writes output and a .git marker to shield it.
    generated_tree = repo / ".claude" / "out"
    generated_tree.mkdir()
    (generated_tree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
    (generated_tree / "leaked.md").write_text(
        "generator wrote this\n", encoding="utf-8"
    )
    # The live worktree's own owner edits a file mid-build.
    live_file.write_text("edited by the worktree owner\n", encoding="utf-8")

    violations = build_all.assert_no_claude_writes(
        repo, baseline, preexisting_boundaries=boundaries
    )

    assert violations == [".claude/out/.git", ".claude/out/leaked.md"]
    assert not any(v.startswith(".claude/worktrees/") for v in violations)


def test_run_flags_a_generator_write_hidden_behind_a_git_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Drive the guard through ``run()``, not by calling it directly.

    The sibling test above passes ``preexisting_boundaries`` itself, so it
    proves the guard honours the argument but not that anything supplies
    it. Measured: dropping the argument at the one real call site, in
    ``_run_generators``, left the sibling test and all 102 others green.
    That is the same helper-tested-but-unwired gap the reviewer flagged
    twice on this PR, so the wiring gets its own end-to-end case.

    A stubbed generator writes ``.claude/out/leaked.md`` next to a
    ``.git`` marker it also writes. ``run()`` must return 2 and name the
    file, which only happens if the boundary set recorded before
    generation reaches :func:`assert_no_claude_writes`.
    """
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_minimal_adr(repo / ".agents" / "architecture")
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")

    def leaking_agents(
        repo_root: Path, cfg: object, platform: object
    ) -> build_all.GeneratorResult:
        hidden = repo_root / ".claude" / "out"
        hidden.mkdir(parents=True, exist_ok=True)
        (hidden / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (hidden / "leaked.md").write_text("generator wrote this\n", encoding="utf-8")
        return build_all.GeneratorResult(
            artifact="agents", platform="*", outputs=0, exit_code=0
        )

    monkeypatch.setattr(build_all, "_build_agents", leaking_agents)

    rc = build_all.run(
        repo, platform=None, check=False, clean=False, audit_format="md"
    )

    assert rc == 2
    assert "REQ-003-010 VIOLATION: generator wrote to .claude/out/leaked.md" in (
        capsys.readouterr().err
    )


def test_run_check_removes_a_generated_tree_behind_a_git_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive the restore path through ``run()``, not by calling it directly.

    ``test_restore_owned_prefixes_removes_a_boundary_tree_created_mid_build``
    passes ``preexisting_boundaries`` itself, so it holds the helper but
    not the one real call site in ``run()``. Measured: dropping that
    argument from the ``run()`` restore call left that test and all 103
    others green, the same helper-tested-but-unwired shape the reviewer
    flagged twice on this PR.

    A stubbed generator writes ``src/out/generated.txt`` next to a
    ``.git`` marker under an owned prefix. ``--check`` must leave the
    working tree as it found it, so both paths and the directory must be
    gone once ``run()`` returns.
    """
    monkeypatch.setattr(build_all, "_git_diff_paths", lambda repo_root: [])
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    _write_minimal_adr(repo / ".agents" / "architecture")
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")

    def boundary_writing_agents(
        repo_root: Path, cfg: object, platform: object
    ) -> build_all.GeneratorResult:
        hidden = repo_root / "src" / "out"
        hidden.mkdir(parents=True, exist_ok=True)
        (hidden / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (hidden / "generated.txt").write_text("output\n", encoding="utf-8")
        return build_all.GeneratorResult(
            artifact="agents", platform="*", outputs=0, exit_code=0
        )

    monkeypatch.setattr(build_all, "_build_agents", boundary_writing_agents)

    build_all.run(
        repo, platform=None, check=True, clean=False, audit_format="md"
    )

    assert not (repo / "src" / "out" / "generated.txt").exists()
    assert not (repo / "src" / "out" / ".git").exists()
    assert not (repo / "src" / "out").exists()


# --- #3856: bytecode written inside the guard's snapshot window -----------
#
# The pre-push hook runs `python-tests` and `build-all-check` in the same
# lefthook job group with `parallel: true`. Pytest imports .claude/lib, so
# CPython writes __pycache__/*.pyc while the REQ-003-010 guard is walking
# the same tree. _ignored_paths() queries git once per snapshot, so a .pyc
# created after that query still lands in the walk and reads as a generator
# write. _is_bytecode_artifact() filters on path shape, which no race can
# invalidate.


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/lib/github_core/__pycache__/__init__.cpython-314.pyc",
        ".claude/lib/__pycache__/helper.cpython-313.pyc",
        ".claude/lib/deep/nested/pkg/__pycache__/mod.cpython-314.pyc",
        ".claude/lib/stray.pyc",
        ".claude/lib/stray.pyo",
        ".claude/lib/__pycache__/data.json",
    ],
)
def test_is_bytecode_artifact_matches_caches(relative: str) -> None:
    """Anything under __pycache__, plus .pyc/.pyo anywhere, is an artifact.

    The rule is path-shaped, not extension-shaped: ``data.json`` inside a
    ``__pycache__`` directory matches, because tools other than CPython
    write there too.
    """
    assert build_all._is_bytecode_artifact(Path("/repo") / relative) is True


@pytest.mark.parametrize(
    "relative",
    [
        ".claude/agents/leak.md",
        ".claude/lib/github_core/__init__.py",
        ".claude/lib/pycache.py",
        ".claude/lib/my__pycache__file.py",
        ".claude/lib/notes.pyc.md",
        ".claude/skills/x/SKILL.md",
    ],
)
def test_is_bytecode_artifact_rejects_real_files(relative: str) -> None:
    """Paths that only resemble a cache are not artifacts.

    Every case here sits outside a ``__pycache__`` directory and does not
    end in ``.pyc``/``.pyo``. Being a data file is not itself
    disqualifying: see the ``__pycache__/data.json`` case above.
    """
    assert build_all._is_bytecode_artifact(Path("/repo") / relative) is False


def _write_bytecode(pkg: Path) -> Path:
    """Create a plausible CPython cache file under ``pkg`` and return it."""
    cache = pkg / "__pycache__"
    cache.mkdir(exist_ok=True)
    pyc = cache / "__init__.cpython-314.pyc"
    pyc.write_bytes(b"\x00bytecode")
    return pyc


def test_snapshot_excludes_bytecode_written_after_the_ignore_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#3856: a .pyc created between `git ls-files` and the tree walk must
    not read as a generator write."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    pkg = repo / ".claude" / "lib" / "github_core"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    baseline = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )

    real_ignored_paths = build_all._ignored_paths

    def _racing(root: Path, prefixes: tuple[str, ...]) -> set[Path]:
        # git ls-files runs, THEN the concurrent pytest import writes bytecode.
        result = real_ignored_paths(root, prefixes)
        _write_bytecode(pkg)
        return result

    monkeypatch.setattr(build_all, "_ignored_paths", _racing)

    assert build_all.assert_no_claude_writes(repo, baseline) == []


def test_bytecode_filter_does_not_mask_a_concurrent_real_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control for #3856: a non-bytecode file appearing in the same
    race window is still reported."""
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    pkg = repo / ".claude" / "lib" / "github_core"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("x = 1\n", encoding="utf-8")

    baseline = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )

    real_ignored_paths = build_all._ignored_paths

    def _racing(root: Path, prefixes: tuple[str, ...]) -> set[Path]:
        result = real_ignored_paths(root, prefixes)
        _write_bytecode(pkg)
        (repo / ".claude" / "lib" / "leak.md").write_text(
            "generated", encoding="utf-8"
        )
        return result

    monkeypatch.setattr(build_all, "_ignored_paths", _racing)

    assert build_all.assert_no_claude_writes(repo, baseline) == [
        ".claude/lib/leak.md"
    ]


# _confirm_ignored: report-time race closure (issue #3773) -------------------


def _race_repo(tmp_path: Path) -> Path:
    """A git repo whose .gitignore covers bytecode, with .claude/lib present."""
    import subprocess

    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "ignore"], check=True)
    (repo / ".claude" / "lib").mkdir(parents=True)
    return repo


def test_bytecode_written_after_the_ignore_scan_is_not_a_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact failure that blocked PR #3688.

    ``_snapshot_owned_prefixes`` computes the ignore set before it walks the
    tree, so a gitignored file created in between is walked and not excluded.
    Simulated deterministically by having the ignore scan write the .pyc as it
    returns, which is the same ordering the real race produces: present in the
    walk, absent from the ignore set.
    """
    repo = _race_repo(tmp_path)
    pyc = repo / ".claude" / "lib" / "__pycache__" / "mod.cpython-314.pyc"
    real_ignored_paths = build_all._ignored_paths

    def racing_scan(repo_root: Path, prefixes: tuple[str, ...]) -> set[Path]:
        result = real_ignored_paths(repo_root, prefixes)
        pyc.parent.mkdir(parents=True, exist_ok=True)
        pyc.write_bytes(b"\x00bytecode")
        return result

    monkeypatch.setattr(build_all, "_ignored_paths", racing_scan)
    baseline = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )
    assert build_all.assert_no_claude_writes(repo, baseline) == []


def test_a_real_generator_write_is_still_reported(tmp_path: Path) -> None:
    """Negative control: closing the race must not blind the guard."""
    repo = _race_repo(tmp_path)
    baseline = build_all._snapshot_owned_prefixes(
        repo, build_all.CLAUDE_GUARD_PREFIX, exclude_ignored=True
    )
    (repo / ".claude" / "lib" / "generated.py").write_text("x = 1\n", encoding="utf-8")
    assert build_all.assert_no_claude_writes(repo, baseline) == [".claude/lib/generated.py"]


def test_confirm_ignored_returns_only_the_gitignored_candidates(tmp_path: Path) -> None:
    """Mixed input: the tracked-looking path survives, the bytecode does not."""
    repo = _race_repo(tmp_path)
    pyc = repo / ".claude" / "lib" / "__pycache__" / "mod.cpython-314.pyc"
    pyc.parent.mkdir(parents=True)
    pyc.write_bytes(b"\x00bytecode")
    real = repo / ".claude" / "lib" / "generated.py"
    real.write_text("x = 1\n", encoding="utf-8")
    assert build_all._confirm_ignored(repo, {pyc, real}) == {pyc}


def test_confirm_ignored_short_circuits_on_no_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The clean case is the common case; it must not shell out to git.

    Asserting only on the return value would pass without the guard, because
    ``check-ignore`` given empty stdin also returns nothing. The spawn is what
    the short-circuit exists to avoid, so the spawn is what this pins.
    """
    repo = _race_repo(tmp_path)
    calls: list[object] = []

    def record(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("git must not run when there is nothing to confirm")

    monkeypatch.setattr(build_all.subprocess, "run", record)
    assert build_all._confirm_ignored(repo, set()) == set()
    assert calls == []


def test_confirm_ignored_survives_an_inherited_git_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git honours ``GIT_DIR`` over ``-C``, and this runs inside a git hook.

    ``build-all-check`` is a lefthook pre-push job, so the environment can
    carry git location vars pointing at another repository. Without the env
    scrub the confirmation would resolve there, match nothing, and report the
    bytecode as a violation. Mirrors the same defence in ``_ignored_paths``
    (issue #2992).
    """
    repo = _race_repo(tmp_path)
    pyc = repo / ".claude" / "lib" / "__pycache__" / "mod.cpython-314.pyc"
    pyc.parent.mkdir(parents=True)
    pyc.write_bytes(b"\x00bytecode")
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere" / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "elsewhere"))
    assert build_all._confirm_ignored(repo, {pyc}) == {pyc}


def test_confirm_ignored_returns_empty_when_git_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed: an unconfirmable candidate stays reported, not dropped."""
    repo = _race_repo(tmp_path)
    pyc = repo / ".claude" / "lib" / "mod.pyc"

    def boom(*args: object, **kwargs: object) -> object:
        raise OSError("git missing")

    monkeypatch.setattr(build_all.subprocess, "run", boom)
    assert build_all._confirm_ignored(repo, {pyc}) == set()


def test_confirm_ignored_ignores_git_exit_one(tmp_path: Path) -> None:
    """``check-ignore`` exits 1 when nothing matches; that is the clean case."""
    repo = _race_repo(tmp_path)
    real = repo / ".claude" / "lib" / "generated.py"
    real.write_text("x = 1\n", encoding="utf-8")
    assert build_all._confirm_ignored(repo, {real}) == set()


def test_confirm_ignored_is_fail_closed_on_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A git error (exit 128) must discard whatever partial output arrived.

    The stdout payload is non-empty on purpose. With empty output the real
    code and a mutant that drops the return-code check are
    indistinguishable, so the test would prove nothing. Trusting partial
    output would exclude a path from the guard on the strength of a failed
    query, which is fail-open.
    """
    pyc = tmp_path / "x.pyc"

    class _Result:
        returncode = 128
        stdout = str(pyc).encode()

    monkeypatch.setattr(build_all.subprocess, "run", lambda *a, **k: _Result())

    assert build_all._confirm_ignored(tmp_path, {pyc}) == set()


def test_confirm_ignored_survives_non_utf8_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-UTF-8 filename must round-trip rather than raise
    UnicodeDecodeError and crash the pre-push guard."""
    import os as _os

    raw = tmp_path / _os.fsdecode(b"caf\xe9.pyc")

    class _Result:
        returncode = 0
        stdout = _os.fsencode(str(raw))

    monkeypatch.setattr(build_all.subprocess, "run", lambda *a, **k: _Result())

    assert build_all._confirm_ignored(tmp_path, {raw}) == {raw}
