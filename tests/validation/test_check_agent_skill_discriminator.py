"""Tests for scripts/validation/check_agent_skill_discriminator.py (Issue #2008).

Pins the Phase 3 agent-skill discriminator CI backstop.

Required fixture coverage (issue acceptance criteria):
- pure-skill agent (c1+c2+c3 all true): fails
- pure-agent agent (prose body, no slash-command invocation): passes
- mixed agent with frontmatter override (isolation_required): passes
- agent invoked from 3+ pipelines (c3 N/A via the 3-pipeline rule): passes

Plus edge and branch cases: PR-description override token, metadata files
excluded, two-source templates/agents siblings scored, c2 conservative
sentence-prose exclusion, and ADR-035 exit codes.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_agent_skill_discriminator.py"


def _load_module():
    """Import the validator by file path for direct-function tests.

    Register the module in sys.modules before exec so the dataclass decorator
    (slots=True) can resolve the module namespace during class creation.
    """
    spec = importlib.util.spec_from_file_location("agent_skill_disc", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


mod = _load_module()


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _reference_body(lines: int = 30) -> str:
    """A heavily structured-reference body (tables + short label bullets)."""
    rows = "\n".join(f"| key{i} | value{i} |" for i in range(lines // 2))
    bullets = "\n".join(f"- field{i}: required" for i in range(lines // 2))
    return f"## Schema\n\n| col | desc |\n|-----|------|\n{rows}\n\n## Rules\n{bullets}\n"


def _prose_body(lines: int = 30) -> str:
    """A prose body of full sentences (reasoning, not reference)."""
    para = (
        "You investigate before implementation and reason about the problem "
        "from first principles to surface the deepest root cause available."
    )
    return "## Mission\n\n" + "\n\n".join(para for _ in range(lines)) + "\n"


def _write_agent(
    repo: Path,
    name: str,
    body: str,
    *,
    isolation_required: bool = False,
    shared_template: bool = False,
) -> str:
    """Write an agent file and return its repo-relative path.

    Frontmatter lines are assembled at column 0 (no dedent) so the optional
    isolation_required line keeps the same zero indentation as the fences.
    """
    fm_lines = [
        "---",
        f"name: {name}",
        f"description: Test agent {name}.",
        "model: sonnet",
    ]
    if isolation_required:
        fm_lines.append("isolation_required: true  # fresh-context review")
    fm_lines.append("---")
    content = "\n".join(fm_lines) + f"\n\n# {name} agent\n\n" + body
    if shared_template:
        rel = f"templates/agents/{name}.shared.md"
    else:
        rel = f".claude/agents/{name}.md"
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel


def _write_command(repo: Path, name: str, text: str) -> None:
    base = repo / ".claude" / "commands"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.md").write_text(text, encoding="utf-8")


def _scaffold(tmp_path: Path) -> Path:
    """Create the minimal repo shape: .claude/commands and .claude/agents."""
    repo = tmp_path / "repo"
    (repo / ".claude" / "commands").mkdir(parents=True)
    (repo / ".claude" / "agents").mkdir(parents=True)
    return repo


def _run(
    repo: Path, changed: list[str], pr_body: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--pr-body",
            pr_body,
            "--changed-files",
            *changed,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Unit: c2 heuristic
# ---------------------------------------------------------------------------


def test_c2_structured_body_scores_true() -> None:
    is_shape, ratio = mod.score_c2(_reference_body())
    assert is_shape is True
    assert ratio >= mod.C2_THRESHOLD


def test_c2_prose_body_scores_false() -> None:
    is_shape, ratio = mod.score_c2(_prose_body())
    assert is_shape is False
    assert ratio < mod.C2_THRESHOLD


def test_c2_long_sentence_bullet_is_not_reference() -> None:
    """A long bullet ending in a period is reasoning prose, not reference."""
    line = (
        "- You must carefully consider every downstream consumer before you "
        "decide whether the change is safe to land in production today."
    )
    assert mod._is_reference_line(line) is False


def test_c2_short_label_bullet_is_reference() -> None:
    assert mod._is_reference_line("- field: required") is True


def test_c2_empty_body_is_not_shape() -> None:
    is_shape, ratio = mod.score_c2("")
    assert is_shape is False
    assert ratio == 0.0


# ---------------------------------------------------------------------------
# Unit: frontmatter escape hatch
# ---------------------------------------------------------------------------


def test_isolation_required_true_detected() -> None:
    assert mod.has_isolation_required("name: x\nisolation_required: true") is True


def test_isolation_required_false_not_detected() -> None:
    assert mod.has_isolation_required("isolation_required: false") is False


def test_isolation_required_absent() -> None:
    assert mod.has_isolation_required("name: x\nmodel: sonnet") is False


# ---------------------------------------------------------------------------
# Unit: path filtering
# ---------------------------------------------------------------------------


def test_metadata_files_excluded() -> None:
    assert mod.is_agent_path(".claude/agents/AGENTS.md") is False
    assert mod.is_agent_path(".claude/agents/CLAUDE.md") is False


def test_agent_and_shared_template_paths_included() -> None:
    assert mod.is_agent_path(".claude/agents/devops.md") is True
    assert mod.is_agent_path("templates/agents/devops.shared.md") is True


def test_skill_path_not_treated_as_agent() -> None:
    assert mod.is_agent_path(".claude/skills/devops/SKILL.md") is False


# ---------------------------------------------------------------------------
# Integration: required fixture scenarios
# ---------------------------------------------------------------------------


def test_pure_skill_agent_fails(tmp_path: Path) -> None:
    """c1+c2+c3 all true with no escape hatch -> exit 1 (candidate fails)."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "shaped", _reference_body())
    # One pipeline invokes both the agent (c1) and a sibling skill (c3).
    _write_command(
        repo,
        "build",
        'Task(subagent_type="shaped"): do work.\n'
        'Invoke Skill(skill="pre-mortem") first.\n',
    )

    proc = _run(repo, [rel])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "FAIL" in proc.stdout
    assert "shaped" in proc.stdout
    assert mod.AUDIT_PATH in proc.stdout


