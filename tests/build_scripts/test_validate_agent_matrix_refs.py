"""Tests for build/scripts/validate_agent_matrix_refs.py.

Covers the parser, per-tree resolution, the anti-vacuous structural guards, and
the CLI exit contract from ADR-035.

Four tests deliberately read the real repository rather than a fixture:
``test_repository_is_clean``, ``test_every_configured_tree_exists_and_is_scanned``,
``test_every_configured_tree_yields_agents``, and
``test_orchestrator_matrix_is_scanned``. Anchoring an expectation in the
filesystem instead of in the module's own constants is what keeps the suite from
adapting to a mutation of those constants. A test parametrized over
``AGENT_TREES`` would pass just as happily if someone shrank ``AGENT_TREES`` to a
single entry, or changed a suffix so a tree silently yielded no agents.

The tree list in ``test_every_configured_tree_exists_and_is_scanned`` is written
out literally and is NOT filtered against the disk. An earlier version filtered
it, which meant deleting a tree, or dropping one inside ``scan``, left the
assertion satisfied by a smaller set. Deleting an agent tree from this repository
must fail this test and force a human to update the guard on purpose.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import frontmatter
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_agent_matrix_refs as vamr  # noqa: E402

CANONICAL = str(vamr.CANONICAL_TREE)

# Every configured agent tree, written out independently of the module constant
# this suite is meant to constrain.
EXPECTED_TREES = {
    "templates/agents",
    ".claude/agents",
    ".github/agents",
    "src/claude",
    "src/copilot-cli/agents",
    "src/vs-code-agents",
}

# Minimum content for a file to count as an agent definition.
AGENT_STUB = "---\ndescription: Test agent.\n---\n\n# {name}\n"

BOLD_MATRIX = """\
## Agent Capability Matrix

| Agent | Use For | Model | Avoid When |
|-------|---------|-------|-----------|
| **analyst** | Research | sonnet | Have context |
| **implementer** | Code | sonnet | Design open |
"""


def _suffix_for(tree: str) -> str:
    """Return the configured filename suffix for a tree, by path string."""
    for path, suffix in vamr.AGENT_TREES:
        if str(path) == tree:
            return suffix
    raise AssertionError(f"{tree} is not a configured agent tree")


def _repo(
    tmp_path: Path,
    files: dict[str, str],
    agents_by_tree: dict[str, list[str]],
    *,
    complete: bool = False,
) -> Path:
    """Build a throwaway repo.

    ``agents_by_tree`` maps a configured tree path to the agent names that tree
    ships. Each name is written using that tree's own suffix, because the
    suffix is what the validator strips to derive a name. Each file carries
    agent frontmatter, because a suffix match alone no longer counts. A tree
    absent from the mapping is not created at all, which ``scan`` skips.

    Pass ``complete=True`` for any test that calls ``main``. ``main`` refuses to
    run against a checkout missing a configured tree, so a partial fixture would
    exit 2 before reaching the behavior under test. Trees the caller did not
    name are backfilled with a single unrelated agent, which is what a real
    checkout looks like: every tree present, most of them irrelevant to the
    matrix being examined.
    """
    if complete:
        agents_by_tree = {
            **{tree: ["filler"] for tree in EXPECTED_TREES},
            **agents_by_tree,
        }
    for tree, names in agents_by_tree.items():
        suffix = _suffix_for(tree)
        directory = tmp_path / tree
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            (directory / f"{name}{suffix}").write_text(
                AGENT_STUB.format(name=name), encoding="utf-8"
            )
    for relative, body in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def _canonical_file(name: str) -> str:
    """Return a path inside the canonical tree using its configured suffix."""
    return f"{CANONICAL}/{name}{_suffix_for(CANONICAL)}"


def _frontmatter_text(text: str) -> str | None:
    """Return the frontmatter block of ``text``, or ``None`` if it has none.

    Written independently of the module under test so the checks built on it
    stay a second opinion. Deliberately more permissive than the
    implementation about the opening fence: for a guard, over-reaching only
    costs a false alarm, while under-reaching lets the thing being guarded
    against slip past unseen.
    """
    opened = re.match(r"-{3,}[ \t]*\n", text)
    if opened is None:
        return None
    close = re.compile(r"^-{3,}[ \t]*$", re.MULTILINE).search(text, opened.end())
    if close is None:
        return None
    return text[opened.end() : close.start()]


# A YAML alias reference (``*name``) inside a frontmatter block. Anchored to a
# boundary so a multiplication sign or an emphasis marker in a description does
# not read as one.
_ALIAS_IN_FRONTMATTER = re.compile(r"(^|[\s\[{,])\*[A-Za-z0-9_-]+")


def _has_agent_frontmatter(path: Path) -> bool:
    """Second opinion on agent membership, used only by the real-repo test.

    Independent where it counts and shared where it does not, stated plainly so
    nobody reads more into an agreement than it earns.

    Independent on block boundaries. The implementation locates the fences with
    its own regexes; this delegates that to ``python-frontmatter``. The two are
    genuinely different code: probed against seven malformed openings they
    disagree on three, including a leading blank line and a fourth hyphen. An
    oracle that reused the implementation's approach could not disagree with it,
    so it would prove nothing.

    Shared on YAML semantics. ``python-frontmatter`` hands the block to PyYAML's
    ``SafeLoader`` too, so agreement here is not evidence. It also means this
    oracle inherits the merge-key amplification the implementation now refuses,
    which is why alias-bearing input is turned away below rather than parsed:
    a test that hangs on regression is worse than no test. The implementation
    fails closed on the same input, so refusing it keeps the comparison honest
    rather than manufacturing agreement on a case the two would dispute.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if (block := _frontmatter_text(text)) and _ALIAS_IN_FRONTMATTER.search(block):
        return False
    try:
        parsed = frontmatter.loads(text)
    except Exception:
        return False
    return "description" in parsed.keys()


