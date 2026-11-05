"""Tests for the ``Import Boundaries`` pre-PR gate (``validate_import_boundaries``).

The gate runs ``lint-imports`` and prints the part of its output that names the
offending imports. Fakes here shape that output like the real command; the
fixture-tree tests in ``tests/test_import_linter_contracts.py`` drive the gate
over real output.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_import_boundaries_gate_runs_lint_imports_with_no_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import checks_ci_parity

    argvs: list[list[str]] = []

    def fake(argv: list[str], **_kwargs: object) -> tuple[int, str, str]:
        argvs.append(argv)
        return 0, "", ""

    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", fake)
    assert checks_ci_parity.validate_import_boundaries(REPO_ROOT) is True
    assert "lint_imports_command" in argvs[0][2]
    assert argvs[0][3:] == ["--no-cache"]


_BANNER = "\n".join(f"banner line {n}" for n in range(1, 46))


def _lint_imports_output(*detail: str) -> str:
    """Shape lint-imports output: a long banner, a summary, then the broken section last."""
    return "\n".join(
        [
            _BANNER,
            "Contracts: 3 kept, 1 broken.",
            "",
            "Broken contracts",
            "----------------",
            *detail,
        ]
    )


def test_import_boundaries_gate_names_the_offending_import_past_the_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import checks_ci_parity

    output = _lint_imports_output(
        "scripts is not allowed to import tests:",
        "-   scripts.ci.tool -> tests.helper (l.1)",
    )
    # The offending line sits past line 40, where the old head slice stopped.
    assert output.splitlines().index("-   scripts.ci.tool -> tests.helper (l.1)") > 40
    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", lambda *_a, **_k: (1, output, ""))
    with redirect_stdout(io.StringIO()) as captured:
        assert checks_ci_parity.validate_import_boundaries(REPO_ROOT) is False
    assert "scripts.ci.tool -> tests.helper (l.1)" in captured.getvalue()
    assert "Contracts: 3 kept, 1 broken." in captured.getvalue()
    assert "banner line 1\n" not in captured.getvalue()


def test_import_boundaries_gate_says_how_many_detail_lines_it_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import checks_ci_parity

    cap = checks_ci_parity._IMPORT_DETAIL_LINES
    output = _lint_imports_output(*(f"- scripts.m{n} -> tests.x (l.1)" for n in range(cap + 7)))
    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", lambda *_a, **_k: (1, output, ""))
    with redirect_stdout(io.StringIO()) as captured:
        assert checks_ci_parity.validate_import_boundaries(REPO_ROOT) is False
    assert "... 9 more lines not shown" in captured.getvalue()
    assert f"scripts.m{cap - 3} -> tests.x" in captured.getvalue()


def test_import_boundaries_gate_prints_the_tail_when_no_section_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import checks_ci_parity

    trace = "\n".join(f"trace line {n}" for n in range(100))
    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", lambda *_a, **_k: (1, "", trace))
    with redirect_stdout(io.StringIO()) as captured:
        assert checks_ci_parity.validate_import_boundaries(REPO_ROOT) is False
    assert "trace line 99" in captured.getvalue()
    assert "trace line 0\n" not in captured.getvalue()


def test_import_boundaries_gate_skips_without_contracts(tmp_path: Path) -> None:
    import checks_ci_parity
    from checks_common import MissingScriptSkip

    (tmp_path / "pyproject.toml").write_text(
        "# [tool.importlinter] only in a comment\n[project]\nname = 'x'\n", encoding="utf-8"
    )
    with pytest.raises(MissingScriptSkip):
        checks_ci_parity.validate_import_boundaries(tmp_path)
    (tmp_path / "pyproject.toml").unlink()
    with pytest.raises(MissingScriptSkip):
        checks_ci_parity.validate_import_boundaries(tmp_path)


@pytest.mark.parametrize(
    "header",
    ["[tool.importlinter]", "  [tool.importlinter.contracts]", "[[tool.importlinter.contracts]]"],
)
def test_import_boundaries_gate_runs_when_a_header_declares_contracts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, header: str
) -> None:
    import checks_ci_parity

    (tmp_path / "pyproject.toml").write_text(f"[project]\nname = 'x'\n{header}\n", encoding="utf-8")
    monkeypatch.setattr(checks_ci_parity, "_run_subprocess", lambda *_a, **_k: (0, "ok", ""))
    with redirect_stdout(io.StringIO()):
        assert checks_ci_parity.validate_import_boundaries(tmp_path) is True


def test_import_boundaries_gate_passes_on_the_real_tree() -> None:
    """Run the real command, not a fake, against this tree's contracts."""
    import checks_ci_parity

    with redirect_stdout(io.StringIO()):
        assert checks_ci_parity.validate_import_boundaries(REPO_ROOT) is True


@pytest.mark.parametrize(
    "extra_env",
    [{"PYTHONIOENCODING": "cp1252"}, {"FORCE_COLOR": "1"}],
    ids=["non-utf8-stdout", "forced-color"],
)
def test_import_boundaries_program_survives_a_hostile_terminal(
    extra_env: dict[str, str],
) -> None:
    import os
    import subprocess
    import sys

    import checks_ci_parity

    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, "-c", checks_ci_parity._LINT_IMPORTS_PROGRAM, "--no-cache"],
        cwd=Path(__file__).resolve().parents[2],
        env={**env, **extra_env},
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\x1b[" not in result.stdout
    assert any(line.startswith("Contracts:") for line in result.stdout.splitlines())
