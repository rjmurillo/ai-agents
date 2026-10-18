"""The lens taxonomy in bootstrap_forms.py matches the reference tables."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
    / "bootstrap_forms.py"
)
_spec = importlib.util.spec_from_file_location("bootstrap_forms_lenses", SCRIPT)
assert _spec is not None and _spec.loader is not None
bootstrap_forms = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap_forms_lenses"] = bootstrap_forms
_spec.loader.exec_module(bootstrap_forms)

REFERENCES = SCRIPT.parent.parent / "references"
# discovery.md names each lens in prose; the plan uses the kebab id.
DISCOVERY_LENS_IDS = {
    "Change control": "change-control",
    "Debugging playbook": "debugging-playbook",
    "Failure archaeology": "failure-archaeology",
    "Architecture contract": "architecture-contract",
    "Domain reference": "domain-reference",
    "Configuration and flags": "config-and-flags",
    "Build and environment": "build-and-env",
    "Run and operate": "run-and-operate",
    "Diagnostics and tooling": "diagnostics-and-tooling",
    "Validation and QA": "validation-and-qa",
    "Documentation and writing": "docs-and-writing",
    "External positioning": "external-positioning",
    "Hardest-problem campaign": "hardest-problem-campaign",
    "Proof and analysis toolkit": "proof-and-analysis-toolkit",
    "Research frontier": "research-frontier",
    "Research methodology": "research-methodology",
}


def test_lenses_match_the_authoring_table():
    text = (REFERENCES / "authoring-and-gates.md").read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `lens` |"))
    ids = {m for m in re.findall(r"`([a-z][a-z-]*)`", row.split("|")[2]) if m != "other"}

    assert ids == set(bootstrap_forms.LENSES)


def test_lenses_match_the_discovery_table():
    text = (REFERENCES / "discovery.md").read_text(encoding="utf-8")
    rows = text.split("| Lens | Instruction for discovery | Usual form |", 1)[1].splitlines()[2:]
    names = []
    for line in rows:
        if not line.startswith("|"):
            break
        names.append(line.split("|")[1].strip())

    assert set(names) == set(DISCOVERY_LENS_IDS)
    assert len(names) == len(DISCOVERY_LENS_IDS)
    assert set(DISCOVERY_LENS_IDS.values()) == set(bootstrap_forms.LENSES)
