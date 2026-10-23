"""Evidence-contract fixtures for check_canonical_citations (issue #5399).

Each test is one of the six fixtures the issue requires. The claim "B mirrors
A" still needs evidence, but the evidence may be structural or executable
instead of copied prose.
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
    spec = importlib.util.spec_from_file_location("check_canonical_citations_ev", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ccc = _load_module()


@pytest.fixture(autouse=True)
def _fresh_test_index() -> None:
    """The defined-test index is cached per repo root; each test builds its own."""
    ccc.clear_test_caches()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts" / "validation").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_session.py").write_text(
        "def test_session_conformance():\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "scripts" / "validate_session_json.py").write_text(
        "CONTRADICTION_PATTERNS = ()\n", encoding="utf-8"
    )
    return tmp_path


def _write(repo: Path, body: str) -> Path:
    target = repo / "scripts" / "validation" / "b.py"
    target.write_text(body, encoding="utf-8")
    return target


# --- 1. conformance-by-test: accepted, no copied contract text --------------


def test_conformance_test_symbol_without_path_or_copy_is_accepted(repo: Path) -> None:
    doc = '"""Mirrors the session validator.\n\nConformance: test_session_conformance.\n"""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path, repo) is None
    assert ccc.scan_copied_contract(path, repo) is None


def test_conformance_token_naming_no_defined_test_is_not_evidence(repo: Path) -> None:
    doc = '"""Mirrors the session validator; see test_contract_nowhere."""\n'
    path = _write(repo, doc)
    violation = ccc.scan_file(path, repo)
    assert violation is not None
    assert violation.matched_token == "mirrors the"


def test_copy_naming_no_defined_test_is_still_a_finding(repo: Path) -> None:
    doc = '"""Mirrors the validator. Copied verbatim; test_contract_nowhere guards it."""\n'
    assert ccc.scan_copied_contract(_write(repo, doc), repo) is not None


def test_repo_without_tests_dir_yields_no_defined_tests(tmp_path: Path) -> None:
    assert ccc.defined_tests(tmp_path) == frozenset()


def test_unreadable_test_file_is_skipped(repo: Path) -> None:
    (repo / "tests" / "test_binary.py").write_bytes(b"\xff\xfe\x00bad")
    assert "test_session_conformance" in ccc.defined_tests(repo)


def test_shared_import_is_accepted_without_path(repo: Path) -> None:
    body = (
        '"""Mirrors the CONTRADICTION_PATTERNS contract by importing it."""\n'
        "from scripts.validate_session_json import CONTRADICTION_PATTERNS\n"
    )
    path = _write(repo, body)
    assert ccc.scan_file(path, repo) is None


def test_direct_import_alias_is_accepted_without_path(repo: Path) -> None:
    body = (
        '"""Mirrors the session validator through the canonical alias."""\n'
        "import scripts.validate_session_json as canonical\n"
    )
    assert ccc.scan_file(_write(repo, body), repo) is None


def test_direct_import_without_alias_is_accepted_by_dotted_name(repo: Path) -> None:
    body = (
        '"""Mirrors scripts.validate_session_json by importing it."""\n'
        "import scripts.validate_session_json\n"
    )
    assert ccc.scan_file(_write(repo, body), repo) is None


def test_direct_stdlib_import_is_not_evidence(repo: Path) -> None:
    body = '"""Mirrors the os.path semantics."""\nimport os.path\n'
    assert ccc.scan_file(_write(repo, body), repo) is not None


def test_stdlib_import_is_not_evidence(repo: Path) -> None:
    body = '"""Mirrors the Path semantics."""\nfrom pathlib import Path\n'
    assert ccc.scan_file(_write(repo, body), repo) is not None


# --- 2. unsupported-equivalence: rejected -----------------------------------


@pytest.mark.parametrize(
    "docstring",
    [
        "Mirrors the session validator.",
        "Matches the validator exactly.",
        "Same as the canonical exit codes.",
        "Mirrors the validator. Stricter than canonical: blocks locally.",
        "Mirrors the validator; a generic test exists.",
    ],
)
def test_unsupported_equivalence_is_rejected(repo: Path, docstring: str) -> None:
    violation = ccc.scan_file(_write(repo, f'"""{docstring}"""\n'), repo)
    assert violation is not None


# --- 3. intentional-divergence: accepted with path plus rationale -----------


def test_divergence_with_reason_and_path_is_accepted_without_a_copy(repo: Path) -> None:
    doc = (
        '"""Mirrors scripts/validate_session_json.py.\n\n'
        "Stricter than canonical: the validator warns, this guard blocks, because\n"
        'CI bounced this check three times.\n"""\n'
    )
    path = _write(repo, doc)
    assert ccc.scan_file(path, repo) is None
    assert ccc.scan_copied_contract(path, repo) is None


