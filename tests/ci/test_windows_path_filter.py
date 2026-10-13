"""Tests for scripts/ci/windows_path_filter.py (issue #5380).

The module decides which `windows_path` test files a pull request reaches, so
the Windows runner starts only for a change that can move its verdict. The
failure that matters is under-selection, a change that reaches a Windows test
and is told it does not. Those cases are pinned against the real repository
below, next to unit tests over small trees.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.ci import run_pytest_windows as rpw
from scripts.ci import windows_path_filter as wpf

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _tree(root: Path, files: dict[str, str]) -> wpf.Inventory:
    for rel, text in files.items():
        _write(root, rel, text)
    return wpf.Inventory(files)


def _reach(root: Path, files: dict[str, str], start: str) -> set[str]:
    return wpf.reach(root, start, _tree(root, files))


class TestReach:
    def test_root_is_always_in_its_own_reach(self, tmp_path: Path) -> None:
        assert _reach(tmp_path, {"tests/test_a.py": "x = 1\n"}, "tests/test_a.py") == {
            "tests/test_a.py"
        }

    def test_dotted_import_resolves_to_a_tracked_module(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "from scripts.ci import tool\n",
            "scripts/ci/tool.py": "x = 1\n",
            "scripts/ci/other.py": "x = 1\n",
        }

        reached = _reach(tmp_path, files, "tests/test_a.py")

        assert "scripts/ci/tool.py" in reached
        assert "scripts/ci/other.py" not in reached

    def test_bare_import_resolves_by_module_tail(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "import validate_thing\n",
            "build/scripts/validate_thing.py": "x = 1\n",
        }

        assert "build/scripts/validate_thing.py" in _reach(tmp_path, files, "tests/test_a.py")

    def test_package_import_resolves_to_init(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "import pkg.sub\n",
            "pkg/sub/__init__.py": "x = 1\n",
        }

        assert "pkg/sub/__init__.py" in _reach(tmp_path, files, "tests/test_a.py")

    def test_relative_import_is_ignored(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "from . import helper\n",
            "tests/helper.py": "x = 1\n",
        }

        assert "tests/helper.py" not in _reach(tmp_path, files, "tests/test_a.py")

    def test_literal_path_resolves_to_a_tracked_file(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'P = ".github/workflows/pytest.yml"\n',
            ".github/workflows/pytest.yml": "name: x\n",
        }

        assert ".github/workflows/pytest.yml" in _reach(tmp_path, files, "tests/test_a.py")

    def test_windows_separator_literal_resolves(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'P = "scripts\\\\ci\\\\tool.py"\n',
            "scripts/ci/tool.py": "x = 1\n",
        }

        assert "scripts/ci/tool.py" in _reach(tmp_path, files, "tests/test_a.py")

    def test_slash_joined_literals_resolve_as_one_path(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'p = ROOT / "scripts" / "eval" / "runner.json"\n',
            "scripts/eval/runner.json": "{}\n",
        }

        assert "scripts/eval/runner.json" in _reach(tmp_path, files, "tests/test_a.py")

    def test_join_run_stops_at_a_computed_segment(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'p = ROOT / "scripts" / name / "runner.json"\n',
            "scripts/runner.json": "{}\n",
        }

        reached = _reach(tmp_path, files, "tests/test_a.py")

        assert "scripts/runner.json" in reached  # the basename rule still sees the tail

    def test_basename_literal_resolves_every_tracked_file_of_that_name(
        self, tmp_path: Path
    ) -> None:
        files = {
            "tests/test_a.py": 'NAME = "lefthook.yml"\n',
            "lefthook.yml": "a: 1\n",
            "docs/lefthook.yml": "a: 1\n",
        }

        reached = _reach(tmp_path, files, "tests/test_a.py")

        assert {"lefthook.yml", "docs/lefthook.yml"} <= reached

    def test_word_without_a_file_suffix_resolves_nothing(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'WORD = "main"\n',
            "scripts/main": "x\n",
        }

        assert _reach(tmp_path, files, "tests/test_a.py") == {"tests/test_a.py"}

    def test_directory_literal_is_not_expanded(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'D = "scripts"\nE = "scripts/ci"\n',
            "scripts/ci/tool.py": "x = 1\n",
            "scripts/other.py": "x = 1\n",
        }

        assert _reach(tmp_path, files, "tests/test_a.py") == {"tests/test_a.py"}

    def test_parent_escape_literal_is_ignored(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'P = "../secret.py"\n',
            "secret.py": "x = 1\n",
        }

        assert "secret.py" not in _reach(tmp_path, files, "tests/test_a.py")

    def test_reach_follows_python_files_transitively(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "import mod_a\n",
            "lib/mod_a.py": 'import mod_b\nCFG = "settings.json"\n',
            "lib/mod_b.py": "x = 1\n",
            "etc/settings.json": "{}\n",
        }

        reached = _reach(tmp_path, files, "tests/test_a.py")

        assert {"lib/mod_a.py", "lib/mod_b.py", "etc/settings.json"} <= reached

    def test_non_python_file_is_not_parsed(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'P = "data.json"\n',
            "data.json": '"tool.py"\n',
            "tool.py": "x = 1\n",
        }

        assert "tool.py" not in _reach(tmp_path, files, "tests/test_a.py")

    def test_import_cycle_terminates(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "import mod_a\n",
            "lib/mod_a.py": "import mod_b\n",
            "lib/mod_b.py": "import mod_a\n",
        }

        assert _reach(tmp_path, files, "tests/test_a.py") == {
            "tests/test_a.py",
            "lib/mod_a.py",
            "lib/mod_b.py",
        }

    def test_unparseable_module_contributes_nothing_and_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        files = {
            "tests/test_a.py": "import broken\n",
            "lib/broken.py": "def (:\n",
        }

        assert _reach(tmp_path, files, "tests/test_a.py") == {"tests/test_a.py", "lib/broken.py"}

    def test_unreadable_module_contributes_nothing(self, tmp_path: Path) -> None:
        inventory = wpf.Inventory(["tests/test_a.py"])

        assert wpf.reach(tmp_path, "tests/test_a.py", inventory) == {"tests/test_a.py"}


class TestFilterPatterns:
    def _patterns(self, root: Path, files: dict[str, str]) -> dict[str, list[str]]:
        for rel, text in files.items():
            _write(root, rel, text)
        return wpf.filter_patterns(root, files)

    def test_one_key_per_marked_module(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "import pytest\npytestmark = pytest.mark.windows_path\n",
            "tests/test_b.py": "import pytest\npytestmark = pytest.mark.windows_path\n",
            "tests/test_c.py": "x = 1\n",
        }

        assert sorted(self._patterns(tmp_path, files)) == ["tests/test_a.py", "tests/test_b.py"]

    def test_each_key_lists_its_reach_and_the_fixed_triggers(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": "import tool\nwindows_path = 1\n",
            "tests/test_b.py": "windows_path = 1\n",
            "lib/tool.py": "x = 1\n",
        }

        patterns = self._patterns(tmp_path, files)

        assert "lib/tool.py" in patterns["tests/test_a.py"]
        assert "lib/tool.py" not in patterns["tests/test_b.py"]
        for key in patterns:
            assert set(wpf.ALWAYS_AFFECTED) <= set(patterns[key])

    def test_path_with_glob_syntax_widens_to_its_directory(self, tmp_path: Path) -> None:
        files = {
            "tests/test_a.py": 'windows_path = 1\nP = "docs/a[1].md"\n',
            "docs/a[1].md": "x\n",
        }

        assert "docs/**" in self._patterns(tmp_path, files)["tests/test_a.py"]

    @pytest.mark.parametrize("name", ["a\nb.md", "a\rb.md", "a\tb.md"])
    def test_path_with_a_line_break_or_tab_widens_to_its_directory(self, name: str) -> None:
        assert wpf._glob_for(f"docs/{name}") == "docs/**"

    def test_top_level_path_with_glob_syntax_widens_to_everything(self) -> None:
        assert wpf._glob_for("a[1].md") == wpf.MATCH_EVERYTHING

    def test_reads_tracked_files_from_git_when_not_given(self, tmp_path: Path) -> None:
        _write(tmp_path, "tests/test_a.py", "windows_path = 1\nimport tool\n")
        _write(tmp_path, "lib/tool.py", "x = 1\n")
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "x")

        assert "lib/tool.py" in wpf.filter_patterns(tmp_path)["tests/test_a.py"]


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


class TestTrackedFiles:
    def test_lists_committed_paths_with_awkward_names(self, tmp_path: Path) -> None:
        _write(tmp_path, "a b/c.py", "x\n")
        _write(tmp_path, "d.py", "x\n")
        _git(tmp_path, "init", "-q")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", "x")

        assert wpf.tracked_files(tmp_path) == ("a b/c.py", "d.py")

    def test_outside_a_repository_raises(self, tmp_path: Path) -> None:
        with pytest.raises(wpf.ReachError, match="git ls-tree exited"):
            wpf.tracked_files(tmp_path)

    def test_missing_git_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: object, **_k: object) -> None:
            raise FileNotFoundError("git")

        monkeypatch.setattr(wpf.subprocess, "run", boom)

        with pytest.raises(wpf.ReachError, match="could not list tracked files"):
            wpf.tracked_files(tmp_path)

    def test_timeout_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired("git", 60)

        monkeypatch.setattr(wpf.subprocess, "run", boom)

        with pytest.raises(wpf.ReachError):
            wpf.tracked_files(tmp_path)


class TestRender:
    def test_document_round_trips_through_yaml(self) -> None:
        patterns = {"tests/test_a.py": ["a.py", "it's.py", "dir/**"], "__all__": ["**"]}

        assert yaml.safe_load(wpf.render(patterns)) == patterns


class TestParseOutputs:
    def test_object_becomes_string_mapping(self) -> None:
        assert wpf.parse_outputs('{"a": "true", "changes": "[]"}') == {
            "a": "true",
            "changes": "[]",
        }

    @pytest.mark.parametrize("raw", ["", "   ", "not json", "[]", '"x"', "{}", "null"])
    def test_untrustworthy_input_is_none(self, raw: str) -> None:
        assert wpf.parse_outputs(raw) is None


MARKED = ["tests/test_a.py", "tests/test_b.py", "tests/test_c.py"]


class TestSelect:
    def _select(
        self,
        outputs: dict[str, str] | None,
        event: str = "pull_request",
        ref: str = "feature",
    ) -> tuple[bool, list[str]]:
        return wpf.select(outputs, MARKED, event, ref, "main")

    def test_unrelated_change_does_not_start_the_job(self) -> None:
        outputs = {path: "false" for path in MARKED} | {"changes": "[]"}

        assert self._select(outputs) == (False, [])

    def test_reached_modules_are_the_only_ones_selected(self) -> None:
        outputs = {
            "tests/test_a.py": "false",
            "tests/test_b.py": "true",
            "tests/test_c.py": "true",
            "changes": '["tests/test_b.py"]',
        }

        assert self._select(outputs) == (True, ["tests/test_b.py", "tests/test_c.py"])

    def test_selection_order_follows_discovery_not_the_action(self) -> None:
        outputs = {"tests/test_c.py": "true", "tests/test_a.py": "true"}

        assert self._select(outputs) == (True, ["tests/test_a.py", "tests/test_c.py"])

    def test_summary_key_alone_never_selects(self) -> None:
        assert self._select({"changes": "true"}) == (False, [])

    @pytest.mark.parametrize("event", ["merge_group", "workflow_dispatch"])
    def test_full_run_events_ignore_the_filter(self, event: str) -> None:
        outputs = {path: "false" for path in MARKED}

        assert self._select(outputs, event=event) == (True, [])

    def test_push_to_the_default_branch_runs_everything(self) -> None:
        outputs = {path: "false" for path in MARKED}

        assert self._select(outputs, event="push", ref="main") == (True, [])

    def test_push_to_a_feature_branch_is_narrowed(self) -> None:
        outputs = {path: "false" for path in MARKED}

        assert self._select(outputs, event="push", ref="feature") == (False, [])

    def test_push_with_no_ref_is_narrowed_not_mistaken_for_default(self) -> None:
        assert wpf.runs_everything("push", "", "") is False

    def test_missing_outputs_run_everything(self) -> None:
        assert self._select(None) == (True, [])

    def test_fallback_key_runs_everything(self) -> None:
        outputs = {wpf.FALLBACK_KEY: "true", "changes": "[]"}

        assert self._select(outputs) == (True, [])

    def test_stale_module_name_runs_everything_rather_than_dropping_it(self) -> None:
        outputs = {"tests/test_a.py": "true", "tests/test_gone.py": "true"}

        assert self._select(outputs) == (True, [])


class TestCli:
    def test_emit_writes_a_parseable_document(self, tmp_path: Path) -> None:
        out = tmp_path / "filter.yml"

        code = wpf.main(["--repo-root", str(REPO_ROOT), "emit", "--output", str(out)])

        assert code == wpf.EXIT_OK
        document = yaml.safe_load(out.read_text(encoding="utf-8"))
        assert sorted(document) == rpw.marked_files(REPO_ROOT)

    def test_emit_falls_back_to_match_everything_when_reach_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_root: Path) -> tuple[str, ...]:
            raise wpf.ReachError("no git")

        monkeypatch.setattr(wpf, "tracked_files", boom)
        out = tmp_path / "filter.yml"

        code = wpf.main(["emit", "--output", str(out)])

        assert code == wpf.EXIT_OK
        assert yaml.safe_load(out.read_text(encoding="utf-8")) == {wpf.FALLBACK_KEY: ["**"]}

    def test_emit_falls_back_when_a_test_module_is_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_root: Path) -> list[str]:
            raise rpw.DiscoveryError("unreadable")

        monkeypatch.setattr(rpw, "marked_files", boom)
        out = tmp_path / "filter.yml"

        assert wpf.main(["emit", "--output", str(out)]) == wpf.EXIT_OK
        assert yaml.safe_load(out.read_text(encoding="utf-8")) == {wpf.FALLBACK_KEY: ["**"]}

    def test_emit_returns_external_when_the_output_cannot_be_written(self, tmp_path: Path) -> None:
        out = tmp_path / "missing" / "filter.yml"

        assert wpf.main(["emit", "--output", str(out)]) == wpf.EXIT_EXTERNAL

    def _env(
        self, monkeypatch: pytest.MonkeyPatch, out: Path, outputs: str, event: str = "pull_request"
    ) -> None:
        monkeypatch.setenv("GITHUB_OUTPUT", str(out))
        monkeypatch.setenv("FILTER_OUTPUTS", outputs)
        monkeypatch.setenv("GH_EVENT_NAME", event)
        monkeypatch.setenv("GH_REF_NAME", "feature")
        monkeypatch.setenv("GH_DEFAULT_BRANCH", "main")

    def test_select_writes_both_outputs_for_an_unrelated_change(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out"
        marked = rpw.marked_files(REPO_ROOT)
        self._env(monkeypatch, out, json.dumps({m: "false" for m in marked} | {"changes": "[]"}))

        assert wpf.main(["select"]) == wpf.EXIT_OK
        assert out.read_text(encoding="utf-8") == "windows-affected=false\nwindows-files=[]\n"

    def test_select_writes_the_reached_modules(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out"
        marked = rpw.marked_files(REPO_ROOT)
        reached = {m: "false" for m in marked} | {marked[0]: "true"}
        self._env(monkeypatch, out, json.dumps(reached))

        assert wpf.main(["select"]) == wpf.EXIT_OK
        lines = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())
        assert lines["windows-affected"] == "true"
        assert json.loads(lines["windows-files"]) == [marked[0]]

    def test_select_runs_everything_when_outputs_are_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out = tmp_path / "out"
        self._env(monkeypatch, out, "{}")

        assert wpf.main(["select"]) == wpf.EXIT_OK
        assert out.read_text(encoding="utf-8") == "windows-affected=true\nwindows-files=[]\n"

    def test_select_runs_everything_when_discovery_is_incomplete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_root: Path) -> list[str]:
            raise rpw.DiscoveryError("unreadable")

        monkeypatch.setattr(rpw, "marked_files", boom)
        out = tmp_path / "out"
        self._env(monkeypatch, out, json.dumps({"tests/x.py": "false", "changes": "[]"}))

        assert wpf.main(["select"]) == wpf.EXIT_OK
        assert out.read_text(encoding="utf-8") == "windows-affected=true\nwindows-files=[]\n"

    def test_select_requires_github_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

        assert wpf.main(["select"]) == wpf.EXIT_CONFIG

    def test_select_returns_external_when_the_output_cannot_be_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._env(monkeypatch, tmp_path / "missing" / "out", "{}")

        assert wpf.main(["select"]) == wpf.EXIT_EXTERNAL

    def test_unknown_subcommand_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as raised:
            wpf.main(["bogus"])

        assert raised.value.code == 2
