# taste-lint: ignore file-size, this suite covers one validator end to end.
"""Tests for the Markdown vendor-portability ratchet (issue #2050).

scripts/validation/check_skill_md_portability.py is the Markdown counterpart to
check_skill_portability.py. The script-only ratchet explicitly deferred SKILL.md
and reference .md files because prose carries a prose-vs-runtime ambiguity. This
validator closes that gap: it counts upstream-only runtime path references in
skill ``.md`` files, grandfathers the existing offenders in a JSON baseline,
fails on new drift, and honors a machine-readable ``vendor-portability`` HTML
comment that lets a skill declare a documented path dependency (the issue's
acceptance criterion: declare paths in a machine-readable section of SKILL.md).

These tests cover the counting/scan/diff units, the opt-out marker, fenced-code
stripping, inline-code path counting, and assert the committed repo has no drift
against its baseline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

_VALIDATION = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_VALIDATION))

import check_skill_md_portability as cmp


def _seed_git_tree(root: Path) -> None:
    """Make the fixture a repository: an unverifiable tree refuses the write."""
    for args in (
        ("init", "-q", "-b", "main"),
        ("add", "-A"),
        ("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "s"),
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _is_under_extra_scan_root(key: str, prefix: str) -> bool:
    """Return True only when key is inside the scanned extra root."""
    key_parts = PurePosixPath(key).parts
    prefix_parts = PurePosixPath(prefix).parts
    return key_parts[: len(prefix_parts)] == prefix_parts


class TestCountUpstreamRefs:
    def test_counts_each_prefix(self) -> None:
        text = (
            "Write to .agents/analysis/foo.md and read .claude/lib/paths.py "
            "and load .claude/review-axes/qa.md.\n"
        )
        assert cmp.count_upstream_refs(text) == 3

    def test_counts_windows_separators_and_mixed_case(self) -> None:
        text = (
            "Save under .agents\\sessions and import from .CLAUDE\\lib\\github_core "
            "and the .claude\\review-axes\\roadmap.md file.\n"
        )
        assert cmp.count_upstream_refs(text) == 3

    def test_ignores_glued_names(self) -> None:
        text = "The word prefix.agents/architecture and .agentship are not paths.\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_counts_multiple_occurrences(self) -> None:
        text = "Files: .agents/a, .agents/b, .claude/review-axes/c.\n"
        assert cmp.count_upstream_refs(text) == 3

    def test_does_not_count_claude_skills_prefix(self) -> None:
        # .claude/skills/ is the install-root-relative convention the helper
        # resolves; it is intentionally not flagged (matches script ratchet
        # exclusion that .claude/skills/ is resolvable, unlike .agents/).
        text = "Run .claude/skills/memory/scripts/search_memory.py here.\n"
        assert cmp.count_upstream_refs(text) == 0

    @pytest.mark.parametrize(
        "text",
        [
            "Use templates/agents for generation.",
            "Use `.agents` for state.",
            "[state](/.agents)",
            "![state](/templates/agents)",
            "See .claude/lib in the plugin.",
            "Use .claude/review-axes, then report findings.",
        ],
    )
    def test_counts_bare_directory_refs_at_word_boundary(self, text: str) -> None:
        assert cmp.count_upstream_refs(text) == 1

    @pytest.mark.parametrize(
        "text",
        [
            "templates/agentsx should not count.",
            ".agentship should not count.",
            ".claude/libx should not count.",
            ".claude/review-axesx should not count.",
        ],
    )
    def test_ignores_partial_word_directory_refs(self, text: str) -> None:
        assert cmp.count_upstream_refs(text) == 0

    def test_counts_templates_agents_and_platforms(self) -> None:
        # Both hold generator inputs that never ship in the plugin, so a
        # consumer following either reference lands on nothing (issue #3459).
        text = (
            "Canonical source: `templates/agents/security.shared.md`. "
            "Event mapping: `templates/platforms/copilot-cli.yaml`.\n"
        )
        assert cmp.count_upstream_refs(text) == 2

    def test_counts_build_root_paths(self) -> None:
        text = "Regenerate with `build/scripts/generate_rules.py` before shipping.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_counts_templates_windows_separators_and_mixed_case(self) -> None:
        text = "See TEMPLATES\\AGENTS\\x.md and templates\\Platforms\\y.yaml.\n"
        assert cmp.count_upstream_refs(text) == 2

    def test_does_not_count_bare_templates_dir(self) -> None:
        # Bare templates/ is overloaded: a Flask or Django render directory and
        # a file-relative asset directory bundled inside a skill both use it,
        # and both resolve consumer-side. Only the agents/ and platforms/
        # segments name upstream-only generator inputs.
        text = (
            "Render from templates/ at request time, and the bundled "
            "templates/report.md ships beside this skill.\n"
        )
        assert cmp.count_upstream_refs(text) == 0

    def test_does_not_count_bare_build_word(self) -> None:
        text = "Run the build before committing.\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_does_not_count_templates_nested_under_another_dir(self) -> None:
        """A second segment is required, so this probes the real nested shape.

        The earlier version of this test used ``assets/templates/foo.md``,
        which matches no pattern at all because ``foo.md`` is not ``agents``
        or ``platforms``. It passed against a regex that did not exclude a
        leading path separator, so it proved nothing.
        """
        text = "The file assets/templates/agents/foo.md ships with the skill.\n"
        assert cmp.count_upstream_refs(text) == 0

    @pytest.mark.parametrize(
        "text",
        [
            "src/templates/agents/x.md",
            "assets/templates/platforms/x.yaml",
            "https://example.com/templates/agents/x.md",
            "../templates/agents/x.md",
            r"src\templates\agents\x.md",
            "mytemplates/agents/x.md",
            "https://x.com/awesome-templates/agents/x.md",
            "--templates/agents/x",
            "templates/agentsfoo",
        ],
    )
    def test_does_not_count_paths_that_resolve_elsewhere(self, text: str) -> None:
        """Paths nested under another directory do not name the upstream dir.

        A non-dot separator or parent-directory prefix before ``templates`` means it resolves
        somewhere else and ships with its container. Windows and POSIX must
        agree; an earlier regex rejected the Windows nested form and accepted
        the POSIX one.
        """
        assert cmp.count_upstream_refs(text + "\n") == 0

    @pytest.mark.parametrize(
        "text",
        [
            "templates/agents/x.md",
            "./templates/agents/x.md",
            r".\templates\agents\x.md",
            "/templates/agents/x.md",
            "See /templates/platforms/x.yaml here",
            r"\templates\agents\x.md",
            "- templates/agents/x.md",
            "  - templates/platforms/x.yaml",
            "`templates/agents/x.md`",
            "|templates/agents/x.md|",
            "(templates/agents/x.md)",
            "'templates/agents'",
            "Templates/Agents/x.md",
            "templates/agents?raw=1",
            "templates/agents#section",
            "templates/agents",
        ],
    )
    def test_counts_paths_that_name_the_upstream_dir(self, text: str) -> None:
        """Every shape that really does name the source-tree directory.

        Covers an optional ``./`` prefix, Markdown bullets, nested list
        items, inline code, table cells, parentheses, quotes, case
        insensitivity, and a query string or anchor after a bare directory
        reference.
        """
        assert cmp.count_upstream_refs(text + "\n") == 1

    def test_does_not_count_hyphenated_or_glued_templates(self) -> None:
        # A URL segment like awesome-templates/agents/ and a glued word like
        # mytemplates/agents/ are not the repo-root templates/ directory.
        text = (
            "See https://example.com/awesome-templates/agents/x and the "
            "mytemplates/agents/y file.\n"
        )
        assert cmp.count_upstream_refs(text) == 0


class TestDotPrefixedUpstreamBoundary:
    """The ``.agents``, ``.claude/lib`` and ``.claude/review-axes`` families.

    These three patterns predate the ``templates/`` families and carried a
    lookbehind that omitted the forward slash, so any nested or URL-embedded
    occurrence counted as an upstream reference. All five patterns now share
    one boundary, so the same shapes must resolve the same way.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "src/.agents/foo.md",
            "https://example.com/.agents/foo.md",
            "vendor/.claude/lib/foo.py",
            "https://example.com/.claude/lib/foo.py",
            "src/.claude/review-axes/x.md",
            "../.agents/x.md",
            "x.agents/foo",
        ],
    )
    def test_nested_dot_prefixed_paths_do_not_count(self, text: str) -> None:
        """A dot directory under another path is not the upstream directory.

        ``src/.agents/`` ships with ``src/``; a consumer following it does not
        land on nothing, so counting it overstates the portability debt.
        """
        assert cmp.count_upstream_refs(text + "\n") == 0

    @pytest.mark.parametrize(
        "text",
        [
            ".agents/specs/x.md",
            "/.agents/specs/x.md",
            "./.agents/specs/x.md",
            ".claude/lib/foo.py",
            "/.claude/lib/foo.py",
            ".claude/review-axes/x.md",
            "/.claude/review-axes/x.md",
            r"\.agents\specs\x.md",
            r"\.claude\lib\foo.py",
            r"\.claude\review-axes\x.md",
        ],
    )
    def test_root_anchored_dot_prefixed_paths_count(self, text: str) -> None:
        """A repository-root-relative link is still an upstream reference.

        GitHub renders a leading-slash link relative to the repository root,
        so ``/.agents/specs/x.md`` names the same directory as ``.agents/``.
        """
        assert cmp.count_upstream_refs(text + "\n") == 1


