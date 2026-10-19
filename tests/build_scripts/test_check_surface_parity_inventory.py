"""Tests for check_surface_parity.py: inventory, listing, CLI, build_all wiring (issue #5637).

Per-relation checks are in ``test_check_surface_parity.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import build_all
import pytest

from tests.build_scripts import _surface_parity_helpers as h
from tests.build_scripts._surface_parity_helpers import (
    REPO_ROOT,
    csp,
    findings,
    generated,
    independent,
    put,
    sm,
    surface,
    write_manifest,
)


@pytest.fixture(autouse=True)
def synthetic_owned_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI and build_all read the live OWNED_PREFIXES; a synthetic repo owns only src/."""
    monkeypatch.setattr(build_all, "OWNED_PREFIXES", ("src/",))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return h.make_repo(tmp_path)


# --- Inventory discovery --------------------------------------------------


def write_binplace(root: Path, plugin: str | None, install: str) -> None:
    plugin_line = f"    plugin_tree: {plugin}\n" if plugin else "    plugin_tree: null\n"
    put(
        root,
        "templates/platforms/binplace.yaml",
        'schemaVersion: "1.0"\nrows:\n  - class: agents\n    source: templates/agents\n'
        f"{plugin_line}    install_tree: {install}\n",
    )


def test_binplace_row_without_an_install_surface_is_unmanifested(repo: Path) -> None:
    write_binplace(repo, "src/out", ".claude/agents")
    found = findings(repo)
    assert [(f.kind, f.path) for f in found] == [("UNMANIFESTED", ".claude/agents")]
    assert "binplace row agents" in found[0].detail


def test_binplace_row_without_a_plugin_surface_is_unmanifested(repo: Path) -> None:
    write_binplace(repo, "build/plugin", ".claude/agents")
    put(repo, "build/plugin/x.md")
    write_manifest(
        repo,
        [
            generated("src/out", "templates/agents", "build/gen.py"),
            independent("src/notes"),
            surface(
                path=".claude/agents",
                relation="binplaced",
                authority="build/plugin",
                generator="build/gen.py",
                owner="o",
            ),
        ],
        ["src"],
    )
    assert [(f.kind, f.path) for f in findings(repo)] == [("UNMANIFESTED", "build/plugin")]


def _self_sourced_layout(repo: Path, source: str) -> None:
    # ADR-119 lib-paths shape: a hand-maintained plugin file binplaced onto .claude/.
    put(
        repo,
        "templates/platforms/binplace.yaml",
        'schemaVersion: "1.0"\nrows:\n  - class: lib-paths\n'
        f"    source: {source}\n    plugin_tree: src/lib/paths.py\n"
        "    install_tree: .claude/lib/paths.py\n",
    )
    put(repo, "src/lib/paths.py")
    write_manifest(
        repo,
        [
            independent("src/lib/paths.py"),
            surface(
                path=".claude/lib/paths.py",
                relation="binplaced",
                authority="src/lib/paths.py",
                generator="build/gen.py",
                owner="o",
            ),
        ],
        ["src"],
    )


def test_self_sourced_plugin_file_may_be_independent(repo: Path) -> None:
    _self_sourced_layout(repo, "src/lib/paths.py")
    assert [f for f in findings(repo) if f.path == "src/lib/paths.py"] == []


def test_independent_plugin_file_with_another_source_is_unmanifested(repo: Path) -> None:
    _self_sourced_layout(repo, "scripts/paths.py")
    found = [(f.kind, f.path) for f in findings(repo) if f.path == "src/lib/paths.py"]
    assert found == [("UNMANIFESTED", "src/lib/paths.py")]


def test_binplace_install_surface_must_name_the_plugin_tree_as_authority(repo: Path) -> None:
    write_binplace(repo, "src/out", ".claude/agents")
    wrong = surface(
        path=".claude/agents",
        relation="binplaced",
        authority="templates/agents",
        generator="build/gen.py",
        owner="o",
    )
    write_manifest(
        repo,
        [generated("src/out", "templates/agents", "build/gen.py"), independent("src/notes"), wrong],
        ["src"],
    )
    assert [f.kind for f in findings(repo)] == ["UNMANIFESTED"]


def test_binplace_row_with_matching_surfaces_passes(repo: Path) -> None:
    write_binplace(repo, "src/out", ".claude/agents")
    right = surface(
        path=".claude/agents",
        relation="binplaced",
        authority="src/out",
        generator="build/gen.py",
        owner="o",
    )
    write_manifest(
        repo,
        [generated("src/out", "templates/agents", "build/gen.py"), independent("src/notes"), right],
        ["src"],
    )
    assert findings(repo) == []


def test_binplace_row_with_no_plugin_stage_accepts_a_generated_install(repo: Path) -> None:
    write_binplace(repo, None, ".github/out.md")
    write_manifest(
        repo,
        [
            generated("src/out", "templates/agents", "build/gen.py"),
            independent("src/notes"),
            generated(".github/out.md", "templates/agents", "build/gen.py"),
        ],
        ["src"],
    )
    assert findings(repo) == []


