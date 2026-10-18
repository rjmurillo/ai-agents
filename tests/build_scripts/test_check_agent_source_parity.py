"""Tests for build/scripts/check_agent_source_parity.py (issue #5688, ADR-107 M3).

The gate compares the three hand-written sources of each agent. The central
case is the issue's acceptance criterion: a contradiction injected into one
member fails the gate, including a contradiction in each of the ADR-107
section 5 invariants that live in prose.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "build" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import check_agent_source_parity as gate  # noqa: E402

SHARED_BODY = """# Widget Agent

Intro paragraph for the widget agent.

## Steps

1. Read the request.
2. Plan the change.
3. Apply the change.

## Completion Criteria

- Every test passes.

## Evidence Requirements

- Cite the command output.

## Failure Handling

- On a failed test, stop and report the failure.

## Approval Gates

- Ask the user before deleting any file.

## Authorization

- MUST NOT write outside the repository.

## Idempotence and Rollback

- Re-running is safe. Roll back with git restore.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | success |
| 1 | logic error |
"""

SHARED = (
    "---\n"
    "role: executor\n"
    "description: Applies widget changes.\n"
    "argument-hint: Describe the widget change\n"
    "tools_vscode: [read, search]\ntools_copilot: [read, search]\n"
    "---\n" + SHARED_BODY
)

CLAUDE = (
    "---\n"
    "name: widget\n"
    "description: Applies widget changes.\n"
    "metadata:\n  role: executor\n"
    "argument-hint: Describe the widget change\n"
    "tools: Read, Grep\n"
    "---\n" + SHARED_BODY + "\n## Claude Code Tools\n\n- Read, Grep\n"
)

COPILOT = SHARED


def build_repo(
    root: Path,
    *,
    shared: str = SHARED,
    claude: str = CLAUDE,
    copilot: str = COPILOT,
    stem: str = "widget",
) -> Path:
    """Write a minimal repo with one agent's three sources."""
    agents = root / "templates" / "agents"
    (agents / "partials").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    if shared:
        (agents / f"{stem}.shared.md").write_text(shared, encoding="utf-8")
    if claude:
        (agents / f"{stem}.claude.md.tmpl").write_text(claude, encoding="utf-8")
    if copilot:
        (agents / f"{stem}.copilot.md.tmpl").write_text(copilot, encoding="utf-8")
    return root


def run_gate(root: Path, *extra: str) -> int:
    return gate.main(["--repo-root", str(root), *extra])


def mutate(text: str, old: str, new: str) -> str:
    assert old in text, f"fixture drifted: {old!r} not in text"
    return text.replace(old, new, 1)


