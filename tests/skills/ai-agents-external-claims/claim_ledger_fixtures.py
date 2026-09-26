"""Shared ledger builders for the claim ledger tests (issue #5388)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/ai-agents-external-claims/scripts/claim_ledger.py",
    module_name="test_claim_ledger_mod",
)

PRIMARY = {
    "kind": "primary",
    "url": "https://kafka.apache.org/documentation/",
    "published": None,
    "accessed": "2026-09-25",
    "secondary_reason": None,
}


def make_claim(**overrides: Any) -> dict[str, Any]:
    claim: dict[str, Any] = {
        "id": "C1",
        "claim": "Kafka consumers pause fetches when the buffer is full",
        "category": "vendor",
        "time_sensitive": False,
        "source": dict(PRIMARY),
        "confidence": "high",
        "disposition": "verified",
        "final_wording": "Kafka consumers pause fetches when the buffer is full",
        "gap": "",
    }
    claim.update(overrides)
    return claim


def make_ledger(*claims: Any, decision: str = "activate") -> dict[str, Any]:
    return {
        "artifact": "analysis/queue-backpressure.md",
        "activation": {"decision": decision, "reason": "vendor and statistic claims"},
        "claims": list(claims),
    }


def make_statistic() -> dict[str, Any]:
    return make_claim(
        id="C2",
        claim="Over 1000 teams run the operator in production",
        category="statistic",
        source={
            "kind": "primary",
            "url": "https://api.github.com/repos/example/operator",
            "published": "2026-09-01",
            "accessed": "2026-09-25",
            "secondary_reason": None,
        },
        confidence="medium",
        disposition="narrowed",
        time_sensitive=True,
        final_wording="As of 2026-09-25 the operator repository lists 987 stars",
        gap="The source counts stars, not production teams.",
    )


def make_secondary() -> dict[str, Any]:
    return make_claim(
        id="C3",
        claim="Vendor X cut p99 latency by 40 percent",
        category="comparative",
        source={
            "kind": "secondary",
            "url": "https://blog.example.com/vendor-x-review",
            "published": "2026-08-10",
            "accessed": "2026-09-25",
            "secondary_reason": "Vendor X publishes no benchmark artifact.",
        },
        confidence="low",
        disposition="qualified",
        final_wording="A third-party review reports that Vendor X cut p99 latency",
        gap="No primary benchmark exists.",
    )


def make_unavailable() -> dict[str, Any]:
    return make_claim(
        id="C4",
        claim="The SDK supports ARM64 on every platform",
        category="api",
        source={
            "kind": "none",
            "url": None,
            "published": None,
            "accessed": None,
            "secondary_reason": None,
        },
        confidence="none",
        disposition="removed",
        final_wording="",
        gap="Browsing was unavailable, so the claim was removed.",
    )


def ledger_errors(ledger: Any, artifact: str | None = None) -> list[str]:
    errors: list[str] = mod.validate(ledger, artifact)
    return errors


def write(tmp_path: Path, name: str, data: object) -> Path:
    path = tmp_path / name
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path
