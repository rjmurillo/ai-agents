"""Tests for the CLI exit-contract ratchet (issue #4068).

ADR-006 extraction turns a `set -e` shell failure into a Python sentinel that
no caller converts into a nonzero exit. Every test that missed this asserted on
a helper's return value and never on `main(argv)`. This gate counts extracted
scripts whose CLI is never proven to exit nonzero.

All git and filesystem I/O is against tmp_path with a stubbed `subprocess.run`,
so no test reads the live repository.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import cli_exit_contract_ratchet as ratchet

_SCRIPT_WITH_MAIN = "def main(argv=None):\n    return 0\n"
_SCRIPT_WITHOUT_MAIN = "def helper():\n    return 0\n"


def _fake_git(scripts: tuple[str, ...], tests: tuple[str, ...], *, returncode: int = 0):
    """Stand in for `git ls-files -z`, answering per glob."""

    def _run(cmd, **_kwargs):  # noqa: ANN001, ANN003
        paths = tests if any("tests/" in arg for arg in cmd) else scripts
        stdout = "\0".join(paths) + ("\0" if paths else "")
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def _seed(root: Path, relative: str, content: str) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return relative


def _baseline(root: Path, value: str) -> Path:
    path = root / "baseline.txt"
    path.write_text(value, encoding="utf-8")
    return path


def _arrange(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str, test: str) -> None:
    scripts = (_seed(tmp_path, "scripts/ci/widget.py", script),)
    tests = (_seed(tmp_path, "tests/ci/test_widget.py", test),)
    monkeypatch.setattr(subprocess, "run", _fake_git(scripts, tests))


def _run(tmp_path: Path, baseline: str, *extra: str) -> int:
    return ratchet.main(
        [
            "--repo-root",
            str(tmp_path),
            "--baseline",
            str(_baseline(tmp_path, baseline)),
            *extra,
        ]
    )


def test_a_proven_cli_exit_counts_as_covered(tmp_path, monkeypatch):
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\ndef test_fails():\n    assert widget.main([]) == 1\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_OK


def test_a_helper_only_assertion_is_a_violation(tmp_path, monkeypatch, capsys):
    """The exact shape that let six silent passes ship."""
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\n"
        "def test_helper():\n    assert widget.helper() is None\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_REGRESSION
    assert "scripts/ci/widget.py" in capsys.readouterr().out


def test_a_script_without_main_is_ignored(tmp_path, monkeypatch):
    _arrange(tmp_path, monkeypatch, _SCRIPT_WITHOUT_MAIN, "def test_nothing():\n    assert True\n")

    assert _run(tmp_path, "0") == ratchet.EXIT_OK


def test_a_main_nested_in_a_class_is_not_an_entry_point(tmp_path, monkeypatch):
    """Edge: only a module-level `main` carries a process exit contract."""
    _arrange(
        tmp_path,
        monkeypatch,
        "class Runner:\n    def main(self):\n        return 0\n",
        "def test_nothing():\n    assert True\n",
    )

    assert _run(tmp_path, "0") == ratchet.EXIT_OK


@pytest.mark.parametrize(
    "assertion",
    [
        "assert widget.main([]) == 1",
        "assert widget.main([]) == widget.EXIT_CONFIG",
        "assert widget.run().returncode == 2",
        "assert widget.excinfo.value.code != 0",
    ],
)
def test_each_accepted_assertion_shape_is_recognized(assertion):
    source = f"from scripts.ci import widget\n\n\ndef test_x():\n    {assertion}\n"

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


@pytest.mark.parametrize(
    "assertion",
    [
        "assert widget.main([]) == 0",
        "assert widget.main([]) == widget.EXIT_OK",
        "assert widget.run().returncode == 0",
    ],
)
def test_a_success_only_assertion_proves_nothing(assertion):
    source = f"from scripts.ci import widget\n\n\ndef test_x():\n    {assertion}\n"

    assert ratchet.covered_stems(source, frozenset({"widget"})) == set()


def test_a_multi_subject_file_does_not_lend_coverage_to_a_sibling():
    """The over-credit that file-wide matching would produce."""
    source = (
        "from scripts.ci import widget\n"
        "from scripts.ci import gadget\n"
        "\n\n"
        "def test_widget_fails():\n"
        "    assert widget.main([]) == 1\n"
        "\n\n"
        "def test_gadget_passes():\n"
        "    assert gadget.main([]) == 0\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget", "gadget"})) == {"widget"}


def test_a_single_subject_file_is_settled_file_wide():
    """A hand-rolled spec_from_file_location block binds no name a matcher sees."""
    source = (
        'spec = importlib.util.spec_from_file_location("widget", path)\n'
        "mod = importlib.util.module_from_spec(spec)\n"
        "\n\n"
        "def test_x():\n"
        "    assert mod.main([]) == 2\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


def test_a_subprocess_driven_cli_counts_by_script_path():
    source = (
        "def test_x():\n"
        '    result = subprocess.run([sys.executable, "scripts/ci/widget.py"])\n'
        "    assert result.returncode == 2\n"
    )

    assert ratchet.covered_stems(source, frozenset({"widget"})) == {"widget"}


def test_a_missing_baseline_is_a_config_error(tmp_path, monkeypatch):
    _arrange(tmp_path, monkeypatch, _SCRIPT_WITH_MAIN, "def test_x():\n    assert True\n")

    code = ratchet.main(
        ["--repo-root", str(tmp_path), "--baseline", str(tmp_path / "absent.txt")]
    )

    assert code == ratchet.EXIT_CONFIG


def test_a_malformed_baseline_is_a_config_error(tmp_path, monkeypatch):
    _arrange(tmp_path, monkeypatch, _SCRIPT_WITH_MAIN, "def test_x():\n    assert True\n")

    assert _run(tmp_path, "not-a-number") == ratchet.EXIT_CONFIG


def test_an_unrecorded_improvement_fails_and_update_records_it(tmp_path, monkeypatch):
    _arrange(
        tmp_path,
        monkeypatch,
        _SCRIPT_WITH_MAIN,
        "from scripts.ci import widget\n\n\ndef test_x():\n    assert widget.main([]) == 1\n",
    )

    assert _run(tmp_path, "3") == ratchet.EXIT_REGRESSION
    assert _run(tmp_path, "3", "--update") == ratchet.EXIT_OK
    assert (tmp_path / "baseline.txt").read_text(encoding="utf-8").strip() == "0"


def test_a_git_failure_is_an_external_error(tmp_path, monkeypatch):
    _seed(tmp_path, "scripts/ci/widget.py", _SCRIPT_WITH_MAIN)
    monkeypatch.setattr(subprocess, "run", _fake_git((), (), returncode=128))

    assert _run(tmp_path, "0") == ratchet.EXIT_EXTERNAL


def test_the_gate_is_wired_into_pr_validation():
    """Issue #3329: a guard nothing runs is not a guard."""
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pr-validation.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/ci/cli_exit_contract_ratchet.py" in workflow
