"""Full-corpus baseline ratchet for the agent-skill discriminator (issue #4087).

`check_agent_skill_discriminator.py` is change-triggered by default: an agent
that is already skill-shaped on `main` stays invisible until an unrelated edit
happens to touch it, which makes the gate fire on PRs that cannot have caused
the condition (PR #4067, PR #4063). `--update-baseline` scores every agent in
the repo and records each one's score in a checked-in JSON file. A later run
with `--baseline <path>` then fails an agent only when its score has risen
above the recorded value; a new agent absent from the baseline still uses the
ordinary score>=2 threshold.

Split out of the discriminator module itself to keep both files under the
project's 500-line ceiling (`.claude/rules/code-quality.md`). The two modules
still share one contract (`AgentScore`), imported here only under
`TYPE_CHECKING` to avoid a runtime circular import; `full_corpus_agent_paths`
takes its agent-path predicate as a parameter for the same reason, rather than
importing `is_agent_path` back from the discriminator module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.check_agent_skill_discriminator import AgentScore

# Default location for the full-corpus baseline (issue #4087).
DEFAULT_BASELINE_NAME = "agent_skill_discriminator_baseline.json"


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


def full_corpus_agent_paths(
    repo_root: Path, is_agent_path: Callable[[str], bool]
) -> list[str]:
    """Every agent-definition path across both two-source roots (issue #4087).

    Shared by ``--all`` (score everything, apply the normal/baseline gate)
    and ``--update-baseline`` (score everything, record it, do not gate).
    ``is_agent_path`` is injected rather than imported, to keep this module
    free of a runtime dependency back on the discriminator module.
    """
    agents_dir = repo_root / ".claude" / "agents"
    templates_dir = repo_root / "templates" / "agents"
    corpus: list[str] = []
    for directory in (agents_dir, templates_dir):
        if directory.is_dir():
            for p in sorted(directory.rglob("*.md")):
                rel = str(p.relative_to(repo_root))
                if is_agent_path(rel):
                    corpus.append(rel)
    return corpus


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
