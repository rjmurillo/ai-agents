"""Tests for new_issue.py.

Acceptance criteria (AC-N) refer to .project-toolkit/specs/SPEC-5700-new-issue-source.md.
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import PROJECT_ROOT, import_skill_script

mod = import_skill_script(".claude/skills/github/scripts/issue/new_issue.py")
main = mod.main

ISSUE_URL = "https://github.com/owner/repo/issues/42\n"
BLOCKED_BY = "Alice on Payments, blocked on the webhook retry"
SIGNAL = "error count spiked to 40/min per PR #1234"
AGENT_ARGS = ["--source", "agent", "--blocked-by", BLOCKED_BY, "--signal", SIGNAL]
STEP0_BODY = (
    "Context line.\n\n## Step 0\n\n### Q3\n\nBob on CI, blocked on red main\n\n"
    "### Q5\n\nrun 123 failed 4 times today\n"
)


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class FakeGh:
    """Route each gh call by its subcommand and record every call."""

    def __init__(
        self,
        label_create: MagicMock | None = None,
        issue_create: MagicMock | None = None,
        issue_edit: MagicMock | None = None,
    ) -> None:
        self.routes = {
            ("label", "create"): label_create or _make_proc(),
            ("issue", "create"): issue_create or _make_proc(stdout=ISSUE_URL),
            ("issue", "edit"): issue_edit or _make_proc(),
        }
        self.calls: list[list[str]] = []

    def __call__(self, args, **_kwargs):
        self.calls.append(list(args))
        return self.routes[(args[1], args[2])]

    def find(self, group: str, verb: str) -> list[str]:
        return next(c for c in self.calls if c[1:3] == [group, verb])

    def verbs(self) -> list[tuple[str, str]]:
        return [(c[1], c[2]) for c in self.calls]


def _run(argv: list[str], gh: FakeGh | None = None) -> tuple[int, FakeGh]:
    gh = gh or FakeGh()
    with patch("subprocess.run", side_effect=gh):
        rc = main([*argv, "--output-format", "json"])
    return rc, gh


def _body_arg(create_call: list[str]) -> str:
    return create_call[create_call.index("--body") + 1]


def _error(capsys) -> str:
    data = json.loads(capsys.readouterr().out)
    assert data["Success"] is False
    return data["Error"]["Message"]


@pytest.fixture(autouse=True)
def resolve_repo():
    """Resolve every run to owner/repo without touching git or gh."""
    with patch.object(mod, "resolve_repo_params") as mock_resolve:
        info = MagicMock()
        info.owner = "owner"
        info.repo = "repo"
        mock_resolve.return_value = info
        yield mock_resolve


class TestNewIssue:
    """Existing behavior, now under an explicit --source."""

    def test_create_basic_issue(self, capsys):
        rc, _ = _run(["--title", "Test Title", "--source", "human"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is True
        assert data["Data"]["issue_number"] == 42
        assert data["Data"]["title"] == "Test Title"

    def test_data_number_is_positive_int_and_url_set_on_success(self, capsys):
        # Regression for issue #2767: callers read Data.number, which was null.
        gh = FakeGh(issue_create=_make_proc(stdout="https://github.com/owner/repo/issues/2767\n"))
        rc, _ = _run(["--title", "Test Title", "--source", "human"], gh)
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        number = data["Data"]["number"]
        assert isinstance(number, int) and number > 0
        assert number == 2767
        assert data["Data"]["url"] == "https://github.com/owner/repo/issues/2767"

    def test_create_with_body_and_labels(self):
        rc, gh = _run(
            ["--title", "Title", "--body", "Body text", "--labels", "bug,P1", "--source", "human"]
        )
        assert rc == 0
        assert "--body" in gh.find("issue", "create")
        assert gh.find("issue", "edit").count("--add-label") == 2

    def test_api_error_exits_3(self, capsys):
        gh = FakeGh(issue_create=_make_proc(returncode=1, stderr="API error"))
        rc, _ = _run(["--title", "Title", "--source", "human"], gh)
        assert rc == 3
        data = json.loads(capsys.readouterr().out)
        assert data["Success"] is False
        assert data["Error"]["Type"] == "ApiError"

    def test_unparseable_result_exits_3(self, capsys):
        gh = FakeGh(issue_create=_make_proc(stdout="no url here"))
        rc, _ = _run(["--title", "Title", "--source", "human"], gh)
        assert rc == 3
        data = json.loads(capsys.readouterr().out)
        assert data["Error"]["Type"] == "ApiError"

    def test_empty_body_not_passed(self):
        _, gh = _run(["--title", "Title", "--body", "", "--source", "human"])
        assert "--body" not in gh.find("issue", "create")

    def test_empty_labels_apply_only_the_source_label(self):
        _, gh = _run(["--title", "Title", "--labels", "", "--source", "human"])
        create = gh.find("issue", "create")
        assert create.count("--label") == 1
        assert ("issue", "edit") not in gh.verbs()


class TestSourceFlag:
    """AC-1, AC-8, AC-9: provenance is required, labeled atomically, validated first."""

    def test_missing_source_exits_2_before_any_call(self, resolve_repo):
        """AC-1: argparse refuses a missing --source."""
        gh = FakeGh()
        with patch("subprocess.run", side_effect=gh), pytest.raises(SystemExit) as exc:
            main(["--title", "x"])
        assert exc.value.code == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()

    def test_invalid_source_value_exits_2(self):
        """AC-1: only human or agent is accepted."""
        with pytest.raises(SystemExit) as exc:
            main(["--title", "x", "--source", "bot"])
        assert exc.value.code == 2

    def test_human_source_labels_in_create_call_without_step0(self):
        """AC-8: the source label rides in the create call; no Step 0 for human."""
        rc, gh = _run(["--title", "T", "--body", "b", "--source", "human"])
        assert rc == 0
        create = gh.find("issue", "create")
        assert create[create.index("--label") + 1] == "source:human"
        assert "## Step 0" not in _body_arg(create)

    def test_source_label_is_ensured_before_create(self):
        """AC-8: the label is created in the target repo before the issue."""
        _, gh = _run(["--title", "T", "--source", "human"])
        assert gh.verbs()[:2] == [("label", "create"), ("issue", "create")]
        label_call = gh.find("label", "create")
        assert label_call[3] == "source:human"
        assert label_call[label_call.index("--repo") + 1] == "owner/repo"

    def test_existing_label_does_not_block_create(self):
        """AC-8: 'already exists' from gh label create is the normal case."""
        exists = 'label with name "source:agent" already exists'
        gh = FakeGh(label_create=_make_proc(1, stderr=exists))
        rc, _ = _run(["--title", "T", *AGENT_ARGS], gh)
        assert rc == 0

    def test_label_ensure_failure_defers_to_create_call(self, capsys):
        """AC-8: a failed ensure leaves the create call as the fail-closed point."""
        gh = FakeGh(
            label_create=_make_proc(1, stderr="HTTP 403: Resource not accessible"),
            issue_create=_make_proc(1, stderr="could not add label: 'source:agent' not found"),
        )
        rc, _ = _run(["--title", "T", *AGENT_ARGS], gh)
        assert rc == 3
        assert ("issue", "edit") not in gh.verbs()
        assert "source:agent" in _error(capsys)

    def test_label_ensure_timeout_defers_to_create_call(self):
        """AC-8: a hung ensure does not abort; the create call still decides."""
        gh = FakeGh()

        def _route(args, **kwargs):
            if args[1:3] == ["label", "create"]:
                raise mod.subprocess.TimeoutExpired(args, 30)
            return gh(args, **kwargs)

        with patch("subprocess.run", side_effect=_route):
            rc = main(["--title", "T", "--source", "human", "--output-format", "json"])
        assert rc == 0
        assert gh.verbs() == [("issue", "create")]

    def test_success_output_reports_source(self, capsys):
        rc, _ = _run(["--title", "T", *AGENT_ARGS])
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["Data"]["source"] == "agent"

    def test_invalid_input_never_resolves_repo(self, resolve_repo):
        """AC-9: validation runs before repository resolution."""
        rc, gh = _run(["--title", "T", "--source", "agent"])
        assert rc == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()

    def test_empty_title_never_resolves_repo(self, resolve_repo):
        """AC-9: the title check moved ahead of repository resolution."""
        rc, gh = _run(["--title", "  ", "--source", "human"])
        assert rc == 2
        assert gh.calls == []
        resolve_repo.assert_not_called()


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


class TestSourceLabelConflicts:
    """AC-6: at most one source label, matching --source."""

    def test_conflicting_source_label_exits_2(self, capsys):
        rc, gh = _run(["--title", "T", "--labels", "bug,source:human", *AGENT_ARGS])
        assert rc == 2
        assert gh.calls == []
        assert _error(capsys) == (
            "--labels carries source:human, which conflicts with --source agent"
        )

    def test_matching_source_label_is_passed_once(self):
        """AC-6: dedupe, case-insensitive; the create call carries it, edit does not."""
        rc, gh = _run(["--title", "T", "--labels", "bug, SOURCE:AGENT", *AGENT_ARGS])
        assert rc == 0
        create = gh.find("issue", "create")
        assert create.count("--label") == 1
        edit = gh.find("issue", "edit")
        assert edit[edit.index("--add-label") + 1 :] == ["bug"]

    def test_only_source_label_in_labels_skips_edit_call(self):
        rc, gh = _run(["--title", "T", "--labels", "source:agent", *AGENT_ARGS])
        assert rc == 0
        assert ("issue", "edit") not in gh.verbs()


class TestCanonicalParity:
    """Copied contracts stay byte-identical to their canonical sources."""

    def test_hedge_phrases_match_canonical_table(self):
        parser_path = PROJECT_ROOT / "tests" / "commands" / "step0_parser.py"
        spec = importlib.util.spec_from_file_location("_step0_parser_for_new_issue", parser_path)
        parser = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(parser)
        gates = PROJECT_ROOT / ".claude/skills/spec-generator/references/spec-step0-gates.md"
        canonical = parser.parse_hedge_phrases(gates.read_text(encoding="utf-8"))
        assert list(mod._HEDGE_PHRASES) == canonical

    def test_bundled_redactor_is_byte_identical(self):
        bundled = PROJECT_ROOT / ".claude/skills/github/scripts/issue/redact_secrets.py"
        canonical = PROJECT_ROOT / "scripts" / "redact_secrets.py"
        assert bundled.read_bytes() == canonical.read_bytes()
