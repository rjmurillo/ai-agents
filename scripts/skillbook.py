#!/usr/bin/env python3
"""Skillbook CLI: evidence-tiered agent policy registry.

Manages .agents/skillbook/policies.json, tensions.json, and workflows.json.
Policies carry an evidence tier (hypothesis -> observed -> validated) that is
grounded in eval pass/fail outcomes rather than regex-detected sentiment.

Core invariants (see .agents/skillbook/README.md):
  - Tiers NEVER decrease. A validated policy whose contradict rate rises does
    not demote; it flips status to 'questioning' (still active, surfaced as
    "re-examine before relying").
  - confirms / contradicts / application_count are a DERIVED projection of the
    evidence array. The evidence array is the system of record; the counts are
    recomputed on every mutation.
  - Evidence is weighted by provenance: external = 1.0, self-referential = 0.25.

Commands:
  status                              List policies with tier/confirms/contradicts.
  confirm <policy-id> --eval <id>     Log an eval-grounded confirmation.
  contradict <policy-id> --eval <id>  Log an eval-grounded contradiction.
  promote                             Re-evaluate tiers and statuses.
  tension list                        Show detected tensions.
  tension prefer <ten> <ctx> <pol>    Record a per-context tension resolution.
  select <agent> <context>            Active policies for an agent in a context.

EXIT CODES (ADR-035):
  0  - Success
  1  - Logic error (policy/tension not found, invalid argument)
  2  - Config error (skillbook file missing or unreadable)

See: ADR-035 Exit Code Standardization.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

SCHEMA_VERSION = 1

# Evidence provenance weights. External signals (eval pass/fail, incidents,
# critic verdicts) are ground truth; a self-referential claim is an agent
# grading its own homework and is discounted accordingly.
CONTEXT_WEIGHTS: dict[str, float] = {"external": 1.0, "self-referential": 0.25}

TIER_RANK: dict[str, int] = {"hypothesis": 0, "observed": 1, "validated": 2}
RANK_TIER: dict[int, str] = {rank: tier for tier, rank in TIER_RANK.items()}

# Promotion gates. See README "Tier semantics".
OBSERVED_MIN_CONFIRMS = 1.0
VALIDATED_MIN_CONFIRMS = 5.0
VALIDATED_MAX_CONTRADICT_RATE = 0.10


# --------------------------------------------------------------------------
# Paths and I/O
# --------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the repository root (the parent of this script's directory)."""
    return Path(__file__).resolve().parent.parent


def skillbook_paths(base_dir: Path) -> dict[str, Path]:
    """Map skillbook file names to their paths under base_dir."""
    return {
        "policies": base_dir / "policies.json",
        "tensions": base_dir / "tensions.json",
        "workflows": base_dir / "workflows.json",
    }


