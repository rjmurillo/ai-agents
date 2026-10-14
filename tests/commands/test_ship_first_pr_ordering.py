"""Ordering contract for `/ship`: a branch with no PR must be able to open its first one.

Issue #4841. `/ship` ran `pipeline-validator` as GitHub pre-flight check 1 and gated
`/push-pr` behind every pre-flight check passing. `pipeline-validator` refuses to run
without a PR, and `/push-pr` is the step that creates the first PR, so a fresh branch
could never leave that state: check 1 stopped the run, the PR was never created, and the
next `/ship` hit the same wall.

The canonical contract this deadlock comes from is in
`.claude/skills/pipeline-validator/SKILL.md`, Step 1 "Decision", read verbatim on
2026-08-13:

    - **No PR found:** Report to user. A PR must exist before pipeline validation. The
      calling skill should have created one.

That contract is correct for the validator. The bug was the order in which `/ship` called
it, so the fix is in `/ship` and this module pins the repaired order.

Two inverse failure modes are pinned alongside the fix, because either one turns the
repair into a worse defect:

1. **Over-deferral.** Deferring pipeline validation for every GitHub run would drop the
   pre-flight CI gate on branches that already have a PR.
   `test_open_pr_still_validates_in_preflight` fails if the existing-PR branch stops
   invoking the validator up front.
2. **Silent skip.** Deferring and never discharging would let a ship report read green
   with zero CI evidence. `test_process_discharges_deferral_after_push_pr` fails if the
   validator is not invoked after `/push-pr`.

Assertions parse the document into sections and bullets rather than substring-matching the
whole file (`.claude/rules/testing.md` MUST 9): a bare `"pipeline-validator" in text` holds
when the name survives only in a prose reference and proves nothing about which branch
invokes it. `TestPreFixControl` feeds the pre-fix ordering back through the same helpers, so
every check here is shown to fail on the shape it was written against
(`.claude/rules/testing.md` SHOULD 10).

`.claude/skills/ship/SKILL.md` is the source; `src/copilot-cli/skills/ship/SKILL.md` is
generated from it by `build/scripts/generate_skills.py` (see
`.agents/governance/GENERATOR-FILES.md`). Both are asserted so the shipped Copilot copy
cannot carry the deadlock after the Claude copy is fixed. The generator rewrites the
invocation syntax (`Skill(skill="pipeline-validator")` becomes
`` `skill: "pipeline-validator"` ``), so `invokes_pipeline_validator` accepts both forms.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / ".claude" / "skills" / "ship" / "SKILL.md"
COMMAND_MIRROR_PATH = REPO_ROOT / "src" / "copilot-cli" / "skills" / "ship" / "SKILL.md"
WAIT_REFERENCE = Path("references") / "ado-policy-wait.md"
VALIDATOR_SKILL_PATH = REPO_ROOT / ".claude" / "skills" / "pipeline-validator" / "SKILL.md"

_FRONTMATTER_RE = re.compile(r"^---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
_HEADING_RE = re.compile(r"^## .+$", re.MULTILINE)
_NUMBERED_ITEM_RE = re.compile(r"^\d+\. ", re.MULTILINE)
_HOST_BULLET_RE = re.compile(r"^ {3}- (?P<body>.*)$", re.MULTILINE)
# Claude: Invoke Skill(skill="pipeline-validator"). Copilot: Invoke `skill: "pipeline-validator"`.
_INVOKE_VALIDATOR_RE = re.compile(r'(?:Skill\(skill=|skill:\s*)"pipeline-validator"')
_DISCHARGES_CI_RE = re.compile(r'(?:Skill\(skill=|skill:\s*)"pipeline-validator"|get_pr_checks\.py')
_NO_PR_DECISION_RE = re.compile(r"^- (\*\*No PR found:\*\* .+)$", re.MULTILINE)


def body_of(text: str) -> str:
    """Return the markdown body with any YAML frontmatter removed."""
    return _FRONTMATTER_RE.sub("", text, count=1)


def section(text: str, heading: str) -> str:
    """Return the ``## heading`` section body, up to the next level-2 heading.

    Raises AssertionError when the heading is absent so a renamed section fails loudly
    instead of silently returning an empty string that passes every "not in" assertion.
    """
    marker = f"## {heading}"
    start = body_of(text).find(marker)
    assert start != -1, f"section '{marker}' not found"
    rest = body_of(text)[start + len(marker) :]
    next_heading = _HEADING_RE.search(rest)
    return rest[: next_heading.start()] if next_heading else rest


def numbered_items(section_text: str) -> list[str]:
    """Return the top-level numbered list items of ``section_text``, in document order."""
    starts = [m.start() for m in _NUMBERED_ITEM_RE.finditer(section_text)]
    assert starts, "section contains no numbered items"
    bounds = zip(starts, [*starts[1:], len(section_text)], strict=True)
    return [section_text[begin:end] for begin, end in bounds]


def numbered_item(section_text: str, opening: str) -> str:
    """Return one numbered list item of ``section_text``, selected by its opening text."""
    matches = [i for i in numbered_items(section_text) if opening in i.splitlines()[0]]
    assert len(matches) == 1, f"expected 1 item opening with {opening!r}, got {len(matches)}"
    return matches[0]


def host_bullets(item_text: str) -> list[str]:
    """Return the host-branch bullets of a pre-flight item (three-space indented)."""
    bullets = (m.group("body") for m in _HOST_BULLET_RE.finditer(item_text))
    return [b for b in bullets if "host=" in b]


def github_bullets(item_text: str) -> list[str]:
    """Return the `host=github` bullets of a pre-flight item."""
    return [b for b in host_bullets(item_text) if "`host=github`" in b]


def ado_bullets(item_text: str) -> list[str]:
    """Return the `host=ado` bullets of a pre-flight item."""
    return [b for b in host_bullets(item_text) if "`host=ado`" in b]


def ado_bullets_without_pr_condition(pipeline_item: str) -> list[str]:
    """Return `host=ado` bullets that do not branch on PR existence (#6576 shape)."""
    return [b for b in ado_bullets(pipeline_item) if "pr=" not in b]


def ado_item_block(pipeline_item: str, pr_marker: str) -> str:
    """Return one `host=ado` bullet plus its indented body (code block included).

    The bullet's first line names the branch; its evidence lives in the nested code
    block, so the block runs to the next three-space bullet or the end of the item.
    """
    lines = pipeline_item.splitlines()
    starts = [
        i
        for i, ln in enumerate(lines)
        if ln.startswith("   - ") and "`host=ado`" in ln and pr_marker in ln
    ]
    assert len(starts) == 1, f"expected 1 host=ado bullet with {pr_marker!r}, got {len(starts)}"
    end = next(
        (j for j in range(starts[0] + 1, len(lines)) if lines[j].startswith("   - ")),
        len(lines),
    )
    return "\n".join(lines[starts[0] : end])


def invokes_pipeline_validator(text: str) -> bool:
    """True when ``text`` invokes the skill, not merely when it names the file."""
    return _INVOKE_VALIDATOR_RE.search(text) is not None


def github_bullets_without_pr_condition(pipeline_item: str) -> list[str]:
    """Return `host=github` bullets that do not branch on PR existence.

    A GitHub bullet with no `pr=` qualifier is the #4841 deadlock shape: it applies to
    every GitHub run, including the one where no PR exists yet.
    """
    return [b for b in host_bullets(pipeline_item) if "`host=github`" in b and "pr=" not in b]


def discharges_ci(text: str) -> bool:
    """True when ``text`` discharges the deferred CI check via any supported mechanism.

    The discharge can invoke the pipeline-validator skill (ADO path) or query CI status
    through ``get_pr_checks.py`` (GitHub path).
    """
    return _DISCHARGES_CI_RE.search(text) is not None


def deferral_discharged_after_push_pr(process_section: str) -> bool:
    """True when a later process step validates CI than the step creating the PR.

    Compares list-item positions rather than character offsets: the discharge step names
    `/push-pr` again while describing which PR to validate, so an offset comparison would
    read that mention and report the invocation as coming first.
    """
    items = numbered_items(process_section)
    creates = [i for i, item in enumerate(items) if "/push-pr" in item]
    validates = [i for i, item in enumerate(items) if discharges_ci(item)]
    return bool(creates) and bool(validates) and min(validates) > min(creates)


def canonical_no_pr_contract() -> str:
    """Return the verbatim 'No PR found' decision line from the pipeline-validator skill."""
    match = _NO_PR_DECISION_RE.search(VALIDATOR_SKILL_PATH.read_text(encoding="utf-8"))
    assert match is not None, f"no 'No PR found' decision line in {VALIDATOR_SKILL_PATH}"
    return match.group(1)


@pytest.fixture(params=[COMMAND_PATH, COMMAND_MIRROR_PATH], ids=["claude", "copilot"])
def ship_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


@pytest.fixture
def pipeline_item(ship_text: str) -> str:
    return numbered_item(section(ship_text, "Pre-flight Checks"), "**Pipeline health**")


class TestPipelineHealthBranchesOnPrExistence:
    def test_no_github_bullet_applies_to_every_run(self, pipeline_item: str) -> None:
        assert github_bullets_without_pr_condition(pipeline_item) == []

    def test_open_pr_still_validates_in_preflight(self, pipeline_item: str) -> None:
        """Inverse guard: the fix must not disarm the gate for branches that have a PR."""
        with_pr = [b for b in github_bullets(pipeline_item) if "`pr=#<number>`" in b]
        assert len(with_pr) == 1
        assert invokes_pipeline_validator(with_pr[0])

    def test_no_pr_bullet_defers_instead_of_invoking(self, pipeline_item: str) -> None:
        without_pr = [b for b in github_bullets(pipeline_item) if "`pr=none`" in b]
        assert len(without_pr) == 1
        assert not invokes_pipeline_validator(without_pr[0])
        assert "DEFERRED" in without_pr[0]
        assert "not skipped" in without_pr[0]

    def test_no_pr_bullet_quotes_the_canonical_validator_contract(self, ship_text: str) -> None:
        """The cited reason must be the validator's real contract, not a remembered one.

        The reference uses a generic name ("the pipeline-validator skill") rather than a
        tree-specific path, per plugin-self-containment.md.
        """
        assert "pipeline-validator skill" in ship_text.lower()
        assert canonical_no_pr_contract() in ship_text

    def test_ado_branch_still_evaluates_build_policies(self, pipeline_item: str) -> None:
        """Sibling non-regression: ADO still evaluates PR build policies, not the validator."""
        ado = ado_bullets(pipeline_item)
        assert len(ado) == 2
        assert all("pipeline-validator does not apply" in b for b in ado)
        assert not any(invokes_pipeline_validator(b) for b in ado)
        assert "az repos pr policy list" in pipeline_item


class TestAdoFirstPrDeferral:
    """Issue #6576: the ADO branch had the same first-PR deadlock as GitHub (#4841).

    Pre-fix, an ADO branch with no PR fell back to the latest completed branch build and
    required every policy to pass. A fresh branch has neither a PR nor a completed build,
    and the PR is only created after the gate passes, so the first ADO PR never opened.
    """

    def test_no_ado_bullet_applies_to_every_run(self, pipeline_item: str) -> None:
        assert ado_bullets_without_pr_condition(pipeline_item) == []

    def test_ado_no_pr_bullet_defers_instead_of_failing(self, pipeline_item: str) -> None:
        without_pr = [b for b in ado_bullets(pipeline_item) if "`pr=none`" in b]
        assert len(without_pr) == 1
        assert "DEFERRED" in without_pr[0]
        assert "not skipped" in without_pr[0]
        assert "6576" in without_pr[0]

    def test_branch_build_fallback_is_gone(self, pipeline_item: str) -> None:
        """The latest-completed-branch-build query is the deadlock; it must not return."""
        assert "az pipelines build list" not in pipeline_item

    def test_ado_open_pr_bullet_checks_blocking_build_evaluations(self, pipeline_item: str) -> None:
        """Inverse guard: the deferral must not disarm the gate for ADO branches with a PR."""
        with_pr = ado_item_block(pipeline_item, "`pr=#<number>`")
        assert "az repos pr policy list" in with_pr
        assert "isBlocking" in with_pr
        assert "'approved'" in with_pr or '"approved"' in with_pr

    def test_ado_open_pr_bullet_binds_builds_to_current_revision(self, pipeline_item: str) -> None:
        """A green build from an older push must not clear the gate."""
        with_pr = ado_item_block(pipeline_item, "`pr=#<number>`")
        assert "lastMergeCommit" in with_pr
        assert "sourceVersion" in with_pr
        assert "az pipelines build show" in with_pr

    def test_ado_query_errors_fail_instead_of_passing(self, pipeline_item: str) -> None:
        """Auth, network, and query errors must stop the check, not read as empty."""
        with_pr = ado_item_block(pipeline_item, "`pr=#<number>`")
        assert with_pr.count("|| exit 3") >= 3
        assert "no blocking build policy" in with_pr.lower()


class TestProcessDischargesTheDeferral:
    def test_process_discharges_deferral_after_push_pr(self, ship_text: str) -> None:
        """Inverse guard: a deferred check must be run later, not dropped."""
        assert deferral_discharged_after_push_pr(section(ship_text, "Process"))

    def test_discharge_step_forbids_reporting_pass_without_the_run(self, ship_text: str) -> None:
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "MUST NOT be reported as PASS without this run" in discharge
        assert "DEFERRED->FAIL" in discharge
        assert "RESULT: BLOCKED" in discharge

    def test_discharge_uses_github_aware_ci_check(self, ship_text: str) -> None:
        """The discharge step must use a GitHub-aware flow, not the ADO-only validator."""
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "get_pr_checks.py" in discharge
        assert "--pull-request" in discharge

    def test_discharge_requires_allpassing_not_just_exit_code(self, ship_text: str) -> None:
        """Exit code 0 alone is insufficient; discharge must check Data.AllPassing."""
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "AllPassing" in discharge, "discharge must gate on Data.AllPassing"
        assert "exit code" in discharge.lower(), (
            "discharge must mention exit code is insufficient alone"
        )

    def test_discharge_covers_ado_first_pr(self, ship_text: str) -> None:
        """Issue #6576: the ADO deferral must be discharged against the created PR."""
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "`host=ado`" in discharge
        assert "pullRequestId" in discharge
        assert f"`{WAIT_REFERENCE.as_posix()}`" in discharge
        assert "queued" in discharge
        assert "running" in discharge
        assert "pre-flight check 1" in discharge

    def test_ado_pr_creation_precedes_its_discharge(self, ship_text: str) -> None:
        items = numbered_items(section(ship_text, "Process"))
        creates = [i for i, item in enumerate(items) if "az repos pr create" in item]
        validates = [i for i, item in enumerate(items) if WAIT_REFERENCE.name in item]
        assert creates
        assert validates
        assert min(validates) > min(creates)

    def test_contributor_mode_still_creates_no_pr(self, ship_text: str) -> None:
        """Inverse guard: the deferral must not leak PR creation into contributor mode."""
        process = section(ship_text, "Process")
        assert "`mode=contributor`: do NOT create a PR and do NOT merge." in process


class TestPrDetectionDistinguishesErrors:
    """The `pr` variable must not treat auth/network failures as 'no PR'."""

    def test_mode_detection_distinguishes_no_pr_from_query_failure(self, ship_text: str) -> None:
        detection = section(ship_text, "Mode Detection")
        # Must mention that non-zero exit can mean different things
        assert "no PR exists" in detection.lower() or "no pull requests" in detection.lower()
        # Must require stopping on non-no-PR failures
        assert "stop" in detection.lower() or "error" in detection.lower()

    def test_ado_detection_distinguishes_no_pr_from_query_failure(self, ship_text: str) -> None:
        """Issue #6576: a failed `az repos pr list` must not set `pr=none`."""
        detection = section(ship_text, "Mode Detection")
        ado = [ln for ln in detection.splitlines() if ln.lstrip().startswith("- `host=ado`")]
        assert len(ado) == 1
        assert "non-zero exit" in ado[0]
        assert "stop with an error" in ado[0]


class TestShipReportStatesTheDeferral:
    def test_report_states_pr_presence_at_preflight(self, ship_text: str) -> None:
        assert "PR-AT-PREFLIGHT: none|#<number>" in section(ship_text, "Output")

    def test_report_offers_both_deferred_outcomes(self, ship_text: str) -> None:
        output = section(ship_text, "Output")
        pipeline_lines = [ln for ln in output.splitlines() if ln.strip().startswith("Pipeline:")]
        assert len(pipeline_lines) == 1
        assert "DEFERRED->PASS" in pipeline_lines[0]
        assert "DEFERRED->FAIL" in pipeline_lines[0]


# The pre-fix ordering, reduced to the parts these helpers read. Reproduced from
# the ship command at commit ab9c636de5 (origin/main, 2026-08-13). Keeping it
# inline rather than reading git history makes the control independent of branch state.
_PRE_FIX_SHIP_MD = """---
description: Ship it.
---

## Pre-flight Checks

1. **Pipeline health**
   - `host=github`: Invoke Skill(skill="pipeline-validator"). All CI checks green?
   - `host=ado`: pipeline-validator does not apply. Evaluate ADO build policies instead.
2. **Security posture** - Invoke Skill(skill="security-scan").

## Process

1. Run all 4 pre-flight checks, branching by `host` and `mode`.
2. If any blocking check fails: report what failed, why, and how to fix. Stop.
3. If all pass:
   - `mode=owner`, `host=github`: run /validate-pr-description, then run /push-pr to open the PR.
4. Report: host, mode, what was validated or shipped, PR link, any warnings.
"""


class TestPreFixControl:
    """The pre-fix text must fail the checks above, or they prove nothing."""

    def test_pre_fix_github_bullet_applies_to_every_run(self) -> None:
        item = numbered_item(section(_PRE_FIX_SHIP_MD, "Pre-flight Checks"), "**Pipeline health**")
        offenders = github_bullets_without_pr_condition(item)
        assert len(offenders) == 1
        assert invokes_pipeline_validator(offenders[0])

    def test_pre_fix_has_no_deferral_branch(self) -> None:
        item = numbered_item(section(_PRE_FIX_SHIP_MD, "Pre-flight Checks"), "**Pipeline health**")
        assert [b for b in host_bullets(item) if "`pr=none`" in b] == []

    def test_pre_fix_never_discharges_after_push_pr(self) -> None:
        assert not deferral_discharged_after_push_pr(section(_PRE_FIX_SHIP_MD, "Process"))

    def test_pre_fix_report_omits_pr_presence(self) -> None:
        assert "PR-AT-PREFLIGHT" not in _PRE_FIX_SHIP_MD


# The pre-#6576 ADO branch, reduced to the parts these helpers read. Reproduced from
# `.claude/skills/ship/SKILL.md` blob 24d1711e14 (origin/main, 2026-10-14).
_PRE_6576_PIPELINE_ITEM = """1. **Pipeline health**
   - `host=github`, `pr=#<number>` (open PR exists): Invoke Skill(skill="pipeline-validator").
   - `host=ado`: pipeline-validator does not apply. Evaluate ADO build policies:

     ```bash
     if [ -n "$pr_id" ]; then
       az repos pr policy list --id "$pr_id" --output table
     else
       az pipelines build list --branch "$branch_ref" --status completed --top 1 --output table
     fi
     ```
"""


class TestPre6576Control:
    """The pre-#6576 ADO branch must fail the ADO checks above, or they prove nothing."""

    def test_pre_fix_ado_bullet_applies_to_every_run(self) -> None:
        assert len(ado_bullets_without_pr_condition(_PRE_6576_PIPELINE_ITEM)) == 1

    def test_pre_fix_ado_has_no_deferral_branch(self) -> None:
        assert [b for b in ado_bullets(_PRE_6576_PIPELINE_ITEM) if "`pr=none`" in b] == []

    def test_pre_fix_ado_uses_branch_build_fallback(self) -> None:
        assert "az pipelines build list" in _PRE_6576_PIPELINE_ITEM


# ---------------------------------------------------------------------------
# Behavioral checks: run the ADO bash blocks against a fake `az`.
#
# The fake applies the query shapes the blocks use to fixture JSON, then prints the
# result with the Azure CLI TSV rules from knack `output.py` (`format_tsv` wraps a
# non-list result in a list; each top-level item is one row; a nested list becomes
# tab-separated columns; `None` inside a row prints as the string "None"). Those rules
# are why a flat `[result, sourceVersion]` query prints two lines, not one row.
# ---------------------------------------------------------------------------

_FAKE_AZ = r"""
import json, os, sys

state = json.load(open(os.environ["FAKE_AZ_STATE"], encoding="utf-8"))
argv = sys.argv[1:]
words = []
for a in argv:
    if a.startswith("--"):
        break
    words.append(a)
sub = " ".join(words)
opts = {}
i = len(words)
while i < len(argv):
    if argv[i].startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
        opts[argv[i]] = argv[i + 1]
        i += 2
    else:
        i += 1
log = os.environ.get("FAKE_AZ_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(sub + "\n")
if sub in state.get("fail", []):
    sys.stderr.write("ERROR: fake az failure for " + sub + "\n")
    sys.exit(1)
query = opts.get("--query", "")


def walk(obj, path):
    for part in path.split("."):
        obj = obj.get(part) if isinstance(obj, dict) else None
    return obj


def fields(obj, spec):
    spec = spec.strip()
    if spec.startswith("[") and spec.endswith("]"):
        return [walk(obj, f.strip()) for f in spec[1:-1].split(",")]
    return walk(obj, spec)


BUILD_FILTER = (
    "[?configuration.isBlocking && configuration.isEnabled"
    " && configuration.type.displayName=='Build']"
)
if sub == "repos pr show":
    result = walk(state["pr"], query)
elif sub == "repos pr policy list":
    if not query.startswith(BUILD_FILTER):
        sys.stderr.write("fake az: unsupported policy query " + query + "\n")
        sys.exit(2)
    rows = [
        p for p in state["policies"]
        if p["configuration"]["isBlocking"] and p["configuration"]["isEnabled"]
        and p["configuration"]["type"]["displayName"] == "Build"
    ]
    tail = query[len(BUILD_FILTER):]
    if not tail.startswith("."):
        sys.stderr.write("fake az: unsupported projection " + tail + "\n")
        sys.exit(2)
    result = [fields(p, tail[1:]) for p in rows]
elif sub == "pipelines build show":
    result = fields(state["builds"][opts["--id"]], query)
else:
    sys.stderr.write("fake az: unsupported command " + sub + "\n")
    sys.exit(2)


def dump_obj(v):
    if isinstance(v, list):
        return str(len(v))
    if isinstance(v, dict):
        return ""
    return v if isinstance(v, str) else str(v)


if result is not None:
    for item in (result if isinstance(result, list) else [result]):
        if isinstance(item, list):
            line = "\t".join(dump_obj(v) for v in item)
        elif isinstance(item, bool):
            line = str(item).lower()
        else:
            line = dump_obj(item)
        sys.stdout.write(line + "\n")
"""

_MERGE = "abc123"
_BASH = shutil.which("bash")
_needs_bash = pytest.mark.skipif(
    _BASH is None or sys.platform == "win32", reason="runs a POSIX bash block"
)


def _bash_block(text: str) -> str:
    """Return the single fenced bash block inside ``text``."""
    blocks = re.findall(r"```bash\n(.*?)\n\s*```", text, re.DOTALL)
    assert len(blocks) == 1, f"expected 1 bash block, got {len(blocks)}"
    return blocks[0]


def _policy(status: str, build_id: int | None, *, blocking: bool = True) -> dict:
    return {
        "status": status,
        "context": {"buildId": build_id},
        "configuration": {
            "isBlocking": blocking,
            "isEnabled": True,
            "type": {"displayName": "Build"},
        },
    }


def _run_block(tmp_path: Path, block: str, state: dict, env_extra: dict | None = None):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "az"
    fake.write_text(f"#!{sys.executable}\n{_FAKE_AZ}", encoding="utf-8")
    fake.chmod(0o755)
    sleeper = bin_dir / "sleep"
    sleeper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleeper.chmod(0o755)
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    script = tmp_path / "block.sh"
    script.write_text(block + "\n", encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "FAKE_AZ_STATE": str(state_path),
        "FAKE_AZ_LOG": str(tmp_path / "az.log"),
        "pr_id": "7",
        **(env_extra or {}),
    }
    return subprocess.run(
        [_BASH, str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def _evaluation_block(ship_text: str) -> str:
    pipeline = numbered_item(section(ship_text, "Pre-flight Checks"), "**Pipeline health**")
    return _bash_block(ado_item_block(pipeline, "`pr=#<number>`"))


@pytest.fixture(params=[COMMAND_PATH, COMMAND_MIRROR_PATH], ids=["claude", "copilot"])
def wait_text(request: pytest.FixtureRequest) -> str:
    return (Path(request.param).parent / WAIT_REFERENCE).read_text(encoding="utf-8")


def _wait_block(wait_text: str) -> str:
    return _bash_block(wait_text)


def _state(policies: list[dict], builds: dict | None = None, fail: list[str] | None = None):
    return {
        "pr": {"lastMergeCommit": {"commitId": _MERGE}},
        "policies": policies,
        "builds": builds or {},
        "fail": fail or [],
    }


_GREEN = {"42": {"result": "succeeded", "sourceVersion": _MERGE}}


@_needs_bash
class TestAdoEvaluationBehavior:
    """Run the pre-flight check 1 ADO evaluation against fake `az` output."""

    def test_green_build_on_merge_commit_passes(self, ship_text: str, tmp_path: Path) -> None:
        """A build show query that prints one value per line must still pass (PR #6610)."""
        run = _run_block(
            tmp_path, _evaluation_block(ship_text), _state([_policy("approved", 42)], _GREEN)
        )
        assert run.returncode == 0, run.stderr

    def test_build_from_older_push_fails(self, ship_text: str, tmp_path: Path) -> None:
        builds = {"42": {"result": "succeeded", "sourceVersion": "old999"}}
        run = _run_block(
            tmp_path, _evaluation_block(ship_text), _state([_policy("approved", 42)], builds)
        )
        assert run.returncode == 1
        assert "old999" in run.stderr

    def test_failed_build_fails(self, ship_text: str, tmp_path: Path) -> None:
        builds = {"42": {"result": "failed", "sourceVersion": _MERGE}}
        run = _run_block(
            tmp_path, _evaluation_block(ship_text), _state([_policy("approved", 42)], builds)
        )
        assert run.returncode == 1

    def test_rejected_policy_fails(self, ship_text: str, tmp_path: Path) -> None:
        run = _run_block(
            tmp_path, _evaluation_block(ship_text), _state([_policy("rejected", 42)], _GREEN)
        )
        assert run.returncode == 1

    def test_not_applicable_policy_is_skipped(self, ship_text: str, tmp_path: Path) -> None:
        """A path-filtered blocking build reports notApplicable and must not block."""
        state = _state([_policy("notApplicable", None), _policy("approved", 42)], _GREEN)
        run = _run_block(tmp_path, _evaluation_block(ship_text), state)
        assert run.returncode == 0, run.stderr

    def test_only_not_applicable_policies_fail(self, ship_text: str, tmp_path: Path) -> None:
        """Inverse guard: skipping notApplicable must not pass a PR with no applied build."""
        run = _run_block(
            tmp_path, _evaluation_block(ship_text), _state([_policy("notApplicable", None)])
        )
        assert run.returncode == 1
        assert "no blocking build policy" in run.stderr.lower()

    def test_no_evaluations_fail(self, ship_text: str, tmp_path: Path) -> None:
        run = _run_block(tmp_path, _evaluation_block(ship_text), _state([]))
        assert run.returncode == 1

    def test_non_blocking_policy_is_ignored(self, ship_text: str, tmp_path: Path) -> None:
        state = _state([_policy("approved", 42, blocking=False)], _GREEN)
        run = _run_block(tmp_path, _evaluation_block(ship_text), state)
        assert run.returncode == 1

    def test_approved_without_build_id_fails(self, ship_text: str, tmp_path: Path) -> None:
        """A null buildId prints as the string None in az TSV output."""
        run = _run_block(
            tmp_path, _evaluation_block(ship_text), _state([_policy("approved", None)])
        )
        assert run.returncode == 1

    @pytest.mark.parametrize(
        "failing", ["repos pr show", "repos pr policy list", "pipelines build show"]
    )
    def test_az_failure_exits_3(self, ship_text: str, tmp_path: Path, failing: str) -> None:
        state = _state([_policy("approved", 42)], _GREEN, fail=[failing])
        run = _run_block(tmp_path, _evaluation_block(ship_text), state)
        assert run.returncode == 3, run.stderr


@_needs_bash
class TestAdoWaitBehavior:
    """Run the Process step 4 ADO wait loop against fake `az` output."""

    def test_reference_queries_blocking_build_policies(self, wait_text: str) -> None:
        block = _wait_block(wait_text)
        assert "az repos pr policy list" in block
        assert "isBlocking" in block
        assert "|| exit 3" in block

    def test_reference_documents_rerun_and_manual_trigger(self, wait_text: str) -> None:
        assert "| 75 |" in wait_text
        assert "az repos pr policy queue" in wait_text

    def test_settled_policies_end_the_wait(self, wait_text: str, tmp_path: Path) -> None:
        state = _state([_policy("approved", 42), _policy("rejected", 43)])
        run = _run_block(
            tmp_path, _wait_block(wait_text), state, {"ADO_WAIT_DEADLINE": "9999999999"}
        )
        assert run.returncode == 0, run.stderr

    def test_missing_evaluations_keep_waiting(self, wait_text: str, tmp_path: Path) -> None:
        """Right after creation ADO may list no evaluation yet; that is not settled."""
        run = _run_block(tmp_path, _wait_block(wait_text), _state([]), {"ADO_WAIT_DEADLINE": "1"})
        assert run.returncode == 1
        assert "30 minutes" in run.stderr

    def test_pending_policy_times_out(self, wait_text: str, tmp_path: Path) -> None:
        run = _run_block(
            tmp_path,
            _wait_block(wait_text),
            _state([_policy("queued", 42)]),
            {"ADO_WAIT_DEADLINE": "1"},
        )
        assert run.returncode == 1

    def test_one_call_stays_under_the_tool_cap(self, wait_text: str, tmp_path: Path) -> None:
        """A single call returns 75 before a 10 minute tool cap; the agent re-runs it."""
        state = _state([_policy("running", 42)])
        clock = tmp_path / "bin" / "date"
        clock.parent.mkdir(exist_ok=True)
        counter = tmp_path / "clock"
        counter.write_text("1000", encoding="utf-8")
        clock.write_text(
            f"#!/bin/sh\nn=$(cat {counter}); echo $((n + 60)) > {counter}; echo $n\n",
            encoding="utf-8",
        )
        clock.chmod(0o755)
        run = _run_block(tmp_path, _wait_block(wait_text), state, {"ADO_WAIT_DEADLINE": "99999"})
        assert run.returncode == 75, run.stderr
        assert int(counter.read_text(encoding="utf-8")) - 1000 < 600 + 120

    def test_az_failure_exits_3(self, wait_text: str, tmp_path: Path) -> None:
        state = _state([], fail=["repos pr policy list"])
        run = _run_block(
            tmp_path, _wait_block(wait_text), state, {"ADO_WAIT_DEADLINE": "9999999999"}
        )
        assert run.returncode == 3

    def test_missing_deadline_is_a_config_error(self, wait_text: str, tmp_path: Path) -> None:
        run = _run_block(tmp_path, _wait_block(wait_text), _state([_policy("approved", 42)]))
        assert run.returncode != 0
        assert "ADO_WAIT_DEADLINE" in run.stderr


class TestAdoProcessWording:
    def test_push_precedes_ado_pr_create(self, ship_text: str) -> None:
        process = section(ship_text, "Process")
        ado = next(ln for ln in process.splitlines() if "`mode=owner`, `host=ado`" in ln)
        assert ado.lower().index("push the branch") < ado.index("az repos pr create")

    def test_discharge_explains_validator_scope(self, ship_text: str) -> None:
        discharge = numbered_item(section(ship_text, "Process"), "Discharge a deferred")
        assert "host-aware only for ADO" not in discharge
        assert "Azure DevOps pipelines" in discharge
