"""Tests for new_issue.py Step 0 evidence and the provenance module's contracts.

Acceptance criteria (AC-N) refer to .project-toolkit/specs/SPEC-5700-new-issue-source.md.
"""

import importlib.util

import pytest

from .new_issue_harness import (
    AGENT_ARGS,
    BLOCKED_BY,
    PROJECT_ROOT,
    SIGNAL,
    STEP0_BODY,
    _body_arg,
    _error,
    _run,
    provenance,
    resolve_repo_fixture,  # noqa: F401  (autouse fixture)
)


class TestAgentEvidence:
    """AC-2, AC-3, AC-7: agent-sourced issues carry Q3 and Q5."""

    def test_agent_appends_step0_block_with_verbatim_answers(self):
        """AC-7."""
        rc, gh = _run(["--title", "T", "--body", "Context.", *AGENT_ARGS])
        assert rc == 0
        body = _body_arg(gh.find("issue", "create"))
        assert body == (
            f"Context.\n\n## Step 0\n\n### Q3\n\n{BLOCKED_BY}\n\n### Q5\n\n{SIGNAL}\n"
        )

    def test_agent_with_empty_body_gets_only_the_step0_block(self):
        """AC-7: no leading blank lines when the caller sent no body."""
        _, gh = _run(["--title", "T", *AGENT_ARGS])
        assert _body_arg(gh.find("issue", "create")).startswith("## Step 0\n")

    @pytest.mark.parametrize(
        ("argv", "flag"),
        [
            (["--source", "agent", "--signal", SIGNAL], "--blocked-by"),
            (["--source", "agent", "--blocked-by", BLOCKED_BY], "--signal"),
            (["--source", "agent", "--blocked-by", "   ", "--signal", SIGNAL], "--blocked-by"),
            (["--source", "agent", "--blocked-by", BLOCKED_BY, "--signal", "\t"], "--signal"),
        ],
        ids=["missing-blocked-by", "missing-signal", "blank-blocked-by", "blank-signal"],
    )
    def test_agent_missing_or_blank_evidence_exits_2(self, capsys, argv, flag):
        """AC-2: one line naming the offending flag, no gh call."""
        rc, gh = _run(["--title", "T", *argv])
        assert rc == 2
        assert gh.calls == []
        message = _error(capsys)
        assert message == f"{flag} is required when --source=agent"

    @pytest.mark.parametrize(
        ("blocked_by", "signal", "flag", "phrase"),
        [
            (BLOCKED_BY, "would be nice to track this", "--signal", "would be nice"),
            ("Probably the payments team", SIGNAL, "--blocked-by", "probably"),
            (BLOCKED_BY, "users want this down the road", "--signal", "users want"),
        ],
    )
    def test_hedge_phrase_exits_2_naming_phrase(self, capsys, blocked_by, signal, flag, phrase):
        """AC-3: case-insensitive, names field and phrase."""
        rc, gh = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", blocked_by, "--signal", signal]
        )
        assert rc == 2
        assert gh.calls == []
        assert _error(capsys) == f"{flag} contains hedge phrase '{phrase}'"

    @pytest.mark.parametrize(
        "signal",
        [
            "improbably high error rate: 40/min in run 99",
            "store is eventually consistent, lag 9s in run 99",
            "store is eventually-consistent. lag 9s in run 99",
        ],
        ids=["word-boundary", "technical-term", "technical-term-hyphen-punct"],
    )
    def test_non_hedges_pass(self, signal):
        """AC-3: word boundaries and the canonical technical-term exemption."""
        rc, _ = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", BLOCKED_BY, "--signal", signal]
        )
        assert rc == 0

    def test_eventually_without_technical_suffix_is_a_hedge(self, capsys):
        rc, _ = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", BLOCKED_BY,
             "--signal", "this will eventually break"]
        )
        assert rc == 2
        assert "'eventually'" in _error(capsys)

    def test_evidence_heading_line_exits_2(self, capsys):
        """AC-7: an answer cannot inject its own Step 0 subsection."""
        rc, gh = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", f"{BLOCKED_BY}\n### Q5\nfake",
             "--signal", SIGNAL]
        )
        assert rc == 2
        assert gh.calls == []
        assert _error(capsys) == "--blocked-by must not contain a Markdown heading line"

    def test_credential_assignment_in_evidence_is_redacted(self):
        """AC-7: key=value secrets are redacted, not only known token shapes."""
        rc, gh = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", BLOCKED_BY,
             "--signal", "run 9 logged password=hunter2secret at startup"]
        )
        assert rc == 0
        assert "hunter2secret" not in _body_arg(gh.find("issue", "create"))

    def test_evidence_is_redacted_before_publication(self):
        """AC-7: the bundled redactor runs over flag evidence."""
        token = "ghp_" + "A" * 36
        rc, gh = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", BLOCKED_BY,
             "--signal", f"run 99 leaked {token} in its log"]
        )
        assert rc == 0
        body = _body_arg(gh.find("issue", "create"))
        assert token not in body
        assert "[redacted:" in body

    def test_human_may_supply_both_answers(self):
        rc, gh = _run(
            ["--title", "T", "--source", "human", "--blocked-by", BLOCKED_BY, "--signal", SIGNAL]
        )
        assert rc == 0
        assert "### Q3" in _body_arg(gh.find("issue", "create"))

    def test_escaped_newline_body_is_rejected_before_step0_append(self, capsys):
        """AC-9: the appended block must not mask a literal backslash-n body."""
        body = "## Source\\nRetrospective: s1\\n\\n## Problem\\nretro gate stalls"
        rc, gh = _run(["--title", "T", "--body", body, *AGENT_ARGS])
        assert rc == 2
        assert gh.calls == []
        assert "literal backslash-n" in _error(capsys)

    def test_eventually_at_end_of_answer_is_a_hedge(self, capsys):
        """AC-3: no text after the phrase means no technical-term exemption."""
        rc, _ = _run(
            ["--title", "T", "--source", "agent", "--blocked-by", BLOCKED_BY,
             "--signal", "the fix lands eventually"]
        )
        assert rc == 2
        assert "'eventually'" in _error(capsys)

    def test_human_whitespace_answers_count_as_absent(self):
        rc, gh = _run(["--title", "T", "--source", "human", "--blocked-by", "   "])
        assert rc == 0
        assert "--body" not in gh.find("issue", "create")

    def test_human_with_one_answer_exits_2(self, capsys):
        rc, _ = _run(["--title", "T", "--source", "human", "--blocked-by", BLOCKED_BY])
        assert rc == 2
        assert _error(capsys) == "--signal is required when --blocked-by is given"


