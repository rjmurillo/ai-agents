"""Choose which scoreable sessions to sample, balanced across harnesses.

python3, stdlib only. Local change to the Warp fork (issue #7187): the
upstream sampler had no harness dimension, so one harness could take the whole
cap. See docs/skill-doctor-upstream-sync.md in the source repository.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from session_common import THREAD_SUBAGENT, THREAD_TOP_LEVEL

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

TOP_LEVEL_RULE = (
    "When --top-level-quota is above 0, top-level sessions are sampled first into up to that "
    "many of the --max-sessions slots, by the rules above. Open reserved slots then take the "
    "remaining top-level sessions, newest first, past the --per-skill and --no-skill caps. "
    "Subagent sessions fill every slot the top-level sessions leave open, and slots the "
    "subagent sessions cannot fill return to top-level sessions that the rules above select "
    "at the larger cap. Both session types count against the same per-harness --per-skill "
    "and --no-skill caps, so only the reserved backfill passes them. "
    "--top-level-quota 0 samples both session types as one pool."
)

SKILL_FIRST = "skill_first"
TIMELINE_SUPPLEMENT = "timeline_supplement"

TIMELINE_RULE = (
    "Opt-in (--timeline-supplement N). After the quotas above, up to N more sessions that "
    "used no detected skill and were not already sampled are added, across all harnesses. "
    "Candidates are ordered oldest first (ties by session key) and N ranks are taken at "
    "evenly spaced positions from the oldest to the newest candidate. The additions go "
    "beyond --max-sessions."
)

NON_PROBABILITY_NOTE = (
    "Not a probability sample. Selection is skill-first plus a rank-spaced supplement, so "
    "grades describe the selected sessions only and do not estimate the whole population."
)


@dataclass
class HarnessUsage:
    """Per-skill and no-skill sessions a harness already holds from an earlier pass."""

    skills: dict[str, int] = field(default_factory=dict)
    no_skill: int = 0


def sample_one_harness(
    sessions: Any, skills: Any, args: Any, seed: HarnessUsage | None = None
) -> set[str]:
    """Skill-first sample of one recency-ordered pool, up to ``args.max_sessions``.

    ``seed`` carries sessions the harness already holds, so the caps bind across passes.
    """
    sampled: set[str] = set()
    counts = dict.fromkeys(skills, 0)
    if seed:
        counts.update(seed.skills)
    for session in sessions:
        if len(sampled) >= args.max_sessions:
            break
        used = session["skills_used"]
        if any(counts.get(name, 0) < args.per_skill for name in used):
            sampled.add(session["_key"])
            # Count every skill the session used, so a multi-skill session fills each quota.
            for name in used:
                counts[name] = counts.get(name, 0) + 1
    no_skill = seed.no_skill if seed else 0
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


def _omission_notice(
    cap: int, ranked: list[str], omitted: list[dict[str, Any]], block: dict[str, Any]
) -> str | None:
    if not omitted:
        return None
    names = ", ".join(f"{item['harness']} ({item['scoreable']} scoreable)" for item in omitted)
    if block and cap >= len(ranked):
        # The cap alone would fit every harness, so the top-level reservation took the slots.
        return (
            f"--top-level-quota {block['top_level_quota']} reserved {block['top_level_reserved']} "
            f"of the --max-sessions {cap} slots and top-level sessions took "
            f"{block['top_level_sampled']}, leaving none for: {names}. Lower "
            "--top-level-quota or raise --max-sessions to cover every harness."
        )
    return (
        f"--max-sessions {cap} is lower than the {len(ranked)} harnesses with scoreable "
        f"sessions, so the sample omits: {names}. Raise the cap to cover every harness."
    )


def _skill_first_by_harness(
    sessions: Any,
    skills: Any,
    args: Any,
    cap: int,
    seed: dict[str, HarnessUsage] | None = None,
) -> tuple[set[str], dict[str, dict[str, int]]]:
    """Deal ``cap`` slots across harnesses, then sample each harness skill-first.

    ``seed`` holds each harness's sessions from an earlier pass, so the caps bind across passes.
    """
    groups: dict[str, list[Any]] = {}
    for session in sessions:
        groups.setdefault(session["harness"], []).append(session)
    quotas = harness_quotas({harness: len(group) for harness, group in groups.items()}, cap)
    sampled: set[str] = set()
    per_harness: dict[str, dict[str, int]] = {}
    for harness, group in groups.items():
        quota = quotas[harness]
        picked: set[str] = set()
        if quota:
            sub = SimpleNamespace(
                max_sessions=quota, per_skill=args.per_skill, no_skill=args.no_skill
            )
            picked = sample_one_harness(group, skills, sub, (seed or {}).get(harness))
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
    return sampled, per_harness


def _usage_by_harness(sessions: Any, keys: set[str]) -> dict[str, HarnessUsage]:
    """Count the sessions in ``keys`` against each harness's per-skill and no-skill caps."""
    usage: dict[str, HarnessUsage] = {}
    for session in sessions:
        if session["_key"] not in keys:
            continue
        held = usage.setdefault(session["harness"], HarnessUsage())
        for name in session["skills_used"]:
            held.skills[name] = held.skills.get(name, 0) + 1
        if not session["skills_used"]:
            held.no_skill += 1
    return usage


