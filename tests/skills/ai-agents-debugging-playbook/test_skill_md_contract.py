"""ADR-108 template contract for ai-agents-debugging-playbook; see _template_contract.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _template_contract import assert_template_owned_contract


def test_skill_md_matches_its_template() -> None:
    assert_template_owned_contract("ai-agents-debugging-playbook")
