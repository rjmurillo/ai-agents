"""CI must install the resolution ``uv.lock`` pins.

``uv pip install -e ".[dev]"`` re-resolves from ``pyproject.toml`` and ignores
the lock entirely. Measured against this repo's lock on 2026-07-28, 30 packages
drifted, including ``mypy`` 2.1.0 to 2.3.0, ``pytest`` 9.0.3 to 9.1.1 and
``ruff`` 0.15.16 to 0.15.22. Every PR was graded by different tools than the
lock pins, and a compromised release of any dependency reached the runner
without a lockfile change to review (issue #3603).

``pytest.yml`` already carries a comment describing the ``ruff`` half of this
drift and works around it per-command with ``uv run --frozen``. That workaround
only covers the commands somebody remembered to wrap; the install itself is the
single place that fixes all of them.

The install logic lives in ``scripts/ci/install_locked_deps.py`` rather than in
the action, per ADR-006. These tests drive that module directly with a stubbed
``uv`` on ``PATH``, so the branch decisions are checked by running them instead
of by pattern matching a shell string. Two tests still read the action, to pin
that it delegates rather than growing its own copy of the logic back.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ACTION = REPO_ROOT / ".github/actions/setup-code-env/action.yml"
SCRIPT = REPO_ROOT / "scripts/ci/install_locked_deps.py"

STUB_UV = "#!/bin/bash\necho \"$*\" >> \"$UVLOG\"\nexit ${UVFAIL:-0}\n"


def _load_module():
    spec = importlib.util.spec_from_file_location("install_locked_deps", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ild = _load_module()


def _install_step() -> str:
    action = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    for step in action["runs"]["steps"]:
        if step.get("name") == "Install Python dependencies":
            return step["run"]
    raise AssertionError("setup-code-env has no 'Install Python dependencies' step")


@pytest.fixture
def uv_calls(tmp_path, monkeypatch):
    """Put a recording stub ``uv`` on ``PATH`` and return a reader for its log.

    The real command installs into the system interpreter. Running it in a test
    would mutate the machine running the suite, so the stub records argv and
    exits 0. What is under test is which commands are issued and in what order,
    which the stub captures exactly.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "uv"
    stub.write_text(STUB_UV, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "uv.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("UVLOG", str(log))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return lambda: [line for line in log.read_text(encoding="utf-8").splitlines() if line]


def _project(tmp_path: Path, *, lock: bool = True, pyproject: bool = True) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    if pyproject:
        (root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    if lock:
        (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    return root


class TestTheLockedPath:
    def test_the_install_reads_the_lock_file(self, tmp_path, uv_calls):
        ild.main([str(_project(tmp_path))])
        assert any("export --frozen" in c and "--no-emit-project" in c for c in uv_calls())

    def test_the_locked_export_is_what_gets_installed(self, tmp_path, uv_calls):
        """An export nobody installs from pins nothing."""
        ild.main([str(_project(tmp_path))])
        exported = [c for c in uv_calls() if c.startswith("export ")]
        installed = [c for c in uv_calls() if "pip install --system -r" in c]
        assert exported and installed
        target = exported[0].split("--output-file ")[1]
        assert target in installed[0], "installed from a different file than was exported"

    def test_the_project_is_installed_without_re_resolving(self, tmp_path, uv_calls):
        """A plain ``-e .`` after the pinned install would resolve again."""
        ild.main([str(_project(tmp_path))])
        assert "pip install --system --no-deps -e ." in uv_calls()

    def test_the_export_precedes_the_install(self, tmp_path, uv_calls):
        calls = uv_calls
        ild.main([str(_project(tmp_path))])
        recorded = calls()
        assert recorded[0].startswith("export ")

    def test_the_project_is_installed_after_the_pinned_set(self, tmp_path, uv_calls):
        """Installing the project first would let it resolve the pinned names."""
        ild.main([str(_project(tmp_path))])
        recorded = uv_calls()
        assert recorded.index("pip install --system --no-deps -e .") == len(recorded) - 1

    def test_the_dev_extra_is_exported(self, tmp_path, uv_calls):
        """CI installs only this extra; dropping it loses every test tool."""
        ild.main([str(_project(tmp_path))])
        assert "--extra dev" in uv_calls()[0]

    def test_no_unpinned_extra_install_on_the_locked_path(self, tmp_path, uv_calls):
        ild.main([str(_project(tmp_path))])
        assert not any(".[dev]" in c for c in uv_calls())

    def test_the_export_lands_in_the_runner_temp_directory(self, tmp_path, uv_calls):
        """A relative path would litter the checkout and dirty the diff."""
        ild.main([str(_project(tmp_path))])
        assert str(tmp_path) in uv_calls()[0]


class TestTheFallbackPath:
    def test_a_project_without_a_lock_still_installs(self, tmp_path, uv_calls):
        """A consumer of this action without a lock must not hard fail."""
        assert ild.main([str(_project(tmp_path, lock=False))]) == 0
        assert uv_calls() == ["pip install --system -e .[dev]"]

    def test_the_fallback_does_not_export(self, tmp_path, uv_calls):
        ild.main([str(_project(tmp_path, lock=False))])
        assert not any(c.startswith("export ") for c in uv_calls())

    def test_a_directory_without_a_pyproject_installs_nothing(self, tmp_path, uv_calls):
        assert ild.main([str(_project(tmp_path, pyproject=False, lock=False))]) == 0
        assert uv_calls() == []

    def test_a_lock_without_a_pyproject_installs_nothing(self, tmp_path, uv_calls):
        """The lock alone is not a project; uv would fail on it."""
        assert ild.main([str(_project(tmp_path, pyproject=False))]) == 0
        assert uv_calls() == []


class TestFailurePropagation:
    def test_a_failing_uv_stops_the_run(self, tmp_path, uv_calls, monkeypatch):
        """Swallowing the failure would leave the runner unpinned and green."""
        monkeypatch.setenv("UVFAIL", "3")
        with pytest.raises(SystemExit) as exc:
            ild.main([str(_project(tmp_path))])
        assert exc.value.code == 3

    def test_a_failing_export_does_not_install(self, tmp_path, uv_calls, monkeypatch):
        """Installing from a partial or stale export is worse than failing."""
        monkeypatch.setenv("UVFAIL", "3")
        with pytest.raises(SystemExit):
            ild.main([str(_project(tmp_path))])
        assert not any("pip install" in c for c in uv_calls())

    def test_the_failure_is_reported_without_a_traceback(self, tmp_path):
        """A traceback buries uv's own error under Python frames in CI output."""
        root = _project(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "uv").write_text("#!/bin/bash\necho boom >&2\nexit 3\n", encoding="utf-8")
        (bin_dir / "uv").chmod(0o755)
        env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
        done = subprocess.run(
            [sys.executable, str(SCRIPT), str(root)],
            capture_output=True, text=True, encoding="utf-8", env=env
        )
        assert done.returncode == 3
        assert "Traceback" not in done.stderr


class TestTheActionDelegates:
    def test_the_action_calls_the_extracted_script(self):
        """ADR-006: the branching belongs in Python, not in the YAML."""
        assert "scripts/ci/install_locked_deps.py" in _install_step()

    def test_the_action_carries_no_install_logic_of_its_own(self):
        """Guards the extraction against a later inline copy creeping back."""
        body = _install_step()
        assert "uv pip install" not in body
        assert "uv export" not in body

    def test_the_extracted_script_exists_and_is_a_module(self):
        assert SCRIPT.is_file()

    def test_the_script_imports_nothing_outside_the_standard_library(self):
        """It runs before the dependencies it installs exist."""
        source = SCRIPT.read_text(encoding="utf-8")
        third_party = ("import yaml", "import requests", "from pydantic", "import click")
        assert not any(token in source for token in third_party)

    def test_the_lock_file_the_action_depends_on_exists(self):
        assert (REPO_ROOT / "uv.lock").is_file()


class TestTheExportPathCannotBecomeAFlag:
    """The one externally-set value that reaches argv is the export path.

    Semgrep flags the ``subprocess.run`` calls as command injection. They are
    list-form with ``shell=False``, so no shell parses them and CWE-78 does not
    reach: an argument containing ``; id`` is passed through literally. What
    does survive that argument is CWE-88: ``RUNNER_TEMP`` is read from the
    environment, and a value starting with ``-`` produces an argv entry shaped
    like an option rather than a path.
    """

    @pytest.mark.parametrize(
        ("runner_temp", "label"),
        [
            ("-rf", "a bare flag"),
            ("--output-file=/etc/passwd", "a long option with a value"),
            ("-", "a lone dash"),
        ],
    )
    def test_a_flag_shaped_runner_temp_never_reaches_argv(
        self, tmp_path, uv_calls, monkeypatch, runner_temp, label
    ):
        monkeypatch.setenv("RUNNER_TEMP", runner_temp)
        ild.main([str(_project(tmp_path))])
        for call in uv_calls():
            for word in call.split():
                assert not word.startswith(f"{runner_temp}/"), f"{label}: {call}"

    @pytest.mark.parametrize(
        ("runner_temp", "label"),
        [
            ("", "unset in practice"),
            ("relative/dir", "not absolute"),
        ],
    )
    def test_an_unusable_runner_temp_falls_back(
        self, tmp_path, uv_calls, monkeypatch, runner_temp, label
    ):
        monkeypatch.setenv("RUNNER_TEMP", runner_temp)
        ild.main([str(_project(tmp_path))])
        exports = [c for c in uv_calls() if c.startswith("export ")]
        assert exports, label
        assert f"/tmp/{ild.EXPORT_NAME}" in exports[0], label

    def test_an_absolute_runner_temp_is_still_honoured(self, tmp_path, uv_calls, monkeypatch):
        """The narrowing must not break the real GitHub Actions value."""
        target = tmp_path / "runner-temp"
        target.mkdir()
        monkeypatch.setenv("RUNNER_TEMP", str(target))
        ild.main([str(_project(tmp_path))])
        exports = [c for c in uv_calls() if c.startswith("export ")]
        assert str(target / ild.EXPORT_NAME) in exports[0]

    def test_the_subprocess_calls_stay_shell_free(self):
        """A shell would make CWE-78 reachable. Hold the list form."""
        source = SCRIPT.read_text(encoding="utf-8")
        assert "shell=True" not in source
        assert "os.system" not in source
