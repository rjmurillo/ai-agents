"""Fail-closed guards on the discriminator baseline mode (issue #4087).

Four defects found in review of PR #5373, each one a way for the gate to
report success while gating nothing:

- a full-corpus scan that git could not answer, or that found no tracked
  agent, previously produced a corpus rather than a refusal;
- a recorded baseline score outside 0..3 passed the shared integer check and
  then made every computable score compare as "not risen";
- the per-agent report labelled a failing agent ``[ok]`` in baseline mode, and
  the failure guidance claimed "score 2+" on a gate that fails at any score;
- ``--update-baseline`` wrote beneath ``--repo-root`` without confirming the
  process was standing inside it.

Split from ``test_agent_skill_discriminator_baseline.py`` to keep both files
under the project's 500-line ceiling (`.claude/rules/code-quality.md`), the
same seam the production modules were split on. Fixture builders and the git
helpers are imported from that sibling rather than duplicated.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.validation.test_agent_skill_discriminator_baseline import (
    init_git,
    run_update_baseline,
    seed_repo,
)
from tests.validation.test_check_agent_skill_discriminator import (
    SCRIPT,
    _reference_body,
    _scaffold,
    _write_agent,
    _write_command,
)


def _shaped_repo(tmp_path: Path, *, commit: bool = True) -> tuple[Path, str]:
    """A scaffolded repo holding one agent that scores 3/3."""
    repo = _scaffold(tmp_path)
    rel = _write_agent(repo, "shaped", _reference_body())
    _write_command(
        repo,
        "build",
        'Task(subagent_type="shaped"): do work.\n'
        'Invoke Skill(skill="pre-mortem") first.\n',
    )
    if commit:
        seed_repo(repo)
    return repo, rel


def _run(
    repo: Path, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo), *args],
        cwd=str(cwd if cwd is not None else repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


class TestFullCorpusRefusals:
    """``--all`` and ``--update-baseline`` refuse an unknown or empty corpus."""

    def test_all_exits_two_when_git_cannot_answer(self, tmp_path: Path) -> None:
        repo, _rel = _shaped_repo(tmp_path, commit=False)

        proc = _run(repo, "--all")

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "tracked at HEAD" in proc.stderr
        # Control: the same tree passes once HEAD exists, so the refusal is
        # about the missing ref and not about the fixture being unscorable.
        seed_repo(repo)
        assert _run(repo, "--all").returncode == 1

    def test_update_baseline_exits_two_and_writes_nothing_without_head(
        self, tmp_path: Path
    ) -> None:
        """A repository, but no commit yet: the discriminating shape.

        With no git repository at all the write is refused anyway, by the
        baseline diffability guard that needs git for its own reasons, so that
        setup cannot tell the two implementations apart. ``git init`` with no
        commit satisfies every guard except the one under test: ``ls-tree
        HEAD`` has no ref to read, while a directory walk finds the agent and
        records it.
        """
        repo, _rel = _shaped_repo(tmp_path, commit=False)
        init_git(repo)
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        assert not baseline_path.exists()

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "tracked at HEAD" in proc.stderr
        assert not baseline_path.exists(), (
            "A baseline was written from a scan that never established what "
            "the commit contains."
        )

    def test_update_baseline_refuses_an_empty_corpus(self, tmp_path: Path) -> None:
        """An empty baseline gates nothing and reads as a clean pass."""
        repo = _scaffold(tmp_path)
        (repo / "README.md").write_text("# no agents here\n", encoding="utf-8")
        seed_repo(repo)
        baseline_path = repo / "scripts" / "validation" / "baseline.json"

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "examined 0" in proc.stderr
        assert not baseline_path.exists()

    def test_an_untracked_agent_is_not_recorded_in_the_baseline(
        self, tmp_path: Path
    ) -> None:
        """Two checkouts of one commit must record the same baseline.

        The dirty-state guard (refuse_dirty_scoring_inputs) rejects the write
        when untracked files exist under a scoring root. This is the correct
        behavior: an untracked agent would produce a baseline that differs
        from what CI can reproduce from the same commit.
        """
        repo, rel = _shaped_repo(tmp_path)
        _write_agent(repo, "ghost", _reference_body())
        baseline_path = repo / "scripts" / "validation" / "baseline.json"

        proc = run_update_baseline(repo, baseline_path)

        assert proc.returncode == 2, (
            f"Expected config-error exit 2 (dirty-state refusal), "
            f"got {proc.returncode}.\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
        )
        assert not baseline_path.exists(), (
            "Baseline file was written despite untracked scoring inputs."
        )


class TestBaselineScoreRange:
    """A score outside 0..3 is a config error, never a silent pass."""

    def _baseline(self, repo: Path, value: int, rel: str) -> Path:
        path = repo / "baseline.json"
        path.write_text(json.dumps({"files": {rel: value}}), encoding="utf-8")
        return path

    def test_an_oversized_score_is_a_config_error(self, tmp_path: Path) -> None:
        """30 silently disables the ratchet: no score can rise above it."""
        repo, rel = _shaped_repo(tmp_path)
        baseline_path = self._baseline(repo, 30, rel)

        proc = _run(repo, "--changed-files", rel, "--baseline", str(baseline_path))

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "outside the valid range 0..3" in proc.stderr
        assert "PASS" not in proc.stdout

    def test_a_negative_score_is_a_config_error(self, tmp_path: Path) -> None:
        repo, rel = _shaped_repo(tmp_path)
        baseline_path = self._baseline(repo, -1, rel)

        proc = _run(repo, "--changed-files", rel, "--baseline", str(baseline_path))

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "outside the valid range 0..3" in proc.stderr

    def test_the_ceiling_value_itself_is_accepted(self, tmp_path: Path) -> None:
        """Control: 3 is a real score and must not be rejected as oversized."""
        repo, rel = _shaped_repo(tmp_path)
        baseline_path = self._baseline(repo, 3, rel)

        proc = _run(repo, "--changed-files", rel, "--baseline", str(baseline_path))

        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestBaselineModeReport:
    """The report names the gate that ran, not the threshold that did not."""

    def _low_scoring_repo(self, tmp_path: Path) -> tuple[Path, str]:
        """An agent scoring exactly 1/3: invoked from one pipeline, prose body.

        1 is below the score>=2 threshold and above a recorded floor of 0, so
        it is the only input on which the two gates disagree.
        """
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "mild", "Some prose about reasoning.\n")
        _write_command(repo, "build", 'Task(subagent_type="mild"): do work.\n')
        seed_repo(repo)
        return repo, rel

    def test_a_rise_from_zero_to_one_fails_and_is_not_labelled_ok(
        self, tmp_path: Path
    ) -> None:
        repo, rel = self._low_scoring_repo(tmp_path)
        baseline_path = repo / "baseline.json"
        baseline_path.write_text(json.dumps({"files": {rel: 0}}), encoding="utf-8")

        proc = _run(repo, "--changed-files", rel, "--baseline", str(baseline_path))

        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "score 1/3" in proc.stdout, proc.stdout
        assert "[REGRESSION] mild" in proc.stdout, proc.stdout
        assert "[ok] mild" not in proc.stdout, (
            "The agent that made the run exit 1 was labelled ok."
        )

    def test_the_failure_guidance_does_not_claim_score_two_plus(
        self, tmp_path: Path
    ) -> None:
        repo, rel = self._low_scoring_repo(tmp_path)
        baseline_path = repo / "baseline.json"
        baseline_path.write_text(json.dumps({"files": {rel: 0}}), encoding="utf-8")

        proc = _run(repo, "--changed-files", rel, "--baseline", str(baseline_path))

        assert "skill-shape candidates (score 2+)" not in proc.stdout, (
            "Baseline mode failed an agent scoring 1 while telling the reader "
            "the failures are agents scoring 2+."
        )
        assert "baseline ratchet" in proc.stdout
        assert "at any score" in proc.stdout

    def test_threshold_mode_still_says_candidate_and_score_two_plus(
        self, tmp_path: Path
    ) -> None:
        """Control: the wording only changes where a baseline is in force."""
        repo, rel = _shaped_repo(tmp_path)

        proc = _run(repo, "--changed-files", rel)

        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "[CANDIDATE] shaped" in proc.stdout
        assert "skill-shape candidates (score 2+)" in proc.stdout
        assert "REGRESSION" not in proc.stdout

    def test_an_agent_at_its_recorded_floor_is_labelled_ok(
        self, tmp_path: Path
    ) -> None:
        """Control: baseline mode does not label every agent a regression."""
        repo, rel = _shaped_repo(tmp_path)
        baseline_path = repo / "baseline.json"
        baseline_path.write_text(json.dumps({"files": {rel: 3}}), encoding="utf-8")

        proc = _run(repo, "--changed-files", rel, "--baseline", str(baseline_path))

        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "[ok] shaped" in proc.stdout
        assert "REGRESSION" not in proc.stdout


class TestUpdateBaselineWorktreeIdentity:
    """MUST-7: confirm the process is inside the root before the first write."""

    def test_a_run_from_outside_the_repo_root_exits_two(
        self, tmp_path: Path
    ) -> None:
        repo, _rel = _shaped_repo(tmp_path)
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        assert not baseline_path.exists()

        proc = run_update_baseline(repo, baseline_path, cwd=elsewhere)

        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "MUST-7" in proc.stderr
        assert not baseline_path.exists(), (
            "The guard raised after the write instead of before it."
        )

    def test_the_same_run_from_inside_the_repo_root_succeeds(
        self, tmp_path: Path
    ) -> None:
        """Control: the refusal is about the cwd and nothing else."""
        repo, _rel = _shaped_repo(tmp_path)
        baseline_path = repo / "scripts" / "validation" / "baseline.json"

        proc = run_update_baseline(repo, baseline_path, cwd=repo)

        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert baseline_path.is_file()

    def test_a_subdirectory_of_the_repo_root_is_inside_it(
        self, tmp_path: Path
    ) -> None:
        """``is_relative_to`` accepts a descendant, not only the root itself."""
        repo, _rel = _shaped_repo(tmp_path)
        baseline_path = repo / "scripts" / "validation" / "baseline.json"

        proc = run_update_baseline(repo, baseline_path, cwd=repo / ".claude")

        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert baseline_path.is_file()
