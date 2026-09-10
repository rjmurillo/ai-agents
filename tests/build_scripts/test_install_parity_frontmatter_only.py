"""Frontmatter-only diffs in validate_install_parity.py (Issue #4922).

``_split_document`` deliberately drops YAML frontmatter before it models a
document, because the six copies of a shared agent carry per-harness values
there. Verified verbatim against the committed ``critic`` group::

    templates/agents/critic.shared.md       model_tier: opus
    .claude/agents/critic.md                model: opus
    .github/agents/critic.agent.md          model: claude-opus-4.6
    src/claude/critic.md                    model: opus
    src/copilot-cli/agents/critic.agent.md  model: claude-opus-4.6
    src/vs-code-agents/critic.agent.md      model: Claude Opus 4.6 (copilot)

Because frontmatter is dropped, a diff confined to it produces an EMPTY
changed-section set. ``_missing_siblings_already_current`` used to test
``if not changed`` and so read that empty set as "cannot vouch", the same
verdict it gives a genuine parse failure. The gate then demanded co-change
for a diff that provably could not alter the invariant it protects.

The fix distinguishes the two verdicts: ``_added_sections`` returning ``{}``
proves the modelled document is byte-identical to base, while ``None`` means
the delta is unverifiable. Only ``None`` fails closed.

Covers:
- positive: frontmatter deletion, addition, value change, and whole-block
  removal pass; in the generated trees, in a hand-maintained copy, and in
  the template, because the rule is content-shaped, not tree-shaped
- negative: a body-section edit, a section addition, a section deletion, a
  preamble edit, and any mix of those with frontmatter still fail
- negative: a non-reference member cannot smuggle a body edit behind a
  frontmatter-only reference
- edge: no base, unresolvable base, duplicate heading, unterminated fence,
  unclosed frontmatter delimiter, and a deleted member all fail closed
- edge: an unmodellable UNTOUCHED sibling does not block a frontmatter-only
  diff, because no evidence about it is needed
- unit: ``_added_sections`` returns ``{}`` for frontmatter-only and ``None``
  for a parse failure, and the two are not conflated
- CLI: exit 0 for a frontmatter-only commit, exit 1 for a body change
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_install_parity as vip  # noqa: E402

# --- Fixture layout ------------------------------------------------------

TEMPLATE = "templates/agents/alpha.shared.md"
CLAUDE_INSTALL = ".claude/agents/alpha.md"
GITHUB_INSTALL = ".github/agents/alpha.agent.md"
SRC_CLAUDE = "src/claude/alpha.md"
SRC_COPILOT = "src/copilot-cli/agents/alpha.agent.md"
SRC_VSCODE = "src/vs-code-agents/alpha.agent.md"

# The two generator outputs. ``_missing_siblings_already_current`` picks the
# lexicographically first touched member as reference when no template is in
# the diff, so SRC_COPILOT is the reference for this pair.
GENERATED = [SRC_COPILOT, SRC_VSCODE]
HAND_MAINTAINED = [CLAUDE_INSTALL, GITHUB_INSTALL, SRC_CLAUDE]

# One shared body, six different frontmatter blocks: the real shape.
BODY = "# alpha\n\n## Core Mission\n\nDo the thing.\n\n## Budget\n\nCap at 5.\n"

BASE_FRONTMATTER: dict[str, str] = {
    TEMPLATE: "---\nmodel_tier: opus\n---\n",
    CLAUDE_INSTALL: "---\nname: alpha\nmodel: opus\n---\n",
    GITHUB_INSTALL: "---\nname: alpha\nmodel: claude-opus-4.6\n---\n",
    SRC_CLAUDE: "---\nname: alpha\nmodel: opus\n---\n",
    SRC_COPILOT: "---\nname: alpha\nmodel: claude-opus-4.6\n---\n",
    SRC_VSCODE: "---\nname: alpha\nmodel: Claude Opus 4.6 (copilot)\n---\n",
}


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def healthy_repo(tmp_path: Path) -> Path:
    """A committed repo whose ``alpha`` group agrees on every H2 body.

    Unlike ``torn_repo`` in the sibling suite, nothing here is torn: the
    tests below start from agreement and mutate one thing at a time, so a
    failure names exactly which mutation the gate reacted to.
    """
    for rel, frontmatter in BASE_FRONTMATTER.items():
        _write(tmp_path, rel, frontmatter + BODY)

    _run_git(tmp_path, "init", "-q")
    _run_git(tmp_path, "config", "user.email", "t@example.com")
    _run_git(tmp_path, "config", "user.name", "t")
    _run_git(tmp_path, "config", "commit.gpgsign", "false")
    _run_git(tmp_path, "add", "-A")
    _run_git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _drop_model_key(repo: Path, rels: list[str]) -> None:
    """Delete the ``model:`` line, leaving every other byte alone.

    This is the ADR-080 point 5 change class the issue reproduces: 60 deleted
    ``model:`` lines across the two generated trees and nothing else.
    """
    for rel in rels:
        path = repo / rel
        kept = [
            line
            for line in path.read_text(encoding="utf-8").splitlines(keepends=True)
            if not line.startswith("model:")
        ]
        path.write_text("".join(kept), encoding="utf-8")


def _violations(repo: Path, touched: list[str], base: str | None = "HEAD") -> list:
    return vip.find_violations(touched, repo_root=repo, base=base)


# --- Positive: frontmatter-only diffs pass -------------------------------


def test_generated_tree_model_key_deletion_passes(healthy_repo: Path) -> None:
    """The exact repro from Issue #4922: 'model:' removed, nothing else."""
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, GENERATED) == []


