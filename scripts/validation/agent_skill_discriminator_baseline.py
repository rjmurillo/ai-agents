"""Full-corpus baseline ratchet for the agent-skill discriminator (issue #4087).

`check_agent_skill_discriminator.py` is change-triggered by default: an agent
that is already skill-shaped on `main` stays invisible until an unrelated edit
happens to touch it, which makes the gate fire on PRs that cannot have caused
the condition (PR #4067, PR #4063). `--update-baseline` scores every agent in
the repo and records each one's score in a checked-in JSON file. A later run
with `--baseline <path>` then fails an agent only when its score has risen
above the recorded value; a new agent absent from the baseline still uses the
ordinary score>=2 threshold.

Split out of the discriminator module itself to hold this file under the
project's 500-line ceiling (`.claude/rules/code-quality.md`) and to keep the
ratchet's own logic separately testable. It does not put the discriminator
module under that ceiling: `check_agent_skill_discriminator.py` was already
past it on `main` and remains an open taste-lint error there, counted in the
existing baseline rather than introduced here. The two modules
still share one contract (`AgentScore`), imported here only under
`TYPE_CHECKING` to avoid a runtime circular import; `full_corpus_agent_paths`
takes its agent-path predicate as a parameter for the same reason, rather than
importing `is_agent_path` back from the discriminator module.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.portability_git import git_timeout_problem, run_git

if TYPE_CHECKING:
    from scripts.validation.check_agent_skill_discriminator import AgentScore

# Default location for the full-corpus baseline (issue #4087).
DEFAULT_BASELINE_NAME = "agent_skill_discriminator_baseline.json"

# The two-source agent roots (ADR-036). A tracked path outside both is not an
# agent definition whatever its name, so the corpus never leaves them.
AGENT_CORPUS_ROOTS: tuple[str, ...] = (".claude/agents/", "templates/agents/")

# Command roots searched for c1/c3 scoring. Dirty files under these roots
# also contaminate a baseline because ``build_pipeline_index`` reads them
# from disk.
COMMAND_ROOTS: tuple[str, ...] = (".claude/commands/", "templates/commands/")

# All roots whose on-disk content feeds into scoring. Used by the dirty-state
# guard to refuse a baseline write when the working tree differs from HEAD.
SCORING_ROOTS: tuple[str, ...] = AGENT_CORPUS_ROOTS + COMMAND_ROOTS

# Closed range a recorded baseline score may occupy.
#
# Canonical source, ``check_agent_skill_discriminator.py`` ``AgentScore.score``,
# quoted verbatim:
#
#     return int(self.c1) + int(self.c2) + int(self.c3)
#
# Three booleans summed, so no real score can fall outside 0..3. A committed
# value above the ceiling silently disables the ratchet for that path, because
# every score the checker can compute compares as "not risen"; a negative value
# fails the path on every run. Both are config defects, not gate outcomes.
MIN_BASELINE_SCORE = 0
MAX_BASELINE_SCORE = 3


def validate_baseline_scores(baseline: Mapping[str, int]) -> None:
    """Raise ``ValueError`` when a recorded score is outside 0..3 (issue #4087).

    ``portability_common.load_baseline`` is the canonical reader and vets the
    JSON shape: it refuses a non-object payload and refuses any value that is
    not a JSON integer (bool excluded). That contract is shared with the
    portability ratchets, whose values are unbounded per-file counts, so the
    range cannot be pushed down into it.

    Stricter than canonical: this adds the discriminator-specific bound on top
    of the shared reader rather than replacing it. Callers run both, in order.
    """
    for path, value in sorted(baseline.items()):
        if not MIN_BASELINE_SCORE <= value <= MAX_BASELINE_SCORE:
            if value < MIN_BASELINE_SCORE:
                effect = (
                    "every valid score compares as above the baseline, so "
                    "the ratchet fails this path on every run"
                )
            else:
                effect = (
                    "every valid score compares as at or below the baseline, "
                    "so the ratchet silently disables itself for this path"
                )
            raise ValueError(
                f"Baseline score for {path!r} is {value}, outside the valid "
                f"range {MIN_BASELINE_SCORE}..{MAX_BASELINE_SCORE}. A "
                f"discriminator score is the sum of three booleans; {effect}."
            )


def is_regression(score: AgentScore, baseline: Mapping[str, int]) -> bool:
    """True when ``score`` fails the baseline-relative gate (issue #4087).

    An agent already recorded in the baseline fails only when its score has
    risen above the recorded value, so pre-existing debt does not re-fail
    every PR that happens to touch the file (PR #4067, PR #4063). An agent
    absent from the baseline -- new, renamed, or moved -- has no recorded
    floor, so it falls back to the ordinary score>=2 threshold.

    Stricter/looser/different than canonical: this deliberately does not call
    ``portability_common.diff_against_baseline``. That ratchet is symmetric:
    it also flags a path whose baseline entry no longer matches, i.e., one
    with a *lower* current count than its baseline says has "improved" and
    blocks a plain run until ``--update-baseline`` tightens it. That symmetry
    assumes ``current`` and ``baseline`` cover the same universe, true for a
    full-corpus scan (``--all`` / ``--update-baseline``) but false for the
    default changed-files gate, whose ``current`` holds only the agents one
    PR touched. Reusing the symmetric ratchet there would read every agent
    outside that PR's diff as a false "improvement" on every single run,
    since it never appears in ``current`` at all. Comparing one score against
    its own baseline entry, with nothing said about the agents that are not
    in ``score``'s run, avoids that false positive in both modes.
    """
    entry = baseline.get(score.path)
    if entry is None:
        return score.is_candidate
    return score.score > entry


def tracked_paths_at_head(repo_root: Path) -> list[str] | None:
    """Paths tracked at ``HEAD``, or ``None`` when git could not answer.

    ``-z`` because paths are not newline-safe, and ``--name-only`` because
    only the pathname matters here; entry mode does not. ``run_git`` strips
    every ``GIT_*`` override and disables replacement objects, so the answer
    describes this checkout's ``HEAD`` and not a redirected one.

    ``None`` is a refusal, never an empty answer. "git errored" and "the tree
    holds nothing" must not reach the caller as the same value, which is the
    discipline ``portability_git`` was split out to keep.
    """
    proc = run_git(repo_root, "ls-tree", "-r", "-z", "--name-only", "HEAD")
    if problem := git_timeout_problem(proc, "listing tracked paths at HEAD"):
        print(problem, file=sys.stderr)
        return None
    if proc is None or proc.returncode != 0:
        return None
    listing = proc.stdout.decode("utf-8", errors="replace")
    return [path for path in listing.split("\0") if path]


def full_corpus_agent_paths(
    repo_root: Path, is_agent_path: Callable[[str], bool]
) -> list[str] | None:
    """Every tracked agent-definition path at ``HEAD``, or ``None`` (issue #4087).

    Shared by ``--all`` (score everything, apply the normal/baseline gate)
    and ``--update-baseline`` (score everything, record it, do not gate).
    ``is_agent_path`` is injected rather than imported, to keep this module
    free of a runtime dependency back on the discriminator module.

    Read from a named ref rather than walked on disk, per
    ``.claude/rules/ci-scripts.md`` MUST-9: "A ratchet baseline is a claim
    about a ref, so the measurement behind it MUST NOT read untracked state".
    A directory walk answered a different question in three ways that all
    produce a wrong baseline from a correct-looking run. It counted untracked
    agent files a contributor happened to have on disk and CI never will. It
    returned an empty corpus for a partial or sparse checkout, which reads
    identically to a repository with no agents. And it made two checkouts of
    the same commit disagree, which is exactly the property a baseline has to
    have to be worth committing.

    ``None`` means git could not answer and the corpus is unknown. The caller
    must fail closed on it; falling back to a walk restores the defect.
    """
    tracked = tracked_paths_at_head(repo_root)
    if tracked is None:
        return None
    return sorted(
        path
        for path in tracked
        if path.startswith(AGENT_CORPUS_ROOTS) and is_agent_path(path)
    )


def refuse_dirty_scoring_inputs(
    repo_root: Path, roots: tuple[str, ...] = SCORING_ROOTS
) -> bool:
    """Refuse a baseline write when scoring inputs differ from HEAD.

    The path inventory comes from ``git ls-tree HEAD``, but ``score_agent``
    reads agent content with ``Path.read_text()`` and
    ``build_pipeline_index`` walks command files on disk. If the working tree
    has dirty tracked files or untracked files under any scoring root, the
    recorded baseline describes a state that differs from HEAD and two
    checkouts of the same commit can produce different baselines.

    ``roots`` defaults to this checker's own scoring roots. It is a parameter
    because the property is not agent-specific: any ratchet that inventories
    paths from a ref and then reads content from disk needs the same refusal,
    and `check_memory_placement.py` passes ``.serena/memories/`` for it.

    Returns True (refuse) when dirty or untracked files exist under any
    scoring root, or when git cannot answer.
    """
    # Check for modified/deleted tracked files under scoring roots.
    proc = run_git(repo_root, "diff", "--name-only", "HEAD", "--", *roots)
    if problem := git_timeout_problem(proc, "checking dirty scoring inputs"):
        print(problem, file=sys.stderr)
        return True  # fail closed
    if proc is None or proc.returncode != 0:
        print(
            "Cannot verify working-tree cleanliness: git diff failed.",
            file=sys.stderr,
        )
        return True
    dirty = proc.stdout.decode("utf-8", errors="replace").strip()
    if dirty:
        print(
            f"Refusing baseline write: modified tracked files under scoring "
            f"roots:\n{dirty}\n"
            "Commit or stash changes before running --update-baseline.",
            file=sys.stderr,
        )
        return True

    # Check for untracked files under scoring roots.
    proc = run_git(
        repo_root, "ls-files", "--others", "--exclude-standard", "--", *roots
    )
    if problem := git_timeout_problem(proc, "checking untracked scoring inputs"):
        print(problem, file=sys.stderr)
        return True
    if proc is None or proc.returncode != 0:
        return True
    untracked = proc.stdout.decode("utf-8", errors="replace").strip()
    if untracked:
        print(
            f"Refusing baseline write: untracked files under scoring roots:\n"
            f"{untracked}\n"
            "Remove or commit untracked files before running --update-baseline.",
            file=sys.stderr,
        )
        return True

    return False


def baseline_from_scores(scores: list[AgentScore]) -> dict[str, int]:
    """Build a baseline payload: path -> score, for ``--update-baseline``.

    Keyed by path rather than by derived agent name. A two-source agent
    (ADR-036) scores twice in one ``--all``/``--update-baseline`` run, once
    for ``.claude/agents/<name>.md`` and once for its
    ``templates/agents/<name>.shared.md`` sibling, and both entries share the
    same ``AgentScore.name``. Keying by name would let the second write
    silently overwrite the first in this dict; keying by path keeps both.
    """
    return {s.path: s.score for s in scores}


def baseline_note(score: AgentScore, baseline: dict[str, int] | None) -> str:
    """Trailing report annotation showing the baseline comparison, if any."""
    if baseline is None:
        return ""
    entry = baseline.get(score.path)
    if entry is None:
        return " baseline=new"
    if score.score > entry:
        return f" baseline={entry} (regression)"
    return f" baseline={entry}"