def load_skillbook_file(path: Path) -> dict[str, Any]:
    """Load and parse a skillbook JSON file.

    Raises FileNotFoundError if missing and ValueError if the JSON is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"skillbook file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc


def save_skillbook_file(path: Path, data: dict[str, Any]) -> None:
    """Write a skillbook JSON file with stable formatting (2-space, trailing newline)."""
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Evidence math (pure functions; the system of record is the evidence array)
# --------------------------------------------------------------------------


def evidence_weight(entry: dict[str, Any]) -> float:
    """Return the weight of one evidence entry based on its context_type."""
    return CONTEXT_WEIGHTS.get(entry.get("context_type", "external"), 1.0)


def recompute_counts(policy: dict[str, Any]) -> None:
    """Recompute confirms / contradicts / application_count / last_tested_at.

    These fields are a derived projection of the evidence array. This is the
    single place they are written.
    """
    evidence = policy.get("evidence", [])
    confirms = 0.0
    contradicts = 0.0
    last_ts = 0
    for entry in evidence:
        weight = evidence_weight(entry)
        if entry.get("type") == "confirmed":
            confirms += weight
        elif entry.get("type") == "contradicted":
            contradicts += weight
        last_ts = max(last_ts, int(entry.get("ts", 0)))
    policy["confirms"] = round(confirms, 4)
    policy["contradicts"] = round(contradicts, 4)
    policy["application_count"] = len(evidence)
    if last_ts:
        policy["last_tested_at"] = last_ts


def contradict_rate(policy: dict[str, Any]) -> float:
    """Return the weighted contradict rate: contradicts / (confirms + contradicts)."""
    confirms = float(policy.get("confirms", 0.0))
    contradicts = float(policy.get("contradicts", 0.0))
    total = confirms + contradicts
    if total == 0:
        return 0.0
    return contradicts / total


def eligible_tier(policy: dict[str, Any]) -> str:
    """Return the tier the policy's evidence currently qualifies it for.

    This is the *eligible* tier, ignoring the never-decrease rule. promote()
    combines it with the current tier so a policy can only ever rise.
    """
    confirms = float(policy.get("confirms", 0.0))
    rate = contradict_rate(policy)
    if confirms >= VALIDATED_MIN_CONFIRMS and rate <= VALIDATED_MAX_CONTRADICT_RATE:
        return "validated"
    # Any confirmed evidence makes the contradict rate strictly below 100%,
    # so the issue's "<100% contradict rate" gate for 'observed' is implied.
    if confirms >= OBSERVED_MIN_CONFIRMS:
        return "observed"
    return "hypothesis"


def resolve_status(policy: dict[str, Any], tier: str) -> str:
    """Return the status for a policy at the given tier.

    A retired policy stays retired. A validated policy whose contradict rate
    exceeds the validated gate is 'questioning'; otherwise 'active'.
    """
    if policy.get("status") == "retired":
        return "retired"
    if tier == "validated" and contradict_rate(policy) > VALIDATED_MAX_CONTRADICT_RATE:
        return "questioning"
    return "active"


def promote_policy(policy: dict[str, Any]) -> bool:
    """Re-evaluate one policy's tier and status. Return True if anything changed.

    Enforces the never-decrease invariant: the new tier is the higher of the
    current tier and the eligible tier.
    """
    old_tier = policy.get("tier", "hypothesis")
    old_status = policy.get("status", "active")

    old_rank = TIER_RANK.get(old_tier, 0)
    new_rank = max(old_rank, TIER_RANK[eligible_tier(policy)])
    # Invariant: tiers never decrease.
    assert new_rank >= old_rank, f"tier decrease blocked for {policy.get('id')}"
    new_tier = RANK_TIER[new_rank]
    new_status = resolve_status(policy, new_tier)

    if new_tier == old_tier and new_status == old_status:
        return False
    policy["tier"] = new_tier
    policy["status"] = new_status
    return True


def add_evidence(policy: dict[str, Any], entry: dict[str, Any]) -> bool:
    """Append an evidence entry to a policy. Return True if it was added.

    Idempotent on eval_id: a second entry with an eval_id already present on
    the policy is a no-op, so re-running the post-eval hook cannot double-count.
    Recomputes derived counts and bumps the version when an entry is added.
    """
    eval_id = entry.get("eval_id")
    for existing in policy.get("evidence", []):
        if existing.get("eval_id") == eval_id:
            return False
    policy.setdefault("evidence", []).append(entry)
    recompute_counts(policy)
    policy["version"] = int(policy.get("version", 1)) + 1
    return True


def make_evidence_entry(
    *,
    evidence_type: str,
    eval_id: str,
    context_type: str,
    ts: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build an evidence entry. 'pass' is derived from the evidence type."""
    entry: dict[str, Any] = {
        "ts": ts,
        "type": evidence_type,
        "eval_id": eval_id,
        "pass": evidence_type == "confirmed",
        "context_type": context_type,
    }
    if reason:
        entry["reason"] = reason
    return entry


# --------------------------------------------------------------------------
# Registry-level operations
# --------------------------------------------------------------------------


def find_policy(data: dict[str, Any], policy_id: str) -> dict[str, Any] | None:
    """Return the policy with the given id, or None."""
    for policy in data.get("policies", []):
        if policy.get("id") == policy_id:
            return policy
    return None


