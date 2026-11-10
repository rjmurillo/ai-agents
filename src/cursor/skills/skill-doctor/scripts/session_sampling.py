"""Choose which scoreable sessions to sample, balanced across harnesses.

Python 3.10+, stdlib only. Local change to the Warp fork (issue #7187): the
upstream sampler had no harness dimension, so one harness could take the whole
cap. See docs/skill-doctor-upstream-sync.md in the source repository.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

SAMPLING_RULE = (
    "Harnesses with scoreable sessions are ranked by scoreable count (descending), "
    "then by harness name (ascending). The --max-sessions cap is dealt one slot at a time "
    "to that ranking, round-robin, and a harness never receives more slots than it has "
    "scoreable sessions. When the cap is lower than the number of harnesses, only the "
    "first harnesses in the ranking receive a slot. A harness with no scoreable session "
    "takes no slot."
)

WITHIN_HARNESS_RULE = (
    "Inside each harness, sessions that used an installed skill are taken first, newest "
    "first, until each skill has --per-skill sessions. Remaining slots go to sessions "
    "that used no skill, newest first, up to --no-skill. This is skill-first selection: "
    "it favors sessions that exercise skills, so per-harness grades describe that "
    "slice, not the harness as a whole. The --per-skill and --no-skill caps apply "
    "within each harness, and a quota the caps cannot fill is left unused."
)


def sample_one_harness(sessions: Any, skills: Any, args: Any) -> set[str]:
    """Skill-first sample of one recency-ordered pool, up to ``args.max_sessions``."""
    sampled: set[str] = set()
    counts = dict.fromkeys(skills, 0)
    for session in sessions:
        if len(sampled) >= args.max_sessions:
            break
        used = session["skills_used"]
        if any(counts.get(name, 0) < args.per_skill for name in used):
            sampled.add(session["_key"])
            # Count every skill the session used, so a multi-skill session fills each quota.
            for name in used:
                counts[name] = counts.get(name, 0) + 1
    no_skill = 0
    for session in sessions:
        if len(sampled) >= args.max_sessions or no_skill >= args.no_skill:
            break
        if not session["skills_used"] and session["_key"] not in sampled:
            sampled.add(session["_key"])
            no_skill += 1
    return sampled


def harness_quotas(pools: dict[str, int], cap: int) -> dict[str, int]:
    """Deal ``cap`` slots round-robin over harnesses ranked by pool size, then name."""
    order = sorted(pools, key=lambda harness: (-pools[harness], harness))
    quotas = dict.fromkeys(order, 0)
    remaining = max(cap, 0)
    progressed = True
    while remaining and progressed:
        progressed = False
        for harness in order:
            if remaining and quotas[harness] < pools[harness]:
                quotas[harness] += 1
                remaining -= 1
                progressed = True
    return quotas


def _omission_notice(cap: int, ranked: list[str], omitted: list[dict[str, Any]]) -> str | None:
    if not omitted:
        return None
    names = ", ".join(f"{item['harness']} ({item['scoreable']} scoreable)" for item in omitted)
    return (
        f"--max-sessions {cap} is lower than the {len(ranked)} harnesses with scoreable "
        f"sessions, so the sample omits: {names}. Raise the cap to cover every harness."
    )


def sample_sessions(
    sessions: Any, skills: Any, args: Any
) -> tuple[set[str], dict[str, dict[str, int]], dict[str, Any]]:
    """Sample per harness. Returns the sampled keys, per-harness counts, and a sampling block.

    ``sessions`` must already be in recency order; that order is kept inside each harness.
    """
    groups: dict[str, list[Any]] = {}
    for session in sessions:
        groups.setdefault(session["harness"], []).append(session)
    quotas = harness_quotas(
        {harness: len(group) for harness, group in groups.items()}, args.max_sessions
    )
    ranked = sorted(quotas, key=lambda harness: (-len(groups[harness]), harness))
    sampled: set[str] = set()
    per_harness: dict[str, dict[str, int]] = {}
    omitted: list[dict[str, Any]] = []
    for harness in ranked:
        group, quota = groups[harness], quotas[harness]
        picked = set()
        if quota:
            sub = SimpleNamespace(
                max_sessions=quota, per_skill=args.per_skill, no_skill=args.no_skill
            )
            picked = sample_one_harness(group, skills, sub)
        else:
            omitted.append({"harness": harness, "scoreable": len(group)})
        sampled |= picked
        per_harness[harness] = {
            "scoreable": len(group),
            "skill_candidates": sum(1 for session in group if session["skills_used"]),
            "quota": quota,
            "sampled": len(picked),
            "sampled_with_skills": sum(
                1 for session in group if session["_key"] in picked and session["skills_used"]
            ),
        }
    sampling = {
        "rule": SAMPLING_RULE,
        "within_harness": WITHIN_HARNESS_RULE,
        "max_sessions": args.max_sessions,
        "harness_coverage_complete": not omitted,
        "omitted_harnesses": omitted,
        "notice": _omission_notice(args.max_sessions, ranked, omitted),
    }
    return sampled, per_harness, sampling
