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

_REPO_ROOT = Path(__file__).resolve().parents[2]

_API_TARGET = _REPO_ROOT / "scripts" / "github_core" / "api.py"
_RATE_TARGET = _REPO_ROOT / "scripts" / "github_core" / "rate_limit.py"
_NEW_PR_TARGET = _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py"

_API_TESTS = ["tests/test_github_core.py"]
_RATE_TESTS = ["tests/test_test_rate_limit.py"]
_NEW_PR_TESTS = ["tests/test_new_pr.py"]


def _clear_pycache() -> None:
    result = subprocess.run(
        ["find", ".", "-name", "__pycache__", "-type", "d"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    for d in result.stdout.splitlines():
        subprocess.run(["rm", "-rf", d], cwd=_REPO_ROOT)


def _run_tests(test_paths: list[str]) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *test_paths, "-x", "-q"],
        cwd=_REPO_ROOT,
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
    target: Path,
    test_paths: list[str],
    label: str,
    old: bytes,
    new: bytes,
    *,
    must_die: bool = True,
) -> None:
    original = target.read_bytes()
    mutated, status = _apply_mutant(original, old, new)
    if status != "OK":
        print(f"  [{label}] {status}")
        if must_die:
            raise SystemExit(f"DID-NOT-APPLY: {label}")
        return

    target.write_bytes(mutated)
    _clear_pycache()

    rc = _run_tests(test_paths)

    target.write_bytes(original)
    _clear_pycache()

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


def main() -> None:
    print("=== Mutation harness: #4324 _resolve_validation_base ===")

    # Mutant 1: remove the remote-ref check (fallback to bare base always)
    run_mutant(
        _NEW_PR_TARGET,
        _NEW_PR_TESTS,
        "#4324: remove origin/ prefix from candidate",
        b'    candidate = f"origin/{base}"',
        b'    candidate = base',
    )

    # Mutant 2: remove the returncode check (always use bare base)
    run_mutant(
        _NEW_PR_TARGET,
        _NEW_PR_TESTS,
        "#4324: return base always instead of checking returncode",
        b"    if result.returncode == 0:\n        return candidate\n    return base",
        b"    return base",
    )

    # Inverted control: removing an unrelated comment must NOT kill the suite
    run_mutant(
        _NEW_PR_TARGET,
        _NEW_PR_TESTS,
        "#4324: inverted control (remove a comment, must survive)",
        b"    # Get current branch if head not specified\n",
        b"",
        must_die=False,
    )

    print()
    print("=== Mutation harness: #4326 _TRANSIENT_403_PATTERN ===")

    # Mutant 3: remove 403 from pattern (reverts to pre-fix behavior)
    run_mutant(
        _API_TARGET,
        _API_TESTS,
        "#4326: remove 403 match arm from pattern",
        b"    r\"(?:\"\n"
        b"    r\"\\(?\\bHTTP\\s+403\\b.*?(?:rate.limit|API rate)\"\n"
        b"    r\"|\"\n"
        b"    r\"(?:rate.limit|API rate).*?\\(?\\bHTTP\\s+403\\b\"\n"
        b"    r\")\",",
        b"    r\"\\bNEVER_MATCH_XYZ_PLACEHOLDER\\b\",",
    )

    # Mutant 4: remove the 403 check from _is_transient_graphql_error
    run_mutant(
        _API_TARGET,
        _API_TESTS,
        "#4326: remove 403 check from _is_transient_graphql_error",
        b"        or _TRANSIENT_403_PATTERN.search(error_msg) is not None\n",
        b"",
    )

    print()
    print("=== Mutation harness: #4333 get_pr_metadata REST ===")

    _BUILD_AI_TARGET = _REPO_ROOT / "scripts" / "ci" / "build_ai_review_context.py"
    _BUILD_AI_TESTS = ["tests/test_build_ai_review_context.py"]

    # Mutant 5: change REST path to wrong endpoint (should fail extraction)
    run_mutant(
        _BUILD_AI_TARGET,
        _BUILD_AI_TESTS,
        "#4333: change REST endpoint path to wrong value",
        b'    result = run_gh(["api", f"repos/{repository}/pulls/{pr_number}"])',
        b'    result = run_gh(["api", f"repos/{repository}/issues/{pr_number}"])',
    )

    # Mutant 6: return wrong field for title
    run_mutant(
        _BUILD_AI_TARGET,
        _BUILD_AI_TESTS,
        "#4333: return body field as title",
        b'    title = sanitize_title(str(data.get("title") or ""))',
        b'    title = sanitize_title(str(data.get("body") or ""))',
    )

    print()
    print("All mutants accounted for.")


if __name__ == "__main__":
    main()
