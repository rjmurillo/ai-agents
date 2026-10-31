"""Equivalence tests for the speed-up of check_test_tree_writes.py (issue #6734).

The gate prefilters files lexically and fans large batches out to worker
interpreters. Both must return exactly what the original parse-everything,
serial scan returned. The base behavior tests live in
``test_check_test_tree_writes.py``. ``_oracle_scan`` is the original scan,
built on the unchanged ``_WriteDetector``.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Import the module under test.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
import check_test_tree_writes as cttw

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "check_test_tree_writes.py"
)


def _oracle_scan(source: str) -> list[tuple[int, str]]:
    """Original scan: parse every file, no prefilter."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    detector = cttw._WriteDetector()
    detector.visit(tree)
    return detector.findings


# (id, source, expect_findings)
_EQUIVALENCE_CORPUS = [
    ("flagged_write_text", "(ROOT / 'a').write_text('x')\n", True),
    ("flagged_open_w", "open(REPO_ROOT / 'a', 'w')\n", True),
    ("flagged_shutil", "import shutil\nshutil.copy(src, PROJECT_ROOT / 'a')\n", True),
    ("flagged_in_fstring", "x = f\"{(_REPO_ROOT / 'a').touch()}\"\n", True),
    ("flagged_mkdir_multiline", "(\n    _PROJECT_ROOT\n    / 'a'\n).mkdir()\n", True),
    ("clean_tmp_path", "(tmp_path / 'a').write_text('x')\nROOT = 1\n", False),
    ("clean_root_no_write", "x = ROOT / 'a'\nprint(x)\n", False),
    ("clean_write_no_root", "(base / 'a').write_text('x')\n", False),
    ("clean_root_only_in_comment", "# ROOT\n(base / 'a').write_text('x')\n", False),
    ("clean_root_substring", "ROOTS = 1\nMY_ROOT = 2\n(base / 'a').write_text('x')\n", False),
    ("clean_sanctioned", "(ROOT / '.pytest_tmp' / 'a').write_text('x')\n", False),
    ("clean_read_only_open", "open(ROOT / 'a', 'r')\n", False),
    ("syntax_error", "ROOT = (\nopen(\n", False),
    ("empty", "", False),
    ("null_byte", "ROOT = 1\x00\nopen(ROOT)\n", False),
    # The parser NFKC-normalizes identifiers: these are the Names ROOT and
    # write_text although the source text contains neither. A lexical
    # prefilter that trusts raw text would skip the file and change the verdict.
    ("flagged_fullwidth_root", "(ＲＯＯＴ / 'a').write_text('x')\n", True),
    ("flagged_fullwidth_method", "(ROOT / 'a').ｗrite_text('x')\n", True),
    ("flagged_non_ascii_elsewhere", "# café\n(ROOT / 'a').write_text('x')\n", True),
]


def _corpus_ids() -> list[str]:
    return [case[0] for case in _EQUIVALENCE_CORPUS]


class TestPrefilterEquivalence:
    def test_fullwidth_corpus_entries_are_flagged_by_the_oracle(self) -> None:
        """Guards the corpus: the NFKC cases must be real findings, not typos."""
        for name, source, expect in _EQUIVALENCE_CORPUS:
            if name.startswith("flagged_fullwidth"):
                assert expect
                assert _oracle_scan(source), name

    def test_fullwidth_root_defeats_a_raw_text_prefilter(self) -> None:
        """Proves the NFKC case differs: raw-text matching alone would skip it."""
        source = "(ＲＯＯＴ / 'a').write_text('x')\n"
        assert not cttw._ROOT_TOKEN_RE.search(source)
        assert _oracle_scan(source)
        assert cttw._scan_source(source, "t.py") == _oracle_scan(source)

    def test_prefilter_skips_only_files_without_findings(self) -> None:
        """If the prefilter rejects a file the oracle must find nothing in it."""
        for name, source, _ in _EQUIVALENCE_CORPUS:
            if not cttw._may_have_findings(source):
                assert _oracle_scan(source) == [], name

    @pytest.mark.parametrize(("name", "source", "expect"), _EQUIVALENCE_CORPUS, ids=_corpus_ids())
    def test_scan_source_matches_oracle(self, name: str, source: str, expect: bool) -> None:
        got = cttw._scan_source(source, f"{name}.py")
        assert got == _oracle_scan(source)
        assert bool(got) is expect

    def test_scan_source_matches_oracle_on_real_test_files(self) -> None:
        """Differential run over this repo's own validation tests."""
        files = sorted(Path(__file__).parent.glob("test_*.py"))
        assert len(files) > 50
        for path in files:
            source = path.read_text(encoding="utf-8")
            assert cttw._scan_source(source, str(path)) == _oracle_scan(source), path.name

    def test_prefilter_patterns_cover_every_detector_constant(self) -> None:
        """Adding a binding or write method must widen the prefilter too."""
        for binding in cttw._ROOT_BINDINGS:
            assert cttw._ROOT_TOKEN_RE.search(f"x = {binding} / 'a'")
        for method in cttw._WRITE_METHODS | cttw._SHUTIL_WRITE_FUNCS:
            assert cttw._WRITE_TOKEN_RE.search(f"obj.{method}(x)")


