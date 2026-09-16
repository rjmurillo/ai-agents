"""Pin which pull-request-triggered jobs can publish a check run or commit status.

A required status context is matched by name. Nothing today ties a context to
the app that may publish it: ADR-101 item 7
(`.agents/architecture/ADR-101-enforcement-planes.md`) exists precisely to add
that binding, an `integration_id` pinned in the ruleset, and it has not landed.
Until it does, `checks: write` or `statuses: write` on a `pull_request` or
`pull_request_target` trigger is the permission to publish a check run or commit
status under any name at all, including the name of a required context, from
code the head of the pull request controls. That is a manufactured green tick on
a gate whose work never ran, the same outcome as the 2026-08-02 Instruction
Budget incident (`.claude/rules/ci-scripts.md`, "Path filters gate the diff,
never the tree"), reached by a different route.

This is a surface inventory, not a prohibition: three jobs hold the permission
for a real reason and are listed below with that reason. The gate is set
equality, matching `test_workflow_job_permissions.py`. A new entry fails until
someone writes down why the job needs to publish, and a removed entry fails
until the line goes too, so a job that loses the permission cannot silently get
it back.

What this does NOT close: a job holding the permission can still publish under a
required context's name today. Only the `integration_id` pin closes that. This
gate makes the set of such jobs a reviewed decision instead of an accident.

The sharpest instance on the list is `claude.yml`'s `claude-response`, which
inherits both scopes and runs an LLM agent over pull request and comment text on
a `pull_request` trigger. An injection that reached the Checks API from there
would mint a required context (ASI01, CWE-94). That predates this gate and is
not made worse by it; it is named here so nobody reads the allowlist as a
statement that the three entries are harmless.

One assumption this resolver rests on: a job that declares no `permissions:`
block at any level resolves to the repository's default `GITHUB_TOKEN` scope,
which cannot be read from workflow YAML, so this code treats that case as
non-publishing. That is only sound because `scripts/validate_workflows.py`
`validate_permissions` already fails a workflow declaring permissions nowhere.
If that gate is ever relaxed, this one acquires a blind spot.

Scope note: the trigger is what matters, not the job. A `push` or `schedule`
workflow runs base-owned code, so its grants are outside this gate. A workflow
carrying both a pull-request trigger and others is in scope, because the
pull-request path is reachable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from tests.workflows.test_workflow_job_permissions import write_scopes

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github/workflows"

# Publishing either of these under a name is what satisfies a required context:
# `checks` creates check runs, `statuses` creates commit statuses. GitHub
# accepts a required context from either.
_PUBLISHER_SCOPES = ("checks", "statuses")

_PR_TRIGGERS = frozenset({"pull_request", "pull_request_target"})

# (workflow filename, job name) for every pull-request-reachable job that can
# publish. Each line needs a reason in the comment above it. Delete the line in
# the same change that removes the permission.
_ALLOWED: frozenset[tuple[str, str]] = frozenset(
    {
        # Both inherit `checks: write` and `statuses: write` from claude.yml's
        # workflow-level block, so neither can be scoped without touching the
        # other. They are already carried in `test_workflow_job_permissions.py`'s
        # `_GRANDFATHERED` set as silent inheritors. Whether the Claude Code
        # action needs either scope is unverified here and worth its own change;
        # this workflow runs the agent loop itself, so narrowing it blind is the
        # riskier move.
        ("claude.yml", "check-authorization"),
        ("claude.yml", "claude-response"),
        # Publishes the "CodeQL Analysis Report" check run through
        # dorny/test-reporter when no scannable file changed. The permission is
        # used, and the name it publishes is not a required context; the four
        # required CodeQL contexts come from the `analyze` matrix, which reports
        # on every run.
        ("codeql-analysis.yml", "skip-analysis"),
    }
)


def _triggers(doc: object) -> set[str]:
    """Return the workflow's trigger names.

    PyYAML resolves a bare ``on:`` key to the boolean ``True`` under YAML 1.1,
    so the key is read at both spellings. A workflow whose ``on:`` is a bare
    string (``on: push``) or a list is handled too.
    """
    if not isinstance(doc, dict):
        return set()
    on = doc.get(True, doc.get("on"))
    if isinstance(on, dict):
        return {str(k) for k in on}
    if isinstance(on, list):
        return {str(k) for k in on}
    if isinstance(on, str):
        return {on}
    return set()


def publishing_jobs(doc: object) -> dict[str, list[str]]:
    """Map job name to the publisher scopes it resolves, for one workflow.

    A job's own ``permissions:`` block wins; with none, it inherits the
    workflow-level block. Returns nothing for a workflow with no pull-request
    trigger, since only that path runs head-controlled code.
    """
    if not isinstance(doc, dict) or not (_triggers(doc) & _PR_TRIGGERS):
        return {}
    inherited = doc.get("permissions")
    found: dict[str, list[str]] = {}
    for name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        resolved = job.get("permissions", inherited)
        scopes = write_scopes(resolved)
        if "ALL" in scopes:
            found[name] = list(_PUBLISHER_SCOPES)
            continue
        publishing = [s for s in _PUBLISHER_SCOPES if s in scopes]
        if publishing:
            found[name] = publishing
    return found


@dataclass(frozen=True)
class Scan:
    """One pass over the workflow directory.

    ``in_scope`` and ``out_of_scope`` partition ``examined``. Keeping both,
    rather than deriving one from the other, is what lets a caller assert that
    every file was classified rather than merely visited.
    """

    found: frozenset[tuple[str, str]]
    examined: int
    in_scope: int
    out_of_scope: int
    untriggered: tuple[str, ...]


def _scan() -> Scan:
    found: set[tuple[str, str]] = set()
    workflows = sorted(WORKFLOW_DIR.glob("*.y*ml"))
    in_scope = out_of_scope = 0
    untriggered: list[str] = []
    for workflow in workflows:
        doc = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        triggers = _triggers(doc)
        if not triggers:
            untriggered.append(workflow.name)
        elif triggers & _PR_TRIGGERS:
            in_scope += 1
        else:
            out_of_scope += 1
        for name in publishing_jobs(doc):
            found.add((workflow.name, name))
    return Scan(
        found=frozenset(found),
        examined=len(workflows),
        in_scope=in_scope,
        out_of_scope=out_of_scope,
        untriggered=tuple(untriggered),
    )


def test_no_new_pull_request_job_can_publish_a_required_context() -> None:
    scan = _scan()
    added = sorted(scan.found - _ALLOWED)
    removed = sorted(_ALLOWED - scan.found)
    assert scan.found == _ALLOWED, (
        f"examined {scan.examined} workflow files, "
        f"{scan.in_scope} with a pull-request trigger.\n"
        "The set of pull-request-reachable jobs that can publish a check run or "
        "commit status changed.\n"
        f"New ({len(added)}): {added}\n"
        "  Each of these can publish under a required context's name from "
        "head-editable code. Drop the scope if unused, or add the entry here "
        "with the reason it must publish.\n"
        f"Gone ({len(removed)}): {removed}\n"
        "  Delete each from _ALLOWED in the same change, or the job can regain "
        "the permission later without failing this gate."
    )


class TestTriggers:
    """`on:` reaches this code at three spellings plus PyYAML's boolean key."""

    def test_bare_on_key_resolves_to_true_under_yaml_1_1(self) -> None:
        doc = yaml.safe_load("on:\n  pull_request:\n    branches: [main]\n")
        assert True in doc, "PyYAML no longer folds `on:` to True; _triggers needs updating"
        assert _triggers(doc) == {"pull_request"}

    def test_quoted_on_key_stays_a_string(self) -> None:
        assert _triggers({"on": {"push": None}}) == {"push"}

    def test_list_form(self) -> None:
        assert _triggers({"on": ["push", "pull_request"]}) == {"push", "pull_request"}

    def test_scalar_form(self) -> None:
        assert _triggers({"on": "pull_request_target"}) == {"pull_request_target"}

    def test_missing_on_key_reports_no_triggers(self) -> None:
        assert _triggers({"jobs": {}}) == set()

    def test_non_mapping_document_reports_no_triggers(self) -> None:
        assert _triggers(["not", "a", "workflow"]) == set()


