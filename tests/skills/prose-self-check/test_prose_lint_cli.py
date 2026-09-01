"""Tests for the prose-self-check command-line contract.

Covers what the CLI promises its caller: the documented exit codes
(claude-agents MUST-7), rule discovery including the vendored-install leg,
the coverage a run reports alongside its findings, and the output formats.
The detectors themselves are covered in test_prose_lint.py.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/prose-self-check/scripts/prose_lint.py")
lint_prose = mod.lint_prose
parse_banned_words = mod.parse_banned_words
discover_rules_file = mod.discover_rules_file
main = mod.main
scan_prose = mod.scan_prose
HIGH = mod.HIGH
INFO = mod.INFO

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VOICE_RULE = PROJECT_ROOT / ".claude" / "rules" / "voice.md"

BANNED = {"delve", "robust", "comprehensive", "nuanced", "significant", "landscape"}


def kinds(text: str, banned: set[str] | None = None) -> list[str]:
    return [f.kind for f in lint_prose(text, BANNED if banned is None else banned)]


class TestCoverageReporting:
    """A run that read almost nothing must not look like a clean one."""

    def test_unterminated_fence_is_a_high_finding(self) -> None:
        findings = lint_prose("Intro.\n\n```bash\necho hi\n\nA robust design.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("unterminated_fence", HIGH)]

    def test_unterminated_fence_fails_the_run(self, tmp_path: Path) -> None:
        target = tmp_path / "d.md"
        target.write_text("Intro.\n\n```bash\necho hi\n\nA robust design.\n", encoding="utf-8")
        assert main([str(target), "--rules", str(VOICE_RULE)]) == 1

    def test_closed_fence_produces_no_unterminated_finding(self) -> None:
        assert kinds("```py\nx\n```\nprose.\n") == []

    def test_scan_reports_examined_and_total_lines(self) -> None:
        scan = scan_prose("Intro.\n\n```py\nx\n```\n\nOutro.\n", BANNED)
        assert scan.total == 7
        assert scan.examined == 2
        assert scan.unterminated_fence_line is None

    def test_clean_output_names_the_examined_count(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "d.md"
        target.write_text("The loader drops the message.\n", encoding="utf-8")
        main([str(target), "--rules", str(VOICE_RULE)])
        assert "0 findings in 1 prose line(s) of 1" in capsys.readouterr().out


class TestRulesDiscovery:
    """Vendor portability: the rule is found through the plugin root too."""

    def test_finds_the_rule_from_the_repo_cwd(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.chdir(PROJECT_ROOT)
        assert discover_rules_file() == PROJECT_ROOT / ".claude/rules/voice.md"

    def test_claude_plugin_root_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rule = tmp_path / "rules" / "voice.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("## Banned Vocabulary\n\n`zzz`.\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert discover_rules_file() == rule

    def test_vendored_install_resolves_by_plugin_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The leg that only fires in a consumer install: no env vars, cwd
        # outside the repo, discovery walks up to .claude-plugin/plugin.json.
        plugin = tmp_path / "plugin"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        (plugin / "rules").mkdir()
        rule = plugin / "rules" / "voice.md"
        rule.write_text("## Banned Vocabulary\n\n`zzz`.\n", encoding="utf-8")
        scripts = plugin / "skills" / "prose-self-check" / "scripts"
        scripts.mkdir(parents=True)
        copied = scripts / "prose_lint.py"
        copied.write_text(Path(mod.__file__).read_text(encoding="utf-8"), encoding="utf-8")

        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        elsewhere = tmp_path / "consumer"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        spec = importlib.util.spec_from_file_location("vendored_prose_lint", copied)
        assert spec is not None and spec.loader is not None
        vendored = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = vendored
        try:
            spec.loader.exec_module(vendored)
        finally:
            sys.modules.pop(spec.name, None)
        assert vendored.discover_rules_file() == rule

    def test_plugin_root_without_the_rule_falls_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        mirror = tmp_path / "copilot" / "instructions"
        mirror.mkdir(parents=True)
        rule = mirror / "voice.instructions.md"
        rule.write_text("## Banned Vocabulary\n\n`zzz`.\n", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(empty))
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path / "copilot"))
        assert discover_rules_file() == rule

    def test_install_root_fallback_resolves_both_layouts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        elsewhere = tmp_path / "consumer"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        root = tmp_path / "root"
        (root / "instructions").mkdir(parents=True)
        rule = root / "instructions" / "voice.instructions.md"
        rule.write_text("## Banned Vocabulary\n\n`zzz`.\n", encoding="utf-8")
        monkeypatch.setattr(mod, "_plugin_install_root", lambda: root)
        assert discover_rules_file() == rule

    def test_returns_none_when_nothing_is_reachable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "_plugin_install_root", lambda: None)
        assert discover_rules_file() is None

    def test_walk_up_finds_the_repo_plugin_root(self) -> None:
        # The real module sits under .claude/, whose marker is the repo's own
        # plugin manifest; this pins the walk-up itself, not a copy of it.
        assert mod._plugin_install_root() == PROJECT_ROOT / ".claude"

    def test_copilot_instructions_mirror_is_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rule = tmp_path / "instructions" / "voice.instructions.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("## Banned Vocabulary\n\n`zzz`.\n", encoding="utf-8")
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path))
        assert discover_rules_file() == rule


class TestExitCodes:
    """The contract SKILL.md documents: 0 clean or info, 1 high, 2 bad input."""

    def _write(self, tmp_path: Path, text: str) -> str:
        target = tmp_path / "draft.md"
        target.write_text(text, encoding="utf-8")
        return str(target)

    def test_exit_zero_when_clean(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "The loader drops the message at line 47.\n")
        assert main([path, "--rules", str(VOICE_RULE)]) == 0

    def test_exit_zero_when_only_info_findings(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "A comprehensive plan.\n")
        assert main([path, "--rules", str(VOICE_RULE)]) == 0

    def test_exit_one_on_high_severity(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "A robust plan.\n")
        assert main([path, "--rules", str(VOICE_RULE)]) == 1

    def test_exit_two_when_file_missing(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "nope.md"), "--rules", str(VOICE_RULE)]) == 2

    def test_exit_two_when_rules_file_missing(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, "text\n")
        assert main([path, "--rules", str(tmp_path / "nope.md")]) == 2

    def test_rules_file_without_the_section_degrades_and_warns(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rules = tmp_path / "voice.md"
        rules.write_text("# Voice\n\nNo list here.\n", encoding="utf-8")
        draft = tmp_path / "d.md"
        draft.write_text("A robust plan.\n", encoding="utf-8")
        assert main([str(draft), "--rules", str(rules)]) == 0
        captured = capsys.readouterr()
        assert "no 'Banned Vocabulary' section" in captured.err
        assert "banned_word" not in captured.out

    def test_rules_file_that_is_not_utf8_exits_two(self, tmp_path: Path) -> None:
        # UnicodeDecodeError is not an OSError, so it escaped the handler and
        # produced a traceback instead of the documented config-error exit.
        rules = tmp_path / "voice.md"
        rules.write_bytes(b"## Banned Vocabulary\n\n`\xff\xfe`.\n")
        draft = tmp_path / "d.md"
        draft.write_text("text\n", encoding="utf-8")
        assert main([str(draft), "--rules", str(rules)]) == 2

    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_no_files_exits_two(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2

    def test_missing_rules_degrades_to_structural_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("COPILOT_PLUGIN_ROOT", raising=False)
        monkeypatch.setattr(mod, "discover_rules_file", lambda: None)
        path = self._write(tmp_path, "A robust plan — really.\n")
        assert main([path]) == 1
        captured = capsys.readouterr()
        assert "no voice rule found" in captured.err
        assert "em_dash" in captured.out
        assert "banned_word" not in captured.out


class TestOutput:
    """Report formats the agent reads."""

    def test_clean_run_still_names_layer_four(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "d.md"
        target.write_text("The loader drops the message.\n", encoding="utf-8")
        main([str(target), "--rules", str(VOICE_RULE)])
        assert "Layer 4" in capsys.readouterr().out

    def test_json_mode_still_warns_when_the_rule_has_no_section(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The warning is the only signal the banned-word scan was disabled;
        # JSON mode used to drop it and report success in silence.
        rules = tmp_path / "voice.md"
        rules.write_text("# Voice\n\nNo list here.\n", encoding="utf-8")
        draft = tmp_path / "d.md"
        draft.write_text("A robust plan.\n", encoding="utf-8")
        assert main([str(draft), "--rules", str(rules), "--json"]) == 0
        captured = capsys.readouterr()
        assert "no 'Banned Vocabulary' section" in captured.err
        assert json.loads(captured.out)["banned_word_count"] == 0

    def test_json_payload_carries_severity_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = tmp_path / "d.md"
        target.write_text("A robust plan.\n", encoding="utf-8")
        main([str(target), "--rules", str(VOICE_RULE), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["high_severity_count"] == 1
        assert payload["banned_word_count"] == 19
        entry = payload["files"][str(target)]
        assert entry["findings"][0]["kind"] == "banned_word"
        assert entry["examined_lines"] == 1
        assert entry["source_lines"] == 1
        assert entry["unterminated_fence_line"] is None

    def test_stdin_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("A robust plan.\n"))
        assert main(["-", "--rules", str(VOICE_RULE)]) == 1
