"""D10 (#6506): links, nested repositories, and the config in a same-repository tree.

D10 says a plugin root that is another work tree of this repository is
verified like an in-tree path, or it blocks. In-tree, a link the trusted ref
does not pin is refused, a file inside a nested repository blocks, and the
config is compared. These tests pin the same three outcomes for a sibling.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import gate
from tests.skills.github.same_repository_helpers import (
    SCRIPT_REL,
    clear_plugin_roots,
    commit_as_trusted,
    git,
    linked_worktree,
    make_repo,
    plain,
    trusted_repo,
    verify,
    write,
    write_config,
)

OTHER_REL = ".claude/skills/demo/scripts/other.py"


@pytest.fixture(autouse=True)
def _no_plugin_root(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_plugin_roots(monkeypatch)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return make_repo(tmp_path, monkeypatch)


def _replace_with_link(sibling: Path, target: Path) -> Path:
    link = sibling / SCRIPT_REL
    link.unlink()
    os.symlink(target, link)
    return link


class TestSiblingLinks:
    def test_unpinned_link_to_a_tracked_identical_script_blocks(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """The target matches the trusted ref, but the link is the PR's blob (CWE-59)."""
        write(repo, OTHER_REL, "print('other')\n")
        trusted_repo(repo, plain(), OTHER_REL)
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        link = _replace_with_link(sibling, sibling / OTHER_REL)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert payload == {}
        assert str(link) in err
        assert not gate._SAME_REPOSITORY_TREES

    def test_unpinned_link_out_of_every_work_tree_blocks(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """Without the link check, the target would get install trust."""
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        outside = write(tmp_path / "outside", "evil.py", "print('pr code')\n")
        link = _replace_with_link(sibling, outside)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert str(link) in err

    def test_dotdot_after_an_unpinned_link_blocks(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """normpath drops "lnk/..", so the link scan must see the spelling as written (CWE-59)."""
        trusted_repo(repo, plain("skills/demo/scripts/lnk/../run.py"))
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        write(tmp_path / "outside", "run.py", "print('pr code')\n")
        (tmp_path / "outside" / "sub").mkdir()
        os.symlink(tmp_path / "outside" / "sub", sibling / ".claude/skills/demo/scripts/lnk")

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2, err
        assert payload == {}
        assert "lnk/../run.py" in err

    def test_dotdot_inside_a_sibling_fails_closed(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """No link at all: a lexical scan still cannot prove which file a ".." spelling opens."""
        trusted_repo(repo, plain("skills/demo/../demo/scripts/run.py"))
        linked_worktree(repo, tmp_path, monkeypatch)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2, err
        assert "demo/../demo/scripts/run.py" in err

    def test_dotdot_in_a_true_install_keeps_install_trust(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        trusted_repo(repo, plain("skills/demo/../demo/scripts/run.py"))
        installed = tmp_path / "installed"
        real = write(installed, "skills/demo/scripts/run.py", "print('installed')\n")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(installed))

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0, err
        assert str(real.resolve()) in payload["skipped_external_files"]

    def test_a_true_install_keeps_its_own_links(self, repo, tmp_path, monkeypatch, capsys) -> None:
        """A link inside a true install is the operator's, not a PR's."""
        trusted_repo(repo, plain())
        installed = tmp_path / "installed"
        real = write(installed, "real/run.py", "print('installed')\n")
        (installed / "skills" / "demo" / "scripts").mkdir(parents=True)
        os.symlink(real, installed / "skills" / "demo" / "scripts" / "run.py")
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(installed))

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0, err
        assert str(real.resolve()) in payload["skipped_external_files"]


class TestAliasedSiblingPluginRoot:
    """The plugin root is a host link to a sibling's ``.claude`` (round 3, R3-ALIAS).

    No lexical ancestor of the spelling holds the sibling's ``.git``, so
    only the resolved ancestors show that the spelling enters the sibling.
    """

    @staticmethod
    def _alias(tmp_path: Path, monkeypatch, sibling: Path) -> Path:
        alias = tmp_path / "host" / "plugin"
        alias.parent.mkdir()
        os.symlink(sibling / ".claude", alias)
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(alias))
        return alias

    def test_unpinned_link_to_a_tracked_identical_script_blocks(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        write(repo, OTHER_REL, "print('other')\n")
        trusted_repo(repo, plain(), OTHER_REL)
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        _replace_with_link(sibling, sibling / OTHER_REL)
        alias = self._alias(tmp_path, monkeypatch, sibling)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert payload == {}
        assert str(alias) in err
        assert not gate._SAME_REPOSITORY_TREES

    def test_unpinned_link_out_of_every_work_tree_blocks(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """Before the fix this target got install trust and the gate exited 0."""
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        outside = write(tmp_path / "outside", "evil.py", "print('pr code')\n")
        _replace_with_link(sibling, outside)
        alias = self._alias(tmp_path, monkeypatch, sibling)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert str(alias) in err
        assert str(outside.resolve()) not in payload.get("skipped_external_files", [])

    def test_aliased_clean_script_blocks_on_availability(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """An alias to a sibling's ``.claude`` cannot be scanned, so it fails closed."""
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        alias = self._alias(tmp_path, monkeypatch, sibling)

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert str(alias) in err

    def test_alias_to_the_sibling_root_also_fails_closed(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """The alias is the first link component at the root, and no ref pins it."""
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        alias = tmp_path / "host" / "checkout"
        alias.parent.mkdir()
        os.symlink(sibling, alias)
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(alias / ".claude"))

        rc, _, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert str(alias / SCRIPT_REL) in err

    def test_unresolvable_alias_ancestor_halts_with_exit_3(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """A resolve failure while walking the alias is a halt, never trust (R4-ALIAS-ERRTEST)."""
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        alias = self._alias(tmp_path, monkeypatch, sibling)
        broken = (alias / Path(SCRIPT_REL).relative_to(".claude")).parent
        real_resolve = Path.resolve

        def resolve(self: Path, strict: bool = False) -> Path:
            if self == broken:
                raise OSError("simulated resolve failure")
            return real_resolve(self, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve)

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 3, err
        assert payload == {}
        assert f"cannot resolve {broken}: simulated resolve failure" in err

    def test_alias_to_a_true_install_keeps_install_trust(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        trusted_repo(repo, plain())
        installed = tmp_path / "installed"
        real = write(installed, "skills/demo/scripts/run.py", "print('installed')\n")
        alias = tmp_path / "host" / "plugin"
        alias.parent.mkdir()
        os.symlink(installed, alias)
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(alias))

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 0, err
        assert str(real.resolve()) in payload["skipped_external_files"]


class TestNestedRepositoryInSibling:
    def test_file_in_a_nested_repository_blocks(self, repo, tmp_path, monkeypatch, capsys) -> None:
        """The innermost .git is another repository; the enclosing tree is ours."""
        nested_rel = ".claude/skills/nested/run.py"
        config = write_config(repo, plain("skills/nested/run.py"))
        commit_as_trusted(repo, config)
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        nested = sibling / ".claude" / "skills" / "nested"
        nested.mkdir(parents=True)
        git(nested, "init", "-q")
        write(sibling, nested_rel, "print('nested repository code')\n")
        git(nested, "add", "run.py")
        git(nested, "commit", "-q", "-m", "nested")

        rc, payload, err = verify(repo, capsys, "--harness", "copilot")

        assert rc == 2
        assert payload == {}
        assert str((sibling / nested_rel).resolve()) in err

    def test_same_repository_root_skips_an_inner_foreign_repository(self, repo, tmp_path) -> None:
        git(repo, "commit", "-q", "--allow-empty", "-m", "base")
        inner = repo.parent / "outer"
        git(repo, "worktree", "add", "-q", "--detach", str(inner), "HEAD")
        foreign = inner / "pkg"
        foreign.mkdir()
        git(foreign, "init", "-q")
        ours, error = gate._repository_identity(repo)
        assert error == ""

        root, error = gate._same_repository_root(foreign / "f.py", ours)

        assert (root, error) == (inner.resolve(), "")


class TestConfigInSameRepositoryRoot:
    @staticmethod
    def _declare(monkeypatch, root: Path) -> None:
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(root))
        monkeypatch.setattr(
            gate,
            "_DISPATCHER_PATH",
            root.resolve() / "skills/github/scripts/pr/run_completion_gate.py",
        )

    def test_sibling_config_gets_no_install_trust(self, repo, tmp_path, monkeypatch) -> None:
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        config = write(sibling, ".claude/skills/pr-review/pr-review-config.yaml", "x: 1\n")
        self._declare(monkeypatch, sibling / ".claude")

        assert gate._install_trusted_root(str(config)) is None

    def test_sibling_config_is_refused_end_to_end(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """Without D10 on the config, this PR-controlled config is install-trusted.

        Layout pinned: the gate tree has no ``scripts/utils`` marker, so
        ``_PROJECT_ROOT`` falls back to the cwd work tree. That is a consumer
        repository with the plugin vendored in a sibling work tree. A work
        tree of this repository never reaches this branch; see
        :class:`TestSiblingServedGateComparesItsConfig`.
        """
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        config = write(
            sibling,
            ".claude/skills/pr-review/pr-review-config.yaml",
            (sibling / "pr-review-config.yaml").read_text(encoding="utf-8"),
        )
        self._declare(monkeypatch, sibling / ".claude")

        rc = gate.main(
            [
                "--config",
                str(config),
                "--pull-request",
                "1",
                "--verify-config-only",
                "--json",
            ],
        )

        assert rc == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "Refusing to load config from unsafe path" in captured.err

    def test_true_install_config_keeps_install_trust(self, repo, tmp_path, monkeypatch) -> None:
        trusted_repo(repo, plain())
        installed = tmp_path / "installed"
        config = write(installed, "skills/pr-review/pr-review-config.yaml", "x: 1\n")
        self._declare(monkeypatch, installed)

        trust = gate._install_trusted_root(str(config))

        assert trust is not None
        assert trust.root == installed.resolve()

    def test_probe_failure_is_not_trust(self, repo, tmp_path, monkeypatch) -> None:
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        config = write(sibling, ".claude/skills/pr-review/pr-review-config.yaml", "x: 1\n")
        self._declare(monkeypatch, sibling / ".claude")
        monkeypatch.setattr(
            gate,
            "_repository_identity",
            lambda work_tree: (None, f"git rev-parse in {work_tree} failed"),
        )

        with pytest.raises(gate.WorkTreeUnavailableError):
            gate._install_trusted_root(str(config))


class TestSiblingServedGateComparesItsConfig:
    """This repository's real layout: the gate itself is served from the sibling.

    Every work tree of this repository holds ``scripts/utils/path_validation.py``,
    so ``_PROJECT_ROOT`` follows the gate into the sibling. Condition 3b then
    withholds install trust before the D10 check runs, containment against the
    sibling passes, and the config is byte-compared with the trusted ref.
    """

    @staticmethod
    def _serve_gate_from(monkeypatch, sibling: Path) -> Path:
        root = sibling / ".claude"
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(root))
        monkeypatch.setattr(gate, "_PROJECT_ROOT", sibling.resolve())
        monkeypatch.setattr(
            gate,
            "_DISPATCHER_PATH",
            root.resolve() / "skills/github/scripts/pr/run_completion_gate.py",
        )
        return root

    def _run(self, sibling: Path, capsys) -> tuple[int, str]:
        rc = gate.main(
            [
                "--config",
                str(sibling / "pr-review-config.yaml"),
                "--pull-request",
                "1",
                "--verify-config-only",
                "--json",
            ],
        )
        return rc, capsys.readouterr().err

    def test_matching_sibling_config_passes_then_command_trust_exits_3(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        """The config compares clean, so the cwd check is what stops the run.

        Command trust classifies relative paths against the gate's work tree,
        and the cwd (this work tree) is outside the sibling, so a clean
        sibling-served gate never reaches exit 0.
        """
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        self._serve_gate_from(monkeypatch, sibling)

        assert gate._install_trusted_root(str(sibling / "pr-review-config.yaml")) is None
        rc, err = self._run(sibling, capsys)

        assert rc == 3, err
        assert "is outside the git work tree" in err
        assert "is not trusted" not in err

    def test_diverged_sibling_config_exits_2_by_comparison(
        self, repo, tmp_path, monkeypatch, capsys
    ) -> None:
        trusted_repo(repo, plain())
        sibling = linked_worktree(repo, tmp_path, monkeypatch)
        self._serve_gate_from(monkeypatch, sibling)
        config = sibling / "pr-review-config.yaml"
        config.write_text(config.read_text(encoding="utf-8") + "# PR edit\n", encoding="utf-8")

        rc, err = self._run(sibling, capsys)

        assert rc == 2
        assert "is not trusted (diverged)" in err
        assert "Refusing to load config from unsafe path" not in err
