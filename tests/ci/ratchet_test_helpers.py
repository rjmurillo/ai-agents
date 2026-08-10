"""Shared fixtures for count-ratchet tests."""

from __future__ import annotations

from pathlib import Path


def write_baseline_file(
    tmp_path: Path,
    filename: str,
    value: str,
    *,
    trailing_newline: bool = False,
) -> Path:
    path = tmp_path / filename
    text = f"{value}\n" if trailing_newline else value
    path.write_text(text, encoding="utf-8")
    return path


def make_baseline_writer(
    filename: str,
    *,
    trailing_newline: bool = False,
):
    def _write_baseline(tmp_path: Path, value: str) -> Path:
        return write_baseline_file(
            tmp_path,
            filename,
            value,
            trailing_newline=trailing_newline,
        )

    return _write_baseline
