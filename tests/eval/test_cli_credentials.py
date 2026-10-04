"""Tests for `_cli_credentials`, the one credential order every CLI shares."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.eval._credential_test_support import _cli_credentials as creds

SECRET = "tok-" + "S" * 12


def _counted(calls: list[int]) -> str:
    calls.append(1)
    return SECRET


def _spec(
    *,
    disk: str | None = None,
    probe: bool = False,
    names: tuple[str, ...] = ("PRIMARY_TOKEN", "SECOND_TOKEN"),
    own_login_first: bool = False,
    disk_step: str = creds.STEP_DISK,
) -> creds.CredentialSpec:
    return creds.CredentialSpec(
        transport="fake-cli",
        env_names=names,
        inject_env=names[0],
        read_disk=lambda environ: disk,
        login_probe=lambda executable, environ: probe,
        missing_message="no credential anywhere",
        own_login_first=own_login_first,
        disk_step=disk_step,
    )


def _resolve(
    spec: creds.CredentialSpec,
    environ: dict[str, str],
    fifo_timeout: float | None = None,
) -> creds.ResolvedCredential:
    return creds.resolve_credential(
        spec,
        executable="fake",
        environ=environ,
        stdin_is_tty=False,
        fifo_timeout=fifo_timeout,
    )


def _dotenv(tmp_path: Path, text: str, name: str = "a.env") -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_env_wins_over_dotenv_disk_and_login(tmp_path: Path) -> None:
    environ = {
        "PRIMARY_TOKEN": SECRET,
        creds.DOTENV_FILES_ENV: _dotenv(tmp_path, "PRIMARY_TOKEN=file\n"),
    }

    result = _resolve(_spec(disk="disk", probe=True), environ)

    assert (result.step, result.secret) == (creds.STEP_ENV, SECRET)


def test_env_names_are_read_in_order() -> None:
    result = _resolve(_spec(), {"SECOND_TOKEN": "two", "PRIMARY_TOKEN": "one"})

    assert result.secret == "one"


def test_dotenv_wins_over_disk_and_login(tmp_path: Path) -> None:
    environ = {creds.DOTENV_FILES_ENV: _dotenv(tmp_path, "# c\nSECOND_TOKEN='quoted'\n")}

    result = _resolve(_spec(disk="disk", probe=True), environ)

    assert (result.step, result.secret) == (creds.STEP_DOTENV, "quoted")


def test_dotenv_files_are_tried_in_listed_order_and_globs_expand(tmp_path: Path) -> None:
    (tmp_path / "1.env").write_text("OTHER=1\n", encoding="utf-8")
    (tmp_path / "2.env").write_text("PRIMARY_TOKEN=from-second\n", encoding="utf-8")
    listed = os.pathsep.join([str(tmp_path / "missing.env"), str(tmp_path / "*.env")])

    result = _resolve(_spec(), {creds.DOTENV_FILES_ENV: listed})

    assert result.secret == "from-second"


def test_dotenv_skips_a_directory_and_an_empty_value(tmp_path: Path) -> None:
    (tmp_path / "dir.env").mkdir()
    environ = {
        creds.DOTENV_FILES_ENV: os.pathsep.join(
            [str(tmp_path / "dir.env"), _dotenv(tmp_path, "PRIMARY_TOKEN=\n")]
        )
    }

    result = _resolve(_spec(disk="disk"), environ)

    assert result.step == creds.STEP_DISK


def test_default_dotenv_is_the_repo_root_env_file() -> None:
    [(path, allow_symlink)] = creds._dotenv_candidates({})

    assert Path(path) == Path(creds.__file__).resolve().parents[2] / ".env"
    assert allow_symlink is False


def test_a_symlinked_default_dotenv_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real.env"
    real.write_text("PRIMARY_TOKEN=leaked\n", encoding="utf-8")
    link = tmp_path / ".env"
    link.symlink_to(real)

    assert creds._read_dotenv_file(str(link), 1.0, allow_symlink=False) is None
    assert creds._read_dotenv_file(str(link), 1.0, allow_symlink=True) is not None


def test_fifo_with_a_writer_is_read(tmp_path: Path) -> None:
    import threading

    fifo = tmp_path / "op.env"
    os.mkfifo(fifo)

    def write() -> None:
        with open(fifo, "w", encoding="utf-8") as handle:
            handle.write("PRIMARY_TOKEN=from-fifo\n")

    # Opening for write blocks until the reader opens, as a 1Password mount does.
    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    result = _resolve(_spec(), {creds.DOTENV_FILES_ENV: str(fifo)}, fifo_timeout=5.0)
    writer.join(timeout=5)

    assert (result.step, result.secret) == (creds.STEP_DOTENV, "from-fifo")


def test_fifo_timeout_falls_through(tmp_path: Path) -> None:
    fifo = tmp_path / "op.env"
    os.mkfifo(fifo)

    result = _resolve(_spec(disk="disk"), {creds.DOTENV_FILES_ENV: str(fifo)}, fifo_timeout=0.2)

    assert result.step == creds.STEP_DISK


def test_disk_wins_over_existing_login() -> None:
    result = _resolve(_spec(disk=SECRET, probe=True), {})

    assert (result.step, result.secret) == (creds.STEP_DISK, SECRET)


def test_own_login_beats_the_disk_source_when_the_spec_says_so() -> None:
    spec = _spec(disk=SECRET, probe=True, own_login_first=True)

    result = _resolve(spec, {})

    assert (result.step, result.secret) == (creds.STEP_EXISTING_LOGIN, None)


def test_disk_is_the_last_resort_and_records_its_own_step_name() -> None:
    spec = _spec(
        disk=SECRET,
        probe=False,
        own_login_first=True,
        disk_step=creds.STEP_DISK_GH_FALLBACK,
    )

    result = _resolve(spec, {})

    assert (result.step, result.secret) == (creds.STEP_DISK_GH_FALLBACK, SECRET)


def test_own_login_first_still_yields_to_env_and_dotenv(tmp_path: Path) -> None:
    spec = _spec(disk=SECRET, probe=True, own_login_first=True)

    assert _resolve(spec, {"PRIMARY_TOKEN": "e"}).step == creds.STEP_ENV
    path = _dotenv(tmp_path, "PRIMARY_TOKEN=d\n")
    assert _resolve(spec, {creds.DOTENV_FILES_ENV: path}).step == creds.STEP_DOTENV


def test_own_login_first_with_nothing_found_exits_with_the_message() -> None:
    spec = _spec(probe=False, own_login_first=True)

    with pytest.raises(creds.CredentialNotFoundError):
        _resolve(spec, {})


def test_existing_login_injects_no_token() -> None:
    result = _resolve(_spec(probe=True), {})

    assert (result.step, result.secret) == (creds.STEP_EXISTING_LOGIN, None)
    assert not result.injects_token


def test_prompt_runs_only_on_a_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(creds.getpass, "getpass", lambda prompt: f"  {SECRET}  ")

    result = creds.resolve_credential(_spec(), executable="fake", environ={}, stdin_is_tty=True)

    assert (result.step, result.secret) == (creds.STEP_PROMPT, SECRET)


def test_non_terminal_exits_with_the_transport_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(prompt: str) -> str:
        raise AssertionError("must not prompt without a terminal")

    monkeypatch.setattr(creds.getpass, "getpass", fail)

    with pytest.raises(creds.CredentialNotFoundError, match="no credential anywhere"):
        _resolve(_spec(), {})


def test_an_empty_prompt_answer_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(creds.getpass, "getpass", lambda prompt: "   ")

    with pytest.raises(creds.CredentialNotFoundError):
        creds.resolve_credential(_spec(), executable="fake", environ={}, stdin_is_tty=True)


def test_terminal_detection_defaults_to_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    with pytest.raises(creds.CredentialNotFoundError):
        creds.resolve_credential(_spec(), executable="fake", environ={})


def test_resolution_is_cached_per_transport_and_steps_are_recorded() -> None:
    creds.reset_credential_cache()
    calls: list[int] = []
    spec = creds.CredentialSpec(
        transport="cache-cli",
        env_names=("X",),
        inject_env="X",
        read_disk=lambda environ: _counted(calls),
        login_probe=lambda executable, environ: False,
        missing_message="m",
    )

    first = creds.resolve_cached(spec, executable="x")
    second = creds.resolve_cached(spec, executable="x")

    assert first is second and len(calls) == 1
    assert creds.recorded_steps() == [creds.STEP_DISK]
    creds.reset_credential_cache()
    assert creds.recorded_steps() == []


def test_secret_is_absent_from_repr_and_labels() -> None:
    resolved = creds.ResolvedCredential(creds.STEP_ENV, SECRET)

    assert SECRET not in repr(resolved)
    assert creds.step_label(creds.STEP_EXISTING_LOGIN) == "existing login: user config may load"
    assert creds.step_label(creds.STEP_ENV) == "env"


def test_parse_dotenv_keeps_the_first_value_and_ignores_other_names() -> None:
    text = "A=1\nB=2\nA=3\nnot a pair\n"

    assert creds.parse_dotenv(text, ("A",)) == {"A": "1"}


def test_fifo_open_failure_and_special_files_read_as_not_found(tmp_path: Path) -> None:
    assert creds._read_fifo(str(tmp_path / "absent"), 0.1) is None
    assert creds._read_dotenv_file(str(tmp_path / "absent"), 0.1, allow_symlink=True) is None
    assert creds._read_dotenv_file("/dev/null", 0.1, allow_symlink=True) is None


def test_an_empty_fifo_writer_reads_as_not_found(tmp_path: Path) -> None:
    import threading

    fifo = tmp_path / "empty.env"
    os.mkfifo(fifo)

    def write() -> None:
        with open(fifo, "w", encoding="utf-8"):
            pass

    writer = threading.Thread(target=write, daemon=True)
    writer.start()

    assert creds._read_fifo(str(fifo), 2.0) is None
    writer.join(timeout=5)


def test_a_read_error_on_the_fifo_reads_as_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    fifo = tmp_path / "bad.env"
    os.mkfifo(fifo)
    writer = threading.Thread(
        target=lambda: open(fifo, "w", encoding="utf-8").write("X=1\n"), daemon=True
    )
    writer.start()

    def broken(fd: int, size: int) -> bytes:
        raise OSError("boom")

    monkeypatch.setattr(creds.os, "read", broken)

    assert creds._read_fifo(str(fifo), 2.0) is None


def test_an_unreadable_regular_file_reads_as_not_found(tmp_path: Path) -> None:
    path = tmp_path / "locked.env"
    path.write_text("PRIMARY_TOKEN=x\n", encoding="utf-8")
    path.chmod(0)
    try:
        assert creds._read_dotenv_file(str(path), 0.1, allow_symlink=True) is None
    finally:
        path.chmod(0o600)


def test_empty_entries_in_the_file_list_are_skipped(tmp_path: Path) -> None:
    listed = os.pathsep.join(["", " ", str(tmp_path / "a.env")])

    assert creds._dotenv_candidates({creds.DOTENV_FILES_ENV: listed}) == [
        (str(tmp_path / "a.env"), True)
    ]
