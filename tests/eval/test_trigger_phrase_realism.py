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
import sqlite3
import sys
from pathlib import Path
from typing import Any

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


def _operator_text(line: str) -> str | None:
    """Return the operator-typed text of a transcript line, or None.

    ``_split_user_text`` returns the text plus a provenance flag, because the
    machine-authored half is this eval's negative control rather than waste.
    These tests assert on the operator half, so they read through this shim.
    """
    split = cli._split_user_text(line)
    if split is None:
        return None
    text, is_operator = split
    return text if is_operator else None


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

    def test_a_multiword_slash_command_is_not_measurable(self):
        # A single-word slash command is also rejected by the single-word rule,
        # so it cannot prove the slash rule exists. This multiword form is
        # rejected only by the slash rule, so deleting that rule fails here.
        assert not realism.is_measurable_phrase("/review BRANCH_OR_PR")

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
        report = realism.score(
            {"a": ["/review BRANCH_OR_PR", "one", "start new session"]}, ["x"]
        )
        assert report.measurable == 1
        assert report.excluded == 2

    def test_realism_is_zero_when_nothing_is_measurable(self):
        report = realism.score({"a": ["/review BRANCH_OR_PR"]}, ["anything"])
        assert report.measurable == 0
        assert report.realism == 0.0

    def test_realism_is_zero_against_an_empty_corpus(self):
        report = realism.score({"a": ["start new session"]}, [])
        assert report.observed == 0
        assert report.realism == 0.0

    def test_hits_cannot_be_mutated_after_scoring(self):
        # frozen=True does not protect a mutable field. Without a read-only
        # mapping, hits could be edited to disagree with observed and realism.
        report = realism.score({"a": ["start new session"]}, ["start new session"])
        hits: Any = report.hits
        with pytest.raises(TypeError):
            hits[("b", "injected")] = 1
        assert report.observed == 1

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
        assert _operator_text(line) == "fix the bug"

    def test_a_sidechain_entry_is_excluded(self):
        # Sidechain entries are prompts an agent wrote for a subagent. They
        # carry the user role but nobody typed them, so admitting them would
        # score the phrases against machine-authored text.
        line = self._line(
            {
                "type": "user",
                "isSidechain": True,
                "message": {"content": "fix the bug"},
            }
        )
        assert _operator_text(line) is None

    def test_an_agent_authored_entry_is_excluded(self):
        line = self._line(
            {
                "type": "user",
                "agentId": "explore-1",
                "message": {"content": "fix the bug"},
            }
        )
        assert _operator_text(line) is None

    def test_an_explicit_non_sidechain_entry_is_kept(self):
        # Negative control for the two exclusions above: a falsey flag must
        # not remove a genuine operator prompt.
        line = self._line(
            {
                "type": "user",
                "isSidechain": False,
                "agentId": None,
                "message": {"content": "fix the bug"},
            }
        )
        assert _operator_text(line) == "fix the bug"

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
        assert _operator_text(line) == "fix the bug"

    def test_a_tool_result_block_is_excluded(self):
        line = self._line(
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "output"}]},
            }
        )
        assert _operator_text(line) is None

    def test_an_assistant_entry_is_excluded(self):
        line = self._line({"type": "assistant", "message": {"content": "hello"}})
        assert _operator_text(line) is None

    def test_a_harness_injected_xml_entry_is_excluded(self):
        line = self._line(
            {"type": "user", "message": {"content": "<system-reminder>x</system-reminder>"}}
        )
        assert _operator_text(line) is None

    def test_an_interrupted_request_marker_is_excluded(self):
        line = self._line(
            {"type": "user", "message": {"content": "[Request interrupted by user]"}}
        )
        assert _operator_text(line) is None

    def test_a_local_command_entry_is_excluded(self):
        line = self._line(
            {"type": "user", "message": {"content": "ran <local-command-stdout>"}}
        )
        assert _operator_text(line) is None

    def test_an_empty_message_is_excluded(self):
        line = self._line({"type": "user", "message": {"content": "   "}})
        assert _operator_text(line) is None

    def test_malformed_json_is_excluded(self):
        assert _operator_text("{not json") is None

    def test_a_non_dict_json_line_is_excluded(self):
        assert _operator_text("[1, 2, 3]") is None

    def test_a_missing_message_key_is_excluded(self):
        assert _operator_text(self._line({"type": "user"})) is None


