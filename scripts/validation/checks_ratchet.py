"""Run every count ratchet from one authoritative registry (issues #4251, #5317).

AGENTS.md names one pre-PR gate, ``scripts/validation/pre_pr.py``. Before this
module existed that gate ran none of the count ratchets; they ran only at
``pre-push``, in the same lefthook group as the full Python test suite. A
contributor whose change raised a ratchet count therefore saw ``pre_pr.py``
pass, pushed, and learned about a 0.21 second failure 674 seconds later.

The ratchets together finish in about three seconds, so the entire signal
is available long before the suite starts. Running them here converts that
674 second round trip into a local three second one.

The pre-push hook and pre-PR runner both delegate to this module. Keeping the
ratchet set and command construction here avoids eight parallel hook jobs
duplicating the registry while preserving early failure before expensive jobs.
"""

from __future__ import annotations

import concurrent.futures
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _refresh_remote_base,
    _resolve_default_base_ref,
    _run_subprocess,
)


@dataclass(frozen=True)
class Ratchet:
    """One ratchet command and its diagnostic job name.

    Attributes:
        job_name: Stable diagnostic name retained from the former individual
            pre-push job.
        script: Path relative to the repository root.
        extra_dev: True when the job passes ``--extra dev``. The two ruff
            ratchets shell out to a bare ``ruff`` executable, so they need the
            dev extra; running them without it reports "command not found",
            which would be a false failure rather than a real count breach.
        uses_base_ref: True when the job passes ``--base-ref``.
    """

    job_name: str
    script: str
    extra_dev: bool
    uses_base_ref: bool


RATCHETS: tuple[Ratchet, ...] = (
    Ratchet("python-lint-ratchet", "scripts/ci/ruff_ratchet.py", True, False),
    Ratchet("python-lint-count-ratchet", "scripts/ci/ruff_count_ratchet.py", True, True),
    Ratchet("taste-count-ratchet", "scripts/ci/taste_count_ratchet.py", False, True),
    Ratchet(
        "type-ignore-count-ratchet",
        "scripts/ci/type_ignore_count_ratchet.py",
        False,
        True,
    ),
    Ratchet(
        "memory-index-count-ratchet",
        "scripts/ci/memory_index_count_ratchet.py",
        False,
        True,
    ),
    Ratchet(
        "cli-exit-contract-ratchet",
        "scripts/ci/cli_exit_contract_ratchet.py",
        False,
        True,
    ),
    Ratchet(
        "memory-index-token-ratchet",
        "scripts/ci/memory_index_token_ratchet.py",
        False,
        False,
    ),
    Ratchet(
        "merge-tree-ratchet",
        "scripts/ci/merge_tree_ratchet_check.py",
        True,
        True,
    ),
    # Issue #5482. This ratchet was the only one CI ran that no local gate did.
    # Its local twin, check_subprocess_encoding.py, reads
    # `git ls-files scripts/*.py scripts/**/*.py`: 469 of the 2198 tracked
    # Python files. The detector was never the difference, the ratchet imports
    # that module's own find_all_violations and runs it over the whole tree, so
    # 78% of tracked Python could fail CI after passing every local check.
    # Measured on PR #5476: a violation in tests/validation/ passed pre-commit,
    # pre-push and pre_pr, then failed CI at 239 against a baseline of 238.
    Ratchet(
        "subprocess-encoding-count-ratchet",
        "scripts/ci/subprocess_encoding_count_ratchet.py",
        False,
        True,
    ),
)

_AGGREGATE_TIMEOUT_SECONDS = 85


def build_command(ratchet: Ratchet, base_ref: str) -> list[str]:
    """Build the argv for one entry in the aggregate ratchet registry.

    Invoking through ``uv`` rather than :data:`sys.executable` is deliberate.
    The ruff ratchets need the dev extra, which the ambient interpreter running
    ``pre_pr.py`` may not carry, and matching lefthook exactly is what lets the
    registry preserve the former per-job command contract.
    """
    cmd = ["uv", "run", "--frozen"]
    if ratchet.extra_dev:
        cmd += ["--extra", "dev"]
    cmd += ["python", ratchet.script]
    if ratchet.uses_base_ref:
        cmd += ["--base-ref", base_ref]
    return cmd


def _print_output(label: str, stdout: str, stderr: str) -> None:
    """Echo a failing ratchet's output, capped so one gate cannot flood."""
    output = (stdout or "") + (stderr or "")
    if not output.strip():
        return
    print(f"[FAIL] {label} output:")
    for line in output.strip().splitlines()[:60]:
        print(f"  {line}")


def _resolve_base_oid(repo_root: Path, base_ref: str) -> str | None:
    exit_code, stdout, stderr = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{base_ref}^{{commit}}",
        ],
        timeout=10,
    )
    oid = str(stdout).strip()
    if exit_code == 0 and oid:
        return oid
    detail = stderr.strip() or f"git rev-parse exit {exit_code}"
    print(f"[ERROR] count ratchets: cannot pin {base_ref}: {detail}", file=sys.stderr)
    return None


def _normalize_remote_head(repo_root: Path, base_ref: str) -> str | None:
    if base_ref != "refs/remotes/origin/HEAD":
        return base_ref
    exit_code, stdout, stderr = _run_subprocess(
        [
            "git",
            "-C",
            str(repo_root),
            "symbolic-ref",
            "--short",
            base_ref,
        ],
        timeout=10,
    )
    resolved = str(stdout).strip()
    if exit_code == 0 and resolved.startswith("origin/"):
        return resolved
    detail = str(stderr).strip() or f"git symbolic-ref exit {exit_code}"
    print(f"[ERROR] count ratchets: cannot resolve remote HEAD: {detail}", file=sys.stderr)
    return None


