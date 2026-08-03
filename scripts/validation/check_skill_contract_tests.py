#!/usr/bin/env python3
"""Fail when a skill documents executable contracts that no test binds.

A SKILL.md that names a script, an exit code, and a meaning is writing a
specification. When nothing reads that specification back, the script is free
to drift away from it and every gate stays green: prose does not go red.

This has already happened in this repository. Exit-code semantics for
pr-autofix drifted, were corrected under #2308, and were then re-documented in
prose with nothing recompiling the claim. The next drift is silent for the
same reason the last one was.

A skill is in scope when its SKILL.md documents at least one exit code
alongside a script invocation. Such a skill must be named by at least one file
under tests/ so that a test opens it and asserts against its contents.

The precedent for content-testing markdown is already established here:
tests/validation/test_check_skill_md_exec_portability.py parses SKILL.md files
as test input.

Exit codes:
    0 - every in-scope skill is bound by a test
    1 - at least one unbound skill
    2 - usage or I/O error
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portability_baseline import (
    refuse_oversized_baseline,
    refuse_symlinked_baseline,
    refuse_undiffable_baseline,
)

SCAN_ROOTS = ("src/copilot-cli/skills", ".claude/skills")
TEST_ROOT = "tests"

# Documented exit-code semantics: "exit 0", "exit code 2", "EXIT=100".
EXIT_CODE = re.compile(r"\bexit(?:\s+code)?[\s=]+(\d{1,3})\b", re.IGNORECASE)

# A script invocation the skill tells the agent to run.
SCRIPT_CALL = re.compile(r"\b(?:python3?|bash|sh|pwsh)\s+\S+\.(?:py|sh|ps1)\b")


@dataclass(frozen=True)
class Unbound:
    skill: str
    path: Path
    exit_codes: list[str]

    def render(self) -> str:
        codes = ", ".join(sorted(set(self.exit_codes), key=int))
        return (
            f"{self.path}\n"
            f"    skill '{self.skill}' documents exit codes ({codes}) and script\n"
            f"    invocations, but no file under {TEST_ROOT}/ references it.\n"
            f"    Add a test that reads this SKILL.md and asserts the documented\n"
            f"    contract, so drift fails CI instead of failing silently."
        )


def documented_contracts(path: Path) -> list[str]:
    """Return documented exit codes when the file also invokes a script."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - surfaced to caller
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if not SCRIPT_CALL.search(text):
        return []
    return EXIT_CODE.findall(text)


def test_corpus(repo_root: Path) -> str:
    """Concatenate every test source so skill references can be searched."""
    base = repo_root / TEST_ROOT
    if not base.is_dir():
        return ""
    chunks: list[str] = []
    for suffix in ("*.py", "*.ps1", "*.sh"):
        for test_file in base.rglob(suffix):
            try:
                chunks.append(test_file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root")
    parser.add_argument(
        "--baseline",
        default="scripts/validation/skill_contract_test_baseline.txt",
        help="newline-delimited skill names exempted while the debt is burned down",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()

    skill_files: list[Path] = []
    for scan_root in SCAN_ROOTS:
        base = repo_root / scan_root
        if base.is_dir():
            skill_files.extend(sorted(base.rglob("SKILL.md")))

    if not skill_files:
        # Refuse to pass on a scan that opened nothing.
        print(
            "error: no SKILL.md files found; refusing to report success on an "
            f"empty scan (repo root: {repo_root})",
            file=sys.stderr,
        )
        return 2

    corpus = test_corpus(repo_root)
    if not corpus:
        print(
            f"error: no test sources found under {repo_root / TEST_ROOT}; "
            "refusing to report success",
            file=sys.stderr,
        )
        return 2

    baseline_path = repo_root / args.baseline
    # Refuse a baseline whose diff attribute is unset (issue #4249).
    if refuse_symlinked_baseline(repo_root, baseline_path):
        return 2
    if refuse_undiffable_baseline(repo_root, baseline_path):
        return 2
    if refuse_oversized_baseline(baseline_path):
        return 2
    baseline: set[str] = set()
    if baseline_path.is_file():
        baseline = {
            line.strip()
            for line in baseline_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    unbound: list[Unbound] = []
    in_scope = 0

    for skill_file in skill_files:
        codes = documented_contracts(skill_file)
        if not codes:
            continue
        in_scope += 1
        skill_name = skill_file.parent.name
        if skill_name in baseline:
            continue
        # Match skill name as a whole token: not preceded or followed by
        # characters that form part of a skill identifier (alnum, hyphen, underscore).
        bound = re.search(
            r"(?<![a-zA-Z0-9_-])" + re.escape(skill_name) + r"(?![a-zA-Z0-9_-])",
            corpus,
        )
        if bound:
            continue
        unbound.append(Unbound(skill=skill_name, path=skill_file, exit_codes=codes))

    if unbound:
        print("Skills documenting executable contracts with no binding test:\n")
        for item in unbound:
            print(item.render())
            print()
        print(
            f"{len(unbound)} unbound of {in_scope} in-scope skill(s); "
            f"{len(baseline)} grandfathered."
        )
        return 1

    print(
        f"Skill contract binding OK. {in_scope} in-scope skill(s), "
        f"{len(baseline)} grandfathered."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
