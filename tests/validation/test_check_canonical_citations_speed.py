"""Equivalence tests for the lazy test-name lookup and the single-pass scan.

The Canonical Citation Check must return the same verdict as the code that
built a full test-name set and parsed every scanned file twice (issue #6734).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from scripts.validation import mirror_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_canonical_citations.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_canonical_citations_speed", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccc = _load_module()


@pytest.fixture(autouse=True)
def _fresh_test_index() -> None:
    ccc.clear_test_caches()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts" / "validation").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_session.py").write_text(
        "def test_session_conformance():\n    pass\n", encoding="utf-8"
    )
    return tmp_path


def _write(repo: Path, body: str) -> Path:
    target = repo / "scripts" / "validation" / "b.py"
    target.write_text(body, encoding="utf-8")
    return target


def _build_varied_test_tree(repo: Path) -> None:
    """Write test files that exercise every branch of the name filter."""
    tests = repo / "tests"
    (tests / "pkg").mkdir()
    (tests / "pkg" / "test_ascii.py").write_text(
        "def test_plain_contract():\n    pass\n\n"
        "class TestBox:\n    def test_boxed_parity(self):\n        pass\n",
        encoding="utf-8",
    )
    # Name appears only inside a string: the substring filter passes, the parse must reject it.
    (tests / "pkg" / "test_text.py").write_text(
        'NOTE = "def test_stringy_equivalence(): pass"\n', encoding="utf-8"
    )
    # Defined only in a nested helper and an uncollected class: not evidence.
    (tests / "pkg" / "test_nested.py").write_text(
        "def helper():\n    def test_nested_conformance():\n        pass\n\n"
        "class Helper:\n    def test_helper_contract(self):\n        pass\n",
        encoding="utf-8",
    )
    # Fullwidth spelling normalizes (NFKC) to the ASCII name, and the file is not ASCII.
    (tests / "pkg" / "test_wide.py").write_text(
        "def \uff54est_wide_contract():\n    pass\n", encoding="utf-8"
    )
    # Non-ASCII definition name.
    (tests / "pkg" / "test_unicode_name.py").write_text(
        "def test_caf\u00e9_parity():\n    pass\n", encoding="utf-8"
    )
    (tests / "pkg" / "test_broken.py").write_text(
        "def test_broken_conformance(:\n", encoding="utf-8"
    )
    (tests / "pkg" / "test_binary.py").write_bytes(b"def test_binary_contract():\n    \xff\n")
    (tests / "pkg" / "dir_named.py").mkdir()


_QUERY_NAMES = [
    "test_session_conformance",
    "test_plain_contract",
    "test_boxed_parity",
    "test_stringy_equivalence",
    "test_nested_conformance",
    "test_helper_contract",
    "test_wide_contract",
    "test_caf\u00e9_parity",
    "test_cafe_parity",
    "test_broken_conformance",
    "test_binary_contract",
    "test_absent_conformance",
    "TEST_PLAIN_CONTRACT",
    "",
]


def test_lazy_lookup_matches_the_full_index_for_every_name(repo: Path) -> None:
    _build_varied_test_tree(repo)
    full = ccc.defined_tests(repo)
    lazy = ccc.LazyTestNames(repo)
    for name in _QUERY_NAMES:
        assert (name in lazy) == (name in full), name
    # Pin the interesting verdicts so the equivalence is not vacuous.
    assert "test_plain_contract" in lazy and "test_boxed_parity" in lazy
    assert "test_wide_contract" in lazy, "NFKC-spelled def in a non-ASCII file must be found"
    assert "test_caf\u00e9_parity" in lazy
    assert "test_stringy_equivalence" not in lazy
    assert "test_nested_conformance" not in lazy
    assert "test_helper_contract" not in lazy
    assert "test_broken_conformance" not in lazy
    assert "test_absent_conformance" not in lazy


def test_lazy_lookup_on_a_repo_without_a_tests_tree_finds_nothing(tmp_path: Path) -> None:
    assert "test_any_conformance" not in ccc.LazyTestNames(tmp_path)


def test_lazy_lookup_rejects_non_string_members(repo: Path) -> None:
    assert 7 not in ccc.LazyTestNames(repo)


def test_wide_spelled_conformance_test_is_evidence_through_scan_file(repo: Path) -> None:
    _build_varied_test_tree(repo)
    ok = '"""Mirrors the validator; see test_wide_contract."""\n'
    assert ccc.scan_file(_write(repo, ok), repo) is None
    bad = '"""Mirrors the validator; see test_stringy_equivalence."""\n'
    assert ccc.scan_file(_write(repo, bad), repo) is not None


def test_run_with_no_conformance_token_never_reads_the_tests_tree(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the tests tree was read")

    monkeypatch.setattr(mirror_evidence, "_test_sources", _boom)
    body = '"""Mirrors the contract. Copied verbatim from the source."""\n'
    _write(repo, body)
    violations, findings = ccc.collect_all(repo)
    assert len(violations) == 1
    assert len(findings) == 1


def test_collect_all_reads_and_extracts_each_file_once(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(repo, '"""Mirrors the contract. Copied verbatim from the source."""\n')
    calls: list[str] = []
    real = ccc._extract_docstring_and_top_comments

    def _counting(source: str) -> str:
        calls.append(source)
        return real(source)

    monkeypatch.setattr(ccc, "_extract_docstring_and_top_comments", _counting)
    ccc.collect_all(repo)
    assert len(calls) == 1


def test_collect_all_reports_an_unreadable_file_like_scan_file(repo: Path) -> None:
    bad = repo / "scripts" / "validation" / "bad.py"
    bad.write_bytes(b'"""Mirrors the contract."""\n\xff\n')
    violations, findings = ccc.collect_all(repo)
    assert [v.path for v in violations] == [bad]
    assert violations[0].matched_token == "read_error"
    assert findings == []
    single = ccc.scan_file(bad, repo)
    assert single is not None and single.matched_token == "read_error"
    assert ccc.scan_copied_contract(bad, repo) is None


def test_collect_all_equals_the_single_file_scans_on_a_mixed_tree(repo: Path) -> None:
    _build_varied_test_tree(repo)
    base = repo / "scripts" / "validation"
    cases = {
        "a.py": '"""Mirrors scripts/x.py. Copied verbatim."""\n',
        "b.py": '"""Mirrors the contract."""\n',
        "c.py": '"""Mirrors the contract; see test_plain_contract. Copied verbatim."""\n',
        "d.py": '"""Mirrors the contract; see test_stringy_equivalence. Copied verbatim."""\n',
        "e.py": '"""Mirrors the contract; see test_wide_contract. Copied verbatim."""\n',
        "f.py": '"""Unrelated."""\n',
    }
    for name, body in cases.items():
        (base / name).write_text(body, encoding="utf-8")
    violations, findings = ccc.collect_all(repo)
    paths = sorted(base.glob("*.py"))
    assert [v.path for v in violations] == [p for p in paths if ccc.scan_file(p, repo)]
    assert [f.path for f in findings] == [p for p in paths if ccc.scan_copied_contract(p, repo)]
    assert {v.path.name for v in violations} == {"b.py", "d.py"}
    assert {f.path.name for f in findings} == {"a.py", "d.py"}
