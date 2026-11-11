"""``agent_tree_copy.py`` Codex output (issue #7226, ADR-115 Decision 7 amendment).

Covers ``skipToolRestricted``, the appended paragraph, ``outputFormat: codex-toml``,
the TOML escaper, suffix-aware prune, and the committed ``src/codex/agents`` files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import agent_toml  # noqa: E402
import agent_tree_copy as atc  # noqa: E402
import validate_templates_schema as vts  # noqa: E402

KEYS = ["name", "description", "developer_instructions"]


def _agent(name: str, extra: str = "", body: str = "\n# Agent\n\nDoes things.\n") -> str:
    return f"---\nname: {name}\ndescription: Does {name}\n{extra}---\n{body}"


def _config(tmp_path: Path, extra: str = "", keep: str = "[name, description]") -> Path:
    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        f"""\
schemaVersion: "1.0"
provider: "test"
artifacts:
  agents:
    sourceDir: "src_agents"
    outputDir: "out_agents"
    frontmatterKeep: {keep}
    outputFormat: codex-toml
    skipToolRestricted: true
{extra}""",
        encoding="utf-8",
    )
    return cfg


def _source(tmp_path: Path, stem: str, text: str) -> None:
    folder = tmp_path / "src_agents"
    folder.mkdir(exist_ok=True)
    (folder / f"{stem}.md").write_text(text, encoding="utf-8")


def _out(tmp_path: Path) -> Path:
    return tmp_path / "out_agents"


def _generate(tmp_path: Path, **kwargs: bool) -> atc.AgentCopyResult:
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path), **kwargs)
    assert result is not None
    return result


# toml_basic_string ------------------------------------------------------------

_HOSTILE = (
    'quote " triple """ back \\ tab \t del \x7f nul \x00 bell \x07 cr \r lf \n ff \f bs \b 😀 é'
)


def _roundtrip(value: str) -> str:
    return tomllib.loads(f"k = {agent_toml.toml_basic_string(value)}\n")["k"]


def test_escaper_round_trips_hostile_text_exactly() -> None:
    assert _roundtrip(_HOSTILE) == _HOSTILE


@pytest.mark.parametrize("char", [chr(c) for c in [*range(0x20), 0x7F]])
def test_escaper_round_trips_every_control_character(char: str) -> None:
    assert _roundtrip(char) == char


def test_escaper_keeps_non_ascii_raw_and_escapes_controls() -> None:
    out = agent_toml.toml_basic_string("😀é\x7f\t")
    assert out == '"😀é\\u007F\\t"'
    assert "\n" not in agent_toml.toml_basic_string("a\nb")


def test_json_dumps_is_not_a_valid_toml_escaper() -> None:
    """Negative control: each json.dumps mode breaks TOML, so the round-trip tests can fail."""
    with pytest.raises(tomllib.TOMLDecodeError):  # raw U+007F
        tomllib.loads(f"k = {json.dumps(chr(0x7F), ensure_ascii=False)}\n")
    with pytest.raises(tomllib.TOMLDecodeError):  # surrogate-pair escape for an emoji
        tomllib.loads(f"k = {json.dumps(chr(0x1F600), ensure_ascii=True)}\n")
    assert _roundtrip(chr(0x7F) + chr(0x1F600)) == chr(0x7F) + chr(0x1F600)


# skipToolRestricted and the appended paragraph --------------------------------


