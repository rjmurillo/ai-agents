"""Tests for scripts/validation/check_skill_adr_bindings.py (issue #5665).

Pins the gate that resolves a skill's declared `metadata.adr` against that ADR's
own lifecycle status. Coverage for the single check `skill-adr-binding`:

- pos: a skill declaring only live records passes; `proposed` is deliberately
  live, because a proposed record is an open decision rather than a retired one
- neg: each of the three retired statuses (superseded, deprecated, rejected) is
  flagged, and every retired id in one declaration is named in one finding
- edge: the key is nested, so a top-level `adr:` is prose and must not be read;
  a YAML list value resolves; `adr-7`, `ADR_37` and `ADR 7` resolve while a bare
  integer does not; an unknown id, absent frontmatter, absent `metadata`, absent
  `adr`, malformed YAML and a scalar frontmatter all read as clean rather than
  as findings that belong to another gate
- I/O: an unreadable SKILL.md becomes a finding rather than a silent pass
- pruning: a SKILL.md inside `.venv`, `node_modules` or `.git` is never scanned

Ratchet and CLI: at baseline exits 0, above exits 1, below exits 0 and says so,
and every unusable-baseline shape plus a missing ADR directory exits 2. The
exit-2 cases are the point of the suite: a gate that cannot read its own
baseline has not run, and scoring that as a pass is the silent-pass failure the
repository's CI-script rules exist to stop.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_skill_adr_bindings import (
    CHECK,
    EXIT_CONFIG,
    EXIT_OK,
    EXIT_REGRESSION,
    RETIRED_STATUSES,
    declared_adr_numbers,
    find_skill_files,
    main,
    read_baseline,
    scan,
    validate_skill_adr_bindings,
    write_baseline,
)


def _write_adr(repo: Path, number: int, status: str) -> None:
    adr_dir = repo / ".agents" / "architecture"
    adr_dir.mkdir(parents=True, exist_ok=True)
    (adr_dir / f"ADR-{number:03d}-fixture.md").write_text(
        f"---\nid: ADR-{number:03d}\nstatus: {status}\n---\n\n# ADR-{number:03d}\n",
        encoding="utf-8",
    )


def _write_skill(repo: Path, name: str, frontmatter: str, tree: str = "skills") -> Path:
    path = repo / tree / name
    path.mkdir(parents=True, exist_ok=True)
    skill = path / "SKILL.md"
    skill.write_text(f"---\n{frontmatter}\n---\n\n# {name}\n", encoding="utf-8")
    return skill


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo root with one ADR per lifecycle status."""
    _write_adr(tmp_path, 1, "accepted")
    _write_adr(tmp_path, 2, "superseded")
    _write_adr(tmp_path, 3, "deprecated")
    _write_adr(tmp_path, 4, "rejected")
    _write_adr(tmp_path, 5, "proposed")
    return tmp_path


def _scan(repo: Path):
    return scan(repo, repo / ".agents" / "architecture")


# --------------------------------------------------------------------------
# Detection: positive
# --------------------------------------------------------------------------


def test_pos_accepted_declaration_passes(repo: Path) -> None:
    _write_skill(repo, "live", "name: live\nmetadata:\n  adr: ADR-001")
    assert _scan(repo) == []


def test_pos_proposed_is_not_retired(repo: Path) -> None:
    """A proposed record is an open decision, not a withdrawn one."""
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-005")
    assert _scan(repo) == []
    assert "proposed" not in RETIRED_STATUSES


# --------------------------------------------------------------------------
# Detection: negative, one per retired status
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "status"),
    [(2, "superseded"), (3, "deprecated"), (4, "rejected")],
)
def test_neg_each_retired_status_is_flagged(repo: Path, number: int, status: str) -> None:
    _write_skill(repo, "s", f"name: s\nmetadata:\n  adr: ADR-{number:03d}")
    violations = _scan(repo)
    assert len(violations) == 1
    assert violations[0].check == CHECK
    assert f"ADR-{number:03d} is {status}" in violations[0].detail


def test_neg_every_retired_id_named_in_one_finding(repo: Path) -> None:
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-001, ADR-002, ADR-004")
    violations = _scan(repo)
    assert len(violations) == 1, "one file yields one finding, not one per id"
    detail = violations[0].detail
    assert "ADR-002 is superseded" in detail
    assert "ADR-004 is rejected" in detail
    assert "ADR-001" not in detail, "a live record must not be named as retired"


