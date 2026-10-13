"""Guards for the host marketplace gate (ADR-115 Decision 11).

Coverage:

- positive: a synthetic repo with every host marketplace passes, and the
  real repository passes with the expected examined count.
- negative: a source outside the repo, a missing source directory, a missing
  manifest, a name mismatch, a non-string source, and an empty plugin list each
  fail; ``main`` returns 1 for them.
- edge: a missing marketplace file, malformed JSON, a non-object document, and
  a missing ``plugins`` list are config errors (exit 2), not passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_host_marketplaces as gate

_MANIFEST = ".claude-plugin/plugin.json"
_CURSOR_MANIFEST = ".cursor-plugin/plugin.json"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _marketplace(name: str = "tool", source: object = "./plugin") -> dict[str, object]:
    return {"name": "mk", "plugins": [{"name": name, "source": source}]}


def _repo(tmp_path: Path) -> Path:
    """A repo where every host marketplace lists plugin ``tool`` at ./plugin."""
    _write_json(tmp_path / "plugin" / _MANIFEST, {"name": "tool"})
    _write_json(tmp_path / "plugin" / _CURSOR_MANIFEST, {"name": "tool"})
    for marketplace, _ in gate.HOST_MARKETPLACES:
        _write_json(tmp_path / marketplace, _marketplace())
    return tmp_path


def _first_marketplace() -> str:
    return gate.HOST_MARKETPLACES[0][0]


def test_clean_repo_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path)
    assert gate.main([str(repo)]) == 0
    assert "4 plugin entries examined" in capsys.readouterr().out


def test_real_repo_passes_and_covers_grok_and_cursor() -> None:
    violations, examined = gate.find_violations(REPO_ROOT)
    assert violations == []
    assert examined == 4
    assert (REPO_ROOT / ".grok-plugin" / "marketplace.json").is_file()
    assert (REPO_ROOT / ".cursor-plugin" / "marketplace.json").is_file()


def test_cursor_row_reads_the_cursor_manifest_not_the_claude_one() -> None:
    assert (".cursor-plugin/marketplace.json", ".cursor-plugin/plugin.json") in (
        gate.HOST_MARKETPLACES
    )


def test_cursor_marketplace_needs_the_cursor_manifest(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "plugin" / _CURSOR_MANIFEST).unlink()
    violations, _ = gate.find_violations(repo)
    assert len(violations) == 1
    assert violations[0].startswith(".cursor-plugin/marketplace.json")
    assert "missing manifest .cursor-plugin/plugin.json" in violations[0]


def test_validate_wrapper_matches_main(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    assert gate.validate_host_marketplaces(repo) is True
    _write_json(repo / _first_marketplace(), _marketplace(name="other"))
    assert gate.validate_host_marketplaces(repo) is False


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("../escape", "outside the repository"),
        ("/etc", "outside the repository"),
        ("./missing-dir", "not a directory"),
        ("", "non-empty string"),
        (None, "non-empty string"),
        (["./plugin"], "non-empty string"),
    ],
)
def test_bad_source_is_a_violation(tmp_path: Path, source: object, fragment: str) -> None:
    repo = _repo(tmp_path)
    _write_json(repo / _first_marketplace(), _marketplace(source=source))
    violations, _ = gate.find_violations(repo)
    assert len(violations) == 1
    assert fragment in violations[0]
    assert gate.main([str(repo)]) == 1


def test_symlink_escaping_the_repo_is_a_violation(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    (outside / ".claude-plugin").mkdir(parents=True)
    _write_json(outside / _MANIFEST, {"name": "tool"})
    repo = _repo(tmp_path / "repo")
    (repo / "link").symlink_to(outside, target_is_directory=True)
    _write_json(repo / _first_marketplace(), _marketplace(source="./link"))
    violations, _ = gate.find_violations(repo)
    assert any("outside the repository" in v for v in violations)


def test_missing_manifest_is_a_violation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "plugin" / _MANIFEST).unlink()
    violations, _ = gate.find_violations(repo)
    claude_format = [m for m, manifest in gate.HOST_MARKETPLACES if manifest == _MANIFEST]
    assert len(violations) == len(claude_format)
    assert all("missing manifest" in v for v in violations)
    assert gate.main([str(repo)]) == 1


def test_unreadable_manifest_is_a_violation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "plugin" / _MANIFEST).write_text("{nope", encoding="utf-8")
    violations, _ = gate.find_violations(repo)
    assert all("unreadable manifest" in v for v in violations)


def test_manifest_without_name_is_a_violation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_json(repo / "plugin" / _MANIFEST, {"description": "x"})
    violations, _ = gate.find_violations(repo)
    assert all("no string 'name'" in v for v in violations)


def test_name_mismatch_is_a_violation_in_the_named_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    grok = ".grok-plugin/marketplace.json"
    _write_json(repo / grok, _marketplace(name="renamed"))
    violations, _ = gate.find_violations(repo)
    assert len(violations) == 1
    assert violations[0].startswith(grok)
    assert "does not match manifest name 'tool'" in violations[0]


def test_non_object_entry_is_a_violation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_json(repo / _first_marketplace(), {"plugins": ["project-toolkit"]})
    violations, _ = gate.find_violations(repo)
    assert any("not a JSON object" in v for v in violations)


def test_empty_plugin_list_is_a_violation(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _write_json(repo / _first_marketplace(), {"plugins": []})
    violations, examined = gate.find_violations(repo)
    assert violations == [f"{_first_marketplace()}: lists no plugins"]
    assert examined == len(gate.HOST_MARKETPLACES) - 1


def test_main_returns_nonzero_on_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    _write_json(repo / _first_marketplace(), _marketplace(source="../escape"))
    assert gate.main([str(repo)]) == 1
    err = capsys.readouterr().err
    assert "outside the repository" in err
    assert "1 host marketplace violation(s) in 4 plugin entries examined" in err


def test_missing_marketplace_file_is_a_config_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".grok-plugin" / "marketplace.json").unlink()
    assert gate.main([str(repo)]) == 2


def test_malformed_json_is_a_config_error(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / _first_marketplace()).write_text("{not json", encoding="utf-8")
    assert gate.main([str(repo)]) == 2


@pytest.mark.parametrize("document", [[], "text", {}, {"plugins": "x"}])
def test_wrong_shape_is_a_config_error(tmp_path: Path, document: object) -> None:
    repo = _repo(tmp_path)
    _write_json(repo / _first_marketplace(), document)
    assert gate.main([str(repo)]) == 2


def test_invalid_repo_root_is_a_config_error(tmp_path: Path) -> None:
    assert gate.main([str(tmp_path / "does-not-exist")]) == 2


def test_default_root_is_the_real_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main([]) == 0
    assert "0 violations" in capsys.readouterr().out