def test_frontmatter_value_change_passes(healthy_repo: Path) -> None:
    for rel in GENERATED:
        _write(healthy_repo, rel, "---\nname: alpha\nmodel: sonnet\n---\n" + BODY)
    assert _violations(healthy_repo, GENERATED) == []


def test_frontmatter_key_addition_passes(healthy_repo: Path) -> None:
    for rel in GENERATED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel].replace(
            "---\nname: alpha\n", "---\nname: alpha\ntier: manager\n"
        ) + BODY)
    assert _violations(healthy_repo, GENERATED) == []


def test_whole_frontmatter_block_removed_passes(healthy_repo: Path) -> None:
    for rel in GENERATED:
        _write(healthy_repo, rel, BODY)
    assert _violations(healthy_repo, GENERATED) == []


def test_frontmatter_added_where_none_existed_passes(healthy_repo: Path) -> None:
    for rel in GENERATED:
        _write(healthy_repo, rel, BODY)
    _run_git(healthy_repo, "add", "-A")
    _run_git(healthy_repo, "commit", "-q", "-m", "strip frontmatter")
    for rel in GENERATED:
        _write(healthy_repo, rel, "---\nname: alpha\n---\n" + BODY)
    assert _violations(healthy_repo, GENERATED) == []


def test_single_generated_tree_frontmatter_only_passes(healthy_repo: Path) -> None:
    """One tree, not both. The invariant is untouched either way."""
    _drop_model_key(healthy_repo, [SRC_COPILOT])
    assert _violations(healthy_repo, [SRC_COPILOT]) == []


# The rule is content-shaped, not tree-shaped: no path prefix is consulted.
# These two pin that a frontmatter-only diff passes outside the generated
# trees as well, which is what distinguishes this fix from the tree-specific
# carve-out the issue's proposed-fix section sketched.


def test_template_frontmatter_only_passes(healthy_repo: Path) -> None:
    _write(healthy_repo, TEMPLATE, "---\nmodel_tier: sonnet\n---\n" + BODY)
    assert _violations(healthy_repo, [TEMPLATE]) == []


def test_mixed_generated_and_template_frontmatter_only_passes(
    healthy_repo: Path,
) -> None:
    _write(healthy_repo, TEMPLATE, "---\nmodel_tier: sonnet\n---\n" + BODY)
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, [TEMPLATE, *GENERATED]) == []