# --------------------------------------------------------------------------
# Detection: edges
# --------------------------------------------------------------------------


def test_edge_top_level_adr_key_is_not_read(repo: Path) -> None:
    """The key is nested. A top-level `adr:` is a different field."""
    _write_skill(repo, "s", "name: s\nadr: ADR-002")
    assert _scan(repo) == []


def test_edge_yaml_list_value_resolves(repo: Path) -> None:
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr:\n    - ADR-001\n    - ADR-002")
    violations = _scan(repo)
    assert len(violations) == 1
    assert "ADR-002 is superseded" in violations[0].detail


@pytest.mark.parametrize("form", ["ADR-002", "adr-2", "ADR_2", "ADR 2", "adr2"])
def test_edge_id_spelling_variants_resolve(repo: Path, form: str) -> None:
    _write_skill(repo, "s", f"name: s\nmetadata:\n  adr: {form}")
    assert len(_scan(repo)) == 1, f"{form!r} should resolve to ADR-002"


def test_edge_bare_integer_is_not_an_id(repo: Path) -> None:
    """`metadata.adr: 2` is far likelier to be a count than a record id."""
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: 2")
    assert _scan(repo) == []


def test_edge_unknown_adr_number_is_clean(repo: Path) -> None:
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-999")
    assert _scan(repo) == []


@pytest.mark.parametrize(
    "frontmatter",
    [
        "name: s",  # no metadata at all
        "name: s\nmetadata:\n  issue: '1875'",  # metadata without adr
        "name: s\nmetadata: not-a-mapping",  # metadata is a scalar
    ],
)
def test_edge_absent_declaration_is_clean(repo: Path, frontmatter: str) -> None:
    _write_skill(repo, "s", frontmatter)
    assert _scan(repo) == []


def test_edge_no_frontmatter_is_clean(repo: Path) -> None:
    path = repo / "skills" / "bare"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("# bare skill\n", encoding="utf-8")
    assert _scan(repo) == []


def test_edge_malformed_yaml_is_not_double_reported(repo: Path) -> None:
    """Frontmatter shape belongs to another gate; inventing a finding here
    would report one defect twice."""
    path = repo / "skills" / "broken"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: [unclosed\n---\n\n# x\n", encoding="utf-8")
    assert _scan(repo) == []


def test_edge_scalar_frontmatter_is_clean(repo: Path) -> None:
    path = repo / "skills" / "scalar"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\njust-a-string\n---\n\n# x\n", encoding="utf-8")
    assert _scan(repo) == []


def test_edge_adr_with_unparseable_frontmatter_is_not_retired(tmp_path: Path) -> None:
    """An ADR the lifecycle gate cannot parse has no status here, and absent is
    the conservative read for a consumer check."""
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-002-broken.md").write_text("---\nid: [oops\n---\n# x\n", encoding="utf-8")
    _write_skill(tmp_path, "s", "name: s\nmetadata:\n  adr: ADR-002")
    assert _scan(tmp_path) == []


def test_edge_non_scalar_status_is_not_retired(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-002-listy.md").write_text(
        "---\nid: ADR-002\nstatus:\n  - superseded\n---\n# x\n", encoding="utf-8"
    )
    _write_skill(tmp_path, "s", "name: s\nmetadata:\n  adr: ADR-002")
    assert _scan(tmp_path) == []


def test_edge_status_case_and_whitespace_tolerated(tmp_path: Path) -> None:
    adr_dir = tmp_path / ".agents" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-002-cased.md").write_text(
        "---\nid: ADR-002\nstatus: '  SUPERSEDED  '\n---\n# x\n", encoding="utf-8"
    )
    _write_skill(tmp_path, "s", "name: s\nmetadata:\n  adr: ADR-002")
    assert len(_scan(tmp_path)) == 1


# --------------------------------------------------------------------------
# I/O faults and pruning
# --------------------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses the unreadable bit")
def test_neg_unreadable_skill_is_a_finding_not_a_silent_pass(repo: Path) -> None:
    skill = _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002")
    skill.chmod(0)
    try:
        violations = _scan(repo)
        assert len(violations) == 1
        assert "could not be read" in violations[0].detail
    finally:
        skill.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_edge_invalid_utf8_skill_is_a_finding(repo: Path) -> None:
    path = repo / "skills" / "binary"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_bytes(b"---\nname: \xff\xfe\n---\n")
    violations = _scan(repo)
    assert len(violations) == 1
    assert "not valid UTF-8" in violations[0].detail


@pytest.mark.parametrize("pruned", [".venv", "node_modules", ".git", "__pycache__"])
def test_edge_pruned_directories_are_never_scanned(repo: Path, pruned: str) -> None:
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002", tree=pruned)
    assert _scan(repo) == []
    assert all(pruned not in p.parts for p in find_skill_files(repo))


def test_declared_adr_numbers_reports_read_fault_separately(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "SKILL.md"
    numbers, fault = declared_adr_numbers(missing)
    assert numbers == []
    assert fault is not None and "could not be read" in fault


# --------------------------------------------------------------------------
# Baseline ratchet and CLI
# --------------------------------------------------------------------------


def _baseline(tmp_path: Path, count: int) -> Path:
    path = tmp_path / "baseline.json"
    path.write_text(
        json.dumps({"schema_version": "1", "counts": {CHECK: count}}) + "\n",
        encoding="utf-8",
    )
    return path


def _run(repo: Path, baseline: Path, *extra: str) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline), *extra])


