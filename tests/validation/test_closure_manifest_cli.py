"""CLI, comparison and real-tree tests for the closure manifest (ADR-101)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import closure_manifest as cm
import pytest
from closure_model import Edge, Manifest, Unresolved, diff

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from tests.validation.closure_helpers import REPO_ROOT, make_repo, workflow

WF = ".github/workflows/t.yml"
CLEAN = {WF: workflow("g", "      - run: python scripts/x.py\n"), "scripts/x.py": "1\n"}


@pytest.fixture(autouse=True)
def _one_pinned_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cm, "REQUIRED_CONTEXTS", frozenset({"Run Python Tests"}))


class TestModel:
    def test_to_json_is_sorted_and_stable(self) -> None:
        manifest = Manifest(
            entrypoints={"b", "a"},
            files={"z": "1", "a": "2"},
            edges={Edge("k", "s2", "t"), Edge("k", "s1", "t")},
            recorded={"y": "1", "x": "2"},
            unresolved={Unresolved("k", "s", "d2"), Unresolved("k", "s", "d1")},
        )

        document = manifest.to_json()

        assert document["entrypoints"] == ["a", "b"]
        assert list(document["files"]) == ["a", "z"]
        assert document["edges"] == [["k", "s1", "t"], ["k", "s2", "t"]]
        assert list(document["recorded"]) == ["x", "y"]
        assert [u[2] for u in document["unresolved"]] == ["d1", "d2"]

    def test_diff_reports_every_kind_of_movement(self) -> None:
        old = {
            "files": {"keep": "1", "gone": "1", "edit": "1"},
            "recorded": {"a": "1", "b": "1"},
            "edges": [["k", "s", "t1"]],
        }
        new = {
            "files": {"keep": "1", "new": "1", "edit": "2"},
            "recorded": {"a": "1", "b": "2", "c": "3"},
            "edges": [["k", "s", "t2"]],
        }

        assert diff(old, new) == {
            "files_added": ["new"],
            "files_removed": ["gone"],
            "files_changed": ["edit"],
            "recorded_changed": ["b", "c"],
            "edges_added": ["k -> s -> t2"],
            "edges_removed": ["k -> s -> t1"],
        }

    def test_diff_of_equal_documents_is_all_empty(self) -> None:
        document = Manifest(files={"a": "1"}).to_json()

        assert all(not moved for moved in diff(document, document).values())


class TestMain:
    def test_a_clean_tree_exits_zero_and_writes_the_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_repo(tmp_path, CLEAN)
        out = tmp_path.parent / f"{tmp_path.name}-manifest.json"

        code = cm.main(["--root", str(tmp_path), "--output", str(out)])

        assert code == cm.EXIT_OK
        assert json.loads(out.read_text(encoding="utf-8"))["entrypoints"] == [f"{WF}:g"]
        assert "0 unresolved" in capsys.readouterr().out

    def test_an_unresolved_edge_exits_one_and_is_printed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        files = {WF: workflow("g", "      - uses: actions/checkout@v4\n")}
        make_repo(tmp_path, files)

        code = cm.main(["--root", str(tmp_path)])

        assert code == cm.EXIT_FAILED
        assert "UNRESOLVED [workflow-reference]" in capsys.readouterr().out

    def test_advisory_reports_the_same_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_repo(tmp_path, {WF: workflow("g", "      - uses: actions/checkout@v4\n")})

        code = cm.main(["--root", str(tmp_path), "--advisory"])

        assert code == cm.EXIT_OK
        assert "UNRESOLVED" in capsys.readouterr().out

    def test_a_workflow_directory_that_does_not_parse_is_a_config_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_repo(tmp_path, {WF: "jobs: [unclosed\n"})

        code = cm.main(["--root", str(tmp_path), "--advisory"])

        assert code == cm.EXIT_CONFIG
        assert "ERROR" in capsys.readouterr().err

    def test_a_tree_with_no_git_directory_is_walked_and_fails_closed(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "workflows").mkdir(parents=True)

        assert cm.main(["--root", str(tmp_path)]) == cm.EXIT_FAILED

    def test_a_root_with_no_workflow_directory_is_a_config_error(self, tmp_path: Path) -> None:
        assert cm.main(["--root", str(tmp_path / "missing")]) == cm.EXIT_CONFIG

    def test_non_ascii_text_in_a_finding_is_escaped_not_raised(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_repo(tmp_path, {WF: workflow("g", "      - uses: 'actions/café@v4'\n")})

        code = cm.main(["--root", str(tmp_path), "--advisory"])

        assert code == cm.EXIT_OK
        assert capsys.readouterr().out.isascii()


class TestAgainst:
    def _emit(self, root: Path, name: str) -> Path:
        out = root.parent / f"{root.name}-{name}.json"
        cm.main(["--root", str(root), "--output", str(out)])
        return out

    def test_an_unchanged_tree_matches_and_exits_zero_under_fail_on_change(
        self, tmp_path: Path
    ) -> None:
        make_repo(tmp_path, CLEAN)
        baseline = self._emit(tmp_path, "base")

        code = cm.main(["--root", str(tmp_path), "--against", str(baseline), "--fail-on-change"])

        assert code == cm.EXIT_OK

    def test_a_changed_file_is_reported_and_fails_only_with_fail_on_change(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        make_repo(tmp_path, CLEAN)
        baseline = self._emit(tmp_path, "base")
        (tmp_path / "scripts/x.py").write_text("2\n", encoding="utf-8")
        capsys.readouterr()

        report_only = cm.main(["--root", str(tmp_path), "--against", str(baseline)])
        strict = cm.main(["--root", str(tmp_path), "--against", str(baseline), "--fail-on-change"])

        assert report_only == cm.EXIT_OK
        assert strict == cm.EXIT_FAILED
        assert "files_changed: 1" in capsys.readouterr().out

    def test_an_unreadable_baseline_is_a_config_error(self, tmp_path: Path) -> None:
        make_repo(tmp_path, CLEAN)

        assert cm.main(["--root", str(tmp_path), "--against", str(tmp_path / "absent.json")]) == (
            cm.EXIT_CONFIG
        )

    def test_a_baseline_that_is_not_a_manifest_is_a_config_error(self, tmp_path: Path) -> None:
        make_repo(tmp_path, CLEAN)
        bad = tmp_path.parent / f"{tmp_path.name}-list.json"
        bad.write_text("[1]", encoding="utf-8")

        assert cm.main(["--root", str(tmp_path), "--against", str(bad)]) == cm.EXIT_CONFIG


class TestCodeownersCheck:
    def test_an_owned_manifest_passes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        files = {**CLEAN, ".github/CODEOWNERS": "/.github/ @o\n/scripts/ @o\n"}
        make_repo(tmp_path, files)

        code = cm.main(["--root", str(tmp_path), "--check-codeowners"])

        assert code == cm.EXIT_OK
        assert "0 of" in capsys.readouterr().out

    def test_an_unowned_file_fails_and_is_named(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        files = {**CLEAN, ".github/CODEOWNERS": "/.github/ @o\n"}
        make_repo(tmp_path, files)

        code = cm.main(["--root", str(tmp_path), "--check-codeowners"])

        assert code == cm.EXIT_FAILED
        assert "UNCOVERED scripts/x.py" in capsys.readouterr().out

    def test_a_named_exclusion_with_a_reason_clears_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        files = {**CLEAN, ".github/CODEOWNERS": "/.github/ @o\n"}
        make_repo(tmp_path, files)
        monkeypatch.setattr(cm, "CODEOWNERS_EXCLUSIONS", {"scripts/x.py": "generated"})

        assert cm.main(["--root", str(tmp_path), "--check-codeowners"]) == cm.EXIT_OK

    def test_an_unsupported_pattern_is_a_config_error_not_a_guess(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {**CLEAN, ".github/CODEOWNERS": "!/scripts/ @o\n"})

        assert cm.main(["--root", str(tmp_path), "--check-codeowners"]) == cm.EXIT_CONFIG

    def test_a_missing_codeowners_file_is_a_config_error(self, tmp_path: Path) -> None:
        make_repo(tmp_path, CLEAN)

        assert cm.main(["--root", str(tmp_path), "--check-codeowners"]) == cm.EXIT_CONFIG


class TestTheRepositoryItself:
    """Run against this checkout, the way ci-scripts.md rule 13 asks of a new gate."""

    @pytest.fixture(scope="class")
    @classmethod
    def manifest(cls) -> Manifest:
        # The class-scoped fixture cannot use the function-scoped autouse patch,
        # so pin the real contexts for the build and restore them afterwards.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(cm, "REQUIRED_CONTEXTS", REQUIRED_CONTEXTS)
            return cm.build_manifest(REPO_ROOT)

    def test_every_pinned_context_has_an_entrypoint(self, manifest: Manifest) -> None:
        assert not [u for u in manifest.unresolved if u.detail.startswith("no job produces")]
        assert len(manifest.entrypoints) >= 6

    def test_every_entrypoint_workflow_is_a_hashed_file_with_a_recorded_trigger(
        self, manifest: Manifest
    ) -> None:
        for entrypoint in manifest.entrypoints:
            workflow_file = entrypoint.rsplit(":", maxsplit=1)[0]
            assert workflow_file in manifest.files
            assert f"{workflow_file}:on" in manifest.recorded

    def test_the_edge_kinds_the_adr_names_are_all_exercised(self, manifest: Manifest) -> None:
        kinds = {edge.kind for edge in manifest.edges}

        assert kinds >= {
            "module-import",
            "action-input-file",
            "workflow-reference",
            "runtime-config",
        }

    def test_the_action_input_files_the_adr_calls_out_are_in_the_closure(
        self, manifest: Manifest
    ) -> None:
        assert ".github/codeql/codeql-config.yml" in manifest.files
        # path_policy.yml left the closure when the pytest context stopped depending on
        # the check-paths job (its condition is no longer part of the verdict).
        assert "scripts/test_selection/path_policy.yml" not in manifest.files

    def test_the_manifest_holds_only_tracked_files(self, manifest: Manifest) -> None:
        from closure_resolvers import RepoTree

        tracked = RepoTree.from_git(REPO_ROOT).tracked

        assert set(manifest.files) <= tracked


class TestOutputEscaping:
    def test_a_newline_in_an_unresolved_detail_is_escaped(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cm._plain("a\n::error::x\x7f") == "a\\x0a::error::x\\x7f"
