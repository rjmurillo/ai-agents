"""Harness that runs `/pr-autofix`'s tier-dispatch block under a real shell.

Refs #5094. Extracts the text between the `# tier-dispatch:start` and `:end`
markers from a shipped document and executes it with `bash`, against fake
producer scripts on `$SCRIPTS_DIR`. Parameterized over the source command and
its generated mirror, so a stale mirror fails.

Three properties here were added only after a mutation proved the earlier
version could not see the defect, and all three are documented at their
definitions: the fake `set_pr_auto_merge.py` records its argument vector rather
than the bare fact of a call, the fake `test_pr_merge_ready.py` does the same so
a dropped `--is-bot` is visible (issue #5208), and the queue walks two PRs so a
per-PR skip is distinguishable from a queue abort.

Split from `test_pr_autofix_tier_dispatch_runtime.py` when it crossed the
500-line taste rule, following the parser precedent in this directory: this
module is the machinery, that one is the cases.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

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
# (testing rule SHOULD-12), so they must never reach the subprocess.
CI_ONLY_ENV = ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "CI")

# The only ambient variables the extracted block is given. Everything else the
# process inherited stays behind.
#
# This was a denylist, `os.environ` minus CI_ONLY_ENV, which is the wrong shape
# for the thing being run: the block is text extracted from a file on the
# branch, executed under `bash -c`, so its contents are whatever the branch
# says. On a CI runner that process was handed the job's `GITHUB_TOKEN`, any
# cloud credentials in scope, and on a developer machine the whole shell
# environment. A branch that edits the command body could read them. CodeRabbit
# reported it; the allowlist is the fix, because a denylist has to predict every
# secret-bearing name and an allowlist only has to name what the harness needs.
#
# What is here and why: `PATH` resolves `bash` and `python3`, `HOME` and
# `TMPDIR` keep the interpreter's own bookkeeping from landing somewhere
# unexpected, and the locale pair keeps its I/O encoding predictable. None
# carries a credential. `SYSTEMROOT` is inert on the platforms that run this
# bash harness and is carried only so the allowlist does not have to change if
# it ever runs somewhere that needs it.
_ENV_ALLOWLIST = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "SYSTEMROOT")

# The SHOULD-12 rule above is now a consequence of the allowlist rather than a
# separate filter, and this keeps that consequence checked instead of assumed.
# Adding a runner-set name to the allowlist fails here at import.
assert not set(CI_ONLY_ENV) & set(_ENV_ALLOWLIST), (
    "an allowlisted variable is also a CI-only variable, so SHOULD-12's "
    "passes-locally-fails-in-CI protection has been reopened"
)


def extract_dispatch(text: str) -> str:
    """Return the tier-dispatch block, markers included."""
    start = text.find(_START)
    end = text.find(_END)
    assert start >= 0, f"missing {_START}"
    assert end > start, f"missing {_END}"
    return text[start : end + len(_END)]


def write_fake_scripts(scripts_dir: Path) -> None:
    (scripts_dir / "test_pr_merge_ready.py").write_text(
        """\
import json
import os
import sys
from pathlib import Path

# Records the argument vector, for the same reason the disarm fake does: the
# bare fact of a call cannot distinguish a run that forwarded --is-bot from one
# that did not, and that flag is the whole of issue #5208. Written before the
# early exits below so a producer failure still records what it was asked for.
Path(os.environ["MERGE_READY_LOG"]).open("a", encoding="utf-8").write(
    "merge-ready " + " ".join(sys.argv[1:]) + "\\n"
)

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
payload = {"Success": True, "Tier": tier, "Ready": False}
# Omitted entirely when the case asks for it, which is the shape a producer
# predating the field would emit. The command must deny the T1 exemption then,
# not assume completeness.
pages = os.environ["FAKE_PAGES_COMPLETE"]
if pages.startswith("RAW:"):
    # A value of the wrong JSON type, so the command's type check is exercised
    # rather than assumed. "RAW:\"true\"" is the string spelling of a boolean,
    # which a bare `tostring` laundered into the real thing.
    payload["fetched_pages_complete"] = json.loads(pages[4:])
elif pages != "OMIT":
    payload["fetched_pages_complete"] = pages == "true"
print(json.dumps(payload, indent=2))
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
data = {"auto_merge_method": payload}

# Same three shapes FAKE_PAGES_COMPLETE uses, and for the same reason: the
# command type-checks this field, so a case has to be able to hand it a wrong
# JSON type and an absent key, not only true and false. "OMIT" is the shape a
# get_pr_context.py predating the field emits (issue #5208).
author = os.environ["FAKE_AUTHOR_IS_BOT"]
if author.startswith("RAW:"):
    data["author_is_bot"] = json.loads(author[4:])
elif author != "OMIT":
    data["author_is_bot"] = author == "true"
print(json.dumps({"Success": True, "Data": data}))
""",
        encoding="utf-8",
    )
    (scripts_dir / "set_pr_auto_merge.py").write_text(
        """\
import json
import os
import sys
from pathlib import Path