def test_pure_agent_passes(tmp_path: Path) -> None:
    """Prose body, never invoked from a slash command -> exit 0."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "thinker", _prose_body())
    _write_command(repo, "build", "No agent invocations here.\n")

    proc = _run(repo, [rel])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout


def test_mixed_agent_with_frontmatter_override_passes(tmp_path: Path) -> None:
    """Skill-shape but isolation_required: true -> exit 0."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(
        repo, "critic", _reference_body(), isolation_required=True
    )
    _write_command(
        repo,
        "review",
        'Task(subagent_type="critic"): review.\n'
        'Skill(skill="taste-lints").\n',
    )

    proc = _run(repo, [rel])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
    assert "isolation_required=yes" in proc.stdout


def test_three_pipeline_agent_passes_via_c3_na(tmp_path: Path) -> None:
    """Agent invoked from 3+ pipelines: c3 is N/A, score caps at 2 only if c1+c2.

    With c1 (true) + c2 (true) the score is 2, which would normally fail. The
    3-pipeline rule forces c3 to N/A (False), so the cross-cutting agent that
    is genuinely orchestrated from many commands does not trip on c3. To keep
    it below the failing threshold the body must not also be skill-shape, OR
    the agent uses an override. Here we prove c3 is suppressed: a 3-pipeline
    agent whose only signals are c1 and c3-eligible siblings scores 1 (c1),
    not 2, because c3 is N/A.
    """
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "analyst", _prose_body())
    for cmd in ("build", "plan", "review"):
        _write_command(
            repo,
            cmd,
            'Task(subagent_type="analyst"): investigate.\n'
            'Skill(skill="memory").\n',
        )

    proc = _run(repo, [rel])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # c1 true, c2 false (prose), c3 N/A => score 1.
    assert "score 1/3" in proc.stdout
    assert "pipelines=3" in proc.stdout


# ---------------------------------------------------------------------------
# Integration: PR-description override
# ---------------------------------------------------------------------------


def test_pr_description_override_token_passes(tmp_path: Path) -> None:
    """A skill-shape candidate passes when the PR body carries the token."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "shaped", _reference_body())
    _write_command(
        repo,
        "build",
        'Task(subagent_type="shaped"): do work.\n'
        'Skill(skill="pre-mortem").\n',
    )

    proc = _run(
        repo,
        [rel],
        pr_body="Adds shaped. [skill-discriminator: one-off, ships with skill next PR]",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PR override present" in proc.stdout
    assert "PASS" in proc.stdout


# ---------------------------------------------------------------------------
# Integration: two-source (ADR-036) shared template
# ---------------------------------------------------------------------------


def test_shared_template_sibling_scored(tmp_path: Path) -> None:
    """A templates/agents/*.shared.md change is scored by agent name."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(
        repo, "devops", _reference_body(), shared_template=True
    )
    _write_command(
        repo,
        "ship",
        'Task(subagent_type="devops"): release.\n'
        'Skill(skill="pipeline-validator").\n',
    )

    proc = _run(repo, [rel])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "devops" in proc.stdout


# ---------------------------------------------------------------------------
# Integration: no changed agents and exit codes
# ---------------------------------------------------------------------------


def test_no_changed_agents_passes(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    _write_command(repo, "build", "nothing.\n")
    proc = _run(repo, [])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "No changed agent definitions" in proc.stdout


def test_non_agent_changed_files_ignored(tmp_path: Path) -> None:
    repo = _scaffold(tmp_path)
    _write_command(repo, "build", "nothing.\n")
    (repo / "README.md").write_text("# readme\n", encoding="utf-8")
    proc = _run(repo, ["README.md", ".claude/agents/AGENTS.md"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "No changed agent definitions" in proc.stdout


def test_missing_repo_root_is_config_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(missing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2


def test_missing_commands_dir_is_config_error(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2


def test_changed_files_via_env(tmp_path: Path, monkeypatch) -> None:
    """CHANGED_FILES env var feeds the file list (workflow path)."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "shaped", _reference_body())
    _write_command(
        repo,
        "build",
        'Task(subagent_type="shaped"): work.\nSkill(skill="pre-mortem").\n',
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
        env={**__import__("os").environ, "CHANGED_FILES": rel},
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "shaped" in proc.stdout