# --- Negative: modelled-content changes still fail -----------------------


def test_body_section_edit_in_generated_trees_still_fails(
    healthy_repo: Path,
) -> None:
    for rel in GENERATED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + BODY.replace(
            "Cap at 5.", "Cap at 99."
        ))
    violations = _violations(healthy_repo, GENERATED)
    assert len(violations) == 1
    assert CLAUDE_INSTALL in violations[0].missing


def test_mixed_frontmatter_and_body_edit_still_fails(healthy_repo: Path) -> None:
    """The issue's third acceptance case: frontmatter plus one H2 edit."""
    for rel in GENERATED:
        _write(healthy_repo, rel, "---\nname: alpha\n---\n" + BODY.replace(
            "Cap at 5.", "Cap at 99."
        ))
    assert _violations(healthy_repo, GENERATED) != []


def test_mixed_frontmatter_and_section_addition_still_fails(
    healthy_repo: Path,
) -> None:
    for rel in GENERATED:
        _write(
            healthy_repo,
            rel,
            "---\nname: alpha\n---\n" + BODY + "\n## Novel\n\nNew text.\n",
        )
    assert _violations(healthy_repo, GENERATED) != []


def test_mixed_frontmatter_and_section_deletion_still_fails(
    healthy_repo: Path,
) -> None:
    for rel in GENERATED:
        _write(
            healthy_repo,
            rel,
            "---\nname: alpha\n---\n# alpha\n\n## Core Mission\n\nDo the thing.\n",
        )
    assert _violations(healthy_repo, GENERATED) != []


def test_mixed_frontmatter_and_preamble_edit_still_fails(
    healthy_repo: Path,
) -> None:
    for rel in GENERATED:
        _write(
            healthy_repo,
            rel,
            "---\nname: alpha\n---\n" + BODY.replace("# alpha", "# alpha v2"),
        )
    assert _violations(healthy_repo, GENERATED) != []


def test_non_reference_member_smuggling_a_body_edit_still_fails(
    healthy_repo: Path,
) -> None:
    """The empty changed-set is demanded of EVERY touched member.

    SRC_COPILOT sorts first and is therefore the reference. A clean
    frontmatter-only reference must not vouch for a sibling in the same diff
    that quietly edited a section body.
    """
    _drop_model_key(healthy_repo, [SRC_COPILOT])
    _write(
        healthy_repo,
        SRC_VSCODE,
        BASE_FRONTMATTER[SRC_VSCODE] + BODY.replace("Cap at 5.", "SMUGGLED."),
    )
    assert _violations(healthy_repo, GENERATED) != []


def test_reference_body_edit_with_frontmatter_only_sibling_still_fails(
    healthy_repo: Path,
) -> None:
    """The inverse of the test above: the reference is the one that changed."""
    _write(
        healthy_repo,
        SRC_COPILOT,
        BASE_FRONTMATTER[SRC_COPILOT] + BODY.replace("Cap at 5.", "SMUGGLED."),
    )
    _drop_model_key(healthy_repo, [SRC_VSCODE])
    assert _violations(healthy_repo, GENERATED) != []


# --- Edge: unverifiable deltas still fail closed -------------------------


def test_frontmatter_only_with_no_base_fails_closed(healthy_repo: Path) -> None:
    """Without a base there is no 'before', so nothing is provable."""
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, GENERATED, base=None) != []


def test_frontmatter_only_with_unresolvable_base_fails_closed(
    healthy_repo: Path,
) -> None:
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, GENERATED, base="no-such-ref-zzqx") != []


def test_duplicate_heading_is_a_parse_failure_not_a_proof(
    healthy_repo: Path,
) -> None:
    """A repeated H2 makes the section map lossy, so ``{}`` is not earned.

    This is the case the fix must NOT swallow: an unmodellable document also
    yields no added sections, and reading that as "nothing changed" would
    launder a body edit hidden under the duplicate.
    """
    dup = "# alpha\n\n## Budget\n\nCap at 5.\n\n## Budget\n\nAgain.\n"
    for rel in GENERATED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + dup)
    _run_git(healthy_repo, "add", "-A")
    _run_git(healthy_repo, "commit", "-q", "-m", "duplicate heading")
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, GENERATED) != []


