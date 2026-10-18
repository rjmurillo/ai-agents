"""``build/scripts/agent_tree_copy.py``: the Cursor agent copy (ADR-115 Decision 2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import agent_tree_copy as atc  # noqa: E402
import generate_agents  # noqa: E402

KEEP = ["name", "description"]
READONLY_TOOLS = ["Read", "Grep", "mcp__github__issue_read", "mcp__serena__find_symbol"]


def _agent(frontmatter: str, body: str = "\n# Agent\n\nDoes things.\n") -> str:
    return f"---\n{frontmatter}---\n{body}"


# Readonly derivation ---------------------------------------------------------


@pytest.mark.parametrize(
    "tool",
    [
        "Read",
        "Glob",
        "Grep",
        "WebFetch",
        "mcp__github__get_file_contents",
        "mcp__github__issue_read",
        "mcp__github__pull_request_read",
        "mcp__github__list_commits",
        "mcp__github__get_workflow_run",
        "mcp__serena__read_memory",
        "mcp__serena__initial_instructions",
        "mcp__context7__resolve_library_id",
    ],
)
def test_read_only_tools_are_recognised(tool: str) -> None:
    assert atc.is_readonly_tool(tool)


@pytest.mark.parametrize(
    "tool",
    [
        "Write",
        "Edit",
        "Bash",
        "TodoWrite",
        "mcp__serena__write_memory",
        "mcp__serena__edit_memory",
        "mcp__serena__replace_content",
        "mcp__github__issue_write",
        "mcp__github__create_pull_request",
        "mcp__github__merge_pull_request",
        "mcp__serena__find_and_replace",
        "mcp__github__request_copilot_review",
        "mcp__db__query",
        "mcp__x__get_and_run",
        "mcp__x__list_and_send",
        "mcp__x__get_then_post",
        "mcp__x__get_and_dispatch",
        "mcp__x__get_or_run",
        "mcp__github__resolve_review_thread",
        "mcp__x__ask_and_close",
        "mcp__x__ask_question",
        "mcp__unknown",
        "mcp__server__",
        "",
        None,
        7,
    ],
)
def test_other_tools_are_not_read_only(tool: object) -> None:
    assert not atc.is_readonly_tool(tool)


def test_derive_readonly_requires_a_tools_list() -> None:
    assert atc.derive_readonly({"tools": READONLY_TOOLS})
    assert not atc.derive_readonly({})
    assert not atc.derive_readonly({"tools": []})
    assert atc.derive_readonly({"tools": "Read, Grep"})
    assert not atc.derive_readonly({"tools": ""})


def test_one_writing_tool_removes_readonly() -> None:
    assert not atc.derive_readonly({"tools": [*READONLY_TOOLS, "Write"]})


# Rendering -------------------------------------------------------------------


def test_render_keeps_listed_keys_in_order_and_the_body_verbatim() -> None:
    src = _agent(
        "name: demo\nmodel: haiku\nmodel-rationale: cost\nmetadata:\n  role: x\n"
        "# why\nisolation_required: true\nargument-hint: Do it\ndescription: 'Does: a thing'\n",
    )
    out = atc.render_agent(src, KEEP, derive_readonly_flag=True, source="demo.md")
    assert out == (
        "---\nname: demo\ndescription: 'Does: a thing'\n---\n\n# Agent\n\nDoes things.\n"
    )


def test_render_adds_readonly_when_every_tool_reads() -> None:
    src = _agent(
        "name: demo\ndescription: d\ntools:\n" + "".join(f"  - {t}\n" for t in READONLY_TOOLS)
    )
    out = atc.render_agent(src, KEEP, derive_readonly_flag=True, source="demo.md")
    assert out is not None
    assert yaml.safe_load(out.split("---")[1]) == {
        "name": "demo",
        "description": "d",
        "readonly": True,
    }


def test_render_omits_readonly_when_derivation_is_off() -> None:
    src = _agent("name: demo\ndescription: d\ntools:\n  - Read\n")
    out = atc.render_agent(src, KEEP, derive_readonly_flag=False, source="demo.md")
    assert out is not None
    assert "readonly" not in out


def test_render_omits_readonly_without_a_tools_list() -> None:
    out = atc.render_agent(
        _agent("name: d\ndescription: x\n"), KEEP, derive_readonly_flag=True, source="d.md"
    )
    assert out is not None
    assert "readonly" not in out


def test_render_skips_a_restricted_agent_readonly_cannot_express() -> None:
    src = _agent("name: d\ndescription: x\ntools:\n  - Read\n  - Write\n")
    assert atc.render_agent(src, KEEP, derive_readonly_flag=True, source="d.md") is None


def test_render_keeps_a_restricted_agent_when_derivation_is_off() -> None:
    src = _agent("name: d\ndescription: x\ntools:\n  - Read\n  - Write\n")
    assert atc.render_agent(src, KEEP, derive_readonly_flag=False, source="d.md") is not None


def test_inexpressible_restriction_needs_a_non_empty_tools_list() -> None:
    assert atc.has_inexpressible_restriction({"tools": ["Read", "Write"]})
    assert not atc.has_inexpressible_restriction({"tools": ["Read"]})
    assert not atc.has_inexpressible_restriction({})
    assert atc.has_inexpressible_restriction({"tools": []})
    assert atc.has_inexpressible_restriction({"tools": ""})
    assert atc.has_inexpressible_restriction({"tools": "Read, Write"})
    assert not atc.has_inexpressible_restriction({"tools": "Read, Grep"})
    assert not atc.has_inexpressible_restriction({"tools": None})


@pytest.mark.parametrize("bad", [{"a": 1}, 7, True, 1.5])
def test_declared_tools_rejects_non_list_non_string(bad: object) -> None:
    with pytest.raises(atc.AgentCopyError, match="list or a comma-separated string"):
        atc.declared_tools({"tools": bad})


def test_declared_tools_splits_and_strips_a_string() -> None:
    assert atc.declared_tools({"tools": " Read ,Grep,, "}) == ["Read", "Grep"]
    assert atc.declared_tools({"tools": ""}) == []
    assert atc.declared_tools({}) is None


def test_render_string_of_read_tools_earns_readonly() -> None:
    out = atc.render_agent(
        _agent("name: d\ndescription: x\ntools: Read, Grep\n"),
        KEEP, derive_readonly_flag=True, source="d.md",
    )  # fmt: skip
    assert out is not None
    assert "readonly: true" in out


def test_render_skips_a_string_with_a_writing_tool() -> None:
    src = _agent("name: d\ndescription: x\ntools: Read, Write\n")
    assert atc.render_agent(src, KEEP, derive_readonly_flag=True, source="d.md") is None


@pytest.mark.parametrize("value", ["[]", '""'])
def test_render_skips_empty_tools(value: str) -> None:
    src = _agent(f"name: d\ndescription: x\ntools: {value}\n")
    assert atc.render_agent(src, KEEP, derive_readonly_flag=True, source="d.md") is None


def test_render_errors_on_a_mapping_tools_value_naming_the_source() -> None:
    src = _agent("name: d\ndescription: x\ntools:\n  a: 1\n")
    with pytest.raises(atc.AgentCopyError, match=r"d\.md: `tools` must be"):
        atc.render_agent(src, KEEP, derive_readonly_flag=True, source="d.md")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("# no frontmatter\n", "no frontmatter"),
        ("---\n- a\n- b\n---\nbody\n", "not a mapping"),
        ("---\nname: [oops\n---\nbody\n", "unparseable"),
    ],
)
def test_render_rejects_bad_sources(text: str, message: str) -> None:
    with pytest.raises(atc.AgentCopyError, match=message):
        atc.render_agent(text, KEEP, derive_readonly_flag=False, source="bad.md")


def test_render_does_not_invent_a_missing_listed_key() -> None:
    out = atc.render_agent(_agent("name: only\n"), KEEP, derive_readonly_flag=False, source="o.md")
    assert out.startswith("---\nname: only\n---\n")


# Generator -------------------------------------------------------------------


def _config(tmp_path: Path, extra: str = "") -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  agents:
    sourceDir: "src_agents"
    outputDir: "out_agents"
    frontmatterKeep: [name, description]
    deriveReadonly: true
{extra}""",
        encoding="utf-8",
    )
    return cfg


