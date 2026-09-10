# taste-lint: ignore file-size
#
# file-size suppression rationale: every test for one script belongs in one file,
# which is the reason tests/validation/test_check_vendor_portability.py gives for
# the same exemption. Splitting them would obscure which cases are covered and
# would need a shared fixture module for the git-backed repo helpers, adding a
# file without reducing complexity. The sibling gate's suite,
# tests/validation/test_check_adr_lifecycle.py, is 1717 lines for the same reason.
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
- tracked scope: an untracked SKILL.md is never counted, against a control that
  differs only in whether the same file was staged; a tracked path a working-tree
  deletion removed is skipped; and a root git cannot read is exit 3, not clean

Ratchet and CLI: at baseline exits 0, above exits 1, below exits 0 and says so,
every unusable-baseline shape plus a missing ADR directory exits 2, and a root
whose index cannot be listed exits 3. Those non-zero cases are the point of the
suite: a gate that cannot read its own baseline, or cannot enumerate the files it
is meant to scan, has not run, and scoring either as a pass is the silent-pass
failure the repository's CI-script rules exist to stop.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_skill_adr_bindings import (
    CHECK,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
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


def _git(repo: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run git in ``repo`` with a clean environment, failing loudly."""
    return subprocess.run(
        ["git", "-C", str(repo), *argv],
        capture_output=True,
        text=True,
        check=True,
        env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    )


def _track(repo: Path, relative: str) -> None:
    """Stage a file written without :func:`_write_skill`.

    Without this the file is untracked, the gate never reads it, and a test
    asserting the tree is clean passes because nothing was examined. That is the
    vacuous shape `.claude/rules/testing.md` SHOULD 14 names.
    """
    _git(repo, "add", "--force", "--", relative)
    assert relative in _git(repo, "ls-files", "--", relative).stdout


def _init_repo(repo: Path) -> None:
    """Make ``repo`` a git repository, idempotently.

    The gate enumerates candidate paths from the index, so a fixture tree that is
    not a repository exercises the git-failure path rather than detection. Only
    `git add` is ever needed, never a commit: `git ls-files` reads the index.
    """
    if not (repo / ".git").exists():
        _git(repo, "init", "--quiet")


def _write_skill(
    repo: Path,
    name: str,
    frontmatter: str,
    tree: str = "skills",
    *,
    track: bool = True,
) -> Path:
    """Write a SKILL.md and, unless ``track`` is False, stage it.

    ``track=False`` is the untracked case the gate must not count. It asserts the
    file really is untracked rather than assuming it, because a helper that
    silently staged it would make the discriminating test pass against the
    filesystem-walk implementation it exists to reject.
    """
    _init_repo(repo)
    path = repo / tree / name
    path.mkdir(parents=True, exist_ok=True)
    skill = path / "SKILL.md"
    skill.write_text(f"---\n{frontmatter}\n---\n\n# {name}\n", encoding="utf-8")
    rel = skill.relative_to(repo).as_posix()
    if track:
        _git(repo, "add", "--force", "--", rel)
        assert rel in _git(repo, "ls-files", "--", rel).stdout, f"{rel} was not staged"
    else:
        assert not _git(repo, "ls-files", "--", rel).stdout.strip(), (
            f"{rel} is tracked, so this case cannot observe untracked scope"
        )
    return skill


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo root with one ADR per lifecycle status.

    Initialized here rather than lazily, so a test that writes a SKILL.md
    directly can stage it without ordering its calls around the helper.
    """
    _init_repo(tmp_path)
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
    _track(repo, "skills/bare/SKILL.md")
    assert _scan(repo) == []


def test_edge_malformed_yaml_is_not_double_reported(repo: Path) -> None:
    """Frontmatter shape belongs to another gate; inventing a finding here
    would report one defect twice."""
    path = repo / "skills" / "broken"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: [unclosed\n---\n\n# x\n", encoding="utf-8")
    _track(repo, "skills/broken/SKILL.md")
    assert _scan(repo) == []


def test_edge_scalar_frontmatter_is_clean(repo: Path) -> None:
    path = repo / "skills" / "scalar"
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\njust-a-string\n---\n\n# x\n", encoding="utf-8")
    _track(repo, "skills/scalar/SKILL.md")
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
    _track(repo, "skills/binary/SKILL.md")
    violations = _scan(repo)
    assert len(violations) == 1
    assert "not valid UTF-8" in violations[0].detail


# --------------------------------------------------------------------------
# Tracked scope: a ratchet baseline is a claim about a ref
# --------------------------------------------------------------------------


def test_pos_a_tracked_declaration_is_counted(repo: Path) -> None:
    """Control for the untracked case below, differing only in whether the same
    file was staged. Without it, a gate that counted nothing at all would pass
    the discriminating test."""
    _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002", track=True)
    assert len(_scan(repo)) == 1


def test_neg_an_untracked_declaration_is_never_counted(repo: Path) -> None:
    """`ci-scripts.md` MUST 9: a ratchet baseline must not read untracked state,
    or the same commit scores differently on two machines.

    Measured against the filesystem-walk implementation this replaced: one
    untracked SKILL.md declaring a superseded record took the real repository's
    count from 16 to 17 and exited 1, and the remedy it printed named a file the
    repository does not contain.
    """
    skill = _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002", track=False)
    assert skill.is_file(), "the file must exist on disk, or this proves nothing"
    assert _scan(repo) == []
    assert skill not in (find_skill_files(repo) or [])


def test_edge_a_gitignored_declaration_is_never_counted(repo: Path) -> None:
    """The shape that turned main red in issue #4748: build output an author
    happens to have generated and CI never will."""
    (repo / ".gitignore").write_text("generated/\n", encoding="utf-8")
    _write_skill(
        repo, "s", "name: s\nmetadata:\n  adr: ADR-002", tree="generated", track=False
    )
    assert _scan(repo) == []


def test_edge_a_suffix_named_file_is_not_a_manifest(repo: Path) -> None:
    """`git ls-files -- "*SKILL.md"` is a suffix match, so it also offers
    `LEGACY-SKILL.md`. The walk this replaced tested the exact basename, and a
    manifest is the only subject this gate has."""
    path = repo / "skills" / "archive"
    path.mkdir(parents=True)
    (path / "LEGACY-SKILL.md").write_text(
        "---\nname: old\nmetadata:\n  adr: ADR-002\n---\n\n# old\n", encoding="utf-8"
    )
    _track(repo, "skills/archive/LEGACY-SKILL.md")
    assert _scan(repo) == []
    assert find_skill_files(repo) == []


def test_edge_a_tracked_path_deleted_from_disk_is_skipped(repo: Path) -> None:
    """The index still lists a file a working-tree deletion removed. That
    intermediate state is not a finding, and must not become an I/O fault."""
    skill = _write_skill(repo, "s", "name: s\nmetadata:\n  adr: ADR-002")
    skill.unlink()
    assert "skills/s/SKILL.md" in _git(repo, "ls-files").stdout, "still indexed"
    assert _scan(repo) == []


def test_neg_an_unlistable_root_is_external_not_a_clean_tree(tmp_path: Path) -> None:
    """A root git cannot read has examined nothing. Reporting that as zero
    violations is the silent-pass shape `ci-scripts.md` MUST 11 and 12 forbid."""
    (tmp_path / ".agents" / "architecture").mkdir(parents=True)
    assert not (tmp_path / ".git").exists(), "the root must not be a repository"
    assert find_skill_files(tmp_path) is None
    fault = _scan(tmp_path)
    assert isinstance(fault, str), f"expected a fault reason, got {fault!r}"
    assert "could not list tracked" in fault


def test_neg_write_baseline_on_an_unlistable_root_writes_nothing(
    tmp_path: Path,
) -> None:
    """The most costly shape of the fault: a failed enumeration counts zero, and
    writing that as the ceiling would make every later run a 16-violation
    regression against a number no tree ever held.

    Closes with the isolating assertion `testing.md` SHOULD 7 asks for: a
    `pytest.raises`-style check that the call failed passes just as well when the
    effect happened first, so the assertion that matters is that the file is
    still absent.
    """
    (tmp_path / ".agents" / "architecture").mkdir(parents=True)
    baseline = tmp_path / "baseline.json"
    assert not baseline.exists(), "the file must not pre-exist, or this proves nothing"

    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(baseline),
                "--write-baseline",
            ]
        )
        == EXIT_EXTERNAL
    )
    assert not baseline.exists(), "a baseline was written from a scan that never ran"


def test_neg_an_unlistable_root_exits_external(tmp_path: Path) -> None:
    """The process-level half of the case above, per `testing.md` MUST 8."""
    (tmp_path / ".agents" / "architecture").mkdir(parents=True)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps({"schema_version": "1", "counts": {CHECK: 0}}), encoding="utf-8"
    )
    assert (
        main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        == EXIT_EXTERNAL
    )
    assert validate_skill_adr_bindings(tmp_path) is False


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