class TestAgreement:
    def test_agreeing_sources_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_repo(tmp_path)
        assert run_gate(tmp_path) == gate.EXIT_OK
        assert "OK: agent sources agree" in capsys.readouterr().out

    def test_tree_specific_frontmatter_is_dropped(self, tmp_path: Path) -> None:
        claude = mutate(
            CLAUDE, "tools: Read, Grep", "tools: Grep, Read\nmodel: opus\nisolation_required: true"
        )
        build_repo(tmp_path, claude=claude)
        assert run_gate(tmp_path) == gate.EXIT_OK

    def test_claude_only_section_is_skipped(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        found, missing = gate.collect_divergence(tmp_path)
        assert found == {}
        assert missing == []

    def test_whitespace_blank_lines_and_mcp_spelling_are_normalized(self, tmp_path: Path) -> None:
        shared = mutate(
            SHARED, "- Cite the command output.", "- Cite `mcp__context7__resolve` output."
        )
        claude = mutate(
            CLAUDE, "- Cite the command output.", "\n- Cite `context7/resolve` output.   \n\n"
        )
        build_repo(
            tmp_path,
            shared=shared,
            claude=claude,
            copilot=shared,
        )
        assert run_gate(tmp_path) == gate.EXIT_OK

    def test_top_level_role_matches_metadata_role(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "metadata:\n  role: executor\n", "role: executor\n")
        build_repo(tmp_path, claude=claude)
        assert run_gate(tmp_path) == gate.EXIT_OK

    def test_partial_include_renders_before_comparison(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        partials = tmp_path / "templates" / "agents" / "partials"
        (partials / "widget-intro.mustache").write_text("# Widget Agent\n", encoding="utf-8")
        claude = mutate(CLAUDE, "# Widget Agent\n", "{{> widget-intro}}")
        (tmp_path / "templates" / "agents" / "widget.claude.md.tmpl").write_text(
            claude, encoding="utf-8"
        )
        assert run_gate(tmp_path) == gate.EXIT_OK


CONTRADICTIONS = {
    "order of steps (invariant 1)": (
        "1. Read the request.\n2. Plan the change.",
        "1. Plan the change.\n2. Read the request.",
    ),
    "completion criteria (invariant 2)": ("- Every test passes.", "- Most tests pass."),
    "evidence requirements (invariant 3)": (
        "- Cite the command output.",
        "- No citation is needed.",
    ),
    "failure handling (invariant 4)": (
        "stop and report the failure",
        "ignore the failure and continue",
    ),
    "approval gate (invariant 5)": (
        "Ask the user before deleting any file.",
        "Delete files without asking.",
    ),
    "authorization (invariant 6)": ("MUST NOT write outside", "MUST write outside"),
    "rollback (invariant 7)": ("Roll back with git restore.", "Never roll back."),
    "exit code (invariant 8)": ("| 1 | logic error |", "| 3 | logic error |"),
}


class TestContradictionInjection:
    @pytest.mark.parametrize("old,new", CONTRADICTIONS.values(), ids=CONTRADICTIONS.keys())
    def test_claude_member_contradiction_fails(self, tmp_path: Path, old: str, new: str) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, old, new))
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED

    @pytest.mark.parametrize("old,new", CONTRADICTIONS.values(), ids=CONTRADICTIONS.keys())
    def test_shared_member_contradiction_fails(self, tmp_path: Path, old: str, new: str) -> None:
        build_repo(tmp_path, shared=mutate(SHARED, old, new), copilot=mutate(COPILOT, old, new))
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED

    @pytest.mark.parametrize("old,new", CONTRADICTIONS.values(), ids=CONTRADICTIONS.keys())
    def test_copilot_member_contradiction_fails(self, tmp_path: Path, old: str, new: str) -> None:
        build_repo(tmp_path, copilot=mutate(COPILOT, old, new))
        found, _ = gate.collect_divergence(tmp_path)
        assert {pair for (_, pair, _) in found} == {gate.PAIR_COPILOT}
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED

    def test_report_names_agent_pair_and_unit(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, "| 1 | logic error |", "| 3 | logic error |"))
        run_gate(tmp_path)
        assert "DIVERGED: widget claude-shared section:Exit Codes" in capsys.readouterr().out

    def test_frontmatter_description_contradiction_fails(self, tmp_path: Path) -> None:
        claude = mutate(
            CLAUDE, "description: Applies widget changes.", "description: Deletes widgets."
        )
        build_repo(tmp_path, claude=claude)
        found, _ = gate.collect_divergence(tmp_path)
        assert ("widget", gate.PAIR_CLAUDE, "frontmatter:description") in found

    def test_missing_shared_frontmatter_key_fails_in_claude_pair(self, tmp_path: Path) -> None:
        claude = mutate(CLAUDE, "argument-hint: Describe the widget change\n", "")
        build_repo(tmp_path, claude=claude)
        found, _ = gate.collect_divergence(tmp_path)
        assert ("widget", gate.PAIR_CLAUDE, "frontmatter:argument-hint") in found

    def test_copilot_section_on_one_side_only_fails(self, tmp_path: Path) -> None:
        build_repo(tmp_path, copilot=COPILOT + "\n## Extra\n\nOnly here.\n")
        found, _ = gate.collect_divergence(tmp_path)
        assert ("widget", gate.PAIR_COPILOT, "section:Extra") in found

    def test_preamble_difference_fails(self, tmp_path: Path) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, "Intro paragraph", "Different intro"))
        found, _ = gate.collect_divergence(tmp_path)
        assert ("widget", gate.PAIR_CLAUDE, "preamble") in found