def _source(tmp_path: Path, name: str, text: str) -> None:
    folder = tmp_path / "src_agents"
    folder.mkdir(exist_ok=True)
    (folder / f"{name}.md").write_text(text, encoding="utf-8")


def test_copy_writes_each_agent_and_prunes_orphans(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\nmodel: haiku\n"))
    (tmp_path / "out_agents").mkdir()
    (tmp_path / "out_agents" / "stale.md").write_text("old", encoding="utf-8")
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path))
    assert result is not None
    assert (result.inputs, result.written, result.pruned) == (1, 1, 1)
    assert not (tmp_path / "out_agents" / "stale.md").exists()
    assert "model" not in (tmp_path / "out_agents" / "a.md").read_text(encoding="utf-8")


RESTRICTED = _agent("name: r\ndescription: R\ntools:\n  - Read\n  - Write\n")


def test_restricted_non_readonly_agent_is_skipped_with_a_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _source(tmp_path, "r", RESTRICTED)
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path))
    assert result is not None
    assert (result.inputs, result.written, result.skipped) == (2, 1, ["r.md"])
    assert not (tmp_path / "out_agents" / "r.md").exists()
    assert "SKIPPED: r.md" in capsys.readouterr().out


def test_stale_copy_of_a_skipped_agent_is_pruned(tmp_path: Path) -> None:
    _source(tmp_path, "r", RESTRICTED)
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    (tmp_path / "out_agents").mkdir()
    stale = tmp_path / "out_agents" / "r.md"
    stale.write_text("old copy", encoding="utf-8")
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path))
    assert result is not None
    assert result.pruned == 1
    assert not stale.exists()


