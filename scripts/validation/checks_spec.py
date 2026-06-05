#!/usr/bin/env python3
"""Spec, citation, and catalog gates for the pre-PR runner.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223). Groups the
checks that wrap a sibling ``scripts/validation/`` Python validator covering
spec catalogs, mirror-claim citations, the agent catalog, and the PR-vs-issue
contradiction heuristic.

Behavior-preserving move: each function is identical to its previous definition
in ``pre_pr.py``. ``pre_pr`` re-exports these names so existing imports keep
working.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from checks_common import (  # noqa: E402
    MissingScriptSkip,
    _resolve_branch_base_ref,
    _run_subprocess,
)


def validate_build_gates(repo_root: Path) -> bool:
    """Verify ``.claude/commands/build.md`` still wires the required exit gates.

    The /build command is the implementer's exit path. If a future edit
    removes the code-qualities-assessment / taste-lints / doc-accuracy
    invocations, the iteration paradox documented in PR #1887 returns.
    Lock the contract here. See ``check_build_gates.py`` for the rules.
    """
    script = repo_root / "scripts" / "validation" / "check_build_gates.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/check_build_gates.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_spec_id_uniqueness(repo_root: Path) -> bool:
    """Enforce unique `id:` frontmatter across spec catalog (Issue #2068).

    Duplicate REQ/DESIGN/TASK IDs break traceability and any spec-graph
    tooling that joins by ID. The README under each category already
    documents uniqueness; this gate enforces it.
    """
    script = repo_root / "scripts" / "validation" / "check_spec_id_uniqueness.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/check_spec_id_uniqueness.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_vendor_portability(repo_root: Path) -> bool:
    """Fail when a new skill script hard-codes an upstream-only path (Issue #2050).

    Wraps ``scripts/validation/check_vendor_portability.py``. The script exits 0
    when there are no NEW offenders (baseline-listed debt is allowed) or no scan
    roots are present, 1 when a NEW offender is found, and 2 on a configuration
    error. Exit 1 and 2 are both hard failures here.
    """
    script = repo_root / "scripts" / "validation" / "check_vendor_portability.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/check_vendor_portability.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_sync_registry(repo_root: Path) -> bool:
    """Enforce that every shared lib package is registered for sync (Issue #1909).

    `scripts/sync_plugin_lib.py:SYNC_PAIRS` lists the shared packages copied
    into `.claude/lib/` for plugin distribution. A new lib package added
    without a SYNC_PAIRS entry silently misses the sync and crashes a shimmed
    hook at install time. This gate fails when a package under the source roots
    or under `.claude/lib/` is unregistered.
    """
    script = repo_root / "scripts" / "validation" / "validate_sync_registry.py"
    if not script.exists():
        raise MissingScriptSkip(
            "scripts/validation/validate_sync_registry.py not present"
        )
    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_agent_catalog(repo_root: Path) -> bool:
    """Detect drift between docs/agent-catalog.md and templates/agents/.

    Wraps ``scripts/validation/validate_agent_catalog.py``. The wrapped script
    regenerates the catalog to a buffer and exits 0 when the committed file
    matches, 1 on drift or a missing catalog, 2 on config error, and 3 on a bad
    template. Any non-zero exit is a hard failure: a stale catalog is the exact
    thing this gate exists to catch (Issue #1904).

    Fails closed when the validator is absent rather than raising
    MissingScriptSkip; a silent skip would defeat the gate.
    """
    script = repo_root / "scripts" / "validation" / "validate_agent_catalog.py"
    if not script.exists():
        print(
            "[ERROR] validate_agent_catalog.py absent; the agent-catalog gate "
            "cannot run. Hard failure: the gate is the point of registering "
            "this validator.",
            file=sys.stderr,
        )
        return False
    exit_code, stdout, stderr = _run_subprocess([sys.executable, str(script)])
    output = (stdout or "") + (stderr or "")
    if output.strip():
        for line in output.strip().splitlines()[:40]:
            print(line)
    return exit_code == 0


def validate_canonical_citations(repo_root: Path) -> bool:
    """Heuristic check for uncited mirror-claims.

    Soft-warn by default. Set STRICT_CANONICAL_CHECK=1 in the environment
    to upgrade to a hard failure. Always returns True in soft-warn mode
    so a single uncited claim does not block the PR pipeline.

    See: `.claude/rules/canonical-source-mirror.md` and PR #1887
    retrospective Layer 4.
    """
    script = repo_root / "scripts" / "validation" / "check_canonical_citations.py"
    if not script.exists():
        print("[WARNING] check_canonical_citations.py not found (skipping)")
        return True

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )

    output = stdout.strip()
    if output:
        print(output)
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)

    # Default mode is soft-warn; the script already exits 0 unless
    # STRICT_CANONICAL_CHECK=1 is set. Treat any non-zero exit as a fail
    # so CI can opt into strict mode by setting the env var.
    return exit_code == 0


def validate_orchestrator_citations(repo_root: Path) -> bool:
    """Verify orchestrator prose path citations resolve to real files.

    Wraps ``scripts/validation/check_orchestrator_citations.py``, which fails
    when a backtick path citation in ``.claude/commands/pr-quality/all.md``
    points to a file that no longer exists. A stale citation (e.g. the removed
    ``AIReviewCommon.psm1`` reference fixed in PR #1934) sends the next reader
    to a dead pointer. See Issue #1966.
    """
    script = repo_root / "scripts" / "validation" / "check_orchestrator_citations.py"
    if not script.exists():
        print("[WARNING] check_orchestrator_citations.py not found (skipping)")
        return True

    exit_code, stdout, stderr = _run_subprocess(
        [sys.executable, str(script), "--repo-root", str(repo_root)]
    )
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    return exit_code == 0


def validate_spec_contradiction(repo_root: Path) -> bool:
    """Advisory check for PR-description vs linked-issue vs code contradictions.

    Wraps ``scripts/validation/spec_contradiction.py`` in ``--advisory`` mode,
    so a heuristic false positive never blocks the local pre-PR cycle. The
    script catches the PR #1897 round-7 loop locally (Issue #1894 claimed
    ``model_tier: sonnet`` while the committed agent frontmatter shipped
    ``model: opus``), which CI's "Validate Spec Coverage" gate surfaced only
    after each push. Always returns True; the WARN output is the signal.

    See Issue #1920 and the retrospective at
    ``.agents/retrospective/2026-05-08-pr-1897-confident-incorrectness-recurrence.md``.
    """
    script = repo_root / "scripts" / "validation" / "spec_contradiction.py"
    if not script.exists():
        print("[WARNING] spec_contradiction.py not found (skipping)")
        return True

    base_ref = _resolve_branch_base_ref(repo_root)
    cmd = [
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--advisory",
    ]
    if base_ref:
        cmd.extend(["--base", base_ref])
    exit_code, stdout, stderr = _run_subprocess(cmd)
    if stdout.strip():
        print(stdout.strip())
    if stderr.strip():
        print(stderr.strip(), file=sys.stderr)
    # Advisory: the wrapped script already exits 0 under --advisory, so any
    # non-zero exit here is a config error (e.g. could not resolve repo). Do
    # not block the pre-PR cycle on it; surface the output and pass.
    return True
