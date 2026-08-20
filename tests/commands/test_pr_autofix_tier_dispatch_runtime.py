"""Runtime tests for the pr-autofix tier-dispatch block.

`tests/commands/test_pr_autofix_field_contract.py` is a static gate: it proves
the `jq` reads name fields their producers emit. It never runs the block, so it
cannot say what the parsed tier makes the shell *do*.

This module runs it. The block between ``# tier-dispatch:start`` and
``# tier-dispatch:end`` is extracted from the shipped command and from its
generated Copilot mirror, then executed under ``bash`` with fake producer
scripts on ``$SCRIPTS_DIR``, following the harness in
``tests/test_pr_autofix_late_live_state_gate.py``.

The discriminating input is a T1 PR with auto-merge armed. Under the shipped
read (``.Tier``) it is dispatched as T1 and keeps the auto-merge it earned;
under the pre-fix read (``.Data.Tier``) the tier resolves to ``UNKNOWN``, which
names no declared tier, so the block skips the PR instead of acting on it.

Before the tier guard landed, that same ``UNKNOWN`` fell through to the disarm
gate, where ``TIER != T1`` holds, and stripped auto-merge from the PR. Copilot
found that fall-through, and an earlier version of this module asserted it as
correct behavior rather than reporting it.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DISPATCH_DOCS = (
    ".claude/commands/pr-autofix.md",
    "src/copilot-cli/skills/pr-autofix/SKILL.md",
)
_START = "# tier-dispatch:start"
_END = "# tier-dispatch:end"

SHIPPED_TIER_READ = "jq -r '.Tier // \"UNKNOWN\"'"
PREFIX_TIER_READ = "jq -r '.Data.Tier // \"UNKNOWN\"'"

# Environment keys GitHub Actions always sets. The block does not read them, but
# inheriting runner-only values is how a test passes locally and fails in CI
# (testing rule SHOULD-12), so drop them unless a case supplies one.
_CI_ONLY_ENV = ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "CI")


def extract_dispatch(text: str) -> str:
    """Return the tier-dispatch block, markers included."""
    start = text.find(_START)
    end = text.find(_END)
    assert start >= 0, f"missing {_START}"
    assert end > start, f"missing {_END}"
    return text[start : end + len(_END)]


def _write_fake_scripts(scripts_dir: Path) -> None:
    (scripts_dir / "test_pr_merge_ready.py").write_text(
        """\
import json
import os
import sys

tier = os.environ["FAKE_TIER"]

# The three ways this producer can fail to name a tier. They do not agree with
# each other downstream, which is the point: without pipefail jq masks the
# failure, and empty stdout leaves TIER empty while a JSON error object leaves
# it UNKNOWN.
if tier == "CRASH":
    print("boom", file=sys.stderr)
    raise SystemExit(1)
if tier == "MALFORMED":
    print("not json at all")
    raise SystemExit(1)
if tier == "ERROR_OBJECT":
    print(json.dumps({"Success": False, "Error": "rate limited"}))
    raise SystemExit(1)

# A not-merge-ready PR exits 1 with a perfectly good tier, so exit status alone
# cannot stand in for tier validity.
print(json.dumps({"Success": True, "Tier": tier, "Ready": False}, indent=2))
raise SystemExit(0 if tier == "T1" else 1)
""",
        encoding="utf-8",
    )
    (scripts_dir / "check_pr_round_cap.py").write_text(
        """\
import json
import os
from pathlib import Path

Path(os.environ["ROUND_CAP_LOG"]).open("a", encoding="utf-8").write("called\\n")
action = os.environ["FAKE_ROUND_ACTION"]
print(json.dumps({
    "Success": True,
    "Data": {"action": action, "reason": "round cap reached"},
}))
""",
        encoding="utf-8",
    )
    (scripts_dir / "get_pr_context.py").write_text(
        """\
import json
import os

if os.environ["FAKE_AUTO_MERGE"] == "UNREADABLE":
    raise SystemExit(1)

method = os.environ["FAKE_AUTO_MERGE"]
payload = None if method == "null" else method
print(json.dumps({"Success": True, "Data": {"auto_merge_method": payload}}))
""",
        encoding="utf-8",
    )
    (scripts_dir / "set_pr_auto_merge.py").write_text(
        """\
import json
import os
from pathlib import Path

