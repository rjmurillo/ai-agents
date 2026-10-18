"""Issue #5280: adr-generator regenerates the ADR index before hand-off."""

from pathlib import Path

SKILL = Path(".claude/skills/adr-generator/SKILL.md")
COMMAND = "uv run python build/scripts/generate_adr_index.py"
ORIGIN_CHECK = "git remote get-url origin | grep -Eq '(^|[/:])rjmurillo/ai-agents(\\.git)?/?$'"
GENERATOR = "build/scripts/generate_adr_index.py"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _hand_off_section(text: str) -> str:
    start = text.index("### Phase G6: Hand Off")
    return text[start : text.index("\n---", start)]


def test_hand_off_runs_the_generator_before_review() -> None:
    section = _hand_off_section(_text())

    flat = " ".join(section.split())
    assert COMMAND in section
    assert "refresh the ADR index, then hand the ADR" in flat


def test_refresh_runs_after_the_gates_that_may_edit_the_adr() -> None:
    text = _text()

    assert text.index("## Mandatory Exit Gates") < text.index(COMMAND)


def test_refresh_is_skipped_when_the_generator_is_absent() -> None:
    section = _hand_off_section(_text())

    assert f"`{GENERATOR}` does not exist" in section
    assert "skip" in section.lower()


def test_marker_names_every_path_the_refresh_prose_references() -> None:
    text = _text()
    marker_start = text.index("<!-- vendor-portability:")
    marker = text[marker_start : text.index("-->", marker_start)]

    assert GENERATOR in marker


def test_verification_checklist_covers_the_refresh() -> None:
    text = _text()
    checklist = text[text.index("## Verification") :]

    assert f"`{GENERATOR}`" in checklist
    assert "Phase G6" in checklist


def test_refresh_runs_only_in_this_repository() -> None:
    """Issue #6506: a consumer checkout's same-named script must never run."""
    section = _hand_off_section(_text())

    assert ORIGIN_CHECK in section
    assert section.index(ORIGIN_CHECK) < section.index(COMMAND)
    assert "Run it only in the `rjmurillo/ai-agents` repository" in section


def test_the_command_is_chained_behind_both_guards() -> None:
    section = _hand_off_section(_text())
    block = section[section.index(ORIGIN_CHECK) : section.index(COMMAND) + len(COMMAND)]

    assert block.count("&&") == 2
    assert f"test -f {GENERATOR}" in block


def test_refresh_guard_executes_as_documented(tmp_path: Path) -> None:
    """The documented guard runs the command in this repository and not elsewhere."""
    import subprocess

    section = _hand_off_section(_text())
    block = section[section.index(ORIGIN_CHECK) : section.index(COMMAND) + len(COMMAND)]
    guard = block.replace("\\\n", " ").replace(COMMAND, "echo RAN")
    cases = {
        "https://github.com/rjmurillo/ai-agents.git": True,
        "git@github.com:rjmurillo/ai-agents": True,
        "https://github.com/someone/other-repo.git": False,
        "https://github.com/notrjmurillo/ai-agents.git": False,
        "git@github.com:rjmurillo/ai-agents.git": True,
        "https://github.com/evil/rjmurillo/ai-agents-fork.git": False,
    }
    for url, expect_run in cases.items():
        repo = tmp_path / url.replace("/", "_").replace(":", "_")
        (repo / "build" / "scripts").mkdir(parents=True)
        (repo / GENERATOR).write_text("", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)

        done = subprocess.run(
            ["sh", "-c", guard], cwd=repo, capture_output=True, text=True, check=False
        )

        assert ("RAN" in done.stdout) is expect_run, (url, done.stdout, done.stderr)
