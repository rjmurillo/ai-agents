"""Coupled-document lookup routing for the ``/test`` Gate 5 trigger (issue #5398).

A changed document is scanned directly. Every other activation cause can leave
a document stale that the diff never touched, so ``coupled_documents_needed``
must stay true beside any changed document.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(
    ".claude/skills/test/scripts/doc_accuracy_trigger.py",
    module_name="test_doc_accuracy_coupled_mod",
)


@pytest.fixture(scope="module")
def classifier():
    return mod.load_classifier()


def _decide(classifier, paths, effects=()):
    return mod.decide(list(paths), list(effects), "origin/main", classifier)


def test_changed_document_with_effect_code_still_needs_coupled_documents(classifier) -> None:
    result = _decide(classifier, ["README.md", "src/filters.py"], ["quantitative-claim"])
    assert result["changed_documents"] == ["README.md"]
    assert result["coupled_documents_needed"] is True


@pytest.mark.parametrize(
    ("paths", "effects"),
    [
        (["docs/guide.md", "src/service.py"], []),
        (["docs/guide.md", "tests/skills/test_a.py"], []),
        (["docs/guide.md"], []),
    ],
)
def test_changed_document_without_a_code_cause_does_not_need_coupled_documents(
    classifier, paths, effects
) -> None:
    result = _decide(classifier, paths, effects)
    assert result["decision"] == "activate"
    assert result["coupled_documents_needed"] is False


@pytest.mark.parametrize(
    ("paths", "effects"),
    [
        (["docs/guide.md", ".doc-accuracy/notes.md"], []),
        (["docs/guide.md", ".claude/skills/test/scripts/doc_accuracy_trigger.py"], []),
        (["docs/guide.md", "src/service.py"], ["no-such-effect"]),
        (["docs/guide.md", "totally/unknown.zzz"], []),
    ],
)
def test_changed_document_beside_another_cause_still_needs_coupled_documents(
    classifier, paths, effects
) -> None:
    result = _decide(classifier, paths, effects)
    assert result["coupled_documents_needed"] is True


def test_gate_reference_scans_coupled_documents_without_diff_base() -> None:
    """--diff-base inventories only changed documents (doc_accuracy.py run_assessment)."""
    ref = (
        Path(__file__).resolve().parents[3]
        / "src/claude/skills/test/references/doc-accuracy-gate.md"
    )
    text = ref.read_text(encoding="utf-8")
    section = text[
        text.index("When `coupled_documents_needed` is true") : text.index("## 5. Verdict")
    ]
    assert "no `--diff-base`" in section
    assert "scan\nit with the same `--diff-base` rules" not in section
