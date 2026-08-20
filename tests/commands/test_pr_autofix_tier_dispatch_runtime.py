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
read (``.Tier``) the disarm gate spares it; under the pre-fix read
(``.Data.Tier``) the tier pins to ``UNKNOWN``, ``TIER != T1`` holds, and the
gate strips auto-merge from a PR that earned it.
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
if tier == "PRODUCER_FAILURE":
    print("boom", file=sys.stderr)
    raise SystemExit(1)

# Flat dict printed directly, exactly as the real producer does. It carries its
# own top-level Success key and no Data envelope.
print(json.dumps({"Success": True, "Tier": tier, "Ready": False}, indent=2))
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
) -> DispatchRun:
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    _write_fake_scripts(scripts_dir)

    round_cap_log = tmp_path / "round-cap"
    disarm_log = tmp_path / "disarm"
    cleanup_log = tmp_path / "cleanup"

    block = extract_dispatch((REPO_ROOT / doc).read_text(encoding="utf-8"))
    if tier_read != SHIPPED_TIER_READ:
        assert SHIPPED_TIER_READ in block, "shipped tier read not found to mutate"
        block = block.replace(SHIPPED_TIER_READ, tier_read)

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
    return DispatchRun(process, round_cap_log, disarm_log, cleanup_log)


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_t1_with_auto_merge_armed_keeps_it(tmp_path: Path, doc: str) -> None:
    run = run_dispatch(tmp_path, doc, tier="T1", auto_merge="SQUASH")

    assert not run.disarmed, "a T1 PR lost the auto-merge it earned"
    assert not run.round_cap_called, "the round cap fired outside T3/T4"
    assert run.reached_end
    assert run.process.returncode == 0


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
def test_a_producer_failure_pins_the_sentinel_and_the_gates_split(tmp_path: Path, doc: str) -> None:
    """A dead tier producer reproduces the pre-fix behavior, in both directions.

    This is the sentinel asymmetry executed rather than described: the breaker
    goes inert and the disarm gate fires, from one stuck value.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier="PRODUCER_FAILURE",
        auto_merge="SQUASH",
        round_action="ACT",
    )

    assert not run.round_cap_called, "breaker fired on UNKNOWN"
    assert run.disarmed, "disarm gate did not fire on UNKNOWN"


@pytest.mark.parametrize("doc", DISPATCH_DOCS)
def test_the_prefix_read_strips_auto_merge_from_a_t1_pr(tmp_path: Path, doc: str) -> None:
    """Negative control: the defect, restored, on its discriminating input.

    `test_t1_with_auto_merge_armed_keeps_it` above asserts the opposite of this
    against the shipped read. Both run the same block on the same inputs, so
    together they show the fix is what moves the behavior.
    """
    run = run_dispatch(
        tmp_path,
        doc,
        tier="T1",
        auto_merge="SQUASH",
        tier_read=PREFIX_TIER_READ,
    )

    assert run.disarmed, "the pre-fix read no longer reproduces the defect"
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
    env["FAKE_TIER"] = "T2"
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

    assert payload["Tier"] == "T2"
    assert "Data" not in payload, "the fake grew an envelope the real producer does not emit"

    real = (REPO_ROOT / ".claude/skills/github/scripts/pr/test_pr_merge_ready.py").read_text(
        encoding="utf-8"
    )
    assert 'result["Tier"]' in real
    assert "print(json.dumps(result, indent=2))" in real
    assert "write_skill_output" not in real, "the real producer started using the Data emitter"