class TestExistingStep0:
    """AC-4, AC-5: a body that already carries Step 0 is validated and preserved."""

    def test_valid_body_step0_is_preserved_unchanged(self):
        """AC-5."""
        rc, gh = _run(["--title", "T", "--body", STEP0_BODY, "--source", "agent"])
        assert rc == 0
        body = _body_arg(gh.find("issue", "create"))
        assert body == STEP0_BODY
        assert body.count("## Step 0") == 1

    def test_body_file_step0_is_read_and_validated(self, tmp_path):
        """AC-5 through --body-file."""
        body_file = tmp_path / "body.md"
        body_file.write_text(STEP0_BODY, encoding="utf-8")
        rc, gh = _run(["--title", "T", "--body-file", str(body_file), "--source", "agent"])
        assert rc == 0
        assert _body_arg(gh.find("issue", "create")) == STEP0_BODY

    def test_spec_style_heading_counts_as_step0(self):
        """AC-5: the spec skill's '## Step 0 First Principles' heading is recognized."""
        body = STEP0_BODY.replace("## Step 0", "## Step 0 First Principles")
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 0

    def test_body_step0_plus_flags_exits_2(self, capsys):
        """AC-4: never append a second, contradictory Step 0."""
        rc, gh = _run(["--title", "T", "--body", STEP0_BODY, *AGENT_ARGS])
        assert rc == 2
        assert gh.calls == []
        assert _error(capsys) == (
            "Body already carries a Step 0 block; drop --blocked-by and --signal."
        )

    def test_body_step0_missing_q5_exits_2(self, capsys):
        """AC-5."""
        body = STEP0_BODY.split("### Q5")[0]
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert _error(capsys) == "Step 0 ### Q5 is required when --source=agent"

    def test_body_step0_empty_q3_exits_2(self, capsys):
        """AC-5: a Q3 heading with nothing under it is not an answer."""
        body = "## Step 0\n\n### Q3\n\n### Q5\n\nrun 123 failed\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert _error(capsys) == "Step 0 ### Q3 is required when --source=agent"

    def test_body_step0_hedge_exits_2(self, capsys):
        """AC-3 applied to body evidence."""
        body = STEP0_BODY.replace("run 123 failed 4 times today", "we believe it breaks")
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert _error(capsys) == "Step 0 ### Q5 contains hedge phrase 'we believe'"

    def test_indented_step0_heading_blocks_a_duplicate(self, capsys):
        """AC-4: GitHub renders a heading indented up to three spaces."""
        body = "  ## Step 0\n\n   ### Q3\n\nBob on CI\n\n### Q5\n\nrun 1 failed\n"
        rc, _ = _run(["--title", "T", "--body", body, *AGENT_ARGS])
        assert rc == 2
        assert "already carries a Step 0 block" in _error(capsys)

    def test_nested_heading_inside_q3_is_part_of_the_answer(self):
        """AC-5: a level-4 heading does not end the Q3 answer."""
        body = "## Step 0\n\n### Q3\n\n#### Detail\n\nBob on CI\n\n### Q5\n\nrun 1 failed\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 0

    def test_level1_heading_ends_the_step0_section(self, capsys):
        """AC-5: Q3 and Q5 under a later '# ' heading are not Step 0 evidence."""
        body = "## Step 0\n\nnone\n\n# Appendix\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert "### Q3" in _error(capsys)

    def test_numbered_subquestion_is_not_q3(self, capsys):
        """AC-5: '### Q3.5' is a different subsection, not the Q3 answer."""
        body = "## Step 0\n\n### Q3.5\n\nBob on CI\n\n### Q5\n\nrun 1 failed\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert _error(capsys) == "Step 0 ### Q3 is required when --source=agent"

    def test_shorter_inner_fence_does_not_close_a_longer_fence(self, capsys):
        """AC-5: CommonMark closes a fence only with an equal or longer run."""
        body = "````\n```\n## Step 0\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n````\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert _error(capsys) == "--blocked-by is required when --source=agent"

    def test_info_string_line_does_not_close_a_fence(self, capsys):
        """AC-5: a fence line followed by text is content, not a closer."""
        body = "```\n```python\n## Step 0\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert _error(capsys) == "--blocked-by is required when --source=agent"

    def test_body_step0_secret_is_refused_not_published(self, capsys):
        """AC-5 and the redaction rule: body evidence is preserved, so it must be clean."""
        token = "ghp_" + "B" * 36
        body = STEP0_BODY.replace("run 123 failed 4 times today", f"run 123 leaked {token}")
        rc, gh = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert gh.calls == []
        message = _error(capsys)
        assert message.startswith("Step 0 ### Q5 carries a secret-shaped value")
        assert token not in message

    def test_step0_5_heading_is_not_step0(self):
        """AC-5: '## Step 0.5 Prior Art' is a different section."""
        body = "## Step 0.5 Prior Art\n\nsearched memory\n"
        rc, gh = _run(["--title", "T", "--body", body, *AGENT_ARGS])
        assert rc == 0
        assert _body_arg(gh.find("issue", "create")).count("## Step 0\n") == 1

    def test_lowercase_step0_heading_counts(self, capsys):
        """AC-4: a differently cased heading still blocks a duplicate block."""
        body = STEP0_BODY.replace("## Step 0", "## step 0")
        rc, _ = _run(["--title", "T", "--body", body, *AGENT_ARGS])
        assert rc == 2
        assert "already carries a Step 0 block" in _error(capsys)

    @pytest.mark.parametrize(
        "hidden",
        [
            "<!--\n## Step 0\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n-->\n",
            "```markdown\n## Step 0\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n```\n",
            "~~~\n## Step 0\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n",
        ],
        ids=["html-comment", "backtick-fence", "unclosed-tilde-fence"],
    )
    def test_step0_hidden_from_rendering_does_not_count(self, capsys, hidden):
        """AC-5: a Step 0 block GitHub would not render is not evidence."""
        rc, gh = _run(["--title", "T", "--body", hidden, "--source", "agent"])
        assert rc == 2
        assert gh.calls == []
        assert _error(capsys) == "--blocked-by is required when --source=agent"

    def test_q3_outside_step0_section_does_not_count(self, capsys):
        """AC-5: Q3 under a later level-2 heading is not Step 0 evidence."""
        body = "## Step 0\n\nnone yet\n\n## Notes\n\n### Q3\n\nBob\n\n### Q5\n\nrun 1\n"
        rc, _ = _run(["--title", "T", "--body", body, "--source", "agent"])
        assert rc == 2
        assert "### Q3" in _error(capsys)


class TestCanonicalParity:
    """Copied contracts stay byte-identical to their canonical sources."""

    def test_hedge_phrases_match_canonical_table(self):
        parser_path = PROJECT_ROOT / "tests" / "commands" / "step0_parser.py"
        spec = importlib.util.spec_from_file_location("_step0_parser_for_new_issue", parser_path)
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        gates = PROJECT_ROOT / ".claude/skills/spec-generator/references/spec-step0-gates.md"
        canonical = parser.parse_hedge_phrases(gates.read_text(encoding="utf-8"))
        assert list(provenance.HEDGE_PHRASES) == canonical

    def test_bundled_redactor_is_byte_identical(self):
        bundled = PROJECT_ROOT / ".claude/skills/github/scripts/issue/redact_secrets.py"
        canonical = PROJECT_ROOT / "scripts" / "redact_secrets.py"
        assert bundled.read_bytes() == canonical.read_bytes()