class TestLoadTranscriptPrompts:
    def test_reads_and_deduplicates_across_transcripts(self, tmp_path):
        project = tmp_path / "repo-ai-agents"
        project.mkdir()
        entry = json.dumps({"type": "user", "message": {"content": "fix the bug"}})
        (project / "a.jsonl").write_text(entry + "\n")
        (project / "b.jsonl").write_text(entry + "\n")
        assert cli.load_transcript_prompts(tmp_path, "ai-agents")[0] == ["fix the bug"]

    def test_a_project_outside_the_filter_is_skipped(self, tmp_path):
        other = tmp_path / "repo-something-else"
        other.mkdir()
        (other / "a.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "fix the bug"}}) + "\n"
        )
        assert cli.load_transcript_prompts(tmp_path, "ai-agents")[0] == []

    def test_an_empty_store_yields_nothing(self, tmp_path):
        assert cli.load_transcript_prompts(tmp_path, "ai-agents")[0] == []

    def test_a_line_that_is_not_a_user_prompt_is_skipped(self, tmp_path):
        project = tmp_path / "repo-ai-agents"
        project.mkdir()
        (project / "a.jsonl").write_text(
            json.dumps({"type": "assistant", "message": {"content": "hi"}})
            + "\n"
            + json.dumps({"type": "user", "message": {"content": "fix the bug"}})
            + "\n"
        )
        assert cli.load_transcript_prompts(tmp_path, "ai-agents")[0] == ["fix the bug"]

    def test_an_unreadable_transcript_is_skipped(self, tmp_path, monkeypatch):
        project = tmp_path / "repo-ai-agents"
        project.mkdir()
        (project / "a.jsonl").write_text(
            json.dumps({"type": "user", "message": {"content": "fix the bug"}}) + "\n"
        )

        def _boom(*args, **kwargs):
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "read_text", _boom)
        assert cli.load_transcript_prompts(tmp_path, "ai-agents")[0] == []


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
        # Phrases are de-duplicated, so the order is sorted rather than source.
        assert documented == {"alpha": ["or this", "say this"]}
        assert promoted == {"alpha": ["say this"]}

    def test_a_trigger_list_is_read_as_well_as_a_table(self, tmp_path):
        # The standard permits "table or list"; a table-only reader would
        # silently drop every list-format phrase and halve the denominator.
        d = tmp_path / "alpha"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\ndescription: 'x'\n---\n\n"
            "## Triggers\n\n- `from a list` runs it\n1. `numbered too` runs it\n"
        )
        documented, _ = cli.collect_phrases(tmp_path)
        assert documented == {"alpha": ["from a list", "numbered too"]}

    def test_a_backticked_description_phrase_is_promoted(self, tmp_path):
        d = tmp_path / "alpha"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\ndescription: 'run `do the thing` now'\n---\n\n"
            "## Triggers\n\n| `do the thing` |\n"
        )
        _, promoted = cli.collect_phrases(tmp_path)
        assert promoted == {"alpha": ["do the thing"]}

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
    """Every case here pins --session-store at a path that does not exist.

    Without that the CLI falls back to the developer's real Copilot store, so
    the suite would read private prompt text and its results would vary by
    machine. The absent path exercises the same code path the guard protects.
    """

    def _store(self, tmp_path, content="start new session", filler=0):
        store = tmp_path / "projects"
        project = store / "x-ai-agents"
        project.mkdir(parents=True)
        lines = [json.dumps({"type": "user", "message": {"content": content}})]
        lines += [
            json.dumps({"type": "user", "message": {"content": f"unrelated prompt {i}"}})
            for i in range(filler)
        ]
        (project / "a.jsonl").write_text("\n".join(lines) + "\n")
        return store

    def _absent_session_store(self, tmp_path):
        return str(tmp_path / "no-session-store.db")

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
                "--session-store",
                self._absent_session_store(tmp_path),
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
                "--session-store",
                self._absent_session_store(tmp_path),
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
                "--session-store",
                self._absent_session_store(tmp_path),
                "--transcript-store",
                str(store),
            ]
        )
        assert code == cli.EXIT_EXTERNAL

    def test_a_corpus_below_the_minimum_is_an_external_error(self, tmp_path):
        """One prompt cannot distinguish a real zero from a broken matcher."""
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                self._absent_session_store(tmp_path),
                "--transcript-store",
                str(self._store(tmp_path)),
            ]
        )
        assert code == cli.EXIT_EXTERNAL

    def test_a_successful_run_exits_zero_and_writes_the_report(self, tmp_path, capsys):
        out = tmp_path / "report.json"
        filler = realism.MINIMUM_CORPUS - 1
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                self._absent_session_store(tmp_path),
                "--transcript-store",
                str(self._store(tmp_path, filler=filler)),
                "--output",
                str(out),
            ]
        )
        assert code == cli.EXIT_OK
        report = json.loads(out.read_text())
        assert report["corpus_prompts"] == realism.MINIMUM_CORPUS
        assert report["documented"]["observed_phrases"] == 1
        assert report["documented"]["realism"] == 1.0
        assert "start new session" in capsys.readouterr().out

    def test_a_run_without_an_output_path_still_exits_zero(self, tmp_path, capsys):
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                self._absent_session_store(tmp_path),
                "--transcript-store",
                str(self._store(tmp_path, filler=realism.MINIMUM_CORPUS - 1)),
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
                "--session-store",
                self._absent_session_store(tmp_path),
                "--transcript-store",
                str(
                    self._store(
                        tmp_path,
                        content="something entirely different",
                        filler=realism.MINIMUM_CORPUS - 1,
                    )
                ),
                "--output",
                str(out),
            ]
        )
        assert code == cli.EXIT_OK
        report = json.loads(out.read_text())
        assert report["documented"]["observed_phrases"] == 0
        assert report["documented"]["realism"] == 0.0


