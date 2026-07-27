"""Tests for the trigger-phrase realism eval.

Offline only: no transcript store is read, no network. Every corpus is built in
the test, so the assertions do not depend on whatever happens to be in the
author's ~/.claude directory.

The interesting cases are the two exclusion rules. Both exist to stop the tool
reporting a number that looks good and means nothing, so each has an explicit
negative control asserting that the naive alternative would have been wrong.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))
import _trigger_realism as realism  # noqa: E402


def _load_cli():
    """Load the hyphenated CLI module by path."""
    path = _EVAL_DIR / "eval-trigger-phrase-realism.py"
    spec = importlib.util.spec_from_file_location("eval_trigger_phrase_realism", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load_cli()


class TestWordBoundaryMatch:
    """Anchoring is the rule that keeps a phrase from matching inside a word."""

    def test_a_phrase_present_as_whole_words_matches(self):
        assert realism.word_boundary_match("threat model", "run a threat model now")

    def test_matching_is_case_insensitive(self):
        assert realism.word_boundary_match("Threat Model", "a THREAT MODEL please")

    def test_a_phrase_absent_from_the_text_does_not_match(self):
        assert not realism.word_boundary_match("threat model", "run the tests")

    def test_a_phrase_inside_a_larger_word_does_not_match(self):
        # The documented failure: 'analyze' matching inside 'genuine'-style words
        # was the entire source of a practitioner's wrong hard blocks.
        assert not realism.word_boundary_match("analyze", "the analyzer crashed")

    def test_a_phrase_suffixed_by_letters_does_not_match(self):
        assert not realism.word_boundary_match("review", "reviewer feedback")

    def test_a_phrase_prefixed_by_letters_does_not_match(self):
        assert not realism.word_boundary_match("spec", "respec the build")

    def test_adjacent_punctuation_still_matches(self):
        assert realism.word_boundary_match("ship it", "ok, ship it!")

    def test_a_phrase_containing_regex_metacharacters_is_matched_literally(self):
        assert realism.word_boundary_match("a.b", "run a.b here")
        assert not realism.word_boundary_match("a.b", "run axb here")

    def test_an_empty_phrase_never_matches(self):
        assert not realism.word_boundary_match("", "anything at all")

    def test_a_whitespace_only_phrase_never_matches(self):
        assert not realism.word_boundary_match("   ", "anything at all")


class TestIsMeasurablePhrase:
    """Two shapes are excluded because a hit on them proves nothing."""

    def test_a_multiword_phrase_is_measurable(self):
        assert realism.is_measurable_phrase("start new session")

    def test_a_slash_command_is_not_measurable(self):
        # Dispatched by name; it never consults a description, so counting it
        # measures the dispatcher rather than the phrase.
        assert not realism.is_measurable_phrase("/session-init")

    def test_a_single_word_is_not_measurable(self):
        assert not realism.is_measurable_phrase("analyze")

    def test_an_empty_phrase_is_not_measurable(self):
        assert not realism.is_measurable_phrase("")

    def test_a_whitespace_only_phrase_is_not_measurable(self):
        assert not realism.is_measurable_phrase("   ")

    def test_surrounding_whitespace_does_not_change_the_verdict(self):
        assert realism.is_measurable_phrase("  start new session  ")


class TestCountOccurrences:
    def test_counts_entries_not_total_matches(self):
        corpus = ["threat model twice: threat model", "threat model", "unrelated"]
        assert realism.count_occurrences("threat model", corpus) == 2

    def test_returns_zero_for_an_absent_phrase(self):
        assert realism.count_occurrences("threat model", ["unrelated"]) == 0

    def test_returns_zero_against_an_empty_corpus(self):
        assert realism.count_occurrences("threat model", []) == 0


class TestScore:
    def test_observed_and_measurable_are_counted_separately(self):
        report = realism.score(
            {"a": ["start new session", "never uttered phrase"]},
            ["please start new session"],
        )
        assert report.measurable == 2
        assert report.observed == 1
        assert report.realism == pytest.approx(0.5)

    def test_excluded_phrases_stay_out_of_the_denominator(self):
        report = realism.score({"a": ["/slash", "one", "start new session"]}, ["x"])
        assert report.measurable == 1
        assert report.excluded == 2

    def test_realism_is_zero_when_nothing_is_measurable(self):
        report = realism.score({"a": ["/slash"]}, ["anything"])
        assert report.measurable == 0
        assert report.realism == 0.0

    def test_realism_is_zero_against_an_empty_corpus(self):
        report = realism.score({"a": ["start new session"]}, [])
        assert report.observed == 0
        assert report.realism == 0.0

    def test_hits_are_keyed_by_skill_and_phrase(self):
        report = realism.score({"skill-a": ["start new session"]}, ["start new session"])
        assert report.hits == {("skill-a", "start new session"): 1}

    def test_the_same_phrase_in_two_skills_is_counted_for_each(self):
        report = realism.score(
            {"a": ["start new session"], "b": ["start new session"]},
            ["start new session"],
        )
        assert report.measurable == 2
        assert report.observed == 2


class TestUserTextExtraction:
    """Only what the user typed counts. Tool results share the user role."""

    def _line(self, payload):
        return json.dumps(payload)

    def test_a_plain_string_user_message_is_returned(self):
        line = self._line({"type": "user", "message": {"content": "  fix the bug  "}})
        assert cli._user_text(line) == "fix the bug"

    def test_text_blocks_are_joined(self):
        line = self._line(
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "text", "text": "fix"},
                        {"type": "text", "text": "the bug"},
                    ]
                },
            }
        )
        assert cli._user_text(line) == "fix the bug"

    def test_a_tool_result_block_is_excluded(self):
        line = self._line(
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "output"}]},
            }
        )
        assert cli._user_text(line) is None

    def test_an_assistant_entry_is_excluded(self):
        line = self._line({"type": "assistant", "message": {"content": "hello"}})
        assert cli._user_text(line) is None

    def test_a_harness_injected_xml_entry_is_excluded(self):
        line = self._line(
            {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}}
        )
        assert cli._user_text(line) is None

    def test_an_interrupted_request_marker_is_excluded(self):
        line = self._line(
            {"type": "user", "message": {"content": "[Request interrupted by user]"}}
        )
        assert cli._user_text(line) is None

    def test_a_local_command_entry_is_excluded(self):
        line = self._line(
            {"type": "user", "message": {"content": "ran <local-command-stdout>"}}
        )
        assert cli._user_text(line) is None

    def test_an_empty_message_is_excluded(self):
        line = self._line({"type": "user", "message": {"content": "   "}})
        assert cli._user_text(line) is None

    def test_malformed_json_is_excluded(self):
        assert cli._user_text("{not json") is None

    def test_a_non_dict_json_line_is_excluded(self):
        assert cli._user_text("[1, 2, 3]") is None

    def test_a_missing_message_key_is_excluded(self):
        assert cli._user_text(self._line({"type": "user"})) is None


class TestLoadTranscriptPrompts:
    def test_reads_and_deduplicates_across_transcripts(self, tmp_path):
        project = tmp_path / "repo-ai-agents"
        project.mkdir()
        entry = json.dumps({"type": "user", "message": {"content": "fix the bug"}})
        (project / "a.jsonl").write_text(entry + "\n")
        (project / "b.jsonl").write_text(entry + "\n")
        assert cli.load_transcript_prompts(tmp_path, "ai-agents") == ["fix the bug"]

    def test_a_project_outside_the_filter_is_skipped(self, tmp_path):
        other = tmp_path / "repo-something-else"
        other.mkdir()
        (other / "a.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "fix the bug"}}) + "\n"
        )
        assert cli.load_transcript_prompts(tmp_path, "ai-agents") == []

    def test_an_empty_store_yields_nothing(self, tmp_path):
        assert cli.load_transcript_prompts(tmp_path, "ai-agents") == []

    def test_a_line_that_is_not_a_user_prompt_is_skipped(self, tmp_path):
        project = tmp_path / "repo-ai-agents"
        project.mkdir()
        (project / "a.jsonl").write_text(
            json.dumps({"type": "assistant", "message": {"content": "hi"}})
            + "\n"
            + json.dumps({"type": "user", "message": {"content": "fix the bug"}})
            + "\n"
        )
        assert cli.load_transcript_prompts(tmp_path, "ai-agents") == ["fix the bug"]

    def test_an_unreadable_transcript_is_skipped(self, tmp_path, monkeypatch):
        project = tmp_path / "repo-ai-agents"
        project.mkdir()
        (project / "a.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "fix the bug"}}) + "\n"
        )

        def _boom(*args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", _boom)
        assert cli.load_transcript_prompts(tmp_path, "ai-agents") == []


class TestCollectPhrases:
    def _skill(self, root, name, description, triggers=None):
        d = root / name
        d.mkdir(parents=True)
        # Single-quoted YAML scalar: descriptions carry double quotes by design.
        escaped = description.replace("'", "''")
        body = f"---\nname: {name}\ndescription: '{escaped}'\n---\n\n# {name}\n"
        if triggers:
            rows = "\n".join(f"| `{t}` | does a thing |" for t in triggers)
            body += f"\n## Triggers\n\n| Phrase | Effect |\n|---|---|\n{rows}\n\n## Next\n"
        (d / "SKILL.md").write_text(body)

    def test_table_phrases_and_promoted_phrases_are_separated(self, tmp_path):
        self._skill(
            tmp_path, "alpha", '"say this" to run it', ["say this", "or this"]
        )
        documented, promoted = cli.collect_phrases(tmp_path)
        assert documented == {"alpha": ["say this", "or this"]}
        assert promoted == {"alpha": ["say this"]}

    def test_a_skill_with_no_trigger_table_is_absent_from_documented(self, tmp_path):
        self._skill(tmp_path, "alpha", "no quoted phrases here")
        documented, promoted = cli.collect_phrases(tmp_path)
        assert documented == {}
        assert promoted == {}

    def test_malformed_frontmatter_is_skipped(self, tmp_path):
        d = tmp_path / "broken"
        d.mkdir()
        (d / "SKILL.md").write_text("---\n: : bad yaml : :\n---\nbody\n")
        assert cli.collect_phrases(tmp_path) == ({}, {})

    def test_a_file_without_frontmatter_is_skipped(self, tmp_path):
        d = tmp_path / "plain"
        d.mkdir()
        (d / "SKILL.md").write_text("# just a heading\n")
        assert cli.collect_phrases(tmp_path) == ({}, {})

    def test_a_trigger_table_with_no_backticked_phrases_is_ignored(self, tmp_path):
        d = tmp_path / "alpha"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: plain text\n---\n\n"
            "## Triggers\n\nProse, no table.\n\n## Next\n"
        )
        documented, _ = cli.collect_phrases(tmp_path)
        assert documented == {}

    def test_a_non_string_description_is_skipped(self, tmp_path):
        d = tmp_path / "listy"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: listy\ndescription:\n  - a\n---\nbody\n")
        assert cli.collect_phrases(tmp_path) == ({}, {})


class TestCliExitCodes:
    def _store(self, tmp_path, content="start new session"):
        store = tmp_path / "projects"
        project = store / "x-ai-agents"
        project.mkdir(parents=True)
        (project / "a.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": content}}) + "\n"
        )
        return store

    def _skills(self, tmp_path):
        skills = tmp_path / "skills" / "alpha"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            '---\nname: alpha\ndescription: does "start new session" work\n---\n\n'
            "## Triggers\n\n| Phrase | Effect |\n|---|---|\n"
            "| `start new session` | runs |\n\n## Next\n"
        )
        return skills.parent

    def test_a_missing_skills_directory_is_a_config_error(self, tmp_path):
        code = cli.main(
            [
                "--skills-dir",
                str(tmp_path / "nope"),
                "--transcript-store",
                str(self._store(tmp_path)),
            ]
        )
        assert code == cli.EXIT_CONFIG

    def test_a_missing_transcript_store_is_an_external_error(self, tmp_path):
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--transcript-store",
                str(tmp_path / "nope"),
            ]
        )
        assert code == cli.EXIT_EXTERNAL

    def test_a_store_with_no_matching_prompts_is_an_external_error(self, tmp_path):
        store = tmp_path / "projects"
        store.mkdir()
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--transcript-store",
                str(store),
            ]
        )
        assert code == cli.EXIT_EXTERNAL

    def test_a_successful_run_exits_zero_and_writes_the_report(self, tmp_path, capsys):
        out = tmp_path / "report.json"
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--transcript-store",
                str(self._store(tmp_path)),
                "--output",
                str(out),
            ]
        )
        assert code == cli.EXIT_OK
        report = json.loads(out.read_text())
        assert report["corpus_prompts"] == 1
        assert report["documented"]["observed_phrases"] == 1
        assert report["documented"]["realism"] == 1.0
        assert "start new session" in capsys.readouterr().out

    def test_a_run_without_an_output_path_still_exits_zero(self, tmp_path, capsys):
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--transcript-store",
                str(self._store(tmp_path)),
            ]
        )
        assert code == cli.EXIT_OK
        out = capsys.readouterr().out
        assert "start new session" in out
        assert "Wrote" not in out

    def test_a_phrase_nobody_said_scores_zero(self, tmp_path):
        out = tmp_path / "report.json"
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--transcript-store",
                str(self._store(tmp_path, content="something entirely different")),
                "--output",
                str(out),
            ]
        )
        assert code == cli.EXIT_OK
        report = json.loads(out.read_text())
        assert report["documented"]["observed_phrases"] == 0
        assert report["documented"]["realism"] == 0.0


class TestRender:
    def test_renders_without_observed_phrases(self):
        report = {
            "corpus_prompts": 3,
            "documented": {"measurable_phrases": 2, "observed_phrases": 0, "realism": 0.0},
            "promoted": {"measurable_phrases": 1, "observed_phrases": 0, "realism": 0.0},
            "observed_phrases": [],
        }
        text = cli.render(report)
        assert "3 unique real prompts" in text
        assert "0 of 2 phrases" in text
        assert "actually said" not in text
