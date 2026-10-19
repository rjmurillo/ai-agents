"""Tests for build/scripts/binplace_links.py and the manifest's ``link`` rows.

A ``link: true`` binplace row places one relative symlink per top-level plugin
entry instead of copying bytes (ADR-119). Exit codes, per the module
docstring: 0 when every link is in place, 1 when a NO-REGEN file was
skipped, 2 for drift in check mode or a real directory whose files differ
from the plugin entry.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILD_SCRIPTS = _REPO_ROOT / "build" / "scripts"
if str(_BUILD_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_BUILD_SCRIPTS))

import binplace_links  # noqa: E402
import binplace_manifest  # noqa: E402

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="symlink creation needs Developer Mode on Windows"
)


def _plugin(root: Path) -> Path:
    plugin = root / "src" / "claude" / "skills"
    (plugin / "alpha" / "scripts").mkdir(parents=True)
    (plugin / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    (plugin / "alpha" / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")
    (plugin / "beta.md").write_text("beta\n", encoding="utf-8")
    return plugin


def _install(root: Path) -> Path:
    return root / ".claude" / "skills"


def test_write_mode_links_every_top_level_entry(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert os.readlink(install / "alpha") == "../../src/claude/skills/alpha"
    assert os.readlink(install / "beta.md") == "../../src/claude/skills/beta.md"
    assert (install / "alpha" / "scripts" / "run.py").read_text(encoding="utf-8") == "print(1)\n"
    assert sorted(Path(p).name for p in outcome.written) == ["alpha", "beta.md"]


def test_second_write_run_changes_nothing(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    binplace_links.link_row(plugin, install, check=False)

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.written == []
    assert outcome.exit_code == 0


def test_check_mode_reports_missing_links_and_writes_nothing(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)

    outcome = binplace_links.link_row(plugin, install, check=True)

    assert outcome.exit_code == 2
    assert sorted(Path(p).name for p in outcome.drifted) == ["alpha", "beta.md"]
    assert not install.exists()


def test_wrong_target_is_drift_in_check_and_repaired_in_write(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    install.mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    os.symlink("../../elsewhere", install / "alpha")

    checked = binplace_links.link_row(plugin, install, check=True)
    written = binplace_links.link_row(plugin, install, check=False)

    assert str(install / "alpha") in checked.drifted
    assert checked.exit_code == 2
    assert written.exit_code == 0
    assert os.readlink(install / "alpha") == "../../src/claude/skills/alpha"


def test_identical_real_directory_is_replaced_by_link(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (install / "alpha" / "scripts").mkdir(parents=True)
    (install / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    (install / "alpha" / "scripts" / "run.py").write_text("print(1)\n", encoding="utf-8")
    (install / "alpha" / "__pycache__").mkdir()
    (install / "alpha" / "__pycache__" / "x.pyc").write_bytes(b"\0")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert (install / "alpha").is_symlink()
    assert not any(p.name.endswith(".binplace-old") for p in install.iterdir())


def test_differing_real_directory_is_refused_and_left_intact(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (install / "alpha").mkdir(parents=True)
    (install / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    (install / "alpha" / "local-edit.md").write_text("only here\n", encoding="utf-8")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 2
    assert str(install / "alpha") in outcome.drifted
    assert not (install / "alpha").is_symlink()
    assert (install / "alpha" / "local-edit.md").read_text(encoding="utf-8") == "only here\n"


def test_real_file_is_replaced_by_link_in_write_mode(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    install.mkdir(parents=True)
    (install / "beta.md").write_text("stale copy\n", encoding="utf-8")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert (install / "beta.md").is_symlink()
    assert (install / "beta.md").read_text(encoding="utf-8") == "beta\n"


def test_no_regen_file_is_skipped_with_exit_1(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    install.mkdir(parents=True)
    (install / "beta.md").write_text("<!-- NO-REGEN: hand fix -->\n", encoding="utf-8")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 1
    assert str(install / "beta.md") in outcome.skipped
    assert not (install / "beta.md").is_symlink()


def test_stale_link_to_removed_entry_is_removed_and_strays_reported(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    binplace_links.link_row(plugin, install, check=False)
    os.symlink("../../src/claude/skills/gone", install / "gone")
    (install / "stray.md").write_text("hand file\n", encoding="utf-8")

    checked = binplace_links.link_row(plugin, install, check=True)
    written = binplace_links.link_row(plugin, install, check=False)

    assert checked.drifted == [str(install / "gone")]
    assert str(install / "gone") in written.written
    assert not (install / "gone").is_symlink()
    assert written.unowned == [str(install / "stray.md")]


def test_skip_names_and_bytecode_are_never_linked(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (plugin / "__pycache__").mkdir()
    (install / "beta.md").parent.mkdir(parents=True)
    (install / "beta.md").mkdir()

    outcome = binplace_links.link_row(
        plugin, install, check=False, skip_names=frozenset({"beta.md"})
    )

    assert outcome.exit_code == 0
    assert (install / "beta.md").is_dir() and not (install / "beta.md").is_symlink()
    assert not (install / "__pycache__").exists()
    assert outcome.unowned == []


def _manifest(root: Path, row_extra: str, plugin_tree: str = "src/claude/agents") -> None:
    (root / ".git").mkdir(exist_ok=True)
    platforms = root / "templates" / "platforms"
    platforms.mkdir(parents=True, exist_ok=True)
    (platforms / "binplace.yaml").write_text(
        'schemaVersion: "1.0"\n'
        "rows:\n"
        "  - class: agents\n"
        "    source: templates/agents\n"
        f"    plugin_tree: {plugin_tree}\n"
        "    install_tree: .claude/agents\n" + row_extra,
        encoding="utf-8",
    )


def test_binplace_places_links_and_allowlists_them(tmp_path: Path) -> None:
    agents = tmp_path / "src" / "claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "analyst.md").write_text("---\nname: analyst\n---\n", encoding="utf-8")
    _manifest(tmp_path, "    link: true\n")

    checked = binplace_manifest.binplace(tmp_path, check=True)
    written = binplace_manifest.binplace(tmp_path, check=False)
    allow = binplace_manifest.claude_allowlist(tmp_path)

    assert checked.exit_code == 2
    assert written.exit_code == 0
    assert os.readlink(tmp_path / ".claude" / "agents" / "analyst.md") == (
        "../../src/claude/agents/analyst.md"
    )
    assert binplace_manifest.binplace(tmp_path, check=True).exit_code == 0
    assert tmp_path / ".claude" / "agents" / "analyst.md" in allow


@pytest.mark.parametrize(
    ("row_extra", "plugin_tree", "message"),
    [
        ('    link: "yes"\n', "src/claude/agents", "must be a boolean"),
        ("    link: true\n", "src/claude/hooks.json", "file-shaped"),
    ],
)
def test_manifest_rejects_malformed_link_rows(
    tmp_path: Path, row_extra: str, plugin_tree: str, message: str
) -> None:
    (tmp_path / "src" / "claude").mkdir(parents=True)
    (tmp_path / "src" / "claude" / "hooks.json").write_text("{}\n", encoding="utf-8")
    _manifest(tmp_path, row_extra, plugin_tree)

    with pytest.raises(binplace_manifest.BinplaceConfigError, match=message):
        binplace_manifest.load(tmp_path)


def test_live_manifest_links_agents_skills_rules_and_instructions() -> None:
    rows = {row.class_name: row for row in binplace_manifest.load(_REPO_ROOT)}

    assert rows["agents"].link is True
    assert rows["skills"].link is True
    assert rows["rules"].link is True
    assert rows["instructions-github"].link is True
    assert rows["hooks"].link is False
    assert rows["skills-sidecar"].install_tree is None


def test_plugin_entry_refusal_names_both_causes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (tmp_path / "outside").mkdir()
    (plugin / "chained").symlink_to(tmp_path / "outside", target_is_directory=True)

    binplace_links.link_row(plugin, install, check=False)

    assert "is a symlink or resolves outside" in capsys.readouterr().err


def test_plugin_entry_that_is_a_symlink_is_refused(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (tmp_path / "outside").mkdir()
    (plugin / "chained").symlink_to(tmp_path / "outside", target_is_directory=True)

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 2
    assert str(plugin / "chained") in outcome.drifted
    assert not (install / "chained").exists()
    assert (install / "alpha").is_symlink(), "other entries still link"


def test_symlink_nested_inside_an_entry_is_refused(tmp_path: Path, capsys) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (tmp_path / "outside").mkdir()
    nested = plugin / "alpha" / "scripts" / "sub"
    nested.symlink_to(tmp_path / "outside", target_is_directory=True)

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 2
    assert str(nested) in outcome.drifted
    assert str(nested) in capsys.readouterr().err
    assert not (install / "alpha").exists(), "the unsafe entry is not linked"
    assert (install / "beta.md").is_symlink(), "other entries still link"


def test_nested_symlink_is_refused_in_check_mode(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (plugin / "alpha" / "SKILL.link").symlink_to("SKILL.md")

    outcome = binplace_links.link_row(plugin, install, check=True)

    assert outcome.exit_code == 2
    assert str(plugin / "alpha" / "SKILL.link") in outcome.drifted


def test_clean_tree_with_bytecode_passes(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    cache = plugin / "alpha" / "scripts" / "__pycache__"
    cache.mkdir()
    (cache / "run.cpython-314.pyc").write_bytes(b"\0")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert (install / "alpha").is_symlink()


def test_dropping_link_true_restores_real_directories(tmp_path: Path) -> None:
    # ADR-119 rollback: remove `link: true` and rebuild.
    skills = tmp_path / "src" / "claude" / "skills" / "alpha"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("alpha\n", encoding="utf-8")
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    row = (
        'schemaVersion: "1.0"\nrows:\n  - class: rules\n    source: templates/rules\n'
        "    plugin_tree: src/claude/skills\n    install_tree: .claude/skills\n"
    )
    (platforms / "binplace.yaml").write_text(row + "    link: true\n", encoding="utf-8")
    assert binplace_manifest.binplace(tmp_path, check=False).exit_code == 0
    assert (tmp_path / ".claude" / "skills" / "alpha").is_symlink()
    (platforms / "binplace.yaml").write_text(row, encoding="utf-8")

    checked = binplace_manifest.binplace(tmp_path, check=True)
    written = binplace_manifest.binplace(tmp_path, check=False)

    installed = tmp_path / ".claude" / "skills" / "alpha"
    assert checked.exit_code == 2
    assert str(installed) in checked.drifted
    assert written.exit_code == 0
    assert installed.is_dir() and not installed.is_symlink()
    assert (installed / "SKILL.md").read_text(encoding="utf-8") == "alpha\n"
    assert (skills / "SKILL.md").exists(), "the plugin tree is never removed"
    assert binplace_manifest.binplace(tmp_path, check=True).exit_code == 0


def test_a_suffix_shaped_stray_is_still_reported(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    install.mkdir(parents=True)
    (install / "evil.binplace-link").mkdir()

    outcome = binplace_links.link_row(plugin, install, check=True)

    assert str(install / "evil.binplace-link") in outcome.unowned


@pytest.mark.parametrize(
    ("install_tree", "accepted"),
    [
        (".agents/skills", True),
        (".agents/governance", False),
        (".agents", False),
        (".agents/skillsx", False),
        (".agents/skills/sub", False),
    ],
)
def test_codex_skills_is_the_only_agents_install_root(
    tmp_path: Path, install_tree: str, accepted: bool
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "codex" / "skills").mkdir(parents=True)
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (platforms / "binplace.yaml").write_text(
        'schemaVersion: "1.0"\nrows:\n  - class: skills-codex\n    source: src/codex/skills\n'
        f"    plugin_tree: src/codex/skills\n    install_tree: {install_tree}\n    link: true\n",
        encoding="utf-8",
    )

    if accepted:
        assert binplace_manifest.load(tmp_path)[0].install_tree == tmp_path / install_tree
    else:
        with pytest.raises(binplace_manifest.BinplaceConfigError, match="must be under"):
            binplace_manifest.load(tmp_path)


def test_live_manifest_links_codex_skills_into_agents() -> None:
    rows = {row.class_name: row for row in binplace_manifest.load(_REPO_ROOT)}

    assert rows["skills-codex"].link is True
    assert rows["skills-codex"].install_tree == _REPO_ROOT / ".agents" / "skills"


def test_github_agents_link_to_shipped_copilot_agents_without_a_model_pin() -> None:
    # ADR-119: .github/agents/*.agent.md link to src/copilot-cli/agents, and
    # that tree is inherit-only (PR #5040; issue #4938: a bad value silently
    # falls back), so no
    # shipped Copilot agent may carry one.
    shipped = sorted((_REPO_ROOT / "src" / "copilot-cli" / "agents").glob("*.agent.md"))
    assert shipped
    for agent in shipped:
        link = _REPO_ROOT / ".github" / "agents" / agent.name
        assert os.readlink(link) == f"../../src/copilot-cli/agents/{agent.name}", agent.name
        frontmatter = agent.read_text(encoding="utf-8").split("---", 2)[1]
        assert not any(line.startswith("model:") for line in frontmatter.splitlines()), agent.name


def test_every_github_agent_file_is_a_link_and_only_known_entries_are_real() -> None:
    github_agents = _REPO_ROOT / ".github" / "agents"
    real = sorted(entry.name for entry in github_agents.iterdir() if not entry.is_symlink())

    assert real == ["pr-comment-responder.prompt.md", "security"]
    for entry in github_agents.glob("*.agent.md"):
        assert os.readlink(entry) == f"../../src/copilot-cli/agents/{entry.name}", entry.name


def test_github_hooks_json_links_to_the_shipped_file_and_registers_nothing() -> None:
    hooks = _REPO_ROOT / ".github" / "hooks"

    assert os.readlink(hooks / "hooks.json") == "../../src/copilot-cli/hooks/hooks.json"
    assert not (hooks / "memory-recall.json").is_symlink()
    shipped = json.loads((_REPO_ROOT / "src/copilot-cli/hooks/hooks.json").read_text("utf-8"))
    assert shipped["hooks"] == {}, (
        "ADR-119 decision 11: Copilot loading a linked .github/hooks/hooks.json is "
        "unverified; record a link-loading probe before registering a hook"
    )


def test_live_manifest_links_claude_lib_and_compiles_without_installing() -> None:
    rows = {row.class_name: row for row in binplace_manifest.load(_REPO_ROOT)}

    assert rows["lib"].link is True
    assert rows["lib"].plugin_tree == _REPO_ROOT / "src" / "claude" / "lib"
    assert rows["lib"].install_tree == _REPO_ROOT / ".claude" / "lib"
    for name in (
        "lib-hook_utilities",
        "lib-github_core",
        "lib-ai_review_common",
        "lib-bootstrap",
        "lib-paths",
    ):
        assert rows[name].install_tree is None, name
    assert binplace_manifest._repo_local_names(_REPO_ROOT, rows["lib"]) == (
        binplace_manifest.REPO_LOCAL_LIB_NAMES
    )


def test_claude_lib_links_every_plugin_entry_and_keeps_repo_local_modules_real() -> None:
    plugin, install = _REPO_ROOT / "src/claude/lib", _REPO_ROOT / ".claude/lib"

    for entry in plugin.iterdir():
        if entry.name == "__pycache__":
            continue
        assert os.readlink(install / entry.name) == f"../../src/claude/lib/{entry.name}", entry.name
        assert (install / entry.name).resolve() == entry.resolve(), entry.name
        assert entry.resolve().is_relative_to(plugin.resolve()), entry.name
    real = {entry.name for entry in install.iterdir() if not entry.is_symlink()}
    assert real - {"__pycache__"} == binplace_manifest.REPO_LOCAL_LIB_NAMES
    for name in binplace_manifest.REPO_LOCAL_LIB_NAMES:
        assert not (plugin / name).exists(), f"{name} now ships; drop it from REPO_LOCAL_LIB_NAMES"


def test_a_hand_edited_real_lib_package_is_refused_not_replaced(tmp_path: Path) -> None:
    plugin, install = _plugin(tmp_path), _install(tmp_path)
    (plugin / "pkg").mkdir()
    (plugin / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (install / "pkg").mkdir(parents=True)
    (install / "pkg" / "mod.py").write_text("x = 2\n", encoding="utf-8")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 2
    assert (install / "pkg" / "mod.py").read_text(encoding="utf-8") == "x = 2\n"


def test_plugin_lib_tree_holds_no_symlinks() -> None:
    """A nested link under src/claude/lib would redirect code the hooks load (CWE-59).

    binplace_links.py checks only top-level plugin entries, so this pins the rest.
    """
    plugin = _REPO_ROOT / "src" / "claude" / "lib"

    nested = [str(path.relative_to(plugin)) for path in plugin.rglob("*") if path.is_symlink()]

    assert nested == []


def test_real_file_at_a_lib_file_link_path_is_replaced_in_write_mode(tmp_path: Path) -> None:
    plugin = tmp_path / "src" / "claude" / "lib"
    plugin.mkdir(parents=True)
    (plugin / "paths.py").write_text("x = 1\n", encoding="utf-8")
    install = tmp_path / ".claude" / "lib"
    install.mkdir(parents=True)
    (install / "paths.py").write_text("x = 1\n", encoding="utf-8")

    outcome = binplace_links.link_row(plugin, install, check=False)

    assert outcome.exit_code == 0
    assert os.readlink(install / "paths.py") == "../../src/claude/lib/paths.py"


def test_dropping_link_true_turns_lib_file_links_back_into_copies(tmp_path: Path) -> None:
    # ADR-119 decision 14 rollback for the file links (bootstrap.py, paths.py).
    plugin = tmp_path / "src" / "claude" / "lib"
    plugin.mkdir(parents=True)
    (plugin / "paths.py").write_text("x = 1\n", encoding="utf-8")
    platforms = tmp_path / "templates" / "platforms"
    platforms.mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    row = (
        'schemaVersion: "1.0"\nrows:\n  - class: lib\n    source: src/claude/lib\n'
        "    plugin_tree: src/claude/lib\n    install_tree: .claude/lib\n"
    )
    (platforms / "binplace.yaml").write_text(row + "    link: true\n", encoding="utf-8")
    assert binplace_manifest.binplace(tmp_path, check=False).exit_code == 0
    installed = tmp_path / ".claude" / "lib" / "paths.py"
    assert installed.is_symlink()
    (platforms / "binplace.yaml").write_text(row, encoding="utf-8")

    written = binplace_manifest.binplace(tmp_path, check=False)

    assert written.exit_code == 0
    assert installed.is_file() and not installed.is_symlink()
    assert installed.read_text(encoding="utf-8") == "x = 1\n"
    assert (plugin / "paths.py").read_text(encoding="utf-8") == "x = 1\n"
