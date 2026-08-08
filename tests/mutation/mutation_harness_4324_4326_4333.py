"""Mutation harness for issues #4324, #4326, #4333: GitHub API resilience.

Verifies that each load-bearing component is individually detectable by
the test suite.

Rules:
- Count each pattern; exit nonzero with DID-NOT-APPLY when count != 1.
- cmp check: fail if mutated bytes are identical to original.
- Clear __pycache__ after every file write to defeat 1-second bytecode mtime cache.
- Restore byte-identically and assert after every mutant.
- One inverted control that MUST SURVIVE (removing an unrelated comment must not kill).
- Outcomes: DEAD (tests caught it), SURVIVED (tests missed it), DID-NOT-APPLY (pattern absent).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.testing.mutation_workspace import (
    isolated_mutation_worktree,
    purge_bytecode,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

_API_TARGET_REL = Path("scripts") / "github_core" / "api.py"
_NEW_PR_TARGET_REL = (
    Path(".claude") / "skills" / "github" / "scripts" / "pr" / "new_pr.py"
)
_BUILD_AI_TARGET_REL = Path("scripts") / "ci" / "build_ai_review_context.py"
_TARGETS = (_API_TARGET_REL, _NEW_PR_TARGET_REL, _BUILD_AI_TARGET_REL)
_BUILD_AI_TESTS = ["tests/test_build_ai_review_context.py"]

_API_TESTS = [
    "tests/test_github_core.py",
    "tests/test_github_auth_classification.py",
]
_NEW_PR_TESTS = ["tests/test_new_pr.py"]


def _run_tests(repo_root: Path, test_paths: list[str]) -> int:
    purge_bytecode(repo_root)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_paths, "-x", "-q"],
        cwd=repo_root,
        capture_output=True,
    )
    return result.returncode


def _apply_mutant(original: bytes, old: bytes, new: bytes) -> tuple[bytes, str]:
    count = original.count(old)
    if count == 0:
        return original, "DID-NOT-APPLY"
    if count > 1:
        return original, f"PATTERN-AMBIGUOUS ({count} occurrences)"
    mutated = original.replace(old, new, 1)
    if mutated == original:
        return original, "DID-NOT-APPLY (byte-identical)"
    return mutated, "OK"


def run_mutant(
    repo_root: Path,
    target_relative: Path,
    test_paths: list[str],
    label: str,
    old: bytes,
    new: bytes,
    *,
    must_die: bool = True,
) -> None:
    target = repo_root / target_relative
    original = target.read_bytes()
    mutated, status = _apply_mutant(original, old, new)
    if status != "OK":
        print(f"  [{label}] {status}")
        if must_die:
            raise SystemExit(f"DID-NOT-APPLY: {label}")
        return

    try:
        target.write_bytes(mutated)
        rc = _run_tests(repo_root, test_paths)
    finally:
        target.write_bytes(original)

    assert target.read_bytes() == original, f"Restore failed for {label}"

    if must_die:
        if rc == 1:
            print(f"  [{label}] DEAD (rc=1, tests caught the mutant)")
        elif rc == 4:
            raise SystemExit(f"  [{label}] FALSE-KILL: pytest exited 4 (bad path), fix the harness")
        else:
            raise SystemExit(f"  [{label}] SURVIVED (rc={rc}), tests did not catch the mutant")
    else:
        if rc == 0:
            print(f"  [{label}] SURVIVED (inverted control, expected)")
        else:
            raise SystemExit(f"  [{label}] INVERTED CONTROL DIED (rc={rc}), baseline may be broken")


def _run_mutants(repo_root: Path) -> None:
    print("=== Mutation harness: #4324 _resolve_validation_base ===")

    # Mutant 1: remove the remote-ref check (fallback to bare base always)
    run_mutant(
        repo_root,
        _NEW_PR_TARGET_REL,
        _NEW_PR_TESTS,
        "#4324: remove origin/ prefix from candidate",
        b'    remote_ref = f"origin/{pr_base}"',
        b'    remote_ref = pr_base',
    )

    # Mutant 2: remove the returncode check (always use bare base)
    run_mutant(
        repo_root,
        _NEW_PR_TARGET_REL,
        _NEW_PR_TESTS,
        "#4324: return base always instead of checking returncode",
        b"    if result.returncode == 0:\n        return remote_ref\n    return pr_base",
        b"    return pr_base",
    )

    # Inverted control: removing an unrelated comment must NOT kill the suite
    run_mutant(
        repo_root,
        _NEW_PR_TARGET_REL,
        _NEW_PR_TESTS,
        "#4324: inverted control (remove a comment, must survive)",
        b"    # Get current branch if head not specified\n",
        b"",
        must_die=False,
    )

    print()
    print("=== Mutation harness: #4326 _TRANSIENT_403_PATTERN ===")

    # Mutant 3: disable rate-limit wording detection (reverts to pre-fix behavior)
    run_mutant(
        repo_root,
        _API_TARGET_REL,
        _API_TESTS,
        "#4326: disable rate-limit wording signature",
        b'_RATE_LIMIT_SIGNATURE = re.compile(r"rate limit (?:already )?exceeded", re.IGNORECASE)',
        b'_RATE_LIMIT_SIGNATURE = re.compile(r"NEVER_MATCH_XYZ", re.IGNORECASE)',
    )

    # Mutant 4: remove classified rate-limit refusals from transient handling
    run_mutant(
        repo_root,
        _API_TARGET_REL,
        _API_TESTS,
        "#4326: ignore classified retryable refusals",
        b"    return classify_gh_failure_text(error_msg) in _RETRYABLE_REFUSAL_STATUSES\n",
        b"    return False  # mutant: ignore classified retryable refusals\n",
    )

    print()
    print("=== Mutation harness: #4333 get_pr_metadata REST ===")

    # Mutant 5: change REST path to wrong endpoint (should fail extraction)
    run_mutant(
        repo_root,
        _BUILD_AI_TARGET_REL,
        _BUILD_AI_TESTS,
        "#4333: change REST endpoint path to wrong value",
        b'    rest = run_gh(["api", f"repos/{repository}/pulls/{pr_number}"])',
        b'    rest = run_gh(["api", f"repos/{repository}/issues/{pr_number}"])',
    )

    # Mutant 6: return wrong field for title
    run_mutant(
        repo_root,
        _BUILD_AI_TARGET_REL,
        _BUILD_AI_TESTS,
        "#4333: return body field as title",
        b'        title=sanitize_title(str(parsed.get("title") or "")),',
        b'        title=sanitize_title(str(parsed.get("body") or "")),',
    )

    print()
    print("All mutants accounted for.")


def main() -> None:
    with isolated_mutation_worktree(_REPO_ROOT, _TARGETS) as workspace:
        _run_mutants(workspace.root)


if __name__ == "__main__":
    main()