Path(os.environ["DISARM_LOG"]).open("a", encoding="utf-8").write("disarmed\\n")
print(json.dumps({"Success": True, "Data": {"disabled": True}}))
""",
        encoding="utf-8",
    )


class DispatchRun:
    """Result of one execution of the tier-dispatch block."""

    def __init__(
        self,
        process: subprocess.CompletedProcess[str],
        round_cap_log: Path,
        disarm_log: Path,
        cleanup_log: Path,
    ) -> None:
        self.process = process
        self.stdout = process.stdout
        self.round_cap_called = round_cap_log.exists()
        self.disarmed = disarm_log.exists()
        self.cleaned_up = cleanup_log.exists()

    @property
    def reached_end(self) -> bool:
        """True when no gate issued `continue` before the block finished."""
        return "reached-post-tier" in self.stdout


def run_dispatch(
    tmp_path: Path,
    doc: str,
    *,
    tier: str,
    auto_merge: str = "null",
    round_action: str = "ACT",
    mutation_rc: str = "",
    tier_read: str = SHIPPED_TIER_READ,
    expected_stderr: str | None = None,
) -> DispatchRun:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    _write_fake_scripts(scripts_dir)

    round_cap_log = tmp_path / "round-cap"
    disarm_log = tmp_path / "disarm"
    cleanup_log = tmp_path / "cleanup"

    block = extract_dispatch((REPO_ROOT / doc).read_text(encoding="utf-8"))
    if tier_read != SHIPPED_TIER_READ:
        # Exactly one, not at least one. A second identical read would make the
        # mutation hit several sites at once, and the negative control would
        # stop isolating the defect it is named for.
        occurrences = block.count(SHIPPED_TIER_READ)
        assert occurrences == 1, f"expected exactly one tier read to mutate, found {occurrences}"
        block = block.replace(SHIPPED_TIER_READ, tier_read, 1)

    harness = f"""\
set -u
SCRIPTS_DIR={shlex.quote(scripts_dir.as_posix())}

cleanup_pr_autofix() {{
    printf 'cleanup\\n' >> "$CLEANUP_LOG"
}}

run_pr_mutation_if_live() {{
    if [ -n "$MUTATION_RC_OVERRIDE" ]; then
        return "$MUTATION_RC_OVERRIDE"
    fi
    "$@"
}}

for PR in 5176; do
{block}
    printf 'reached-post-tier\\n'
done
"""

    env = {k: v for k, v in os.environ.items() if k not in _CI_ONLY_ENV}
    env.update(
        {
            "CLEANUP_LOG": str(cleanup_log),
            "ROUND_CAP_LOG": str(round_cap_log),
            "DISARM_LOG": str(disarm_log),
            "FAKE_TIER": tier,
            "FAKE_AUTO_MERGE": auto_merge,
            "FAKE_ROUND_ACTION": round_action,
            "MUTATION_RC_OVERRIDE": mutation_rc,
        }
    )
    process = subprocess.run(
        ["bash", "-c", harness],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    # Every case asserts this, not just one. A log file that exists or a string
    # in stdout proves a branch ran; it does not prove the block finished, so
    # without this a shell error after the observed effect leaves the case green
    # (testing rule MUST-8). Measured: all nine input shapes exit 0 with empty
    # stderr, including the ones that `continue`. Verified by injecting an unset
    # variable into the harness under `set -u`: 22 of the 22 cases that run the
    # block fail, and only the two that never spawn bash still pass.
    assert process.returncode == 0, (
        f"the extracted block exited {process.returncode}: {process.stderr.strip()}"
    )
    if expected_stderr is None:
        assert process.stderr == "", f"the block wrote to stderr: {process.stderr.strip()}"
    else:
        # Declared per case rather than allowed globally, so an unexpected
        # diagnostic still fails everywhere else. The command redirects the
        # producer's stderr to /dev/null but not jq's, so malformed producer
        # output surfaces a jq parse error to the operator, which is the loud
        # failure we want rather than something to suppress.
        assert expected_stderr in process.stderr, (
            f"expected {expected_stderr!r} on stderr, got: {process.stderr.strip()!r}"
        )
    return DispatchRun(process, round_cap_log, disarm_log, cleanup_log)


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_t1_with_auto_merge_armed_keeps_it(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="SQUASH")

    assert not run.disarmed, "a T1 PR lost the auto-merge it earned"
    assert not run.round_cap_called, "the round cap fired outside T3/T4"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("tier", ["T3", "T4"])
def test_round_cap_runs_for_t3_and_t4(tmp_path: Path, doc: str, tier: str) -> None:
    run = run_dispatch(tmp_path, doc, tier=tier, round_action="ACT")

    assert run.round_cap_called, f"the round-cap breaker stayed inert on {tier}"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_round_cap_escalation_stops_before_the_disarm_gate(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        round_action="ESCALATE",
    )

    assert run.round_cap_called
    assert "Stopping thread-fix loop" in run.stdout
    assert run.cleaned_up
    assert not run.disarmed, "the loop kept acting after the round cap escalated"
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_non_t1_with_auto_merge_armed_is_disarmed(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="SQUASH", round_action="ACT")

    assert run.disarmed
    assert "Auto-merge armed on non-T1 PR" in run.stdout
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_unarmed_pr_is_left_alone(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T3", auto_merge="null", round_action="ACT")

    assert not run.disarmed
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_unreadable_auto_merge_state_skips_instead_of_guessing(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="UNREADABLE")

    assert "Cannot read auto-merge state" in run.stdout
    assert run.cleaned_up
    assert not run.disarmed, "the disarm path fired on no evidence"
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_skipped_mutation_is_not_reported_as_a_failure(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        round_action="ACT",
        mutation_rc="75",
    )

    assert "Failed to disable auto-merge" not in run.stdout
    assert run.cleaned_up
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_a_failed_mutation_is_reported(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T3",
        auto_merge="SQUASH",
        round_action="ACT",
        mutation_rc="1",
    )

    assert "Failed to disable auto-merge" in run.stdout
    assert run.cleaned_up
    assert not run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("failure", ["CRASH", "MALFORMED", "ERROR_OBJECT"])
def test_a_producer_that_names_no_tier_skips_the_pr(tmp_path: Path, doc: str, failure: str) -> None:
    """Fail closed when the tier is unknown, in all three failure shapes.

    An earlier version of this test asserted the opposite and called it the
    sentinel asymmetry: no round cap, auto-merge disarmed. That codified a
    fail-open as correct. Copilot caught it. Without `pipefail` `jq` masks the
    producer's failure, and the shapes do not even agree: a crash or malformed
    output leaves `TIER` empty, a JSON error object leaves it `UNKNOWN`. Both
    skip the T3/T4 breaker *and* satisfy `TIER != T1`, so the loop would strip
    auto-merge from a PR whose tier it never learned and then keep acting on it.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier=failure,
        auto_merge="SQUASH",
        round_action="ACT",
        expected_stderr="jq: parse error" if failure == "MALFORMED" else None,
    )

    assert "Cannot determine tier" in run.stdout
    assert run.cleaned_up
    assert not run.disarmed, "auto-merge was stripped on an unknown tier"
    assert not run.round_cap_called
    assert not run.reached_end, "the loop kept acting without a valid tier"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