class TestKnownAgents:
    """Per-tree roster derivation.

    Membership takes two signals, and both are load-bearing. The filename must
    end in the tree's suffix, and the file must open with frontmatter carrying
    ``description:``. Suffix alone was the original rule and an adversarial
    review defeated it: in a tree whose suffix is a bare ``.md`` it admits every
    sibling markdown file, so ``claude-instructions.template.md`` became a
    citable agent named ``claude-instructions.template``.
    """

    @staticmethod
    def _agent(directory: Path, filename: str) -> None:
        (directory / filename).write_text(AGENT_STUB.format(name=filename), encoding="utf-8")

    def test_strips_the_configured_suffix(self, tmp_path):
        self._agent(tmp_path, "analyst.agent.md")
        self._agent(tmp_path, "critic.agent.md")
        assert vamr.known_agents(tmp_path, ".agent.md") == {"analyst", "critic"}

    def test_files_not_matching_the_suffix_are_excluded(self, tmp_path):
        """``copilot-instructions.md`` is not an agent in an ``.agent.md`` tree."""
        self._agent(tmp_path, "analyst.agent.md")
        self._agent(tmp_path, "copilot-instructions.md")
        assert vamr.known_agents(tmp_path, ".agent.md") == {"analyst"}

    def test_shared_suffix_is_stripped_whole(self, tmp_path):
        self._agent(tmp_path, "orchestrator.shared.md")
        assert vamr.known_agents(tmp_path, ".shared.md") == {"orchestrator"}

    def test_sibling_docs_without_frontmatter_are_excluded(self, tmp_path):
        """The Critical defect from round two of adversarial review.

        ``src/claude`` and ``.claude/agents`` both use a bare ``.md`` suffix and
        both hold non-agent documents alongside the agents. Two are uppercase,
        but ``claude-instructions.template.md`` is not, so a case rule cannot
        carry this. Only frontmatter separates them.
        """
        self._agent(tmp_path, "analyst.md")
        for doc in ("AGENTS.md", "CLAUDE.md", "claude-instructions.template.md"):
            (tmp_path / doc).write_text("# Instructions\n\nProse.\n", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_frontmatter_without_description_is_excluded(self, tmp_path):
        """A frontmatter block alone is not enough; it must describe an agent."""
        self._agent(tmp_path, "analyst.md")
        (tmp_path / "notes.md").write_text("---\napplyTo: '**'\n---\n\n# Notes\n", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_unterminated_frontmatter_is_excluded(self, tmp_path):
        """An opening fence with no closing fence is not a frontmatter block."""
        (tmp_path / "broken.md").write_text("---\ndescription: never closed\n", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_horizontal_rule_does_not_fake_a_frontmatter_block(self, tmp_path):
        """The opening fence is load-bearing, not decoration.

        Without it, ``---`` used as a horizontal rule anywhere in the body closes
        an imaginary block that starts at byte zero, so any line above the rule
        beginning with ``description:`` admits the document.
        """
        (tmp_path / "notes.md").write_text(
            "# Notes\n\ndescription: prose, not frontmatter\n\n---\n\nMore.\n",
            encoding="utf-8",
        )
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_a_key_merely_ending_in_description_is_excluded(self, tmp_path):
        """The key is anchored to the start of a line, so suffixes do not count."""
        for stem, key in (("a", "x-description"), ("b", "long_description")):
            (tmp_path / f"{stem}.md").write_text(
                f"---\n{key}: something\n---\n\n# Doc\n", encoding="utf-8"
            )
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_description_after_the_frontmatter_block_is_excluded(self, tmp_path):
        """The key must sit inside the block, not merely somewhere in the file."""
        (tmp_path / "prose.md").write_text(
            "---\napplyTo: '**'\n---\n\ndescription: this is body text\n",
            encoding="utf-8",
        )
        assert vamr.known_agents(tmp_path, ".md") == set()

    @pytest.mark.parametrize(
        "closing",
        ["---not-a-closing-fence", "----", "--- trailing prose", "---\tx"],
    )
    def test_a_partial_line_does_not_close_the_frontmatter_block(self, tmp_path, closing):
        """The closing fence must be a line holding nothing but three hyphens.

        A substring search for a newline followed by three hyphens accepted
        ``---not-a-closing-fence``, so a malformed document presented itself as
        an agent and a matrix row citing its stem passed.
        """
        (tmp_path / "malformed.md").write_text(
            f"---\ndescription: not an agent\n{closing}\n\n# Doc\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == set()

    @pytest.mark.parametrize(
        ("label", "block"),
        [
            ("unclosed flow sequence", "description: ["),
            ("unclosed flow mapping", "description: {"),
            ("tab indentation", "description: x\n\tnested: y"),
            ("unclosed quote", 'description: "unterminated'),
            ("undefined alias", "description: *missing"),
            ("block sequence under a scalar", "description: x\n- item"),
        ],
    )
    def test_frontmatter_that_is_not_loadable_yaml_is_excluded(self, tmp_path, label, block):
        """A block no host can parse cannot define an agent.

        The check tested for a textual ``description:`` key and never parsed the
        block, so ``description: [`` was admitted to the roster. Review used that
        to substitute a non-agent document for a real one, cite its stem from a
        matrix, and pass the run. The name resolved here and nowhere a host
        looks, which is exactly the phantom this validator exists to catch.
        """
        (tmp_path / "phantom.md").write_text(f"---\n{block}\n---\n\n# Doc\n", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == set(), label

    def test_a_scalar_frontmatter_block_is_excluded(self, tmp_path):
        """Valid YAML that is not a mapping has no keys to carry."""
        (tmp_path / "scalar.md").write_text("---\njust a string\n---\n", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_a_sequence_frontmatter_block_is_excluded(self, tmp_path):
        (tmp_path / "seq.md").write_text("---\n- description\n---\n", encoding="utf-8")
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_a_nested_description_key_is_excluded(self, tmp_path):
        """The key must be top level, where a host reads it."""
        (tmp_path / "nested.md").write_text(
            "---\nmeta:\n  description: buried\n---\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_a_closing_fence_with_trailing_whitespace_still_closes(self, tmp_path):
        """Trailing spaces on the fence line are invisible and must not exclude."""
        (tmp_path / "analyst.md").write_text(
            "---\ndescription: An agent.\n---  \n\n# Analyst\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_an_opening_fence_with_trailing_whitespace_still_opens(self, tmp_path):
        """The opening fence tolerates what the closing fence tolerates.

        Rejecting an invisible trailing space here reported a real agent as
        absent, so a matrix citing it failed with ``agent does not ship`` while
        the file sat in the tree. The two fences must agree.
        """
        (tmp_path / "analyst.md").write_text(
            "---  \ndescription: An agent.\n---\n\n# Analyst\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_a_wider_opening_fence_shifts_the_search_for_the_close(self, tmp_path):
        """The close is searched from the end of the open, not a fixed offset.

        A hardcoded offset of four is correct only for a bare ``---\\n``. With a
        wider opening fence it lands mid-key, so a block whose first key would
        be truncated proves the offset follows the match.
        """
        (tmp_path / "analyst.md").write_text(
            "---\t \ndescription: An agent.\n---\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    @pytest.mark.parametrize(
        ("label", "opening"),
        [
            ("four hyphens", "----\n"),
            ("two hyphens", "--\n"),
            ("leading blank line", "\n---\n"),
            ("leading space", " ---\n"),
            ("trailing text", "--- x\n"),
        ],
    )
    def test_a_malformed_opening_fence_excludes_the_file(self, tmp_path, label, opening):
        """Only three hyphens at the first byte open a block.

        The anchor is what stops a body-level horizontal rule from turning the
        prose above it into a pseudo-block, so loosening it is not safe.
        """
        (tmp_path / "analyst.md").write_text(
            f"{opening}description: An agent.\n---\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == set(), label

    def test_a_byte_order_mark_does_not_hide_an_agent(self, tmp_path):
        """A BOM ahead of the fence is a real agent to the hosts that load it.

        Treating it as prose is worse than a missing agent: every matrix row
        citing it reports the agent does not ship, so a well-formed file
        produces a violation nobody can act on.
        """
        (tmp_path / "analyst.md").write_bytes("\ufeff---\ndescription: An agent.\n---\n".encode())
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_a_byte_order_mark_does_not_hide_a_matrix(self, tmp_path):
        """The same BOM must not hide the table either.

        ``scan`` reads matrix files on a separate path from the roster, so
        fixing one and not the other leaves a file whose agent is known and
        whose rows are invisible.
        """
        repo = _repo(
            tmp_path,
            {},
            {CANONICAL: ["analyst", "implementer", "orchestrator"]},
            complete=True,
        )
        (repo / _canonical_file("orchestrator")).write_bytes(
            ("\ufeff---\ndescription: An agent.\n---\n\n" + BOLD_MATRIX).encode()
        )
        result = vamr.scan(repo)
        assert [c.name for c in result.citations] == ["analyst", "implementer"]

    def test_directory_matching_the_suffix_is_excluded(self, tmp_path):
        """A directory named ``foo.md`` cannot be read, so it cannot be an agent."""
        (tmp_path / "bogus.md").mkdir()
        self._agent(tmp_path, "analyst.md")
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_empty_directory_returns_empty_set(self, tmp_path):
        assert vamr.known_agents(tmp_path, ".md") == set()


class TestAliasAmplification:
    """Frontmatter must not be able to hold the scan open.

    ``safe_load`` stops arbitrary object construction, not resource use.
    ``SafeConstructor.flatten_mapping`` expands a merge key by copying every
    entry of the mapping the alias names, so each level of a chain that
    references the level below it nine times multiplies the entry count by nine.
    Measured before the fix: a 433 byte block held ``is_agent_definition`` for
    21.67 seconds, and every added level costs another factor of nine. The
    validator runs on ``pull_request``, so a fork supplies the file.
    """

    @staticmethod
    def _bomb(levels: int) -> str:
        """Return frontmatter whose merge chain expands to ``9 ** levels`` entries."""
        rows = ["a: &a {x: x}"]
        previous = "a"
        for name in "bcdefghijklmnop"[:levels]:
            fanout = ", ".join(f"*{previous}" for _ in range(9))
            rows.append(f"{name}: &{name} {{<<: [{fanout}]}}")
            previous = name
        return "---\n" + "\n".join(rows) + "\ndescription: bomb\n---\n\n# Doc\n"

    def test_a_merge_key_chain_is_rejected_quickly(self, tmp_path):
        """The payload that cost 21.67 seconds must now cost effectively nothing.

        The assertion is on elapsed time, not only on the verdict, because a
        loader that accepted aliases would also return ``set()`` here, after
        expanding the chain. Only the clock separates rejection from expansion.

        The depth is capped at 8 on purpose. Each level multiplies the work by
        nine, so depth 10 runs for roughly half an hour. A regression must fail,
        not hang: at depth 8 a loader that expands aliases trips this assertion
        in about 22 seconds and names the cause. Do not raise the depth.
        """
        (tmp_path / "bomb.md").write_text(self._bomb(8), encoding="utf-8")
        started = time.monotonic()
        assert vamr.known_agents(tmp_path, ".md") == set()
        assert time.monotonic() - started < 2.0

    def test_a_bomb_does_not_hide_a_sibling_agent(self, tmp_path):
        """Rejecting one file must not abort the roster scan for the rest."""
        (tmp_path / "bomb.md").write_text(self._bomb(8), encoding="utf-8")
        (tmp_path / "analyst.md").write_text(
            "---\ndescription: An agent.\n---\n\n# Analyst\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_a_plain_alias_is_rejected(self, tmp_path):
        """The guard refuses the alias itself, not only the merge key.

        A merge key cannot amplify without an alias to reference, so the alias is
        the narrower cut. Refusing it fails closed: the file drops out of the
        roster, and a matrix citing its stem reports an unknown agent instead of
        passing silently.
        """
        (tmp_path / "alias.md").write_text(
            "---\nbase: &base a description\ndescription: *base\n---\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == set()

    def test_an_anchor_with_no_alias_still_defines_an_agent(self, tmp_path):
        """An anchor that nothing references cannot amplify, so it is left alone."""
        (tmp_path / "analyst.md").write_text(
            "---\ndescription: &unused An agent.\n---\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}

    def test_a_merge_key_over_an_inline_mapping_still_defines_an_agent(self, tmp_path):
        """Without an alias a merge key copies one literal mapping once."""
        (tmp_path / "analyst.md").write_text(
            "---\n<<: {description: An agent.}\nname: analyst\n---\n", encoding="utf-8"
        )
        assert vamr.known_agents(tmp_path, ".md") == {"analyst"}


class TestPerTreeResolution:
    """Resolution is scoped to the tree that carries the citation.

    This is the defect an adversarial review found in the first version. A
    global roster answers "does this name exist anywhere", but the plugin roots
    install standalone, so the load-bearing question is whether the name exists
    in the install that publishes the table.
    """

    def test_name_shipped_in_its_own_tree_is_clean(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        assert vamr.violations(vamr.scan(repo)) == []

    def test_name_missing_from_its_own_tree_is_a_violation(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
        )
        bad = vamr.violations(vamr.scan(repo))
        assert [c.name for c in bad] == ["implementer"]

    def test_presence_in_a_sibling_tree_does_not_satisfy_a_citation(self, tmp_path):
        """The exact shape of the quality-auditor defect.

        One tree ships the agent, another cites it without shipping it. A
        repository-wide roster reports success here; a per-tree roster does not.
        """
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                ".claude/agents/orchestrator.md": BOLD_MATRIX,
            },
            {
                CANONICAL: ["analyst", "implementer"],
                ".claude/agents": ["analyst"],
            },
        )
        bad = vamr.violations(vamr.scan(repo))
        assert len(bad) == 1
        assert bad[0].name == "implementer"
        assert str(bad[0].tree) == ".claude/agents"

    def test_violation_records_the_tree_that_lacks_the_agent(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
        )
        bad = vamr.violations(vamr.scan(repo))
        assert str(bad[0].tree) == CANONICAL

    def test_violation_reported_once_per_site(self, tmp_path):
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                _canonical_file("planner"): BOLD_MATRIX,
            },
            {CANONICAL: ["analyst"]},
        )
        bad = vamr.violations(vamr.scan(repo))
        assert len(bad) == 2
        assert {str(c.path) for c in bad} == {
            _canonical_file("orchestrator"),
            _canonical_file("planner"),
        }

    def test_absent_tree_is_skipped_by_scan_so_fixtures_can_be_partial(self, tmp_path):
        """``scan`` tolerates a missing tree; ``main`` is where that is refused.

        Every fixture in this suite builds one or two trees rather than all six,
        so the tolerance has to live somewhere. Keeping it in ``scan`` and the
        refusal in ``main`` means a real run cannot pass by omission while the
        tests stay small. The refusal is pinned by
        ``TestMainCli.test_missing_configured_tree_exits_two``.
        """
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        result = vamr.scan(repo)
        assert [str(t) for t in result.trees_scanned] == [CANONICAL]
        assert vamr.violations(result) == []

    def test_files_without_a_matrix_are_not_counted(self, tmp_path):
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                f"{CANONICAL}/notes.md": "# Notes\n\nNo table here.\n",
            },
            {CANONICAL: ["analyst", "implementer"]},
        )
        result = vamr.scan(repo)
        assert len(result.files_with_matrix) == 1


class TestAntiVacuousGuards:
    """A scan that silently finds nothing must fail, not pass."""

    def test_no_matrix_anywhere_is_degenerate(self, tmp_path):
        repo = _repo(
            tmp_path,
            {f"{CANONICAL}/notes.md": "# Notes\n"},
            {CANONICAL: ["analyst"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any("no capability matrix found in any" in r for r in reasons)

    def test_matrix_outside_the_canonical_tree_only_is_degenerate(self, tmp_path):
        repo = _repo(
            tmp_path,
            {".claude/agents/orchestrator.md": BOLD_MATRIX},
            {CANONICAL: ["analyst"], ".claude/agents": ["analyst", "implementer"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any(CANONICAL in r for r in reasons)

    def test_header_present_but_no_rows_is_a_parse_gap(self, tmp_path):
        text = "| Agent | Role |\n|-------|------|\n\nProse.\n"
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): text},
            {CANONICAL: ["analyst"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any("no rows parsed" in r for r in reasons)

    def test_unparsed_row_inside_a_matrix_is_degenerate(self, tmp_path):
        text = (
            "| Agent | Role |\n"
            "|-------|------|\n"
            "| **analyst** | Research |\n"
            "| TODO fill this in | Unknown |\n"
        )
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): text},
            {CANONICAL: ["analyst", "orchestrator"]},
        )
        reasons = vamr.scan(repo).degeneracy()
        assert any("does not parse as an agent name" in r for r in reasons)

    def test_tree_present_but_yielding_no_agents_is_degenerate(self, tmp_path):
        """A suffix that stops matching makes every citation resolve to nothing."""
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
        )
        (repo / ".claude" / "agents").mkdir(parents=True)
        (repo / ".claude" / "agents" / "README.rst").write_text("x", encoding="utf-8")
        reasons = vamr.scan(repo).degeneracy()
        assert any("yields no agent files" in r for r in reasons)

    def test_tree_holding_only_agent_files_is_not_degenerate(self, tmp_path):
        """A tree with definitions and no routing table is a valid state.

        An earlier version required every scanned tree to yield a matrix. That
        is not an invariant and fired on correct repositories, so the rule was
        narrowed to conditions that are unambiguously degenerate.
        """
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {
                CANONICAL: ["analyst", "implementer"],
                ".claude/agents": ["analyst", "implementer"],
            },
        )
        assert vamr.scan(repo).degeneracy() == []

    def test_no_matrix_anywhere_fails_the_cli(self, tmp_path, capsys):
        repo = _repo(
            tmp_path,
            {f"{CANONICAL}/notes.md": "# Notes\n"},
            {CANONICAL: ["analyst"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1
        assert "ERROR" in capsys.readouterr().out

    def test_canonical_degeneracy_fails_the_cli(self, tmp_path):
        repo = _repo(
            tmp_path,
            {".claude/agents/orchestrator.md": BOLD_MATRIX},
            {CANONICAL: ["analyst"], ".claude/agents": ["analyst", "implementer"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1

    def test_parse_gap_fails_the_cli_even_with_no_violations(self, tmp_path):
        text = "| Agent | Role |\n|-------|------|\n\nProse.\n"
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                _canonical_file("planner"): text,
            },
            {CANONICAL: ["analyst", "implementer", "orchestrator", "planner"]},
            complete=True,
        )
        result = vamr.scan(repo)
        assert vamr.violations(result) == []
        assert vamr.main(["--repo-root", str(repo)]) == 1

    def test_a_degenerate_scan_does_not_also_report_success(self, tmp_path, capsys):
        """A run that errors must not end on OK.

        The exit code was already right, but the summary printed the ERROR lines
        and then announced that every agent checks out. A reader who trusts the
        last line draws the opposite conclusion from the one the run reached.
        """
        text = "| Agent | Role |\n|-------|------|\n\nProse.\n"
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): BOLD_MATRIX,
                _canonical_file("planner"): text,
            },
            {CANONICAL: ["analyst", "implementer", "orchestrator", "planner"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1
        out = capsys.readouterr().out
        assert "ERROR:" in out
        assert "OK:" not in out

    def test_empty_tree_fails_the_cli_even_with_no_violations(self, tmp_path):
        """A tree present but yielding no agents is degenerate, not clean.

        The tree is named explicitly with an empty roster so the backfill leaves
        it empty. Its only file carries a suffix the tree does not use, which is
        what a suffix-convention change looks like from the validator's side.
        """
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"], ".claude/agents": []},
            complete=True,
        )
        (repo / ".claude" / "agents" / "README.rst").write_text("x", encoding="utf-8")
        assert vamr.violations(vamr.scan(repo)) == []
        assert vamr.main(["--repo-root", str(repo)]) == 1


class TestMainCli:
    """Exit contract from ADR-035."""

    def test_clean_repo_exits_zero(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 0

    def test_violation_exits_one(self, tmp_path):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1

    def test_phantom_row_in_an_indented_matrix_exits_one(self, tmp_path, capsys):
        """End-to-end proof that indent support closed the hole, not just parsing.

        An adversarial review hid a phantom row in a two-space-indented table and
        the validator reported success. The table renders; a reader routing off
        it would try to invoke an agent the tree does not ship.
        """
        indented = (
            "## Matrix\n\n"
            "  | Agent | Role |\n"
            "  |-------|------|\n"
            "  | **analyst** | Research |\n"
            "  | **memory** | Phantom |\n"
        )
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): indented},
            {CANONICAL: ["analyst"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1
        assert "'memory' is not shipped" in capsys.readouterr().out

    def test_row_citing_a_sibling_doc_exits_one(self, tmp_path, capsys):
        """End-to-end proof for the frontmatter rule.

        ``src/claude`` uses a bare ``.md`` suffix, so before this rule a row
        naming ``claude-instructions.template`` resolved against a real file and
        the validator reported success.
        """
        matrix = (
            "| Agent | Role |\n"
            "|-------|------|\n"
            "| **analyst** | Research |\n"
            "| **claude-instructions.template** | Phantom |\n"
        )
        repo = _repo(
            tmp_path,
            {
                _canonical_file("orchestrator"): matrix,
                f"{CANONICAL}/claude-instructions.template"
                f"{_suffix_for(CANONICAL)}": "# Template\n\nProse.\n",
            },
            {CANONICAL: ["analyst"]},
            complete=True,
        )
        assert vamr.main(["--repo-root", str(repo)]) == 1
        assert "'claude-instructions.template' is not shipped" in capsys.readouterr().out

    def test_no_agents_anywhere_exits_two(self, tmp_path, capsys):
        """No roster at all is a configuration error, not a flood of violations.

        Every configured tree is present but empty, so this exercises the empty
        roster rather than the absent-tree refusal that precedes it.
        """
        repo = _repo(
            tmp_path,
            {f"{CANONICAL}/notes.md": "# Notes\n"},
            {tree: [] for tree in EXPECTED_TREES},
        )
        assert vamr.main(["--repo-root", str(repo)]) == 2
        assert "no configured tree yields any agent file" in capsys.readouterr().err

    def test_missing_configured_tree_exits_two(self, tmp_path, capsys):
        """An absent tree is a configuration error, not a tree to skip.

        The two gates that run this code fire on different paths. The workflow
        that invokes this script covers every agent tree, while the workflow
        that runs the test suite fires only on Python changes. Deleting an agent
        tree is a markdown-only change, so it reaches the script without ever
        reaching the filesystem test in ``TestRealRepository``. If ``main``
        skipped the absent tree, every citation into it would pass by omission.
        """
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
            complete=True,
        )
        dropped = ".github/agents"
        for path in sorted((repo / dropped).iterdir()):
            path.unlink()
        (repo / dropped).rmdir()

        assert vamr.main(["--repo-root", str(repo)]) == 2
        assert dropped in capsys.readouterr().err

    def test_violation_names_the_agent_the_site_and_the_tree(self, tmp_path, capsys):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst"]},
            complete=True,
        )
        vamr.main(["--repo-root", str(repo)])
        out = capsys.readouterr().out
        assert "implementer" in out
        assert "orchestrator" in out
        assert CANONICAL in out

    def test_clean_run_names_what_it_looked_at(self, tmp_path, capsys):
        repo = _repo(
            tmp_path,
            {_canonical_file("orchestrator"): BOLD_MATRIX},
            {CANONICAL: ["analyst", "implementer"]},
            complete=True,
        )
        vamr.main(["--repo-root", str(repo)])
        out = capsys.readouterr().out
        assert "Rows cited:" in out
        assert "Trees scanned:" in out


class TestRealRepository:
    """Filesystem-anchored checks. These do not read the module's constants."""

    def test_repository_is_clean(self):
        assert vamr.main(["--repo-root", str(REPO_ROOT)]) == 0

    def test_no_shipped_agent_frontmatter_uses_an_alias(self):
        """The alias guard costs nothing today, which is why it can fail closed.

        ``TestAliasAmplification`` proves an alias is refused. This proves the
        refusal excludes nothing real. If an agent ever adopts an alias this
        fails first and states the tradeoff, instead of that agent silently
        vanishing from the roster and taking its matrix rows down with it.
        """
        offenders = []
        examined = 0
        for tree, suffix in vamr.AGENT_TREES:
            root = REPO_ROOT / tree
            for path in sorted(root.glob(f"*{suffix}")):
                text = path.read_text(encoding="utf-8", errors="replace")
                block = _frontmatter_text(text)
                if block is None:
                    continue
                examined += 1
                if _ALIAS_IN_FRONTMATTER.search(block):
                    offenders.append(str(path))
        assert offenders == []
        assert examined >= 175, f"only {examined} frontmatter blocks examined"

    def test_every_configured_tree_exists_and_is_scanned(self):
        """Guard against a tree being dropped, from the constant or from ``scan``.

        Three assertions, each killing a different mutation. The existence check
        kills deleting a tree from disk without updating this guard. The
        equality against ``AGENT_TREES`` kills shrinking the constant. The
        equality against ``trees_scanned`` kills discarding a tree inside
        ``scan`` while leaving the constant intact, which is the mutation that
        survived the first mutation run because this list used to be filtered by
        ``is_dir()`` and compared with ``<=``. A subset assertion is satisfied by
        a smaller set, so it cannot see a tree go missing.

        ``EXPECTED_TREES`` is written out literally at module scope and is not
        derived from ``AGENT_TREES``. Deleting an agent tree from this repository
        is supposed to fail here and force a human to update the guard on purpose.
        """
        missing = {name for name in EXPECTED_TREES if not (REPO_ROOT / name).is_dir()}
        assert not missing, f"configured agent trees missing from disk: {missing}"

        configured = {str(tree) for tree, _ in vamr.AGENT_TREES}
        assert configured == EXPECTED_TREES

        result = vamr.scan(REPO_ROOT)
        assert {str(tree) for tree in result.trees_scanned} == EXPECTED_TREES

    def test_the_four_documented_sibling_documents_stay_out_of_the_roster(self):
        """The frontmatter rule must hold against the real trees, not a fixture.

        These four documents live beside agents in trees whose suffix is a bare
        ``.md``. Suffix matching alone admitted all four, and only three of them
        are uppercase, so the case rule that preceded this could not have caught
        ``claude-instructions.template``.

        This is the named-regression check. The complete check, over every file
        rather than four names, is
        ``test_every_roster_matches_an_independent_frontmatter_oracle``.
        """
        result = vamr.scan(REPO_ROOT)
        leaked = {
            f"{tree}:{name}"
            for tree, names in result.agents_by_tree.items()
            for name in names
            if name in {"AGENTS", "CLAUDE", "README", "claude-instructions.template"}
        }
        assert not leaked, f"non-agent documents in the roster: {leaked}"

    def test_every_roster_matches_an_independent_frontmatter_oracle(self):
        """Check every suffix-matching file, not a list of names known to leak.

        A named list only proves the four documents someone already found are
        excluded. It says nothing about the fifth. This walks every file in
        every tree and compares roster membership against an oracle written a
        different way: a line scan plus a real YAML parse, rather than the
        module's regexes. Agreement on all 179 suffix-matching files is what
        makes the membership rule a rule rather than a denylist.
        """
        result = vamr.scan(REPO_ROOT)
        checked = 0
        disagreements = []
        for tree, suffix in vamr.AGENT_TREES:
            roster = result.agents_by_tree[tree]
            for path in sorted((REPO_ROOT / tree).glob(f"*{suffix}")):
                name = path.name[: -len(suffix)]
                if not name:
                    continue
                checked += 1
                if (name in roster) != _has_agent_frontmatter(path):
                    disagreements.append(str(path.relative_to(REPO_ROOT)))
        assert not disagreements, f"roster disagrees with the oracle on: {disagreements}"
        assert checked >= 175, f"oracle only examined {checked} files"

    def test_every_configured_tree_yields_agents(self):
        """Guard against a suffix that stops matching what a tree ships.

        A wrong suffix yields an empty roster, and an empty roster makes every
        citation in that tree look broken or, before the degeneracy guard, makes
        the tree silently contribute nothing.
        """
        result = vamr.scan(REPO_ROOT)
        assert result.trees_scanned, "no configured tree exists on disk"
        for tree in result.trees_scanned:
            assert result.agents_by_tree[tree], f"{tree} yielded no agent names"

    def test_orchestrator_matrix_is_scanned(self):
        """The matrix this validator was written for must be in the results."""
        result = vamr.scan(REPO_ROOT)
        names = {str(p) for p in result.files_with_matrix}
        assert any("orchestrator" in n for n in names)
