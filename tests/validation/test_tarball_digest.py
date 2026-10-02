"""The tarball digest: compute it once, verify it directly before npm publish.

ADR-113 decision 4. A file that changed, a symlink, a directory, and an empty or
ambiguous download directory each end in a non-zero exit, so a publish step that
runs `verify` first cannot publish bytes the gate did not bind.
"""

from __future__ import annotations

import hashlib
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.tarball_digest import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_MISMATCH,
    EXIT_OK,
    TarballError,
    file_digest,
    single_tarball,
)
from scripts.validation.tarball_digest import main as digest_main

DATA = b"tarball"
GOOD = hashlib.sha256(DATA).hexdigest()


def _tarball(directory: Path, name: str = "pkg-1.0.0.tgz", data: bytes = DATA) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


class TestDigest:
    def test_the_digest_is_the_sha256_of_the_bytes_across_chunks(self, tmp_path: Path) -> None:
        big = b"x" * (3 * (1 << 20) + 5)
        assert file_digest(_tarball(tmp_path, data=big)) == hashlib.sha256(big).hexdigest()

    def test_a_symlink_is_refused(self, tmp_path: Path) -> None:
        link = tmp_path / "link.tgz"
        link.symlink_to(_tarball(tmp_path / "real"))
        with pytest.raises(TarballError, match="symlink"):
            file_digest(link)

    def test_a_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(TarballError, match="regular"):
            file_digest(tmp_path)

    def test_a_missing_file_is_an_os_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            file_digest(tmp_path / "none")


class TestSingleTarball:
    def test_the_one_tarball_is_found(self, tmp_path: Path) -> None:
        path = _tarball(tmp_path)
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        assert single_tarball(tmp_path) == path

    @pytest.mark.parametrize("names", [[], ["a.tgz", "b.tgz"]])
    def test_none_or_several_are_refused(self, tmp_path: Path, names: list[str]) -> None:
        tmp_path.mkdir(exist_ok=True)
        for name in names:
            _tarball(tmp_path, name)
        with pytest.raises(TarballError, match="exactly one"):
            single_tarball(tmp_path)

    def test_only_the_tgz_suffix_counts(self, tmp_path: Path) -> None:
        _tarball(tmp_path, "pkg.tar")
        _tarball(tmp_path, "pkg.tgz.sig")
        with pytest.raises(TarballError):
            single_tarball(tmp_path)

    def test_a_missing_directory_is_an_os_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            single_tarball(tmp_path / "none")


class TestCli:
    def test_compute_prints_and_writes_the_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _tarball(tmp_path / "pack")
        sink = tmp_path / "out"
        argv = ["compute", "--dir", str(tmp_path / "pack"), "--github-output", str(sink)]
        assert digest_main(argv) == EXIT_OK
        assert GOOD in capsys.readouterr().out
        assert sink.read_text(encoding="utf-8") == f"digest={GOOD}\n"

    def test_compute_takes_a_file_and_needs_no_sink(self, tmp_path: Path) -> None:
        assert digest_main(["compute", "--file", str(_tarball(tmp_path))]) == EXIT_OK

    def test_verify_passes_on_a_match_and_names_the_file(self, tmp_path: Path) -> None:
        path = _tarball(tmp_path)
        sink = tmp_path / "out"
        argv = ["verify", "--dir", str(tmp_path), "--expected", GOOD, "--github-output", str(sink)]
        assert digest_main(argv) == EXIT_OK
        assert sink.read_text(encoding="utf-8") == f"file={path}\n"

    def test_verify_fails_when_the_bytes_changed_after_the_gate(self, tmp_path: Path) -> None:
        path = _tarball(tmp_path)
        sink = tmp_path / "out"
        path.write_bytes(b"swapped after the gate")
        argv = ["verify", "--file", str(path), "--expected", GOOD, "--github-output", str(sink)]
        assert digest_main(argv) == EXIT_MISMATCH
        assert not sink.exists()

    def test_verify_fails_for_another_bound_digest(self, tmp_path: Path) -> None:
        argv = ["verify", "--file", str(_tarball(tmp_path)), "--expected", "0" * 64]
        assert digest_main(argv) == EXIT_MISMATCH

    @pytest.mark.parametrize("expected", ["", "abc", "D" * 64, "g" * 64, GOOD + "0"])
    def test_verify_refuses_a_malformed_expected_digest(
        self, tmp_path: Path, expected: str
    ) -> None:
        argv = ["verify", "--file", str(_tarball(tmp_path)), "--expected", expected]
        assert digest_main(argv) == EXIT_CONFIG

    def test_a_missing_file_or_directory_exits_three(self, tmp_path: Path) -> None:
        assert digest_main(["compute", "--file", str(tmp_path / "none")]) == EXIT_EXTERNAL
        assert digest_main(["compute", "--dir", str(tmp_path / "none")]) == EXIT_EXTERNAL

    def test_an_unreadable_file_exits_three(self, tmp_path: Path) -> None:
        path = _tarball(tmp_path)
        path.chmod(0)
        try:
            code = digest_main(["compute", "--file", str(path)])
        finally:
            path.chmod(0o600)
        assert code in (EXIT_EXTERNAL, EXIT_OK)  # root can still read it

    def test_a_symlink_a_directory_and_an_ambiguous_download_exit_two(self, tmp_path: Path) -> None:
        link = tmp_path / "link.tgz"
        link.symlink_to(_tarball(tmp_path / "real"))
        assert digest_main(["compute", "--file", str(link)]) == EXIT_CONFIG
        assert digest_main(["compute", "--file", str(tmp_path)]) == EXIT_CONFIG
        _tarball(tmp_path / "two", "a.tgz")
        _tarball(tmp_path / "two", "b.tgz")
        assert digest_main(["compute", "--dir", str(tmp_path / "two")]) == EXIT_CONFIG

    def test_file_and_dir_are_mutually_exclusive_and_one_is_required(self, tmp_path: Path) -> None:
        for argv in (["compute"], ["compute", "--file", "a", "--dir", "b"]):
            with pytest.raises(SystemExit) as stop:
                digest_main(argv)
            assert stop.value.code == 2

    def test_the_entry_point_guard_returns_the_exit_code(self) -> None:
        script = Path(digest_main.__code__.co_filename)
        with patch.object(sys, "argv", [str(script), "compute"]), pytest.raises(SystemExit) as stop:
            runpy.run_path(str(script), run_name="__main__")
        assert stop.value.code == 2

    def test_the_script_runs_under_bare_python(self, tmp_path: Path) -> None:
        import subprocess

        script = Path(digest_main.__code__.co_filename)
        result = subprocess.run(
            [sys.executable, "-S", str(script), "compute", "--file", str(_tarball(tmp_path))],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )  # fmt: skip
        assert result.returncode == 0, result.stderr
        assert GOOD in result.stdout
