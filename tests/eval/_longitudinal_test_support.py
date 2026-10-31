"""Shared helpers for the longitudinal pilot tests (issue #6993). No model is spawned."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _longitudinal_report as rep  # noqa: E402
import eval_longitudinal_pilot as cli  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PILOT_PATH = cli.DEFAULT_PILOT
SENTINEL = "SECRET-TRANSCRIPT-SENTINEL"


def fake_checkout(tmp_path: Path, pilot: dict[str, Any]) -> Path:
    for fact in pilot["local_context"]["facts"]:
        target = tmp_path / fact["probe"]["path_exists"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x", encoding="utf-8")
    return tmp_path


def runs(
    pilot: dict[str, Any],
    tmp_path: Path,
    runner: Any,
    ledger: Any = None,
    reps: int = 1,
    minutes: Any = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = fake_checkout(tmp_path, pilot)
    return cli.execute(pilot, runner, {"pre": root, "post": root}, "m", reps, ledger, minutes)


def report_of(
    pilot: dict[str, Any], records: list[dict[str, Any]], ledger: Any = None
) -> dict[str, Any]:
    window = {"elapsed_s": 10.0}
    return rep.build_report(pilot, records, {"model": "m"}, window, ledger, None, "test")
