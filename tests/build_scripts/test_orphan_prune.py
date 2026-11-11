"""``build/scripts/orphan_prune.py``: what a plain build deletes, keeps, and reports.

Issue #7224. Cases run in temp git repositories built by ``orphan_test_helpers``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_all  # noqa: E402
import orphan_outputs as oo  # noqa: E402
import orphan_prune as op  # noqa: E402
from orphan_test_helpers import (  # noqa: E402
    AGENT_TREES,
    add_skill,
    delete_agent_templates,
    delete_skill_template,
    git,
    make_repo,
    names,
    symlink_or_skip,
    write,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


# --- Symlinked install entries ---------------------------------------------------


def test_dangling_symlink_without_template_is_flagged_and_left_for_binplace(
    repo: Path,
) -> None:
    symlink_or_skip(repo / ".claude/skills/ghost", "../../src/claude/skills/ghost")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert names(found, repo) == {".claude/skills/ghost"}
    assert done.swept_by_binplace == [repo.resolve() / ".claude/skills/ghost"]
    assert done.unresolved == []
    assert (repo / ".claude/skills/ghost").is_symlink()


def test_prune_never_follows_a_symlink_into_its_target(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    keep = write(outside / "keep.txt")
    symlink_or_skip(repo / ".claude/skills/escape", outside)

    found = oo.scan(repo)
    op.prune(repo, found.orphans)

    assert keep.exists()
    assert (repo / ".claude/skills/escape").is_symlink()


def test_live_symlink_to_orphan_source_stays_unresolved(repo: Path) -> None:
    delete_skill_template(repo, "alpha")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "drop alpha template")
    write(repo / "src/claude/skills/alpha/references/notes.md")
    git(repo, "add", "-A")

    done = op.prune(repo, oo.scan(repo).orphans)

    reasons = {o.path.relative_to(repo.resolve()).as_posix(): r for o, r in done.unresolved}
    assert "hand-maintained file" in reasons["src/claude/skills/alpha"]
    assert reasons[".claude/skills/alpha"] == "link target still exists"
    assert "still holds the source" in reasons["src/codex/skills/alpha"]


# --- Write mode: prune ------------------------------------------------------------


def test_uncommitted_template_deletion_prunes_skill_mirrors_and_source(repo: Path) -> None:
    delete_skill_template(repo, "alpha")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert not (repo / "src/claude/skills/alpha").exists()
    assert not (repo / "src/codex/skills/alpha").exists()
    assert (repo / "src/claude/skills/beta/SKILL.md").exists()
    assert done.unresolved == []
    assert op.exit_code(found, done) == 0
    assert [p.relative_to(repo.resolve()).as_posix() for p in done.swept_by_binplace] == [
        ".claude/skills/alpha"
    ]


def test_committed_template_deletion_is_proven_from_history(repo: Path) -> None:
    delete_skill_template(repo, "alpha")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "drop alpha")

    done = op.prune(repo, oo.scan(repo).orphans)

    assert done.unresolved == []
    assert not (repo / "src/codex/skills/alpha").exists()


def test_agent_template_deletion_prunes_generated_files(repo: Path) -> None:
    delete_agent_templates(repo, "planner")

    done = op.prune(repo, oo.scan(repo).orphans)

    for tree, suffix in AGENT_TREES:
        assert not (repo / tree / f"planner{suffix}").exists()
        assert (repo / tree / f"critic{suffix}").exists()
    assert done.unresolved == []
    assert done.errors == []


def test_dir_that_never_had_a_template_is_kept(repo: Path) -> None:
    write(repo / "src/codex/skills/never/SKILL.md")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "hand made")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert (repo / "src/codex/skills/never/SKILL.md").exists()
    assert "owner is unknown" in done.unresolved[0][1]
    assert op.exit_code(found, done) == 2


def test_untracked_file_inside_orphan_mirror_is_kept(repo: Path) -> None:
    delete_skill_template(repo, "alpha")
    mine = write(repo / "src/codex/skills/alpha/mine.txt")

    done = op.prune(repo, oo.scan(repo).orphans)

    assert mine.exists()
    assert any("untracked" in reason for _, reason in done.unresolved)


def test_edited_tracked_agent_file_is_kept(repo: Path) -> None:
    delete_agent_templates(repo, "planner")
    edited = write(repo / "src/cursor/agents/planner.md", "my local edit\n")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert edited.read_text(encoding="utf-8") == "my local edit\n"
    assert not (repo / "src/claude/agents/planner.md").exists()
    assert any("uncommitted" in reason for _, reason in done.unresolved)
    assert op.exit_code(found, done) == 2


def test_ignored_file_inside_orphan_mirror_is_kept(repo: Path) -> None:
    write(repo / ".gitignore", "*.local\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore local files")
    delete_skill_template(repo, "alpha")
    secret = write(repo / "src/codex/skills/alpha/settings.local")

    done = op.prune(repo, oo.scan(repo).orphans)

    assert secret.exists()
    assert any("settings.local" in reason for _, reason in done.unresolved)


def test_ignored_bytecode_cache_does_not_protect_an_orphan_mirror(repo: Path) -> None:
    write(repo / ".gitignore", "__pycache__/\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ignore bytecode")
    delete_skill_template(repo, "alpha")
    write(repo / "src/codex/skills/alpha/__pycache__/x.pyc")

    done = op.prune(repo, oo.scan(repo).orphans)

    assert not (repo / "src/codex/skills/alpha").exists()
    assert done.unresolved == []


def test_dangling_link_whose_plugin_tree_is_gone_stays_unresolved(repo: Path) -> None:
    symlink_or_skip(repo / ".claude/skills/ghost", "../../gone/skills/ghost")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert done.swept_by_binplace == []
    assert "plugin tree is gone" in done.unresolved[0][1]
    assert op.exit_code(found, done) == 2


def test_untracked_agent_file_is_kept(repo: Path) -> None:
    delete_agent_templates(repo, "planner")
    git(repo, "rm", "-q", "--cached", "src/cursor/agents/planner.md")

    done = op.prune(repo, oo.scan(repo).orphans)

    assert (repo / "src/cursor/agents/planner.md").exists()
    assert not (repo / "src/claude/agents/planner.md").exists()
    assert op.exit_code(oo.scan(repo), done) == 2


def test_source_dir_with_support_files_is_reported_not_deleted(repo: Path) -> None:
    add_skill(repo, "gamma", support=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "gamma")
    delete_skill_template(repo, "gamma")

    found = oo.scan(repo)
    done = op.prune(repo, found.orphans)

    assert (repo / "src/claude/skills/gamma/references/notes.md").exists()
    assert (repo / "src/codex/skills/gamma/SKILL.md").exists()
    assert op.exit_code(found, done) == 2


def test_no_regen_file_inside_orphan_mirror_is_kept(repo: Path) -> None:
    delete_skill_template(repo, "alpha")
    write(repo / "src/codex/skills/alpha/SKILL.md", "<!-- NO-REGEN: keep -->\n")

    done = op.prune(repo, oo.scan(repo).orphans)

    assert (repo / "src/codex/skills/alpha/SKILL.md").exists()
    assert any("NO-REGEN" in reason for _, reason in done.unresolved)


def test_what_if_deletes_nothing(repo: Path) -> None:
    delete_skill_template(repo, "alpha")

    done = op.prune(repo, oo.scan(repo).orphans, what_if=True)

    assert (repo / "src/codex/skills/alpha/SKILL.md").exists()
    assert done.pruned


def test_write_mode_wiring_prunes_and_reports(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    delete_skill_template(repo, "alpha")

    result = build_all._build_orphans(repo, check=False)

    out = capsys.readouterr().out
    assert result.exit_code == 0
    assert result.outputs == 2
    assert "PRUNED orphan: src/codex/skills/alpha" in out
    assert not (repo / "src/codex/skills/alpha").exists()


def test_write_mode_wiring_fails_when_an_orphan_cannot_be_pruned(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(repo / "src/claude/skills/never/SKILL.md")

    result = build_all._build_orphans(repo, check=False)

    assert result.exit_code == 2
    assert "ORPHANED OUTPUT kept: src/claude/skills/never" in capsys.readouterr().err


# --- Wiring into build_all._run_generators ----------------------------------------


def _drive_run_generators(repo: Path, monkeypatch: pytest.MonkeyPatch, order: list[str]) -> int:
    """Run ``_run_generators`` with every other step stubbed, recording the call order."""

    def stub(label: str):
        def _inner(*_a: object, **_k: object) -> build_all.GeneratorResult:
            order.append(label)
            return build_all.GeneratorResult(artifact=label, platform="*")

        return _inner

    for name in (
        "_build_agents",
        "_build_agent_catalog",
        "_build_adr_index",
        "_build_lib",
        "_build_skills",
        "_build_rules",
        "_build_hooks",
        "_run_binplace",
    ):
        monkeypatch.setattr(build_all, name, stub(name))
    monkeypatch.setattr(build_all, "assert_no_claude_writes", lambda *_a, **_k: [])
    monkeypatch.setattr(build_all, "write_audit", lambda *_a, **_k: [])
    monkeypatch.setattr(build_all, "_load_blocklist", lambda *_a, **_k: [])
    config = repo / "templates" / "platforms" / "codex.yaml"
    return build_all._run_generators(
        repo, [config], check=False, audit_format="md", claude_baseline={}
    )


def test_run_generators_runs_the_orphan_gate_first(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    real = build_all._build_orphans

    def recording(*args: object, **kwargs: object) -> build_all.GeneratorResult:
        order.append("_build_orphans")
        return real(*args, **kwargs)

    monkeypatch.setattr(build_all, "_build_orphans", recording)

    clean = _drive_run_generators(repo, monkeypatch, order)

    assert clean == 0
    assert order[0] == "_build_orphans"
    assert order.index("_build_orphans") < order.index("_build_agents")


def test_run_generators_fails_on_an_orphan_that_cannot_be_pruned(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(repo / "src/claude/skills/never/SKILL.md")

    code = _drive_run_generators(repo, monkeypatch, [])

    assert code == 2