class TestPublishingJobs:
    """Only a pull-request-reachable job that resolves a publisher scope counts."""

    def _doc(self, perms: object, job_perms: object = "__absent__") -> dict:
        job: dict[str, object] = {"runs-on": "ubuntu-latest"}
        if job_perms != "__absent__":
            job["permissions"] = job_perms
        return {"on": {"pull_request": None}, "permissions": perms, "jobs": {"j": job}}

    def test_job_level_checks_write_is_reported(self) -> None:
        assert publishing_jobs(self._doc(None, {"checks": "write"})) == {"j": ["checks"]}

    def test_job_level_statuses_write_is_reported(self) -> None:
        assert publishing_jobs(self._doc(None, {"statuses": "write"})) == {"j": ["statuses"]}

    def test_inherited_scope_is_reported_when_the_job_declares_none(self) -> None:
        assert publishing_jobs(self._doc({"checks": "write"})) == {"j": ["checks"]}

    def test_a_job_block_overrides_the_inherited_grant(self) -> None:
        # The job's own block wins outright, which is why an inheriting job and
        # a scoped job cannot be judged by the workflow block alone.
        assert publishing_jobs(self._doc({"checks": "write"}, {"contents": "read"})) == {}

    def test_write_all_shorthand_reports_every_publisher_scope(self) -> None:
        assert publishing_jobs(self._doc(None, "write-all")) == {"j": ["checks", "statuses"]}

    def test_read_level_grants_nothing(self) -> None:
        assert publishing_jobs(self._doc(None, {"checks": "read"})) == {}

    def test_contents_write_alone_is_not_a_publisher_scope(self) -> None:
        assert publishing_jobs(self._doc(None, {"contents": "write"})) == {}

    def test_a_push_only_workflow_is_out_of_scope(self) -> None:
        doc = {"on": {"push": None}, "jobs": {"j": {"permissions": {"checks": "write"}}}}
        assert publishing_jobs(doc) == {}

    def test_a_mixed_trigger_workflow_is_in_scope(self) -> None:
        doc = {
            "on": {"push": None, "pull_request": None},
            "jobs": {"j": {"permissions": {"checks": "write"}}},
        }
        assert publishing_jobs(doc) == {"j": ["checks"]}

    def test_pull_request_target_is_in_scope(self) -> None:
        doc = {
            "on": {"pull_request_target": None},
            "jobs": {"j": {"permissions": {"statuses": "write"}}},
        }
        assert publishing_jobs(doc) == {"j": ["statuses"]}

    def test_non_mapping_job_is_skipped(self) -> None:
        doc = {
            "on": {"pull_request": None},
            "permissions": {"checks": "write"},
            "jobs": {"j": None},
        }
        assert publishing_jobs(doc) == {}

    def test_a_workflow_with_no_jobs_is_clean(self) -> None:
        assert publishing_jobs({"on": {"pull_request": None}, "permissions": "write-all"}) == {}

    def test_non_mapping_document_is_clean(self) -> None:
        assert publishing_jobs("not a workflow") == {}


