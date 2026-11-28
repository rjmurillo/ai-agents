"""Real-child proof that a checkout ``ruff`` never shadows the installed one.

CWE-427: ``python -P`` drops only the implicit script and working directory
entries. A ``PYTHONPATH`` entry that reaches the checkout still outranks
site-packages, so an attacker-controlled ``ruff`` package in a pull request
checkout could run in place of the real linter. These tests start real
interpreters; a fake ``find_spec`` cannot show what a child imports.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci import ruff_ratchet

_SHADOW_SOURCE = (
    "import pathlib\n"
    "pathlib.Path({sentinel!r}).write_text('shadow ran', encoding='utf-8')\n"
    "print('[]')\n"
)


def _plant_shadow(directory: Path, sentinel: Path, layout: str) -> None:
    """Plant a ``ruff`` that records its own execution in ``sentinel``."""
    source = _SHADOW_SOURCE.format(sentinel=str(sentinel))
    directory.mkdir(parents=True, exist_ok=True)
    if layout == "package":
        package = directory / "ruff"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(source, encoding="utf-8")
    else:
        (directory / "ruff.py").write_text(source, encoding="utf-8")


def _checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "clean.py").write_text("print('ok')\n", encoding="utf-8")
    return checkout


def _installed_ruff_present() -> bool:
    probe = subprocess.run(
        [
            sys.executable,
            "-E",
            "-P",
            "-c",
            "import importlib.util as u;raise SystemExit(0 if u.find_spec('ruff') else 1)",
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _installed_ruff_present(), reason="needs the installed ruff module"
)


def _python_path(kind: str, checkout: Path) -> str | None:
    if kind == "root":
        return str(checkout)
    if kind == "subdirectory":
        return str(checkout / "src")
    if kind == "dot":
        return "."
    if kind == "empty":
        return ""
    return None


@pytest.mark.parametrize("layout", ["package", "module"])
@pytest.mark.parametrize("kind", ["root", "subdirectory", "dot", "empty"])
def test_run_ruff_ignores_a_shadow_ruff_reachable_through_pythonpath(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str, layout: str
) -> None:
    checkout = _checkout(tmp_path)
    sentinel = tmp_path / "sentinel"
    _plant_shadow(checkout / "src" if kind == "subdirectory" else checkout, sentinel, layout)
    monkeypatch.setenv("PYTHONPATH", _python_path(kind, checkout) or "")

    exit_code = ruff_ratchet.run_ruff(["clean.py"], checkout, {})

    assert not sentinel.exists(), "the checkout ruff shadow executed"
    assert exit_code == ruff_ratchet.EXIT_OK


def test_run_ruff_runs_the_installed_ruff_without_pythonpath(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checkout = _checkout(tmp_path)
    (checkout / "bad.py").write_text("import os\n", encoding="utf-8")
    monkeypatch.delenv("PYTHONPATH", raising=False)

    exit_code = ruff_ratchet.run_ruff(["bad.py"], checkout, None)

    assert exit_code == ruff_ratchet.EXIT_VIOLATIONS
    assert "F401" in capsys.readouterr().out


def test_unscrubbed_dash_p_child_does_execute_the_shadow(tmp_path: Path) -> None:
    """Control: the harness can fail, so the passing cases above mean something."""
    checkout = _checkout(tmp_path)
    sentinel = tmp_path / "sentinel"
    _plant_shadow(checkout, sentinel, "package")

    subprocess.run(
        [sys.executable, "-P", "-m", "ruff"],
        check=False,
        cwd=checkout,
        env={"PYTHONPATH": str(checkout)},
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    assert sentinel.exists()


@pytest.mark.parametrize("kind", ["root", "subdirectory", "dot"])
def test_probe_ignores_a_module_that_exists_only_in_the_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    checkout = _checkout(tmp_path)
    (checkout / "src").mkdir()
    module_dir = checkout / "src" if kind == "subdirectory" else checkout
    (module_dir / "checkout_only_probe_mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", _python_path(kind, checkout) or "")

    assert ruff_ratchet._module_available_outside_checkout("checkout_only_probe_mod", checkout) is (
        False
    )


def test_probe_finds_the_installed_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(checkout))

    assert ruff_ratchet._module_available_outside_checkout("ruff", checkout) is True


def test_probe_reports_a_missing_module_as_unavailable(tmp_path: Path) -> None:
    assert (
        ruff_ratchet._module_available_outside_checkout("no_such_module_for_probe", tmp_path)
        is False
    )


@pytest.mark.parametrize(
    "failure",
    [
        subprocess.TimeoutExpired(cmd=["python"], timeout=1),
        FileNotFoundError("no interpreter"),
        PermissionError("denied"),
    ],
)
def test_probe_failure_is_unavailable_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: Exception
) -> None:
    def fail(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise failure

    monkeypatch.setattr(ruff_ratchet.subprocess, "run", fail)

    assert ruff_ratchet._module_available_outside_checkout("ruff", tmp_path) is False


def test_probe_and_ruff_child_share_one_interpreter_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []

    def record(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(ruff_ratchet.subprocess, "run", record)
    monkeypatch.setattr(ruff_ratchet, "_run_subprocess", lambda *_a, **_k: (0, "[]", ""))

    ruff_ratchet.run_ruff(["clean.py"], tmp_path, {})

    prefix = [sys.executable, *ruff_ratchet._ISOLATED_PYTHON_FLAGS]
    assert seen[0][: len(prefix)] == prefix
