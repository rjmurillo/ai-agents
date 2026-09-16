#!/usr/bin/env python3
"""Show the harness x billing matrix and what is runnable right now.

The matrix is two questions an operator asks before spending anything: which
cells exist, and which of them this machine can actually reach. Answering the
second one from a script matters more than it looks. A missing credential or
an uninstalled CLI otherwise surfaces as a non-zero exit somewhere inside a
long eval run, after the baseline half has already been paid for.

Readiness here is a precondition check, never a claim about the backend. It
reports that a credential variable is set and that an executable is on PATH.
It does not call anything, so it cannot tell a valid token from a revoked one
and does not pretend to: `READY` means "nothing is obviously missing", and a
cell's `status` column still says whether a live run has ever confirmed it.

Exit codes follow AGENTS.md: 0 ok, 2 config, 3 external.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence

from _billing_matrix import (
    BILLING_MODES,
    HARNESSES,
    BillingMatrixError,
    MatrixCell,
    cells,
    format_matrix,
    resolve_selection,
)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

READY = "READY"
NOT_READY = "NOT_READY"
#: The cell needs a credential this check cannot see: a CLI login on disk.
#: Reported separately from READY so a preflight never claims a run will
#: authenticate when nothing here looked at the thing that authenticates it.
UNKNOWN = "UNKNOWN"

#: Executable each cell shells out to, when it shells out to one. An HTTP cell
#: has no entry: nothing needs to be installed for it.
_CELL_EXECUTABLE: dict[str, tuple[str, str]] = {
    "claude-cli": ("claude", "CLAUDE_CLI_BIN"),
    "codex-cli": ("codex", "CODEX_CLI_BIN"),
    "copilot-cli": ("copilot", "COPILOT_CLI_BIN"),
}

#: Extra variables a cell cannot run without, beyond its credential. Only the
#: copilot/api cell has one, because it has no default endpoint to fall back
#: on; see `_providers._make_copilot_api`.
_CELL_REQUIRED_SETTINGS: dict[str, tuple[str, ...]] = {
    "copilot-api": ("COPILOT_API_BASE_URL",),
}


def _executable_for(cell: MatrixCell) -> str | None:
    entry = _CELL_EXECUTABLE.get(cell.provider)
    if entry is None:
        return None
    default, override_env = entry
    return (os.environ.get(override_env) or "").strip() or default


def _missing_requirements(cell: MatrixCell) -> list[str]:
    """Return every hard reason this cell cannot run on this machine.

    All of them, not the first: an operator fixing one at a time pays a round
    trip per miss, and the checks are independent.
    """
    missing: list[str] = []
    if cell.credential_required and not _has_credential(cell):
        missing.append("no credential in " + " or ".join(cell.credentials))
    for name in _CELL_REQUIRED_SETTINGS.get(cell.provider, ()):
        if not (os.environ.get(name) or "").strip():
            missing.append(f"{name} is unset")
    executable = _executable_for(cell)
    if executable is not None and shutil.which(executable) is None:
        missing.append(f"{executable} is not on PATH")
    return missing


def _has_credential(cell: MatrixCell) -> bool:
    return any(os.environ.get(name) for name in cell.credentials)


def _verdict(cell: MatrixCell, missing: list[str]) -> str:
    if missing:
        return NOT_READY
    if cell.credentials and not cell.credential_required and not _has_credential(cell):
        return UNKNOWN
    return READY


def _readiness(cell: MatrixCell) -> dict[str, object]:
    missing = _missing_requirements(cell)
    verdict = _verdict(cell, missing)
    if verdict == UNKNOWN:
        missing = [
            "no credential in "
            + " or ".join(cell.credentials)
            + "; the CLI may still authenticate from a login on disk, which "
            "this check does not read"
        ]
    return {
        "harness": cell.harness,
        "billing": cell.billing,
        "cell": cell.name,
        "provider": cell.provider,
        "transport": cell.transport,
        "credentials": list(cell.credentials),
        "cost_basis": cell.cost_basis,
        "status": cell.status,
        "readiness": verdict,
        "missing": missing,
        "note": cell.note,
    }


def _render_text(rows: Sequence[dict[str, object]]) -> str:
    lines = [format_matrix(), "", "Readiness on this machine:"]
    for row in rows:
        missing = row["missing"]
        reasons = missing if isinstance(missing, list) else []
        detail = "; ".join(str(item) for item in reasons) or "nothing missing"
        lines.append(f"  {row['cell']}: {row['readiness']} ({detail})")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Print the eval harness x billing matrix and whether each cell "
            "can run on this machine."
        )
    )
    parser.add_argument("--harness", choices=HARNESSES, help="Limit to one harness.")
    parser.add_argument(
        "--billing", choices=BILLING_MODES, help="Limit to one billing mode."
    )
    parser.add_argument(
        "--provider", help="Limit to the cell this provider name selects."
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help=(
            "Exit 3 when any selected cell is not ready. UNKNOWN does not "
            "fail: an unreadable on-disk login is not evidence of a missing "
            "one. Use it as a precondition step before a paid run."
        ),
    )
    return parser


def _selected_cells(args: argparse.Namespace) -> list[MatrixCell]:
    """Return the cells the flags name, in matrix order.

    A fully specified selection goes through `resolve_selection` so this
    command and an eval run agree on what a given set of flags means; a
    partial one filters, because "every api cell" is a useful question here
    and not a transport an eval could run.
    """
    if args.provider or (args.harness and args.billing):
        return [
            resolve_selection(
                provider=args.provider,
                harness=args.harness,
                billing=args.billing,
                environ={},
            )
        ]
    return [
        cell
        for cell in cells()
        if (args.harness is None or cell.harness == args.harness)
        and (args.billing is None or cell.billing == args.billing)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        selected = _selected_cells(args)
    except BillingMatrixError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    rows = [_readiness(cell) for cell in selected]
    if args.json:
        print(json.dumps({"cells": rows}, indent=2, sort_keys=True))
    else:
        print(_render_text(rows))
    if args.require_ready and any(row["readiness"] == NOT_READY for row in rows):
        print(
            "error: at least one selected cell is not ready; see the missing "
            "column above.",
            file=sys.stderr,
        )
        return EXIT_EXTERNAL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
