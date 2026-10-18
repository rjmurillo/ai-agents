"""Issue #6506: adr-generator runs the ADR index refresh only in rjmurillo/ai-agents."""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SURFACES = [
    REPO_ROOT / "templates/skills/adr-generator.SKILL.md.tmpl",
    REPO_ROOT / ".claude/skills/adr-generator/SKILL.md",
]
GENERATOR = "build/scripts/generate_adr_index.py"
COMMAND = f"uv run python {GENERATOR}"


def _hand_off(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index("### Phase G6: Hand Off")
    return text[start : text.index("\n---", start)]


def _guard_block(path: Path) -> str:
    section = _hand_off(path)
    return section[
        section.index("git remote get-url origin") : section.index(COMMAND) + len(COMMAND)
    ]


@pytest.mark.parametrize("path", SURFACES, ids=["template", "rendered"])
def test_refresh_runs_only_in_this_repository(path: Path) -> None:
    section = _hand_off(path)

    assert "Run it only in the `rjmurillo/ai-agents` repository" in section
    assert section.index("git remote get-url origin") < section.index(COMMAND)


@pytest.mark.parametrize("path", SURFACES, ids=["template", "rendered"])
def test_the_command_is_chained_behind_both_guards(path: Path) -> None:
    block = _guard_block(path)

    assert block.count("&&") == 2
    assert f"test -f {GENERATOR}" in block


@pytest.mark.parametrize("path", SURFACES, ids=["template", "rendered"])
@pytest.mark.parametrize(
    ("url", "expect_run"),
    [
        ("https://github.com/rjmurillo/ai-agents.git", True),
        ("https://github.com/rjmurillo/ai-agents", True),
        ("https://github.com/rjmurillo/ai-agents/", True),
        ("https://user@github.com/rjmurillo/ai-agents.git", True),
        ("git@github.com:rjmurillo/ai-agents.git", True),
        ("git@github.com:rjmurillo/ai-agents", True),
        ("ssh://git@github.com/rjmurillo/ai-agents.git", True),
        ("https://gitlab.com/rjmurillo/ai-agents.git", False),
        ("https://evil.example/x/rjmurillo/ai-agents.git", False),
        ("git@evil.example:rjmurillo/ai-agents", False),
        ("https://evil.example/github.com/rjmurillo/ai-agents", False),
        ("https://github.com.evil.example/rjmurillo/ai-agents", False),
        ("https://github.com/evil/rjmurillo/ai-agents.git", False),
        ("https://github.com/notrjmurillo/ai-agents.git", False),
        ("https://github.com/rjmurillo/ai-agents-fork.git", False),
        ("https://github.com/someone/other-repo.git", False),
        ("/srv/git/rjmurillo/ai-agents", False),
        ("file:///srv/rjmurillo/ai-agents", False),
    ],
)
def test_the_documented_guard_runs_the_command_for_github_only(
    tmp_path: Path, path: Path, url: str, expect_run: bool
) -> None:
    """Execute the documented block with `echo RAN` in place of the generator."""
    guard = _guard_block(path).replace("\\\n", " ").replace(COMMAND, "echo RAN")
    repo = tmp_path / "repo"
    (repo / "build" / "scripts").mkdir(parents=True)
    (repo / GENERATOR).write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)

    done = subprocess.run(
        ["sh", "-c", guard],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert ("RAN" in done.stdout) is expect_run, (url, done.stdout, done.stderr)


@pytest.mark.parametrize("path", SURFACES, ids=["template", "rendered"])
def test_the_guard_skips_when_the_generator_is_missing(tmp_path: Path, path: Path) -> None:
    guard = _guard_block(path).replace("\\\n", " ").replace(COMMAND, "echo RAN")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    remote = "https://github.com/rjmurillo/ai-agents.git"
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", remote], check=True)

    done = subprocess.run(
        ["sh", "-c", guard],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert "RAN" not in done.stdout


@pytest.mark.parametrize("path", SURFACES, ids=["template", "rendered"])
def test_the_guard_skips_with_no_origin_remote(tmp_path: Path, path: Path) -> None:
    guard = _guard_block(path).replace("\\\n", " ").replace(COMMAND, "echo RAN")
    (tmp_path / "build" / "scripts").mkdir(parents=True)
    (tmp_path / GENERATOR).write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    done = subprocess.run(
        ["sh", "-c", guard],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert "RAN" not in done.stdout
