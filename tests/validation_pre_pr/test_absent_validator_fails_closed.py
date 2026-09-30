"""A blocking pre-PR gate whose validator script is absent must fail (issue #5636).

``validate_agent_catalog`` already fails closed on a missing script.
``validate_orchestrator_citations`` returned True instead, so a checkout
missing the validator reported a green gate for a check that never ran.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.pre_pr import validate_orchestrator_citations

_SCRIPT = "check_orchestrator_citations.py"


def _repo(tmp_path: Path, *, with_script: bool) -> Path:
    validation = tmp_path / "scripts" / "validation"
    validation.mkdir(parents=True)
    if with_script:
        (validation / _SCRIPT).write_text("# stub\n", encoding="utf-8")
    return tmp_path


class TestOrchestratorCitations:
    def test_absent_script_fails_closed(self, tmp_path: Path, capsys) -> None:
        repo = _repo(tmp_path, with_script=False)
        with patch("checks_spec._run_subprocess") as run:
            assert validate_orchestrator_citations(repo) is False
        run.assert_not_called()
        err = capsys.readouterr().err
        assert "[ERROR]" in err
        assert "absent" in err
        assert "skipping" not in err

    def test_passes_when_validator_exits_zero(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, with_script=True)
        with patch("checks_spec._run_subprocess", return_value=(0, "ok", "")):
            assert validate_orchestrator_citations(repo) is True

    @pytest.mark.parametrize("exit_code", [1, 2])
    def test_fails_when_validator_exits_nonzero(self, tmp_path: Path, exit_code: int) -> None:
        repo = _repo(tmp_path, with_script=True)
        result = (exit_code, "", "bad")
        with patch("checks_spec._run_subprocess", return_value=result):
            assert validate_orchestrator_citations(repo) is False