def _prepare_base_oid(repo_root: Path) -> str | None:
    base_ref = _resolve_default_base_ref(repo_root)
    if not base_ref:
        print(
            "[ERROR] count ratchets: base ref could not be resolved; refusing "
            "to invoke a ratchet without an explicit --base-ref.",
            file=sys.stderr,
        )
        return None
    base_ref = _normalize_remote_head(repo_root, base_ref)
    if base_ref is None:
        return None
    fetch_result = _refresh_remote_base(base_ref, repo_root)
    if fetch_result:
        print(
            f"[ERROR] count ratchets: could not refresh {base_ref} "
            f"({fetch_result}); refusing to evaluate a stale base.",
            file=sys.stderr,
        )
        return None
    return _resolve_base_oid(repo_root, base_ref)


def _run_ratchets(
    repo_root: Path,
    base_oid: str,
) -> dict[str, tuple[int, str, str]]:
    """Run every ratchet concurrently; return each result by job name.

    Concurrent rather than sequential because the registry's cost is dominated
    by a few entries: measured warm on this tree, merge-tree 22.9s,
    subprocess-encoding 33.7s and cli-exit-contract 15.6s against 0.1s to 2.6s
    for the other six. One shared deadline over a sequential loop spends that
    budget in registry order, so the last entry runs on whatever is left and is
    the one that times out; observed on a cold run, where merge-tree,
    registered last, reported "Command timed out after 33s" and then passed on
    retry with no code change.

    Measured A/B over this registry: 84.2s sequential against an 85 second
    deadline, 51.4s concurrent. Sequential is what made the
    subprocess-encoding entry unshippable, not the entry itself.

    Every registered ratchet only reads: none of the scripts issues a git
    command that writes (`add`, `commit`, `checkout`, `reset`, `read-tree`,
    `update-index`, `stash`, `fetch`), and the one fetch the gate needs happens
    once in `_prepare_base_oid` before this call. So there is no index lock to
    contend over.

    The deadline stays absolute. Each ratchet is given the budget remaining
    when it starts, so a hung entry cannot push the gate past its 90 second
    lefthook timeout, and an entry that never starts is reported as a failure
    rather than silently skipped.
    """
    deadline = time.monotonic() + _AGGREGATE_TIMEOUT_SECONDS
    # Threads, not processes: each worker only waits on a subprocess, so the
    # GIL is released for the whole of it.
    workers = min(len(RATCHETS), os.cpu_count() or 4)
    results: dict[str, tuple[int, str, str]] = {}

    def run_one(ratchet: Ratchet) -> tuple[int, str, str]:
        remaining_seconds = int(deadline - time.monotonic())
        if remaining_seconds <= 0:
            return -1, "", "aggregate timeout exhausted before this ratchet started"
        # Bound before returning: _run_subprocess is untyped to mypy, so
        # returning its result directly reports no-any-return here, where the
        # old tuple-unpacking loop happened to hide it.
        exit_code, stdout, stderr = _run_subprocess(
            build_command(ratchet, base_oid),
            cwd=repo_root,
            timeout=remaining_seconds,
        )
        return exit_code, stdout, stderr

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_one, r): r for r in RATCHETS}
        for future in concurrent.futures.as_completed(futures):
            results[futures[future].job_name] = future.result()
    return results


def validate_count_ratchets(repo_root: Path) -> bool:
    """Run every ratchet in :data:`RATCHETS`; return True when all pass.

    Raises:
        MissingScriptSkip: when ``uv`` is absent. Every ratchet job in
            ``lefthook.yml`` invokes ``uv``, so without it this gate cannot
            reproduce the push-time command. Reporting SKIP states that
            plainly; guessing at a substitute interpreter would report a
            result the push will not honour.
    """
    if shutil.which("uv") is None:
        raise MissingScriptSkip(
            "uv is not on PATH; the count ratchets run via "
            "'uv run --frozen'. Install uv to gate them before pushing."
        )

    missing = [r for r in RATCHETS if not (repo_root / r.script).exists()]
    if missing:
        for ratchet in missing:
            print(
                f"[ERROR] {ratchet.script} absent; the {ratchet.job_name} gate "
                f"cannot run. Hard failure: gating the count is the point of "
                f"registering this ratchet.",
                file=sys.stderr,
            )
        return False

    base_oid = _prepare_base_oid(repo_root)
    if base_oid is None:
        return False

    results = _run_ratchets(repo_root, base_oid)
    failures: list[str] = []
    # Reported in registry order, not completion order, so the output is stable
    # across runs and a diff between two runs shows a real change.
    for ratchet in RATCHETS:
        exit_code, stdout, stderr = results[ratchet.job_name]
        if exit_code != 0:
            failures.append(ratchet.job_name)
            _print_output(ratchet.job_name, stdout, stderr)

    if failures:
        print(
            f"[ERROR] count ratchet(s) failed: {', '.join(failures)}. "
            f"A baseline may only fall; lower the count rather than raising "
            f"the baseline.",
            file=sys.stderr,
        )
        return False
    return True


def main() -> int:
    """Run all registered ratchets for the current repository."""
    try:
        passed = validate_count_ratchets(Path.cwd())
    except MissingScriptSkip as exc:
        print(f"[ERROR] count ratchets: {exc}", file=sys.stderr)
        return 2
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
