"""Verify the bounded doctor/bootstrap handoff across shipped entry points."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIPPED_ROOTS = (".claude", "src/claude", "src/copilot-cli", "src/codex")


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_doctor_diagnosis_precedes_candidate_mining(root: str) -> None:
    text = (REPO_ROOT / root / "skills" / "skill-bootstrap" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    phase = text.split("### Phase 2:", 1)[1].split("### Phase 3:", 1)[0]
    assert phase.index("Invoke `skill-doctor`") < phase.index("bootstrap_mine.py")
    assert "--sessions-json" in phase
    assert "references/discovery.md#existing-skill-improvement-loop" in phase


@pytest.mark.parametrize("root", SHIPPED_ROOTS)
def test_doctor_child_returns_without_recursive_bootstrap(root: str) -> None:
    text = (REPO_ROOT / root / "skills" / "skill-doctor" / "SKILL.md").read_text(encoding="utf-8")
    startup = text.split("### Step 0:", 1)[1].split("### Step 1:", 1)[0]
    collection = text.split("### Step 1:", 1)[1].split("### Step 2:", 1)[0]
    assert "reuse its validated repository" in startup
    assert "Do not invoke skill-bootstrap from a bootstrap child run." in startup
    assert "return it to the caller instead of starting another run" in collection
    assert "omit `--open`" in text
