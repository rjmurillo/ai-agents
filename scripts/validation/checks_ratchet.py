"""Run the pre-push count ratchets inside the pre-PR gate (issue #4251).

AGENTS.md names one pre-PR gate, ``scripts/validation/pre_pr.py``. Before this
module existed that gate ran none of the count ratchets; they ran only at
``pre-push``, in the same lefthook group as the full Python test suite. A
contributor whose change raised a ratchet count therefore saw ``pre_pr.py``
pass, pushed, and learned about a 0.21 second failure 674 seconds later.

The ratchets together finish in about three seconds, so the entire signal
is available long before the suite starts. Running them here converts that
674 second round trip into a local three second one.

Command shape is copied from ``lefthook.yml``'s ``*-ratchet`` jobs rather than
reinvented, and ``tests/ci/test_pre_pr_runs_lefthook_ratchets.py`` asserts the
two stay identical. Adding a ratchet to ``lefthook.yml`` without adding
it here fails that test, which is the drift this module exists to prevent.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
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
    """One count ratchet, described exactly as ``lefthook.yml`` invokes it.

    Attributes:
        job_name: The ``name`` of the matching ``pre-push`` job in
            ``lefthook.yml``. The parity test keys on this.
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
)


def build_command(ratchet: Ratchet, base_ref: str) -> list[str]:
    """Build the argv for one ratchet, matching its ``lefthook.yml`` job.

    Invoking through ``uv`` rather than :data:`sys.executable` is deliberate.
    The ruff ratchets need the dev extra, which the ambient interpreter running
    ``pre_pr.py`` may not carry, and matching lefthook exactly is what lets the
    parity test compare the two as strings.
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

    base_ref = _resolve_default_base_ref(repo_root)
    if not base_ref:
        print(
            "[ERROR] count ratchets: base ref could not be resolved; refusing "
            "to invoke a ratchet without an explicit --base-ref.",
            file=sys.stderr,
        )
        return False

    # Issue #2453: a stale local origin/<branch> lets a ratchet compare against
    # an old baseline and false-PASS. Best-effort; a failed fetch warns only.
    fetch_result = _refresh_remote_base(base_ref, repo_root)
    if fetch_result:
        print(
            f"[WARN] count ratchets: could not refresh {base_ref} "
            f"({fetch_result}); continuing with the local ref.",
            file=sys.stderr,
        )

    failures: list[str] = []
    for ratchet in RATCHETS:
        cmd = build_command(ratchet, base_ref)
        exit_code, stdout, stderr = _run_subprocess(cmd, cwd=repo_root)
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