# --- 4. stale-copy: finding recommends eliminating the copy -----------------


def test_copied_contract_without_structure_yields_elimination_finding(repo: Path) -> None:
    doc = (
        '"""Mirrors scripts/validate_session_json.py.\n\n'
        "Verbatim contract copied character-for-character from the validator:\n"
        '    PATTERN = a|b|c\n"""\n'
    )
    finding = ccc.scan_copied_contract(_write(repo, doc), repo)
    assert finding is not None
    assert "eliminate the copy" in finding.remediation.lower()
    for option in ("import", "generate", "conformance test"):
        assert option in finding.remediation.lower()


def test_copy_backed_by_conformance_test_is_not_a_finding(repo: Path) -> None:
    doc = (
        '"""Mirrors scripts/validate_session_json.py.\n\n'
        "Copied verbatim here; test_session_conformance fails when the source moves.\n"
        '"""\n'
    )
    assert ccc.scan_copied_contract(_write(repo, doc), repo) is None


def test_copy_findings_are_reported_but_never_block(repo: Path, capsys) -> None:
    doc = '"""Mirrors scripts/a.py. Copied verbatim from the source."""\n'
    _write(repo, doc)
    assert ccc.main(["--repo-root", str(repo), "--strict"]) == 0
    out = capsys.readouterr().out
    assert "[PASS] No uncited mirror-claims found in 1 file(s) examined." in out
    assert "[WARN] 1 copied-contract" in out
    assert "eliminate the copy" in out.lower()


# --- 5. generated-projection: not independent authored duplication ----------


def test_generated_projection_is_evidence_and_not_a_copy_finding(repo: Path) -> None:
    doc = '"""Mirrors the schema. Copied verbatim; generated from schema.yaml."""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path, repo) is None
    assert ccc.scan_copied_contract(path, repo) is None


# --- 6. transaction-evidence: no durable copy is required -------------------


def test_path_reference_alone_passes_without_a_verbatim_quote(repo: Path) -> None:
    doc = '"""Matches scripts/validate_session_json.py exit codes."""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path, repo) is None
    assert ccc.scan_copied_contract(path, repo) is None


def test_commit_scoped_verification_text_is_not_a_mirror_claim(repo: Path) -> None:
    doc = '"""Verified against scripts/a.py at commit abc1234; conformance passes."""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path, repo) is None
    assert ccc.scan_copied_contract(path, repo) is None


def test_copy_findings_read_as_advisory_through_the_wrapper(repo: Path, capsys) -> None:
    from scripts.validation import checks_citations

    _write(repo, '"""Mirrors scripts/a.py. Copied verbatim from the source."""\n')
    assert ccc.main(["--repo-root", str(repo)]) == 0
    outcome = checks_citations._status_outcome(
        "validate_canonical_citations", "s", capsys.readouterr().out
    )
    assert outcome.state.name == "FAIL"
    assert outcome.reason == "advisory.findings"
    assert outcome.findings == 1


@pytest.mark.parametrize(
    "imports",
    [
        "import pytest\n",
        "import pytest as canonical\n",
        "from pytest import fixture\n",
        "import yaml.constructor\n",
    ],
)
def test_third_party_import_is_not_evidence(repo: Path, imports: str) -> None:
    doc = '"""Mirrors pytest fixture semantics: pytest, canonical, yaml.constructor."""'
    body = f"{doc}\n{imports}"
    assert ccc.scan_file(_write(repo, body), repo) is not None


def test_sibling_module_import_is_evidence(repo: Path) -> None:
    (repo / "scripts" / "validation" / "schema_rules.py").write_text(
        "SCHEMA_RULES = 1\n", encoding="utf-8"
    )
    body = '"""Mirrors the SCHEMA_RULES contract."""\nfrom schema_rules import SCHEMA_RULES\n'
    assert ccc.scan_file(_write(repo, body), repo) is None