def put_platform(root: Path, body: str) -> None:
    put(root, "templates/platforms/p.yaml", 'schemaVersion: "1.0"\nprovider: p\n' + body)


def test_platform_artifact_output_without_a_surface_is_unmanifested(repo: Path) -> None:
    put_platform(root=repo, body="artifacts:\n  agents:\n    outputDir: src/new-tree\n")
    found = findings(repo)
    assert [(f.kind, f.path) for f in found] == [("UNMANIFESTED", "src/new-tree")]
    assert "p.yaml artifacts.agents" in found[0].detail


@pytest.mark.parametrize(
    "stanza",
    [
        "outputDirs:\n      - src/out\n      - src/second\n",
        "outputConfig: src/second/hooks.json\n",
        "outputScripts: src/second\n",
    ],
)
def test_every_output_key_shape_is_discovered(repo: Path, stanza: str) -> None:
    put_platform(root=repo, body=f"artifacts:\n  hooks:\n    {stanza}")
    assert [f.path for f in findings(repo)] == [
        "src/second" + ("/hooks.json" if "Config" in stanza else "")
    ]


def test_legacy_output_dir_is_discovered(repo: Path) -> None:
    put_platform(root=repo, body="legacy:\n  outputDir: src/vs-code-agents\n")
    found = findings(repo)
    assert [(f.kind, f.path) for f in found] == [("UNMANIFESTED", "src/vs-code-agents")]
    assert "p.yaml legacy" in found[0].detail


def test_platform_outputs_under_a_surface_pass(repo: Path) -> None:
    put_platform(root=repo, body="artifacts:\n  agents:\n    outputDir: src/out\n")
    assert findings(repo) == []


def test_restricted_ancestor_row_does_not_cover_a_new_output(repo: Path) -> None:
    write_manifest(
        repo,
        [
            generated("src/out", "templates/agents", "build/gen.py"),
            independent("src", include=["G.md"]),
            independent("src/notes"),
        ],
        roots=["src"],
    )
    put_platform(root=repo, body="artifacts:\n  agents:\n    outputDir: src/new-projection\n")
    assert [(f.kind, f.path) for f in findings(repo)] == [("UNMANIFESTED", "src/new-projection")]


def test_unrestricted_ancestor_row_covers_a_new_output(repo: Path) -> None:
    write_manifest(
        repo,
        [generated("src/out", "templates/agents", "build/gen.py"), independent("src")],
        roots=["src"],
    )
    put_platform(root=repo, body="artifacts:\n  agents:\n    outputDir: src/new-projection\n")
    assert findings(repo) == []


def test_owned_prefix_under_only_a_restricted_ancestor_is_unmanifested(repo: Path) -> None:
    write_manifest(
        repo,
        [
            generated("src/out", "templates/agents", "build/gen.py"),
            independent("src", include=["G.md"]),
            independent("src/notes"),
        ],
        roots=["src"],
    )
    found = findings(repo, prefixes=("src/new/",))
    assert [(f.kind, f.path) for f in found] == [("UNMANIFESTED", "src/new/")]


def test_yaml_without_a_provider_key_is_not_a_platform(repo: Path) -> None:
    put(
        repo,
        "templates/platforms/other.yaml",
        'schemaVersion: "1.0"\nartifacts:\n  agents:\n    outputDir: src/ignored\n',
    )
    assert findings(repo) == []


def test_owned_prefix_without_a_surface_is_unmanifested(repo: Path) -> None:
    found = findings(repo, prefixes=("src/out/", "docs/agent-catalog.md"))
    assert [(f.kind, f.path) for f in found] == [("UNMANIFESTED", "docs/agent-catalog.md")]


def test_owned_prefix_above_several_surfaces_is_covered(repo: Path) -> None:
    assert findings(repo, prefixes=("src/",)) == []


def test_deleting_a_surface_row_fails_instead_of_silencing(repo: Path) -> None:
    put_platform(root=repo, body="artifacts:\n  agents:\n    outputDir: src/out\n")
    write_manifest(repo, [independent("src/notes")], ["src"])
    assert {f.kind for f in findings(repo)} == {"UNCLASSIFIED", "UNMANIFESTED"}


# --- File listing ---------------------------------------------------------


