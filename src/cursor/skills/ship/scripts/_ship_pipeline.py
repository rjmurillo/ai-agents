"""Read a PR's pipeline state for the ship preflight: GitHub checks or Azure DevOps policies.

``check_pipeline`` returns one ``Check`` named ``pipeline`` with a state of
PASS, FAIL, PENDING, or DEFERRED, or a ``Halt`` when a query fails. It never
changes the PR. ``ship_preflight.py`` owns the deadline and the terminal line.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import _ship_common as common
    import ship_detect as detect_mod
    from ship_detect import Context, Halt
else:
    common = sys.modules["_ship_common"]
    detect_mod = common.load_sibling("ship_detect")
    # One Halt type across the ship scripts, so a detect-side halt reads as a halt here.
    Halt = detect_mod.Halt

POLL_SECONDS = 30
CHECKS_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.state in ("FAIL", "dirty")


def _github_head(ctx: Context, pr: int) -> tuple[str, str] | Halt:
    done = common.run(
        ["gh", "pr", "view", str(pr), "--json", "headRefName,headRefOid"], cwd=ctx.root
    )
    if done.returncode != 0:
        return detect_mod.query_halt("checks-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict) or not data.get("headRefName") or not data.get("headRefOid"):
        return Halt("checks-query-failed", common.EXIT_EXTERNAL, f"PR {pr} head did not parse")
    return str(data["headRefName"]), str(data["headRefOid"])


def _binding(ctx: Context, pr: int, branch: str, sha: str, after_publish: bool) -> Check | None:
    """Return a non-PASS check when PR ``pr`` does not carry this branch at HEAD."""
    if branch != ctx.branch:
        return Check("pipeline", "FAIL", f"pr={pr} head branch {branch} is not {ctx.branch}")
    if sha != ctx.head:
        detail = f"pr={pr} head {sha[:12]} is not HEAD {ctx.head[:12]}"
        if after_publish:
            return Check("pipeline", "PENDING", detail + "; host has not seen the push yet")
        return Check("pipeline", "DEFERRED", detail + "; checks run after publish")
    return None


def _read_github_checks(
    ctx: Context, pr: int, wait_seconds: int
) -> tuple[int, dict[str, Any]] | Check | Halt:
    """Run get_pr_checks.py once; return (exit code, Data), a PENDING check, or a Halt.

    It waits at most ``min(wait_seconds, CHECKS_TIMEOUT_SECONDS)``. Zero reads once.
    """
    budget = max(0, min(wait_seconds, CHECKS_TIMEOUT_SECONDS))
    helper = common.skill_script("github", "pr", "get_pr_checks.py")
    if not helper.is_file():
        return Halt("checks-query-failed", common.EXIT_CONFIG, "get_pr_checks.py not found")
    argv = [
        sys.executable,
        "-I",
        str(helper),
        "--pull-request",
        str(pr),
        *(["--wait", "--timeout-seconds", str(budget)] if budget else []),
        "--required-only",
        "--output-format",
        "json",
    ]
    done = common.run(argv, cwd=ctx.root, timeout=budget + 60)
    if done.returncode == 4:
        return Halt("auth-failed", common.EXIT_AUTH, "check query was not authorized")
    lines = done.stdout.strip().splitlines()
    envelope = common.parse_json(lines[-1]) if lines else None
    data = envelope.get("Data") if isinstance(envelope, dict) else None
    if done.returncode == 7:
        # Exit 7 is a timeout or an incomplete rollup, and it can still carry a
        # failed required check, so the Data decides when it parses.
        if isinstance(data, dict):
            return 7, data
        return Check("pipeline", "PENDING", f"pr={pr} required checks still running")
    if not isinstance(data, dict) or done.returncode not in (0, 1):
        error = envelope.get("Error") if isinstance(envelope, dict) else None
        message = error.get("Message") if isinstance(error, dict) else None
        reason = message or common.cause_line(done.stderr, "")
        detail = f"get_pr_checks exit {done.returncode}" + (f": {reason}" if reason else "")
        return Halt("checks-query-failed", common.EXIT_EXTERNAL, detail)
    return done.returncode, data


def _github_verdict(ctx: Context, pr: int, code: int, data: dict[str, Any]) -> Check:
    """Turn one get_pr_checks.py result into PASS, PENDING, or FAIL. Exit 0 alone is not green."""
    if code == 0 and data.get("RequiredState") == "SUCCESS" and data.get("AllPassing") is True:
        return Check("pipeline", "PASS", f"pr={pr} head={ctx.head[:12]}")
    if (code == 7 or data.get("RequiredState") == "PENDING") and not data.get(
        "FailedRequiredChecks"
    ):
        # Read without waiting, or the wait ended early: still running, not failed.
        pending = _names(data, "pending", ("PendingRequiredChecks",))
        return Check("pipeline", "PENDING", f"pr={pr} required checks still running{pending}")
    detail = f"pr={pr} required={data.get('RequiredState')} all_passing={data.get('AllPassing')}"
    for label, key in (
        ("failed", "FailedRequiredChecks"),
        ("missing", "MissingRequiredChecks"),
        ("pending", "PendingRequiredChecks"),
    ):
        detail += _names(data, label, (key,))
    if data.get("MergeRefUsable") is False:
        # A conflicting branch has no merge ref, so CI cannot run: name that cause.
        detail += f" merge_state={data.get('MergeState')}"
        if data.get("MergeStateWarning"):
            detail += f" ({data.get('MergeStateWarning')})"
    return Check("pipeline", "FAIL", detail)


def _names(data: dict[str, Any], label: str, keys: tuple[str, ...]) -> str:
    """Return `` label=a,b`` for up to 10 check names under the Data keys, or ''."""
    items = [item for key in keys for item in data.get(key) or []][:10]
    names = [str(i.get("Name", i)) if isinstance(i, dict) else str(i) for i in items]
    return f" {label}=" + ",".join(names) if names else ""


def _github_pipeline(ctx: Context, pr: int, after_publish: bool, wait_seconds: int) -> Check | Halt:
    """Read CI only for PR ``pr`` at this branch and HEAD, and re-check the head after."""
    before = _github_head(ctx, pr)
    if isinstance(before, Halt):
        return before
    mismatch = _binding(ctx, pr, *before, after_publish)
    if mismatch is not None:
        return mismatch
    read = _read_github_checks(ctx, pr, wait_seconds)
    if not isinstance(read, tuple):
        return read
    after = _github_head(ctx, pr)
    if isinstance(after, Halt):
        return after
    if after != before:
        return Check("pipeline", "PENDING", f"pr={pr} head moved during the check")
    return _github_verdict(ctx, pr, *read)


def _ado_policy_rows(ctx: Context, pr: int) -> list[dict[str, Any]] | Halt:
    done = common.run(
        [
            "az",
            "repos",
            "pr",
            "policy",
            "list",
            "--id",
            str(pr),
            "--query",
            "[?configuration.isBlocking && configuration.isEnabled && "
            "configuration.type.displayName=='Build'].{status: status, buildId: context.buildId}",
            "--output",
            "json",
        ],
        cwd=ctx.root,
    )
    if done.returncode != 0:
        return detect_mod.query_halt("pipeline-query-failed", done)
    rows = common.parse_json(done.stdout)
    if not isinstance(rows, list):
        return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "policy list did not parse")
    return [
        row
        for row in rows
        if isinstance(row, dict) and row.get("status") not in (None, "", "notApplicable")
    ]


def _ado_state(ctx: Context, pr: int) -> dict[str, Any] | Halt:
    done = common.run(
        [
            "az",
            "repos",
            "pr",
            "show",
            "--id",
            str(pr),
            "--query",
            "{source: sourceRefName, head: lastMergeSourceCommit.commitId, "
            "merge: lastMergeCommit.commitId}",
            "--output",
            "json",
        ],
        cwd=ctx.root,
    )
    if done.returncode != 0:
        return detect_mod.query_halt("pipeline-query-failed", done)
    data = common.parse_json(done.stdout)
    if not isinstance(data, dict):
        return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "pr show did not parse")
    return data


def _ado_evaluate(
    ctx: Context, pr: int, rows: list[dict[str, Any]], state: dict[str, Any]
) -> Check | Halt:
    merge_commit = str(state.get("merge") or "")
    if not merge_commit:
        return Check("pipeline", "FAIL", f"pr={pr} has no merge commit to compare builds against")
    failures = []
    for row in rows:
        status = str(row.get("status"))
        build_id = row.get("buildId")
        if status != "approved" or build_id in (None, "", "None"):
            failures.append(f"policy={status} build={build_id}")
            continue
        build = common.run(
            [
                "az",
                "pipelines",
                "build",
                "show",
                "--id",
                str(build_id),
                "--query",
                "{result: result, sourceVersion: sourceVersion}",
                "--output",
                "json",
            ],
            cwd=ctx.root,
        )
        if build.returncode != 0:
            return detect_mod.query_halt("pipeline-query-failed", build)
        info = common.parse_json(build.stdout)
        if not isinstance(info, dict):
            return Halt("pipeline-query-failed", common.EXIT_EXTERNAL, "build show did not parse")
        if info.get("result") != "succeeded" or info.get("sourceVersion") != merge_commit:
            failures.append(
                f"build={build_id} result={info.get('result')} at={info.get('sourceVersion')}"
            )
    if failures:
        return Check(
            "pipeline", "FAIL", f"pr={pr} merge={merge_commit} " + "; ".join(failures[:10])
        )
    return Check("pipeline", "PASS", f"pr={pr} builds={len(rows)} merge={merge_commit}")


def _ado_moved(ctx: Context, pr: int, state: dict[str, Any]) -> Check | Halt | None:
    """Re-read the PR after a check; PENDING when its head or merge commit moved."""
    again = _ado_state(ctx, pr)
    if isinstance(again, Halt):
        return again
    if again.get("head") != state.get("head"):
        return Check("pipeline", "PENDING", f"pr={pr} head moved during the check")
    if again.get("merge") != state.get("merge"):
        # The builds ran against a newer merge commit: check them again.
        return Check("pipeline", "PENDING", f"pr={pr} merge commit moved during the check")
    return None


def _ado_pipeline(ctx: Context, pr: int, wait_seconds: int, after_publish: bool) -> Check | Halt:
    state = _ado_state(ctx, pr)
    if isinstance(state, Halt):
        return state
    source = str(state.get("source") or "")
    branch = source[len("refs/heads/") :] if source.startswith("refs/heads/") else source
    mismatch = _binding(ctx, pr, branch, str(state.get("head") or ""), after_publish)
    if mismatch is not None:
        return mismatch
    # Leave room for the evaluation calls after the wait, inside the run budget.
    call_end = time.monotonic() + min(wait_seconds, max(0.0, common.remaining_seconds() - 120))
    while True:
        rows = _ado_policy_rows(ctx, pr)
        if isinstance(rows, Halt):
            return rows
        pending = [row for row in rows if row.get("status") in ("queued", "running")]
        if rows and not pending:
            verdict = _ado_evaluate(ctx, pr, rows, state)
            return _ado_moved(ctx, pr, state) or verdict
        if not rows and not after_publish:
            return Check("pipeline", "FAIL", f"pr={pr} has no blocking build policy evaluation")
        remaining = call_end - time.monotonic()
        if remaining <= 0:
            return Check(
                "pipeline", "PENDING", f"pr={pr} {len(pending)} of {len(rows)} queued or running"
            )
        time.sleep(min(POLL_SECONDS, remaining))


def check_pipeline(
    ctx: Context, pr: int | None, wait_seconds: int, after_publish: bool
) -> Check | Halt:
    if pr is None:
        return Check("pipeline", "DEFERRED", "no open PR yet")
    if ctx.host == "github":
        return _github_pipeline(ctx, pr, after_publish, wait_seconds)
    return _ado_pipeline(ctx, pr, wait_seconds, after_publish)