class TestBaseline:
    def contradiction_repo(self, root: Path) -> Path:
        claude = mutate(CLAUDE, "- Every test passes.", "- Most tests pass.")
        return build_repo(root, claude=claude)

    def test_write_baseline_then_gate_passes(self, tmp_path: Path) -> None:
        self.contradiction_repo(tmp_path)
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED
        assert run_gate(tmp_path, "--write-baseline") == gate.EXIT_OK
        assert run_gate(tmp_path) == gate.EXIT_OK

    def test_pinned_unit_edited_again_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.contradiction_repo(tmp_path)
        run_gate(tmp_path, "--write-baseline")
        claude_path = tmp_path / "templates" / "agents" / "widget.claude.md.tmpl"
        text = claude_path.read_text(encoding="utf-8")
        claude_path.write_text(mutate(text, "Most tests pass.", "No tests pass."), encoding="utf-8")
        capsys.readouterr()
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED
        assert (
            "PIN-CHANGED: widget claude-shared section:Completion Criteria"
            in capsys.readouterr().out
        )

    def test_pin_goes_stale_when_sources_agree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.contradiction_repo(tmp_path)
        run_gate(tmp_path, "--write-baseline")
        (tmp_path / "templates" / "agents" / "widget.claude.md.tmpl").write_text(
            CLAUDE, encoding="utf-8"
        )
        capsys.readouterr()
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED
        assert (
            "PIN-STALE: widget claude-shared section:Completion Criteria" in capsys.readouterr().out
        )

    def test_write_baseline_refuses_past_ceiling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self.contradiction_repo(tmp_path)
        monkeypatch.setattr(gate, "BASELINE_CEILING", 0)
        assert run_gate(tmp_path, "--write-baseline") == gate.EXIT_DIVERGED
        assert "exceed BASELINE_CEILING" in capsys.readouterr().err
        assert not (tmp_path / gate.BASELINE_RELATIVE_PATH).exists()

    def test_oversized_baseline_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self.contradiction_repo(tmp_path)
        run_gate(tmp_path, "--write-baseline")
        monkeypatch.setattr(gate, "BASELINE_CEILING", 0)
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED

    def test_baseline_file_has_sorted_entries_and_schema(self, tmp_path: Path) -> None:
        self.contradiction_repo(tmp_path)
        run_gate(tmp_path, "--write-baseline")
        data = json.loads((tmp_path / gate.BASELINE_RELATIVE_PATH).read_text(encoding="utf-8"))
        assert data["schema_version"] == gate.BASELINE_SCHEMA_VERSION
        assert [e["unit"] for e in data["entries"]] == ["section:Completion Criteria"]
        assert len(data["entries"][0]["digest"]) == 64

    @pytest.mark.parametrize(
        "content",
        [
            "not json",
            "[]",
            json.dumps({"schema_version": "9", "entries": []}),
            json.dumps({"schema_version": "1", "entries": {}}),
            json.dumps({"schema_version": "1", "entries": ["x"]}),
            json.dumps(
                {
                    "schema_version": "1",
                    "entries": [{"agent": "a", "pair": "claude-shared", "unit": "u"}],
                }
            ),
            json.dumps(
                {
                    "schema_version": "1",
                    "entries": [{"agent": "a", "pair": "nope", "unit": "u", "digest": "d"}],
                }
            ),
            json.dumps(
                {
                    "schema_version": "1",
                    "entries": [{"agent": "a", "pair": "claude-shared", "unit": "u", "digest": "d"}]
                    * 2,
                }
            ),
        ],
        ids=[
            "bad-json",
            "not-object",
            "bad-version",
            "entries-not-list",
            "entry-not-object",
            "missing-field",
            "unknown-pair",
            "duplicate",
        ],
    )
    def test_malformed_baseline_is_a_config_error(self, tmp_path: Path, content: str) -> None:
        build_repo(tmp_path)
        path = tmp_path / gate.BASELINE_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG

    def test_unreadable_baseline_is_a_config_error(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        path = tmp_path / gate.BASELINE_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe\x00")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG


class TestStructure:
    def test_stem_without_shared_source_is_reported(self, tmp_path: Path) -> None:
        build_repo(tmp_path, shared="")
        assert run_gate(tmp_path) == gate.EXIT_DIVERGED
        _, missing = gate.collect_divergence(tmp_path)
        assert [f.detail for f in missing] == ["no shared.md"]

    def test_stem_with_shared_but_no_template_pair_is_reported(self, tmp_path: Path) -> None:
        build_repo(tmp_path, claude="", copilot="")
        _, missing = gate.collect_divergence(tmp_path)
        assert [f.detail for f in missing] == ["no claude/copilot template pair"]

    def test_half_template_pair_is_reported(self, tmp_path: Path) -> None:
        build_repo(tmp_path, copilot="")
        _, missing = gate.collect_divergence(tmp_path)
        assert [f.kind for f in missing] == [gate.KIND_MISSING]

    def test_missing_agents_directory_is_a_config_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG
        assert "directory not found" in capsys.readouterr().err

    def test_unrenderable_template_is_a_config_error(self, tmp_path: Path) -> None:
        build_repo(tmp_path, claude=CLAUDE + "\n{{> missing-partial}}")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG

    def test_invalid_frontmatter_yaml_is_a_config_error(self, tmp_path: Path) -> None:
        build_repo(tmp_path, shared="---\nkey: [unclosed\n---\n# Body\n")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG

    def test_unreadable_shared_source_is_a_config_error(self, tmp_path: Path) -> None:
        build_repo(tmp_path)
        (tmp_path / "templates" / "agents" / "widget.shared.md").write_bytes(b"\xff\xfe\x00")
        assert run_gate(tmp_path) == gate.EXIT_CONFIG

    def test_source_without_frontmatter_has_no_frontmatter_units(self) -> None:
        units = gate.extract_units("# Title\n\n## Steps\n\nDo it.\n")
        assert set(units) == {"preamble", "section:Steps"}

    def test_non_mapping_frontmatter_is_ignored(self) -> None:
        units = gate.extract_units("---\n- a\n- b\n---\n## Steps\n\nDo it.\n")
        assert set(units) == {"section:Steps"}

    def test_role_with_non_mapping_metadata_is_absent(self) -> None:
        units = gate.extract_units("---\nmetadata: text\n---\n## Steps\n\nDo it.\n")
        assert "frontmatter:role" not in units

    def test_find_repo_root_walks_up(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert gate._find_repo_root(nested) == tmp_path.resolve()

    def test_find_repo_root_failure_is_a_config_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            gate,
            "_find_repo_root",
            lambda _start: (_ for _ in ()).throw(gate.ConfigError("no root")),
        )
        assert gate.main([]) == gate.EXIT_CONFIG
        assert "no root" in capsys.readouterr().err

    def test_find_repo_root_raises_when_no_pyproject(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "exists", lambda self: False)
        with pytest.raises(gate.ConfigError):
            gate._find_repo_root(tmp_path)


class TestEntryPoint:
    def test_script_runs_as_main_and_adds_its_directory_to_the_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import runpy

        build_repo(tmp_path)
        monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p).resolve() != _SCRIPTS])
        monkeypatch.setattr(
            sys, "argv", ["check_agent_source_parity.py", "--repo-root", str(tmp_path)]
        )
        with pytest.raises(SystemExit) as raised:
            runpy.run_path(str(_SCRIPTS / "check_agent_source_parity.py"), run_name="__main__")
        assert raised.value.code == gate.EXIT_OK


