"""AC-DUP-7: Both scanners preserve rule parsing through shared code."""

import os
import subprocess
from pathlib import Path

import pytest

from scripts.hook_utilities.scan_rules import parse_scan_rules
from tests.test_push_pr_interpreter_floor import PYTHON310, requires_python310

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("value,expected", [("", ("one", "two")), (" two , one ", ("two", "one"))])
def test_rule_selection_preserves_defaults_and_order(value: str, expected: tuple[str, ...]) -> None:
    assert parse_scan_rules(value, ("one", "two"), 1) == expected


def test_invalid_rules_keep_the_existing_exit_and_diagnostic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        parse_scan_rules("bad,missing", ("one", "two"), 1)
    assert error.value.code == 1
    assert capsys.readouterr().err == (
        "error: unknown rules: bad, missing\nvalid rules: one, two\n"
    )


_SCANNERS = (
    "src/claude/skills/golden-principles/scripts/scan_principles.py",
    "src/claude/skills/taste-lints/scripts/taste_lints.py",
)


@requires_python310
@pytest.mark.parametrize("script", _SCANNERS)
def test_scanner_imports_on_the_python310_floor(script: str) -> None:
    """Both scanners run on the host interpreter, which can be 3.10.

    The shared parser lives in hook_utilities. ai_review_common imports
    datetime.UTC (3.11+) from its package __init__, so a scanner that
    imported the parser from there failed to load on 3.10.
    """
    assert PYTHON310 is not None
    load = (
        "import importlib.util, sys; p = sys.argv[1]; "
        "sys.path.insert(0, __import__('os').path.dirname(p)); "
        "s = importlib.util.spec_from_file_location('probe_target', p); "
        "m = importlib.util.module_from_spec(s); sys.modules['probe_target'] = m; "
        "s.loader.exec_module(m)"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
    }

    result = subprocess.run(
        [PYTHON310, "-I", "-c", load, str(REPO_ROOT / script)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stderr