class TestRender:
    def _report(self, **overrides):
        report = {
            "corpus_prompts": 3,
            "control_prompts": 5,
            "documented": {"measurable_phrases": 2, "observed_phrases": 0, "realism": 0.0},
            "promoted": {"measurable_phrases": 1, "observed_phrases": 0, "realism": 0.0},
            "control_documented": {
                "measurable_phrases": 2,
                "observed_phrases": 0,
                "realism": 0.0,
            },
            "observed_phrases": [],
        }
        report.update(overrides)
        return report

    def test_renders_without_observed_phrases(self):
        text = cli.render(self._report())
        assert "3 unique operator-typed prompts" in text
        assert "0 of 2 phrases" in text
        assert "actually said" not in text

    def test_renders_the_negative_control_block(self):
        """The control is what makes a low operator number interpretable."""
        text = cli.render(
            self._report(
                control_documented={
                    "measurable_phrases": 2,
                    "observed_phrases": 2,
                    "realism": 1.0,
                }
            )
        )
        assert "5 machine-authored prompts" in text
        assert "negative control" in text
        assert "2 of 2 phrases appear" in text


class TestSessionStorePrompts:
    """The Copilot store is where operator turns actually live.

    Its ``turns.user_message`` column is the human turn by construction, so
    provenance here is structural rather than inferred from heuristics.
    """

    def _db(self, tmp_path, rows, repository="rjmurillo/ai-agents"):
        path = tmp_path / "session-store.db"
        connection = sqlite3.connect(path)
        with connection:
            connection.execute("CREATE TABLE sessions (id TEXT, repository TEXT)")
            connection.execute("CREATE TABLE turns (session_id TEXT, user_message TEXT)")
            connection.execute("INSERT INTO sessions VALUES ('s1', ?)", (repository,))
            connection.executemany(
                "INSERT INTO turns VALUES ('s1', ?)", [(row,) for row in rows]
            )
        connection.close()
        return path

    def test_reads_operator_turns(self, tmp_path):
        db = self._db(tmp_path, ["fix the bug", "ship it"])
        assert cli.load_session_store_prompts(db, "ai-agents") == ["fix the bug", "ship it"]

    def test_deduplicates_and_strips(self, tmp_path):
        db = self._db(tmp_path, ["fix the bug", "  fix the bug  "])
        assert cli.load_session_store_prompts(db, "ai-agents") == ["fix the bug"]

    def test_a_session_in_another_repository_is_skipped(self, tmp_path):
        db = self._db(tmp_path, ["fix the bug"], repository="someone/other-project")
        assert cli.load_session_store_prompts(db, "ai-agents") == []

    def test_a_synthetic_turn_is_excluded(self, tmp_path):
        """Agent-injected turns open with an XML tag and are not operator text."""
        db = self._db(tmp_path, ["<command-name>/ship</command-name>", "fix the bug"])
        assert cli.load_session_store_prompts(db, "ai-agents") == ["fix the bug"]

    def test_a_null_message_is_excluded(self, tmp_path):
        db = self._db(tmp_path, [None, "fix the bug"])
        assert cli.load_session_store_prompts(db, "ai-agents") == ["fix the bug"]

    def test_the_store_is_opened_read_only(self, tmp_path):
        """A measurement must never mutate a live store."""
        db = self._db(tmp_path, ["fix the bug"])
        captured = {}
        real_connect = sqlite3.connect

        def spy(target, *args, **kwargs):
            captured["target"] = target
            return real_connect(target, *args, **kwargs)

        cli.sqlite3.connect = spy
        try:
            cli.load_session_store_prompts(db, "ai-agents")
        finally:
            cli.sqlite3.connect = real_connect
        assert captured["target"] == f"file:{db}?mode=ro"

    def test_a_corrupt_store_raises_for_the_caller_to_classify(self, tmp_path):
        path = tmp_path / "session-store.db"
        path.write_text("not a database")
        with pytest.raises(sqlite3.Error):
            cli.load_session_store_prompts(path, "ai-agents")


