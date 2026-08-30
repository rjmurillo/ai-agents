#!/usr/bin/env python3
"""Mutation harness for the pre-PR ratchet parity guard (issue #4251).

Proves each test fails when the defect it guards is reintroduced. A guard that
passes with the bug present delivers nothing, which is the exact failure this
change exists to prevent, so the bar here is absolute.

Restores every mutated file from an in-memory
snapshot in a finally block.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.testing.mutation_workspace import (
    isolated_mutation_worktree,
    purge_bytecode,
)

ROOT = Path(__file__).resolve().parents[2]
SEQ_REL = Path("scripts") / "validation" / "pre_pr_sequence.py"
RAT_REL = Path("scripts") / "validation" / "checks_ratchet.py"
LEFTHOOK_REL = Path("lefthook.yml")
TARGETS = (SEQ_REL, RAT_REL, LEFTHOOK_REL)
TEST = "tests/ci/test_pre_pr_runs_lefthook_ratchets.py"

COUNT_GATE_ROW = """    _Gate(
        "Count Ratchets",
        _root_only(validate_count_ratchets),
        already_run_by="count-ratchets",
    ),
"""
SEQUENCE_TAIL = ")\n\n\ndef run_all_validations("


def run_tests(repo_root: Path, node: str) -> tuple[bool, str]:
    purge_bytecode(repo_root)
    proc = subprocess.run(
        ["uv", "run", "--frozen", "--extra", "dev", "python", "-m", "pytest", node, "-q"],
        capture_output=True,
        encoding="utf-8",
        cwd=repo_root,
        timeout=300,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ANCHOR MISSING in {path.name}: {old[:60]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def apply_m2(sequence: Path) -> None:
    text = sequence.read_text(encoding="utf-8")
    if text.count(COUNT_GATE_ROW) != 1 or text.count(SEQUENCE_TAIL) != 1:
        raise SystemExit("ANCHOR MISSING: count gate row or sequence tail")
    text = text.replace(COUNT_GATE_ROW, "", 1)
    text = text.replace(SEQUENCE_TAIL, COUNT_GATE_ROW + SEQUENCE_TAIL, 1)
    sequence.write_text(text, encoding="utf-8")


def _run_mutants(repo_root: Path) -> int:
    sequence = repo_root / SEQ_REL
    ratchet = repo_root / RAT_REL
    lefthook = repo_root / LEFTHOOK_REL
    mutations = [
        (
            "M1 unwire the gate entirely",
            sequence,
            COUNT_GATE_ROW,
            "",
            f"{TEST}::TestWiredIntoTheSequence",
        ),
        (
            "M2 move the gate to the end of the sequence",
            sequence,
            COUNT_GATE_ROW,
            "",
            f"{TEST}::TestWiredIntoTheSequence::test_gate_runs_second",
        ),
        (
            "M3 drop one ratchet from RATCHETS",
            ratchet,
            '    Ratchet("taste-count-ratchet", '
            '"scripts/ci/taste_count_ratchet.py", False, True),\n',
            "",
            f"{TEST}::TestAggregateLefthookDelegation::test_registry_contains_all_eight_ratchets",
        ),
        (
            "M4 drop --extra dev from the command builder",
            ratchet,
            '        cmd += ["--extra", "dev"]',
            "        pass",
            f"{TEST}::TestAggregateLefthookDelegation::test_command_builder_adds_dev_extra_when_required",
        ),
        (
            "M5 drop --base-ref from the command builder",
            ratchet,
            '        cmd += ["--base-ref", base_ref]',
            "        pass",
            f"{TEST}::TestAggregateLefthookDelegation::test_command_builder_adds_base_ref_when_required",
        ),
        (
            "M6 gate always passes",
            ratchet,
            '    if shutil.which("uv") is None:',
            '    return True\n    if shutil.which("uv") is None:',
            f"{TEST}::TestValidatorBehaviour",
        ),
        (
            "M7 ignore a nonzero ratchet exit",
            ratchet,
            "        if exit_code != 0:",
            "        if False:",
            f"{TEST}::TestValidatorBehaviour::test_fails_when_one_ratchet_exits_nonzero",
        ),
        (
            "M8 unwire the aggregate lefthook job",
            lefthook,
            "          - name: count-ratchets",
            "          - name: phantom-count-ratchets",
            f"{TEST}::TestAggregateLefthookDelegation::test_aggregate_job_exists",
        ),
    ]
    snapshots = {
        path: path.read_text(encoding="utf-8")
        for path in (sequence, ratchet, lefthook)
    }
    results: list[tuple[str, str]] = []
    try:
        ok, out = run_tests(repo_root, TEST)
        if not ok:
            print("NEGATIVE CONTROL FAILED: unmutated suite is red.")
            print(out[-3000:])
            return 1
        print(f"NEGATIVE CONTROL: unmutated suite green. {out.strip().splitlines()[-1]}")

        for label, path, old, new, node in mutations:
            for p, text in snapshots.items():
                p.write_text(text, encoding="utf-8")
            if label.startswith("M2"):
                apply_m2(sequence)
            else:
                mutate(path, old, new)
            ok, out = run_tests(repo_root, node)
            verdict = "SURVIVED (VACUOUS)" if ok else "KILLED"
            tail = out.strip().splitlines()[-1] if out.strip() else ""
            results.append((label, f"{verdict} :: {node.split('::', 1)[-1]} :: {tail}"))
            print(f"{label}: {verdict}")
    finally:
        for p, text in snapshots.items():
            p.write_text(text, encoding="utf-8")
        print("\nRestored all mutated files.")

    print("\n=== SUMMARY ===")
    survived = 0
    for label, detail in results:
        print(f"{label}: {detail}")
        if "SURVIVED" in detail:
            survived += 1
    ok, out = run_tests(repo_root, TEST)
    print(f"\nPost-restore suite green: {ok} :: {out.strip().splitlines()[-1]}")
    return 1 if survived or not ok else 0


def main() -> int:
    with isolated_mutation_worktree(ROOT, TARGETS) as workspace:
        return _run_mutants(workspace.root)


if __name__ == "__main__":
    sys.exit(main())
