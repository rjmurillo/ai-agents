"""Tests for the literal plugin path check in the exec portability gate (issue #7226).

A shipped instruction must not run a script through a literal ``.claude/skills``,
``.claude/hooks`` or ``.claude/lib`` path. The check has no baseline.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
_ORIGINAL_SYS_PATH = sys.path.copy()
try:
    sys.path.insert(0, str(_VALIDATION))
    import check_skill_md_exec_portability as cep
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH

_PORTABLE = '"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/demo/scripts/x.py"'


class TestFindLiteralPluginPaths:
    @pytest.mark.parametrize(
        "command",
        [
            "python3 .claude/skills/demo/scripts/x.py --flag",
            "python .claude/skills/demo/scripts/x.py",
            "uv run python .claude/skills/demo/scripts/x.py",
            "uv run --frozen python .claude/skills/demo/scripts/x.py",
            "pwsh .claude/skills/demo/scripts/x.ps1",
            "bash .claude/skills/demo/scripts/x.sh",
            "sh .claude/hooks/x.sh",
            "node .claude/skills/demo/scripts/x.py",
            "python3 .claude/lib/tool.py",
            "python3 .claude/hooks/PreToolUse/guard.py",
            "./.claude/skills/demo/scripts/x.sh",
            'python3 ".claude/skills/demo/scripts/x.py"',
            "python3 -u .claude/skills/demo/scripts/x.py",
        ],
    )
    def test_flags_each_interpreter_and_tree(self, command: str) -> None:
        assert len(cep.find_literal_plugin_paths(f"Run `{command}` now.\n")) == 1

    def test_flags_a_line_continuation_and_reports_the_first_line(self) -> None:
        text = "intro\n```bash\npython3 \\\n  .claude/skills/demo/scripts/x.py --flag\n```\n"
        assert cep.find_literal_plugin_paths(text) == [(3, "skills/demo/scripts/x.py")]

    def test_flags_each_site_on_its_own_line(self) -> None:
        text = (
            "python3 .claude/skills/a/scripts/one.py\n"
            "text\n"
            "python3 .claude/skills/b/scripts/two.py\n"
        )
        assert [line for line, _ in cep.find_literal_plugin_paths(text)] == [1, 3]

    def test_flags_a_table_cell_and_a_pipeline(self) -> None:
        text = (
            "| 3.1 | Verify | `python3 .claude/skills/a/scripts/one.py` exits 0 |\n"
            "git diff | python3 .claude/skills/b/scripts/two.py\n"
        )
        assert len(cep.find_literal_plugin_paths(text)) == 2

    def test_accepts_the_portable_form(self) -> None:
        assert cep.find_literal_plugin_paths(f"python3 {_PORTABLE} --flag\n") == []

    def test_accepts_the_portable_form_with_an_unquoted_tail(self) -> None:
        text = 'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"/skills/a/x.py\n'
        assert cep.find_literal_plugin_paths(text) == []

    @pytest.mark.parametrize(
        "prose",
        [
            "The script lives at `.claude/skills/demo/scripts/x.py`.",
            "See .claude/lib/tool.py for the helper.",
            "| `.claude/skills/demo/scripts/x.py` | Validate the file. |",
            "Modeled on `.claude/skills/github/scripts/pr/check_pr_round_cap.py`.",
            "Scan the tree: `--directory .claude/skills/`.",
            "analyze_skill_placement.py -p .claude/skills/github",
            "Edit ~/.claude/skills/my-skill/notes.md by hand.",
        ],
    )
    def test_ignores_a_path_with_no_interpreter(self, prose: str) -> None:
        assert cep.find_literal_plugin_paths(prose + "\n") == []

    def test_ignores_a_path_that_is_not_a_script(self) -> None:
        assert cep.find_literal_plugin_paths("python3 .claude/skills/demo/data.json\n") == []

    def test_ignores_a_scripts_tree_invocation(self) -> None:
        # ``scripts/`` and ``build/`` belong to the baseline ratchet, not this check.
        assert cep.find_literal_plugin_paths("python3 scripts/validation/x.py\n") == []

    def test_marker_exempts_a_dogfood_only_example(self) -> None:
        text = (
            "<!-- vendor-portability-exec: dogfood example, runs in this repository only -->\n"
            "```bash\npython3 .claude/skills/demo/scripts/x.py\n```\n"
        )
        assert cep.find_literal_plugin_paths(text) == []

    def test_an_unrelated_comment_does_not_exempt(self) -> None:
        text = "<!-- vendor-portability: declared -->\npython3 .claude/skills/demo/scripts/x.py\n"
        assert len(cep.find_literal_plugin_paths(text)) == 1

    @pytest.mark.parametrize("rel", sorted(cep.LITERAL_ALLOWANCES))
    def test_allowance_covers_only_its_own_script(self, rel: str) -> None:
        assert cep.find_literal_plugin_paths(f"uv run python .claude/{rel} --x\n") == []
        other = "uv run python .claude/skills/other/scripts/other.py\n"
        assert len(cep.find_literal_plugin_paths(other)) == 1

    def test_allowance_entries_name_real_scripts(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for rel in cep.LITERAL_ALLOWANCES:
            assert (root / "src" / "claude" / rel).is_file(), rel

    def test_empty_text_has_no_hits(self) -> None:
        assert cep.find_literal_plugin_paths("") == []


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill(root: Path, name: str, body: str, *, tree: str = ".claude/skills") -> None:
    _write(root, f"{tree}/{name}/SKILL.md", f"---\nname: {name}\n---\n{body}")


class TestScanLiteralPluginPaths:
    def test_scans_skill_body_reference_and_readme(self, tmp_path: Path) -> None:
        cmd = "python3 .claude/skills/demo/scripts/x.py\n"
        _skill(tmp_path, "demo", cmd)
        _write(tmp_path, ".claude/skills/demo/references/more.md", cmd)
        _write(tmp_path, ".claude/skills/demo/README.md", cmd)
        hits, examined = cep.scan_literal_plugin_paths(tmp_path)
        assert examined == 3
        assert sorted(hit.split(":")[0] for hit in hits) == [
            ".claude/skills/demo/README.md",
            ".claude/skills/demo/SKILL.md",
            ".claude/skills/demo/references/more.md",
        ]

    def test_scans_the_copilot_skill_tree(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", "uv run python .claude/lib/x.py\n", tree="src/copilot-cli/skills")
        hits, _ = cep.scan_literal_plugin_paths(tmp_path)
        assert hits == ["src/copilot-cli/skills/demo/SKILL.md:4: .claude/lib/x.py"]

    @pytest.mark.parametrize(
        "rel",
        [
            "src/claude/agents/helper.md",
            "src/copilot-cli/agents/helper.agent.md",
            "src/copilot-cli/instructions/helper.instructions.md",
            "src/cursor/agents/helper.md",
            "src/cursor/rules/helper.mdc",
            "src/vs-code-agents/helper.agent.md",
            "templates/agents/helper.claude.md.tmpl",
            "templates/agents/partials/helper.mustache",
            "templates/rules/helper.md",
            "src/claude/rules/helper.md",
            "src/codex/agents/helper.toml",
        ],
    )
    def test_scans_agent_and_rule_files(self, tmp_path: Path, rel: str) -> None:
        _skill(tmp_path, "demo", "clean\n")
        _write(tmp_path, rel, "Run `python3 .claude/skills/demo/scripts/x.py`.\n")
        hits, _ = cep.scan_literal_plugin_paths(tmp_path)
        assert hits == [f"{rel}:1: .claude/skills/demo/scripts/x.py"]

    def test_every_on_disk_instruction_tree_is_scanned(self) -> None:
        """Converse guard: a hand-authored agent, rule, or instruction tree must be listed."""
        root = Path(__file__).resolve().parents[2]
        bases = [root / "templates", root / "src"]
        bases.extend(sorted(path for path in (root / "src").iterdir() if path.is_dir()))
        on_disk: set[tuple[str, ...]] = set()
        for base in bases:
            for child in sorted(base.iterdir()):
                is_tree = child.name in {"agents", "rules", "instructions"}
                if child.is_dir() and (is_tree or child.name.endswith("-agents")):
                    on_disk.add(child.relative_to(root).parts)
        assert on_disk, "discovery found no agent or rule trees; the walk is broken"
        unlisted = sorted(on_disk - set(cep.LITERAL_EXTRA_DIRS))
        assert unlisted == [], f"add to LITERAL_EXTRA_DIRS: {unlisted}"
        missing = [parts for parts in cep.LITERAL_EXTRA_DIRS if not root.joinpath(*parts).is_dir()]
        assert missing == [], f"LITERAL_EXTRA_DIRS names a tree that is gone: {missing}"

    def test_every_allowance_is_still_invoked_in_the_repository(self) -> None:
        """Converse guard: an allowance that matches nothing is a stale exemption."""
        root = Path(__file__).resolve().parents[2]
        assert cep.unused_literal_allowances(root) == []

    def test_reports_an_allowance_that_no_file_invokes(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", "uv run python .claude/skills/used/scripts/a.py\n")
        allowances = ["skills/used/scripts/a.py", "skills/gone/scripts/b.py"]
        assert cep.unused_literal_allowances(tmp_path, allowances) == ["skills/gone/scripts/b.py"]

    def test_a_marked_file_does_not_count_as_a_use(self, tmp_path: Path) -> None:
        body = (
            "<!-- vendor-portability-exec: dogfood example -->\n"
            "uv run python .claude/skills/used/scripts/a.py\n"
        )
        _skill(tmp_path, "demo", body)
        assert cep.unused_literal_allowances(tmp_path, ["skills/used/scripts/a.py"]) == [
            "skills/used/scripts/a.py"
        ]

    def test_an_invocation_in_an_agent_tree_counts_as_a_use(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", "clean\n")
        _write(tmp_path, "src/claude/agents/a.md", "python3 .claude/skills/s/scripts/a.py\n")
        assert cep.unused_literal_allowances(tmp_path, ["skills/s/scripts/a.py"]) == []

    def test_scans_a_command_that_starts_a_line_in_a_generated_toml_agent(
        self, tmp_path: Path
    ) -> None:
        """A generated agent is one escaped line; the command follows a literal backslash-n."""
        _skill(tmp_path, "demo", "clean\n")
        body = "Run this:\\npython3 .claude/skills/demo/scripts/x.py --flag\\n"
        _write(tmp_path, "src/codex/agents/helper.toml", f'developer_instructions = "{body}"\n')
        hits, _ = cep.scan_literal_plugin_paths(tmp_path)
        assert [h.split(":")[:2] for h in hits] == [["src/codex/agents/helper.toml", "1"]]

    def test_a_clean_generated_toml_agent_has_no_hits(self, tmp_path: Path) -> None:
        """Negative control for the TOML decode."""
        _skill(tmp_path, "demo", "clean\n")
        _write(tmp_path, "src/codex/agents/helper.toml", 'developer_instructions = "Run it.\\n"\n')
        assert cep.scan_literal_plugin_paths(tmp_path)[0] == []

    def test_ignores_a_non_markdown_file_in_an_agent_tree(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", "clean\n")
        _write(tmp_path, "src/claude/agents/data.json", "python3 .claude/skills/a/scripts/x.py")
        assert cep.scan_literal_plugin_paths(tmp_path)[0] == []

    def test_clean_tree_reports_the_examined_count(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", f"python3 {_PORTABLE}\n")
        assert cep.scan_literal_plugin_paths(tmp_path) == ([], 1)

    def test_a_missing_agent_tree_is_skipped(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", "clean\n")
        assert cep.scan_literal_plugin_paths(tmp_path) == ([], 1)

    def test_refuses_a_symlink_that_escapes_the_repository(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "leak.md").write_text("python3 .claude/skills/a/scripts/x.py\n")
        repo = tmp_path / "repo"
        _skill(repo, "demo", "clean\n")
        (repo / "src/claude/agents").mkdir(parents=True)
        try:
            (repo / "src/claude/agents/leak.md").symlink_to(outside / "leak.md")
        except (OSError, NotImplementedError):
            pytest.skip("symlink creation unavailable on this platform (issue #7226)")
        with pytest.raises(OSError, match="outside the repository root"):
            cep.scan_literal_plugin_paths(repo)


def _seed(root: Path) -> None:
    for args in (
        ("init", "-q", "-b", "main"),
        ("add", "-A"),
        ("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "s"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class TestMainExitCode:
    def _run(self, root: Path) -> int:
        baseline = root / "baseline.json"
        baseline.write_text('{"files": {}, "marker_files": {}}', encoding="utf-8")
        return cep.main(["--repo-root", str(root), "--baseline", str(baseline)])

    def test_exits_1_on_a_literal_path(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        _skill(tmp_path, "demo", "python3 .claude/skills/demo/scripts/x.py\n")
        _seed(tmp_path)
        assert self._run(tmp_path) == 1
        out = capsys.readouterr().out
        assert "[LITERAL] .claude/skills/demo/SKILL.md:4: .claude/skills/demo/scripts/x.py" in out
        assert "Literal plugin paths: 1 in 1 files examined." in out

    def test_exits_0_on_the_portable_form(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _skill(tmp_path, "demo", f"python3 {_PORTABLE}\n")
        _seed(tmp_path)
        assert self._run(tmp_path) == 0
        assert "Literal plugin paths: 0 in 1 files examined." in capsys.readouterr().out

    def test_a_literal_path_in_an_agent_file_fails_the_run(self, tmp_path: Path) -> None:
        _skill(tmp_path, "demo", "clean\n")
        _write(tmp_path, "templates/agents/a.claude.md.tmpl", "python3 .claude/lib/x.py\n")
        _seed(tmp_path)
        assert self._run(tmp_path) == 1

    def test_a_literal_path_cannot_be_hidden_by_the_baseline(self, tmp_path: Path) -> None:
        # The ratchet grandfathers per-file counts. This class has none.
        _skill(tmp_path, "demo", "python3 .claude/skills/demo/scripts/x.py\n")
        _seed(tmp_path)
        baseline = tmp_path / "baseline.json"
        rel = ".claude/skills/demo/SKILL.md"
        baseline.write_text(f'{{"files": {{"{rel}": 5}}, "marker_files": {{}}}}', encoding="utf-8")
        assert cep.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 1


class TestJsonAndUpdateBaseline:
    def _hit(self, root: Path) -> Path:
        _skill(root, "demo", "python3 .claude/skills/demo/scripts/x.py\n")
        _seed(root)
        baseline = root / "baseline.json"
        baseline.write_text('{"files": {}, "marker_files": {}}', encoding="utf-8")
        return baseline

    def test_json_output_is_one_document_that_carries_literal_hits(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        baseline = self._hit(tmp_path)
        rc = cep.main(
            ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--output-format", "json"]
        )
        report = json.loads(capsys.readouterr().out)
        assert rc == 1
        assert report["literal_examined"] == 1
        assert report["literal"] == [
            ".claude/skills/demo/SKILL.md:4: .claude/skills/demo/scripts/x.py"
        ]

    def test_json_output_for_a_clean_tree_is_valid_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        _skill(tmp_path, "demo", f"python3 {_PORTABLE}\n")
        _seed(tmp_path)
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}, "marker_files": {}}', encoding="utf-8")
        rc = cep.main(
            ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--output-format", "json"]
        )
        report = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert report["literal"] == []

    def test_update_baseline_refuses_while_a_literal_path_exists(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        baseline = self._hit(tmp_path)
        before = baseline.read_text(encoding="utf-8")
        rc = cep.main(
            ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--update-baseline"]
        )
        assert rc == 1
        assert baseline.read_text(encoding="utf-8") == before
        assert "[LITERAL] .claude/skills/demo/SKILL.md:4" in capsys.readouterr().out


class TestCommittedTree:
    def test_the_shipped_tree_has_no_literal_plugin_paths(self) -> None:
        root = Path(__file__).resolve().parents[2]
        hits, examined = cep.scan_literal_plugin_paths(root)
        assert examined > 100
        assert hits == []
