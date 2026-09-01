"""Run every count ratchet from one authoritative registry (issues #4251, #5317).

AGENTS.md names one pre-PR gate, ``scripts/validation/pre_pr.py``. Before this
module existed that gate ran none of the count ratchets; they ran only at
``pre-push``, in the same lefthook group as the full Python test suite. A
contributor whose change raised a ratchet count therefore saw ``pre_pr.py``
pass, pushed, and learned about a 0.21 second failure 674 seconds later.

Running the fast ratchets here converts that 674 second round trip into a
local one. Five of the ratchets are also registered in
``scripts/ci/merge_tree_ratchet_registry.py``: their local baseline check is
subsumed by ``scripts/ci/merge_tree_ratchet_check.py``, which the docstring on
``_verdict_for_move`` in ``count_ratchet.py`` already documents as the real
gate for a merge-tree-backed ratchet. Issue #5441: this module used to ALSO
run each of those five individually before handing them to the merge-tree
check a second time, so a push paid for the same five counts twice inside one
85 second budget and could not finish. This module now runs each of them
exactly once, through ``validate_count_ratchets`` below, which delegates to
``scripts/ci/merge_tree_ratchet_check.py``'s ``_evaluate_merged_tree``, the
same function a ``uv run --frozen`` caller of that script reaches directly
when it is run as its own Lefthook job.

The pre-push hook and pre-PR runner both delegate to this module. Keeping the
ratchet set and command construction here avoids parallel hook jobs
duplicating the registry while preserving early failure before expensive jobs.
"""

from __future__ import annotations

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

from scripts.ci.merge_tree_ratchet_check import (  # noqa: E402
    EXIT_OK as _MERGE_TREE_EXIT_OK,
)
from scripts.ci.merge_tree_ratchet_check import (  # noqa: E402
    _evaluate_merged_tree as _evaluate_merge_tree_backstop,
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
    Ratchet(
        "memory-index-token-ratchet",
        "scripts/ci/memory_index_token_ratchet.py",
        False,
        False,
    ),
)
"""Ratchets with no merge-tree backstop, run individually as before.

The five ratchets registered in ``merge_tree_ratchet_registry.py`` (ruff
count, taste count, type-ignore count, memory-index count, cli exit
contract) are NOT listed here: ``validate_count_ratchets`` below runs each of
them exactly once, through the merge-tree evaluation, instead of running them
here a second time (issue #5441).
"""

_AGGREGATE_TIMEOUT_SECONDS = 60
"""Bounds the two RATCHETS entries; does NOT bound the merge-tree backstop.

Measured 2026-09-01 on a warm checkout (issue #5441): the two remaining
individual entries finish in well under a second, so 60s is generous headroom
for them alone. This deadline is also a pre-check ``_run_merge_tree_backstop``
uses to skip the backstop outright if those two somehow consumed the whole
window, but it is deliberately NOT handed down as the backstop's own deadline.

An earlier version of this fix did hand it down, which put a 60s cap on a
path ``scripts/ci/merge_tree_ratchet_check.py`` measures at ~64s worst case
(the non-fast-forward materialize-and-recount fallback): a 60s cap under a
64s worst case is a guaranteed failure, not headroom, on exactly the branch
this backstop exists to judge (issue #5441 review). The backstop instead runs
under its own internal deadline
(``scripts/ci/merge_tree_ratchet_check.py::_TIMEOUT_SECONDS``, 90s, with that
module's own docstring recording the margin over the 64s measurement), the
same one the standalone ``merge-tree-ratchet`` Lefthook job gets when it runs
that check standalone.
"""


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


def _prepare_base_oid(repo_root: Path) -> tuple[str | None, str | None]:
    """Resolve the base ref once, returning ``(base_ref, base_oid)``.

    Returns ``(None, None)`` on any failure to resolve; both values must be
    checked for None by the same test, so the base ref is reported so the
    merge-tree backstop can also be pointed at it without re-resolving.
    """
    base_ref = _resolve_default_base_ref(repo_root)
    if not base_ref:
        print(
            "[ERROR] count ratchets: base ref could not be resolved; refusing "
            "to invoke a ratchet without an explicit --base-ref.",
            file=sys.stderr,
        )
        return None, None
    base_ref = _normalize_remote_head(repo_root, base_ref)
    if base_ref is None:
        return None, None
    fetch_result = _refresh_remote_base(base_ref, repo_root)
    if fetch_result:
        print(
            f"[ERROR] count ratchets: could not refresh {base_ref} "
            f"({fetch_result}); refusing to evaluate a stale base.",
            file=sys.stderr,
        )
        return None, None
    return base_ref, _resolve_base_oid(repo_root, base_ref)


def _missing_ratchet_scripts(repo_root: Path) -> list[Ratchet]:
    return [r for r in RATCHETS if not (repo_root / r.script).exists()]


