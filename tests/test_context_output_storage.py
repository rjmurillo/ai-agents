"""Tests for context-output filesystem and Git-index access."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).parent.parent
        / ".claude"
        / "skills"
        / "context-optimizer"
        / "scripts"
    ),
)

import context_output_storage as storage


def _raise_os_error(*args, **kwargs):
    raise OSError("Git unavailable")


def test_read_staged_text_maps_process_error(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.subprocess, "run", _raise_os_error)

    with pytest.raises(RuntimeError, match="Unable to read the Git index"):
        storage._read_staged_text(tmp_path / "source.md", tmp_path)


def test_read_staged_text_rejects_non_utf8(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"\xff"),
    )

    with pytest.raises(ValueError, match="not UTF-8"):
        storage._read_staged_text(tmp_path / "source.md", tmp_path)


def test_read_staged_text_returns_none_for_missing_index_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b""),
    )

    assert storage._read_staged_text(tmp_path / "source.md", tmp_path) is None


def test_staged_paths_maps_process_error(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.subprocess, "run", _raise_os_error)

    with pytest.raises(RuntimeError, match="Unable to list the Git index"):
        storage._staged_paths_under(tmp_path, tmp_path)


def test_staged_paths_maps_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        storage.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=b""),
    )

    with pytest.raises(RuntimeError, match="Unable to list the Git index"):
        storage._staged_paths_under(tmp_path, tmp_path)


def test_detail_names_returns_empty_for_missing_directory(tmp_path):
    assert storage._detail_names(tmp_path / "missing", tmp_path, staged=False) == set()


def test_output_files_returns_empty_for_missing_root(tmp_path):
    assert storage._output_files(tmp_path / "missing", tmp_path, staged=False) == set()


def test_output_files_reports_file_root(tmp_path):
    output = tmp_path / "output.md"
    output.write_text("output\n", encoding="utf-8")

    assert storage._output_files(output, tmp_path, staged=False) == {"output.md"}


def test_manifest_path_value_requires_nonempty_string():
    with pytest.raises(ValueError, match="must be a non-empty string"):
        storage._manifest_path_value(None, "source")