class TestNewRejectionShapes:
    """Every non-human marker routes text to the control, never to the corpus."""

    def _line(self, extra):
        entry = {"type": "user", "message": {"content": "fix the bug"}}
        entry.update(extra)
        return json.dumps(entry)

    @pytest.mark.parametrize("flag", sorted(realism.NON_HUMAN_ENTRY_FLAGS))
    def test_a_non_human_flag_routes_to_the_control(self, flag):
        text, is_operator = cli._split_user_text(self._line({flag: True}))
        assert text == "fix the bug"
        assert is_operator is False

    @pytest.mark.parametrize("source", sorted(realism.NON_HUMAN_PROMPT_SOURCES))
    def test_a_non_human_prompt_source_routes_to_the_control(self, source):
        text, is_operator = cli._split_user_text(self._line({"promptSource": source}))
        assert is_operator is False

    def test_an_explicitly_typed_prompt_is_operator_text(self):
        text, is_operator = cli._split_user_text(self._line({"promptSource": "typed"}))
        assert is_operator is True

    def test_an_unlabelled_prompt_is_operator_text(self):
        """Absence of promptSource is not evidence: it is present on 120 of 3331
        non-human entries and both sets span the same dates, so rejecting the
        unlabelled majority would discard the corpus."""
        text, is_operator = cli._split_user_text(self._line({}))
        assert is_operator is True

    def test_a_sourced_tool_use_routes_to_the_control(self):
        text, is_operator = cli._split_user_text(self._line({"sourceToolUseID": "t1"}))
        assert is_operator is False