def test_check_reports_a_stale_copy_of_a_skipped_agent_as_drift(tmp_path: Path) -> None:
    _source(tmp_path, "r", RESTRICTED)
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    atc.generate_agent_copies(tmp_path, _config(tmp_path))
    stale = tmp_path / "out_agents" / "r.md"
    stale.write_text("old copy", encoding="utf-8")
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path), check=True)
    assert result is not None
    assert result.drift == [stale.as_posix()]
    assert stale.exists()


def test_read_only_agent_is_emitted_with_readonly_true(tmp_path: Path) -> None:
    _source(tmp_path, "ro", _agent("name: ro\ndescription: R\ntools:\n  - Read\n  - Grep\n"))
    atc.generate_agent_copies(tmp_path, _config(tmp_path))
    text = (tmp_path / "out_agents" / "ro.md").read_text(encoding="utf-8")
    assert yaml.safe_load(text.split("---")[1])["readonly"] is True


def test_agent_without_tools_is_emitted_without_readonly(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("name: free\ndescription: F\n"))
    atc.generate_agent_copies(tmp_path, _config(tmp_path))
    text = (tmp_path / "out_agents" / "free.md").read_text(encoding="utf-8")
    assert "readonly" not in text


def test_restricted_agent_ships_when_derivation_is_off(tmp_path: Path) -> None:
    _source(tmp_path, "r", RESTRICTED)
    config = (
        _config(tmp_path)
        .read_text(encoding="utf-8")
        .replace("deriveReadonly: true", "deriveReadonly: false")
    )
    off = tmp_path / "off.yaml"
    off.write_text(config, encoding="utf-8")
    atc.generate_agent_copies(tmp_path, off)
    assert (tmp_path / "out_agents" / "r.md").is_file()


def test_copy_is_idempotent(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    atc.generate_agent_copies(tmp_path, _config(tmp_path))
    second = atc.generate_agent_copies(tmp_path, _config(tmp_path))
    assert second is not None
    assert (second.written, second.pruned, second.drift) == (0, 0, [])


def test_check_reports_drift_and_writes_nothing(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path), check=True)
    assert result is not None
    assert len(result.drift) == 1
    assert not (tmp_path / "out_agents").exists()


def test_check_reports_a_stale_extra_file_without_deleting_it(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    atc.generate_agent_copies(tmp_path, _config(tmp_path))
    extra = tmp_path / "out_agents" / "extra.md"
    extra.write_text("x", encoding="utf-8")
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path), check=True)
    assert result is not None
    assert result.drift == [extra.as_posix()]
    assert extra.exists()


def test_what_if_writes_nothing(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path), what_if=True)
    assert result is not None
    assert result.written == 0
    assert not (tmp_path / "out_agents").exists()


def test_no_regen_sentinel_is_honored(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    (tmp_path / "out_agents").mkdir()
    target = tmp_path / "out_agents" / "a.md"
    target.write_text("<!-- NO-REGEN -->\nhand edit\n", encoding="utf-8")
    atc.generate_agent_copies(tmp_path, _config(tmp_path))
    assert target.read_text(encoding="utf-8") == "<!-- NO-REGEN -->\nhand edit\n"


def test_excluded_names_are_skipped(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    _source(tmp_path, "AGENTS", "# guide\n")
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path))
    assert result is not None
    assert result.inputs == 1
    assert not (tmp_path / "out_agents" / "AGENTS.md").exists()


def test_platform_without_the_key_is_not_a_tree_copy(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text(
        'schemaVersion: "1.0"\nprovider: t\nartifacts:\n  agents:\n    outputDir: "x"\n',
        encoding="utf-8",
    )
    assert atc.generate_agent_copies(tmp_path, cfg) is None
    assert not atc.uses_agent_tree_copy({"outputDir": "x"})
    assert not atc.uses_agent_tree_copy(None)
    assert atc.uses_agent_tree_copy({"frontmatterKeep": ["name"]})


def test_missing_source_dir_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(atc.AgentCopyError, match="sourceDir not found"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path))


