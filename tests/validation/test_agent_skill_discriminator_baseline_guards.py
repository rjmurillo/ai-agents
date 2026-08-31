"""Guard tests for the skill-discriminator baseline ratchet (issue #4087).

Split out of ``test_agent_skill_discriminator_baseline.py`` to stay under the
project's 500-line ceiling (``.claude/rules/code-quality.md``). Covers:

- Ceiling enforcement: ``--update-baseline`` rejects score increases
- Dirty-state guard: refuses baseline writes when scoring inputs differ from
  HEAD (modified tracked files or untracked files under scoring roots)
- Error message specificity: negative vs above-max baseline values
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.validation.agent_skill_discriminator_baseline as bmod
from tests.validation.test_agent_skill_discriminator_baseline import (
    run_update_baseline,
    seed_repo,
)
from tests.validation.test_check_agent_skill_discriminator import (
    _prose_body,
    _reference_body,
    _scaffold,
    _write_agent,
    _write_command,
)


class TestBaselineCeilingEnforcement:
    """--update-baseline rejects score increases (ceiling, not floor)."""

    def test_update_baseline_rejects_score_increase(self, tmp_path: Path) -> None:
        """A rising score is a regression the ratchet must block, not record."""
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        # Record a lower ceiling than the agent's actual score of 3.
        baseline_path.write_text(
            json.dumps({"files": {rel: 1}}), encoding="utf-8"
        )
        seed_repo(repo)

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "rose from" in proc.stderr or "regression" in proc.stderr

    def test_update_baseline_accepts_score_decrease(self, tmp_path: Path) -> None:
        """A falling score tightens the ceiling, which is always safe."""
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _prose_body())
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps({"files": {rel: 3}}), encoding="utf-8"
        )
        seed_repo(repo)

        proc = run_update_baseline(repo, baseline_path, "--allow-baseline-shrink")

        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestBaselineDirtyStateGuard:
    """--update-baseline refuses dirty or untracked scoring inputs."""

    def test_update_baseline_rejects_dirty_agent(self, tmp_path: Path) -> None:
        """An uncommitted edit under a scoring root contaminates the baseline."""
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        seed_repo(repo)

        # Dirty the agent file after commit.
        (repo / rel).write_text("# changed after commit\n", encoding="utf-8")

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "modified tracked files" in proc.stderr or "dirty" in proc.stderr.lower()

    def test_update_baseline_rejects_untracked_command(self, tmp_path: Path) -> None:
        """An untracked file under a command root contaminates the baseline."""
        repo = _scaffold(tmp_path)
        _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        seed_repo(repo)

        # Add an untracked command file after commit.
        ghost_cmd = repo / ".claude" / "commands" / "ghost.md"
        ghost_cmd.write_text("Ghost command\n", encoding="utf-8")

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "untracked" in proc.stderr.lower()


class TestValidateBaselineScoresMessages:
    """The error message distinguishes negative from above-max scores."""

    def test_negative_score_message_says_fails_every_run(self) -> None:
        with pytest.raises(ValueError, match=r"fails this path on every run"):
            bmod.validate_baseline_scores({"a.md": -1})

    def test_above_max_score_message_says_disables_ratchet(self) -> None:
        with pytest.raises(ValueError, match=r"disables itself"):
            bmod.validate_baseline_scores({"a.md": 30})


class TestRefuseDirtyScoringInputs:
    """Unit tests for the dirty-state guard."""

    def test_clean_repo_is_accepted(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        seed_repo(repo)

        assert bmod.refuse_dirty_scoring_inputs(repo) is False

    def test_dirty_agent_is_refused(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "alpha", _prose_body())
        seed_repo(repo)
        (repo / rel).write_text("# dirty\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is True

    def test_untracked_command_is_refused(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        seed_repo(repo)
        ghost = repo / ".claude" / "commands" / "ghost.md"
        ghost.write_text("ghost\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is True

    def test_not_a_repo_fails_closed(self, tmp_path: Path) -> None:
        repo = tmp_path / "not-a-repo"
        repo.mkdir()

        assert bmod.refuse_dirty_scoring_inputs(repo) is True