class TestTerminatorWordBoundary:
    """Issue #3482: a bare directory reference that ends at a word boundary.

    The older terminator ``(?:[\\/]+|['\"?#]|$)`` ended a reference only at a
    path separator, a quote, ``?``, ``#`` or end of string. A directory name
    that ended at a space, a period, a comma, a closing bracket or most other
    punctuation was therefore invisible. The widened terminator
    ``(?:[\\/]+|(?![\\w-])(?!\\.[\\w]))`` ends the reference at any
    non-identifier boundary while still rejecting a longer directory name and a
    file-extension dot.

    Each positive below returned 0 under the old terminator and 1 under the new
    one; the revert proof in the PR body pins that direction. Each regression
    guard returned 1 under both and must stay 1. Each negative returns 0 under
    the new terminator, and the annotated ones return 1 under a plausible wrong
    widening, so they are non-vacuous.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "Generate under templates/agents for each platform.\n",  # space
            "The source is templates/agents. It ships nowhere.\n",  # period then space
            "See templates/agents.",  # period then end of file, no newline
            "Use (templates/agents) as the input.\n",  # closing paren
            "Inputs: templates/agents, platforms, and more.\n",  # comma
            "Run `templates/agents` by hand.\n",  # backtick
            "Root templates/agents: the generator source.\n",  # colon
            "Root templates/agents; see below.\n",  # semicolon
            "Delete templates/agents! Now.\n",  # exclamation
            "A list templates/agents] closes.\n",  # closing bracket
            "A brace templates/agents} closes.\n",  # closing brace
            "Edit templates/agents\nthen rebuild.\n",  # interior end of line
            "Flow templates/agents\u2192platforms today.\n",  # non-ASCII non-letter
        ],
    )
    def test_new_boundary_shapes_count(self, text: str) -> None:
        """A bare directory reference ending at a newly accepted boundary counts."""
        assert cmp.count_upstream_refs(text) == 1

    @pytest.mark.parametrize(
        "text",
        [
            "See templates/agents",  # end of file via the old ``$`` alternative
            "The templates/agents's contents ship nowhere.\n",  # possessive apostrophe
            'He cited "templates/agents" as the source.\n',  # double quote
            "Is it templates/agents? Yes.\n",  # question mark
            "templates/agents#section links within.\n",  # fragment hash
        ],
    )
    def test_old_boundary_shapes_still_count(self, text: str) -> None:
        """Every shape the old terminator already counted must keep counting."""
        assert cmp.count_upstream_refs(text) == 1

    @pytest.mark.parametrize(
        "text",
        [
            "templates/agentsx",  # trailing letter, longer directory name
            "templates/agents2",  # trailing digit, longer directory name
            "templates/agents_v2",  # trailing underscore, longer directory name
            "templates/agents-v2",  # trailing hyphen; a bare \\b widening would match
            "templates/agents.md",  # file extension dot; a naive widening would match
            "templates/AGENTS.md",  # case-folded file; a naive widening would match
            "templates/agents\u00e9",  # non-ASCII letter, longer directory name
            "{templates/agents}",  # brace is not an anchor; template variable shape
            "The word .agentsx is not a path.\n",  # dot-prefixed trailing letter
        ],
    )
    def test_word_boundary_negatives_do_not_count(self, text: str) -> None:
        """A partial-word match or a file-extension collision still does not count."""
        assert cmp.count_upstream_refs(text + "\n") == 0

    def test_cli_new_boundary_ref_causes_drift_exit_1(self, tmp_path: Path) -> None:
        """A skill file with a newly counted bare ref drifts from an empty baseline."""
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Writes under .agents today.\n", encoding="utf-8")
        # issue #3582: main() now requires every REQUIRED_SKILLS_ROOTS entry to
        # exist, not just .claude, so a bare `.claude`-only fixture exits 2.
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        # issue #5214: main() now also requires REQUIRED_EXTRA_ROOTS to exist.
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_cli_glued_negative_stays_clean_exit_0(self, tmp_path: Path) -> None:
        """A glued word that is not a directory reference does not drift."""
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "The templates/agentsx word is not a path.\n", encoding="utf-8"
        )
        # issue #3582: main() now requires every REQUIRED_SKILLS_ROOTS entry to
        # exist, not just .claude, so a bare `.claude`-only fixture exits 2.
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        # issue #5214: main() now also requires REQUIRED_EXTRA_ROOTS to exist.
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 0


class TestPathStartAnchor:
    """The anchor that decides where a path may begin.

    An earlier revision tested the character before the path with a negative
    lookbehind, ``(?<![\\w.\\-/\\\\])``, applied ahead of an optional separator.
    Any character outside that set therefore opened a match, so a home-relative
    path, a Windows drive, a shell or batch variable expansion, a ``file://``
    URL, a protocol-relative URL and a URL fragment all counted as
    repository-root references. The anchor now names the characters that may
    precede a path instead of naming the ones that may not.
    """

    @pytest.mark.parametrize(
        "text",
        [
            "~/templates/agents/x.md",
            "~/.agents/x.md",
            "${ROOT}/templates/agents/x.md",
            "${ROOT}/.agents/x.md",
            "%ROOT%\\templates\\agents\\x.md",
            "C:\\templates\\agents\\x.md",
            "C:\\.agents\\x.md",
            "file:///templates/agents/x.md",
            "//templates/agents/x.md",
            "[x](https://example.com/#/templates/agents/x.md)",
            "[x](https://example.com/?next=/.agents/x.md)",
        ],
    )
    def test_paths_rooted_somewhere_else_do_not_count(self, text: str) -> None:
        """None of these resolve from the repository root.

        A home directory, a drive letter, a variable expansion and a URL
        authority each supply their own root, so the path that follows is not
        the upstream directory even though the text after the separator matches.
        """
        assert cmp.count_upstream_refs(text + "\n") == 0

    @pytest.mark.parametrize(
        "text",
        [
            "/templates/agents/x.md",
            "[x](/templates/agents/x.md)",
            "See /templates/platforms/x.yaml for the shape.",
            "| /templates/agents/x.md | generated |",
            '<img src="/templates/agents/x.md">',
            "`templates/agents/x.md`",
            "Prose line.\n/templates/agents/x.md",
            ">/templates/agents/x.md",
        ],
    )
    def test_paths_at_a_real_start_of_context_count(self, text: str) -> None:
        """A path may open the document, follow whitespace, or follow a delimiter.

        Markdown link parentheses, table pipes, HTML attribute quotes and inline
        code backticks all introduce a path without changing where it resolves
        from, so each one still counts. A tight blockquote marker counts too, so
        it agrees with the spaced form that whitespace already accepts.
        """
        assert cmp.count_upstream_refs(text + "\n") == 1

    @pytest.mark.parametrize(
        "text",
        [
            "[x]:/templates/agents/x.md",
            "path:/templates/agents/x.md",
            "<img src=/templates/agents/x.md>",
        ],
    )
    def test_labelled_and_attribute_contexts_count(self, text: str) -> None:
        """A colon or equals in a named context introduces a real path.

        A link reference definition and a ``path:`` label both put a colon
        before the path; an unquoted HTML attribute puts an equals sign there.
        Only the ``[label]:`` form is a CommonMark construct, a link reference
        definition; ``path:`` is a project convention and the unquoted attribute
        is HTML. The validator treats each as a path reference by naming the
        context, so each counts.

        Naming the context is what makes this safe. Admitting a raw ``:`` would
        also count the Windows drive letters ``C:\\templates\\`` and
        ``C:\\.agents\\``; admitting a raw ``=`` would also count the URL query
        parameter ``?next=/.agents/x``. The guards below pin those out (issue
        #3489).
        """
        assert cmp.count_upstream_refs(text + "\n") == 1

    @pytest.mark.parametrize(
        "text",
        [
            "[x]: /templates/agents/x.md",
            "[x]:   /templates/agents/x.md",
            "[x]:\t/templates/agents/x.md",
            "[x]:\n/templates/agents/x.md",
            "path:   /templates/agents/x.md",
            "<img src= /templates/agents/x.md>",
        ],
    )
    def test_label_definition_whitespace_after_colon_still_counts(self, text: str) -> None:
        """Whitespace between the label colon and the path still counts.

        CommonMark allows optional spaces, tabs, and up to one line ending
        between a link reference definition's colon and its destination. A
        review asked to widen ``_LABEL_ANCHOR`` and ``_ATTR_ANCHOR`` to accept
        that gap, but no widening is needed: the whitespace is itself an anchor
        character, a space, tab or newline, so the path anchors on the gap
        rather than on the label. Widening the label anchors would only re-match
        what the whitespace anchor already matches, which is dead regex. This
        pins the deliberate limit so the label anchors stay tight-only.
        """
        assert cmp.count_upstream_refs(text + "\n") == 1

    @pytest.mark.parametrize(
        "text",
        [
            "C:\\templates\\agents\\x.md",
            "C:\\.agents\\specs\\x.md",
            "[x](https://example.com/p?next=/.agents/x)",
            "file:/templates/agents/x.md",
            "note:/templates/agents/x.md",
            "https://example.com/path:/templates/agents/x.md",
            "https://example.com/?src=/templates/agents/x.md",
        ],
    )
    def test_shapes_that_raw_colon_or_equals_anchors_would_break(self, text: str) -> None:
        """Negative control for the contextual anchors above.

        Each of these carries a colon or an equals sign immediately before a
        path-looking string, and none of them names the repository root. A
        colon anchors a path only when the literal ``path`` or a bracketed
        label sits at an anchor before it: a Windows drive letter, a URI scheme,
        and a bare prose word (``note:``) are none of those, and a URL query
        parameter has no enclosing tag for the attribute anchor. If someone
        replaces the contextual anchors with a raw ``:`` or ``=`` in the
        character set, these start counting and this test fails, which is the
        intended warning.
        """
        assert cmp.count_upstream_refs(text + "\n") == 0


class TestBlockquotedFence:
    """A fenced block inside a blockquote is still a code block.

    GitHub admonitions put an example inside ``>``-prefixed lines. CommonMark
    parses blockquote content as Markdown once the marker is removed, so the
    fence has to be recognised there or the example counts as prose.
    """

    def test_fence_inside_a_blockquote_is_stripped(self) -> None:
        text = "> [!NOTE]\n> ```bash\n> cp /templates/agents/x.md .\n> ```\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_blockquoted_prose_still_counts(self) -> None:
        """Only the fence is exempt; a quoted prose reference is a real one."""
        assert cmp.count_upstream_refs("> Copy /templates/agents/x.md first.\n") == 1

    def test_quoted_line_does_not_close_a_top_level_fence(self) -> None:
        """A close must match the context its open was found in.

        Otherwise a ``>``-prefixed backtick line inside a top-level fence would
        end the block early and expose the rest of the example as prose.
        """
        text = "```\n> ```\n/templates/agents/x.md\n```\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_unquoted_line_ends_a_quoted_fence(self) -> None:
        """A fenced block has no lazy continuation, so it dies with its quote.

        The unquoted line is top-level prose, not fence body, so a reference on
        it is a real dependency and must count.
        """
        text = "> ```\n> code .agents/a\nplain /templates/agents/b\n> ```\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_unterminated_quoted_fence_does_not_swallow_later_prose(self) -> None:
        text = "> ```\n> code .agents/a\nreal prose /templates/agents/b\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_line_ending_a_quoted_fence_is_re_read_at_top_level(self) -> None:
        """Ending the blockquote must not skip fence detection on that line.

        The bare fence marker leaves the blockquote and opens a top-level fence,
        so the lines after it are code and must not count.
        """
        text = "> ```bash\n> echo hi\n```\n> cp .agents/x .\n> ```\n"
        assert cmp.count_upstream_refs(text) == 0


class TestCodeBlockAndInlineHandling:
    def test_ignores_fenced_code_blocks(self) -> None:
        text = (
            "Prose before.\n\n"
            "```bash\n"
            "cat .agents/sessions/log.json\n"
            "ls .claude/lib/\n"
            "```\n\n"
            "Prose after with a real path .agents/analysis/x.md.\n"
        )
        # Only the prose-level path counts; fenced example commands are skipped.
        assert cmp.count_upstream_refs(text) == 1

    def test_counts_inline_code_spans(self) -> None:
        text = "See `.agents/sessions/` for examples; write to .agents/analysis/y.md.\n"
        assert cmp.count_upstream_refs(text) == 2

    def test_tilde_fences_are_stripped(self) -> None:
        text = "~~~\n.agents/foo\n~~~\nReal .claude/lib/bar here.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_indented_fences_are_stripped(self) -> None:
        # CommonMark allows 0-3 spaces of indentation on fence markers.
        text = "   ```bash\n   .agents/foo\n   ```\nReal .claude/lib/bar here.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_indented_fence_marker_not_opted_out(self) -> None:
        # A marker inside an indented code block must not opt the file out.
        text = (
            "   ```\n"
            "   <!-- vendor-portability: example -->\n"
            "   ```\n"
            "This prose references .agents/sessions/.\n"
        )
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 1


class TestVendorPortabilityMarker:
    def test_marker_suppresses_all_refs_in_file(self) -> None:
        text = (
            "<!-- vendor-portability: declared -->\n"
            "This skill writes to .agents/analysis/foo.md and reads "
            ".claude/lib/paths.py; both documented above.\n"
        )
        assert cmp.has_portability_marker(text) is True
        assert cmp.count_file_refs(text) == 0

    def test_marker_is_case_insensitive_and_tolerant_of_spacing(self) -> None:
        text = "<!--vendor-portability:ok-->\nWrites .agents/x.\n"
        assert cmp.has_portability_marker(text) is True

    def test_no_marker_counts_refs(self) -> None:
        text = "Writes .agents/x and .claude/lib/y.\n"
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 2

    def test_marker_inside_fenced_code_does_not_suppress(self) -> None:
        # A marker shown only inside a code block must not opt the file out.
        text = (
            "```\n"
            "<!-- vendor-portability: example -->\n"
            "```\n"
            "This prose references .agents/sessions/ which must still be counted.\n"
        )
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 1

    def test_marker_inside_inline_code_does_not_suppress(self) -> None:
        # Same rule for inline code spans.
        text = (
            "Use `<!-- vendor-portability: ok -->` in your file header.\n"
            "But this prose still references .agents/sessions/ without declaring.\n"
        )
        assert cmp.has_portability_marker(text) is False
        assert cmp.count_file_refs(text) == 1

    def test_marker_suppressed_count_excludes_marker_text(self) -> None:
        text = (
            "<!-- vendor-portability: declares .agents/state -->\n"
            "This prose references .agents/state once.\n"
        )
        assert cmp.count_marker_suppressed_refs(text) == 1

    def test_marker_suppressed_count_is_zero_without_marker(self) -> None:
        text = "This prose references .agents/state once.\n"
        assert cmp.count_marker_suppressed_refs(text) == 0


class TestScan:
    def _skill_md(self, root: Path, rel: str, body: str) -> None:
        path = root / ".claude" / "skills" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_scan_collects_md_with_refs(self, tmp_path: Path) -> None:
        self._skill_md(tmp_path, "alpha/SKILL.md", "Writes .agents/analysis/a.md\n")
        self._skill_md(tmp_path, "beta/references/b.md", "Clean prose only.\n")
        self._skill_md(tmp_path, "gamma/SKILL.md", "Reads .claude/lib/x and .agents/y\n")
        skills_dir = tmp_path / ".claude" / "skills"
        counts = cmp.scan_skill_markdown(skills_dir).counts
        assert counts == {
            "skills/alpha/SKILL.md": 1,
            "skills/gamma/SKILL.md": 2,
        }

    def test_scan_skips_marked_files(self, tmp_path: Path) -> None:
        self._skill_md(
            tmp_path,
            "alpha/SKILL.md",
            "<!-- vendor-portability: declared -->\nWrites .agents/a and .agents/b\n",
        )
        skills_dir = tmp_path / ".claude" / "skills"
        assert cmp.scan_skill_markdown(skills_dir).counts == {}


class TestPluginRootScan:
    """Every plugin root's skills tree must be scanned, not just the first one."""

    def _skill_md(self, root: Path, plugin_root: str, rel: str, body: str) -> None:
        path = root / plugin_root / "skills" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_skills_dirs_skips_roots_without_one(self, tmp_path: Path) -> None:
        """A root with no skills tree is absent, not an error.

        ``src/claude`` ships agents and rules but no skills, so a missing tree
        is the normal case rather than a misconfiguration.
        """
        self._skill_md(tmp_path, ".claude", "a/SKILL.md", "prose\n")
        assert cmp.skills_dirs(tmp_path) == [tmp_path / ".claude" / "skills"]

    def test_skills_dirs_preserves_declared_order(self, tmp_path: Path) -> None:
        """Scan order fixes baseline diff order, so it must not follow the filesystem."""
        for name in reversed(cmp.PLUGIN_ROOTS):
            self._skill_md(tmp_path, name, "a/SKILL.md", "prose\n")
        found = [d.parent.relative_to(tmp_path).as_posix() for d in cmp.skills_dirs(tmp_path)]
        assert found == list(cmp.PLUGIN_ROOTS)

    def test_a_second_root_is_scanned(self, tmp_path: Path) -> None:
        """The defect this closes: refs in a shipped mirror were invisible.

        ``src/copilot-cli/skills`` is generated from ``.claude/commands``, so it
        was covered by neither the commands tree nor the ``.claude/skills``
        scan. Thirty nine references lived there unratcheted. Refs #3578.
        """
        self._skill_md(tmp_path, ".claude", "a/SKILL.md", "Clean prose.\n")
        self._skill_md(tmp_path, "src/copilot-cli", "a/SKILL.md", "Reads .agents/x\n")
        assert cmp.scan_plugin_roots(tmp_path) == {"src/copilot-cli/skills/a/SKILL.md": 1}

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    def test_marker_scan_reports_broken_md_symlink(self, tmp_path: Path) -> None:
        """Marker drift scan must fail closed on the same partial-scan case."""
        skill = tmp_path / ".claude" / "skills" / "a"
        skill.mkdir(parents=True)
        (skill / "broken.md").symlink_to(tmp_path / "missing.md")

        with pytest.raises(OSError, match="Broken .md symlink"):
            cmp.scan_marker_suppressions(tmp_path)

    def test_marker_scan_contract_names_extra_scan_dirs(self) -> None:
        """The public wrapper docstring must match its scan surface."""
        assert "extra scan dirs" in (cmp.scan_marker_suppressions.__doc__ or "")

    def test_marker_scan_includes_extra_scan_dirs(self, tmp_path: Path) -> None:
        """Markers in command docs feed the same exact-count marker baseline."""
        self._skill_md(tmp_path, ".claude", "a/SKILL.md", "Clean prose.\n")
        command = tmp_path / ".claude" / "commands" / "ship.md"
        command.parent.mkdir(parents=True)
        command.write_text(
            "<!-- vendor-portability: declared -->\nWrites .agents/state.\n",
            encoding="utf-8",
        )

        assert cmp.scan_marker_suppressions(tmp_path) == {".claude/commands/ship.md": 1}

    def test_same_named_skills_in_two_roots_do_not_collide(self, tmp_path: Path) -> None:
        """Keys are repository relative because both roots hold ``skills/spec``.

        A key relative to the skills dir parent is ``skills/spec/SKILL.md`` in
        both roots, so one count would overwrite the other and half the surface
        would vanish from the baseline while still reporting clean.
        """
        self._skill_md(tmp_path, ".claude", "spec/SKILL.md", "Reads .agents/x\n")
        self._skill_md(
            tmp_path, "src/copilot-cli", "spec/SKILL.md", "Reads .agents/x and .agents/y\n"
        )
        assert cmp.scan_plugin_roots(tmp_path) == {
            ".claude/skills/spec/SKILL.md": 1,
            "src/copilot-cli/skills/spec/SKILL.md": 2,
        }

    def test_drift_in_the_second_root_returns_exit_1(self, tmp_path: Path) -> None:
        """End to end proof that the widened scan reaches the CLI exit code."""
        self._skill_md(tmp_path, ".claude", "a/SKILL.md", "Clean prose.\n")
        self._skill_md(tmp_path, "src/copilot-cli", "a/SKILL.md", "Reads .agents/x\n")
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        code = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert code == 1

    @pytest.mark.parametrize("absent", sorted(cmp.REQUIRED_SKILLS_ROOTS))
    def test_exit_2_when_a_required_root_is_missing(self, tmp_path: Path, absent: str) -> None:
        """A partial scan must fail, not narrow silently.

        This is the same failure shape as issue #3578 one level up. If a
        required root vanishes, the remaining roots still produce files, still
        compare cleanly against the baseline, and still exit 0, so nothing
        reports that a whole shipped tree went unread. Adversarial review
        caught this: the first version of the multi root scan failed only when
        every root was missing.

        Parametrized over each required root so that dropping any single entry
        from ``REQUIRED_SKILLS_ROOTS`` fails a test. A test that omitted only
        one fixed root would let the other silently leave the set.
        """
        for name in sorted(cmp.REQUIRED_SKILLS_ROOTS - {absent}):
            self._skill_md(tmp_path, name, "a/SKILL.md", "Clean prose.\n")
        assert cmp.missing_required_roots(tmp_path) == [absent]
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        assert cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 2

    def test_an_optional_root_without_skills_is_not_an_error(self, tmp_path: Path) -> None:
        """``src/claude`` ships agents and rules and has no skills tree today."""
        for name in cmp.REQUIRED_SKILLS_ROOTS:
            self._skill_md(tmp_path, name, "a/SKILL.md", "Clean prose.\n")
        for name in cmp.REQUIRED_EXTRA_ROOTS:
            (tmp_path / name).mkdir(parents=True, exist_ok=True)
        assert cmp.missing_required_roots(tmp_path) == []
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        assert cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)]) == 0

    def test_every_required_root_is_a_declared_root(self) -> None:
        """A required root missing from ``PLUGIN_ROOTS`` would never be scanned."""
        assert cmp.REQUIRED_SKILLS_ROOTS <= set(cmp.PLUGIN_ROOTS)

    def test_every_root_with_a_skills_tree_is_required(self) -> None:
        """Reality, not the constant, decides which roots are required.

        Anchoring on the filesystem is the point. Mutation testing showed that
        the parametrized case above derives its cases from
        ``REQUIRED_SKILLS_ROOTS``, so shrinking that set shrinks the test with
        it and the mutant survives. This assertion reads the repository
        instead: a root that ships a skills tree today must be required, so
        removing one from the set fails here.

        It also self-maintains. The day ``src/claude`` grows a skills tree,
        this test fails and names the root to add.
        """
        root = Path(__file__).resolve().parents[2]
        have_skills = {name for name in cmp.PLUGIN_ROOTS if (root / name / "skills").is_dir()}
        assert have_skills, "no plugin root has a skills tree; the scan would be empty"
        assert have_skills <= cmp.REQUIRED_SKILLS_ROOTS, (
            f"these roots ship skills but are not required: "
            f"{sorted(have_skills - cmp.REQUIRED_SKILLS_ROOTS)}"
        )

    def test_this_repo_has_every_required_root(self) -> None:
        """Pins the two sets against reality so the required list cannot rot."""
        root = Path(__file__).resolve().parents[2]
        assert cmp.missing_required_roots(root) == []

    def test_exit_2_when_no_root_has_a_skills_dir(self, tmp_path: Path) -> None:
        """An empty scan must fail loudly rather than report a clean zero."""
        assert cmp.main(["--repo-root", str(tmp_path)]) == 2