class TestOutput:
    def test_json_format(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        build_repo(tmp_path, claude=mutate(CLAUDE, "- Every test passes.", "- Most tests pass."))
        assert run_gate(tmp_path, "--format", "json") == gate.EXIT_DIVERGED
        report = json.loads(capsys.readouterr().out)
        assert report["agents_examined"] == 1
        assert report["findings"][0]["kind"] == gate.KIND_DIVERGED
        assert report["findings"][0]["unit"] == "section:Completion Criteria"

    def test_text_report_is_bounded(self, capsys: pytest.CaptureFixture[str]) -> None:
        findings = [
            gate.Finding(gate.KIND_DIVERGED, f"a{i}", "claude-shared", "u") for i in range(130)
        ]
        gate.print_text(findings, examined=130, pinned=0)
        lines = capsys.readouterr().out.splitlines()
        assert "  ... and 30 more" in lines
        assert len(lines) < 110


class TestLiveRepository:
    """The committed sources and baseline must satisfy the gate."""

    def test_repository_passes(self) -> None:
        assert gate.main(["--repo-root", str(_REPO_ROOT)]) == gate.EXIT_OK

    def test_baseline_is_within_ceiling(self) -> None:
        pinned = gate.load_baseline(_REPO_ROOT)
        assert 0 < len(pinned) <= gate.BASELINE_CEILING

    def test_contradiction_in_live_template_fails(self, tmp_path: Path) -> None:
        """Copy the real sources, add a contradicting line to one partial, expect failure."""
        import shutil

        shutil.copytree(_REPO_ROOT / "templates" / "agents", tmp_path / "templates" / "agents")
        shutil.copy(_REPO_ROOT / "templates" / "toolsets.yaml", tmp_path / "templates")
        shutil.copy(_REPO_ROOT / "templates" / "agent-mcp-servers.yaml", tmp_path / "templates")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        gov = tmp_path / gate.BASELINE_RELATIVE_PATH
        gov.parent.mkdir(parents=True)
        shutil.copy(_REPO_ROOT / gate.BASELINE_RELATIVE_PATH, gov)
        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_OK
        partial = tmp_path / "templates" / "agents" / "partials" / "explainer-intro.mustache"
        partial.write_text(
            partial.read_text(encoding="utf-8") + "Never verify anything.\n", encoding="utf-8"
        )
        assert gate.main(["--repo-root", str(tmp_path)]) == gate.EXIT_DIVERGED
