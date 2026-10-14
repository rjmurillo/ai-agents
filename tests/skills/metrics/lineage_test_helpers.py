"""Shared fixtures for the defect lineage tests (issue #5638)."""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = PROJECT_ROOT / ".claude" / "skills" / "metrics"
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

REPO = "rjmurillo/ai-agents"
URL = f"https://github.com/{REPO}"
SHA_A = "a" * 40
SHA_B = "b" * 40


def fixed_chain() -> dict[str, Any]:
    """The #5623 chain: a review 5 s after merge, repaired by #5630, now fixed."""
    return copy.deepcopy(
        {
            "schema_version": 1,
            "id": "pr-5623-chain",
            "repository": REPO,
            "default_branch": "main",
            "claim": "The probe verified an incomplete topology.",
            "supports": ["defect", "review_race"],
            "introduction": {
                "pr": 5623,
                "url": f"{URL}/pull/5623",
                "commit": "aa951a04e76d3db2bc16c72cf7e34573314e65dd",
                "merged_at": "2026-09-06T22:23:33Z",
            },
            "detection": {
                "source": "devin review",
                "url": f"{URL}/pull/5623#pullrequestreview-5126799992",
                "at": "2026-09-06T22:23:38Z",
            },
            "detection_delay_seconds": 5,
            "follow_up": {
                "kind": "defect_repair",
                "pr": 5630,
                "url": f"{URL}/pull/5630",
                "commit": "a719e452d",
                "merged_at": "2026-09-07T02:36:22Z",
            },
            "status": "FIXED",
            "status_history": [
                {
                    "status": "CURRENT",
                    "live_sha": SHA_A,
                    "checked_at": "2026-09-06T22:30:00Z",
                    "basis": "claim held at introduction",
                },
                {
                    "status": "FIXED",
                    "live_sha": SHA_B,
                    "checked_at": "2026-10-13T11:00:00Z",
                    "basis": "pattern absent",
                },
            ],
            "recheck": {
                "description": "The bug line lived in one file.",
                "command": "git show <rev>:scripts/x.py | grep bug",
                "path": "scripts/x.py",
                "pattern": "bug_line",
                "live_when": "present",
            },
            "limitations": ["Proves the line is gone, not that the replacement is right."],
        }
    )


def observation_chain() -> dict[str, Any]:
    """A planned follow-up chain that claims no defect."""
    record = fixed_chain()
    record["id"] = "planned-chain"
    record["supports"] = ["observation"]
    record["follow_up"]["kind"] = "planned_work"
    record["status"] = "CURRENT"
    record["status_history"] = [
        {
            "status": "CURRENT",
            "live_sha": SHA_B,
            "checked_at": "2026-10-13T11:00:00Z",
            "basis": "pattern present",
        }
    ]
    record.pop("detection_delay_seconds")
    return record