# Records the argument vector, not just the fact of an invocation. A fake that
# ignores argv proves a call happened and says nothing about what was asked
# for, so `--disable` could become `--enable` with the whole suite green. That
# mutation was verified to survive before this line existed.
Path(os.environ["DISARM_LOG"]).open("a", encoding="utf-8").write(
    "disarmed " + " ".join(sys.argv[1:]) + "\\n"
)
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
        merge_ready_log: Path,
    ) -> None:
        self.process = process
        self.stdout = process.stdout
        self.round_cap_called = round_cap_log.exists()
        self.disarmed = disarm_log.exists()
        self.cleaned_up = cleanup_log.exists()
        self.disarm_argv = disarm_log.read_text(encoding="utf-8") if self.disarmed else ""
        self.merge_ready_argv = (
            merge_ready_log.read_text(encoding="utf-8") if merge_ready_log.exists() else ""
        )

    @property
    def forwarded_is_bot(self) -> bool:
        """True when every tier-producer call in this run carried `--is-bot`.

        Every call, not any call, because the queue walks two PRs and both get
        the same fake author. A read that returned true on one of two would
        pass a block that forwarded the flag on the first pass and lost it on
        the second, which is a shape a per-PR variable reset produces.
        """
        calls = [line for line in self.merge_ready_argv.splitlines() if line]
        return bool(calls) and all("--is-bot" in line for line in calls)

    @property
    def reached_end(self) -> bool:
        """True when no gate issued `continue` before the block finished."""
        return "reached-post-tier" in self.stdout

    @property
    def queue_completed(self) -> bool:
        """True when the loop walked its whole queue instead of aborting.

        The harness iterates two PRs. With one, `continue`, `break`, and
        `exit 0` are observationally identical to every other accessor here:
        the gate's message is printed, cleanup ran, and the shell exits 0
        because the shared helper requires exactly that. Mutating the SKIP
        arm's `continue` to `break` or `exit 0` was verified to survive the
        whole suite before this property existed.

        This asserts the second PR was *visited*, not that the loop exited
        normally. The first version checked a marker printed after `done`,
        which `break` still reaches, so the `break` mutant survived the very
        fix meant to kill it. That is the same unit-narrower-than-the-claim
        mistake this suite exists to catch, committed while fixing an instance
        of it, and caught only because the control was re-run afterwards.

        The distinction is not cosmetic. Every terminating arm in the block is
        a per-PR skip, so turning one into a queue abort means a single draft
        PR early in the queue silently stops autofix for every PR behind it,
        with the process still exiting 0 for a supervisor to read as success.
        """
        return "visiting 5177" in self.stdout


def run_dispatch(
    tmp_path: Path,
    doc: str,
    *,
    tier: str,
    auto_merge: str = "null",
    round_action: str = "ACT",
    pages_complete: str = "true",
    author_is_bot: str = "false",
    mutation_rc: str = "",
    tier_read: str = SHIPPED_TIER_READ,
    block_edit: tuple[str, str] | None = None,
    expected_stderr: str | None = None,
) -> DispatchRun:
    scripts_dir = tmp_path / "scripts"
    # `parents=True` so a case can hand in a fresh subdirectory of its own
    # `tmp_path` when it runs the block more than once, which the comparison
    # cases do. Without it those cases fail on a missing parent rather than on
    # anything they are testing.
    scripts_dir.mkdir(parents=True)
    write_fake_scripts(scripts_dir)

    round_cap_log = tmp_path / "round-cap"
    disarm_log = tmp_path / "disarm"
    cleanup_log = tmp_path / "cleanup"
    merge_ready_log = tmp_path / "merge-ready"

    block = extract_dispatch((REPO_ROOT / doc).read_text(encoding="utf-8"))
    if tier_read != SHIPPED_TIER_READ:
        # Exactly one, not at least one. A second identical read would make the
        # mutation hit several sites at once, and the negative control would
        # stop isolating the defect it is named for.
        occurrences = block.count(SHIPPED_TIER_READ)
        assert occurrences == 1, f"expected exactly one tier read to mutate, found {occurrences}"
        block = block.replace(SHIPPED_TIER_READ, tier_read, 1)
    if block_edit is not None:
        # Arbitrary edit to the extracted block, used by the in-suite inverted
        # control. Same exactly-one discipline as the tier read: a mutation
        # that lands on several sites is not evidence about any one of them.
        before, after = block_edit
        occurrences = block.count(before)
        assert occurrences == 1, f"expected exactly one {before!r} to edit, found {occurrences}"
        block = block.replace(before, after, 1)

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

for PR in 5176 5177; do
    printf 'visiting %s\\n' "$PR"
{block}
    printf 'reached-post-tier\\n'
done
"""

    env = {k: os.environ[k] for k in _ENV_ALLOWLIST if k in os.environ}
    env.update(
        {
            "CLEANUP_LOG": str(cleanup_log),
            "ROUND_CAP_LOG": str(round_cap_log),
            "DISARM_LOG": str(disarm_log),
            "FAKE_TIER": tier,
            "FAKE_AUTO_MERGE": auto_merge,
            "FAKE_ROUND_ACTION": round_action,
            "FAKE_PAGES_COMPLETE": pages_complete,
            "FAKE_AUTHOR_IS_BOT": author_is_bot,
            "MERGE_READY_LOG": str(merge_ready_log),
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
    # (testing rule MUST-8). Verified by injecting an unset variable into the
    # harness under `set -u`: every case that spawns bash fails, and the only
    # survivors are the fake-shape cases that never spawn it. Stated as that
    # property rather than as a pass count, because the count was written as
    # "22 of the 22" and was 38 of 38 by the time Copilot checked it. A number
    # in a comment goes stale on the commit that adds a case; the property does
    # not, and re-running the injection still checks it.
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
    return DispatchRun(process, round_cap_log, disarm_log, cleanup_log, merge_ready_log)