def _is_top_level(session: Any) -> bool:
    return session.get("thread", THREAD_TOP_LEVEL) != THREAD_SUBAGENT


def _merge_harness_counts(
    target: dict[str, dict[str, int]], extra: dict[str, dict[str, int]]
) -> None:
    for harness, counts in extra.items():
        entry = target.setdefault(harness, dict.fromkeys(counts, 0))
        for name, value in counts.items():
            entry[name] = entry.get(name, 0) + value


def _backfill(
    pool: Any,
    picked: set[str],
    per_harness: dict[str, dict[str, int]],
    limit: int,
    allowed: set[str] | None = None,
) -> None:
    """Add unsampled sessions from ``pool``, newest first, until ``picked`` holds ``limit``.

    When ``allowed`` is given, only sessions whose key it holds are added.
    """
    for session in pool:
        if len(picked) >= limit:
            break
        if allowed is not None and session["_key"] not in allowed:
            continue
        if session["_key"] not in picked:
            picked.add(session["_key"])
            entry = per_harness[session["harness"]]
            entry["sampled"] += 1
            entry["quota"] = max(entry["quota"], entry["sampled"])
            entry["sampled_with_skills"] += bool(session["skills_used"])


def _reserve_top_level(
    sessions: Any, skills: Any, args: Any, reserve: int
) -> tuple[set[str], dict[str, dict[str, int]], dict[str, Any]]:
    """Fill up to ``reserve`` slots with top-level sessions, then give the rest to subagents."""
    top = [session for session in sessions if _is_top_level(session)]
    children = [session for session in sessions if not _is_top_level(session)]
    reserved = min(reserve, max(args.max_sessions, 0))
    top_keys, per_harness = _skill_first_by_harness(top, skills, args, reserved)
    _backfill(top, top_keys, per_harness, reserved)
    child_cap = max(args.max_sessions - len(top_keys), 0)
    # Both passes count against the same per-harness caps. Only the reserved backfill may pass them.
    child_keys, child_counts = _skill_first_by_harness(
        children, skills, args, child_cap, _usage_by_harness(top, top_keys)
    )
    _merge_harness_counts(per_harness, child_counts)
    # Slots the subagent sessions left open return to top-level sessions, but only to
    # ones a skill-first pass at the larger cap would pick, so the caps still bind.
    top_cap = max(args.max_sessions - len(child_keys), 0)
    if top_cap > len(top_keys):
        wider, _ = _skill_first_by_harness(
            top, skills, args, top_cap, _usage_by_harness(children, child_keys)
        )
        _backfill(top, top_keys, per_harness, top_cap, allowed=wider)
    block = {
        "top_level_rule": TOP_LEVEL_RULE,
        "top_level_quota": reserve,
        "top_level_reserved": reserved,
        "top_level_sampled": len(top_keys),
        "subagent_slots": child_cap,
    }
    return top_keys | child_keys, per_harness, block