def test_every_workflow_file_is_classified_not_merely_visited() -> None:
    """A file whose `on:` shape the resolver cannot read must fail, not vanish.

    The weaker check this replaces compared the examined count against a second
    `glob` of the same directory. Both counts came from the same call, so it was
    close to tautological: it proved the loop visited every file, not that every
    file was classified. A future workflow whose `on:` took a shape `_triggers`
    does not fold would resolve to an empty trigger set, drop out of `in_scope`
    without being counted anywhere, and carry any `checks: write` grant past the
    gate in silence. Raised as MEDIUM-001 in the security review of the commit
    that introduced this file.

    Asserting the partition closes that: every file lands in exactly one of
    in-scope or out-of-scope, and a file that lands in neither is named.
    `.claude/rules/ci-scripts.md` MUST 12 is the same idea one level up.
    """
    scan = _scan()
    assert scan.examined > 0, "no workflow files found; WORKFLOW_DIR is wrong"
    assert not scan.untriggered, (
        f"examined {scan.examined} workflow files; {len(scan.untriggered)} resolved no "
        f"trigger at all: {list(scan.untriggered)}.\n"
        "Either the file has no `on:` block, or its `on:` uses a shape `_triggers` "
        "does not handle. Until `_triggers` reads it, that workflow's jobs are never "
        "checked for a publishing permission."
    )
    assert scan.in_scope + scan.out_of_scope == scan.examined
    assert scan.in_scope > 0, "no pull-request-triggered workflow found; the resolver is broken"
    assert scan.found, "no publishing job found at all; the resolver is probably broken"
