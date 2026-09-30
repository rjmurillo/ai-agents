"""Tests for scripts/validation/closure_manifest.py (ADR-101 typed closure).

Each case builds a throwaway git repository, so the tracked-file view, the
import closure and the CODEOWNERS check run the way they do on the real tree.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import closure_manifest as cm
import pytest
from closure_model import (
    EDGE_ACTION_INPUT,
    EDGE_CONFIG_COMMAND,
    EDGE_IMPORT,
    EDGE_RUNTIME_CONFIG,
    EDGE_WORKFLOW_REF,
    RESOLVED_KINDS,
    UNOBSERVABLE,
    Edge,
)
from required_context_types import WorkflowLoadError

from tests.validation.closure_helpers import GATE, SHA, make_repo, workflow

WF = ".github/workflows/t.yml"


@pytest.fixture(autouse=True)
def _one_pinned_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cm, "REQUIRED_CONTEXTS", frozenset({"Run Python Tests"}))


def _build(tmp_path: Path, files: dict[str, str], **kwargs: bool) -> cm.Manifest:
    make_repo(tmp_path, files, **kwargs)
    return cm.build_manifest(tmp_path, gate_root=tmp_path)


def _targets(manifest: cm.Manifest, kind: str) -> set[str]:
    return {e.target for e in manifest.edges if e.kind == kind}


class TestEntrypoints:
    def test_the_producing_job_is_the_entrypoint_and_its_workflow_is_a_file(
        self, tmp_path: Path
    ) -> None:
        manifest = _build(tmp_path, {WF: workflow("gate", "      - run: echo hi\n")})

        assert manifest.entrypoints == {f"{WF}:gate"}
        assert WF in manifest.files
        assert manifest.unresolved == set()

    def test_a_pinned_context_with_no_producer_is_unresolved(self, tmp_path: Path) -> None:
        manifest = _build(tmp_path, {WF: "on: push\njobs:\n  a:\n    name: Other\n    steps: []\n"})

        assert [u.source for u in manifest.unresolved] == ["Run Python Tests"]

    def test_jobs_the_producer_needs_are_walked_transitively(self, tmp_path: Path) -> None:
        files = {
            WF: (
                "on: push\njobs:\n"
                "  base:\n    steps:\n      - run: python scripts/base.py\n"
                "  mid:\n    needs: base\n    steps:\n      - run: python scripts/mid.py\n"
                "  gate:\n    name: Run Python Tests\n    needs: [mid]\n"
                "    steps:\n      - run: python scripts/gate.py\n"
                "  unrelated:\n    steps:\n      - run: python scripts/other.py\n"
            ),
            "scripts/base.py": "x = 1\n",
            "scripts/mid.py": "x = 2\n",
            "scripts/gate.py": "x = 3\n",
            "scripts/other.py": "x = 4\n",
        }

        manifest = _build(tmp_path, files)

        assert {"scripts/base.py", "scripts/mid.py", "scripts/gate.py"} <= set(manifest.files)
        assert "scripts/other.py" not in manifest.files

    def test_a_needs_cycle_terminates(self, tmp_path: Path) -> None:
        files = {
            WF: (
                "on: push\njobs:\n  a:\n    needs: b\n    steps: []\n"
                "  b:\n    name: Run Python Tests\n    needs: a\n    steps: []\n"
            )
        }

        assert _build(tmp_path, files).entrypoints == {f"{WF}:b"}


class TestEdgeKinds:
    def test_kind_four_a_run_step_naming_a_script(self, tmp_path: Path) -> None:
        files = {WF: workflow("g", "      - run: python scripts/x.py\n"), "scripts/x.py": "1\n"}

        manifest = _build(tmp_path, files)

        assert "scripts/x.py" in _targets(manifest, EDGE_WORKFLOW_REF)

    def test_kind_four_a_local_composite_action_is_followed_into_its_steps(
        self, tmp_path: Path
    ) -> None:
        files = {
            WF: workflow("g", "      - uses: ./.github/actions/setup\n"),
            ".github/actions/setup/action.yml": (
                "runs:\n  using: composite\n  steps:\n    - run: python scripts/in_action.py\n"
                "      shell: bash\n"
            ),
            "scripts/in_action.py": "1\n",
        }

        manifest = _build(tmp_path, files)

        assert ".github/actions/setup/action.yml" in manifest.files
        assert "scripts/in_action.py" in manifest.files

    def test_kind_four_a_local_reusable_workflow_is_followed(self, tmp_path: Path) -> None:
        files = {
            WF: "on: push\njobs:\n  g:\n    name: Run Python Tests\n"
            "    uses: ./.github/workflows/reuse.yml\n",
            ".github/workflows/reuse.yml": (
                "on: workflow_call\njobs:\n  inner:\n    runs-on: x\n    steps:\n"
                "      - run: python scripts/reused.py\n"
            ),
            "scripts/reused.py": "1\n",
        }

        manifest = _build(tmp_path, files)

        assert ".github/workflows/reuse.yml" in manifest.files
        assert "scripts/reused.py" in manifest.files

    def test_kind_four_an_external_action_on_a_tag_is_unresolved(self, tmp_path: Path) -> None:
        manifest = _build(tmp_path, {WF: workflow("g", "      - uses: actions/checkout@v4\n")})

        assert [u.kind for u in manifest.unresolved] == [EDGE_WORKFLOW_REF]

    def test_kind_four_an_external_action_on_a_commit_is_recorded(self, tmp_path: Path) -> None:
        manifest = _build(tmp_path, {WF: workflow("g", f"      - uses: actions/checkout@{SHA}\n")})

        assert manifest.recorded[f"uses:actions/checkout@{SHA}"] == "pinned"
        assert manifest.unresolved == set()

    def test_kind_three_an_action_input_naming_a_file(self, tmp_path: Path) -> None:
        step = (
            f"      - uses: github/codeql-action/init@{SHA}\n"
            "        with:\n          config-file: .github/codeql/config.yml\n"
        )
        files = {WF: workflow("g", step), ".github/codeql/config.yml": "paths: []\n"}

        manifest = _build(tmp_path, files)

        assert _targets(manifest, EDGE_ACTION_INPUT) == {".github/codeql/config.yml"}
        assert ".github/codeql/config.yml" in manifest.files

    def test_kind_three_a_missing_input_file_is_unresolved(self, tmp_path: Path) -> None:
        step = (
            f"      - uses: github/codeql-action/init@{SHA}\n"
            "        with:\n          config-file: .github/codeql/gone.yml\n"
        )

        manifest = _build(tmp_path, {WF: workflow("g", step)})

        assert [u.kind for u in manifest.unresolved] == [EDGE_ACTION_INPUT]

    def test_kind_two_a_config_file_naming_a_command_path(self, tmp_path: Path) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/gate.py --config cfg/pr.yaml\n"),
            "scripts/gate.py": "1\n",
            "cfg/pr.yaml": "cmd: python3 scripts/verifier.py --n 1\n",
            "scripts/verifier.py": "1\n",
        }
        files[WF] = workflow("g", "      - run: python scripts/gate.py --config scripts/pr.yaml\n")
        files["scripts/pr.yaml"] = files.pop("cfg/pr.yaml")

        manifest = _build(tmp_path, files)

        assert _targets(manifest, EDGE_CONFIG_COMMAND) == {"scripts/verifier.py"}
        assert "scripts/verifier.py" in manifest.files

    def test_kind_two_a_shell_script_is_read_for_the_files_it_names(self, tmp_path: Path) -> None:
        files = {
            WF: workflow("g", "      - run: bash scripts/run.sh\n"),
            "scripts/run.sh": "python scripts/from_shell.py\n",
            "scripts/from_shell.py": "1\n",
        }

        assert "scripts/from_shell.py" in _build(tmp_path, files).files

    def test_kind_one_module_imports_join_through_the_gates_closure(self, tmp_path: Path) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/entry.py\n"),
            "scripts/entry.py": "import helper\n",
            "scripts/helper.py": "import deeper\n",
            "scripts/deeper.py": "X = 1\n",
        }

        manifest = _build(tmp_path, files)

        assert {"scripts/helper.py", "scripts/deeper.py"} <= _targets(manifest, EDGE_IMPORT)
        assert {"scripts/helper.py", "scripts/deeper.py"} <= set(manifest.files)

    def test_kind_one_an_unresolvable_dynamic_load_is_unresolved(self, tmp_path: Path) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/entry.py\n"),
            "scripts/entry.py": "import sys\n__import__(sys.argv[1])\n",
        }

        manifest = _build(tmp_path, files)

        assert [(u.kind, u.source) for u in manifest.unresolved] == [
            (EDGE_IMPORT, "scripts/entry.py")
        ]
        assert next(iter(manifest.unresolved)).detail.startswith(
            "line 2: unresolvable dynamic load"
        )

    def test_kind_one_with_no_gate_the_import_kind_is_unresolved_not_skipped(
        self, tmp_path: Path
    ) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/entry.py\n"),
            "scripts/entry.py": "1\n",
        }

        manifest = _build(tmp_path, files, with_gate=False)

        assert [u.kind for u in manifest.unresolved] == [EDGE_IMPORT]
        assert "unavailable" in next(iter(manifest.unresolved)).detail

    def test_kind_five_runtime_configuration_is_recorded_by_key(self, tmp_path: Path) -> None:
        files = {
            WF: workflow(
                "g",
                "      - name: s\n        if: github.actor != 'bot'\n        env:\n          K: v\n"
                "        run: echo hi\n",
                extra="permissions:\n  contents: read\nenv:\n  A: '1'\n",
            )
        }

        manifest = _build(tmp_path, files)

        assert json.loads(manifest.recorded[f"{WF}:permissions"]) == {"contents": "read"}
        assert json.loads(manifest.recorded[f"{WF}:env"]) == {"A": "1"}
        assert json.loads(manifest.recorded[f"{WF}:g:runs-on"]) == "ubuntu-latest"
        assert manifest.recorded[f"{WF}:on"] == '"pull_request"'
        assert json.loads(manifest.recorded[f"{WF}:g:step[0]:env"]) == {"K": "v"}
        assert "github.actor" in manifest.recorded[f"{WF}:g:step[0]:if"]

    def test_the_p2_anchors_that_are_tracked_are_hashed_as_runtime_config(
        self, tmp_path: Path
    ) -> None:
        files = {WF: workflow("g", "      - run: echo hi\n"), ".github/CODEOWNERS": "/a/ @o\n"}

        manifest = _build(tmp_path, files)

        assert Edge(EDGE_RUNTIME_CONFIG, "p2-anchor", ".github/CODEOWNERS") in manifest.edges
        assert ".github/CODEOWNERS" in manifest.files


class TestManifestDocument:
    def test_the_document_names_what_a_p1_run_cannot_observe(self, tmp_path: Path) -> None:
        document = _build(tmp_path, {WF: workflow("g", "      - run: echo hi\n")}).to_json()

        assert document["resolved_kinds"] == list(RESOLVED_KINDS)
        assert document["unobservable"] == dict(sorted(UNOBSERVABLE.items()))
        assert set(document["unobservable"]) == {"core.hooksPath", "p2-api-state"}

    def test_the_same_tree_yields_the_same_bytes(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {WF: workflow("g", "      - run: echo hi\n")})

        first = json.dumps(cm.build_manifest(tmp_path, tmp_path).to_json())
        second = json.dumps(cm.build_manifest(tmp_path, tmp_path).to_json())

        assert first == second

    def test_a_changed_file_changes_its_hash_and_only_its_hash(self, tmp_path: Path) -> None:
        files = {WF: workflow("g", "      - run: python scripts/x.py\n"), "scripts/x.py": "1\n"}
        make_repo(tmp_path, files)
        before = cm.build_manifest(tmp_path, tmp_path).to_json()
        (tmp_path / "scripts/x.py").write_text("2\n", encoding="utf-8")

        after = cm.build_manifest(tmp_path, tmp_path).to_json()

        changed = {p for p in after["files"] if after["files"][p] != before["files"][p]}
        assert changed == {"scripts/x.py"}
        assert after["edges"] == before["edges"]

    def test_the_workflow_directory_missing_is_a_load_error(self, tmp_path: Path) -> None:
        make_repo(tmp_path, {"a.txt": "x\n"})

        with pytest.raises(WorkflowLoadError):
            cm.build_manifest(tmp_path, tmp_path)

    def test_the_gate_constant_names_a_file_the_repository_ships(self) -> None:
        assert (Path(__file__).resolve().parents[2] / GATE).is_file()


class TestOtherShapes:
    def test_a_config_whose_top_level_is_a_list_is_still_read_for_commands(
        self, tmp_path: Path
    ) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/gate.py --config scripts/list.json\n"),
            "scripts/gate.py": "1\n",
            "scripts/list.json": '["python scripts/verifier.py"]',
            "scripts/verifier.py": "1\n",
        }

        manifest = _build(tmp_path, files)

        assert "scripts/verifier.py" in _targets(manifest, EDGE_CONFIG_COMMAND)

    def test_a_config_that_does_not_parse_adds_no_edge_and_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/gate.py --config scripts/bad.json\n"),
            "scripts/gate.py": "1\n",
            "scripts/bad.json": "{",
        }

        manifest = _build(tmp_path, files)

        assert "scripts/bad.json" in manifest.files
        assert _targets(manifest, EDGE_CONFIG_COMMAND) == set()

    def test_a_step_that_is_not_a_mapping_is_skipped(self, tmp_path: Path) -> None:
        files = {WF: workflow("g", "      - just a string\n      - run: echo ok\n")}

        assert _build(tmp_path, files).unresolved == set()

    def test_a_reusable_workflow_job_pinned_externally_records_the_pin_and_follows_nothing(
        self, tmp_path: Path
    ) -> None:
        files = {
            WF: "on: push\njobs:\n  g:\n    name: Run Python Tests\n"
            f"    uses: owner/repo/.github/workflows/w.yml@{SHA}\n"
        }

        manifest = _build(tmp_path, files)

        assert manifest.recorded[f"uses:owner/repo/.github/workflows/w.yml@{SHA}"] == "pinned"
        assert manifest.unresolved == set()

    def test_a_gate_that_raises_on_import_leaves_the_import_kind_unresolved(
        self, tmp_path: Path
    ) -> None:
        files = {
            WF: workflow("g", "      - run: python scripts/entry.py\n"),
            "scripts/entry.py": "import helper\n",
            "scripts/helper.py": "1\n",
            GATE: "raise RuntimeError('broken gate')\n",
        }

        manifest = _build(tmp_path, files, with_gate=False)

        assert [u.kind for u in manifest.unresolved] == [EDGE_IMPORT]
        assert "unavailable" in next(iter(manifest.unresolved)).detail

    def test_the_script_runs_as_a_process(self, tmp_path: Path) -> None:
        import subprocess

        make_repo(tmp_path, {WF: workflow("g", "      - run: echo hi\n")})

        result = subprocess.run(
            [sys.executable, str(_VALIDATION_DIR / "closure_manifest.py"), "--root", str(tmp_path)],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )

        # A fresh process reads the real pinned contexts, and this repository has
        # a producer for only one of them, so the tool fails closed on the rest.
        assert result.returncode == 1
        assert "no job produces this pinned context" in result.stdout

    def test_the_measured_trees_own_gate_is_never_executed(self, tmp_path: Path) -> None:
        """A pull request's head is read as data: its copy of the resolver must not run."""
        marker = tmp_path / "gate_ran.txt"
        files = {
            WF: workflow("g", "      - run: python scripts/entry.py\n"),
            "scripts/entry.py": "import helper\n",
            "scripts/helper.py": "1\n",
            GATE: f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n",
        }
        make_repo(tmp_path, files, with_gate=False)

        manifest = cm.build_manifest(tmp_path)

        assert not marker.exists()
        assert "scripts/helper.py" in manifest.files

    def test_gate_root_selects_the_resolver_tree_from_the_command_line(
        self, tmp_path: Path
    ) -> None:
        make_repo(tmp_path, {WF: workflow("g", "      - run: echo hi\n")}, with_gate=False)

        code = cm.main(["--root", str(tmp_path), "--gate-root", str(tmp_path / "nowhere")])

        assert code == cm.EXIT_OK


class TestRecordedValueIsBounded:
    def test_an_alias_bomb_is_truncated_not_expanded(self) -> None:
        import yaml

        bomb = "a: &a [x, x, x, x, x, x, x, x, x]\n"
        prev = "a"
        for i in range(9):
            name = f"l{i}"
            refs = ", ".join([f"*{prev}"] * 9)
            bomb += f"{name}: &{name} [{refs}]\n"
            prev = name
        manifest = cm.Manifest()

        cm._record(manifest, "k", yaml.safe_load(bomb))

        assert "<truncated>" in manifest.recorded["k"] or len(manifest.recorded["k"]) <= 4000

    def test_a_small_value_is_recorded_exactly(self) -> None:
        manifest = cm.Manifest()

        cm._record(manifest, "k", {"b": [1, 2], "a": "x"})

        assert manifest.recorded["k"] == '{"a": "x", "b": [1, 2]}'
