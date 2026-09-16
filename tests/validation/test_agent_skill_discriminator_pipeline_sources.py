"""The discriminator's c1/c3 corpus after ADR-064 (issue #5684).

``check_agent_skill_discriminator.py`` scored c1 and c3 by reading
``.claude/commands/`` and ``templates/commands/``, then exited 2 when the
first of those was absent. ADR-064 deleted both trees and made skills the
single user-invocable surface, and ``pre_pr.py``'s "Commands Retired
(ADR-064)" gate keeps them deleted, so every run in this repository exited 2
before scoring anything: the check was red on every PR that touched an agent
file and had been for as long as the trees were gone.

The corpus now names skills first. Two properties have to hold together, and
each is worth a test:

- a pipeline authored as a skill is read, so c1 and c3 mean what the
  discriminator docstring says they mean; and
- an empty corpus still exits 2 rather than degrading to c2-only scoring.
  c2 alone maxes out at 1 against a threshold of 2, so a degrading run could
  not fail whatever it was handed. That is the ADR-109 B1 install-parity
  failure mode, a gate reporting PASS while checking nothing, and it is worse
  than the red check it would replace.

Split from ``test_check_agent_skill_discriminator.py``, which sits at 491
lines against the 500-line ceiling in ``.claude/rules/code-quality.md``. This
is the same seam ``test_agent_skill_discriminator_fail_closed.py`` was split
on; fixture builders are imported from the parent file rather than copied.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.validation.test_check_agent_skill_discriminator import (
    SCRIPT,
    _prose_body,
    _reference_body,
    _write_agent,
)


def _write_skill(repo: Path, name: str, text: str) -> None:
    """Author a pipeline as a skill: one SKILL.md per skill directory."""
    base = repo / ".claude" / "skills" / name
    base.mkdir(parents=True, exist_ok=True)
    (base / "SKILL.md").write_text(text, encoding="utf-8")


def _write_skill_template(repo: Path, name: str, text: str) -> None:
    """Author a pipeline in the skill template tree (flat, suffixed)."""
    base = repo / "templates" / "skills"
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{name}.SKILL.md.tmpl").write_text(text, encoding="utf-8")


def _scaffold_skills(tmp_path: Path) -> Path:
    """A post-ADR-064 repository: skills and agents, no command tree."""
    repo = tmp_path / "repo"
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".claude" / "agents").mkdir(parents=True)
    return repo


def _run(repo: Path, changed: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo), "--changed"]
        + changed,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_skill_pipeline_scores_c1(tmp_path: Path) -> None:
    """An agent invoked from a SKILL.md is invoked from a pipeline.

    This is the whole point of the corpus move: before it, the same repository
    shape scored c1=n for every agent because nothing was read at all.
    """
    repo = _scaffold_skills(tmp_path)
    rel = _write_agent(repo, "shaped", _prose_body())
    _write_skill(repo, "ship", 'Task(subagent_type="shaped") runs the work.\n')

    proc = _run(repo, [rel])

    assert proc.returncode == 0, proc.stderr
    assert "c1=Y" in proc.stdout
    assert "pipelines=1" in proc.stdout


def test_skill_template_pipeline_scores_c1(tmp_path: Path) -> None:
    """The skill template tree counts too, mirroring templates/commands."""
    repo = _scaffold_skills(tmp_path)
    rel = _write_agent(repo, "shaped", _prose_body())
    _write_skill_template(
        repo, "ship", 'Task(subagent_type="shaped") runs the work.\n'
    )

    proc = _run(repo, [rel])

    assert proc.returncode == 0, proc.stderr
    assert "c1=Y" in proc.stdout


def test_skill_pipeline_scores_c3_from_sibling_skill(tmp_path: Path) -> None:
    """c3 reads a sibling Skill() invocation in the same skill pipeline.

    c1 and c3 come from the same file, so a corpus that reaches one and not
    the other would be a half-fixed gate. A reference body supplies c2, which
    puts the agent at 3/3 and makes the run fail as a candidate: that failure
    is the assertion, because it proves all three criteria were computed.
    """
    repo = _scaffold_skills(tmp_path)
    rel = _write_agent(repo, "shaped", _reference_body())
    _write_skill(
        repo,
        "ship",
        'Task(subagent_type="shaped") then Skill(skill="pipeline-validator").\n',
    )

    proc = _run(repo, [rel])

    assert proc.returncode == 1
    assert "c1=Y c2=Y c3=Y" in proc.stdout
    assert "CANDIDATE" in proc.stdout


def test_skills_only_repo_is_not_a_config_error(tmp_path: Path) -> None:
    """Regression guard for #5684: this exact shape used to exit 2.

    A repository with skills and no command tree is what ADR-064 leaves
    behind. It must score, whatever the verdict, rather than refuse.
    """
    repo = _scaffold_skills(tmp_path)
    rel = _write_agent(repo, "shaped", _prose_body())
    _write_skill(repo, "ship", "No agent invocation here.\n")

    proc = _run(repo, [rel])

    assert proc.returncode == 0, proc.stderr
    assert "Commands directory not found" not in proc.stderr
    assert "shaped" in proc.stdout


def test_no_pipeline_tree_at_all_still_fails_closed(tmp_path: Path) -> None:
    """Negative control: an empty corpus refuses instead of degrading.

    Without this, the fix for #5684 could be "skip c1/c3 and score c2", which
    passes every input because c2 alone cannot reach the threshold of 2. The
    stderr assertion names the trees searched so the refusal is actionable.
    """
    repo = tmp_path / "repo"
    (repo / ".claude" / "agents").mkdir(parents=True)
    _write_agent(repo, "shaped", _reference_body())

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 2
    assert "No pipeline source directory found" in proc.stderr
    assert ".claude/skills" in proc.stderr


def test_non_skill_markdown_inside_a_skill_is_not_a_pipeline(
    tmp_path: Path,
) -> None:
    """Only SKILL.md is a pipeline; a skill's references are not.

    Skills carry `references/*.md` holding examples and catalogs. Reading
    those as pipelines would score c1 from a documented sample invocation,
    inventing a caller that does not exist.
    """
    repo = _scaffold_skills(tmp_path)
    rel = _write_agent(repo, "shaped", _prose_body())
    _write_skill(repo, "ship", "No agent invocation here.\n")
    refs = repo / ".claude" / "skills" / "ship" / "references"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "examples.md").write_text(
        'For example: Task(subagent_type="shaped").\n', encoding="utf-8"
    )

    proc = _run(repo, [rel])

    assert proc.returncode == 0, proc.stderr
    assert "c1=n" in proc.stdout
    assert "pipelines=0" in proc.stdout
