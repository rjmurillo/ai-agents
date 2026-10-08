"""Shared lookups for the vendor-portability gate tests (issues #5670, #6211).

Used by test_pre_pr_covers_vendor_portability.py and the two real-checker files
split from it. The real-checker test runs slow checkers, so issue #6211 spread
its cases over two files to keep xdist ``loadfile`` workers balanced; the map of
expected validators lives here so all three files read one copy.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the pre-PR runner modules the way they are designed to be imported:
# add ``scripts/validation`` to ``sys.path`` and import by bare name. These
# modules self-insert their own directory and use bare intra-package imports
# (issue #2223). Insert once and leave it, matching production; see the longer
# note in test_pre_pr_model_pin_wiring.py for why restoring sys.path breaks the
# function-local imports in checks_tooling.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_portability
import checks_spec

# Not used here. The real checkers run as subprocesses, so no import edge links
# a test to the scripts it exercises. Before issue #6211 the real-checker test
# shared a file with the pre_pr_sequence import, and that import's closure is
# what made test selection pick it when a checker script changed. Importing it
# here keeps that selection for the real-checker files split out of that file.
import pre_pr_sequence  # noqa: F401

# The six wrappers live in two modules: two predate this change in
# ``checks_spec``, four are new in ``checks_portability`` (see that module's
# docstring for why they did not join the first two). Resolution walks both so
# a later move between them does not need a test edit.
VALIDATOR_MODULES = (checks_portability, checks_spec)

# Workflow command -> (pre_pr gate name, validator function name).
#
# Keyed on the command exactly as the workflow spells it, so a change to the
# invocation form (script to module, or a new flag) shows up here as an
# unmapped command rather than passing silently against a stale key.
EXPECTED: dict[str, tuple[str, str]] = {
    "python3 scripts/validation/check_vendor_portability.py": (
        "Vendor Portability",
        "validate_vendor_portability",
    ),
    "python3 -m scripts.validation.check_skill_portability": (
        "Skill Script Portability",
        "validate_skill_script_portability",
    ),
    "uv run --frozen python scripts/validation/check_skill_md_exec_portability.py": (
        "Skill Markdown Exec Portability",
        "validate_skill_md_exec_portability",
    ),
    "uv run --frozen python scripts/validation/check_skill_md_portability.py": (
        "Skill Markdown Portability",
        "validate_skill_md_portability",
    ),
    "python3 scripts/validation/check_skill_resolver_anchoring.py": (
        "Skill Resolver Anchoring",
        "validate_skill_resolver_anchoring",
    ),
    "python3 scripts/validation/check_skill_contract_tests.py": (
        "Skill Contract Tests",
        "validate_skill_contract_tests",
    ),
    "python3 scripts/validation/check_plugin_root_interpreter.py": (
        "Plugin-Root Interpreter",
        "validate_plugin_root_interpreter",
    ),
}

# Validators whose real-checker case runs in its own file. Measured on
# 2026-10-08: check_skill_md_portability took 25.8s of the real-checker test's
# 38s, because it scans every SKILL.md in the tree. Keeping it with the other
# cases made that file the slowest unit an xdist ``loadfile`` worker could get.
REAL_CHECKER_ISOLATED = frozenset({"validate_skill_md_portability"})


def defining_module(name: str) -> Any:
    """Return the module that defines a wrapper.

    Stubbing ``_run_subprocess`` has to target the module the wrapper resolves
    it from. Patching the wrong one leaves the real subprocess running and turns
    an assertion about argv into an assertion about nothing.
    """
    for module in VALIDATOR_MODULES:
        if getattr(module, name, None) is not None:
            return module
    raise AssertionError(f"no module defines {name!r}")


def validator(name: str) -> Any:
    """Resolve a wrapper by name across the modules that define the six."""
    return getattr(defining_module(name), name)


def real_checker_cases(*, isolated: bool) -> list[tuple[str, str]]:
    """Return the (gate name, validator name) cases for one real-checker file.

    ``isolated=True`` returns the cases in ``REAL_CHECKER_ISOLATED``; ``False``
    returns every other case. A validator added to ``EXPECTED`` lands in the
    shared file without an edit here.
    """
    return [
        case for case in sorted(EXPECTED.values()) if (case[1] in REAL_CHECKER_ISOLATED) is isolated
    ]