def test_unterminated_fence_is_a_parse_failure_not_a_proof(
    healthy_repo: Path,
) -> None:
    unterminated = "# alpha\n\n## Budget\n\n```md\nno closing fence\n"
    for rel in GENERATED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + unterminated)
    _run_git(healthy_repo, "add", "-A")
    _run_git(healthy_repo, "commit", "-q", "-m", "unterminated fence")
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, GENERATED) != []


def test_unclosed_frontmatter_delimiter_fails_closed(healthy_repo: Path) -> None:
    """No closing ``---`` means the YAML is body text, so this is a real edit.

    ``_split_document`` strips frontmatter only when it finds the closing
    delimiter. A malformed block therefore lands in the preamble, the
    preamble comparison fails, and ``_added_sections`` returns None.
    """
    for rel in GENERATED:
        _write(healthy_repo, rel, "---\nname: alpha\n" + BODY)
    assert _violations(healthy_repo, GENERATED) != []


def test_deleted_member_fails_closed(healthy_repo: Path) -> None:
    """A touched member that is gone from disk is unreadable, not unchanged."""
    _drop_model_key(healthy_repo, [SRC_COPILOT])
    (healthy_repo / SRC_VSCODE).unlink()
    assert _violations(healthy_repo, GENERATED) != []


def test_unmodellable_untouched_sibling_does_not_block(
    healthy_repo: Path,
) -> None:
    """Pre-existing damage in a file this diff never touched must not block.

    A frontmatter-only diff needs no evidence about the missing siblings,
    so the carve-out returns before reading them. Reading them would let an
    untouched copy's duplicate heading veto a change with no honest way to
    comply, which is the trap Issue #4922 names.
    """
    _write(
        healthy_repo,
        CLAUDE_INSTALL,
        BASE_FRONTMATTER[CLAUDE_INSTALL]
        + "# alpha\n\n## Budget\n\nCap at 5.\n\n## Budget\n\nAgain.\n",
    )
    _run_git(healthy_repo, "add", "-A")
    _run_git(healthy_repo, "commit", "-q", "-m", "pre-existing damage")
    _drop_model_key(healthy_repo, GENERATED)
    assert _violations(healthy_repo, GENERATED) == []


# The contrast that defines the fix: the SAME pre-existing damage in the same
# untouched sibling blocks an ADDITIVE repair, because that repair needs the
# sibling's content as evidence, and does not block a frontmatter-only diff,
# because that one needs no evidence at all.


def test_unmodellable_missing_sibling_blocks_an_additive_repair(
    healthy_repo: Path,
) -> None:
    _write(
        healthy_repo,
        CLAUDE_INSTALL,
        BASE_FRONTMATTER[CLAUDE_INSTALL]
        + "# alpha\n\n## Budget\n\nCap at 5.\n\n## Budget\n\nAgain.\n",
    )
    _run_git(healthy_repo, "add", "-A")
    _run_git(healthy_repo, "commit", "-q", "-m", "pre-existing damage")
    for rel in GENERATED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + BODY + "\n## Extra\n\nx.\n")
    assert _violations(healthy_repo, GENERATED) != []


def test_unreadable_missing_sibling_blocks_an_additive_repair(
    healthy_repo: Path,
) -> None:
    """A missing sibling that is not on disk cannot vouch for the addition."""
    (healthy_repo / CLAUDE_INSTALL).unlink()
    for rel in GENERATED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + BODY + "\n## Extra\n\nx.\n")
    assert _violations(healthy_repo, GENERATED) != []


# --- Interaction with the carve-outs that run first ----------------------


