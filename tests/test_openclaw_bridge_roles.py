"""Role resolution in the OpenClaw bridge (issue #5130).

Split out of tests/test_openclaw_bridge.py, which crossed the 500-line
taste-lint ceiling when these cases were added. The split is by concern, not
just by size: everything here exercises `_resolve_role` and `_read_declared_role`,
which turn frontmatter into an exported role, while the parent module covers
export shape, workspace writing, and the CLI.

The field exists in two frontmatter shapes. The shared templates and the
generated trees put it at the top level; the Claude-side install copies nest it
under `metadata:`. Reading only the top level silently mapped every
nested-shape agent to the fallback role, so these tests cover both, with a
negative control for a file still carrying the pre-migration `metadata.tier`.
"""

from __future__ import annotations

import logging
import textwrap

import pytest

from scripts.openclaw_bridge import parse_agent_file


class TestResolveRole:
    def test_defaults_model_and_role(self, tmp_path):
        content = textwrap.dedent("""\
            ---
            name: minimal
            description: Minimal agent.
            ---
            # Body
        """)
        md_file = tmp_path / "minimal.md"
        md_file.write_text(content, encoding="utf-8")
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.model == "sonnet"
        assert result.role == "support"

    @pytest.mark.parametrize(
        "role",
        ["strategic", "coordinator", "executor", "support"],
    )
    def test_accepts_every_known_role(self, tmp_path, role):
        md_file = tmp_path / f"{role}.md"
        md_file.write_text(
            textwrap.dedent(f"""\
                ---
                name: agent
                description: An agent.
                role: {role}
                ---
                # Body
            """),
            encoding="utf-8",
        )
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == role

    def test_unknown_role_falls_back_and_warns(self, tmp_path, caplog):
        md_file = tmp_path / "typo.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: agent
                description: An agent.
                role: buidler
                ---
                # Body
            """),
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING):
            result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "support"
        assert "buidler" in caplog.text

    def test_non_string_role_falls_back_and_warns(self, tmp_path, caplog):
        md_file = tmp_path / "listy.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: agent
                description: An agent.
                role:
                  - executor
                ---
                # Body
            """),
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING):
            result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "support"
        assert "Unrecognized role" in caplog.text

    def test_role_surrounding_whitespace_is_stripped(self, tmp_path):
        md_file = tmp_path / "spaced.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: agent
                description: An agent.
                role: "  executor  "
                ---
                # Body
            """),
            encoding="utf-8",
        )
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "executor"

    def test_reads_role_nested_under_metadata(self, tmp_path):
        """The Claude-side install copies nest the field under ``metadata:``.

        Reading only the top level mapped every nested-shape agent to the
        fallback role, so .claude/agents/architect.md declared `strategic` and
        exported as `support`.
        """
        md_file = tmp_path / "architect.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: architect
                description: An agent.
                metadata:
                  tier_note: kept to prove sibling keys survive
                  role: strategic
                ---
                # Body
            """),
            encoding="utf-8",
        )
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "strategic"

    def test_top_level_role_wins_over_nested(self, tmp_path):
        md_file = tmp_path / "both.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: both
                description: An agent.
                role: executor
                metadata:
                  role: strategic
                ---
                # Body
            """),
            encoding="utf-8",
        )
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "executor"

    def test_unmigrated_nested_tier_does_not_become_a_role(self, tmp_path):
        """A file still carrying ``metadata.tier`` must not resolve to a role.

        Negative control for the mid-migration shape: the old key is not a
        role source, so this falls back rather than reading `expert`.
        """
        md_file = tmp_path / "stale.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: stale
                description: An agent.
                metadata:
                  tier: expert
                ---
                # Body
            """),
            encoding="utf-8",
        )
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "support"

    def test_unrecognized_nested_role_warns(self, tmp_path, caplog):
        md_file = tmp_path / "typo-nested.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: typo
                description: An agent.
                metadata:
                  role: stratgic
                ---
                # Body
            """),
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING):
            result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "support"
        assert "stratgic" in caplog.text

    def test_non_mapping_metadata_falls_back(self, tmp_path):
        """``metadata:`` as a scalar must not raise on the nested lookup."""
        md_file = tmp_path / "scalar-metadata.md"
        md_file.write_text(
            textwrap.dedent("""\
                ---
                name: scalar
                description: An agent.
                metadata: not-a-mapping
                ---
                # Body
            """),
            encoding="utf-8",
        )
        result = parse_agent_file(md_file)
        assert result is not None
        assert result.role == "support"