def run_promote(data: dict[str, Any], now: int) -> list[str]:
    """Promote every policy in the registry. Return ids of policies that changed.

    Bumps meta.promotion_count and meta.last_promotion_at only when at least
    one policy changed, keeping a no-op promote idempotent.
    """
    changed: list[str] = []
    for policy in data.get("policies", []):
        if promote_policy(policy):
            changed.append(str(policy.get("id")))
    if changed:
        meta = data.setdefault("meta", {})
        meta["promotion_count"] = int(meta.get("promotion_count", 0)) + 1
        meta["last_promotion_at"] = now
    return changed


def find_tension(data: dict[str, Any], tension_id: str) -> dict[str, Any] | None:
    """Return the tension with the given id, or None."""
    for tension in data.get("tensions", []):
        if tension.get("id") == tension_id:
            return tension
    return None


def tension_prefer(
    tension: dict[str, Any], context: str, policy_id: str, eval_id: str
) -> bool:
    """Record a per-context resolution for a tension. Return True if it changed.

    Idempotent on eval_id within the context. policy_id must be one of the two
    policies the tension pairs; the caller validates that.
    """
    contexts = tension.setdefault("preferred_in_context", {})
    resolution = contexts.get(context)
    if resolution is None:
        resolution = {"preferred": policy_id, "confirmed_count": 0, "evidence": []}
        contexts[context] = resolution
    if eval_id in resolution["evidence"]:
        # Already recorded; only the preferred pointer may need updating.
        changed = resolution["preferred"] != policy_id
        resolution["preferred"] = policy_id
        return changed
    resolution["preferred"] = policy_id
    resolution["evidence"].append(eval_id)
    resolution["confirmed_count"] = int(resolution.get("confirmed_count", 0)) + 1
    return True


def select_policies(
    data: dict[str, Any],
    tensions_data: dict[str, Any],
    agent: str,
    context: str,
) -> list[dict[str, Any]]:
    """Return active policies for an agent in a context, with tension resolution.

    Includes the agent's own policies plus shared cross-cutting policies.
    Retired policies are hidden. Each result is annotated with whether it wins
    or yields under any tension that applies in the given context. Ordering:
    active policies first, questioning policies after (surfaced, not hidden).
    """
    selected = [
        policy
        for policy in data.get("policies", [])
        if policy.get("owner_agent") in (agent, "shared")
        and policy.get("status") != "retired"
    ]
    selected_ids = {policy["id"] for policy in selected}

    results: list[dict[str, Any]] = []
    for policy in selected:
        annotation = _tension_annotation(
            policy["id"], selected_ids, tensions_data, context
        )
        results.append(
            {
                "id": policy["id"],
                "name": policy.get("name", ""),
                "owner_agent": policy.get("owner_agent", ""),
                "tier": policy.get("tier", "hypothesis"),
                "status": policy.get("status", "active"),
                "tension": annotation,
            }
        )
    # Active first, questioning surfaced after. Stable within each group.
    results.sort(key=lambda r: 0 if r["status"] == "active" else 1)
    return results


def _tension_annotation(
    policy_id: str,
    selected_ids: set[str],
    tensions_data: dict[str, Any],
    context: str,
) -> dict[str, Any] | None:
    """Return how a policy fares under any tension that applies in this context."""
    for tension in tensions_data.get("tensions", []):
        pair = {tension.get("policy_a"), tension.get("policy_b")}
        if policy_id not in pair:
            continue
        other = (pair - {policy_id}).pop()
        resolution = tension.get("preferred_in_context", {}).get(context)
        if resolution is None:
            verdict = "unresolved"
        elif resolution.get("preferred") == policy_id:
            verdict = "wins"
        else:
            verdict = "yields"
        return {
            "tension_id": tension.get("id"),
            "with_policy": other,
            "verdict": verdict,
        }
    return None


# --------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------


def _load_or_exit(path: Path) -> dict[str, Any]:
    """Load a skillbook file, printing a diagnostic and exiting on failure."""
    try:
        return load_skillbook_file(path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG) from exc
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_LOGIC) from exc