class TestFrontmatterRobustness:
    def test_a_non_mapping_frontmatter_is_skipped(self, tmp_path):
        """A bare scalar or list parses as valid YAML but has no description."""
        d = tmp_path / "scalar"
        d.mkdir()
        (d / "SKILL.md").write_text("---\njust a string\n---\nbody\n")
        assert cli.collect_phrases(tmp_path) == ({}, {})

    def test_a_quoted_trigger_cell_is_collected(self, tmp_path):
        """The canonical example in the governance standard quotes its phrases,
        so a backtick-only cell pattern would silently miss the documented form."""
        d = tmp_path / "quoted"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: quoted\ndescription: x\n---\n\n"
            '## Triggers\n\n| Phrase | Effect |\n|---|---|\n| "run the audit" | goes |\n'
        )
        documented, _ = cli.collect_phrases(tmp_path)
        assert documented == {"quoted": ["run the audit"]}

    def test_backticked_and_quoted_cells_coexist(self, tmp_path):
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: mixed\ndescription: x\n---\n\n"
            "## Triggers\n\n| Phrase | Effect |\n|---|---|\n"
            '| `alpha phrase` | a |\n| "beta phrase" | b |\n'
        )
        documented, _ = cli.collect_phrases(tmp_path)
        assert documented == {"mixed": ["alpha phrase", "beta phrase"]}


class TestExternalErrorClassification:
    """ADR-035: an unreadable store or unwritable output is external, not logic."""

    def _skills(self, tmp_path):
        skills = tmp_path / "skills" / "alpha"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: x\n---\n\n"
            "## Triggers\n\n| Phrase | Effect |\n|---|---|\n| `start new session` | runs |\n"
        )
        return skills.parent

    def _store(self, tmp_path):
        store = tmp_path / "projects"
        project = store / "x-ai-agents"
        project.mkdir(parents=True)
        project.joinpath("a.jsonl").write_text(
            "\n".join(
                json.dumps({"type": "user", "message": {"content": f"prompt {i}"}})
                for i in range(realism.MINIMUM_CORPUS)
            )
            + "\n"
        )
        return store

    def test_a_corrupt_session_store_is_an_external_error(self, tmp_path, capsys):
        bad = tmp_path / "session-store.db"
        bad.write_text("not a database")
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                str(bad),
                "--transcript-store",
                str(self._store(tmp_path)),
            ]
        )
        assert code == cli.EXIT_EXTERNAL
        assert "Cannot read" in capsys.readouterr().err

    def test_an_unwritable_output_is_an_external_error(self, tmp_path, capsys):
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                str(tmp_path / "absent.db"),
                "--transcript-store",
                str(self._store(tmp_path)),
                "--output",
                str(tmp_path / "no-such-dir" / "report.json"),
            ]
        )
        assert code == cli.EXIT_EXTERNAL
        assert "Cannot write" in capsys.readouterr().err

    def test_a_readable_session_store_contributes_to_the_corpus(self, tmp_path, capsys):
        db = tmp_path / "session-store.db"
        connection = sqlite3.connect(db)
        with connection:
            connection.execute("CREATE TABLE sessions (id TEXT, repository TEXT)")
            connection.execute("CREATE TABLE turns (session_id TEXT, user_message TEXT)")
            connection.execute(
                "INSERT INTO sessions VALUES ('s1', 'rjmurillo/ai-agents')"
            )
            connection.executemany(
                "INSERT INTO turns VALUES ('s1', ?)",
                [(f"session prompt {i}",) for i in range(realism.MINIMUM_CORPUS)],
            )
        connection.close()
        empty = tmp_path / "projects"
        empty.mkdir()
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                str(db),
                "--transcript-store",
                str(empty),
            ]
        )
        assert code == cli.EXIT_OK
        assert f"Corpus: {realism.MINIMUM_CORPUS}" in capsys.readouterr().out


