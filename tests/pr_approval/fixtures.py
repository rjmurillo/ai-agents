"""Synthetic evidence for the PR approval policy tests. No real PR data."""

from __future__ import annotations

import copy

from scripts.pr_approval.codeowners import parse_codeowners
from scripts.pr_approval.engine import evaluate, evidence_fingerprint
from scripts.pr_approval.policy import parse_policy
from scripts.pr_approval.registry import parse_registry
from scripts.pr_approval.snapshot import parse_snapshot

AUTHOR = 1001
APPROVER = 2002
BOT = 3003
HUMAN = 4004
AGENT = 5005
REPO = 77
HEAD = "a" * 40
CHECK_APP = 15368

POLICY_TOML = """
schema_version = 1
mode = "observe"

[budget]
max_rounds = 3
max_classifier_calls = 1
max_spend_usd = 0.02
deadline_seconds = 15

[[rules]]
id = "docs-prose-only"
mode = "observe"
effect = "allow"

[rules.all]
paths = ["docs/runbooks/*.md", "docs/design/**/*.md"]
author_class = "independent"
max_files = 5
max_changed_lines = 100
forbid_renames = true
forbid_binary = true
forbid_code_fences = true
"""

REGISTRY_TOML = f"""
schema_version = 1
approver_principals = [{{ id = {APPROVER}, login = "approver-app" }}]
agent_accounts = [{{ id = {AGENT} }}]
bot_accounts = [{{ id = {BOT}, login = "review-bot" }}]

[[independent_authors]]
id = {AUTHOR}
login = "independent-human"
"""

CODEOWNERS = "/.github/workflows/ @owner\n/scripts/validation/ @owner\n"


def golden() -> dict:
    """A snapshot that the test policy evaluates to WOULD_APPROVE."""
    return copy.deepcopy(
        {
            "repository": {"id": REPO, "default_branch": "main", "default_branch_sha": "b" * 40},
            "pull_request": {
                "number": 42,
                "state": "open",
                "draft": False,
                "head_sha": HEAD,
                "head_repository_id": REPO,
                "base_ref": "main",
                "base_sha": "c" * 40,
                "merge_base_sha": "d" * 40,
                "mergeable": "MERGEABLE",
                "author": {"id": AUTHOR, "login": "independent-human", "type": "User"},
            },
            "files": {
                "complete": True,
                "items": [
                    {
                        "path": "docs/design/external-signal-gating.md",
                        "status": "modified",
                        "additions": 6,
                        "deletions": 2,
                        "binary": False,
                        "patch_present": True,
                        "touches_code_fence": False,
                    }
                ],
            },
            "labels": {"complete": True, "items": [{"name": "documentation"}]},
            "reviews": {"complete": True, "items": []},
            "review_threads": {"complete": True, "unresolved": 0},
            "checks": {
                "required": {
                    "complete": True,
                    "items": [{"context": "Validate PR", "app_id": CHECK_APP}],
                },
                "results": {
                    "complete": True,
                    "items": [
                        {
                            "context": "Validate PR",
                            "app_id": CHECK_APP,
                            "conclusion": "success",
                            "head_sha": HEAD,
                        }
                    ],
                },
            },
            "stops": {"repository": False},
        }
    )


def run(
    raw: object,
    policy_toml: str = POLICY_TOML,
    registry_toml: str = REGISTRY_TOML,
    codeowners=CODEOWNERS,
):
    """Evaluate ``raw`` with parsed test inputs."""
    rules = parse_codeowners(codeowners) if codeowners is not None else None
    return evaluate(
        parse_snapshot(raw),
        parse_policy(policy_toml.encode()),
        parse_registry(registry_toml.encode()),
        rules,
        evidence_fingerprint(raw),
    )
