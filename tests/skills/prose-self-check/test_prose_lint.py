#!/usr/bin/env python3
"""Tests for the prose-self-check Layer 1 and Layer 2 scanner.

Asserts the tiering SKILL.md documents (high fails, low-signal only informs),
the DRY contract (the word list is parsed from the voice rule, not embedded),
the code-skipping behavior, and the documented exit codes
(claude-agents MUST-7).
"""

from __future__ import annotations

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
HIGH = mod.HIGH
INFO = mod.INFO

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VOICE_RULE = PROJECT_ROOT / ".claude" / "rules" / "voice.md"

BANNED = {"delve", "robust", "comprehensive", "nuanced", "significant"}


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
        assert kinds("We should look, then decide.\n") == []

    def test_model_identity_phrase_is_flagged(self) -> None:
        assert kinds("As an AI language model, I cannot.\n") == ["model_identity"]

    def test_findings_are_sorted_by_position(self) -> None:
        text = "Honestly, a robust plan.\nThis is not a bug, it's a feature.\n"
        findings = lint_prose(text, BANNED)
        assert [(f.line, f.column) for f in findings] == sorted(
            (f.line, f.column) for f in findings
        )


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
        assert payload["files"][str(target)][0]["kind"] == "banned_word"

    def test_stdin_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO("A robust plan.\n"))
        assert main(["-", "--rules", str(VOICE_RULE)]) == 1