class TestExtraScanDirs:
    """Extra scan dirs (commands/, templates/agents/) extend the ratchet scope.

    ``.claude/commands`` mirrors into ``src/copilot-cli/skills``, which the
    plugin-root scan covers. ``templates/agents`` mirrors into
    ``src/copilot-cli/agents``, which this validator deliberately does not
    scan, so scanning the template source is the covered surface. Issue #3646.
    """

    def _write_md(self, root: Path, rel: str, body: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        # Create required skills dirs so main() doesn't exit 2
        for required in cmp.REQUIRED_SKILLS_ROOTS:
            placeholder = root / required / "skills" / "_placeholder" / "SKILL.md"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.write_text("placeholder\n", encoding="utf-8")
        for required in cmp.REQUIRED_EXTRA_ROOTS:
            (root / required).mkdir(parents=True, exist_ok=True)

    def test_extra_scan_dirs_returns_existing_dirs(self, tmp_path: Path) -> None:
        """Directories in EXTRA_SCAN_ROOTS that exist are returned."""
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        dirs = cmp.extra_scan_dirs(tmp_path)
        assert tmp_path / ".claude" / "commands" in dirs

    def test_extra_scan_dirs_skips_missing(self, tmp_path: Path) -> None:
        """Missing directories are silently skipped."""
        dirs = cmp.extra_scan_dirs(tmp_path)
        assert dirs == []

    def test_extra_scan_prefix_does_not_cover_sibling_directory(self, tmp_path: Path) -> None:
        """A sibling path like commands-old is not under commands."""
        (tmp_path / ".claude" / "commands").mkdir(parents=True)
        extra_dir_prefixes = {
            d.relative_to(tmp_path).as_posix() for d in cmp.extra_scan_dirs(tmp_path)
        }

        assert not any(
            _is_under_extra_scan_root(".claude/commands-old/stale.md", prefix)
            for prefix in extra_dir_prefixes
        )

    def test_commands_dir_refs_are_included_in_scan(self, tmp_path: Path) -> None:
        """A ref inside .claude/commands/ is counted by scan_plugin_roots."""
        self._write_md(
            tmp_path,
            ".claude/commands/spec.md",
            "Read the spec at .agents/planning/spec.md\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert ".claude/commands/spec.md" in counts
        assert counts[".claude/commands/spec.md"] == 1

    def test_templates_agents_refs_are_included_in_scan(self, tmp_path: Path) -> None:
        """A ref inside templates/agents/ is counted by scan_plugin_roots."""
        self._write_md(
            tmp_path,
            "templates/agents/orchestrator.shared.md",
            "Session logs go under .agents/sessions/\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert "templates/agents/orchestrator.shared.md" in counts

    def test_clean_commands_file_not_in_counts(self, tmp_path: Path) -> None:
        """A commands file with no upstream refs does not appear in counts."""
        self._write_md(
            tmp_path,
            ".claude/commands/clean.md",
            "This file has no upstream refs.\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert ".claude/commands/clean.md" not in counts

    def test_extra_dir_drift_causes_exit_1(self, tmp_path: Path) -> None:
        """An unbaselined ref in a commands/ file exits 1."""
        self._write_md(
            tmp_path,
            ".claude/commands/drift.md",
            "Write to .agents/sessions/output.md\n",
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        code = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert code == 1

    def test_vendor_marker_suppresses_extra_dir_refs(self, tmp_path: Path) -> None:
        """A vendor-portability marker in a commands/ file silences its refs."""
        self._write_md(
            tmp_path,
            ".claude/commands/annotated.md",
            "<!-- vendor-portability: upstream refs only -->\n"
            "Read .agents/sessions/ for context.\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert ".claude/commands/annotated.md" not in counts


class TestInstructionsScanRoot:
    """``src/copilot-cli/instructions`` closes the coverage gap from issue #5214.

    ``check_skill_md_portability.py`` scanned only ``skills/`` trees and a
    handful of source dirs, so the generated Copilot instruction mirror
    (``build/scripts/generate_rules.py``) shipped undeclared upstream-only
    paths in prose with no gate reading it: neither the plugin-root ``skills/``
    scan (wrong subtree) nor the generator's ``applyTo``-only
    ``_INTERNAL_PATH_PREFIXES`` filter (globs, not body prose) covered it.
    ``.github/instructions`` is the sibling in-repo Copilot mirror, not a
    shipped plugin root, and MUST stay out of scope.
    """

    def _write_md(self, root: Path, rel: str, body: str) -> None:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        for required in cmp.REQUIRED_SKILLS_ROOTS:
            placeholder = root / required / "skills" / "_placeholder" / "SKILL.md"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.write_text("placeholder\n", encoding="utf-8")

    def test_instructions_root_is_in_extra_scan_roots(self) -> None:
        assert "src/copilot-cli/instructions" in cmp.EXTRA_SCAN_ROOTS

    def test_every_on_disk_instructions_tree_is_in_extra_scan_roots(self) -> None:
        """Converse guard: every shipped ``instructions/`` tree must be configured.

        The previous test only proves the configured root exists; it says
        nothing about a DIFFERENT on-disk plugin ``instructions/`` tree that
        ``EXTRA_SCAN_ROOTS`` fails to name. Issue #5214 was exactly this
        shape: a shipped ``instructions/`` tree existed with no scan root
        naming it, and nothing caught the gap until a human filed it. Walk
        every real plugin root in the checked-out repo and assert each one's
        ``instructions/`` directory, if present, is configured.
        """
        root = Path(__file__).resolve().parents[2]
        for plugin_root in cmp.PLUGIN_ROOTS:
            candidate = root / plugin_root / "instructions"
            if not candidate.is_dir():
                continue
            rel = candidate.relative_to(root).as_posix()
            assert rel in cmp.EXTRA_SCAN_ROOTS, (
                f"{rel} ships an instructions/ tree but is not in EXTRA_SCAN_ROOTS"
            )

    def test_instructions_dir_refs_are_included_in_scan(self, tmp_path: Path) -> None:
        """A ref inside src/copilot-cli/instructions/ is counted by scan_plugin_roots."""
        self._write_md(
            tmp_path,
            "src/copilot-cli/instructions/ci-scripts.instructions.md",
            "Run scripts/validation/pre_pr.py before every push.\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert "src/copilot-cli/instructions/ci-scripts.instructions.md" in counts
        assert counts["src/copilot-cli/instructions/ci-scripts.instructions.md"] == 1

    def test_github_instructions_mirror_is_not_scanned(self, tmp_path: Path) -> None:
        """.github/instructions is the in-repo Copilot mirror, not a shipped
        plugin root, so an upstream ref there must not be flagged."""
        self._write_md(
            tmp_path,
            ".github/instructions/ci-scripts.instructions.md",
            "Run scripts/validation/pre_pr.py before every push.\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert ".github/instructions/ci-scripts.instructions.md" not in counts

    def test_clean_instructions_file_not_in_counts(self, tmp_path: Path) -> None:
        """An instructions file with no upstream refs does not appear in counts."""
        self._write_md(
            tmp_path,
            "src/copilot-cli/instructions/clean.instructions.md",
            "This file has no upstream refs.\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert "src/copilot-cli/instructions/clean.instructions.md" not in counts

    def test_instructions_dir_drift_causes_exit_1(self, tmp_path: Path) -> None:
        """An unbaselined ref in an instructions/ file exits 1."""
        self._write_md(
            tmp_path,
            "src/copilot-cli/instructions/drift.instructions.md",
            "Write to .agents/sessions/output.md\n",
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        code = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert code == 1

    def test_vendor_marker_suppresses_instructions_dir_refs(self, tmp_path: Path) -> None:
        """A vendor-portability marker in an instructions/ file silences its refs."""
        self._write_md(
            tmp_path,
            "src/copilot-cli/instructions/annotated.instructions.md",
            "<!-- vendor-portability: upstream refs only -->\n"
            "Read .agents/sessions/ for context.\n",
        )
        counts = cmp.scan_plugin_roots(tmp_path)
        assert "src/copilot-cli/instructions/annotated.instructions.md" not in counts

    def test_missing_instructions_root_exits_2(self, tmp_path: Path) -> None:
        """A checkout missing the shipped instructions/ tree must fail closed.

        Without ``REQUIRED_EXTRA_ROOTS``, a checkout where generation failed
        to produce ``src/copilot-cli/instructions`` (or the directory was
        moved or deleted) would scan zero files there and still report clean,
        the same silent fail-open shape issue #5214 itself exemplified.
        """
        for required in cmp.REQUIRED_SKILLS_ROOTS:
            placeholder = tmp_path / required / "skills" / "_placeholder" / "SKILL.md"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.write_text("placeholder\n", encoding="utf-8")
        # Deliberately do NOT create src/copilot-cli/instructions.
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        code = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert code == 2

    def test_instructions_root_appears_in_success_report(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The success line names every examined root, including instructions/.

        Proves the coverage fix: ``src/copilot-cli/instructions`` used to be
        invisible in ``files_by_root`` (extra scan dirs were excluded from
        it), so the success report could not distinguish "instructions/ was
        examined and clean" from "instructions/ was never read."
        """
        self._write_md(
            tmp_path,
            "src/copilot-cli/instructions/clean.instructions.md",
            "Clean prose with no upstream refs.\n",
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"files": {}}', encoding="utf-8")
        code = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        out = capsys.readouterr().out
        assert code == 0
        assert "src/copilot-cli/instructions (1)" in out


class TestReport:
    """The output branches. None had coverage before ``_report`` was extracted."""

    def _args(self, **over: object) -> dict[str, object]:
        base: dict[str, object] = {
            "regressions": [],
            "improvements": [],
            "current": {},
            "baseline": {},
            "scanned_by_root": {".claude/skills": 1},
            "output_format": "text",
        }
        base.update(over)
        return base

    def test_json_format_emits_totals_and_scanned_by_root(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmp._report(
            **self._args(
                regressions=["a: 2 refs"],
                improvements=["b: 1 ref"],
                current={"a": 2},
                baseline={"a": 1, "b": 1},
                output_format="json",
            )
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "regressions": ["a: 2 refs"],
            "improvements": ["b: 1 ref"],
            "current_total": 2,
            "baseline_total": 2,
            "scanned_by_root": {".claude/skills": 1},
        }

    def test_json_format_prints_no_prose(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Machine output must stay parseable, so the human lines cannot leak in."""
        cmp._report(**self._args(regressions=["a: 2 refs"], output_format="json"))
        assert "DRIFT" not in capsys.readouterr().out

    def test_drift_suppresses_the_clean_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Reporting both a drift list and a no-drift summary would contradict itself."""
        cmp._report(**self._args(regressions=["a: 2 refs"]))
        out = capsys.readouterr().out
        assert "[DRIFT] a: 2 refs" in out
        assert "No Markdown vendor-portability drift" not in out

    def test_improvements_print_alongside_the_clean_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An improvement is not drift, so the run is still clean and says so."""
        cmp._report(**self._args(improvements=["b: 1 ref"], baseline={"b": 1}))
        out = capsys.readouterr().out
        assert "[IMPROVED] b: 1 ref" in out
        assert "No Markdown vendor-portability drift" in out

    def test_the_clean_line_names_every_scanned_root(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Reading 'across 0 files' as 'scanned 0 files' is what hid issue #3578."""
        cmp._report(
            **self._args(
                scanned_by_root={
                    ".claude/skills": 3,
                    "src/copilot-cli/skills": 3,
                }
            )
        )
        assert (
            "Scanned .claude/skills (3), src/copilot-cli/skills (3)."
            in capsys.readouterr().out
        )

    def test_the_clean_line_distinguishes_zero_examined_from_never_walked(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """An empty root and an unwalked root must not read the same (#5214 review)."""
        cmp._report(**self._args(scanned_by_root={"src/copilot-cli/instructions": 0}))
        assert "src/copilot-cli/instructions (0)" in capsys.readouterr().out

    def test_json_format_includes_scanned_by_root(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cmp._report(
            **self._args(
                output_format="json",
                scanned_by_root={".claude/skills": 5, "src/copilot-cli/instructions": 2},
            )
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["scanned_by_root"] == {
            ".claude/skills": 5,
            "src/copilot-cli/instructions": 2,
        }


class TestDiff:
    def test_regression_when_count_rises(self) -> None:
        regressions, improvements = cmp.diff_against_baseline(
            {"skills/a/SKILL.md": 3}, {"skills/a/SKILL.md": 2}
        )
        assert regressions and "skills/a/SKILL.md" in regressions[0]
        assert improvements == []

    def test_regression_when_new_file_offends(self) -> None:
        regressions, _ = cmp.diff_against_baseline({"skills/new/SKILL.md": 1}, {})
        assert regressions and "skills/new/SKILL.md" in regressions[0]

    def test_improvement_when_count_drops(self) -> None:
        regressions, improvements = cmp.diff_against_baseline(
            {"skills/a/SKILL.md": 1}, {"skills/a/SKILL.md": 3}
        )
        assert regressions == []
        assert improvements and "skills/a/SKILL.md" in improvements[0]

    def test_no_drift_at_baseline(self) -> None:
        regressions, improvements = cmp.diff_against_baseline(
            {"skills/a/SKILL.md": 2}, {"skills/a/SKILL.md": 2}
        )
        assert regressions == []
        assert improvements == []


class TestMarkerDiff:
    def test_marker_count_increase_is_regression(self) -> None:
        regressions, improvements = cmp.diff_marker_baseline(
            {".claude/skills/a/SKILL.md": 2},
            {".claude/skills/a/SKILL.md": 1},
        )
        assert regressions and ".claude/skills/a/SKILL.md" in regressions[0]
        assert improvements == []

    def test_marker_count_decrease_is_regression(self) -> None:
        regressions, improvements = cmp.diff_marker_baseline(
            {".claude/skills/a/SKILL.md": 0},
            {".claude/skills/a/SKILL.md": 1},
        )
        assert regressions and "baseline 1" in regressions[0]
        assert improvements == []


class TestMainCli:
    def _required_roots(self, root: Path) -> None:
        """Create an empty skills tree in every required root.

        Empty trees contribute no counts, so the tests keep their original
        expectations while satisfying the required-root check that closes the
        silent-narrowing hole.
        """
        for name in cmp.REQUIRED_SKILLS_ROOTS:
            (root / name / "skills").mkdir(parents=True, exist_ok=True)
        for name in cmp.REQUIRED_EXTRA_ROOTS:
            (root / name).mkdir(parents=True, exist_ok=True)

    def test_exit_2_when_skills_dir_missing(self, tmp_path: Path) -> None:
        rc = cmp.main(["--repo-root", str(tmp_path)])
        assert rc == 2

    def test_update_baseline_writes_and_exits_zero(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Writes .agents/x\n", encoding="utf-8"
        )
        # Every shipped root must hold a readable file or the scan-coverage guard
        # refuses the write, because one starved root is a partial checkout.
        (tmp_path / "src" / "copilot-cli" / "skills" / "a").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "skills" / "a" / "SKILL.md").write_text(
            "Nothing upstream.\n", encoding="utf-8"
        )
        (tmp_path / "src" / "copilot-cli" / "instructions" / "x.instructions.md").write_text(
            "Nothing upstream.\n", encoding="utf-8"
        )
        _seed_git_tree(tmp_path)
        baseline = tmp_path / "baseline.json"
        rc = cmp.main(
            ["--repo-root", str(tmp_path), "--baseline", str(baseline), "--update-baseline"]
        )
        assert rc == 0
        data = json.loads(baseline.read_text(encoding="utf-8"))
        assert data["files"] == {".claude/skills/a/SKILL.md": 1}

    def test_drift_returns_exit_1(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Writes .agents/x and .agents/z\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {".claude/skills/a/SKILL.md": 1}}), encoding="utf-8"
        )
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_clean_repo_returns_zero(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 0

    def test_marker_stale_count_returns_exit_1(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "<!-- vendor-portability: declares .agents/state -->\n"
            "The declaration stayed but the prose moved away.\n",
            encoding="utf-8",
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text(
            json.dumps({"files": {}, "marker_files": {".claude/skills/a/SKILL.md": 1}}),
            encoding="utf-8",
        )
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1

    def test_baseline_path_traversal_is_refused(self, tmp_path: Path) -> None:
        # A --baseline argument escaping the repo root must be refused and
        # cause a config error (exit 2), not read an arbitrary file.
        root = tmp_path / "repo"
        root.mkdir()
        (root / ".claude" / "skills").mkdir(parents=True)
        traversal = Path("../../etc/passwd")
        result = cmp._resolve_baseline_path(root, traversal)
        assert result is None, "path traversal must be refused"


    def test_absolute_baseline_outside_root_is_refused(self, tmp_path: Path) -> None:

        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        result = cmp._resolve_baseline_path(root, outside)
        assert result is None, "absolute path outside root must be refused"



class TestUnexpectedScanException:
    """Unexpected parser exceptions must return exit 2, not bubble up as exit 1.

    Exit 1 means 'drift detected'. A scan-time exception is a configuration
    or tool failure, not drift, so it must return exit 2. Without the catch-all
    handler, an unexpected ValueError from markdown-it propagates as an unhandled
    exception (exit 1) and misreports a scan failure as drift.
    """

    def test_unexpected_exception_returns_exit_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        (skills / "SKILL.md").write_text("Some content.\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")

        def _exploding_scan(root: Path, *, check_drift: bool = False) -> None:
            raise RuntimeError("simulated markdown-it internal error")

        monkeypatch.setattr(cmp, "scan_all", _exploding_scan)
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2

    def test_unexpected_exception_prints_type_and_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        (skills / "SKILL.md").write_text("Some content.\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")

        def _exploding_scan(root: Path, *, check_drift: bool = False) -> None:
            raise TypeError("bad token type")

        monkeypatch.setattr(cmp, "scan_all", _exploding_scan)
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2
        err = capsys.readouterr().err
        assert "TypeError" in err
        assert "bad token type" in err


class TestCommittedRepoHasNoDrift:
    """The CI ratchet: the committed baseline must match the committed tree."""

    def test_repo_markdown_matches_baseline(self) -> None:
        root = Path(__file__).resolve().parents[2]
        if not cmp.skills_dirs(root):
            pytest.skip("no plugin root has a skills dir in this checkout")
        baseline_path = root / "scripts" / "validation" / cmp._DEFAULT_BASELINE_NAME
        current = cmp.scan_plugin_roots(root)
        baseline = cmp._load_baseline(baseline_path)
        regressions, _ = cmp.diff_against_baseline(current, baseline)
        assert regressions == [], "\n".join(regressions)

    def test_the_baseline_covers_every_scanned_root(self) -> None:
        """Guards the vacuous pass this test had while the scan was single root.

        ``diff_against_baseline`` reports a baseline entry with no current file
        as an improvement, not a regression. So a scan narrower than the
        baseline stays green while ignoring whole roots. Asserting that the
        baseline's roots are a subset of the scanned roots catches a future
        narrowing that the drift assertion alone would let through.

        Both skills dirs and extra dirs (commands/, templates/agents/) are
        included in the scan, so the assertion covers both (issue #3646).
        """
        root = Path(__file__).resolve().parents[2]
        if not cmp.skills_dirs(root):
            pytest.skip("no plugin root has a skills dir in this checkout")
        baseline_path = root / "scripts" / "validation" / cmp._DEFAULT_BASELINE_NAME
        # Skills dirs contribute the plugin root name as the recorded prefix
        skills_parent_set = {d.parent.relative_to(root).as_posix() for d in cmp.skills_dirs(root)}
        # Extra dirs are scanned directly, so any baseline key that starts with
        # one of their repo-relative paths is already covered.
        extra_dir_prefixes = {d.relative_to(root).as_posix() for d in cmp.extra_scan_dirs(root)}
        # A baseline key belongs to a scanned root if either:
        #   - its skills-subpath prefix is a known skills parent (e.g. ".claude"), OR
        #   - the key starts with an extra-scan prefix (e.g. ".claude/commands/")
        unscanned = set()
        for key in cmp._load_baseline(baseline_path):
            skills_root = key.split("/skills/", 1)[0]
            if skills_root in skills_parent_set:
                continue
            if any(_is_under_extra_scan_root(key, prefix) for prefix in extra_dir_prefixes):
                continue
            unscanned.add(key)
        assert not unscanned, f"baseline names unscanned paths: {unscanned}"


class TestBlockquoteFenceDepth:
    """A quoted fence remembers the depth it opened at, not just that it was quoted.

    Tracking only a boolean loses both directions of the question. Each case
    below was cross-checked against CommonMark via markdown-it, which is the
    arbiter for what is code and what is prose (issue #3489).
    """

    def test_deeper_marker_does_not_close_a_shallower_fence(self) -> None:
        """``>>`` inside a ``>`` fence is content, not the closing marker.

        Stripping every marker made the depth-2 line look like a bare closing
        fence, which ended the block early and exposed the following code line
        as prose. CommonMark keeps the path inside a fence token.
        """
        text = "> ```\n>> ```\n> /templates/agents/x.md\n> ```\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_dropping_below_the_opening_depth_ends_the_fence(self) -> None:
        """A fence opened at depth 2 ends when the document returns to depth 1.

        The depth-1 line has left the blockquote the fence opened in, so it is
        prose. Testing only for the presence of a marker kept the fence open and
        hid it. CommonMark puts the path in an inline token.
        """
        text = ">> ```\n>> code\n> /templates/agents/x.md\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_same_depth_marker_still_closes(self) -> None:
        """The ordinary case keeps working: a marker at the opening depth closes."""
        text = "> ```\n> code\n> ```\n> /templates/agents/x.md\n"
        assert cmp.count_upstream_refs(text) == 1


class TestAstCodeStripping:
    """Regressions locking the #3499 AST rewrite of ``_strip_code``.

    Each case was a disagreement between the old line scanner and the CommonMark
    AST over the full repo corpus. The AST verdict is correct in every one; these
    tests would fail against the old scanner and pass against the AST walk.
    """

    def test_indented_code_block_path_does_not_count(self) -> None:
        """A path inside an indented code block is code, not a runtime directive.

        The old line scanner stripped only fenced blocks, so this counted; the
        AST classifies the indented block as code and it no longer counts.
        """
        text = "Prose /templates/agents/a.md\n\n    code /templates/agents/b.md\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_fence_indented_in_nested_list_does_not_count(self) -> None:
        """A fence aligned to a nested list sits past 3-space indent.

        The old ``[ \\t]{0,3}`` fence regex missed it and counted the example
        command; the AST resolves the list-relative indent and strips it.
        """
        text = "- outer:\n  - inner:\n    ```bash\n    cp .agents/x .\n    ```\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_prose_after_nested_fence_example_counts(self) -> None:
        """A stray closing fence must not swallow real prose to end of document.

        The old scanner opened a phantom fence at the extra ``` and hid every
        later reference; the AST ends the block at the list-item boundary, so the
        following prose reference counts.
        """
        text = (
            "1. example:\n"
            "   ```markdown\n"
            "   ### H\n"
            "   ```python\n"
            "   code\n"
            "   ```\n"
            "   ```\n"
            "\n"
            "2. real: write to .agents/analysis/x.md\n"
        )
        assert cmp.count_upstream_refs(text) == 1

    def test_indented_code_drift_not_flagged_exit_zero(self, tmp_path: Path) -> None:
        """End-to-end: a reference confined to indented code is not drift.

        Under the old scanner this file counted 1 and, against an empty baseline,
        the CLI exited 1. The AST counts 0, so the CLI exits 0.
        """
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        (skills / "SKILL.md").write_text(
            "# Skill\n\nExample:\n\n    write to .agents/x.md\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 0


class TestScanAccounting:
    """Finding 3: scanned-file accounting is separate from offending counts.

    A zero-file scan (empty tree, mistargeted root, unreadable dir) must not
    read as a healthy scan that simply found no offenders. The success line and
    JSON must report files SCANNED, not the offending count.
    """

    def _skill_md(self, root: Path, rel: str, body: str) -> None:
        path = root / ".claude" / "skills" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    def test_scanned_counts_every_md_not_only_offenders(self, tmp_path: Path) -> None:
        # Three .md files, one offends. scanned must be 3; counts must hold 1.
        self._skill_md(tmp_path, "a/SKILL.md", "Writes .agents/x\n")
        self._skill_md(tmp_path, "b/references/b.md", "Clean prose.\n")
        self._skill_md(tmp_path, "c/notes.md", "Also clean.\n")
        skills_dir = tmp_path / ".claude" / "skills"
        scan = cmp.scan_skill_markdown(skills_dir)
        assert scan.scanned == 3
        assert scan.counts == {"skills/a/SKILL.md": 1}

    def test_zero_md_scan_refused_exit_2(self, tmp_path: Path) -> None:
        # Skills dir exists but holds no .md. Refuse (exit 2), do not report clean.
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "notes.txt").write_text("not markdown\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2

    def test_zero_md_scan_refused_before_writing_baseline(self, tmp_path: Path) -> None:
        # An empty scan must not silently write an empty baseline either: the
        # refusal precedes the --update-baseline branch.
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "notes.txt").write_text("not markdown\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(baseline),
                "--update-baseline",
            ]
        )
        assert rc == 2
        assert not baseline.exists()

    def test_success_line_reports_scanned_not_offending(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Two clean files: success output names the scanned roots.
        self._skill_md(tmp_path, "a/SKILL.md", "Clean prose.\n")
        self._skill_md(tmp_path, "b/SKILL.md", "Also clean.\n")
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        out = capsys.readouterr().out
        assert rc == 0
        assert "No Markdown vendor-portability drift" in out
        assert ".claude/skills" in out

    def test_json_output_includes_files_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._skill_md(tmp_path, "a/SKILL.md", "Clean prose.\n")
        self._skill_md(tmp_path, "b/SKILL.md", "Also clean.\n")
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(baseline),
                "--output-format",
                "json",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["regressions"] == []
        assert payload["current_total"] == 0


class TestBaselineSemanticConflictGuard:
    """Issue #4195: a checked-in baseline is bound to its generated tree."""

    def _init_repo(self, root: Path) -> None:
        (root / ".claude" / "skills" / "a").mkdir(parents=True)
        (root / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        for required in cmp.REQUIRED_EXTRA_ROOTS:
            (root / required).mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
        (root / "scripts" / "validation").mkdir(parents=True)
        (root / "scripts" / "validation" / "check_skill_md_portability.py").write_text(
            "# scanner\n", encoding="utf-8"
        )
        # Create a stub for the upstream path that marker tests reference
        (root / ".agents" / "state").mkdir(parents=True)
        baseline = root / "baseline.json"
        baseline.write_text(json.dumps({"files": {}, "marker_files": {}}), encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)

    def test_new_marker_declaration_alongside_baseline_is_allowed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The documented opt-out flow must be reachable in one commit (issue #4300).

        ``validate-vendor-portability.yml`` tells an author to add a
        ``vendor-portability`` marker and then run ``--update-baseline``. Under
        the original blanket refusal that pair was rejected whenever
        ``--base-ref`` was set, so following the documented remedy turned CI
        red. Marker drift is still caught exactly against the on-disk baseline,
        and the same check runs again on ``main`` after the merge.
        """
        self._init_repo(tmp_path)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "<!-- vendor-portability: declares .agents/state -->\nUses .agents/state.\n",
            encoding="utf-8",
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {"files": {}, "marker_files": {".claude/skills/a/SKILL.md": 1}}
            ),
            encoding="utf-8",
        )

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                "HEAD",
            ]
        )

        assert rc == 0
        assert "Semantic baseline conflict" not in capsys.readouterr().out

    def test_stale_marker_declaration_baseline_still_fails(
        self, tmp_path: Path
    ) -> None:
        """A stale baseline that does not match the current scan still fails."""
        self._init_repo(tmp_path)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "<!-- vendor-portability: declares .agents/state -->\nUses .agents/state.\n",
            encoding="utf-8",
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps({"files": {}, "marker_files": {}}),
            encoding="utf-8",
        )

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                "HEAD",
            ]
        )

        assert rc == 1

    def test_undeclared_refs_added_alongside_baseline_still_fail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The guard's real target: a branch-local regeneration hiding new debt."""
        self._init_repo(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path, capture_output=True, text=True, check=True,
        ).stdout.strip()
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Uses .agents/state.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {"files": {".claude/skills/a/SKILL.md": 1}, "marker_files": {}}
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "add debt"], cwd=tmp_path, check=True)

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                base_sha,
            ]
        )

        assert rc == 1

    def test_baseline_only_change_does_not_trigger_semantic_conflict(
        self, tmp_path: Path
    ) -> None:
        """A baseline-only remediation against current main remains allowed."""
        self._init_repo(tmp_path)
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {
                    "_comment": "refreshed wording only",
                    "files": {},
                    "marker_files": {},
                }
            ),
            encoding="utf-8",
        )

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                "HEAD",
            ]
        )

        assert rc == 0

    def test_baseline_matches_scan_suppresses_conflict(
        self, tmp_path: Path
    ) -> None:
        """Baseline regenerated after merge exits 0 when it matches current scan.

        This is the fix for issue #4300: when a skill file and the baseline both
        changed from base-ref BUT the baseline on disk already reflects the
        current scan, the guard should not fire. The regeneration happened
        correctly post-merge.
        """
        self._init_repo(tmp_path)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "<!-- vendor-portability: declares .agents/state -->\nUses .agents/state.\n",
            encoding="utf-8",
        )
        # Baseline correctly reflects the current scan (1 marker for a/SKILL.md).
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {"files": {}, "marker_files": {".claude/skills/a/SKILL.md": 1}}
            ),
            encoding="utf-8",
        )

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                "HEAD",
            ]
        )

        assert rc == 0

    def test_baseline_and_counter_code_cochange_skips_guard(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Scanner script + baseline co-change: guard is skipped (bootstrapping case).

        When the scanner script itself changes (e.g. to extend EXTRA_SCAN_ROOTS),
        the baseline MUST be regenerated to match the new scope. The semantic
        conflict guard cannot distinguish a correct co-regen from an accidental
        one in this case, so it defers to the user. Issue #4195.
        """
        self._init_repo(tmp_path)
        (tmp_path / "scripts" / "validation" / "check_skill_md_portability.py").write_text(
            "# scanner semantics changed\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps({"_comment": "regenerated", "files": {}, "marker_files": {}}),
            encoding="utf-8",
        )

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                "HEAD",
            ]
        )

        assert rc == 0

    def test_bad_base_ref_fails_closed_as_config_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative: an explicit but unreadable base ref cannot skip the guard."""
        self._init_repo(tmp_path)

        rc = cmp.main(
            [
                "--repo-root",
                str(tmp_path),
                "--baseline",
                str(tmp_path / "baseline.json"),
                "--base-ref",
                "missing-ref",
            ]
        )

        assert rc == 2
        err = capsys.readouterr().err
        assert "Could not compare against --base-ref missing-ref" in err

    def test_future_plugin_skill_root_counts_as_measured_input(self) -> None:
        """Edge: the co-change guard stays aligned with PLUGIN_ROOTS."""
        assert cmp._is_measured_input("src/claude/skills/example/SKILL.md") is True

    def test_extra_scan_root_counts_as_measured_input(self) -> None:
        """The co-change guard must cover EXTRA_SCAN_ROOTS, not only PLUGIN_ROOTS.

        AI-Spec-Validation review on PR #5284 found this gap: scan_all() folds
        EXTRA_SCAN_ROOTS (.claude/commands, templates/agents,
        src/copilot-cli/instructions) into the same baseline as the plugin
        skills/ trees, but _is_measured_input() only recognized the latter, so
        a co-change to an instructions mirror plus the baseline in one commit
        was invisible to the --base-ref semantic-conflict guard.
        """
        assert (
            cmp._is_measured_input(
                "src/copilot-cli/instructions/example.instructions.md"
            )
            is True
        )
        assert cmp._is_measured_input(".claude/commands/example.md") is True
        assert cmp._is_measured_input("templates/agents/example.shared.md") is True

    def test_non_md_file_under_extra_scan_root_is_not_measured_input(self) -> None:
        """Negative: only Markdown files feed this scanner's counts."""
        assert (
            cmp._is_measured_input("src/copilot-cli/instructions/example.json")
            is False
        )

    def _init_repo_with_debt(self, root: Path) -> None:
        """Seed a committed tree carrying one unsuppressed ref and a matching baseline."""
        self._init_repo(root)
        (root / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Uses .agents/state.\n", encoding="utf-8"
        )
        (root / "baseline.json").write_text(
            json.dumps(
                {"files": {".claude/skills/a/SKILL.md": 1}, "marker_files": {}}
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "debt"], cwd=root, check=True)

    def _run(self, root: Path, base_ref: str) -> int:
        return cmp.main(
            [
                "--repo-root",
                str(root),
                "--baseline",
                str(root / "baseline.json"),
                "--base-ref",
                base_ref,
            ]
        )

    def test_lowered_baseline_alongside_md_change_is_allowed(
        self, tmp_path: Path
    ) -> None:
        """Issue #4300: paying debt down must not read as a semantic conflict.

        Before this, the guard refused every baseline plus measured-input
        co-change, which a main merge always produces, so the branch could
        never be made green.
        """
        self._init_repo_with_debt(tmp_path)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps({"files": {}, "marker_files": {}}), encoding="utf-8"
        )

        assert self._run(tmp_path, "HEAD") == 0

    def test_raised_count_is_caught_even_when_baseline_is_regenerated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative: the ratchet reads base_ref from git, so regenerating cannot launder it.

        This is the property the old blanket refusal was protecting. The
        working-tree baseline agrees with the scan and would report zero
        regressions on its own.
        """
        self._init_repo_with_debt(tmp_path)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path, capture_output=True, text=True, check=True,
        ).stdout.strip()
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Files: .agents/a, .agents/b, .claude/review-axes/c.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {"files": {".claude/skills/a/SKILL.md": 3}, "marker_files": {}}
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "raise count"], cwd=tmp_path, check=True)

        rc = self._run(tmp_path, base_sha)

        assert rc == 1
        out = capsys.readouterr().out
        assert "Counts rose above the baseline recorded at" in out
        assert ".claude/skills/a/SKILL.md" in out

    def test_instructions_mirror_raised_count_is_caught(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Same guard as the plugin-skills case, but for an EXTRA_SCAN_ROOTS file.

        Before _is_measured_input() covered EXTRA_SCAN_ROOTS, this exact
        co-change (new undeclared refs under src/copilot-cli/instructions/
        plus a baseline update, in one commit) would slip past --base-ref: the
        guard would not have recognized the changed file as measured input at
        all, so it read as an unrelated, allowed co-change.
        """
        self._init_repo(tmp_path)
        instructions_file = (
            tmp_path / "src" / "copilot-cli" / "instructions" / "example.instructions.md"
        )
        instructions_file.write_text("Uses .agents/state.\n", encoding="utf-8")
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {
                    "files": {
                        "src/copilot-cli/instructions/example.instructions.md": 1
                    },
                    "marker_files": {},
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "instructions debt"], cwd=tmp_path, check=True)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path, capture_output=True, text=True, check=True,
        ).stdout.strip()

        instructions_file.write_text(
            "Files: .agents/a, .agents/b, .claude/review-axes/c.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {
                    "files": {
                        "src/copilot-cli/instructions/example.instructions.md": 3
                    },
                    "marker_files": {},
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "raise instructions count"],
            cwd=tmp_path,
            check=True,
        )

        rc = self._run(tmp_path, base_sha)

        assert rc == 1
        out = capsys.readouterr().out
        assert "Counts rose above the baseline recorded at" in out
        assert "src/copilot-cli/instructions/example.instructions.md" in out

    def test_baseline_absent_at_base_ref_fails_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: with no recorded numbers there is nothing to ratchet against."""
        self._init_repo_with_debt(tmp_path)
        subprocess.run(["git", "rm", "-q", "baseline.json"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "drop baseline"], cwd=tmp_path, check=True
        )
        base_ref = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.strip()
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps({"files": {}, "marker_files": {}}), encoding="utf-8"
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "branch changes"], cwd=tmp_path, check=True)

        rc = self._run(tmp_path, base_ref)

        assert rc == 1
        assert "Semantic baseline conflict" in capsys.readouterr().out

    def test_unparsable_baseline_at_base_ref_fails_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: a corrupt recorded baseline must not be read as permission."""
        self._init_repo_with_debt(tmp_path)
        (tmp_path / "baseline.json").write_text("{not json", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "corrupt"], cwd=tmp_path, check=True)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=tmp_path, capture_output=True, text=True, check=True,
        ).stdout.strip()
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps({"files": {}, "marker_files": {}}), encoding="utf-8"
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "branch changes"], cwd=tmp_path, check=True)

        rc = self._run(tmp_path, base_sha)

        assert rc == 1
        assert "Semantic baseline conflict" in capsys.readouterr().out

    def test_a_baseline_outside_the_repo_says_so_instead_of_failing_mutely(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Edge: the one fail-closed path that used to return None in silence.

        Every other way ``_baseline_payload_at_ref`` gives up names the reason
        on stderr. A baseline resolving outside the repository root did not, so
        the guard reported nothing and the caller only saw a missing ratchet.
        """
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "elsewhere" / "baseline.json"

        assert cmp._baseline_payload_at_ref(root, "HEAD", outside) is None

        err = capsys.readouterr().err
        assert str(outside) in err
        assert str(root) in err
        assert "outside the repository root" in err

    def test_a_baseline_inside_the_repo_is_not_blamed_on_its_location(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Negative control: an in-tree baseline fails for its own reason.

        Without this, the assertions above pass for a build that prints the
        outside-the-root complaint on every failure.
        """
        self._init_repo(tmp_path)
        missing = tmp_path / "no-such-baseline.json"

        assert cmp._baseline_payload_at_ref(tmp_path, "HEAD", missing) is None

        err = capsys.readouterr().err
        assert "outside the repository root" not in err
        assert "no-such-baseline.json" in err

    def test_new_marker_declaration_is_allowed_against_base_ref(
        self, tmp_path: Path
    ) -> None:
        """Edge: markers are declarations, so base_ref has nothing to ratchet.

        A file added on the branch has no ``base_ref`` entry. Ratcheting the
        marker section here would reject the sanctioned opt-out flow outright.
        """
        self._init_repo_with_debt(tmp_path)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
        new_skill = tmp_path / ".claude" / "skills" / "b" / "SKILL.md"
        new_skill.parent.mkdir(parents=True, exist_ok=True)
        new_skill.write_text(
            "<!-- vendor-portability: declares .agents/state -->\nUses .agents/state.\n",
            encoding="utf-8",
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {"files": {}, "marker_files": {".claude/skills/b/SKILL.md": 1}}
            ),
            encoding="utf-8",
        )

        assert self._run(tmp_path, "HEAD") == 0

    def test_marker_decrease_alongside_md_change_is_allowed(
        self, tmp_path: Path
    ) -> None:
        """Edge: exact-count marker drift is on-disk semantics, not the base_ref ratchet."""
        self._init_repo(tmp_path)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "<!-- vendor-portability: declares .agents/state -->\nUses .agents/state.\n",
            encoding="utf-8",
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps(
                {"files": {}, "marker_files": {".claude/skills/a/SKILL.md": 1}}
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "marker"], cwd=tmp_path, check=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Clean prose.\n", encoding="utf-8"
        )
        (tmp_path / "baseline.json").write_text(
            json.dumps({"files": {}, "marker_files": {}}), encoding="utf-8"
        )

        assert self._run(tmp_path, "HEAD") == 0


