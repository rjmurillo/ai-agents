"""Ratchet gate: jobs must not inherit workflow-level write permissions (issue #3964).

A job without its own ``permissions:`` block silently inherits the
workflow-level block. When the workflow grants write scopes, every job in it
holds write whether it uses it or not. The ADR-006 extraction campaign is
converting jobs from "inline shell, no checkout" into "checkout + repo script",
which turns a dormant inherited over-grant into a live one.

This gate freezes the current offenders. A new job without ``permissions:``
that lands in a write-scoped workflow fails immediately (the live set is a
strict superset of the grandfathered set). A job that gains its own block is
removed from the live set, which also fails (set shrank without removing the
literal from _GRANDFATHERED). Both failure modes force an explicit code change,
so the count only ratchets down.

Set equality rather than subset: see scripts/ci/count_ratchet.py for the same
"unrecorded decrease fails" policy stated there.

CWE-269: improper privilege management. See also #2967 (ADR-006 extraction).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github/workflows"

# Snapshot of over-granted jobs on origin/main at the time of this test's
# creation. Each entry is (workflow_filename, job_name). Jobs that gain their
# own ``permissions:`` block MUST be removed from this set in the same PR.
# New jobs with the same problem MUST NOT be added; the test will fail.
_GRANDFATHERED: frozenset[tuple[str, str]] = frozenset(
    {
        ("ai-issue-triage.yml", "ai-issue-triage"),
        ("ai-metrics-analysis.yml", "analyze-metrics"),
        ("ai-pr-quality-gate.yml", "aggregate"),
        ("ai-pr-quality-gate.yml", "check-changes"),
        ("ai-pr-quality-gate.yml", "debounce"),
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
        ("homework-scanner.yml", "scan"),
        ("investigation-claim-backstop.yml", "validate-claims"),
        ("label-issues.yml", "label"),
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
        ("velocity-accelerator.yml", "detect-opportunities"),
        ("velocity-accelerator.yml", "post-summary"),
        ("workflow-coalescing-metrics.yml", "collect-metrics"),
    }
)


def write_scopes(perms: object) -> list[str]:
    """Return write-granted scope names for a permissions value.

    ``perms`` is the value of a ``permissions:`` YAML key. Three forms exist:

    - string ``"write-all"`` or ``"read-all"``
    - mapping ``{scope: level, ...}``
    - missing / ``{}`` (no write)

    Returns the sorted list of scope names whose level is ``"write"``, or
    ``["ALL"]`` for the ``"write-all"`` string shorthand, or ``[]`` for any
    read-only or absent value.
    """
    if perms == "write-all":
        return ["ALL"]
    if not isinstance(perms, dict):
        return []
    return sorted(k for k, v in perms.items() if v == "write")


def over_granted(doc: object) -> list[tuple[str, list[str]]]:
    """Yield (job_name, write_scopes) for jobs inheriting workflow write.

    A job is over-granted when it has no ``permissions:`` key of its own AND
    the workflow-level ``permissions:`` grants at least one write scope.
    Jobs that carry their own block (even an empty one) are not returned.
    """
    if not isinstance(doc, dict):
        return []
    wf_write = write_scopes(doc.get("permissions"))
    if not wf_write:
        return []
    result = []
    for name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        if "permissions" in job:
            continue
        result.append((name, wf_write))
    return result


def _workflows() -> list[Path]:
    return sorted(p for p in WORKFLOW_DIR.glob("*.y*ml"))


def _jobs(doc: object) -> dict[str, dict]:
    if not isinstance(doc, dict):
        return {}
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict):
        return {}
    return {name: job for name, job in jobs.items() if isinstance(job, dict)}


# ---- ratchet gate -------------------------------------------------------


def test_over_granted_jobs_match_grandfathered_set() -> None:
    """Live set of over-granted jobs must equal the frozen snapshot exactly.

    - A new offender grows the live set above the snapshot -> test fails.
    - A fixed job shrinks the live set below the snapshot -> test fails
      (forces the literal out of _GRANDFATHERED so there is no slack).
    """
    live: set[tuple[str, str]] = set()
    for wf in _workflows():
        try:
            doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        for job_name, _ in over_granted(doc):
            live.add((wf.name, job_name))

    new_offenders = live - _GRANDFATHERED
    assert not new_offenders, (
        "New over-granted jobs detected (add explicit permissions: or extend "
        "_GRANDFATHERED and document why):\n"
        + "\n".join(f"  {f}:{j}" for f, j in sorted(new_offenders))
    )

    fixed_not_removed = _GRANDFATHERED - live
    assert not fixed_not_removed, (
        "Jobs in _GRANDFATHERED no longer over-granted -- remove them from "
        "the frozen set to keep the ratchet tight:\n"
        + "\n".join(f"  {f}:{j}" for f, j in sorted(fixed_not_removed))
    )


# ---- unit tests for helpers ---------------------------------------------


class TestWriteScopes:
    def test_write_all_string_returns_all_sentinel(self) -> None:
        assert write_scopes("write-all") == ["ALL"]

    def test_read_all_string_returns_empty(self) -> None:
        assert write_scopes("read-all") == []

    def test_mapping_extracts_write_keys(self) -> None:
        perms = {"contents": "write", "issues": "read", "pull-requests": "write"}
        assert write_scopes(perms) == ["contents", "pull-requests"]

    def test_all_read_mapping_returns_empty(self) -> None:
        assert write_scopes({"contents": "read"}) == []

    def test_empty_mapping_returns_empty(self) -> None:
        assert write_scopes({}) == []

    def test_none_returns_empty(self) -> None:
        assert write_scopes(None) == []

    def test_missing_value_returns_empty(self) -> None:
        # permissions: key absent
        assert write_scopes(object()) == []


class TestOverGranted:
    def _make_doc(self, wf_perms: object, jobs: dict) -> dict:
        doc: dict = {"jobs": jobs}
        if wf_perms is not None:
            doc["permissions"] = wf_perms
        return doc

    def test_job_without_own_block_is_returned(self) -> None:
        doc = self._make_doc(
            {"issues": "write"}, {"my-job": {"runs-on": "ubuntu-latest"}}
        )
        result = over_granted(doc)
        assert result == [("my-job", ["issues"])]

    def test_job_with_own_block_is_excluded(self) -> None:
        doc = self._make_doc(
            {"issues": "write"},
            {
                "my-job": {
                    "runs-on": "ubuntu-latest",
                    "permissions": {"contents": "read"},
                }
            },
        )
        assert over_granted(doc) == []

    def test_job_with_empty_own_block_is_excluded(self) -> None:
        doc = self._make_doc(
            {"issues": "write"},
            {"my-job": {"runs-on": "ubuntu-latest", "permissions": {}}},
        )
        assert over_granted(doc) == []

    def test_read_only_workflow_perms_returns_empty(self) -> None:
        doc = self._make_doc(
            {"contents": "read"},
            {"my-job": {"runs-on": "ubuntu-latest"}},
        )
        assert over_granted(doc) == []

    def test_no_workflow_permissions_block_returns_empty(self) -> None:
        doc = self._make_doc(None, {"my-job": {"runs-on": "ubuntu-latest"}})
        assert over_granted(doc) == []

    def test_write_all_string_is_detected(self) -> None:
        doc = self._make_doc(
            "write-all", {"my-job": {"runs-on": "ubuntu-latest"}}
        )
        result = over_granted(doc)
        assert result == [("my-job", ["ALL"])]

    def test_non_dict_doc_returns_empty(self) -> None:
        assert over_granted("not a dict") == []
        assert over_granted(None) == []
        assert over_granted([]) == []

    def test_non_dict_job_entry_is_skipped(self) -> None:
        doc = self._make_doc({"issues": "write"}, {"bad-job": "string"})
        assert over_granted(doc) == []


@pytest.mark.parametrize("workflow", _workflows(), ids=lambda p: p.name)
def test_workflow_parses_as_yaml(workflow: Path) -> None:
    """Each workflow file must be parseable. Catches syntax regressions early."""
    doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert doc is not None