def test_tool_restricted_agent_is_skipped_and_others_ship(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _source(tmp_path, "locked", _agent("locked", "tools: Read, Grep\n"))
    _source(tmp_path, "listed", _agent("listed", "tools:\n  - Read\n"))
    _source(tmp_path, "empty", _agent("empty", "tools: ''\n"))
    result = _generate(tmp_path)
    assert sorted(p.name for p in _out(tmp_path).iterdir()) == ["free.toml"]
    assert result.skipped == ["empty.md", "listed.md", "locked.md"]


def test_paragraph_lists_the_derived_sorted_skip_list_in_every_body(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _source(tmp_path, "other", _agent("other"))
    _source(tmp_path, "zeta", _agent("zeta", "tools: Read\n"))
    _source(tmp_path, "alpha", _agent("alpha", "tools: Read\n"))
    _generate(tmp_path)
    for stem in ("free", "other"):
        text = tomllib.loads((_out(tmp_path) / f"{stem}.toml").read_text(encoding="utf-8"))
        body = text["developer_instructions"]
        assert "## Agents not installed on this host" in body
        assert "`alpha`, `zeta`" in body
        assert body.count("Agents not installed") == 1


def test_no_paragraph_when_nothing_is_skipped(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _generate(tmp_path)
    parsed = tomllib.loads((_out(tmp_path) / "free.toml").read_text(encoding="utf-8"))
    assert "not installed" not in parsed["developer_instructions"]
    assert parsed["developer_instructions"] == "\n# Agent\n\nDoes things.\n"


def test_paragraph_text_comes_from_the_skip_list_argument() -> None:
    assert "`b`, `x`" in agent_toml.not_installed_paragraph(["x", "b"])
    assert "`zz`" not in agent_toml.not_installed_paragraph(["x", "b"])


def test_stale_toml_of_a_newly_skipped_agent_is_pruned(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _source(tmp_path, "was_ok", _agent("was_ok"))
    _generate(tmp_path)
    assert (_out(tmp_path) / "was_ok.toml").is_file()
    _source(tmp_path, "was_ok", _agent("was_ok", "tools: Read\n"))
    result = _generate(tmp_path)
    assert result.pruned == 1
    assert not (_out(tmp_path) / "was_ok.toml").exists()


def test_check_reports_a_stale_toml_and_deletes_nothing(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _generate(tmp_path)
    stale = _out(tmp_path) / "ghost.toml"
    stale.write_text("name = 'ghost'\n", encoding="utf-8")
    result = _generate(tmp_path, check=True)
    assert result.drift == [stale.as_posix()]
    assert stale.exists()


def test_check_is_clean_after_a_write(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _source(tmp_path, "locked", _agent("locked", "tools: Read\n"))
    _generate(tmp_path)
    assert _generate(tmp_path, check=True).drift == []


def test_a_symlinked_output_dir_is_refused_and_nothing_is_deleted(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    keep = elsewhere / "users-own.toml"
    keep.write_text("name = 'mine'\n", encoding="utf-8")
    try:
        _out(tmp_path).symlink_to(elsewhere, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(atc.AgentCopyError, match="symlink"):
        _generate(tmp_path)
    assert keep.exists()
    assert not (elsewhere / "free.toml").exists()


def test_a_plain_output_dir_is_still_written(tmp_path: Path) -> None:
    """Negative control for the symlink refusal."""
    _source(tmp_path, "free", _agent("free"))
    _generate(tmp_path)
    assert (_out(tmp_path) / "free.toml").exists()


def test_markdown_md_files_in_a_toml_output_dir_are_not_pruned(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _out(tmp_path).mkdir()
    (_out(tmp_path) / "note.md").write_text("keep", encoding="utf-8")
    _generate(tmp_path)
    assert (_out(tmp_path) / "note.md").exists()


def test_body_replace_applies_before_toml_serialization(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free", body='\nHand to the "security" agent.\n'))
    extra = '    bodyReplace:\n      free.md:\n        "Hand to the": "Report to the"\n'
    atc.generate_agent_copies(tmp_path, _config(tmp_path, extra))
    parsed = tomllib.loads((_out(tmp_path) / "free.toml").read_text(encoding="utf-8"))
    assert parsed["developer_instructions"] == '\nReport to the "security" agent.\n'


def test_body_replace_naming_a_skipped_agent_fails(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    _source(tmp_path, "locked", _agent("locked", "tools: Read\n", "\nx y\n"))
    extra = '    bodyReplace:\n      locked.md:\n        "x": "z"\n'
    with pytest.raises(atc.AgentCopyError, match="skipped"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, extra))


def test_toml_has_exactly_three_keys_in_order(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free", "model: haiku\nmetadata: {a: 1}\n"))
    _generate(tmp_path)
    assert list(tomllib.loads((_out(tmp_path) / "free.toml").read_text(encoding="utf-8"))) == KEYS


# name and stem ------------------------------------------------------------------


def test_name_that_differs_from_the_file_stem_fails(tmp_path: Path) -> None:
    _source(tmp_path, "file-stem", _agent("other-name"))
    with pytest.raises(atc.AgentCopyError, match="differs from file stem"):
        _generate(tmp_path)
    assert not _out(tmp_path).exists()


def test_missing_name_fails(tmp_path: Path) -> None:
    _source(tmp_path, "x", "---\ndescription: d\n---\nbody\n")
    with pytest.raises(atc.AgentCopyError):
        _generate(tmp_path)


def test_non_string_description_fails_for_toml(tmp_path: Path) -> None:
    _source(tmp_path, "x", "---\nname: x\ndescription: 12\n---\nbody\n")
    with pytest.raises(atc.AgentCopyError, match="must be a string"):
        _generate(tmp_path)


def test_a_skipped_agent_with_a_mismatched_name_also_fails(tmp_path: Path) -> None:
    """Every source agent is name-checked, shipped or skipped."""
    _source(tmp_path, "free", _agent("free"))
    _source(tmp_path, "locked", _agent("different", "tools: Read\n"))
    with pytest.raises(atc.AgentCopyError, match="differs from file stem"):
        _generate(tmp_path)


def test_check_names_match_stems_accepts_matching_names_and_rejects_others() -> None:
    agent_toml.check_names_match_stems([("a", "a"), ("b", "b")])
    with pytest.raises(agent_toml.CodexOutputError, match="'x'"):
        agent_toml.check_names_match_stems([("a", "a"), ("b", "x")])
    with pytest.raises(agent_toml.CodexOutputError):
        agent_toml.check_names_match_stems([("a", None)])


def test_markdown_format_also_checks_names(tmp_path: Path) -> None:
    _source(tmp_path, "file-stem", _agent("other"))
    cfg = _config(tmp_path)
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("    outputFormat: codex-toml\n", ""))
    with pytest.raises(atc.AgentCopyError, match="differs from file stem"):
        atc.generate_agent_copies(tmp_path, cfg)


# stanza validation (runtime) -----------------------------------------------------


@pytest.mark.parametrize("keep", ["[name]", "[description, name]", "[name, description, model]"])
def test_codex_toml_rejects_other_keep_lists(tmp_path: Path, keep: str) -> None:
    _source(tmp_path, "free", _agent("free"))
    with pytest.raises(atc.AgentCopyError, match="exactly"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, keep=keep))


def test_unknown_output_format_fails(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    cfg = _config(tmp_path)
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("codex-toml", "yaml"))
    with pytest.raises(atc.AgentCopyError, match="outputFormat"):
        atc.generate_agent_copies(tmp_path, cfg)


def test_skip_with_derive_readonly_fails(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    with pytest.raises(atc.AgentCopyError, match="deriveReadonly"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, "    deriveReadonly: true\n"))


def test_non_boolean_skip_fails(tmp_path: Path) -> None:
    _source(tmp_path, "free", _agent("free"))
    cfg = _config(tmp_path)
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace(
            "skipToolRestricted: true", 'skipToolRestricted: "yes"'
        )
    )
    with pytest.raises(atc.AgentCopyError, match="boolean"):
        atc.generate_agent_copies(tmp_path, cfg)


def test_markdown_default_is_unchanged_by_the_new_keys() -> None:
    text = _agent("a", body="\nBody\n")
    out = atc.render_agent(text, ["name", "description"], derive_readonly_flag=False, source="a.md")
    assert out == "---\nname: a\ndescription: Does a\n---\n\nBody\n"


def test_appendix_is_added_to_a_markdown_body() -> None:
    loaded, body = atc.parse_agent(_agent("a", body="\nBody\n"), "a.md")
    spec = atc.RenderSpec(["name"], appendix=agent_toml.not_installed_paragraph(["z"]))
    out = atc.render_parsed(loaded, body, "a.md", spec)
    assert out is not None and out.endswith("judge the artifact itself.\n") and "`z`" in out


def test_paragraph_adds_the_security_sentence_only_when_security_is_skipped() -> None:
    with_security = agent_toml.not_installed_paragraph(["analyst", "security"])
    assert "no security agent reviewed it" in with_security
    assert "no security agent reviewed it" not in agent_toml.not_installed_paragraph(["analyst"])


# schema validation ----------------------------------------------------------------


def _agents(**extra: object) -> dict[str, object]:
    return {"sourceDir": "src/claude/agents", "outputDir": "src/x/agents", **extra}


def _errors(stanza: dict[str, object]) -> list[str]:
    return vts._validate_artifact_stanza("agents", stanza)


def test_schema_accepts_the_codex_stanza() -> None:
    stanza = _agents(
        frontmatterKeep=["name", "description"], outputFormat="codex-toml", skipToolRestricted=True
    )
    assert _errors(stanza) == []


@pytest.mark.parametrize("key", ["skipToolRestricted", "outputFormat"])
def test_schema_rejects_the_new_keys_without_keep(key: str) -> None:
    value = True if key == "skipToolRestricted" else "codex-toml"
    errors = _errors(_agents(**{key: value}))
    assert any("requires `frontmatterKeep`" in e for e in errors)


def test_schema_rejects_skip_with_derive_readonly() -> None:
    stanza = _agents(frontmatterKeep=["name"], skipToolRestricted=True, deriveReadonly=True)
    assert any("deriveReadonly" in e for e in _errors(stanza))


def test_schema_allows_skip_with_derive_readonly_false() -> None:
    stanza = _agents(frontmatterKeep=["name"], skipToolRestricted=True, deriveReadonly=False)
    assert _errors(stanza) == []


@pytest.mark.parametrize("value", ["yes", 1, None, []])
def test_schema_requires_boolean_skip(value: object) -> None:
    stanza = _agents(frontmatterKeep=["name"], skipToolRestricted=value)
    assert any("skipToolRestricted" in e for e in _errors(stanza))


@pytest.mark.parametrize("value", ["toml", "Markdown", "", None, 3])
def test_schema_rejects_unknown_output_format(value: object) -> None:
    stanza = _agents(frontmatterKeep=["name", "description"], outputFormat=value)
    assert any("outputFormat" in e for e in _errors(stanza))


def test_schema_accepts_markdown_output_format() -> None:
    assert _errors(_agents(frontmatterKeep=["name"], outputFormat="markdown")) == []


@pytest.mark.parametrize("keep", [["name"], ["description", "name"], ["name", "description", "x"]])
def test_schema_codex_toml_needs_exact_keep(keep: list[str]) -> None:
    errors = _errors(_agents(frontmatterKeep=keep, outputFormat="codex-toml"))
    assert any("[name, description]" in e for e in errors)