@pytest.mark.parametrize("tier", ["T2", "T5", "BEHIND", "BLOCKED", "DIRTY", "SKIP"])
def test_a_valid_tier_exiting_nonzero_is_still_dispatched(
    tmp_path: Path, doc: str, tier: str
) -> None:
    """Every declared tier is dispatched, and exit status is not the discriminator.

    Two things this pins. `test_pr_merge_ready.py` exits 1 for any PR that is
    not merge-ready, so these tiers legitimately arrive with a non-zero status,
    and a guard rejecting exit 1 would skip every PR the loop exists to fix.

    And the set is the producer's `_TIER_ORDER`, not the T1-T5 ladder the
    command's prose describes. BEHIND, BLOCKED, DIRTY, and SKIP are declared
    return values; the guard first shipped rejecting all four, which turned a
    healthy classification into "producer failed" and stopped the documented
    BEHIND and DIRTY handling.
    """
    run = run_dispatch(tmp_path, doc, tier=tier, auto_merge="null")

    assert "Cannot determine tier" not in run.stdout
    assert not run.round_cap_called, "the breaker fired outside T3/T4"
    assert run.reached_end


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_prefix_read_stops_a_t1_pr_from_being_dispatched(tmp_path: Path, doc: str) -> None:
    """Negative control: the defect, restored, on its discriminating input.

    `test_t1_with_auto_merge_armed_keeps_it` above asserts the opposite of this
    against the shipped read. Both run the same block on the same inputs, so
    together they show the fix is what moves the behavior.

    What the pre-fix read does changed once the tier guard landed, and this test
    changed with it rather than being left asserting the old outcome. Before the
    guard, `UNKNOWN` reached the disarm gate and stripped auto-merge from a T1
    PR. Now the guard catches it first and the PR is skipped. Both are wrong for
    a T1 PR, so the control still discriminates; the observable outcome is the
    skip, not the disarm.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T1",
        auto_merge="SQUASH",
        tier_read=PREFIX_TIER_READ,
    )

    assert "Cannot determine tier" in run.stdout, "the pre-fix read no longer reproduces the defect"
    assert not run.reached_end, "a T1 PR was dispatched on a tier the read never resolved"
    assert not run.round_cap_called


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_fake_tier_producer_matches_the_real_output_shape(tmp_path: Path, doc: str) -> None:
    """Guard the fake against drifting from the producer it stands in for.

    A fake that grew a `Data` envelope would make every case above pass under
    the pre-fix read too, and the negative control would stop discriminating.
    """
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    _write_fake_scripts(scripts_dir)

    env = {k: v for k, v in os.environ.items() if k not in _CI_ONLY_ENV}
    env["FAKE_TIER"] = "T1"  # exits 0; the fake mirrors the real not-ready status
    process = subprocess.run(
        ["python3", str(scripts_dir / "test_pr_merge_ready.py")],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        timeout=60,
    )
    payload = json.loads(process.stdout)

    assert payload["Tier"] == "T1"
    assert "Data" not in payload, "the fake grew an envelope the real producer does not emit"

    real = (REPO_ROOT / ".claude/skills/github/scripts/pr/test_pr_merge_ready.py").read_text(
        encoding="utf-8"
    )
    assert 'result["Tier"]' in real
    assert "print(json.dumps(result, indent=2))" in real
    assert "write_skill_output" not in real, "the real producer started using the Data emitter"