def test_lib_package_import_is_evidence() -> None:
    from scripts.validation import mirror_evidence as me

    owned = me.owned_roots(REPO_ROOT, REPO_ROOT / "scripts" / "validation")
    assert {"scripts", "build", "ai_review_common"} <= owned
    assert "pytest" not in owned
    assert "os" not in owned


def _make_canonpkg(repo: Path) -> None:
    (repo / "canonpkg").mkdir()
    (repo / "canonpkg" / "__init__.py").write_text("CANON = 1\n", encoding="utf-8")


def test_import_ownership_uses_the_scanned_repo_root(repo: Path) -> None:
    _make_canonpkg(repo)
    body = '"""Mirrors the CANON contract by importing it."""\nfrom canonpkg import CANON\n'
    path = _write(repo, body)
    assert ccc.scan_file(path, repo) is None
    assert ccc.scan_copied_contract(path, repo) is None
    assert ccc.collect_violations(repo) == []


def test_checkout_only_package_is_not_evidence_in_another_repo(repo: Path) -> None:
    assert (REPO_ROOT / "build").is_dir()
    body = '"""Mirrors the build contract by importing it."""\nfrom build import contract\n'
    path = _write(repo, body)
    assert ccc.scan_file(path, repo) is not None
    assert [v.path for v in ccc.collect_violations(repo)] == [path]


def test_main_judges_imports_against_repo_root(repo: Path) -> None:
    _make_canonpkg(repo)
    _write(repo, '"""Mirrors the CANON contract."""\nfrom canonpkg import CANON\n')
    assert ccc.main(["--repo-root", str(repo), "--strict"]) == 0


def test_missing_module_under_owned_root_is_not_evidence(repo: Path) -> None:
    body = (
        '"""Mirrors the CONTRACT by importing it."""\nfrom scripts.does_not_exist import CONTRACT\n'
    )
    path = _write(repo, body)
    assert ccc.scan_file(path, repo) is not None
    assert ccc.scan_copied_contract(path, repo) is None


def test_missing_module_in_plain_import_is_not_evidence(repo: Path) -> None:
    body = '"""Mirrors scripts.does_not_exist by importing it."""\nimport scripts.does_not_exist\n'
    assert ccc.scan_file(_write(repo, body), repo) is not None


def test_existing_dotted_module_is_evidence(repo: Path) -> None:
    (repo / "scripts" / "canon.py").write_text("CONTRACT = 1\n", encoding="utf-8")
    body = '"""Mirrors the CONTRACT by importing it."""\nfrom scripts.canon import CONTRACT\n'
    assert ccc.scan_file(_write(repo, body), repo) is None


def test_relative_import_must_resolve_to_a_sibling(repo: Path) -> None:
    body = '"""Mirrors the CONTRACT by importing it."""\nfrom .missing import CONTRACT\n'
    assert ccc.scan_file(_write(repo, body), repo) is not None
    (repo / "scripts" / "validation" / "present.py").write_text("CONTRACT = 1\n", encoding="utf-8")
    ok = '"""Mirrors the CONTRACT by importing it."""\nfrom .present import CONTRACT\n'
    assert ccc.scan_file(_write(repo, ok), repo) is None


def test_bare_relative_import_must_name_an_existing_sibling(repo: Path) -> None:
    body = '"""Mirrors the CONTRACT by importing it."""\nfrom . import missing_mod\n'
    assert ccc.scan_file(_write(repo, body), repo) is not None
    (repo / "scripts" / "validation" / "present_mod.py").write_text("X = 1\n", encoding="utf-8")
    ok = '"""Mirrors the present_mod contract by importing it."""\nfrom . import present_mod\n'
    assert ccc.scan_file(_write(repo, ok), repo) is None


def test_collect_all_matches_the_two_collectors(repo: Path) -> None:
    _write(repo, '"""Mirrors scripts/a.py. Copied verbatim from the source."""\n')
    other = repo / "scripts" / "validation" / "c.py"
    other.write_text('"""Mirrors the contract."""\n', encoding="utf-8")
    violations, findings = ccc.collect_all(repo)
    assert [v.path for v in violations] == [v.path for v in ccc.collect_violations(repo)]
    assert [f.path for f in findings] == [f.path for f in ccc.collect_copy_findings(repo)]
    assert len(violations) == 1 and len(findings) == 1


