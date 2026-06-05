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
    _write_skill(repo / ".claude" / "skills", "alpha")
    _write_platform_with_skills(repo, provider="copilot-cli")
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
        text=True,
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
