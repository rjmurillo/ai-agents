"""The review marker validator has one canonical copy (issue #6098).

``scripts/validation/validate_review_marker.py`` renders into three other
trees. ``lib_mirror`` writes the plugin trees. Under ADR-119,
``.claude/skills/review`` is a relative symlink to ``src/claude/skills/review``,
so the install path reads the Claude plugin render directly and no separate
install copy exists to go stale (issue #6098 was a stale install copy
overwriting the render). These tests run the same steps ``build_all.py`` runs,
in the same order, on a scratch repo.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import binplace_manifest  # noqa: E402
import generate_skills  # noqa: E402
import lib_mirror  # noqa: E402

CANONICAL = lib_mirror.SKILLS_SIDECAR_SOURCE
COPIES = (
    lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE,
    lib_mirror.SKILLS_SIDECAR_COPILOT_TREE,
    lib_mirror.SKILLS_SIDECAR_CODEX_TREE,
    lib_mirror.SKILLS_SIDECAR_INSTALL_TREE,
)
OLD = '"""Marker v1."""\n'
NEW = '"""Marker v2."""\n'


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A scratch repo with the real binplace manifest and one review skill."""
    for pkg in lib_mirror.PACKAGES:
        _write(tmp_path, f"scripts/{pkg}/__init__.py", "")
    _write(tmp_path, "scripts/hook_utilities/bootstrap.py", '"""Bootstrap."""\n')
    _write(tmp_path, CANONICAL, OLD)
    _write(tmp_path, "src/claude/skills/review/SKILL.md", "# review\n")
    _write(tmp_path, "src/claude/skills/review/scripts/other.py", "print('other')\n")
    _write(tmp_path, "src/claude/skills/review/references/axes.md", "axes\n")
    manifest = tmp_path / "templates" / "platforms"
    manifest.mkdir(parents=True)
    shutil.copy(_REPO_ROOT / "templates" / "platforms" / "binplace.yaml", manifest)
    (manifest / "copilot-cli.yaml").write_text(
        'schemaVersion: "1.0"\n'
        "provider: copilot-cli\n"
        "artifacts:\n"
        "  skills:\n"
        "    mode: directory-copy\n"
        "    sourceDir: src/claude/skills\n"
        "    outputDir: src/copilot-cli/skills\n",
        encoding="utf-8",
    )
    return tmp_path


def _build(repo: Path) -> None:
    """One ``build_all.py`` write run: lib, then skills, then binplace."""
    assert not lib_mirror.compile_all(repo).had_errors
    config = repo / "templates" / "platforms" / "copilot-cli.yaml"
    assert generate_skills.generate_skills(config, repo) == 0
    binplace_manifest.binplace(repo, check=False)


def test_first_build_renders_every_copy_from_the_canonical_file(repo: Path) -> None:
    _build(repo)

    for copy in COPIES:
        assert _read(repo, copy) == OLD, copy


def test_edit_to_canonical_file_reaches_every_copy_in_one_build(repo: Path) -> None:
    _build(repo)
    _write(repo, CANONICAL, NEW)

    _build(repo)

    for copy in COPIES:
        assert _read(repo, copy) == NEW, copy


def test_edit_survives_a_second_build(repo: Path) -> None:
    _build(repo)
    _write(repo, CANONICAL, NEW)
    _build(repo)

    _build(repo)

    for copy in COPIES:
        assert _read(repo, copy) == NEW, copy


def test_install_path_reads_the_fresh_render_without_a_second_binplace(repo: Path) -> None:
    """ADR-119: the install path is a link, so a lib render is visible at once."""
    _build(repo)
    _write(repo, CANONICAL, NEW)

    lib_mirror.compile_all(repo)
    generate_skills.sync_claude_plugin_skill_support(repo)

    assert _read(repo, lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE) == NEW
    assert _read(repo, lib_mirror.SKILLS_SIDECAR_INSTALL_TREE) == NEW


def test_install_skill_directory_is_a_link_to_the_plugin_tree(repo: Path) -> None:
    _build(repo)

    link = repo / ".claude" / "skills" / "review"

    assert link.is_symlink()
    assert os.readlink(link) == "../../src/claude/skills/review"