# --- review hardening: symbols and test definitions must be real -------------


def test_import_of_symbol_the_module_does_not_define_is_not_evidence(repo: Path) -> None:
    (repo / "scripts" / "validation" / "schema_rules.py").write_text("X = 1\n", encoding="utf-8")
    body = '"""Mirrors the SCHEMA_RULES contract."""\nfrom schema_rules import SCHEMA_RULES\n'
    path = _write(repo, body)
    assert ccc.scan_file(path, repo) is not None
    assert ccc.scan_copied_contract(path, repo) is None


@pytest.mark.parametrize(
    "module_source",
    [
        "def SCHEMA_RULES():\n    pass\n",
        "class SCHEMA_RULES:\n    pass\n",
        "SCHEMA_RULES: int = 1\n",
        "a, SCHEMA_RULES = 1, 2\n",
        "from elsewhere import SCHEMA_RULES\n",
        "try:\n    SCHEMA_RULES = 1\nexcept ImportError:\n    SCHEMA_RULES = 2\n",
        "if True:\n    SCHEMA_RULES = 1\n",
    ],
)
def test_import_of_defined_symbol_is_evidence(repo: Path, module_source: str) -> None:
    (repo / "scripts" / "validation" / "schema_rules.py").write_text(
        module_source, encoding="utf-8"
    )
    body = '"""Mirrors the SCHEMA_RULES contract."""\nfrom schema_rules import SCHEMA_RULES\n'
    assert ccc.scan_file(_write(repo, body), repo) is None


def test_import_of_submodule_of_a_package_is_evidence(repo: Path) -> None:
    pkg = repo / "scripts" / "validation" / "rulepkg"
    pkg.mkdir()
    (pkg / "schema_rules.py").write_text("Y = 1\n", encoding="utf-8")
    body = '"""Mirrors the schema_rules contract."""\nfrom rulepkg import schema_rules\n'
    assert ccc.scan_file(_write(repo, body), repo) is None


def test_import_from_module_with_syntax_error_is_not_evidence(repo: Path) -> None:
    (repo / "scripts" / "validation" / "schema_rules.py").write_text("def (\n", encoding="utf-8")
    body = '"""Mirrors the SCHEMA_RULES contract."""\nfrom schema_rules import SCHEMA_RULES\n'
    assert ccc.scan_file(_write(repo, body), repo) is not None


def test_test_name_inside_a_string_is_not_a_defined_test(repo: Path) -> None:
    (repo / "tests" / "test_text.py").write_text(
        'TEXT = "def test_contract_in_a_string(): pass"\n', encoding="utf-8"
    )
    assert "test_contract_in_a_string" not in ccc.defined_tests(repo)
    doc = '"""Mirrors the validator; see test_contract_in_a_string."""\n'
    assert ccc.scan_file(_write(repo, doc), repo) is not None


def test_async_and_method_tests_are_defined_tests(repo: Path) -> None:
    (repo / "tests" / "test_more.py").write_text(
        "class TestX:\n    def test_method_contract(self):\n        pass\n\n"
        "async def test_async_parity():\n    pass\n",
        encoding="utf-8",
    )
    assert {"test_method_contract", "test_async_parity"} <= ccc.defined_tests(repo)


def test_test_file_with_syntax_error_is_skipped(repo: Path) -> None:
    (repo / "tests" / "test_broken.py").write_text("def test_x(:\n", encoding="utf-8")
    assert "test_session_conformance" in ccc.defined_tests(repo)


def test_nested_and_uncollected_test_defs_are_not_defined_tests(repo: Path) -> None:
    (repo / "tests" / "test_nested.py").write_text(
        "def helper():\n    def test_nested_contract():\n        pass\n\n"
        "class Helper:\n    def test_uncollected_parity(self):\n        pass\n",
        encoding="utf-8",
    )
    found = ccc.defined_tests(repo)
    assert "test_nested_contract" not in found
    assert "test_uncollected_parity" not in found


# --- speed: lazy test index and one parse per file must not change a verdict --


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
