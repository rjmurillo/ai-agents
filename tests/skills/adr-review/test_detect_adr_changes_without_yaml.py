"""detect_adr_changes imports and fails closed when PyYAML is not installed.

`.claude/rules/plugin-self-containment.md` MUST 4: a plugin-root script runs
under a consumer's bare ``python3`` and may import only the standard library at
import time. The script used to ``import yaml`` unguarded, so it raised
``ModuleNotFoundError`` before it could report anything.

Without a parser the script cannot prove a frontmatter-only change is safe, so
the adr-review gate must fire (ADR-073) rather than skip.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "tests" / "skills"))

from claude_skills_import import import_skill_script

_TREES = [
    ".claude/skills/adr-review/scripts/detect_adr_changes.py",
    "src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py",
]

_BLOCK_YAML_THEN_RUN = (
    "import sys, runpy; sys.modules['yaml'] = None; "
    "script = sys.argv[1]; sys.argv = [script, '--help']; "
    "runpy.run_path(script, run_name='__main__')"
)


@pytest.mark.parametrize("tree", _TREES)
def test_script_starts_with_pyyaml_blocked(tree: str) -> None:
    """A blocked ``yaml`` import must not stop the script from starting."""
    script = str(REPO_ROOT / tree)
    result = subprocess.run(
        [sys.executable, "-c", _BLOCK_YAML_THEN_RUN, script],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )

    assert "ModuleNotFoundError" not in result.stderr
    assert "ImportError" not in result.stderr
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize("tree", _TREES)
class TestFailsClosedWithoutPyYaml:
    def _without_yaml(self, tree: str, monkeypatch: pytest.MonkeyPatch) -> Any:
        detector = import_skill_script(tree)
        monkeypatch.setattr(detector, "_HAVE_YAML", False)
        return detector

    def test_parse_reports_cannot_parse(self, tree: str, monkeypatch: pytest.MonkeyPatch) -> None:
        detector = self._without_yaml(tree, monkeypatch)

        assert detector._parse_frontmatter("status: proposed\n") is None

    def test_duplicate_key_check_does_not_vouch_for_the_block(
        self, tree: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = self._without_yaml(tree, monkeypatch)

        assert detector._has_duplicate_keys("status: proposed\n") is True

    def test_status_is_unknown_not_proposed(
        self, tree: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        detector = self._without_yaml(tree, monkeypatch)
        adr = tmp_path / "ADR-001.md"
        adr.write_text("---\nstatus: accepted\n---\n# Title\n", encoding="utf-8")

        assert detector._get_adr_status(adr) == detector.STATUS_UNKNOWN

    def test_exemption_is_refused(self, tree: str, monkeypatch: pytest.MonkeyPatch) -> None:
        detector = self._without_yaml(tree, monkeypatch)

        exempt = detector._only_non_decision_fields_changed(
            "status: accepted\nimplemented: false\n", "status: accepted\nimplemented: true\n"
        )

        assert exempt is False

    def test_exemption_is_granted_when_pyyaml_is_present(self, tree: str) -> None:
        """Control: the refusal above comes from the missing parser, not the input."""
        pytest.importorskip("yaml")
        detector = import_skill_script(tree)

        exempt = detector._only_non_decision_fields_changed(
            "status: accepted\nimplemented: false\n", "status: accepted\nimplemented: true\n"
        )

        assert exempt is True
