# taste-lint: ignore file-size
"""Tests for which text the routing gate treats as a route.

A route counts only inside a table cell the CommonMark parser actually
recognises. These cases pin that boundary in both directions:

- suppression: fenced blocks (nested, longer, and tilde fences), HTML comments
  (terminated and not), indented code, and inline code spans hold no routes,
  and neither does pipe-shaped prose without a delimiter row
- detection: tables written without outer pipes, inside a blockquote, or
  indented under a list item are scanned, and emphasis does not hide a route

Every fixture here carries a ``| --- | --- |`` delimiter row on purpose. An
earlier revision omitted it, so the content rendered as a paragraph rather than
a table and each suppression test passed whether or not the defence it named
existed. A mutation battery surfaced eight such tests.

Enforcement of the invariant itself lives in
test_check_shipped_skill_routes.py.

File-size suppression rationale: this module is already the markdown half of
one split, and the tests are a flat list of independent functions with no
shared state, so a reader greps for a behaviour rather than navigating
structure. Splitting again would put the code-span tests in a different file
from the punctuation tests that share their fixtures and their failure mode,
and would leave nobody with a single place to answer "how does the gate read
markdown". Forty-nine tracked test files in this repository exceed the same
limit, the largest by a factor of eighteen. Revisit if the file grows a second
concern rather than more cases of this one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.shipped_skill_routes_helpers import (
    EXIT_DRIFT,
    EXIT_OK,
    repo,
    run_gate,
    write_doc,
    write_skill,
)

__all__ = ["repo"]


def test_fenced_block_is_ignored(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "```markdown\n| Task | Route |\n| --- | --- |\n| X | Skill: ghost |\n```\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_longer_outer_fence_is_not_closed_by_a_shorter_inner_one(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "````markdown\n```\n| X | R |\n| --- | --- |\n| X | Skill: ghost |\n```\n````\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_tilde_fence_is_not_closed_by_backticks(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "~~~\n```\n| X | R |\n| --- | --- |\n| X | Skill: ghost |\n~~~\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_html_comment_is_ignored(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "<!--\n| X | R |\n| --- | --- |\n| X | Skill: ghost |\n-->\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_line_numbers_are_reported_after_an_html_comment(repo: Path) -> None:
    write_skill(
        repo,
        "src/copilot-cli",
        "autoplan",
        "# autoplan\n<!--\nfiller\nfiller\n-->\n\n| X | R |\n| --- | --- |\n| X | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "SKILL.md:9:" in result.stdout


def test_indented_code_block_is_ignored(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "text\n\n    | X | R |\n    | --- | --- |\n    | X | Skill: ghost |\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_inline_code_span_is_ignored(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "| X | R |\n| --- | --- |\n| X | route with `Skill: ghost` shown |\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_prose_outside_a_table_is_ignored(repo: Path) -> None:
    """Heading text such as `# Skill: API Documentation Generator` is not a route."""
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "# Skill: API Documentation Generator\n\n- [ ] Skill: create a test file\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_compound_word_is_not_a_route(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "guide.md",
        "| X | R |\n| --- | --- |\n| X | MetaSkill: ghost |\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_blockquoted_table_row_is_scanned(repo: Path) -> None:
    """A table inside a blockquote still routes readers."""
    write_doc(
        repo,
        "src/copilot-cli",
        "quoted.md",
        "> | M | R |\n> | --- | --- |\n> | Merge | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


def test_blockquote_support_does_not_readmit_indented_code(repo: Path) -> None:
    """Guard the indent bound that blockquote support could have relaxed away.

    Both shapes are here on purpose. An earlier fixture carried only the
    top-level indent, so it never exercised the blockquote path its own name
    claims and would have passed with blockquote handling removed entirely.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "indented.md",
        "    | Merge | R |\n    | --- | --- |\n    | Merge | Skill: ghost |\n"
        "\n>     | M | R |\n>     | --- | --- |\n>     | M | Skill: ghost |\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_unterminated_html_comment_does_not_fail_the_build(repo: Path) -> None:
    """An unterminated comment hides its content from every reader.

    Matching ``<!--.*?-->`` over the whole document found nothing here, so the
    commented-out route was scanned as live and failed the build on text
    nobody sees. A false positive in a push-blocking gate is worse than a miss.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "open.md",
        "<!-- draft\n| Merge | R |\n| --- | --- |\n| Merge | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_quoted_comment_markers_do_not_hide_a_table(repo: Path) -> None:
    """Documenting the comment syntax must not blank out the table between."""
    write_doc(
        repo,
        "src/copilot-cli",
        "syntax.md",
        "`<!--`\n\n| M | R |\n| --- | --- |\n| Merge | Skill: ghost |\n\n`-->`\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


def test_table_without_outer_pipes_is_scanned(repo: Path) -> None:
    """GFM outer pipes are optional; a pipe-shaped-line scanner missed this."""
    write_doc(repo, "src/copilot-cli", "bare.md", "I | R\n--- | ---\nM | Skill: ghost\n")
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


def test_table_indented_under_a_list_item_is_scanned(repo: Path) -> None:
    """Four spaces inside a list is continuation, not an indented code block."""
    write_doc(
        repo,
        "src/copilot-cli",
        "listed.md",
        "1. Routes:\n\n    | I | R |\n    | --- | --- |\n    | M | Skill: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "ghost" in result.stdout


def test_pipe_shaped_paragraph_is_not_a_table(repo: Path) -> None:
    """Without a delimiter row markdown renders a paragraph, so it routes nobody.

    The original fixtures in this suite omitted the delimiter row and asserted
    the gate treated them as routes, encoding a model markdown does not have.
    """
    write_doc(repo, "src/copilot-cli", "prose.md", "| I | R |\n| M | Skill: ghost |\n")
    assert run_gate(repo).returncode == EXIT_OK


def test_emphasised_route_is_scanned(repo: Path) -> None:
    write_doc(
        repo,
        "src/copilot-cli",
        "bold.md",
        "| I | R |\n| --- | --- |\n| M | **Skill: ghost** |\n",
    )
    assert run_gate(repo).returncode == EXIT_DRIFT


def test_invalid_fence_does_not_hide_a_table(repo: Path) -> None:
    """```lang`bad is not a CommonMark fence; the parser knows, a regex did not."""
    write_doc(
        repo,
        "src/copilot-cli",
        "badfence.md",
        "```lang`bad\n\n| I | R |\n| --- | --- |\n| M | Skill: ghost |\n",
    )
    assert run_gate(repo).returncode == EXIT_DRIFT


def test_malformed_name_is_reported_not_prefix_matched(repo: Path) -> None:
    """Capturing to the first illegal character would resolve a bogus route."""
    write_doc(
        repo,
        "src/copilot-cli",
        "slash.md",
        "| I | R |\n| --- | --- |\n| M | Skill: merge-resolver/ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT
    assert "not a legal skill name" in result.stdout


def test_several_routes_in_one_cell_resolve(repo: Path) -> None:
    """The live tables list skills comma-separated, so punctuation must strip."""
    write_skill(repo, "src/copilot-cli", "github")
    write_doc(
        repo,
        "src/copilot-cli",
        "list.md",
        "| I | R |\n| --- | --- |\n| M | Skill: github, Skill: merge-resolver. |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_entity_encoded_keyword_is_still_a_route(repo: Path) -> None:
    """``Sk&#105;ll:`` renders as a route, so the scan must see it.

    A source-text prefilter that required the literal keyword skipped this
    file entirely and reported a pass. Rendering is what consumers read, so
    rendering is what the gate has to check.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "entity.md",
        "| I | R |\n| --- | --- |\n| M | Sk&#105;ll: ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost" in result.stdout


