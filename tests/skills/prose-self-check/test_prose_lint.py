#!/usr/bin/env python3
"""Tests for the prose-self-check Layer 1 and Layer 2 scanner.

Asserts the tiering SKILL.md documents (high fails, low-signal only informs),
the DRY contract (the word list is parsed from the voice rule, not embedded),
the code-skipping behavior, and the documented exit codes
(claude-agents MUST-7).
"""

from __future__ import annotations

import importlib.util
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


class TestParseBannedWords:
    """The list is read from the rule, never embedded in the script."""

    def test_reads_the_real_voice_rule(self) -> None:
        words = parse_banned_words(VOICE_RULE.read_text(encoding="utf-8"))
        assert {"delve", "robust", "tapestry", "significant"} <= words

    def test_stops_at_the_next_heading(self) -> None:
        text = "## Banned Vocabulary\n\n`delve`, `robust`.\n\n## Next\n\n`keepme`\n"
        assert parse_banned_words(text) == {"delve", "robust"}

    def test_ignores_multi_word_and_path_tokens(self) -> None:
        text = "## Banned Vocabulary\n\n`delve`, `some phrase`, `scripts/x.py`, `--flag`.\n"
        assert parse_banned_words(text) == {"delve"}

    def test_missing_section_yields_empty_set(self) -> None:
        assert parse_banned_words("# Voice\n\nNo list here.\n") == set()

    def test_script_does_not_embed_the_word_list(self) -> None:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "tapestry" not in source
        assert "multifaceted" not in source