def test_file_listing_drops_paths_git_still_lists_after_deletion(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    (repo / "src/notes/readme.md").unlink()
    assert "src/notes/readme.md" not in sm.list_files(repo)


def test_file_listing_walks_the_tree_outside_git(tmp_path: Path) -> None:
    put(tmp_path, "a/b.md")
    put(tmp_path, "a/__pycache__/c.pyc")
    put(tmp_path, ".git/config")
    assert sm.list_files(tmp_path) == ["a/b.md"]


def test_untracked_files_are_checked_before_they_are_committed(repo: Path) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    put(repo, "src/new/file.md")
    assert [f.path for f in findings(repo)] == ["src/new/file.md"]


# --- Report and CLI -------------------------------------------------------


def test_report_is_capped_with_a_remainder_count() -> None:
    many = [sm.Finding("STALE", "s", f"p{i}") for i in range(5)]
    lines = csp.format_report(many, limit=2)
    assert lines[:2] == ["STALE: [s] p0", "STALE: [s] p1"]
    assert lines[2] == "... and 3 more"


def test_finding_without_a_surface_renders_a_dash() -> None:
    assert sm.Finding("UNCLASSIFIED", "", "x", "why").render() == "UNCLASSIFIED: [-] x (why)"


def test_cli_exits_zero_on_a_clean_repo(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert csp.main(["--repo-root", str(repo)]) == 0
    assert "OK across 2 surfaces" in capsys.readouterr().out


def test_cli_exits_one_and_names_the_file(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    put(repo, "src/orphan/file.md")
    assert csp.main(["--repo-root", str(repo)]) == 1
    out = capsys.readouterr().out
    assert "UNCLASSIFIED: [-] src/orphan/file.md" in out
    assert "FAIL: 1 surface parity finding(s)" in out


def test_cli_json_output_carries_the_rendered_line(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(repo, "src/orphan/file.md")
    assert csp.main(["--repo-root", str(repo), "--format", "json"]) == 1
    (row,) = json.loads(capsys.readouterr().out)
    assert row["kind"] == "UNCLASSIFIED"
    assert row["line"].startswith("UNCLASSIFIED")


def test_cli_exits_two_when_the_manifest_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert csp.main(["--repo-root", str(tmp_path)]) == 2
    assert "not found" in capsys.readouterr().err


def test_cli_exits_two_when_the_manifest_is_malformed(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(repo, sm.MANIFEST_REL, "roots: [src]\nsurfaces: []\n")
    assert csp.main(["--repo-root", str(repo)]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_cli_exits_two_when_binplace_metadata_is_malformed(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(repo, "templates/platforms/binplace.yaml", 'schemaVersion: "1.0"\nrows: nope\n')
    assert csp.main(["--repo-root", str(repo)]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_find_repo_root_walks_up_to_pyproject(repo: Path) -> None:
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)
    assert csp._find_repo_root(nested) == repo.resolve()


def test_find_repo_root_raises_outside_a_repo(tmp_path: Path) -> None:
    lonely = tmp_path / "x"
    lonely.mkdir()
    with pytest.raises(FileNotFoundError):
        csp._find_repo_root(lonely)


# --- build_all --check wiring --------------------------------------------


def test_build_all_check_passes_without_a_manifest(tmp_path: Path) -> None:
    assert build_all._surface_parity_exit(tmp_path, []) == 0


def test_build_all_check_passes_on_a_clean_repo(repo: Path) -> None:
    assert build_all._surface_parity_exit(repo, []) == 0


def test_build_all_check_fails_on_a_finding_and_prints_it(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(repo, "src/orphan/file.md")
    assert build_all._surface_parity_exit(repo, []) == 2
    err = capsys.readouterr().err
    assert "SURFACE PARITY VIOLATION" in err
    assert "src/orphan/file.md" in err


def test_build_all_check_labels_stale_generator_paths(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert build_all._surface_parity_exit(repo, ["src/out/a.md"]) == 2
    assert "STALE-generated: [src-out] src/out/a.md" in capsys.readouterr().err


def test_build_all_check_reports_a_malformed_manifest_as_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    put(repo, sm.MANIFEST_REL, "roots: [src]\nsurfaces: []\n")
    assert build_all._surface_parity_exit(repo, []) == 2
    assert "surface parity manifest" in capsys.readouterr().err


# --- Edge paths -----------------------------------------------------------


def test_file_listing_falls_back_to_a_walk_when_git_cannot_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("git missing")

    monkeypatch.setattr(sm.subprocess, "run", boom)
    assert "src/out/a.md" in sm.list_files(repo)


def test_file_level_surface_owns_exactly_that_file(repo: Path) -> None:
    put(repo, "src/one.txt")
    write_manifest(
        repo,
        [
            generated("src/one.txt", "templates/agents", "build/gen.py"),
            generated("src/out", "templates/agents", "build/gen.py"),
            independent("src/notes"),
        ],
        ["src"],
    )
    manifest = sm.load_manifest(repo)
    assert manifest is not None
    owner, _ = sm.owner_of(manifest, "src/one.txt")
    assert owner is not None
    assert owner.path == "src/one.txt"
    assert findings(repo) == []


def test_unreadable_platform_file_is_skipped(repo: Path) -> None:
    put(repo, "templates/platforms/binary.yaml").write_bytes(b"\xff\xfe\x00bad")
    assert csp._is_platform_config(repo / "templates/platforms/binary.yaml") is False


def test_non_mapping_output_stanza_yields_no_paths() -> None:
    assert csp._stanza_outputs("not a mapping") == []


def test_script_runs_as_a_program(repo: Path) -> None:
    script = REPO_ROOT / "build" / "scripts" / "check_surface_parity.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "UNMANIFESTED" in proc.stdout
