"""Tests for the agent drift detector's install-copy comparison.

Issue #2267: detect_agent_drift.py gained a second comparison pass that checks
the hand-maintained install copies (.claude/agents/*.md vs
.github/agents/*.agent.md) for shared-template agents, in addition to the
existing vendored comparison (src/claude vs src/vs-code-agents).

Covers the new helpers (shared_template_names, run_detection restrict_to,
run_install_detection) and the advisory exit-code policy: vendored drift always
blocks, install drift is advisory unless --fail-on-install-drift is set.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "build" / "scripts" / "detect_agent_drift.py"

# Load the module by path: build/scripts is not an importable package.
_spec = importlib.util.spec_from_file_location("detect_agent_drift", _SCRIPT)
assert _spec is not None and _spec.loader is not None
drift = importlib.util.module_from_spec(_spec)
sys.modules["detect_agent_drift"] = drift
_spec.loader.exec_module(drift)


# A minimal agent body that yields high similarity when compared with itself.
_AGENT_BODY = """---
name: {name}
---

# {Name}

## Core Mission

Do the one thing the {name} agent does, the same way in every copy.

## Key Responsibilities

- Responsibility one for {name}.
- Responsibility two for {name}.

## Constraints

- Stay within the {name} lane.
"""


def _write_agent(path: Path, name: str, body: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = body if body is not None else _AGENT_BODY.format(name=name, Name=name.title())
    path.write_text(content, encoding="utf-8")


def _divergent_body(name: str) -> str:
    """An agent body for ``name`` whose Core Mission shares no words with the
    canonical body, so the comparison reports low similarity (drift)."""
    return (
        f"---\nname: {name}\n---\n\n"
        f"# {name.title()}\n\n"
        "## Core Mission\n\n"
        "Totally different prose with zero overlapping vocabulary.\n"
    )


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Build a small repo tree with templates and install copies."""
    templates = tmp_path / "templates" / "agents"
    claude_install = tmp_path / ".claude" / "agents"
    github_install = tmp_path / ".github" / "agents"
    for name in ("alpha", "beta"):
        _write_agent(templates / f"{name}.shared.md", name)
        _write_agent(claude_install / f"{name}.md", name)
        _write_agent(github_install / f"{name}.agent.md", name)
    # Directory metadata that must be ignored.
    _write_agent(claude_install / "AGENTS.md", "agents-meta")
    _write_agent(claude_install / "CLAUDE.md", "claude-meta")
    # Freestanding Claude-only agent: no template, no github sibling.
    _write_agent(claude_install / "claude-only.md", "claude-only")
    return tmp_path


# --- shared_template_names -------------------------------------------------


def test_shared_template_names_lists_stems(fake_repo: Path) -> None:
    names = drift.shared_template_names(fake_repo / "templates" / "agents")

    assert names == frozenset({"alpha", "beta"})


def test_shared_template_names_empty_when_no_templates(tmp_path: Path) -> None:
    (tmp_path / "templates" / "agents").mkdir(parents=True)

    assert drift.shared_template_names(tmp_path / "templates" / "agents") == frozenset()


# --- run_detection restrict_to and metadata skipping ------------------------


def test_run_detection_skips_metadata_files(fake_repo: Path) -> None:
    results = drift.run_detection(
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
    )
    names = {r.agent_name for r in results}

    assert "AGENTS" not in names
    assert "CLAUDE" not in names


def test_run_detection_restrict_to_excludes_freestanding(fake_repo: Path) -> None:
    results = drift.run_detection(
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
        restrict_to=frozenset({"alpha", "beta"}),
    )
    names = {r.agent_name for r in results}

    assert names == {"alpha", "beta"}
    assert "claude-only" not in names


def test_run_detection_restrict_to_reports_missing_source(fake_repo: Path) -> None:
    (fake_repo / ".claude" / "agents" / "beta.md").unlink()

    results = drift.run_detection(
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
        restrict_to=frozenset({"alpha", "beta"}),
    )
    by_name = {r.agent_name: r for r in results}

    assert by_name["alpha"].status == "OK"
    assert by_name["beta"].status == "NO COUNTERPART"
    assert by_name["beta"].overall_similarity is None


def test_run_detection_stamps_comparison_label(fake_repo: Path) -> None:
    results = drift.run_detection(
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
        restrict_to=frozenset({"alpha"}),
        comparison="install",
    )

    assert all(r.comparison == "install" for r in results)


# --- run_install_detection --------------------------------------------------


def test_install_detection_matches_identical_copies(fake_repo: Path) -> None:
    results = drift.run_install_detection(
        fake_repo / "templates" / "agents",
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
    )

    assert {r.agent_name for r in results} == {"alpha", "beta"}
    assert all(r.status == "OK" for r in results)


def test_install_detection_flags_drift(fake_repo: Path) -> None:
    # Make the github copy of beta diverge structurally.
    _write_agent(
        fake_repo / ".github" / "agents" / "beta.agent.md",
        "beta",
        body=_divergent_body("beta"),
    )

    results = drift.run_install_detection(
        fake_repo / "templates" / "agents",
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
    )
    by_name = {r.agent_name: r for r in results}

    assert by_name["alpha"].status == "OK"
    assert by_name["beta"].status == "DRIFT DETECTED"


