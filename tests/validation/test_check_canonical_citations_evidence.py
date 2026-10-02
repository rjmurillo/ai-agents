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


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "scripts" / "validation").mkdir(parents=True)
    return tmp_path


def _write(repo: Path, body: str) -> Path:
    target = repo / "scripts" / "validation" / "b.py"
    target.write_text(body, encoding="utf-8")
    return target


# --- 1. conformance-by-test: accepted, no copied contract text --------------


def test_conformance_test_symbol_without_path_or_copy_is_accepted(repo: Path) -> None:
    doc = '"""Mirrors the session validator.\n\nConformance: test_session_conformance.\n"""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path) is None
    assert ccc.scan_copied_contract(path) is None


def test_shared_import_is_accepted_without_path(repo: Path) -> None:
    body = (
        '"""Mirrors the CONTRADICTION_PATTERNS contract by importing it."""\n'
        "from scripts.validate_session_json import CONTRADICTION_PATTERNS\n"
    )
    path = _write(repo, body)
    assert ccc.scan_file(path) is None


def test_direct_import_alias_is_accepted_without_path(repo: Path) -> None:
    body = (
        '"""Mirrors the session validator through the canonical alias."""\n'
        "import scripts.validate_session_json as canonical\n"
    )
    assert ccc.scan_file(_write(repo, body)) is None


def test_direct_import_without_alias_is_accepted_by_dotted_name(repo: Path) -> None:
    body = (
        '"""Mirrors scripts.validate_session_json by importing it."""\n'
        "import scripts.validate_session_json\n"
    )
    assert ccc.scan_file(_write(repo, body)) is None


def test_direct_stdlib_import_is_not_evidence(repo: Path) -> None:
    body = '"""Mirrors the os.path semantics."""\nimport os.path\n'
    assert ccc.scan_file(_write(repo, body)) is not None


def test_stdlib_import_is_not_evidence(repo: Path) -> None:
    body = '"""Mirrors the Path semantics."""\nfrom pathlib import Path\n'
    assert ccc.scan_file(_write(repo, body)) is not None


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
    violation = ccc.scan_file(_write(repo, f'"""{docstring}"""\n'))
    assert violation is not None


# --- 3. intentional-divergence: accepted with path plus rationale -----------


def test_divergence_with_reason_and_path_is_accepted_without_a_copy(repo: Path) -> None:
    doc = (
        '"""Mirrors scripts/validate_session_json.py.\n\n'
        "Stricter than canonical: the validator warns, this guard blocks, because\n"
        'CI bounced this check three times.\n"""\n'
    )
    path = _write(repo, doc)
    assert ccc.scan_file(path) is None
    assert ccc.scan_copied_contract(path) is None


# --- 4. stale-copy: finding recommends eliminating the copy -----------------


def test_copied_contract_without_structure_yields_elimination_finding(repo: Path) -> None:
    doc = (
        '"""Mirrors scripts/validate_session_json.py.\n\n'
        "Verbatim contract copied character-for-character from the validator:\n"
        '    PATTERN = a|b|c\n"""\n'
    )
    finding = ccc.scan_copied_contract(_write(repo, doc))
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
    assert ccc.scan_copied_contract(_write(repo, doc)) is None


def test_copy_findings_are_reported_but_never_block(repo: Path, capsys) -> None:
    doc = '"""Mirrors scripts/a.py. Copied verbatim from the source."""\n'
    _write(repo, doc)
    assert ccc.main(["--repo-root", str(repo), "--strict"]) == 0
    out = capsys.readouterr().out
    assert "[PASS] No uncited mirror-claims found." in out
    assert "[WARN] 1 copied-contract" in out
    assert "eliminate the copy" in out.lower()


# --- 5. generated-projection: not independent authored duplication ----------


def test_generated_projection_is_evidence_and_not_a_copy_finding(repo: Path) -> None:
    doc = '"""Mirrors the schema. Copied verbatim; generated from schema.yaml."""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path) is None
    assert ccc.scan_copied_contract(path) is None


# --- 6. transaction-evidence: no durable copy is required -------------------


def test_path_reference_alone_passes_without_a_verbatim_quote(repo: Path) -> None:
    doc = '"""Matches scripts/validate_session_json.py exit codes."""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path) is None
    assert ccc.scan_copied_contract(path) is None


def test_commit_scoped_verification_text_is_not_a_mirror_claim(repo: Path) -> None:
    doc = '"""Verified against scripts/a.py at commit abc1234; conformance passes."""\n'
    path = _write(repo, doc)
    assert ccc.scan_file(path) is None
    assert ccc.scan_copied_contract(path) is None


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
    assert ccc.scan_file(_write(repo, body)) is not None


def test_sibling_module_import_is_evidence(repo: Path) -> None:
    (repo / "scripts" / "validation" / "schema_rules.py").write_text("X = 1\n", encoding="utf-8")
    body = '"""Mirrors the SCHEMA_RULES contract."""\nfrom schema_rules import SCHEMA_RULES\n'
    assert ccc.scan_file(_write(repo, body)) is None


def test_lib_package_import_is_evidence() -> None:
    from scripts.validation import mirror_evidence as me

    owned = me.owned_roots(REPO_ROOT, REPO_ROOT / "scripts" / "validation")
    assert {"scripts", "build", "ai_review_common"} <= owned
    assert "pytest" not in owned
    assert "os" not in owned


def test_import_ownership_uses_the_scanned_repo_root(repo: Path) -> None:
    (repo / "canonpkg").mkdir()
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
    (repo / "canonpkg").mkdir()
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
