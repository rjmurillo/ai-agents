#!/usr/bin/env python3
"""Read the branch protection and ruleset rules applying to a branch.

Agents need this before they can explain a blocked merge, evaluate whether a
required check is missing, or confirm what a merge will enforce. Without it
they reach for raw ``gh api repos/.../protection`` and ``.../rules/branches``
calls. Read-only.

Two sources are combined, because GitHub enforces both:

- Classic branch protection: ``GET repos/{owner}/{repo}/branches/{branch}/protection``.
  A 404 means no classic protection, not no protection at all.
- Rulesets: ``GET repos/{owner}/{repo}/rules/branches/{branch}`` returns every
  rule the active rulesets apply to the branch, including organization
  rulesets when ``includes_parents`` style information is present. Required
  status checks can live here without any classic protection at all, which is
  why a script that reads only the classic endpoint misses required contexts.

Output is the normalized intersection an agent needs: required status check
contexts, required approving review count, whether stale reviews are
dismissed on push, code-owner review requirement, signature requirement,
admin enforcement, force-push and deletion permission, plus the raw rule
type list so an unrecognized rule is still visible.

Exit codes follow ADR-035. Reads only, so exit 1 cannot occur:
    0 - Protection state reported; an unprotected branch is a success answer
    2 - --branch is blank
    3 - The API read failed in a way that makes the verdict unknown, or the
        branch does not exist (Error.Type is NotFound for a missing branch)
    4 - Auth error
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from skill_bootstrap import ensure_plugin_paths

ensure_plugin_paths(__file__, (".claude", "lib"))

from github_core.api import (
    assert_gh_authenticated,
    gh_api_get,
    resolve_repo_params,
)
from github_core.output import (
    add_output_format_arg,
    get_output_format,
    write_skill_error,
    write_skill_output,
)

_SCRIPT_NAME = "get_branch_protection.py"


def _classic_required_contexts(protection: dict) -> list[str]:
    checks = protection.get("required_status_checks") or {}
    contexts = list(checks.get("contexts") or [])
    for entry in checks.get("checks") or []:
        if isinstance(entry, dict) and entry.get("context"):
            contexts.append(entry["context"])
    return sorted(set(contexts))


def _ruleset_required_contexts(rules: list[dict]) -> list[str]:
    contexts: list[str] = []
    for rule in rules:
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        for entry in params.get("required_status_checks") or []:
            if isinstance(entry, dict) and entry.get("context"):
                contexts.append(entry["context"])
    return sorted(set(contexts))


def normalize(protection: dict | None, rules: list[dict], branch: str) -> dict:
    """Combine classic protection and ruleset rules into one shape. Pure."""
    review_count = 0
    dismiss_stale = False
    code_owner = False
    if protection:
        reviews = protection.get("required_pull_request_reviews") or {}
        review_count = int(reviews.get("required_approving_review_count") or 0)
        dismiss_stale = bool(reviews.get("dismiss_stale_reviews"))
        code_owner = bool(reviews.get("require_code_owner_reviews"))

    rule_types: list[str] = []
    ruleset_review_count = 0
    ruleset_sources: dict[str, list[str]] = {}
    for rule in rules:
        rtype = str(rule.get("type") or "unknown")
        rule_types.append(rtype)
        source = rule.get("ruleset_source") or rule.get("source") or ""
        if source:
            ruleset_sources.setdefault(str(source), []).append(rtype)
        if rtype == "pull_request":
            params = rule.get("parameters") or {}
            ruleset_review_count = max(
                ruleset_review_count,
                int(params.get("required_approving_review_count") or 0),
            )
            dismiss_stale = dismiss_stale or bool(params.get("dismiss_stale_reviews_on_push"))
            code_owner = code_owner or bool(params.get("require_code_owner_review"))

    classic_contexts = _classic_required_contexts(protection) if protection else []
    ruleset_contexts = _ruleset_required_contexts(rules)

    return {
        "branch": branch,
        "protected": bool(protection) or bool(rules),
        "required_status_check_contexts": sorted(set(classic_contexts + ruleset_contexts)),
        "required_status_check_contexts_classic": classic_contexts,
        "required_status_check_contexts_ruleset": ruleset_contexts,
        "required_approving_review_count": max(review_count, ruleset_review_count),
        "dismiss_stale_reviews_on_push": dismiss_stale,
        "require_code_owner_reviews": code_owner,
        "required_signatures": bool(
            protection and (protection.get("required_signatures") or {}).get("enabled")
        )
        or "required_signatures" in rule_types,
        "enforce_admins": bool(
            protection and (protection.get("enforce_admins") or {}).get("enabled")
        ),
        # Ruleset blocks bind even when classic protection allows: a
        # non_fast_forward rule overrides a classic force-push allowance.
        "allows_force_pushes": bool(
            protection and (protection.get("allow_force_pushes") or {}).get("enabled")
        )
        and "non_fast_forward" not in rule_types,
        "allows_deletions": bool(
            protection and (protection.get("allow_deletions") or {}).get("enabled")
        )
        and "deletion" not in rule_types,
        "strict_required_status_checks": bool(
            protection and (protection.get("required_status_checks") or {}).get("strict")
        )
        or any(
            (rule.get("parameters") or {}).get("strict_required_status_checks_policy")
            for rule in rules
            if rule.get("type") == "required_status_checks"
        ),
        "rule_types": sorted(set(rule_types)),
        "ruleset_sources": ruleset_sources,
        "classic_protection_present": bool(protection),
    }


_HELP_EPILOG = """\
examples:
  %(prog)s --branch main
  %(prog)s --branch main --output-format human

