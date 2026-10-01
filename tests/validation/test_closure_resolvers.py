"""Tests for scripts/validation/closure_resolvers.py, one class per edge kind."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import pytest
from closure_model import (
    EDGE_ACTION_INPUT,
    EDGE_CONFIG_COMMAND,
    EDGE_WORKFLOW_REF,
    Edge,
)
from closure_resolvers import (
    RepoTree,
    load_config,
    normalize,
    resolve_action_inputs,
    resolve_config_commands,
    resolve_tokens,
    resolve_uses,
    tokens_in,
)

from tests.validation.closure_helpers import SHA, git, make_repo


@pytest.fixture
def tree(tmp_path: Path) -> RepoTree:
    make_repo(
        tmp_path,
        {
            "scripts/a.py": "x = 1\n",
            "scripts/run.sh": "echo hi\n",
            ".github/codeql/config.yml": "paths: []\n",
            ".github/actions/setup/action.yml": "runs: {using: composite, steps: []}\n",
            ".github/workflows/reuse.yml": "on: workflow_call\njobs: {}\n",
            "docs/readme.md": "hi\n",
        },
        with_gate=False,
    )
    return RepoTree.from_git(tmp_path)


class TestRepoTree:
    def test_a_tree_without_git_is_walked_and_skips_symlinks(self, tmp_path: Path) -> None:
        (tmp_path / "d").mkdir()
        (tmp_path / "d" / "a.py").write_text("1\n", encoding="utf-8")
        (tmp_path / "link.py").symlink_to(tmp_path / "d" / "a.py")

        loaded = RepoTree.from_root(tmp_path)

        assert loaded.has("d/a.py")
        assert not loaded.has("link.py")

    def test_a_checkout_uses_git_not_the_walk(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "1\n"}, with_gate=False)
        (tmp_path / "untracked.py").write_text("2\n", encoding="utf-8")

        loaded = RepoTree.from_root(tmp_path)

        assert loaded.has("a.py")
        assert not loaded.has("untracked.py")

    def test_a_hook_configured_in_the_measured_repo_does_not_run(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "1\n"}, with_gate=False)
        marker = tmp_path / "ran"
        hooks = tmp_path / "hooks"
        hooks.mkdir()
        (hooks / "fsmonitor").write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        (hooks / "fsmonitor").chmod(0o755)
        git(tmp_path, "config", "core.fsmonitor", str(hooks / "fsmonitor"))

        RepoTree.from_git(tmp_path)

        assert not marker.exists()

    def test_tracked_files_only(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "1\n"}, with_gate=False)
        (tmp_path / "untracked.py").write_text("2\n", encoding="utf-8")

        loaded = RepoTree.from_git(tmp_path)

        assert loaded.has("a.py")
        assert not loaded.has("untracked.py")

    def test_digest_is_the_content_hash(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "hello\n"}, with_gate=False)

        digest = RepoTree.from_git(tmp_path).digest("a.py")

        assert digest == "5891b5b522d5df086d0ff0b110fbd9d21bb4fc7163af34d08286a2e846f6be03"

    def test_a_directory_that_is_not_a_repository_fails_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="git ls-files failed"):
            RepoTree.from_git(tmp_path)

    def test_non_utf8_paths_do_not_crash(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.py": "1\n"}, with_gate=False)
        git(tmp_path, "config", "core.quotepath", "false")

        assert RepoTree.from_git(tmp_path).has("a.py")


class TestTokens:
    def test_a_long_run_of_plus_characters_scans_in_linear_time(self) -> None:
        import time

        start = time.perf_counter()
        tokens_in("+" * 190_000 + "/a")

        assert time.perf_counter() - start < 5

    def test_text_past_the_bound_is_not_scanned(self) -> None:
        text = "scripts/a.py " + "x" * 300_000 + " scripts/late.py"

        assert tokens_in(text) == ["scripts/a.py"]

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("python scripts/a.py --x", ["scripts/a.py"]),
            ("bash ./scripts/run.sh", ["./scripts/run.sh"]),
            (
                "uv run python scripts/ci/x.py arg .github/y.yml",
                ["scripts/ci/x.py", ".github/y.yml"],
            ),
            ("curl https://example.com/a/b.py", []),
            ("cat ${{ github.workspace }}/scripts/a.py", []),
            ("plain words and flags --long-flag", []),
            ("a/b", ["a/b"]),
        ],
    )
    def test_path_like_tokens(self, text: str, expected: list[str]) -> None:
        assert tokens_in(text) == expected

    def test_normalize_strips_one_leading_dot_slash(self) -> None:
        assert normalize("./a/b.py") == "a/b.py"
        assert normalize("a/b.py") == "a/b.py"

    def test_a_tracked_token_is_an_edge(self, tree: RepoTree) -> None:
        edges, unresolved = resolve_tokens("python scripts/a.py", "wf", EDGE_WORKFLOW_REF, tree)

        assert edges == [Edge(EDGE_WORKFLOW_REF, "wf", "scripts/a.py")]
        assert unresolved == []

    def test_a_repo_rooted_executable_that_is_not_tracked_is_unresolved(
        self, tree: RepoTree
    ) -> None:
        edges, unresolved = resolve_tokens(
            "python scripts/missing.py", "wf", EDGE_WORKFLOW_REF, tree
        )

        assert edges == []
        assert [u.detail for u in unresolved] == [
            "names scripts/missing.py, which is not a tracked file"
        ]

    @pytest.mark.parametrize(
        "text",
        [
            "echo artifacts/report.xml",
            "echo build/output.bin",
            "echo docs/missing.md",
            "echo ./sarif-results",
            "echo other/thing.py",
        ],
    )
    def test_generated_documentation_and_foreign_paths_are_not_findings(
        self, tree: RepoTree, text: str
    ) -> None:
        _, unresolved = resolve_tokens(text, "wf", EDGE_WORKFLOW_REF, tree)

        assert unresolved == []

    def test_a_tracked_documentation_file_is_still_an_edge(self, tree: RepoTree) -> None:
        edges, _ = resolve_tokens("cat docs/readme.md", "wf", EDGE_WORKFLOW_REF, tree)

        assert [e.target for e in edges] == ["docs/readme.md"]

    def test_a_dot_slash_token_in_a_script_resolves_beside_the_script(self, tmp_path: Path) -> None:
        make_repo(
            tmp_path, {"tools/run.sh": "./helper.sh\n", "tools/helper.sh": "x\n"}, with_gate=False
        )
        loaded = RepoTree.from_git(tmp_path)

        edges, unresolved = resolve_tokens(
            "./helper.sh", "tools/run.sh", EDGE_WORKFLOW_REF, loaded, "tools"
        )

        assert [e.target for e in edges] == ["tools/helper.sh"]
        assert unresolved == []

    def test_a_dot_slash_token_missing_everywhere_is_unresolved(self, tree: RepoTree) -> None:
        _, unresolved = resolve_tokens(
            "./gone.sh", "scripts/run.sh", EDGE_WORKFLOW_REF, tree, "scripts"
        )

        assert len(unresolved) == 1


class TestActionInputs:
    def test_a_with_value_naming_a_tracked_file_is_an_action_input_edge(
        self, tree: RepoTree
    ) -> None:
        edges, unresolved = resolve_action_inputs(
            {"config-file": ".github/codeql/config.yml", "languages": "python"},
            "wf:job:step[2]",
            tree,
        )

        assert edges == [
            Edge(EDGE_ACTION_INPUT, "wf:job:step[2]#with.config-file", ".github/codeql/config.yml")
        ]
        assert unresolved == []

    def test_a_missing_config_input_is_unresolved(self, tree: RepoTree) -> None:
        _, unresolved = resolve_action_inputs(
            {"config-file": ".github/codeql/gone.yml"}, "wf", tree
        )

        assert [u.source for u in unresolved] == ["wf#with.config-file"]

    def test_non_string_values_are_skipped(self, tree: RepoTree) -> None:
        assert resolve_action_inputs({"fetch-depth": 0, "flag": True}, "wf", tree) == ([], [])

    def test_a_multi_token_value_yields_every_file(self, tree: RepoTree) -> None:
        edges, _ = resolve_action_inputs(
            {"paths": "scripts/a.py\n.github/codeql/config.yml"}, "wf", tree
        )

        assert sorted(e.target for e in edges) == [".github/codeql/config.yml", "scripts/a.py"]


class TestUses:
    def test_a_local_action_resolves_to_its_action_file(self, tree: RepoTree) -> None:
        edges, pins, unresolved, follow = resolve_uses("./.github/actions/setup", "wf", tree)

        assert follow == ".github/actions/setup/action.yml"
        assert edges == [Edge(EDGE_WORKFLOW_REF, "wf", ".github/actions/setup/action.yml")]
        assert pins == {}
        assert unresolved == []

    def test_a_local_reusable_workflow_resolves_to_the_file(self, tree: RepoTree) -> None:
        _, _, _, follow = resolve_uses("./.github/workflows/reuse.yml", "wf", tree)

        assert follow == ".github/workflows/reuse.yml"

    def test_a_local_action_with_no_action_file_is_unresolved(self, tree: RepoTree) -> None:
        edges, _, unresolved, follow = resolve_uses("./.github/actions/missing", "wf", tree)

        assert edges == []
        assert follow is None
        assert len(unresolved) == 1

    def test_an_external_action_pinned_to_a_commit_is_recorded(self, tree: RepoTree) -> None:
        edges, pins, unresolved, follow = resolve_uses(f"actions/checkout@{SHA}", "wf", tree)

        assert (edges, unresolved, follow) == ([], [], None)
        assert pins == {f"uses:actions/checkout@{SHA}": "pinned"}

    @pytest.mark.parametrize("ref", ["v4", "main", "v4.1.2", "abc123", "A" * 40])
    def test_an_external_action_on_a_tag_or_branch_is_unresolved(
        self, tree: RepoTree, ref: str
    ) -> None:
        _, pins, unresolved, _ = resolve_uses(f"actions/checkout@{ref}", "wf", tree)

        assert pins == {}
        assert "not pinned to a commit" in unresolved[0].detail

    def test_a_uses_with_no_ref_is_unresolved(self, tree: RepoTree) -> None:
        _, _, unresolved, _ = resolve_uses("actions/checkout", "wf", tree)

        assert "names no ref" in unresolved[0].detail

    def test_a_docker_image_needs_a_digest(self, tree: RepoTree) -> None:
        digest = "@sha256:" + "b" * 64
        _, pins, unresolved, _ = resolve_uses(f"docker://alpine{digest}", "wf", tree)
        _, _, floating, _ = resolve_uses("docker://alpine:3", "wf", tree)

        assert pins == {f"uses:docker://alpine{digest}": "pinned"}
        assert unresolved == []
        assert "no digest" in floating[0].detail


class TestConfigCommands:
    def test_a_yaml_string_naming_a_script_is_a_config_command_edge(self, tree: RepoTree) -> None:
        document = {
            "scripts": {"go": "python3 scripts/a.py --pr {n}", "note": "see docs/readme.md"}
        }

        edges, unresolved = resolve_config_commands(document, "cfg.yaml", tree)

        assert edges == [Edge(EDGE_CONFIG_COMMAND, "cfg.yaml", "scripts/a.py")]
        assert unresolved == []

    def test_a_missing_script_is_unresolved_but_a_missing_document_is_not(
        self, tree: RepoTree
    ) -> None:
        _, unresolved = resolve_config_commands(
            ["python scripts/gone.py", "see docs/gone.md"], "cfg.yaml", tree
        )

        assert [u.detail for u in unresolved] == [
            "names scripts/gone.py, which is not a tracked file"
        ]

    def test_nested_lists_and_mappings_are_walked(self, tree: RepoTree) -> None:
        document = {"a": [{"b": ["run scripts/run.sh"]}]}

        edges, _ = resolve_config_commands(document, "cfg.json", tree)

        assert [e.target for e in edges] == ["scripts/run.sh"]


class TestLoadConfig:
    @pytest.mark.parametrize(
        ("name", "body", "expected"),
        [
            ("a.yml", "k: v\n", {"k": "v"}),
            ("a.yaml", "- 1\n", [1]),
            ("a.json", '{"k": 2}', {"k": 2}),
            ("a.toml", "k = 3\n", {"k": 3}),
        ],
    )
    def test_parses_data_formats(
        self, tmp_path: Path, name: str, body: str, expected: object
    ) -> None:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")

        assert load_config(path) == expected

    @pytest.mark.parametrize(
        ("name", "body"),
        [
            ("bad.yml", "k: [unclosed\n"),
            ("bad.json", "{"),
            ("bad.toml", "k ="),
            ("notes.txt", "k: v\n"),
            ("nested.yml", "x: " + "[" * 4000 + "]" * 4000 + "\n"),
        ],
    )
    def test_anything_unparseable_or_unknown_is_none(
        self, tmp_path: Path, name: str, body: str
    ) -> None:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")

        assert load_config(path) is None

    def test_a_missing_file_is_none(self, tmp_path: Path) -> None:
        assert load_config(tmp_path / "absent.yml") is None
