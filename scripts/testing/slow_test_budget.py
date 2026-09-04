"""Performance budget gate for the validator suites (issue #5382).

Reads the JUnit report a pytest run already wrote, groups it with
``slow_test_report``, and fails when a suite named in ``[tool.slow-test-budget]``
spent more seconds than that table allows::

    uv run python scripts/testing/slow_test_budget.py junit.xml --budget pyproject.toml

The table is a map of module path to seconds. A budgeted module absent from the
report is not a violation: partitioned and change-scoped CI runs legitimately do
not execute every suite, and the printed counts say which case a green run was.

Exit codes: 0 ok (nothing over budget), 1 logic (a module over budget, or no
records at all), 2 config (unreadable budget or arguments), 3 external
(unreadable input).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from pathlib import Path

import tomllib

from scripts.testing.slow_test_report import ModuleGroup, group_by_module, load_inputs


def load_budget(path: Path) -> dict[str, float]:
    """Read the ``[tool.slow-test-budget]`` table from a TOML file.

    A file with no such table budgets nothing, which is how a report can be run
    against a project that has not adopted the gate.
    """
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    table = data.get("tool", {}).get("slow-test-budget", {})
    if not isinstance(table, dict):
        raise ValueError(f"{path}: [tool.slow-test-budget] is not a table")
    return {str(module): float(seconds) for module, seconds in table.items()}


def overruns(
    groups: Iterable[ModuleGroup], budget: dict[str, float]
) -> list[tuple[str, float, float]]:
    """Every budgeted module over its limit, all of them, not the first.

    A run that pushed two suites over budget has to name both, or the second
    surfaces only after someone fixes the first.
    """
    return [
        (group.module, group.seconds, budget[group.module])
        for group in groups
        if group.module in budget and group.seconds > budget[group.module]
    ]


def report(groups: Sequence[ModuleGroup], budget: dict[str, float]) -> int:
    """Print the verdict and return the exit code it implies."""
    present = [g for g in groups if g.module in budget]
    over = overruns(groups, budget)
    for module, seconds, limit in over:
        print(
            f"over budget: {module} recorded {seconds:.2f}s against {limit:.2f}s",
            file=sys.stderr,
        )
    print(
        f"budget: {len(over)} over, {len(present)} of {len(budget)} budgeted "
        f"modules present, {len(groups)} modules in this report",
        file=sys.stderr,
    )
    return 1 if over else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail when a validator suite exceeds its seconds budget "
        "(issue #5382)."
    )
    parser.add_argument(
        "inputs", nargs="+", type=Path, help="Recorder JSON and/or JUnit XML files."
    )
    parser.add_argument(
        "--budget",
        type=Path,
        default=Path("pyproject.toml"),
        metavar="TOML",
        help="TOML file holding [tool.slow-test-budget] (default: pyproject.toml).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        budget = load_budget(args.budget)
    except OSError as exc:
        print(f"could not read budget: {exc}", file=sys.stderr)
        return 3
    except (tomllib.TOMLDecodeError, ValueError, TypeError) as exc:
        print(f"malformed budget: {exc}", file=sys.stderr)
        return 2
    try:
        records = load_inputs(args.inputs)
    except FileNotFoundError as exc:
        print(f"input not found: {exc}", file=sys.stderr)
        return 3
    except (OSError, ET.ParseError) as exc:
        print(f"could not read input: {exc}", file=sys.stderr)
        return 3
    except (ValueError, KeyError, TypeError) as exc:
        print(f"malformed input: {exc}", file=sys.stderr)
        return 2
    if not records:
        print("no test records in the given inputs", file=sys.stderr)
        return 1
    return report(group_by_module(records.values(), min_seconds=0.0), budget)


if __name__ == "__main__":
    sys.exit(main())