exit codes:
  0  success
  2  usage or configuration error (blank --branch)
  3  external error (API failure, or the branch was not found; see Error.Type)
  4  auth error
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Read branch protection and ruleset rules for a branch.",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--branch", default="main", help="Branch name (default: main)")
    add_output_format_arg(p)
    return p


def quote_branch(branch: str) -> str:
    """Encode a branch name for use in a REST path segment.

    Slashed names (feature/foo) are legal git branches but a raw slash splits
    the path and the read hits the wrong resource or 404s, which this script
    would report as absent protection.
    """
    return urllib.parse.quote(branch, safe="")


def _branch_missing_reason(owner: str, repo: str, branch: str) -> str:
    """Return the exit-3 NotFound reason when the remote has no such branch, or empty."""
    branch_obj, branch_error = gh_api_get(f"repos/{owner}/{repo}/branches/{quote_branch(branch)}")
    if branch_obj is None and ("404" in branch_error or "Not Found" in branch_error):
        return f"Branch '{branch}' not found in {owner}/{repo}; a mistyped branch is not an unprotected one"
    return ""


def _branch_rejection(owner: str, repo: str, branch: str) -> tuple[str, int, str] | None:
    """Return (message, exit code, Error.Type) for an unusable --branch, or None.

    A blank value is a usage error (2). A branch the remote lacks is exit 3
    NotFound (ADR-035), so a typo never reads as an unprotected branch.
    """
    if not branch.strip():
        return "--branch must not be blank", 2, "InvalidParams"
    if missing_reason := _branch_missing_reason(owner, repo, branch):
        return missing_reason, 3, "NotFound"
    return None


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fmt = get_output_format(args.output_format)

    assert_gh_authenticated(rest_only=True)
    resolved = resolve_repo_params(args.owner, args.repo)
    owner, repo = resolved.owner, resolved.repo

    if rejection := _branch_rejection(owner, repo, args.branch):
        message, code, error_type = rejection
        write_skill_error(
            message, code, error_type=error_type, output_format=fmt, script_name=_SCRIPT_NAME
        )
        return code

    protection, protection_error = gh_api_get(
        f"repos/{owner}/{repo}/branches/{quote_branch(args.branch)}/protection"
    )
    protection_missing = False
    if protection is None:
        # A 404 means no classic protection. Anything else is a transport or
        # permission failure, which makes the verdict unknown rather than empty.
        if "404" in protection_error or "Not Found" in protection_error:
            protection_missing = True
            protection = {}
        else:
            write_skill_error(
                f"Branch protection read failed: {protection_error}",
                3,
                error_type="ApiError",
                output_format=fmt,
                script_name=_SCRIPT_NAME,
            )
            return 3

    rules, rules_error = gh_api_get(
        f"repos/{owner}/{repo}/rules/branches/{quote_branch(args.branch)}?per_page=100"
    )
    ruleset_read = True
    if rules is None:
        if "404" in rules_error or "Not Found" in rules_error:
            rules = []
        elif "403" in rules_error or "Forbidden" in rules_error:
            # Ruleset reads need higher scope on some repos. Report what we
            # have and say the ruleset half was not read.
            rules = []
            ruleset_read = False
        else:
            write_skill_error(
                f"Branch rules read failed: {rules_error}",
                3,
                error_type="ApiError",
                output_format=fmt,
                script_name=_SCRIPT_NAME,
            )
            return 3
    if not isinstance(rules, list):
        rules = []

    data = normalize(protection or {}, rules, args.branch)
    if protection_missing:
        data["classic_protection_present"] = False
    data["ruleset_rules_read"] = ruleset_read
    data["ruleset_scan_capped"] = isinstance(rules, list) and len(rules) >= 100
    if not ruleset_read:
        data["coverage_warning"] = (
            "ruleset rules were not read (403); required contexts and review "
            "counts from rulesets are invisible in this output"
        )

    contexts = len(data["required_status_check_contexts"])
    write_skill_output(
        data,
        output_format=fmt,
        human_summary=(
            f"{args.branch}: protected={data['protected']}, "
            f"{contexts} required check context(s), "
            f"{data['required_approving_review_count']} required approval(s)"
        ),
        status="PASS",
        script_name=_SCRIPT_NAME,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