def _write_corpus_files(directory: Path, count: int) -> list[Path]:
    """Create *count* test files; every fifth one holds a distinct finding."""
    paths = []
    for i in range(count):
        if i % 5 == 0:
            body = "\n" * i + "(ROOT / 'a').write_text('x')\n"
        elif i % 7 == 0:
            body = "ROOT = 1\n"
        else:
            body = f"def test_{i}(tmp_path):\n    (tmp_path / 'a').write_text('x')\n"
        path = directory / f"test_gen_{i:03d}.py"
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return paths


class TestParallelEquivalence:
    def test_parallel_matches_serial_and_keeps_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _write_corpus_files(tmp_path, 40)
        serial = [cttw._scan_file(p) for p in paths]
        monkeypatch.setattr(cttw, "_PARALLEL_MIN_FILES", 1)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        parallel = cttw._scan_files_parallel(paths, 3)
        assert parallel == serial
        # A scrambled merge would move a finding to the wrong file or line.
        assert [bool(f) for f in serial].count(True) == 8
        assert cttw._scan_files(paths) == serial

    def test_worker_count_above_file_count(self, tmp_path: Path) -> None:
        paths = _write_corpus_files(tmp_path, 2)
        assert cttw._scan_files_parallel(paths, 5) == [cttw._scan_file(p) for p in paths]

    def test_small_batches_stay_serial(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _write_corpus_files(tmp_path, 3)

        def _boom(*_a: object, **_k: object) -> None:
            raise AssertionError("parallel path used for a small batch")

        monkeypatch.setattr(cttw, "_scan_files_parallel", _boom)
        assert cttw._scan_files(paths) == [cttw._scan_file(p) for p in paths]

    def test_unreadable_and_binary_files_match_serial(self, tmp_path: Path) -> None:
        binary = tmp_path / "test_bin.py"
        binary.write_bytes(b"\xff\xfe\x00ROOT open")
        missing = tmp_path / "test_missing.py"
        paths = [binary, missing, *_write_corpus_files(tmp_path, 6)]
        assert cttw._scan_files_parallel(paths, 2) == [cttw._scan_file(p) for p in paths]

    def test_falls_back_to_serial_when_workers_cannot_start(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _write_corpus_files(tmp_path, 12)
        expected = [cttw._scan_file(p) for p in paths]

        def _no_spawn(*_a: object, **_k: object) -> None:
            raise OSError("no processes")

        monkeypatch.setattr(cttw, "_PARALLEL_MIN_FILES", 1)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        monkeypatch.setattr(cttw.subprocess, "Popen", _no_spawn)
        assert cttw._scan_files_parallel(paths, 3) is None
        assert cttw._scan_files(paths) == expected

    def test_falls_back_to_serial_when_a_worker_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        paths = _write_corpus_files(tmp_path, 12)
        expected = [cttw._scan_file(p) for p in paths]
        # An unknown flag makes the worker exit non-zero.
        monkeypatch.setattr(cttw, "_WORKER_FLAG", "--no-such-worker-mode")
        monkeypatch.setattr(cttw, "_PARALLEL_MIN_FILES", 1)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        assert cttw._scan_files_parallel(paths, 3) is None
        assert cttw._scan_files(paths) == expected

    def test_worker_mode_reads_json_and_writes_json(self, tmp_path: Path) -> None:
        paths = _write_corpus_files(tmp_path, 6)
        result = subprocess.run(
            [sys.executable, "-I", str(_SCRIPT), "--scan-worker"],
            input=json.dumps([str(p) for p in paths]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert result.returncode == 0
        decoded = [[tuple(f) for f in per_file] for per_file in json.loads(result.stdout)]
        assert decoded == [cttw._scan_file(p) for p in paths]

    def test_end_to_end_verdict_unchanged_in_parallel_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        paths = _write_corpus_files(tmp_path, 30)
        monkeypatch.setattr(cttw, "_PARALLEL_MIN_FILES", 1)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        got = cttw.check_test_tree_writes(tmp_path)
        expected = [(p, lineno, desc) for p in sorted(paths) for lineno, desc in cttw._scan_file(p)]
        assert sorted(got) == sorted(expected)
        assert len(got) == 6
        assert cttw.validate_test_tree_writes(tmp_path) is False

    def test_end_to_end_clean_repo_passes_in_parallel_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        for i in range(30):
            (tmp_path / f"test_ok_{i}.py").write_text(
                "def test_x(tmp_path):\n    (tmp_path / 'a').write_text('x')\n", encoding="utf-8"
            )
        monkeypatch.setattr(cttw, "_PARALLEL_MIN_FILES", 1)
        monkeypatch.setattr(os, "cpu_count", lambda: 4)
        assert cttw.validate_test_tree_writes(tmp_path) is True