def test_code_styled_name_is_a_route(repo: Path) -> None:
    """``Skill: `name`` is a route whose name happens to be styled."""
    write_doc(
        repo,
        "src/copilot-cli",
        "styled.md",
        "| I | R |\n| --- | --- |\n| M | Skill: `ghost` |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost" in result.stdout


def test_code_styled_name_that_resolves_does_not_block(repo: Path) -> None:
    """The same shape must not be reported malformed when the skill ships.

    Dropping every code span turned this natural documentation form into a
    push-blocking malformed-name report.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "styled-ok.md",
        "| I | R |\n| --- | --- |\n| M | Skill: `merge-resolver` |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_quoted_and_bracketed_routes_resolve(repo: Path) -> None:
    """Quotation and bracket punctuation is not part of the name."""
    write_doc(
        repo,
        "src/copilot-cli",
        "quoted.md",
        '| I | R |\n| --- | --- |\n| M | "Skill: merge-resolver" |\n'
        "| M | [Skill: merge-resolver] |\n"
        "| M | {Skill: merge-resolver} |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_compound_separator_before_keyword_is_not_a_route(repo: Path) -> None:
    """``Meta-Skill:`` and ``Task/Skill:`` are prose the live tree already uses."""
    write_doc(
        repo,
        "src/copilot-cli",
        "compound.md",
        "| I | R |\n| --- | --- |\n| M | Meta-Skill: ghost |\n"
        "| M | Task/Skill: 10+ delegations |\n"
        "| M | docs\\Skill: ghost |\n"
        "| M | Skill: merge-resolver |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_skillforge_name_survives_code_styling(repo: Path) -> None:
    """A code span is only blanked when it carries a whole route.

    ``Skill: `SkillForge`` contains the keyword but not a route, so blanking
    on the bare keyword would have turned a live route into a malformed name.
    """
    write_skill(repo, "src/copilot-cli", "SkillForge")
    write_doc(
        repo,
        "src/copilot-cli",
        "forge.md",
        "| I | R |\n| --- | --- |\n| M | Skill: `SkillForge` |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_route_with_no_name_is_reported(repo: Path) -> None:
    """``Skill:`` with nothing after it is an unfinished route, not prose.

    Dropping the empty capture was proposed to protect prose such as
    "Select a Skill:". No table cell in the repository has that shape (0 of
    97 files that mention the keyword), so the silent hole would cost more
    than the hypothetical false positive.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "empty.md",
        "| I | R |\n| --- | --- |\n| M | Skill: |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "not a legal skill name" in result.stdout


def test_a_code_span_holding_only_the_keyword_does_not_hide_the_route(repo: Path) -> None:
    """`Skill:` styles the label of a real route whose name sits outside it.

    Blanking a span the route pattern merely touches deleted the keyword and
    the route vanished, which is the fail-open direction. A span is treated
    as syntax documentation only when it carries a name as well.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "prefix.md",
        "| I | R |\n| --- | --- |\n| M | `Skill:` ghost |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost" in result.stdout


def test_a_code_span_holding_only_the_keyword_still_resolves(repo: Path) -> None:
    """The same shape with a real name must pass, not merely fail differently."""
    write_doc(
        repo,
        "src/copilot-cli",
        "prefix-ok.md",
        "| I | R |\n| --- | --- |\n| M | `Skill:` autoplan |\n",
    )
    assert run_gate(repo).returncode == EXIT_OK


def test_a_code_span_holding_only_the_keyword_alone_is_documentation(
    repo: Path,
) -> None:
    """`Skill:` with nothing after it documents the keyword, it is not a route.

    Keeping every bare-keyword span so the two tests above could pass made a
    cell that only shows the keyword report as an empty malformed name, which
    blocks the push over prose. What follows the span in the cell is what
    separates the two, so the decision needs cell context, not just the span.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "keyword-only.md",
        "| I | R |\n| --- | --- |\n| M | `Skill:` |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_a_code_span_holding_only_the_keyword_reads_across_later_spans(
    repo: Path,
) -> None:
    """The name after the keyword counts whether or not it is itself styled.

    Looking only at plain text after the span would read ``Skill:`` ``ghost``
    as a bare keyword and pass, which is the fail-open direction.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "keyword-split.md",
        "| I | R |\n| --- | --- |\n| M | `Skill:` `ghost` |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost" in result.stdout


@pytest.mark.parametrize(
    ("label", "tail", "expected"),
    [
        ("resolves", "autoplan", EXIT_OK),
        ("drift", "ghost", EXIT_DRIFT),
        ("prose", "see the syntax above", EXIT_DRIFT),
    ],
)
def test_backticking_the_keyword_never_changes_the_verdict(
    repo: Path, label: str, tail: str, expected: int
) -> None:
    """A code span on the keyword must not decide what follows it.

    If it did, an author could silence a drift report by typing two backticks,
    which is a fail-open escape hatch made of punctuation. The third case is
    the uncomfortable one: prose after a bare keyword is indistinguishable
    from a misspelled target, and both forms report it. That is the
    fail-closed default, and the workaround is to put the whole example inside
    the span.
    """
    for prefix, name in (("Skill:", "plain"), ("`Skill:`", "spanned")):
        path = write_doc(
            repo,
            "src/copilot-cli",
            f"paired-{label}-{name}.md",
            f"| I | R |\n| --- | --- |\n| M | {prefix} {tail} |\n",
        )
        result = run_gate(repo)
        path.unlink()
        assert result.returncode == expected, (
            f"{name} form diverged: " + result.stdout + result.stderr
        )


@pytest.mark.parametrize(
    ("label", "wrapped"),
    [
        ("paren", "(autoplan)"),
        ("double", '"autoplan"'),
        ("bracket", "[autoplan]"),
        ("single", "'autoplan'"),
        ("brace", "{autoplan}"),
        ("curly", "“autoplan”"),
    ],
)
def test_punctuation_wrapping_a_name_does_not_block_the_push(
    repo: Path, label: str, wrapped: str
) -> None:
    """Only the right end was stripped, so a parenthesised route read malformed."""
    write_doc(
        repo,
        "src/copilot-cli",
        f"wrap-{label}.md",
        f"| I | R |\n| --- | --- |\n| M | Skill: {wrapped} |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_stripping_wrapping_punctuation_does_not_mask_drift(repo: Path) -> None:
    """The strip must not turn a dangling route into a resolvable one."""
    write_doc(
        repo,
        "src/copilot-cli",
        "wrap-drift.md",
        "| I | R |\n| --- | --- |\n| M | Skill: (ghost) |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost" in result.stdout


@pytest.mark.parametrize(
    ("label", "name"),
    [
        ("doubled-paren", "((autoplan"),
        ("opener-only", "(autoplan"),
        ("open-quote", '"autoplan'),
        ("all-openers", "((("),
    ],
)
def test_an_unmatched_opening_wrapper_is_malformed(
    repo: Path, label: str, name: str
) -> None:
    """Unwrapping must be balanced or it invents a legal name from a broken one.

    Stripping any leading bracket unconditionally made ``Skill: ((autoplan``
    resolve to an installed skill and pass. That is the fail-open direction:
    text nobody wrote deliberately reported as a healthy route, so a real
    typo next to a bracket would never be seen.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        f"unbalanced-{label}.md",
        f"| I | R |\n| --- | --- |\n| M | Skill: {name} |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr


def test_a_wrapper_closed_by_a_sentence_reduces_fully(repo: Path) -> None:
    """``Skill: (autoplan).`` needs both rules, alternating, to resolve.

    The trailing period hides the closing bracket from the balance test, so a
    single pass of either rule alone leaves a name that is not legal.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "wrap-sentence.md",
        "| I | R |\n| --- | --- |\n| M | Skill: (autoplan). |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_a_closing_bracket_alone_is_still_stripped(repo: Path) -> None:
    """``[Skill: autoplan]`` puts only the closer inside the captured name.

    Requiring balance for the closing half too would report every link-wrapped
    route as malformed.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "wrap-closer.md",
        "| I | R |\n| --- | --- |\n| M | [Skill: autoplan] |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_OK, result.stdout + result.stderr


def test_raw_html_code_is_read_as_a_route(repo: Path) -> None:
    """Documents the known limitation rather than asserting it is desirable.

    ``<code>Skill: x</code>`` is not a code_inline token, so the syntax-span
    exemption does not apply to it and the route is read. That is the
    fail-closed direction: a documentation example reads as drift rather than
    a real route going unchecked. Measured across the three plugin roots, no
    table cell contains a <code> tag, and the workaround is one backtick.
    Teaching the shared parser to track HTML token depth would add a
    fail-open path to a module several gates depend on.
    """
    write_doc(
        repo,
        "src/copilot-cli",
        "rawhtml.md",
        "| I | R |\n| --- | --- |\n| M | <code>Skill: ghost</code> |\n",
    )
    result = run_gate(repo)
    assert result.returncode == EXIT_DRIFT, result.stdout + result.stderr
    assert "ghost" in result.stdout
