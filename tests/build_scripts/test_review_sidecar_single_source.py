"""The review marker validator has one canonical copy (issue #6098).

``scripts/validation/validate_review_marker.py`` renders into three other
trees. ``lib_mirror`` writes the two plugin trees. Binplace copies the Claude
plugin tree onto ``.claude/skills/review/scripts/``. The skill-support mirror
used to copy that stale install copy back over the render, so an edit to the
canonical file never reached any copy. These tests run the same steps
``build_all.py`` runs, in the same order, on a scratch repo.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

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
    _write(tmp_path, ".claude/skills/review/SKILL.md", "# review\n")
    _write(tmp_path, ".claude/skills/review/scripts/other.py", "print('other')\n")
    _write(tmp_path, ".claude/skills/review/references/axes.md", "axes\n")
    manifest = tmp_path / "templates" / "platforms"
    manifest.mkdir(parents=True)
    shutil.copy(_REPO_ROOT / "templates" / "platforms" / "binplace.yaml", manifest)
    (manifest / "copilot-cli.yaml").write_text(
        'schemaVersion: "1.0"\n'
        "provider: copilot-cli\n"
        "artifacts:\n"
        "  skills:\n"
        "    mode: directory-copy\n"
        "    sourceDir: .claude/skills\n"
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


def test_stale_install_copy_does_not_revert_the_render(repo: Path) -> None:
    """The #6098 failure: a stale .claude copy overwrote the fresh render."""
    _build(repo)
    _write(repo, CANONICAL, NEW)

    lib_mirror.compile_all(repo)
    generate_skills.sync_claude_plugin_skill_support(repo)

    assert _read(repo, lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE) == NEW
    assert _read(repo, lib_mirror.SKILLS_SIDECAR_INSTALL_TREE) == OLD


def test_other_review_support_files_still_mirror_from_the_install_tree(repo: Path) -> None:
    _build(repo)

    for root in ("src/claude/skills", "src/copilot-cli/skills"):
        assert _read(repo, f"{root}/review/scripts/other.py") == "print('other')\n"
        assert _read(repo, f"{root}/review/references/axes.md") == "axes\n"


def test_sidecar_is_not_pruned_from_the_plugin_trees(repo: Path) -> None:
    _build(repo)

    removed = generate_skills.sync_claude_plugin_skill_support(repo)[1]

    assert removed == 0
    assert (repo / lib_mirror.SKILLS_SIDECAR_PLUGIN_TREE).is_file()


def test_same_filename_in_another_skill_is_still_mirrored(repo: Path) -> None:
    _write(repo, ".claude/skills/other/SKILL.md", "# other\n")
    _write(repo, ".claude/skills/other/scripts/validate_review_marker.py", "x = 1\n")

    generate_skills.sync_claude_plugin_skill_support(repo)

    copied = repo / "src/claude/skills/other/scripts/validate_review_marker.py"
    assert copied.read_text(encoding="utf-8") == "x = 1\n"


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


def test_binplace_check_reports_a_stale_install_copy(repo: Path) -> None:
    _build(repo)
    _write(repo, lib_mirror.SKILLS_SIDECAR_INSTALL_TREE, "# stale\n")

    outcome = binplace_manifest.binplace(repo, check=True)

    assert outcome.exit_code == 2
    assert any("validate_review_marker.py" in str(p) for p in outcome.drifted)