def test_empty_source_dir_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "src_agents").mkdir()
    with pytest.raises(atc.AgentCopyError, match="no agent files"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path))


@pytest.mark.parametrize("bad", ["frontmatterKeep: []", "frontmatterKeep: name"])
def test_bad_keep_list_is_an_error(tmp_path: Path, bad: str) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    cfg = (
        _config(tmp_path)
        .read_text(encoding="utf-8")
        .replace("frontmatterKeep: [name, description]", bad)
    )
    (tmp_path / "bad.yaml").write_text(cfg, encoding="utf-8")
    with pytest.raises(atc.AgentCopyError, match="frontmatterKeep"):
        atc.generate_agent_copies(tmp_path, tmp_path / "bad.yaml")


def test_traversing_output_dir_is_an_error(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    text = _config(tmp_path).read_text(encoding="utf-8").replace('"out_agents"', '"../escape"')
    (tmp_path / "bad.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(atc.AgentCopyError):
        atc.generate_agent_copies(tmp_path, tmp_path / "bad.yaml")
    assert not (tmp_path.parent / "escape").exists()


def test_bad_exclude_list_is_an_error(tmp_path: Path) -> None:
    _source(tmp_path, "a", _agent("name: a\ndescription: A\n"))
    with pytest.raises(atc.AgentCopyError, match="excludeFilenames"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, "    excludeFilenames: nope\n"))


# Copilot generator leaves tree-copy platforms alone ----------------------------


def test_generate_agents_skips_a_tree_copy_platform(tmp_path: Path) -> None:
    templates = tmp_path / "templates"
    (templates / "platforms").mkdir(parents=True)
    (templates / "agents").mkdir()
    (templates / "agents" / "a.shared.md").write_text(
        "---\nname: a\ndescription: A\n---\n# A\n", encoding="utf-8"
    )
    (templates / "platforms" / "cursor.yaml").write_text(
        'schemaVersion: "1.0"\nprovider: cursor\nartifacts:\n  agents:\n'
        '    sourceDir: "src/claude/agents"\n    outputDir: "src/cursor/agents"\n'
        "    frontmatterKeep: [name]\n",
        encoding="utf-8",
    )
    rc = generate_agents.generate_agents(templates, tmp_path / "src", tmp_path)
    assert rc == 0
    assert not (tmp_path / "src" / "cursor").exists()


# Committed tree --------------------------------------------------------------


def test_committed_cursor_agents_match_the_claude_agents() -> None:
    source = sorted((REPO_ROOT / "src" / "claude" / "agents").glob("*.md"))
    copied = sorted((REPO_ROOT / "src" / "cursor" / "agents").glob("*.md"))
    shipped = [p.name for p in source if p.name not in {"AGENTS.md", "CLAUDE.md"}]
    restricted = [
        n
        for n in shipped
        if atc.has_inexpressible_restriction(
            yaml.safe_load(
                (REPO_ROOT / "src" / "claude" / "agents" / n)
                .read_text(encoding="utf-8")
                .split("---")[1]
            )
        )
    ]
    assert restricted == ["security.md"]
    assert [p.name for p in copied] == [n for n in shipped if n not in restricted]
    for path in copied:
        frontmatter = yaml.safe_load(path.read_text(encoding="utf-8").split("---")[1])
        assert set(frontmatter) <= {"name", "description", "readonly"}, path.name
        assert frontmatter["name"] == path.stem


def test_committed_readonly_agents_are_exactly_the_read_only_ones() -> None:
    readonly = {
        p.stem
        for p in (REPO_ROOT / "src" / "cursor" / "agents").glob("*.md")
        if "readonly: true" in p.read_text(encoding="utf-8").split("---")[1]
    }
    assert readonly == {"analyst", "code-reviewer", "comment-analyzer"}


@pytest.mark.parametrize("agent", ["analyst", "code-reviewer", "comment-analyzer"])
def test_adr107_agents_render_to_cursor_readonly(agent: str) -> None:
    """Server wildcards do not stop the ADR-107 agents shipping as `readonly: true`."""
    text = (REPO_ROOT / "src" / "claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")

    rendered = atc.render_agent(
        text, ["name", "description"], derive_readonly_flag=True, source=agent
    )

    assert rendered is not None
    assert "readonly: true" in rendered.split("---")[1]


def test_wildcard_with_read_builtins_is_readonly() -> None:
    assert atc.derive_readonly({"tools": ["Read", "mcp__serena__*", "ToolSearch"]})
    assert atc.has_inexpressible_restriction({"tools": ["Write", "mcp__serena__*"]})


def test_wildcard_does_not_hide_a_write_builtin() -> None:
    assert not atc.derive_readonly({"tools": ["Read", "Write", "mcp__serena__*"]})