def cmd_status(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """List all policies with tier, status, and evidence counts."""
    data = _load_or_exit(paths["policies"])
    policies = data.get("policies", [])
    if args.json:
        print(json.dumps(policies, indent=2))
        return EXIT_OK
    if not policies:
        print("No policies registered.")
        return EXIT_OK
    print(f"{'POLICY':<36} {'TIER':<11} {'STATUS':<12} {'CONF':>6} {'CONTRA':>7}")
    for policy in policies:
        print(
            f"{policy.get('id', ''):<36} "
            f"{policy.get('tier', ''):<11} "
            f"{policy.get('status', ''):<12} "
            f"{float(policy.get('confirms', 0)):>6.2f} "
            f"{float(policy.get('contradicts', 0)):>7.2f}"
        )
    return EXIT_OK


def _log_evidence(
    args: argparse.Namespace,
    paths: dict[str, Path],
    evidence_type: str,
) -> int:
    """Shared handler for confirm and contradict."""
    data = _load_or_exit(paths["policies"])
    policy = find_policy(data, args.policy_id)
    if policy is None:
        print(f"Error: policy not found: {args.policy_id}", file=sys.stderr)
        return EXIT_LOGIC
    entry = make_evidence_entry(
        evidence_type=evidence_type,
        eval_id=args.eval,
        context_type=args.context_type,
        ts=int(time.time()),
        reason=getattr(args, "reason", None),
    )
    if add_evidence(policy, entry):
        save_skillbook_file(paths["policies"], data)
        print(
            f"{evidence_type}: {args.policy_id} "
            f"(confirms={policy['confirms']}, contradicts={policy['contradicts']}, "
            f"tier={policy['tier']} -- run 'promote' to re-evaluate)"
        )
    else:
        print(f"No-op: eval {args.eval!r} already recorded for {args.policy_id}.")
    return EXIT_OK


def cmd_confirm(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Log an eval-grounded confirmation for a policy."""
    return _log_evidence(args, paths, "confirmed")


def cmd_contradict(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Log an eval-grounded contradiction for a policy."""
    return _log_evidence(args, paths, "contradicted")


def cmd_promote(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Re-evaluate every policy's tier and status."""
    data = _load_or_exit(paths["policies"])
    changed = run_promote(data, int(time.time()))
    if changed:
        save_skillbook_file(paths["policies"], data)
        print(f"Promoted/updated {len(changed)} policy(ies):")
        for policy_id in changed:
            policy = find_policy(data, policy_id)
            assert policy is not None
            print(f"  {policy_id} -> tier={policy['tier']}, status={policy['status']}")
    else:
        print("No policy tier or status changed.")
    return EXIT_OK


def cmd_tension(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Dispatch the tension subcommands (list, prefer)."""
    if args.tension_command == "list":
        return _cmd_tension_list(args, paths)
    return _cmd_tension_prefer(args, paths)


def _cmd_tension_list(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Show all detected tensions and their per-context resolutions."""
    data = _load_or_exit(paths["tensions"])
    tensions = data.get("tensions", [])
    if args.json:
        print(json.dumps(tensions, indent=2))
        return EXIT_OK
    if not tensions:
        print("No tensions recorded.")
        return EXIT_OK
    for tension in tensions:
        print(
            f"{tension['id']} [{tension.get('status', '')}]: "
            f"{tension['policy_a']} vs {tension['policy_b']}"
        )
        for context, resolution in tension.get("preferred_in_context", {}).items():
            print(
                f"  {context}: prefer {resolution['preferred']} "
                f"(confirmed {resolution.get('confirmed_count', 0)}x)"
            )
    return EXIT_OK


def _cmd_tension_prefer(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Record a per-context resolution for a tension."""
    data = _load_or_exit(paths["tensions"])
    tension = find_tension(data, args.tension_id)
    if tension is None:
        print(f"Error: tension not found: {args.tension_id}", file=sys.stderr)
        return EXIT_LOGIC
    pair = {tension.get("policy_a"), tension.get("policy_b")}
    if args.policy_id not in pair:
        print(
            f"Error: {args.policy_id} is not part of tension {args.tension_id} "
            f"({tension['policy_a']} vs {tension['policy_b']})",
            file=sys.stderr,
        )
        return EXIT_LOGIC
    if tension_prefer(tension, args.context, args.policy_id, args.eval):
        save_skillbook_file(paths["tensions"], data)
        print(
            f"tension {args.tension_id}: in context {args.context!r} "
            f"prefer {args.policy_id}"
        )
    else:
        print(f"No-op: eval {args.eval!r} already recorded for that context.")
    return EXIT_OK


def cmd_select(args: argparse.Namespace, paths: dict[str, Path]) -> int:
    """Return active policies for an agent in a context, with tension resolution."""
    policies_data = _load_or_exit(paths["policies"])
    try:
        tensions_data = load_skillbook_file(paths["tensions"])
    except (FileNotFoundError, ValueError):
        # Tensions are optional for select; an absent table just means no resolution.
        tensions_data = {"schema_version": SCHEMA_VERSION, "tensions": []}
    results = select_policies(policies_data, tensions_data, args.agent, args.context)
    if args.json:
        print(json.dumps(results, indent=2))
        return EXIT_OK
    if not results:
        print(f"No active policies for agent {args.agent!r}.")
        return EXIT_OK
    print(f"Active policies for {args.agent!r} in context {args.context!r}:")
    for result in results:
        marker = "  " if result["status"] == "active" else "? "
        line = (
            f"{marker}{result['id']} [{result['tier']}/{result['status']}] "
            f"{result['name']}"
        )
        print(line)
        tension = result["tension"]
        if tension and tension["verdict"] != "unresolved":
            print(
                f"      tension {tension['tension_id']}: {tension['verdict']} "
                f"vs {tension['with_policy']}"
            )
        elif tension:
            print(
                f"      tension {tension['tension_id']}: unresolved for this "
                f"context vs {tension['with_policy']}"
            )
    return EXIT_OK


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the skillbook CLI."""
    parser = argparse.ArgumentParser(
        prog="skillbook",
        description="Evidence-tiered agent policy registry.",
    )
    parser.add_argument(
        "--skillbook-dir",
        type=Path,
        default=repo_root() / ".agents" / "skillbook",
        help="Directory holding policies.json/tensions.json/workflows.json.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="List policies with tier and counts.")
    status.add_argument("--json", action="store_true", help="Emit JSON.")

    confirm = sub.add_parser("confirm", help="Log an eval-grounded confirmation.")
    contradict = sub.add_parser(
        "contradict", help="Log an eval-grounded contradiction."
    )
    for evidence_parser in (confirm, contradict):
        evidence_parser.add_argument("policy_id", help="Policy id (pol-*).")
        evidence_parser.add_argument(
            "--eval", required=True, help="Eval run/fixture identifier."
        )
        evidence_parser.add_argument(
            "--context-type",
            choices=sorted(CONTEXT_WEIGHTS),
            default="external",
            help="Evidence provenance (default: external).",
        )
    contradict.add_argument("--reason", help="Why the policy was contradicted.")

    sub.add_parser("promote", help="Re-evaluate tiers and statuses.")

    tension = sub.add_parser("tension", help="Inspect or resolve tensions.")
    tension_sub = tension.add_subparsers(dest="tension_command", required=True)
    tension_list = tension_sub.add_parser("list", help="Show all tensions.")
    tension_list.add_argument("--json", action="store_true", help="Emit JSON.")
    tension_prefer_p = tension_sub.add_parser(
        "prefer", help="Record a per-context resolution."
    )
    tension_prefer_p.add_argument("tension_id", help="Tension id (ten-*).")
    tension_prefer_p.add_argument("context", help="Context name.")
    tension_prefer_p.add_argument("policy_id", help="Preferred policy id (pol-*).")
    tension_prefer_p.add_argument(
        "--eval", required=True, help="Eval run identifier supporting the resolution."
    )

    select = sub.add_parser("select", help="Active policies for an agent.")
    select.add_argument("agent", help="Agent persona name.")
    select.add_argument("context", help="Decision context name.")
    select.add_argument("--json", action="store_true", help="Emit JSON.")

    return parser


_COMMANDS = {
    "status": cmd_status,
    "confirm": cmd_confirm,
    "contradict": cmd_contradict,
    "promote": cmd_promote,
    "tension": cmd_tension,
    "select": cmd_select,
}


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch to the requested command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    paths = skillbook_paths(args.skillbook_dir)
    handler = _COMMANDS[args.command]
    try:
        return handler(args, paths)
    except SystemExit as exc:  # raised by _load_or_exit
        return int(exc.code or EXIT_OK)


if __name__ == "__main__":
    sys.exit(main())