def test_hand_maintained_carve_out_still_short_circuits(
    healthy_repo: Path,
) -> None:
    """Hand-maintained-only diffs never reach the content check."""
    _write(
        healthy_repo,
        CLAUDE_INSTALL,
        BASE_FRONTMATTER[CLAUDE_INSTALL] + BODY.replace("Cap at 5.", "Cap at 99."),
    )
    assert _violations(healthy_repo, HAND_MAINTAINED[:1]) == []


def test_torn_repair_carve_out_still_works(healthy_repo: Path) -> None:
    """A genuine additive repair still passes on its own evidence."""
    repaired = BODY + "\n## Extra\n\nx.\n"
    for rel in HAND_MAINTAINED:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + repaired)
    _run_git(healthy_repo, "add", "-A")
    _run_git(healthy_repo, "commit", "-q", "-m", "tear the group")
    for rel in [TEMPLATE, *GENERATED]:
        _write(healthy_repo, rel, BASE_FRONTMATTER[rel] + repaired)
    assert _violations(healthy_repo, [TEMPLATE, *GENERATED]) == []


# --- Unit: the two verdicts are distinct ---------------------------------


def test_added_sections_returns_empty_dict_for_frontmatter_only(
    healthy_repo: Path,
) -> None:
    _drop_model_key(healthy_repo, [SRC_COPILOT])
    result = vip._added_sections(healthy_repo, "HEAD", SRC_COPILOT)
    assert result == {}
    assert result is not None


def test_added_sections_returns_none_for_preamble_edit(
    healthy_repo: Path,
) -> None:
    _write(
        healthy_repo,
        SRC_COPILOT,
        BASE_FRONTMATTER[SRC_COPILOT] + BODY.replace("# alpha", "# alpha v2"),
    )
    assert vip._added_sections(healthy_repo, "HEAD", SRC_COPILOT) is None


def test_added_sections_returns_none_for_missing_file(
    healthy_repo: Path,
) -> None:
    (healthy_repo / SRC_COPILOT).unlink()
    assert vip._added_sections(healthy_repo, "HEAD", SRC_COPILOT) is None


def test_carve_out_distinguishes_empty_set_from_parse_failure(
    healthy_repo: Path,
) -> None:
    """The root cause, at the level it lives.

    Both inputs produce "no added sections". Only one of them is a proof.
    """
    _drop_model_key(healthy_repo, GENERATED)
    assert vip._added_sections(healthy_repo, "HEAD", SRC_COPILOT) == {}
    assert (
        vip._missing_siblings_already_current(
            healthy_repo, "HEAD", GENERATED, [CLAUDE_INSTALL]
        )
        is True
    )

    _write(
        healthy_repo,
        SRC_COPILOT,
        "---\nname: alpha\n---\n" + BODY + "\n## Budget\n\nDuplicate.\n",
    )
    assert vip._added_sections(healthy_repo, "HEAD", SRC_COPILOT) is None
    assert (
        vip._missing_siblings_already_current(
            healthy_repo, "HEAD", GENERATED, [CLAUDE_INSTALL]
        )
        is False
    )


# --- CLI: exit codes (ADR-035) -------------------------------------------


def _commit_all(repo: Path, message: str) -> None:
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "-m", message)


def test_cli_exits_zero_for_frontmatter_only_commit(
    healthy_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _drop_model_key(healthy_repo, GENERATED)
    _commit_all(healthy_repo, "drop model key")
    code = vip.main(
        ["--repo-root", str(healthy_repo), "--base", "HEAD~1"]
    )
    assert code == 0
    assert "install-parity: OK" in capsys.readouterr().out


def test_cli_exits_one_for_body_change_commit(
    healthy_repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for rel in GENERATED:
        _write(
            healthy_repo,
            rel,
            BASE_FRONTMATTER[rel] + BODY.replace("Cap at 5.", "Cap at 99."),
        )
    _commit_all(healthy_repo, "edit body")
    code = vip.main(
        ["--repo-root", str(healthy_repo), "--base", "HEAD~1"]
    )
    assert code == 1
    assert "install-parity: DRIFT" in capsys.readouterr().out
