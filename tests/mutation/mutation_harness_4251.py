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

ROOT = Path(__file__).resolve().parents[2]
SEQ = ROOT / "scripts" / "validation" / "pre_pr_sequence.py"
RAT = ROOT / "scripts" / "validation" / "checks_ratchet.py"
LEFTHOOK = ROOT / "lefthook.yml"
TEST = "tests/ci/test_pre_pr_runs_lefthook_ratchets.py"

WIRING_BLOCK = """    run_validation(
        "Count Ratchets",
        state,
        lambda: validate_count_ratchets(repo_root),
    )

"""


def run_tests(node: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["uv", "run", "--frozen", "--extra", "dev", "python", "-m", "pytest", node, "-q"],
        capture_output=True,
        encoding="utf-8",
        cwd=ROOT,
        timeout=300,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ANCHOR MISSING in {path.name}: {old[:60]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


MUTATIONS = [
    (
        "M1 unwire the gate entirely",
        SEQ,
        WIRING_BLOCK,
        "",
        f"{TEST}::TestWiredIntoTheSequence",
    ),
    (
        "M2 move the gate to the end of the sequence",
        SEQ,
        WIRING_BLOCK,
        "",
        f"{TEST}::TestWiredIntoTheSequence::test_gate_runs_second",
    ),
    (
        "M3 drop one ratchet from RATCHETS",
        RAT,
        '    Ratchet("taste-count-ratchet", "scripts/ci/taste_count_ratchet.py", False, True),\n',
        "",
        f"{TEST}::TestParityWithLefthook",
    ),
    (
        "M4 drop --extra dev from the command builder",
        RAT,
        '        cmd += ["--extra", "dev"]',
        "        pass",
        f"{TEST}::TestParityWithLefthook::test_commands_match",
    ),
    (
        "M5 drop --base-ref from the command builder",
        RAT,
        '        cmd += ["--base-ref", base_ref]',
        "        pass",
        f"{TEST}::TestParityWithLefthook::test_commands_match",
    ),
    (
        "M6 gate always passes",
        RAT,
        '    if shutil.which("uv") is None:',
        '    return True\n    if shutil.which("uv") is None:',
        f"{TEST}::TestValidatorBehaviour",
    ),
    (
        "M7 ignore a nonzero ratchet exit",
        RAT,
        "        if exit_code != 0:",
        "        if False:",
        f"{TEST}::TestValidatorBehaviour::test_fails_when_one_ratchet_exits_nonzero",
    ),
    (
        "M8 add a fifth ratchet to lefthook only",
        LEFTHOOK,
        "          - name: taste-count-ratchet",
        "          - name: phantom-count-ratchet\n"
        "            run: uv run --frozen python scripts/ci/phantom.py\n\n"
        "          - name: taste-count-ratchet",
        f"{TEST}::TestParityWithLefthook::test_job_names_match",
    ),
]

# M2 needs a different mutation than M1: re-inserting the block at the end.
M2_TAIL_ANCHOR = "def run_all_validations("


def apply_m2() -> None:
    text = SEQ.read_text(encoding="utf-8")
    text = text.replace(WIRING_BLOCK, "", 1)
    # Re-append at the very end of the function body so it still runs, just last.
    text = text.rstrip("\n") + "\n\n" + WIRING_BLOCK.rstrip("\n") + "\n"
    SEQ.write_text(text, encoding="utf-8")


def main() -> int:
    snapshots = {p: p.read_text(encoding="utf-8") for p in (SEQ, RAT, LEFTHOOK)}
    results: list[tuple[str, str]] = []
    try:
        ok, out = run_tests(TEST)
        if not ok:
            print("NEGATIVE CONTROL FAILED: unmutated suite is red.")
            print(out[-3000:])
            return 1
        print(f"NEGATIVE CONTROL: unmutated suite green. {out.strip().splitlines()[-1]}")

        for label, path, old, new, node in MUTATIONS:
            for p, text in snapshots.items():
                p.write_text(text, encoding="utf-8")
            if label.startswith("M2"):
                apply_m2()
            else:
                mutate(path, old, new)
            ok, out = run_tests(node)
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
    ok, out = run_tests(TEST)
    print(f"\nPost-restore suite green: {ok} :: {out.strip().splitlines()[-1]}")
    return 1 if survived or not ok else 0


if __name__ == "__main__":
    sys.exit(main())