def sample_sessions(
    sessions: Any, skills: Any, args: Any
) -> tuple[set[str], dict[str, dict[str, int]], dict[str, Any]]:
    """Sample per harness. Returns the sampled keys, per-harness counts, and a sampling block.

    ``sessions`` must already be in recency order; that order is kept inside each harness.
    A positive ``args.top_level_quota`` reserves that many slots for top-level sessions.
    """
    reserve = max(int(getattr(args, "top_level_quota", 0) or 0), 0)
    if reserve:
        sampled, per_harness, block = _reserve_top_level(sessions, skills, args, reserve)
    else:
        sampled, per_harness = _skill_first_by_harness(sessions, skills, args, args.max_sessions)
        block = {}
    ranked = sorted(per_harness, key=lambda harness: (-per_harness[harness]["scoreable"], harness))
    per_harness = {harness: per_harness[harness] for harness in ranked}
    omitted = [
        {"harness": harness, "scoreable": per_harness[harness]["scoreable"]}
        for harness in ranked
        if not per_harness[harness]["quota"]
    ]
    skill_first = set(sampled)
    sampling = {
        "rule": SAMPLING_RULE,
        "within_harness": WITHIN_HARNESS_RULE,
        "max_sessions": args.max_sessions,
        **block,
        "harness_coverage_complete": not omitted,
        "omitted_harnesses": omitted,
        "notice": _omission_notice(args.max_sessions, ranked, omitted, block),
    }
    requested = getattr(args, "timeline_supplement", 0) or 0
    if requested > 0:
        supplement = timeline_supplement(sessions, skill_first, requested)
        sampled = skill_first | set(supplement)
        _count_supplement(sessions, per_harness, supplement)
        sampling.update(stratum_metadata(sessions, skill_first, supplement, requested))
        if "top_level_rule" in block:
            strata = sampling["strata"][SKILL_FIRST]
            strata["rule"] = f"{strata['rule']} {block['top_level_rule']}"
    return sampled, per_harness, sampling


def _count_supplement(
    sessions: Any, per_harness: dict[str, dict[str, int]], supplement: list[str]
) -> None:
    added = set(supplement)
    for harness, entry in per_harness.items():
        extra = sum(1 for s in sessions if s["harness"] == harness and s["_key"] in added)
        entry["supplemented"] = extra
        entry["sampled"] += extra


def evenly_spaced(items: list[Any], count: int) -> list[Any]:
    """Pick ``count`` items at evenly spaced ranks, always including both ends when count > 1."""
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    if count == 1:
        return [items[(len(items) - 1) // 2]]
    last = len(items) - 1
    return [items[index * last // (count - 1)] for index in range(count)]


def timeline_supplement(sessions: Any, sampled: set[str], count: int) -> list[str]:
    """Keys of up to ``count`` unsampled no-skill sessions spaced evenly over time."""
    pool = sorted(
        (s for s in sessions if not s["skills_used"] and s["_key"] not in sampled),
        key=lambda s: (s.get("modified_at", ""), s["_key"]),
    )
    return [s["_key"] for s in evenly_spaced(pool, count)]


def stratum_metadata(
    sessions: Any, skill_first: set[str], supplement: list[str], requested: int
) -> dict[str, Any]:
    """Sampling-block additions recorded only when timeline supplementation is requested."""
    pool = sum(1 for s in sessions if not s["skills_used"] and s["_key"] not in skill_first)
    return {
        "representative": False,
        "non_probability_note": NON_PROBABILITY_NOTE,
        "timeline_supplement": {
            "requested": requested,
            "added": len(supplement),
            "rule": TIMELINE_RULE,
        },
        "strata": {
            SKILL_FIRST: {
                "candidates": len(sessions),
                "selected": len(skill_first),
                "rule": f"{SAMPLING_RULE} {WITHIN_HARNESS_RULE}",
            },
            TIMELINE_SUPPLEMENT: {
                "candidates": pool,
                "selected": len(supplement),
                "rule": TIMELINE_RULE,
            },
        },
        "stratum_members": {
            SKILL_FIRST: sorted(skill_first),
            TIMELINE_SUPPLEMENT: sorted(supplement),
        },
    }


def apply_strata(sessions: Any, sampling: dict[str, Any]) -> None:
    """Tag sampled sessions with their stratum. No-op unless the sampling block has strata."""
    members = sampling.get("stratum_members")
    if not members:
        return
    stratum_of = {key: name for name, keys in members.items() for key in keys}
    for session in sessions:
        stratum = stratum_of.get(session["_key"])
        if stratum:
            session["stratum"] = stratum
