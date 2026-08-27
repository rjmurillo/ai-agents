"""Tests for scripts/validation/agent_skill_discriminator_baseline.py (issue #4087).

Split out of ``test_check_agent_skill_discriminator.py`` alongside the
production module split (both files were pushing past the project's 500-line
ceiling; see ``.claude/rules/code-quality.md``). Fixture builders and the
loaded discriminator module (``mod``) are reused from that sibling test file
rather than duplicated, matching the existing cross-file test-helper pattern
in this package (e.g. ``tests/validation/test_always_on_corpus_claims.py``
importing from ``always_on_corpus_helpers``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import scripts.validation.agent_skill_discriminator_baseline as bmod
from tests.validation.test_check_agent_skill_discriminator import (
    SCRIPT,
    _prose_body,
    _reference_body,
    _scaffold,
    _write_agent,
    _write_command,
    mod,
)


def _score(
    path: str, *, c1: bool = True, c2: bool = True, c3: bool = True
) -> mod.AgentScore:
    return mod.AgentScore(
        name=Path(path).stem,
        path=path,
        c1=c1,
        c2=c2,
        c3=c3,
        pipeline_count=0,
        isolation_required=False,
    )


class TestIsRegression:
    def test_agent_absent_from_baseline_uses_threshold(self) -> None:
        # No recorded floor: falls back to score>=2 (is_candidate).
        assert bmod.is_regression(_score("new.md"), {}) is True
        assert bmod.is_regression(_score("new.md", c2=False, c3=False), {}) is False

    def test_score_above_recorded_baseline_is_regression(self) -> None:
        assert bmod.is_regression(_score("a.md"), {"a.md": 2}) is True

    def test_score_at_or_below_recorded_baseline_is_not_regression(self) -> None:
        assert bmod.is_regression(_score("a.md"), {"a.md": 3}) is False
        # Equal to the recorded floor: not a regression.
        assert bmod.is_regression(_score("a.md", c3=False), {"a.md": 2}) is False


class TestFullCorpusAgentPaths:
    def test_collects_both_two_source_roots(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        rel_a = _write_agent(repo, "alpha", _prose_body())
        rel_b = _write_agent(repo, "beta", _prose_body(), shared_template=True)

        corpus = bmod.full_corpus_agent_paths(repo, mod.is_agent_path)

        assert set(corpus) == {rel_a, rel_b}

    def test_excludes_non_agent_reference_docs(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "alpha", _prose_body())
        readme = repo / ".claude" / "agents" / "README.md"
        readme.write_text("# Not an agent\n", encoding="utf-8")

        corpus = bmod.full_corpus_agent_paths(repo, mod.is_agent_path)

        assert corpus == [rel]

    def test_missing_directories_yield_empty_corpus(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty-repo"
        repo.mkdir()

        assert bmod.full_corpus_agent_paths(repo, mod.is_agent_path) == []


class TestBaselineFromScores:
    def test_keys_by_path_not_name(self) -> None:
        # A two-source agent (ADR-036) scores twice under the same derived
        # name; keying by name would let the second write silently overwrite
        # the first.
        scores = [
            _score(".claude/agents/shaped.md"),
            _score("templates/agents/shaped.shared.md", c3=False),
        ]

        baseline = bmod.baseline_from_scores(scores)

        assert baseline == {
            ".claude/agents/shaped.md": 3,
            "templates/agents/shaped.shared.md": 2,
        }


class TestBaselineNote:
    def test_no_baseline_configured_is_silent(self) -> None:
        assert bmod.baseline_note(_score("a.md"), None) == ""

    def test_agent_absent_from_baseline_is_flagged_new(self) -> None:
        assert bmod.baseline_note(_score("a.md"), {}) == " baseline=new"

    def test_regression_above_baseline_is_annotated(self) -> None:
        note = bmod.baseline_note(_score("a.md"), {"a.md": 2})
        assert note == " baseline=2 (regression)"

    def test_score_at_baseline_has_no_regression_suffix(self) -> None:
        note = bmod.baseline_note(_score("a.md"), {"a.md": 3})
        assert note == " baseline=3"


def _run_with_baseline(
    repo: Path, changed: list[str], baseline_path: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--changed-files",
            *changed,
            "--baseline",
            str(baseline_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


class TestBaselineCli:
    def _init_git(self, repo: Path) -> None:
        for command in (
            ["init", "-q"],
            ["config", "user.email", "t@example.com"],
            ["config", "user.name", "t"],
        ):
            subprocess.run(
                ["git", "-C", str(repo), *command], check=True, capture_output=True
            )

    def _commit_all(self, repo: Path) -> None:
        subprocess.run(
            ["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-qm", "seed"],
            check=True,
            capture_output=True,
        )

    def test_update_baseline_records_every_agent_score(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        self._init_git(repo)
        baseline_path = repo / "scripts" / "validation" / "baseline.json"

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(repo),
                "--baseline",
                str(baseline_path),
                "--update-baseline",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        assert proc.returncode == 0, proc.stdout + proc.stderr
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        assert data["files"][rel] == 3

    def test_baseline_mode_passes_when_score_unchanged(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        baseline_path = repo / "baseline.json"
        baseline_path.write_text(json.dumps({"files": {rel: 3}}), encoding="utf-8")

        proc = _run_with_baseline(repo, [rel], baseline_path)

        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "no agent regressed" in proc.stdout

    def test_baseline_mode_fails_when_score_rises_above_recorded_value(
        self, tmp_path: Path
    ) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        baseline_path = repo / "baseline.json"
        # Recorded floor is below the agent's actual score of 3.
        baseline_path.write_text(json.dumps({"files": {rel: 1}}), encoding="utf-8")

        proc = _run_with_baseline(repo, [rel], baseline_path)

        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "regression" in proc.stdout

    def test_baseline_mode_new_agent_uses_ordinary_threshold(
        self, tmp_path: Path
    ) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())
        _write_command(
            repo,
            "build",
            'Task(subagent_type="shaped"): do work.\n'
            'Invoke Skill(skill="pre-mortem") first.\n',
        )
        baseline_path = repo / "baseline.json"
        baseline_path.write_text(json.dumps({"files": {}}), encoding="utf-8")

        proc = _run_with_baseline(repo, [rel], baseline_path)

        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "baseline=new" in proc.stdout

    def test_missing_baseline_file_is_config_error(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        rel = _write_agent(repo, "shaped", _reference_body())

        proc = _run_with_baseline(repo, [rel], repo / "does-not-exist.json")

        assert proc.returncode == 2, proc.stdout + proc.stderr

    def test_baseline_shrink_requires_explicit_override(self, tmp_path: Path) -> None:
        repo = _scaffold(tmp_path)
        _write_agent(repo, "shaped", _reference_body())
        self._init_git(repo)
        baseline_path = repo / "scripts" / "validation" / "baseline.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps({"files": {"stale/agent.md": 3}}), encoding="utf-8"
        )
        self._commit_all(repo)

        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(repo),
                "--baseline",
                str(baseline_path),
                "--update-baseline",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        # The old repo's shaped.md replaces stale/agent.md entirely, which is
        # a dropped entry and must be refused without --allow-baseline-shrink.
        assert proc.returncode == 2, proc.stdout + proc.stderr

        proc_allowed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--repo-root",
                str(repo),
                "--baseline",
                str(baseline_path),
                "--update-baseline",
                "--allow-baseline-shrink",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        assert proc_allowed.returncode == 0, proc_allowed.stdout + proc_allowed.stderr
