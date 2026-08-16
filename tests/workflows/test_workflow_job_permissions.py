"""A job with no ``permissions:`` block silently inherits the workflow-level one.

38 jobs hold a write scope they never asked for. A ``debounce`` job that only
computes an output carries ``pull-requests: write``; ``claude.yml``'s
authorization check carries seven write scopes including ``id-token``. Nothing
in the job body says so, so a reviewer reading the job cannot see it (CWE-269).

``scripts/validate_workflows.py`` ``validate_permissions`` does not close this.
It errors only when a workflow declares permissions nowhere; one top-level block
satisfies it and per-job least privilege is never checked. Every job in this
repository therefore resolves a permission set, which is why a workflow with no
top-level block contributes no offenders here: its jobs each carry their own.

The ADR-006 run-block extraction campaign (#2967, 93 blocks left) is what makes
this worth a gate now. Extraction converts "inline bash, no checkout" into
"check out the repo and run a script from it," so each pass is a fresh chance to
give an over-granted job attacker-reachable code. That happened once already:
``post-pr-retrospective.yml:prepare`` gained a checkout while inheriting
``pull-requests``, ``issues``, and ``id-token`` write. A manual review caught it
(PR #3967) and scoped it to ``contents: read``. Manual review is the only
control this repository has for it.

The 38 stay frozen below rather than scoped by hand: each needs per-job
knowledge of what it calls, and a wrong guess breaks CI. The gate stops the
bleeding, and the burn-down rides the extraction PRs.

Comparison is set equality, not a subset check. A stale entry would re-permit
the exact regression this gate exists to block: scope a job, leave its line
here, and a later PR deleting that ``permissions:`` block passes. So fixing a
job means deleting its line in the same PR.

Implementer note: ``permissions: {}`` breaks ``actions/checkout``. The floor for
a read-only job is ``contents: read``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github/workflows"

# (workflow filename, job name) for every job inheriting a write scope today.
# Delete a line when you give that job its own permissions block.
_GRANDFATHERED: frozenset[tuple[str, str]] = frozenset(
    {
        ("ai-metrics-analysis.yml", "analyze-metrics"),
        ("ai-session-protocol.yml", "aggregate"),
        ("ai-session-protocol.yml", "check-changes"),
        ("ai-session-protocol.yml", "detect-changes"),
        ("ai-session-protocol.yml", "skip-validation"),
        ("ai-session-protocol.yml", "validate"),
        ("ai-session-protocol.yml", "validate-investigation-claims"),
        ("ai-spec-validation.yml", "check-paths"),
        ("ai-spec-validation.yml", "debounce"),
        ("ai-spec-validation.yml", "validate-spec"),
        ("artifact-insight-scanner.yml", "scan-artifacts"),
        ("auto-assign-reviewer.yml", "assign-reviewer"),
        ("claude.yml", "check-authorization"),
        ("claude.yml", "claude-response"),
        ("copilot-context-synthesis.yml", "sweep-missed"),
        ("copilot-context-synthesis.yml", "synthesize-single"),
        ("investigation-claim-backstop.yml", "validate-claims"),
        ("label-pr.yml", "label"),
        ("memory-health.yml", "check-paths"),
        ("memory-health.yml", "health-check"),
        ("memory-health.yml", "skip-health-check"),
        ("memory-validation.yml", "check-paths"),
        ("memory-validation.yml", "validate-memories"),
        ("milestone-tracking.yml", "assign-milestone"),
        ("post-pr-retrospective.yml", "retrospective"),
        ("pr-validation.yml", "validate-pr"),
        ("quality-grades.yml", "audit"),
        ("rjmurillo-bot.yml", "respond"),
        ("software-engineering-library-activation.yml", "activation-gate"),
        ("update-reviewer-stats.yml", "update-stats"),
    }
)


def _workflows() -> list[Path]:
    return sorted(p for p in WORKFLOW_DIR.glob("*.y*ml"))


def _jobs(doc: object) -> dict[str, dict]:
    if not isinstance(doc, dict):
        return {}
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


def write_scopes(permissions: object) -> list[str]:
    """Return the scopes a ``permissions:`` value grants at write level.

    ``write-all`` is the string shorthand for every scope, so it reports as
    ``["ALL"]`` rather than an enumeration nobody would keep current. ``{}``,
    ``read-all``, and a missing key grant no writes.
    """
    if isinstance(permissions, str):
        return ["ALL"] if permissions == "write-all" else []
    if isinstance(permissions, dict):
        return sorted(str(scope) for scope, level in permissions.items() if level == "write")
    return []


def jobs_inheriting_write(doc: object) -> dict[str, list[str]]:
    """Map job name to the write scopes it inherits by declaring none itself.

    A job that declares any ``permissions:`` block is clean regardless of what
    that block contains. The value is the author's call, made where a reviewer
    can see it. This gate is about the jobs where nobody made a call at all.
    """
    inherited = write_scopes(doc.get("permissions") if isinstance(doc, dict) else None)
    if not inherited:
        return {}
    return {name: inherited for name, job in _jobs(doc).items() if "permissions" not in job}


def _offenders() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for workflow in _workflows():
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        for name in jobs_inheriting_write(doc):
            found.add((workflow.name, name))
    return found


def test_no_job_silently_inherits_a_new_write_scope() -> None:
    found = _offenders()
    added = sorted(found - _GRANDFATHERED)
    removed = sorted(_GRANDFATHERED - found)
    assert found == _GRANDFATHERED, (
        "Jobs inheriting a workflow-level write scope changed.\n"
        f"New offenders (give each an explicit `permissions:` block; "
        f"`contents: read` is the floor for a job that only reads code): {added}\n"
        f"Fixed, so delete these lines from _GRANDFATHERED: {removed}"
    )


class TestWriteScopes:
    def test_reports_only_the_write_entries(self) -> None:
        assert write_scopes({"contents": "read", "issues": "write"}) == ["issues"]

    def test_sorts_multiple_write_entries(self) -> None:
        assert write_scopes({"pull-requests": "write", "id-token": "write"}) == [
            "id-token",
            "pull-requests",
        ]

    def test_write_all_shorthand_reports_all(self) -> None:
        assert write_scopes("write-all") == ["ALL"]

    def test_read_all_shorthand_grants_nothing(self) -> None:
        assert write_scopes("read-all") == []

    def test_empty_block_grants_nothing(self) -> None:
        assert write_scopes({}) == []

    def test_read_only_block_grants_nothing(self) -> None:
        assert write_scopes({"contents": "read"}) == []

    def test_missing_key_grants_nothing(self) -> None:
        assert write_scopes(None) == []

    def test_non_mapping_value_grants_nothing(self) -> None:
        assert write_scopes(["contents: read"]) == []


class TestJobsInheritingWrite:
    def test_a_job_with_no_block_inherits(self) -> None:
        doc = {"permissions": {"issues": "write"}, "jobs": {"debounce": {"steps": []}}}
        assert jobs_inheriting_write(doc) == {"debounce": ["issues"]}

    def test_a_job_with_its_own_block_is_clean(self) -> None:
        doc = {
            "permissions": {"issues": "write"},
            "jobs": {"debounce": {"permissions": {"contents": "read"}, "steps": []}},
        }
        assert jobs_inheriting_write(doc) == {}

    def test_a_job_with_an_empty_own_block_is_clean(self) -> None:
        """Declaring ``permissions: {}`` is a decision a reviewer can see."""
        doc = {
            "permissions": {"issues": "write"},
            "jobs": {"debounce": {"permissions": {}, "steps": []}},
        }
        assert jobs_inheriting_write(doc) == {}

    def test_a_read_only_workflow_level_block_inherits_nothing(self) -> None:
        doc = {"permissions": {"contents": "read"}, "jobs": {"debounce": {"steps": []}}}
        assert jobs_inheriting_write(doc) == {}

    def test_only_the_undeclared_jobs_are_reported(self) -> None:
        doc = {
            "permissions": {"issues": "write"},
            "jobs": {
                "scoped": {"permissions": {"contents": "read"}},
                "unscoped": {"steps": []},
            },
        }
        assert jobs_inheriting_write(doc) == {"unscoped": ["issues"]}

    def test_a_workflow_with_no_jobs_is_clean(self) -> None:
        assert jobs_inheriting_write({"permissions": {"issues": "write"}}) == {}

    def test_non_mapping_jobs_are_skipped(self) -> None:
        doc = {"permissions": {"issues": "write"}, "jobs": {"oops": "not-a-mapping"}}
        assert jobs_inheriting_write(doc) == {}

    @pytest.mark.parametrize("jobs", [[], "nope", 7, True])
    def test_a_non_mapping_jobs_key_is_skipped(self, jobs: object) -> None:
        """Edge: ``jobs`` itself is not a mapping, so there is nothing to walk.

        Distinct from the test above, where ``jobs`` is a mapping and one job
        value is not. A ``jobs: []`` document reaches ``.items()`` on a list
        and raises ``AttributeError`` unless ``_jobs`` type-checks the key.

        The isinstance check that prevents this cannot be deleted without
        failing ``test_a_workflow_with_no_jobs_is_clean``, but it can be
        weakened to ``jobs is None``, which passes every other test in this
        module and reinstates the crash. This case is what catches that.
        """
        assert jobs_inheriting_write({"permissions": {"issues": "write"}, "jobs": jobs}) == {}

    def test_a_non_mapping_document_is_clean(self) -> None:
        assert jobs_inheriting_write("---") == {}