def _report_missing_scripts(missing: list[Ratchet]) -> None:
    for ratchet in missing:
        print(
            f"[ERROR] {ratchet.script} absent; the {ratchet.job_name} gate "
            f"cannot run. Hard failure: gating the count is the point of "
            f"registering this ratchet.",
            file=sys.stderr,
        )


def _run_individual_ratchets(
    repo_root: Path, base_oid: str, deadline: float
) -> list[str]:
    """Run every entry in :data:`RATCHETS`; return the job names that failed."""
    failures: list[str] = []
    for ratchet in RATCHETS:
        remaining_seconds = int(deadline - time.monotonic())
        if remaining_seconds <= 0:
            failures.append(ratchet.job_name)
            print(
                f"[FAIL] {ratchet.job_name} not run: aggregate timeout exhausted.",
                file=sys.stderr,
            )
            continue
        cmd = build_command(ratchet, base_oid)
        exit_code, stdout, stderr = _run_subprocess(
            cmd,
            cwd=repo_root,
            timeout=remaining_seconds,
        )
        if exit_code != 0:
            failures.append(ratchet.job_name)
            _print_output(ratchet.job_name, stdout, stderr)
    return failures


def _run_merge_tree_backstop(repo_root: Path, base_ref: str, deadline: float) -> str | None:
    """Run the merge-tree backstop; return its failure label, or None on pass.

    ``deadline`` gates only whether the backstop starts at all: a fast exit if
    the two RATCHETS entries already burned through the whole aggregate
    window. The evaluation call itself gets no ``deadline`` argument, so it
    falls back to its own internal ``_TIMEOUT_SECONDS`` (90s) instead of
    inheriting the tighter 60s aggregate budget, which measures below the
    documented ~64s materialize-and-recount worst case (see
    ``_AGGREGATE_TIMEOUT_SECONDS``'s docstring).
    """
    if time.monotonic() >= deadline:
        print(
            "[FAIL] merge-tree-ratchet not run: aggregate timeout exhausted.",
            file=sys.stderr,
        )
        return "merge-tree-ratchet"
    if _evaluate_merge_tree_backstop(repo_root, base_ref) != _MERGE_TREE_EXIT_OK:
        return "merge-tree-ratchet"
    return None


def validate_count_ratchets(repo_root: Path, *, skip_merge_tree: bool = False) -> bool:
    """Run every ratchet in :data:`RATCHETS`, then the merge-tree backstop.

    ``skip_merge_tree`` lets the ``count-ratchets`` Lefthook job cover only
    the two ratchets with no merge-tree registration and leave the backstop to
    the separate ``merge-tree-ratchet`` job (issue #5441): the two jobs then
    run in Lefthook's ``parallel: true`` group instead of one paying for both
    in series. ``pre_pr_sequence.py`` and a bare ``checks_ratchet.py`` call
    both leave it False and get full coverage in one call, which is also what
    a test asserting the five shared counters run exactly once exercises.

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

    missing = _missing_ratchet_scripts(repo_root)
    if missing:
        _report_missing_scripts(missing)
        return False

    # The merge-tree backstop always needs the base ref; a RATCHETS entry
    # needs it only when it declares uses_base_ref=True. Skipping resolution
    # (and its network fetch) when neither applies matters concretely: the
    # count-ratchets Lefthook job always passes skip_merge_tree=True, and
    # both entries left in RATCHETS after issue #5441 have uses_base_ref=False,
    # so that job used to block on a base-ref refresh failure for a value
    # nothing it runs would consume (issue #5441 review).
    needs_base_ref = not skip_merge_tree or any(r.uses_base_ref for r in RATCHETS)
    base_ref: str | None = None
    base_oid: str | None = None
    if needs_base_ref:
        base_ref, base_oid = _prepare_base_oid(repo_root)
        if base_oid is None or base_ref is None:
            return False

    deadline = time.monotonic() + _AGGREGATE_TIMEOUT_SECONDS
    failures = _run_individual_ratchets(repo_root, base_oid or "", deadline)

    if not skip_merge_tree:
        assert base_ref is not None, "needs_base_ref forces resolution above"
        backstop_failure = _run_merge_tree_backstop(repo_root, base_ref, deadline)
        if backstop_failure is not None:
            failures.append(backstop_failure)

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
    """Run registered ratchets for the current repository.

    ``--skip-merge-tree`` is what the ``count-ratchets`` Lefthook job passes;
    see :func:`validate_count_ratchets`.
    """
    skip_merge_tree = "--skip-merge-tree" in sys.argv[1:]
    try:
        passed = validate_count_ratchets(Path.cwd(), skip_merge_tree=skip_merge_tree)
    except MissingScriptSkip as exc:
        print(f"[ERROR] count ratchets: {exc}", file=sys.stderr)
        return 2
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