def test_pos_at_baseline_exits_ok(repo: Path, tmp_path: Path) -> None:
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002")
    assert _run(repo, _baseline(tmp_path, 1)) == EXIT_OK


def test_neg_above_baseline_exits_regression(repo: Path, tmp_path: Path) -> None:
    _write_skill(repo, "a", "name: a\nmetadata:\n  adr: ADR-002")
    _write_skill(repo, "b", "name: b\nmetadata:\n  adr: ADR-003")
    assert _run(repo, _baseline(tmp_path, 1)) == EXIT_REGRESSION


def test_edge_below_baseline_exits_ok_and_says_so(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(repo, _baseline(tmp_path, 3)) == EXIT_OK
    assert "improved" in capsys.readouterr().out


def test_neg_missing_baseline_exits_config(repo: Path, tmp_path: Path) -> None:
    assert _run(repo, tmp_path / "absent.json") == EXIT_CONFIG


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        json.dumps({"schema_version": "1"}),  # no counts mapping
        json.dumps({"counts": {"wrong-name": 0}}),  # unknown check
        json.dumps({"counts": {CHECK: -1}}),  # negative
        json.dumps({"counts": {CHECK: True}}),  # bool is not a count
        json.dumps({"counts": {CHECK: "3"}}),  # string is not a count
    ],
)
def test_neg_unusable_baseline_shapes_exit_config(
    repo: Path, tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "b.json"
    path.write_text(payload, encoding="utf-8")
    assert _run(repo, path) == EXIT_CONFIG


def test_neg_missing_adr_directory_exits_config(tmp_path: Path) -> None:
    assert _run(tmp_path, _baseline(tmp_path, 0)) == EXIT_CONFIG


def test_read_baseline_reports_reason_for_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    path.write_bytes(b"\xff\xfe{")
    reason = read_baseline(path)
    assert isinstance(reason, str) and "not valid UTF-8" in reason


def test_pos_write_baseline_records_current_count(repo: Path, tmp_path: Path) -> None:
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002")
    path = tmp_path / "b.json"
    assert _run(repo, path, "--write-baseline") == EXIT_OK
    assert json.loads(path.read_text(encoding="utf-8"))["counts"][CHECK] == 1


def test_edge_write_baseline_leaves_no_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    write_baseline(path, {CHECK: 4})
    assert json.loads(path.read_text(encoding="utf-8"))["counts"][CHECK] == 4
    assert [p.name for p in tmp_path.iterdir()] == ["b.json"]


def test_adapter_returns_false_on_config_error(tmp_path: Path) -> None:
    """The pre-PR adapter must not score an unrun gate as a pass."""
    assert validate_skill_adr_bindings(tmp_path) is False


def test_edge_write_baseline_removes_temp_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The atomic swap's rollback path: a failed replace must not strand a
    temp file next to the baseline, because the next run would still read a
    valid baseline while an orphan accumulated beside it."""
    import check_skill_adr_bindings as mod

    def _boom(src: str, dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mod.os, "replace", _boom)
    path = tmp_path / "b.json"
    with pytest.raises(OSError, match="disk full"):
        write_baseline(path, {CHECK: 1})
    assert not path.exists()
    assert list(tmp_path.iterdir()) == [], "temp file must be cleaned up"
