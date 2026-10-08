"""Pipeline-root coverage of the discriminator baseline dirty-state guard.

Split out of ``test_agent_skill_discriminator_baseline_guards.py`` to keep that
file cohesive. The guard must cover every tree ``PIPELINE_SOURCES`` reads, so a
dirty SKILL.md or skill template cannot contaminate a recorded baseline.
"""

from __future__ import annotations

from pathlib import Path

import scripts.validation.agent_skill_discriminator_baseline as bmod
import scripts.validation.check_agent_skill_discriminator as dmod
from tests.validation.test_agent_skill_discriminator_baseline import (
    run_update_baseline,
    seed_repo,
)
from tests.validation.test_check_agent_skill_discriminator import (
    _prose_body,
    _scaffold,
    _write_agent,
)


class TestPipelineRootGuard:
    """The guard covers every tree the scorer reads pipelines from."""

    def test_dirty_skill_is_refused(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        skill = repo / ".claude" / "skills" / "build" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text('Task(subagent_type="alpha")\n', encoding="utf-8")
        seed_repo(repo)
        skill.write_text("# dirty\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is True

    def test_untracked_skill_template_is_refused(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        seed_repo(repo)
        tmpl = repo / "templates" / "skills" / "ghost.SKILL.md.tmpl"
        tmpl.parent.mkdir(parents=True)
        tmpl.write_text("ghost\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is True

    def test_update_baseline_rejects_dirty_skill(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        skill = repo / ".claude" / "skills" / "build" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("clean\n", encoding="utf-8")
        seed_repo(repo)
        skill.write_text("# dirty\n", encoding="utf-8")
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "modified tracked files" in proc.stderr
        assert not baseline_path.exists()

    def test_dirty_file_outside_scoring_roots_is_accepted(
        self, tmp_path: Path
    ) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "alpha", _prose_body())
        doc = repo / "docs" / "x.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("clean\n", encoding="utf-8")
        seed_repo(repo)
        doc.write_text("# dirty\n", encoding="utf-8")
        (repo / "docs" / "new.md").write_text("untracked\n", encoding="utf-8")

        assert bmod.refuse_dirty_scoring_inputs(repo) is False

    def test_scoring_roots_cover_every_pipeline_source(self) -> None:
        """Conformance: a tree added to PIPELINE_SOURCES is guarded too."""
        sources = {f"{rel}/" for rel, _ in dmod.PIPELINE_SOURCES}

        assert sources <= set(bmod.SCORING_ROOTS)
        assert set(bmod.AGENT_CORPUS_ROOTS) <= set(bmod.SCORING_ROOTS)
        assert dmod.PIPELINE_SOURCES is bmod.PIPELINE_SOURCES