class TestNoPromptTextEscapes:
    """The report must never carry prompt text.

    Both corpora are private local data. The eval reads them, counts matches,
    and emits only phrases that the skills tree already documents publicly.
    A change that put a prompt into the report or the summary would leak
    private text into a committed artifact, so it is guarded here rather than
    left to review.
    """

    SECRET = "my private prompt about an unreleased thing"

    def _skills(self, tmp_path):
        skills = tmp_path / "skills" / "alpha"
        skills.mkdir(parents=True, exist_ok=True)
        (skills / "SKILL.md").write_text(
            "---\nname: alpha\ndescription: x\n---\n\n"
            "## Triggers\n\n| Phrase | Effect |\n|---|---|\n| `documented phrase` | runs |\n"
        )
        return skills.parent

    def _store(self, tmp_path):
        store = tmp_path / "projects"
        project = store / "x-ai-agents"
        project.mkdir(parents=True)
        lines = [
            json.dumps({"type": "user", "message": {"content": f"{self.SECRET} {i}"}})
            for i in range(realism.MINIMUM_CORPUS)
        ]
        project.joinpath("a.jsonl").write_text("\n".join(lines) + "\n")
        return store

    def _run(self, tmp_path, capsys):
        out = tmp_path / "report.json"
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                str(tmp_path / "absent.db"),
                "--transcript-store",
                str(self._store(tmp_path)),
                "--output",
                str(out),
            ]
        )
        assert code == cli.EXIT_OK
        return out.read_text(), capsys.readouterr().out

    def test_no_transcript_prompt_reaches_the_report_or_stdout(self, tmp_path, capsys):
        report, stdout = self._run(tmp_path, capsys)
        assert self.SECRET not in report
        assert self.SECRET not in stdout

    def test_no_session_store_prompt_reaches_the_report_or_stdout(self, tmp_path, capsys):
        db = tmp_path / "session-store.db"
        connection = sqlite3.connect(db)
        with connection:
            connection.execute("CREATE TABLE sessions (id TEXT, repository TEXT)")
            connection.execute("CREATE TABLE turns (session_id TEXT, user_message TEXT)")
            connection.execute("INSERT INTO sessions VALUES ('s1', 'x/ai-agents')")
            connection.executemany(
                "INSERT INTO turns VALUES ('s1', ?)",
                [(f"{self.SECRET} {i}",) for i in range(realism.MINIMUM_CORPUS)],
            )
        connection.close()
        empty = tmp_path / "projects"
        empty.mkdir()
        out = tmp_path / "report.json"
        code = cli.main(
            [
                "--skills-dir",
                str(self._skills(tmp_path)),
                "--session-store",
                str(db),
                "--transcript-store",
                str(empty),
                "--output",
                str(out),
            ]
        )
        assert code == cli.EXIT_OK
        assert self.SECRET not in out.read_text()
        assert self.SECRET not in capsys.readouterr().out

    def test_the_report_carries_only_schema_keys_and_documented_phrases(
        self, tmp_path, capsys
    ):
        """Negative control for the two tests above: they would still pass if
        the report were empty. This pins that every string in it is either a
        schema key or a phrase the skills tree documents publicly."""
        report_text, _ = self._run(tmp_path, capsys)
        report = json.loads(report_text)

        def strings(node):
            if isinstance(node, str):
                yield node
            elif isinstance(node, dict):
                for key, value in node.items():
                    yield key
                    yield from strings(value)
            elif isinstance(node, list):
                for value in node:
                    yield from strings(value)

        schema = {
            "corpus_prompts", "control_prompts", "documented", "promoted",
            "control_documented", "observed_phrases", "skills",
            "measurable_phrases", "excluded_phrases", "realism", "skill",
            "phrase", "occurrences",
        }
        public = (self._skills(tmp_path) / "alpha" / "SKILL.md").read_text()
        untraceable = [s for s in strings(report) if s not in schema and s not in public]
        assert untraceable == []