def test_other_review_support_files_are_edited_in_the_plugin_tree(repo: Path) -> None:
    """Support files have one hand-maintained copy; Copilot mirrors from it."""
    _build(repo)

    assert _read(repo, ".claude/skills/review/scripts/other.py") == "print('other')\n"
    for root in ("src/claude/skills", "src/copilot-cli/skills"):
        assert _read(repo, f"{root}/review/scripts/other.py") == "print('other')\n"
        assert _read(repo, f"{root}/review/references/axes.md") == "axes\n"


def test_sidecar_is_not_pruned_from_the_plugin_trees(repo: Path) -> None:
    _build(repo)

    removed = generate_skills.sync_claude_plugin_skill_support(repo)[1]

    assert removed == 0
    assert (repo / lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE).is_file()


def test_same_filename_in_another_skill_is_still_mirrored_to_copilot(repo: Path) -> None:
    _write(repo, "src/claude/skills/other/SKILL.md", "# other\n")
    _write(repo, "src/claude/skills/other/scripts/validate_review_marker.py", "x = 1\n")

    _build(repo)

    copied = repo / "src/copilot-cli/skills/other/scripts/validate_review_marker.py"
    assert copied.read_text(encoding="utf-8") == "x = 1\n"
    # The plugin copy is the only Claude copy and is left untouched.
    kept = repo / "src/claude/skills/other/scripts/validate_review_marker.py"
    assert kept.read_text(encoding="utf-8") == "x = 1\n"


def test_lib_owned_support_files_names_only_the_review_sidecar() -> None:
    assert lib_mirror.lib_owned_support_files("review") == frozenset(
        {Path("scripts/validate_review_marker.py")}
    )
    assert lib_mirror.lib_owned_support_files("ship") == frozenset()


def test_owned_path_matches_the_install_tree_constant() -> None:
    skill, rel = lib_mirror.SKILLS_SIDECAR_OWNED

    assert f".claude/skills/{skill}/{rel}" == lib_mirror.SKILLS_SIDECAR_INSTALL_TREE
    assert f"src/claude/skills/{skill}/{rel}" == lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE
    assert f"src/copilot-cli/skills/{skill}/{rel}" == lib_mirror.SKILLS_SIDECAR_COPILOT_TREE
    assert f"src/codex/skills/{skill}/{rel}" == lib_mirror.SKILLS_SIDECAR_CODEX_TREE


# --check ----------------------------------------------------------------


def test_lib_check_is_clean_after_a_build(repo: Path) -> None:
    _build(repo)

    result = lib_mirror.compile_all(repo, check=True)

    assert not result.had_errors, result.errors
    assert not result.had_drift, result.drift


@pytest.mark.parametrize(
    "drifted",
    [
        lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE,
        lib_mirror.SKILLS_SIDECAR_COPILOT_TREE,
        lib_mirror.SKILLS_SIDECAR_CODEX_TREE,
    ],
)
def test_lib_check_reports_a_drifted_plugin_copy(repo: Path, drifted: str) -> None:
    _build(repo)
    _write(repo, drifted, "# hand edit\n")

    result = lib_mirror.compile_all(repo, check=True)

    assert result.had_drift
    assert any(drifted in line for line in result.drift), result.drift
    assert _read(repo, drifted) == "# hand edit\n"


def test_lib_check_reports_a_canonical_edit_not_yet_rendered(repo: Path) -> None:
    _build(repo)
    _write(repo, CANONICAL, NEW)

    result = lib_mirror.compile_all(repo, check=True)

    assert len(result.drift) == len(lib_mirror.SKILLS_SIDECAR_PLUGIN_TREES)


def test_lib_check_reports_a_missing_plugin_copy(repo: Path) -> None:
    _build(repo)
    (repo / lib_mirror.SKILLS_SIDECAR_COPILOT_TREE).unlink()

    result = lib_mirror.compile_all(repo, check=True)

    assert any("created:" in line for line in result.drift), result.drift


def test_lib_write_mode_does_not_report_drift(repo: Path) -> None:
    result = lib_mirror.compile_all(repo)

    assert not result.had_drift
    assert result.changes


def test_binplace_check_reports_an_install_directory_that_replaced_the_link(
    repo: Path,
) -> None:
    _build(repo)
    link = repo / ".claude" / "skills" / "review"
    link.unlink()
    _write(repo, lib_mirror.SKILLS_SIDECAR_INSTALL_TREE, "# stale\n")

    outcome = binplace_manifest.binplace(repo, check=True)

    assert outcome.exit_code == 2
    assert any(str(link) in str(p) for p in outcome.drifted), outcome.drifted
    assert not link.is_symlink()
