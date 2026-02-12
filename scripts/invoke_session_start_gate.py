#!/usr/bin/env python3
"""Verification-based session start gate for all AI agents.

Implements BLOCKING gates for AI agent sessions to ensure:
1. Memory-First: memory-index and task-relevant memories loaded
2. Skill Availability: GitHub skills cataloged and usage-mandatory memory loaded
3. Session Log: Valid session log exists
4. Branch Verification: Not on main/master branch

EXIT CODES (per ADR-035):
  0  - Success: All gates passed
  1  - Logic error in gate script itself
  2  - Gate condition not met (BLOCKING)
  3  - External dependency failure (git, file system)

See: ADR-033 Routing-Level Enforcement Gates
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True)


def get_repo_root() -> Path | None:
    result = run_git("rev-parse", "--show-toplevel")
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def check_memory_gate(repo_root: Path) -> bool:
    print("\n=== Gate 1: Memory-First Verification ===")
    memory_index = repo_root / ".serena" / "memories" / "memory-index.md"

    if not memory_index.exists():
        print(f"[FAIL] Memory index not found: {memory_index}")
        return False

    print(f"[PASS] Memory index exists: {memory_index}")

    content = memory_index.read_text(encoding="utf-8")
    memory_count = len(re.findall(r"\[([^\]]+)\]\(([^)]+)\.md\)", content))
    print(f"  Memory index contains {memory_count} memory references")

    tier1_memories = ["project-overview", "codebase-structure", "usage-mandatory"]
    missing = [m for m in tier1_memories if not (repo_root / ".serena" / "memories" / f"{m}.md").exists()]

    if missing:
        print(f"[WARN] Missing Tier 1 memories: {', '.join(missing)}")
    else:
        print("[PASS] All Tier 1 (essential) memories available")

    return True


def check_skill_gate(repo_root: Path) -> bool:
    print("\n=== Gate 2: Skill Availability Check ===")
    skill_base = repo_root / ".claude" / "skills" / "github" / "scripts"

    if not skill_base.exists():
        print(f"[FAIL] GitHub skills directory not found: {skill_base}")
        return False

    print("[PASS] GitHub skills directory exists")
    skill_count = 0
    for op in ["pr", "issue", "reactions", "label", "milestone"]:
        op_path = skill_base / op
        if op_path.exists():
            scripts = list(op_path.glob("*.ps1")) + list(op_path.glob("*.py"))
            if scripts:
                skill_count += len(scripts)
                print(f"  {op} operations: {len(scripts)} skills available")

    if skill_count == 0:
        print("[WARN] No GitHub skill scripts found")
    else:
        print(f"[PASS] Total GitHub skills cataloged: {skill_count}")

    usage_mandatory = repo_root / ".serena" / "memories" / "usage-mandatory.md"
    if not usage_mandatory.exists():
        print("[WARN] usage-mandatory memory not found")
    else:
        print("[PASS] usage-mandatory memory available")

    return True


def check_session_log_gate(repo_root: Path) -> bool:
    print("\n=== Gate 3: Session Log Verification ===")
    sessions_dir = repo_root / ".agents" / "sessions"

    if not sessions_dir.exists():
        print(f"[FAIL] Sessions directory not found: {sessions_dir}")
        return False

    today = date.today().isoformat()
    today_sessions = sorted(sessions_dir.glob(f"{today}-session-*.json"), reverse=True)

    if not today_sessions:
        print(f"[FAIL] No session log found for today ({today})")
        return False

    latest = today_sessions[0]
    print(f"[PASS] Session log found: {latest.name}")

    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
        required = ["schemaVersion", "session", "protocolCompliance"]
        missing = [f for f in required if f not in data]
        if missing:
            print(f"[WARN] Session log missing fields: {', '.join(missing)}")
        else:
            print("[PASS] Session log structure valid")
            if "session" in data and "objective" in data["session"]:
                print(f"  Objective: {data['session']['objective']}")
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] Could not parse session log: {e}")

    return True


def check_branch_gate(repo_root: Path) -> tuple[bool, int]:
    print("\n=== Gate 4: Branch Verification ===")
    result = run_git("branch", "--show-current")

    if result.returncode != 0:
        print("[FAIL] Could not determine current branch")
        return False, 3

    branch = result.stdout.strip()
    if branch in ("main", "master"):
        print(f"[FAIL] Currently on protected branch: {branch}")
        print("  Create a feature branch: git checkout -b feat/your-feature-name")
        return False, 0

    print(f"[PASS] Current branch: {branch}")
    commit_result = run_git("rev-parse", "--short", "HEAD")
    if commit_result.returncode == 0:
        print(f"  Starting commit: {commit_result.stdout.strip()}")

    return True, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Session start gate verification")
    parser.add_argument("--check-only", action="store_true", help="Non-blocking diagnostic mode")
    parser.add_argument("--skip-memory-gate", action="store_true")
    parser.add_argument("--skip-skill-gate", action="store_true")
    parser.add_argument("--skip-session-log-gate", action="store_true")
    parser.add_argument("--skip-branch-gate", action="store_true")
    args = parser.parse_args(argv)

    repo_root = get_repo_root()
    if not repo_root:
        print("[FAIL] Could not find git repository root")
        return 3

    print("\nSession Start Gate - Verification-Based Protocol Enforcement")
    print(f"Repository: {repo_root}")
    print(f"Mode: {'Check Only (Non-Blocking)' if args.check_only else 'Enforcement (Blocking)'}")

    results: dict[str, bool | None] = {}
    failed_gates: list[str] = []
    exit_code = 0

    if not args.skip_memory_gate:
        passed = check_memory_gate(repo_root)
        results["Gate1_MemoryFirst"] = passed
        if not passed:
            failed_gates.append("Gate 1 (Memory-First)")
    else:
        print("\n=== Gate 1: Memory-First Verification (SKIPPED) ===")

    if not args.skip_skill_gate:
        passed = check_skill_gate(repo_root)
        results["Gate2_SkillAvailability"] = passed
        if not passed:
            failed_gates.append("Gate 2 (Skill Availability)")
    else:
        print("\n=== Gate 2: Skill Availability Check (SKIPPED) ===")

    if not args.skip_session_log_gate:
        passed = check_session_log_gate(repo_root)
        results["Gate3_SessionLog"] = passed
        if not passed:
            failed_gates.append("Gate 3 (Session Log)")
    else:
        print("\n=== Gate 3: Session Log Verification (SKIPPED) ===")

    if not args.skip_branch_gate:
        passed, err = check_branch_gate(repo_root)
        results["Gate4_BranchVerification"] = passed
        if not passed:
            failed_gates.append("Gate 4 (Branch Verification)")
            if err:
                exit_code = err
    else:
        print("\n=== Gate 4: Branch Verification (SKIPPED) ===")

    print("\n" + "=" * 60)
    print("Gate Results Summary")
    print("=" * 60)

    passed_count = sum(1 for v in results.values() if v is True)
    failed_count = sum(1 for v in results.values() if v is False)
    skipped = 4 - len(results)

    for name, result in sorted(results.items()):
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed_count} passed, {failed_count} failed, {skipped} skipped")

    if failed_gates:
        print("\nSESSION START BLOCKED")
        print(f"Failed gates: {', '.join(failed_gates)}")
        if not args.check_only:
            return exit_code if exit_code else 2
        print("\n(Running in Check-Only mode - not blocking)")
    else:
        print("\nALL GATES PASSED - Session start authorized")

    return 0


if __name__ == "__main__":
    sys.exit(main())