def test_install_detection_flags_missing_shared_agent(fake_repo: Path) -> None:
    (fake_repo / ".claude" / "agents" / "beta.md").unlink()

    results = drift.run_install_detection(
        fake_repo / "templates" / "agents",
        fake_repo / ".claude" / "agents",
        fake_repo / ".github" / "agents",
        threshold=80,
    )
    by_name = {r.agent_name: r for r in results}

    assert by_name["alpha"].status == "OK"
    assert by_name["beta"].status == "NO COUNTERPART"


def test_install_detection_returns_empty_without_templates(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".github" / "agents").mkdir(parents=True)

    results = drift.run_install_detection(
        tmp_path / "templates" / "agents",  # missing
        tmp_path / ".claude" / "agents",
        tmp_path / ".github" / "agents",
        threshold=80,
    )

    assert results == []


# --- _exit_code advisory policy ---------------------------------------------


def _drift_result(name: str, comparison: str) -> object:
    return drift.AgentResult(
        agent_name=name,
        overall_similarity=10.0,
        status="DRIFT DETECTED",
        comparison=comparison,
    )


def test_exit_code_vendored_drift_always_blocks() -> None:
    vendored = _drift_result("merge-resolver", "src-claude vs src-vscode")

    assert drift._exit_code([vendored], [], fail_on_install=False) == 1


def test_exit_code_install_drift_is_advisory_by_default() -> None:
    install = _drift_result("orchestrator", drift._INSTALL_COMPARISON_LABEL)

    assert drift._exit_code([install], [install], fail_on_install=False) == 0


def test_exit_code_uses_comparison_label_for_install_results() -> None:
    install = _drift_result("orchestrator", drift._INSTALL_COMPARISON_LABEL)

    assert drift._exit_code([install], [], fail_on_install=False) == 0


def test_exit_code_install_drift_blocks_when_flag_set() -> None:
    install = _drift_result("orchestrator", drift._INSTALL_COMPARISON_LABEL)

    assert drift._exit_code([install], [install], fail_on_install=True) == 1


def test_exit_code_missing_install_counterpart_blocks_when_flag_set() -> None:
    install = drift.AgentResult(
        agent_name="orchestrator",
        overall_similarity=None,
        status="NO COUNTERPART",
        comparison=drift._INSTALL_COMPARISON_LABEL,
    )

    assert drift._exit_code([install], [install], fail_on_install=True) == 1


def test_exit_code_missing_vendored_counterpart_does_not_block_strict_install() -> None:
    vendored = drift.AgentResult(
        agent_name="claude-instructions.template",
        overall_similarity=None,
        status="NO COUNTERPART",
        comparison="src-claude vs src-vscode",
    )

    assert drift._exit_code([vendored], [], fail_on_install=True) == 0


def test_exit_code_zero_when_no_drift() -> None:
    assert drift._exit_code([], [], fail_on_install=False) == 0


# --- main() integration: install drift does not change the exit code --------


def test_main_install_drift_advisory_exit_zero(fake_repo: Path) -> None:
    # Diverge an install copy but keep the vendored dirs identical (point both
    # at the same templates dir so vendored similarity is 100%).
    _write_agent(
        fake_repo / ".github" / "agents" / "alpha.agent.md",
        "alpha",
        body=_divergent_body("alpha"),
    )

    exit_code = drift.main(
        [
            "--claude-path",
            str(fake_repo / "templates" / "agents"),
            "--vscode-path",
            str(fake_repo / "templates" / "agents"),
            "--templates-path",
            str(fake_repo / "templates" / "agents"),
            "--claude-install-path",
            str(fake_repo / ".claude" / "agents"),
            "--github-install-path",
            str(fake_repo / ".github" / "agents"),
            "--output-format",
            "json",
        ]
    )

    assert exit_code == 0


def test_main_install_drift_blocks_with_flag(fake_repo: Path) -> None:
    _write_agent(
        fake_repo / ".github" / "agents" / "alpha.agent.md",
        "alpha",
        body=_divergent_body("alpha"),
    )

    exit_code = drift.main(
        [
            "--claude-path",
            str(fake_repo / "templates" / "agents"),
            "--vscode-path",
            str(fake_repo / "templates" / "agents"),
            "--templates-path",
            str(fake_repo / "templates" / "agents"),
            "--claude-install-path",
            str(fake_repo / ".claude" / "agents"),
            "--github-install-path",
            str(fake_repo / ".github" / "agents"),
            "--fail-on-install-drift",
        ]
    )

    assert exit_code == 1


def test_main_missing_install_path_returns_exit_2(
    fake_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = drift.main(
        [
            "--claude-path",
            str(fake_repo / "templates" / "agents"),
            "--vscode-path",
            str(fake_repo / "templates" / "agents"),
            "--templates-path",
            str(fake_repo / "missing" / "templates"),
            "--claude-install-path",
            str(fake_repo / ".claude" / "agents"),
            "--github-install-path",
            str(fake_repo / ".github" / "agents"),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "install comparison path(s) not found" in captured.err


def test_main_skip_install_comparison_only_vendored(fake_repo: Path) -> None:
    # Diverge an install copy; with --skip-install-comparison it must not show.
    _write_agent(
        fake_repo / ".github" / "agents" / "alpha.agent.md",
        "alpha",
        body=_divergent_body("alpha"),
    )

    exit_code = drift.main(
        [
            "--claude-path",
            str(fake_repo / "templates" / "agents"),
            "--vscode-path",
            str(fake_repo / "templates" / "agents"),
            "--skip-install-comparison",
        ]
    )

    assert exit_code == 0
