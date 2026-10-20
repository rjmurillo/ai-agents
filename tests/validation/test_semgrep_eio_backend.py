"""The semgrep subprocess runs with the posix Eio backend (issue #6708).

semgrep-core's default Eio_linux backend calls io_uring_queue_init, which fails
with "Cannot allocate memory" under concurrent pushes when `ulimit -l` is low.
`EIO_BACKEND=posix` avoids io_uring. These tests start a real child process so
the proof is the environment the child sees, not the arguments passed to a mock.

Coverage:

- positive: on Linux the scan child sees EIO_BACKEND=posix.
- negative: a caller-set io_uring value does not reach the child.
- edge: the version probe, which also starts semgrep, gets the same env.
- edge: off Linux the env is empty, because Windows semgrep-core disables the
  posix backend.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scripts.validation import git_hook_policy as policy

_LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="io_uring is Linux only")
_PRINT_BACKEND = "import os; print(os.environ.get('EIO_BACKEND', 'unset'))"


@_LINUX_ONLY
def test_scan_child_sees_posix_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EIO_BACKEND", raising=False)
    monkeypatch.setattr(policy, "_semgrep_target_batches", lambda targets, _root: [targets])
    monkeypatch.setattr(
        policy, "_semgrep_command", lambda *_a, **_k: [sys.executable, "-c", _PRINT_BACKEND]
    )
    monkeypatch.setattr(policy, "_verify_semgrep_targets", lambda result, *_a: result)

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 0
    assert result.stdout.strip() == "posix"


@_LINUX_ONLY
def test_caller_io_uring_setting_is_overridden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EIO_BACKEND", "io-uring")
    monkeypatch.setattr(policy, "_semgrep_target_batches", lambda targets, _root: [targets])
    monkeypatch.setattr(
        policy, "_semgrep_command", lambda *_a, **_k: [sys.executable, "-c", _PRINT_BACKEND]
    )
    monkeypatch.setattr(policy, "_verify_semgrep_targets", lambda result, *_a: result)

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.stdout.strip() == "posix"


def _fake_semgrep(directory: Path) -> str:
    """Write an executable that prints the EIO_BACKEND it sees for `--version`."""
    script = directory / "fake-semgrep"
    script.write_text(f"#!{sys.executable}\n{_PRINT_BACKEND}\n", encoding="utf-8")
    script.chmod(0o755)
    return str(script)


@_LINUX_ONLY
def test_version_probe_child_sees_posix_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("EIO_BACKEND", raising=False)

    assert policy._probe_semgrep_version(_fake_semgrep(tmp_path), tmp_path) == "posix"


@_LINUX_ONLY
def test_version_probe_overrides_caller_io_uring_setting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EIO_BACKEND", "io-uring")

    assert policy._probe_semgrep_version(_fake_semgrep(tmp_path), tmp_path) == "posix"


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("linux", {"EIO_BACKEND": "posix"}), ("win32", {}), ("darwin", {})],
)
def test_only_linux_gets_the_posix_backend(platform: str, expected: dict[str, str]) -> None:
    """Windows semgrep-core has the posix backend disabled, so it must not be set."""
    assert policy._semgrep_env(platform) == expected
