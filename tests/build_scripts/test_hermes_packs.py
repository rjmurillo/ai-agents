"""Tests for hermes_packs.py: pack layout, planning, the index, and writing (ADR-115 Decision 6).

Fixture tests build a tiny repository under ``tmp_path`` with ``make_repo``.
Wiring is in ``test_hermes_packs_wiring.py`` and the checks against the real
repository are in ``test_hermes_packs_conformance.py``.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import hermes_pack_config as cfg  # noqa: E402
import hermes_packs  # noqa: E402
import lib_render  # noqa: E402
from _hermes_pack_helpers import (  # noqa: E402
    EM_DASH,
    EN_DASH,
    NESTED_FRONTMATTER,
    make_config,
    make_repo,
    make_stanza,
    write_skill,
)
from frontmatter_key_drop import drop_keys_from_skill_md  # noqa: E402

# --- drop_keys_from_skill_md ---------------------------------------------------


def test_drop_keys_removes_nested_metadata_and_keeps_the_body() -> None:
    out = drop_keys_from_skill_md(NESTED_FRONTMATTER, frozenset({"metadata", "model"}))

    assert out == "---\nname: alpha\ndescription: d\n---\nBody\n"


def test_drop_keys_with_no_keys_is_identity() -> None:
    assert drop_keys_from_skill_md(NESTED_FRONTMATTER, frozenset()) == NESTED_FRONTMATTER


def test_drop_keys_rejects_a_file_without_frontmatter() -> None:
    with pytest.raises(ValueError, match="no fenced frontmatter"):
        drop_keys_from_skill_md("# Title\n", frozenset({"metadata"}))


# --- build_pack ------------------------------------------------------------------


def test_build_pack_lays_out_manifest_skills_and_lib(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config()
    lib = lib_render.render_lib_files(repo)

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, lib)

    assert "plugin.json" in files
    assert "skills/alpha/scripts/run.py" in files
    assert "skills/alpha/references/r.md" in files
    assert "skills/beta/SKILL.md" in files
    assert "lib/hook_utilities/util.py" in files
    assert "lib/bootstrap.py" in files
    assert not any(rel.startswith("skills/gamma") for rel in files)


def test_build_pack_applies_the_frontmatter_drop_to_skill_md_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config(frontmatterDrop=["metadata", "model"])

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert files["skills/alpha/SKILL.md"].data == b"---\nname: alpha\ndescription: d\n---\nBody\n"
    assert files["skills/alpha/scripts/run.py"].data == b"print('a')\n"


def test_build_pack_manifest_has_no_version(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    config = make_config()

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})
    manifest = json.loads(files["plugin.json"].data)

    assert manifest["$schema"] == cfg.PLUGIN_SCHEMA_URL
    assert manifest["name"] == "project-toolkit-one"
    assert manifest["description"] == "First pack."
    assert "version" not in manifest


def test_build_pack_keeps_the_execute_bit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    script = repo / "src/claude/skills/alpha/scripts/run.py"
    script.chmod(0o755)
    config = make_config()

    files = hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})

    assert files["skills/alpha/scripts/run.py"].mode == 0o755
    assert files["skills/beta/SKILL.md"].mode == 0o644


def test_build_pack_fails_loud_on_a_skill_md_without_frontmatter(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/beta/SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")
    config = make_config()

    with pytest.raises(cfg.HermesPackError, match="beta/SKILL.md"):
        hermes_packs.build_pack(repo / "src/claude/skills", config.packs[0], config, {})


# --- plan_tree -------------------------------------------------------------------


def test_plan_tree_includes_every_pack_and_the_index(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    tree = hermes_packs.plan_tree(repo, make_config())

    assert "README.md" in tree
    assert "project-toolkit-one/plugin.json" in tree
    assert "project-toolkit-two/skills/gamma/SKILL.md" in tree
    assert "project-toolkit-two/lib/bootstrap.py" in tree
    assert not any("/skills/delta/" in rel for rel in tree)


def test_plan_tree_writes_one_lib_copy_per_pack(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    tree = hermes_packs.plan_tree(repo, make_config())

    for pack_dir in ("project-toolkit-one", "project-toolkit-two"):
        assert tree[f"{pack_dir}/lib/hook_utilities/util.py"].data == b"x = 1\n"
        assert tree[f"{pack_dir}/lib/hook_utilities/__init__.py"].data == (b"from .util import x\n")


def test_plan_tree_fails_when_a_skill_is_unassigned(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_skill(repo / "src/claude/skills", "newcomer")

    with pytest.raises(cfg.HermesPackError, match="newcomer"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_fails_when_a_pack_exceeds_the_file_budget(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    with pytest.raises(cfg.HermesPackError, match="packMaxFiles is 5"):
        hermes_packs.plan_tree(repo, make_config(packMaxFiles=5))


def test_plan_tree_counts_lib_against_the_budget(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lib = lib_render.render_lib_files(repo)
    config = make_config()
    biggest = max(
        len(hermes_packs.build_pack(repo / "src/claude/skills", pack, config, lib))
        for pack in config.packs
    )

    assert hermes_packs.plan_tree(repo, make_config(packMaxFiles=biggest))
    with pytest.raises(cfg.HermesPackError):
        hermes_packs.plan_tree(repo, make_config(packMaxFiles=biggest - 1))


def test_plan_tree_fails_when_a_file_exceeds_one_megabyte(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    big = repo / "src/claude/skills/gamma/references/big.md"
    big.parent.mkdir(parents=True)
    big.write_bytes(b"x" * (cfg.HERMES_MAX_FILE_BYTES + 1))

    with pytest.raises(cfg.HermesPackError, match="big.md"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_fails_when_a_skill_refers_across_packs(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/alpha/references/r.md").write_text(
        "see skills/gamma/scripts/x.py\n", encoding="utf-8"
    )

    with pytest.raises(cfg.HermesPackError, match="refers to 'gamma'"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_fails_when_a_skill_refers_to_an_excluded_skill(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/beta/SKILL.md").write_text(
        "---\nname: beta\n---\nUse ../delta/references/x.md\n", encoding="utf-8"
    )

    with pytest.raises(cfg.HermesPackError, match="excluded skill 'delta'"):
        hermes_packs.plan_tree(repo, make_config())


def test_plan_tree_reports_a_missing_lib_source(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "scripts" / "hook_utilities" / "bootstrap.py").unlink()

    with pytest.raises(cfg.HermesPackError, match="bootstrap.py"):
        hermes_packs.plan_tree(repo, make_config())


# --- render_index ----------------------------------------------------------------


def test_index_lists_packs_skills_and_excluded_reasons() -> None:
    text = hermes_packs.render_index(make_config()).decode("utf-8")

    assert "## project-toolkit-one" in text
    assert "- `alpha`" in text and "- `gamma`" in text
    assert "- `delta`: plugin_guard returns dangerous." in text


def test_index_says_so_when_nothing_is_excluded() -> None:
    config = make_config(excluded={})

    assert "No skill is excluded." in hermes_packs.render_index(config).decode("utf-8")


def test_index_has_no_dash_characters_or_generated_banner() -> None:
    text = hermes_packs.render_index(make_config()).decode("utf-8")

    assert EM_DASH not in text and EN_DASH not in text
    assert "generated" not in text.lower() and "do not edit" not in text.lower()


# --- apply_tree and generate_hermes_packs -----------------------------------------


def test_generate_writes_the_tree_then_check_finds_no_drift(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert (repo / "src/hermes/project-toolkit-one/plugin.json").is_file()
    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 0


def test_check_reports_a_hand_edit_without_writing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    edited = repo / "src/hermes/project-toolkit-one/skills/beta/SKILL.md"
    edited.write_text("hand edit\n", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    assert edited.read_text(encoding="utf-8") == "hand edit\n"


def test_generate_repairs_a_hand_edit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    edited = repo / "src/hermes/project-toolkit-one/skills/beta/SKILL.md"
    edited.write_text("hand edit\n", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 0


def test_check_reports_and_generate_removes_a_stale_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    stale = repo / "src/hermes/project-toolkit-one/skills/old/SKILL.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("x", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1
    assert stale.exists()
    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert not stale.exists()
    assert not stale.parent.exists()


def test_generate_removes_a_retired_pack_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    hermes_packs.generate_hermes_packs(make_stanza(), repo)
    only_one = make_stanza(
        packs={"one": {"description": "First pack.", "skills": ["alpha", "beta", "gamma"]}}
    )

    assert hermes_packs.generate_hermes_packs(only_one, repo) == 0
    assert not (repo / "src/hermes/project-toolkit-two").exists()


def test_check_reports_a_missing_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    (repo / "src/hermes/README.md").unlink()

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1


def test_check_reports_a_lost_execute_bit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "src/claude/skills/alpha/scripts/run.py").chmod(0o755)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    target = repo / "src/hermes/project-toolkit-one/skills/alpha/scripts/run.py"
    assert target.stat().st_mode & stat.S_IXUSR
    target.chmod(0o644)

    assert hermes_packs.generate_hermes_packs(stanza, repo, check=True) == 1


def test_generate_replaces_a_symlink_instead_of_writing_through_it(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stanza = make_stanza()
    hermes_packs.generate_hermes_packs(stanza, repo)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    readme = repo / "src/hermes/README.md"
    readme.unlink()
    readme.symlink_to(outside)

    assert hermes_packs.generate_hermes_packs(stanza, repo) == 0
    assert not readme.is_symlink()
    assert outside.read_text(encoding="utf-8") == "keep"


def test_what_if_writes_nothing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    assert hermes_packs.generate_hermes_packs(make_stanza(), repo, what_if=True) == 0
    assert not (repo / "src" / "hermes").exists()


def test_a_failed_rule_writes_nothing_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    write_skill(repo / "src/claude/skills", "newcomer")

    code = hermes_packs.generate_hermes_packs(make_stanza(), repo)

    assert code == 2
    assert "newcomer" in capsys.readouterr().err
    assert not (repo / "src" / "hermes").exists()


def test_a_malformed_stanza_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = hermes_packs.generate_hermes_packs(make_stanza(packMaxFiles=999), make_repo(tmp_path))

    assert code == 2
    assert "packMaxFiles" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["/abs/out", "../escape"])
def test_an_output_dir_outside_the_repo_is_refused(tmp_path: Path, bad: str) -> None:
    assert hermes_packs.generate_hermes_packs(make_stanza(outputDir=bad), make_repo(tmp_path)) == 2


@pytest.mark.parametrize("bad", [".", "src", "src/hermesx", "docs"])
def test_an_output_dir_outside_src_hermes_is_refused(
    tmp_path: Path, bad: str, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_repo(tmp_path)
    keep = repo / "keep.txt"
    keep.write_text("repo file", encoding="utf-8")

    code = hermes_packs.generate_hermes_packs(make_stanza(outputDir=bad), repo)

    assert code == 2
    assert "src/hermes" in capsys.readouterr().err
    assert keep.read_text(encoding="utf-8") == "repo file"


def test_an_output_dir_under_src_hermes_is_accepted(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    assert hermes_packs.generate_hermes_packs(make_stanza(outputDir="src/hermes/nested"), repo) == 0
    assert (repo / "src/hermes/nested/README.md").is_file()


@pytest.mark.parametrize("check", [False, True])
def test_a_symlinked_pack_directory_is_refused_and_nothing_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], check: bool
) -> None:
    repo = make_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (repo / "src/hermes").mkdir(parents=True)
    (repo / "src/hermes/project-toolkit-one").symlink_to(outside, target_is_directory=True)

    code = hermes_packs.generate_hermes_packs(make_stanza(), repo, check=check)

    assert code == 2
    assert "symlinked ancestor" in capsys.readouterr().err
    assert list(outside.iterdir()) == []


def test_a_stale_path_below_a_symlinked_directory_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "out"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "stale.txt").write_text("keep", encoding="utf-8")
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(cfg.HermesPackError) as excinfo:
        hermes_packs._refuse_symlinked_ancestors(root, ["link/stale.txt"])

    assert "symlinked ancestor" in excinfo.value.problems[0]
    assert (outside / "stale.txt").read_text(encoding="utf-8") == "keep"


def test_real_directories_pass_the_symlink_guard(tmp_path: Path) -> None:
    (tmp_path / "pack").mkdir()

    hermes_packs._refuse_symlinked_ancestors(tmp_path, ["pack/file.txt", "top.txt", "new/x.txt"])


def test_an_unwritable_output_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path)
    (repo / "src").mkdir(exist_ok=True)
    blocker = repo / "src" / "hermes"
    blocker.write_text("a file where the directory should be", encoding="utf-8")

    assert hermes_packs.generate_hermes_packs(make_stanza(), repo) == 1
    assert "cannot write" in capsys.readouterr().err