class TestTraversalErrorsSurface:
    """Finding 3: traversal errors must fail closed, not be swallowed.

    ``Path.rglob`` walks past a permission error on a subdirectory, so a partial
    scan reads as clean; ``os.walk`` with a re-raising ``onerror`` refuses. A
    broken ``.md`` symlink is a configuration error, not a file to drop.
    """

    def _skill_md(self, root: Path, rel: str, body: str) -> None:
        path = root / ".claude" / "skills" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    def test_broken_md_symlink_raises(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        (skills / "dangling.md").symlink_to(skills / "gone.md")
        with pytest.raises(OSError, match="Broken .md symlink"):
            cmp.scan_skill_markdown(tmp_path / ".claude" / "skills")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    def test_broken_md_symlink_makes_cli_exit_2(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        (skills / "dangling.md").symlink_to(skills / "gone.md")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    def test_dangling_directory_symlink_outside_root_raises(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        (skills / "escape-dir").symlink_to(
            tmp_path.parent / "outside-dir" / "gone",
            target_is_directory=True,
        )
        with pytest.raises(OSError, match="outside the repository root"):
            cmp.scan_skill_markdown(tmp_path / ".claude" / "skills")

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require privileges on Windows",
    )
    def test_dangling_directory_symlink_outside_root_makes_cli_exit_2(
        self, tmp_path: Path
    ) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        (skills / "escape-dir").symlink_to(
            tmp_path.parent / "outside-dir" / "gone",
            target_is_directory=True,
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2

    @pytest.mark.skipif(
        getattr(os, "geteuid", lambda: -1)() == 0,
        reason="chmod-based permission denial is a no-op for root (web containers)",
    )
    def test_unreadable_subdir_raises(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        locked = tmp_path / ".claude" / "skills" / "locked"
        locked.mkdir()
        (locked / "SKILL.md").write_text("Writes .agents/x\n", encoding="utf-8")
        locked.chmod(0o000)
        try:
            with pytest.raises(OSError):
                cmp.scan_skill_markdown(tmp_path / ".claude" / "skills")
        finally:
            locked.chmod(0o755)

    @pytest.mark.skipif(
        getattr(os, "geteuid", lambda: -1)() == 0,
        reason="chmod-based permission denial is a no-op for root (web containers)",
    )
    def test_unreadable_subdir_makes_cli_exit_2(self, tmp_path: Path) -> None:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (skills / "SKILL.md").write_text("Clean prose.\n", encoding="utf-8")
        locked = tmp_path / ".claude" / "skills" / "locked"
        locked.mkdir()
        (locked / "SKILL.md").write_text("Writes .agents/x\n", encoding="utf-8")
        locked.chmod(0o000)
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        try:
            rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        finally:
            locked.chmod(0o755)
        assert rc == 2


class TestNestingExhaustionGate:
    """Finding 1: parser nesting exhaustion is a gate bypass and must fail closed.

    At ``maxNesting`` (20) markdown-it stops emitting fence tokens, so a
    ``vendor-portability`` marker fenced that deep would leak and suppress a
    genuine violation. End-to-end, the validator must refuse (exit 2) rather
    than silently pass (exit 0).
    """

    @staticmethod
    def _nested_fence(depth: int) -> str:
        quote = ">" * depth + " "
        return (
            quote
            + "```\n"
            + quote
            + "<!-- vendor-portability: example -->\n"
            + quote
            + "```\n"
            + "Ref .agents/analysis/foo.md.\n"
        )

    def _write_skill(self, tmp_path: Path, body: str) -> Path:
        skills = tmp_path / ".claude" / "skills" / "a"
        skills.mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "skills").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
        (skills / "SKILL.md").write_text(body, encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"files": {}}), encoding="utf-8")
        return baseline

    def test_depth_20_fenced_marker_refused_exit_2(self, tmp_path: Path) -> None:
        # The fence vanishes at depth 20, so the marker would leak and zero the
        # file. The gate must refuse the un-scannable file, not pass it.
        baseline = self._write_skill(tmp_path, self._nested_fence(20))
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 2

    def test_depth_19_control_flags_drift_exit_1(self, tmp_path: Path) -> None:
        # Depth 19 is fully represented: the fence is stripped, the marker is
        # blanked, and the genuine prose ref counts as drift against an empty
        # baseline. This proves the refusal at depth 20 is the nesting limit, not
        # the reference itself.
        baseline = self._write_skill(tmp_path, self._nested_fence(19))
        rc = cmp.main(["--repo-root", str(tmp_path), "--baseline", str(baseline)])
        assert rc == 1


class TestScriptsPathDetection:
    """Prose reference detection for scripts/ paths (issue #4013).

    The scripts/ tree exists only in the upstream checkout; neither plugin root
    ships it. A skill that instructs the agent to open or run scripts/x.py will
    fail silently in every consumer install.
    """

    def test_counts_scripts_inline_code_ref(self) -> None:
        """An inline-code scripts/ reference is counted as an upstream ref.

        Isolating negative control: removing the scripts[\\/] pattern from
        UPSTREAM_PATTERNS causes count_upstream_refs to return 0, failing this
        assertion. The text contains no .agents/, .claude/lib/, templates/, or
        other upstream prefix, so only the scripts/ component triggers it.
        """
        text = "Run `scripts/validation/check_vendor_portability.py` to validate.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_counts_scripts_bare_prose_ref(self) -> None:
        """A bare prose scripts/ reference (no backticks) is also counted."""
        text = "Edit scripts/validation/pre_pr.py before running.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_ignores_scripts_in_fenced_code_block(self) -> None:
        """A scripts/ path inside a fenced code block is stripped before counting.

        Fenced blocks document example invocations; they do not represent prose
        instructions to the agent.
        """
        text = "```bash\npython3 scripts/validation/pre_pr.py\n```\n"
        assert cmp.count_upstream_refs(text) == 0

    def test_counts_build_scripts_prose_ref(self) -> None:
        """A build/scripts reference is counted as an upstream ref."""
        text = "Generated by `build/scripts/generate_rules.py`.\n"
        assert cmp.count_upstream_refs(text) == 1

    def test_ignores_plain_word_scripts_without_separator(self) -> None:
        """The bare English word "scripts" without a trailing slash is not counted.

        The pattern requires scripts[\\/] (a path separator after the word), so
        prose like "the scripts are located here" does not count as an upstream
        path reference.
        """
        text = "The scripts are maintained by the team.\n"
        assert cmp.count_upstream_refs(text) == 0


# ---------------------------------------------------------------------------
# Marker path-drift tests (issue #4116)