class TestLexicalLayer:
    """Layer 1: dashes and banned vocabulary."""

    def test_em_dash_is_high_severity(self) -> None:
        findings = lint_prose("A sentence — with a dash.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("em_dash", HIGH)]

    def test_en_dash_is_high_severity(self) -> None:
        findings = lint_prose("Range 1 – 2.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("en_dash", HIGH)]

    def test_hyphen_is_not_a_dash_finding(self) -> None:
        assert kinds("A well-known trade-off.\n") == []

    def test_banned_word_is_high_severity(self) -> None:
        findings = lint_prose("A robust design.\n", BANNED)
        assert [(f.kind, f.severity) for f in findings] == [("banned_word", HIGH)]

    def test_low_signal_word_is_info_only(self) -> None:
        findings = lint_prose("A comprehensive and nuanced plan.\n", BANNED)
        assert {f.severity for f in findings} == {INFO}
        assert {f.kind for f in findings} == {"banned_word_low_signal"}

    def test_match_is_case_insensitive_but_reports_original(self) -> None:
        findings = lint_prose("Robust things.\n", BANNED)
        assert findings[0].match == "Robust"

    def test_substring_of_a_longer_word_is_not_matched(self) -> None:
        assert kinds("The delveson build is fine.\n") == []

    def test_position_is_one_indexed(self) -> None:
        findings = lint_prose("ab robust\n", BANNED)
        assert (findings[0].line, findings[0].column) == (1, 4)


class TestCodeIsSkipped:
    """Prose rules do not apply to code."""

    def test_fenced_block_is_skipped(self) -> None:
        assert kinds("```python\n# robust — code\n```\n") == []

    def test_inline_code_span_is_skipped(self) -> None:
        assert kinds("The `robust` flag is set.\n") == []

    def test_tilde_fence_is_skipped(self) -> None:
        assert kinds("~~~\nrobust\n~~~\n") == []

    def test_prose_after_a_closed_fence_is_checked(self) -> None:
        assert kinds("```\nrobust\n```\n\nA robust claim.\n") == ["banned_word"]

    def test_shorter_fence_does_not_close_a_longer_one(self) -> None:
        assert kinds("````\n```\nrobust\n```\n````\n") == []

    def test_inline_span_wrapped_across_a_line_break_is_skipped(self) -> None:
        # A document that documents these tells wraps its examples.
        text = "Openers: `Honestly,` / `In today's\nlandscape`. Delete them.\n"
        assert kinds(text) == []

    def test_fence_marker_backticks_do_not_pair_with_an_inline_span(self) -> None:
        text = "```\ncode\n```\n\nA robust claim.\n"
        assert kinds(text) == ["banned_word"]


class TestStructuralLayer:
    """Layer 2: the sentence shapes readers actually cite."""

    @pytest.mark.parametrize(
        "text",
        [
            "This is not a bug, it's a feature.\n",
            "It is not just slow, it is wrong.\n",
            "Refactoring isn't about speed, it's about risk.\n",
            "The fix is not cosmetic, but rather structural.\n",
        ],
    )
    def test_contrast_framing_is_flagged(self, text: str) -> None:
        assert "contrast_framing" in kinds(text)

    def test_plain_negation_is_not_contrast_framing(self) -> None:
        assert kinds("This is not a bug. The loader drops the message.\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "Want me to also add a dashboard?\n",
            "I could also wire up the gate.\n",
            "Let me know if you'd like a follow-up.\n",
            "Would you like me to open an issue?\n",
        ],
    )
    def test_trailing_offer_is_flagged(self, text: str) -> None:
        assert kinds(text) == ["trailing_offer"]

    @pytest.mark.parametrize(
        "text",
        [
            "Honestly, the queue drains.\n",
            "Look, the loader is wrong.\n",
            "It's worth noting that the gate is red.\n",
            "In today's landscape, retries matter.\n",
        ],
    )
    def test_signposting_opener_is_flagged(self, text: str) -> None:
        assert "signposting" in kinds(text)

    def test_signposting_mid_sentence_is_not_flagged(self) -> None:
        # Capitalized so the line-start anchor is the only thing that can
        # reject it; the lowercase form passes even with the anchor deleted.
        assert kinds("We should Look, then decide.\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "This is not a bug,\nit's a feature.\n",
            "Refactoring isn't about speed,\nit's about risk.\n",
        ],
    )
    def test_tell_that_straddles_a_hard_wrap_is_caught(self, text: str) -> None:
        assert "contrast_framing" in kinds(text)

    def test_match_does_not_cross_a_paragraph_break(self) -> None:
        assert kinds("A thing is not here,\n\nit's elsewhere.\n") == []

    @pytest.mark.parametrize(
        "text",
        [
            "The failure is not a flake, it's a real bug.\n",
            "The queue is not slow, it's unbounded.\n",
        ],
    )
    def test_noun_phrase_subject_is_caught(self, text: str) -> None:
        # Anchoring on it/this/that missed every sentence with a real subject.
        assert "contrast_framing" in kinds(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Claim is inaccurate (7 lines, not 5), but immaterial.\n",
            "| `v` | Not recognized | Keep it, but Claude ignores |\n",
        ],
    )
    def test_ordinary_not_but_is_not_contrast_framing(self, text: str) -> None:
        assert kinds(text) == []

    def test_but_rather_is_still_contrast_framing(self) -> None:
        assert kinds("It is not cosmetic, but rather structural.\n") == ["contrast_framing"]

    def test_model_identity_phrase_is_flagged(self) -> None:
        assert kinds("As an AI language model, I cannot.\n") == ["model_identity"]

    def test_signposting_on_a_later_line_reports_that_line(self) -> None:
        # The pattern consumes the preceding newline, so the reported offset
        # must be advanced past it or every hit lands one line early.
        findings = lint_prose("Intro line.\nHonestly, the queue drains.\n", BANNED)
        assert [(f.line, f.column, f.kind) for f in findings] == [(2, 1, "signposting")]

    def test_findings_are_sorted_by_position(self) -> None:
        text = "Honestly, a robust plan.\nThis is not a bug, it's a feature.\n"
        findings = lint_prose(text, BANNED)
        assert [(f.line, f.column) for f in findings] == sorted(
            (f.line, f.column) for f in findings
        )


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


class TestTokenizer:
    """A banned word keeps its identity through possessives and compounds."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("the landscape's shape", "landscape's"),
            ("a landscape-level view", "landscape-level"),
            ("a robust design", "robust"),
        ],
    )
    def test_banned_word_forms_are_matched(self, text: str, expected: str) -> None:
        assert [f.match for f in lint_prose(text, BANNED)] == [expected]

    @pytest.mark.parametrize(
        "text",
        [
            "see https://x.com/robust for more",
            "    </existing_landscape>",
            "the field is called robust_mode",
        ],
    )
    def test_non_prose_context_is_skipped(self, text: str) -> None:
        assert lint_prose(text, BANNED) == []

    def test_low_signal_compound_stays_info(self) -> None:
        assert [f.severity for f in lint_prose("a comprehensive-ish plan", BANNED)] == [INFO]


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
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("A robust plan.\n"))
        assert main(["-", "--rules", str(VOICE_RULE)]) == 1
