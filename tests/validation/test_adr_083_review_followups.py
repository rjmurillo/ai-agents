"""ADR-083 and ADR-097 prose must match what the repository does.

Follow-up to #6746. Each test pins one audit finding with a positive check
(the corrected claim is present) and a negative check (the false claim is gone
or the premise still holds).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCH = ROOT / ".project-toolkit" / "architecture"
ADR_083 = (ARCH / "ADR-083-copilot-dogfood-surface-separation.md").read_text(encoding="utf-8")
ADR_097 = (ARCH / "ADR-097-zero-tool-use-hooks.md").read_text(encoding="utf-8")
SMOKE = (ROOT / "tests" / "e2e" / "test_plugin_load_smoke.py").read_text(encoding="utf-8")
BEST_PRACTICES = (
    ROOT / "src" / "claude" / "skills" / "adr-generator" / "references" / "adr-best-practices.md"
).read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _function_body(source: str, name: str) -> str:
    match = re.search(rf"^def {name}\(.*?(?=^def |\Z)", source, re.S | re.M)
    assert match, f"{name} not found"
    return match.group(0)


# Finding 1: the in-place rewrite is recorded as a departure, not hidden.


def test_adr_083_records_the_in_place_amendment_form() -> None:
    flat = _flat(ADR_083)
    assert "Form: the owner asked for" in flat
    assert "rewrote Decision items 1 to 6" in flat
    assert "adr-best-practices.md" in flat
    assert "owner has not recorded a choice of the in-place form" in flat


def test_adr_083_best_practice_citation_still_holds() -> None:
    assert "Decision change after any implementation" in BEST_PRACTICES
    assert "create a new superseding ADR" in BEST_PRACTICES


def test_adr_083_does_not_claim_the_owner_chose_in_place() -> None:
    flat = _flat(ADR_083)
    assert "owner chose the in-place" not in flat
    assert "owner chose an in-place" not in flat


# Finding 2: item 4 states an unmet requirement, not a present-tense fact.


def test_adr_083_item_4_states_the_script_assertion_as_unmet() -> None:
    flat = _flat(ADR_083)
    assert "must also assert a real shipped skill script resolves" in flat
    assert "No Copilot test does this yet" in flat
    assert "The test also asserts a real shipped skill script" not in flat


def test_copilot_smoke_test_still_has_no_script_assertion() -> None:
    """If this fails, the gap closed: update ADR-083 item 4 and the amendment."""
    body = _function_body(SMOKE, "test_copilot_plugin_loads_expected_skills")
    assert "EXPECTED_SKILLS" in body
    assert not re.search(r"script", body, re.I)


# Finding 3: the cross-citation runs both ways.


def test_adr_097_cites_adr_083() -> None:
    related = ADR_097.split("## Related Decisions", 1)[1].split("## References", 1)[0]
    assert "ADR-083" in related


def test_adr_083_cites_adr_097_in_related_decisions() -> None:
    related = ADR_083.split("## Related Decisions", 1)[1].split("## References", 1)[0]
    assert "ADR-097" in related
    assert "cites this ADR back" in _flat(related)


def test_adr_083_no_longer_calls_the_cross_citation_one_way() -> None:
    flat = _flat(ADR_083)
    assert "The cross-citation is one-way" not in flat
    assert "ADR-097 does not cite this ADR" not in flat
    assert "added the ADR-097 back-reference" in flat
