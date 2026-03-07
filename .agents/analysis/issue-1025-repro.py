#!/usr/bin/env python3
"""
Repro case for Issue #1025: Path traversal StartsWith vulnerability

Demonstrates how the current StartsWith check can be bypassed using
prefix-based directory attacks (e.g., /allowed/dir-evil bypasses /allowed/dir)

CWE-22: Improper Limitation of a Pathname to a Restricted Directory
Attack Vector: Directory prefix collision
"""

import os
import sys
from pathlib import Path


def test_vulnerable_code(memories_dir: str, user_input: str) -> dict:
    """Simulates the vulnerable code from templates/agents/security.shared.md:644"""
    memories_dir_full = os.path.abspath(memories_dir)
    output_file = os.path.abspath(os.path.join(memories_dir_full, user_input))

    # VULNERABLE: No directory separator appended
    is_valid = output_file.lower().startswith(memories_dir_full.lower())

    return {
        "memories_dir": memories_dir_full,
        "output_file": output_file,
        "is_valid": is_valid,
    }


def test_fixed_code(memories_dir: str, user_input: str) -> dict:
    """Simulates the FIXED code with directory separator"""
    memories_dir_full = os.path.abspath(memories_dir)
    output_file = os.path.abspath(os.path.join(memories_dir_full, user_input))

    # FIXED: Append directory separator before startswith check
    memories_dir_with_sep = memories_dir_full + os.sep
    is_valid = output_file.lower().startswith(memories_dir_with_sep.lower())

    return {
        "memories_dir": memories_dir_full,
        "memories_dir_with_sep": memories_dir_with_sep,
        "output_file": output_file,
        "is_valid": is_valid,
    }


def main():
    print("=" * 70)
    print("Issue #1025: Path Traversal StartsWith Vulnerability Repro")
    print("=" * 70)
    print()

    # Test cases
    test_cases = [
        {
            "name": "LEGITIMATE: File in allowed directory",
            "memories_dir": "/tmp/memories",
            "user_input": "secret.txt",
            "expected_vulnerable": True,
            "expected_fixed": True,
        },
        {
            "name": "LEGITIMATE: Nested file in allowed directory",
            "memories_dir": "/tmp/memories",
            "user_input": "subdir/secret.txt",
            "expected_vulnerable": True,
            "expected_fixed": True,
        },
        {
            "name": "ATTACK: Prefix-based directory escape",
            "memories_dir": "/tmp/memories",
            "user_input": "../memories-evil/malicious.txt",
            "expected_vulnerable": True,  # BUG: Should be False
            "expected_fixed": False,  # Correctly blocked
        },
        {
            "name": "ATTACK: Adjacent directory with same prefix",
            "memories_dir": "/tmp/allowed",
            "user_input": "../allowed-evil/steal.txt",
            "expected_vulnerable": True,  # BUG: Should be False
            "expected_fixed": False,  # Correctly blocked
        },
        {
            "name": "LEGITIMATE: Path traversal correctly blocked by abspath",
            "memories_dir": "/tmp/memories",
            "user_input": "../../etc/passwd",
            "expected_vulnerable": False,  # abspath resolves .. sequences
            "expected_fixed": False,
        },
    ]

    vulnerable_failures = 0
    fixed_failures = 0
    attack_bypasses = []

    for test in test_cases:
        print()
        print(f"\033[93mTest: {test['name']}\033[0m")
        print("-" * 60)

        # Test vulnerable code
        vuln_result = test_vulnerable_code(test["memories_dir"], test["user_input"])
        vuln_pass = vuln_result["is_valid"] == test["expected_vulnerable"]
        vuln_status = "PASS" if vuln_pass else "FAIL"
        vuln_color = "\033[92m" if vuln_pass else "\033[91m"

        print(f"  Vulnerable Code:")
        print(f"    Base Dir:   {vuln_result['memories_dir']}")
        print(f"    Output:     {vuln_result['output_file']}")
        print(f"    Allowed:    {vuln_result['is_valid']}")
        print(f"    Expected:   {test['expected_vulnerable']}")
        print(f"    Status:     {vuln_color}[{vuln_status}]\033[0m")

        if not vuln_pass:
            vulnerable_failures += 1

        # Check if this is an attack that bypasses the vulnerable code
        if "ATTACK" in test["name"] and vuln_result["is_valid"]:
            attack_bypasses.append(
                {
                    "name": test["name"],
                    "input": test["user_input"],
                    "resolved_to": vuln_result["output_file"],
                    "base_dir": vuln_result["memories_dir"],
                }
            )

        # Test fixed code
        fixed_result = test_fixed_code(test["memories_dir"], test["user_input"])
        fixed_pass = fixed_result["is_valid"] == test["expected_fixed"]
        fixed_status = "PASS" if fixed_pass else "FAIL"
        fixed_color = "\033[92m" if fixed_pass else "\033[91m"

        print(f"  Fixed Code:")
        print(f"    Base Dir:   {fixed_result['memories_dir_with_sep']}")
        print(f"    Output:     {fixed_result['output_file']}")
        print(f"    Allowed:    {fixed_result['is_valid']}")
        print(f"    Expected:   {test['expected_fixed']}")
        print(f"    Status:     {fixed_color}[{fixed_status}]\033[0m")

        if not fixed_pass:
            fixed_failures += 1

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()
    print(
        f"Vulnerable Code: {len(test_cases) - vulnerable_failures}/{len(test_cases)} tests passed"
    )
    print(f"Fixed Code:      {len(test_cases) - fixed_failures}/{len(test_cases)} tests passed")
    print()

    if attack_bypasses:
        print("\033[91mVULNERABILITY CONFIRMED: Attack paths bypass the vulnerable code\033[0m")
        print()
        print("\033[93mAttack Bypasses Detected:\033[0m")
        for bypass in attack_bypasses:
            print(f"  - {bypass['name']}")
            print(f"    Input: {bypass['input']}")
            print(f"    Resolved: {bypass['resolved_to']}")
            print(f"    Base: {bypass['base_dir']}")
            print(
                f"    Why: '{bypass['resolved_to']}' starts with '{bypass['base_dir']}' (string match)"
            )
            print()

        print("\033[93mRoot Cause Analysis:\033[0m")
        print("  1. StartsWith('/tmp/memories') returns True for '/tmp/memories-evil/file.txt'")
        print("  2. The attacker creates a sibling directory with the same prefix")
        print(
            "  3. Using '../memories-evil/file.txt' as input, abspath resolves to '/tmp/memories-evil/file.txt'"
        )
        print(
            "  4. This path starts with '/tmp/memories' (string match) but is OUTSIDE the directory"
        )
        print()
        print("\033[92mFix: Append directory separator before comparison:\033[0m")
        print("  memories_dir_full + os.sep")
        print("  Now startswith('/tmp/memories/') returns FALSE for '/tmp/memories-evil/file.txt'")
        print()
        print("\033[91mVerdict: Issue #1025 is VALID - vulnerability confirmed\033[0m")
        return 1
    else:
        print("\033[92mAll tests passed - vulnerability NOT confirmed\033[0m")
        return 0


if __name__ == "__main__":
    sys.exit(main())
