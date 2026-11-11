"""``agent_tree_copy.py`` body replacement (issue #7226).

Cursor ships no ``security`` agent, so the Cursor platform file rewords the lines
that hand work to one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "build"))

import agent_tree_copy as atc  # noqa: E402


def _agent(frontmatter: str, body: str = "\n# Agent\n\nDoes things.\n") -> str:
    return f"---\n{frontmatter}---\n{body}"


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


def _replace_extra(*entries: tuple[str, str, str]) -> str:
    lines = ["    bodyReplace:"]
    for file, old, new in entries:
        lines += [f"      {file}:", f"        {old!r}: {new!r}"]
    return "\n".join(lines) + "\n"


def test_apply_replaces_text_that_occurs_once() -> None:
    out = atc.apply_body_replacements("a hand off b", [("hand off", "report")], "x.md")
    assert out == "a report b"


def test_apply_can_delete_a_table_row() -> None:
    text = "| a | b |\n| **security** | c |\n| d | e |\n"
    out = atc.apply_body_replacements(text, [("| **security** | c |\n", "")], "x.md")
    assert out == "| a | b |\n| d | e |\n"


@pytest.mark.parametrize("text", ["nothing here", "hand off and hand off"])
def test_apply_rejects_text_that_is_absent_or_repeated(text: str) -> None:
    with pytest.raises(atc.AgentCopyError, match="expected 1"):
        atc.apply_body_replacements(text, [("hand off", "report")], "x.md")


def test_copy_applies_body_replace_to_the_named_agent_only(tmp_path: Path) -> None:
    body = "\nHand to the security agent.\n"
    _source(tmp_path, "one", _agent("name: one\ndescription: d\n", body))
    _source(tmp_path, "two", _agent("name: two\ndescription: d\n", body))
    extra = _replace_extra(("one.md", "Hand to the security agent.", "Tell the user."))
    atc.generate_agent_copies(tmp_path, _config(tmp_path, extra))
    assert "Tell the user." in (tmp_path / "out_agents" / "one.md").read_text(encoding="utf-8")
    assert "security agent" in (tmp_path / "out_agents" / "two.md").read_text(encoding="utf-8")


def test_check_reports_drift_when_a_replacement_is_not_applied(tmp_path: Path) -> None:
    _source(tmp_path, "one", _agent("name: one\ndescription: d\n", "\nold text\n"))
    cfg = _config(tmp_path)
    atc.generate_agent_copies(tmp_path, cfg)
    extra = _replace_extra(("one.md", "old text", "new text"))
    result = atc.generate_agent_copies(tmp_path, _config(tmp_path, extra), check=True)
    assert result is not None
    assert result.drift == [(tmp_path / "out_agents" / "one.md").as_posix()]


def test_stale_replacement_text_fails_the_copy(tmp_path: Path) -> None:
    _source(tmp_path, "one", _agent("name: one\ndescription: d\n", "\nbody\n"))
    extra = _replace_extra(("one.md", "gone text", "x"))
    with pytest.raises(atc.AgentCopyError, match="expected 1"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, extra))


def test_replacement_for_a_missing_agent_fails_the_copy(tmp_path: Path) -> None:
    _source(tmp_path, "one", _agent("name: one\ndescription: d\n"))
    extra = _replace_extra(("ghost.md", "a", "b"))
    with pytest.raises(atc.AgentCopyError, match="ghost.md"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, extra))


@pytest.mark.parametrize(
    "extra",
    [
        "    bodyReplace: nope\n",
        "    bodyReplace: [1]\n",
        "    bodyReplace:\n      a.md: nope\n",
        "    bodyReplace:\n      a.md: {}\n",
        "    bodyReplace:\n      a.md: {'': y}\n",
        "    bodyReplace:\n      a.md: {x: 3}\n",
    ],
)
def test_bad_body_replace_is_an_error(tmp_path: Path, extra: str) -> None:
    _source(tmp_path, "one", _agent("name: one\ndescription: d\n"))
    with pytest.raises(atc.AgentCopyError, match="bodyReplace"):
        atc.generate_agent_copies(tmp_path, _config(tmp_path, extra))


def test_cursor_agents_do_not_hand_work_to_an_agent_cursor_does_not_ship() -> None:
    claude = {p.stem for p in (REPO_ROOT / "src" / "claude" / "agents").glob("*.md")}
    cursor_dir = REPO_ROOT / "src" / "cursor" / "agents"
    cursor = {p.stem for p in cursor_dir.glob("*.md")}
    unshipped = claude - cursor - {"AGENTS", "CLAUDE"}
    assert "security" in unshipped
    for path in cursor_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for name in unshipped:
            assert f"{name} agent" not in text, f"{path.name} names the {name} agent"
            assert f"| **{name}** |" not in text, f"{path.name} lists the {name} agent"
