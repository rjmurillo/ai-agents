"""Tests for scripts/metrics/source_module.py: source wins over a stale .pyc."""

from __future__ import annotations

import os
import py_compile
import sys
from importlib import util
from pathlib import Path

import pytest

from scripts.metrics.source_module import load_source_module

OLD = "VALUE = 'old'\n"
NEW = "VALUE = 'new'\n"


def _plant_stale_pyc(path: Path) -> None:
    path.write_text(OLD, encoding="utf-8")
    os.utime(path, (1_700_000_000, 1_700_000_000))
    py_compile.compile(str(path), cfile=util.cache_from_source(str(path)), doraise=True)
    path.write_text(NEW, encoding="utf-8")  # same size as OLD
    os.utime(path, (1_700_000_000, 1_700_000_000))  # same mtime as OLD


def test_stale_pyc_with_matching_size_and_mtime_loses_to_source(tmp_path: Path) -> None:
    hook = tmp_path / "small_hook.py"
    _plant_stale_pyc(hook)
    assert len(OLD) == len(NEW)
    spec = util.spec_from_file_location("stale_probe", hook)
    assert spec is not None and spec.loader is not None
    default_loaded = util.module_from_spec(spec)
    spec.loader.exec_module(default_loaded)
    assert default_loaded.VALUE == "old"  # the default loader is fooled: the test bites
    assert load_source_module("small_hook_probe", hook).VALUE == "new"
    sys.modules.pop("small_hook_probe", None)


def test_loader_writes_no_bytecode(tmp_path: Path) -> None:
    hook = tmp_path / "plain_hook.py"
    hook.write_text(NEW, encoding="utf-8")
    load_source_module("plain_hook_probe", hook)
    sys.modules.pop("plain_hook_probe", None)
    assert not (tmp_path / "__pycache__").exists()


def test_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        load_source_module("absent_probe", tmp_path / "absent.py")
    sys.modules.pop("absent_probe", None)
