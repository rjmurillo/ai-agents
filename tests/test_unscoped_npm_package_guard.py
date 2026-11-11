"""Guard against docs that run the unrelated unscoped npm package `ai-agents`.

This project publishes the scoped package `@rjmurillo/ai-agents`. The unscoped
name `ai-agents` on npm belongs to a third party (issue #7220). A doc that says
`npx ai-agents ...` makes a reader execute that stranger's code.

The scan covers tracked `.md`, `.tmpl`, and `.mustache` files. The CLI binary
name `ai-agents init` with no package-runner prefix is fine: it describes an
already-installed command.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

SCANNED_PATTERNS = ("*.md", "*.tmpl", "*.mustache")

# Internal plans and triage snapshots record past wording and are not read as
# install instructions. User-facing docs, skills, and templates stay in scope.
EXCLUDED_PREFIXES = (".project-toolkit/",)

_RUNNER = (
    r"(?:npx|bunx"
    r"|npm\s+(?:exec|install|i|add)"
    r"|pnpm\s+(?:dlx|exec|add|install|i)"
    r"|yarn\s+(?:dlx|add)"
    r"|bun\s+(?:x|add|install))"
)
_FLAGS = r"(?:\s+--?[\w-]+(?:=\S+)?)*"

UNSCOPED_INVOCATION = re.compile(
    rf"(?<![\w/@.-]){_RUNNER}{_FLAGS}\s+ai-agents(?:@[\w.^~<>=*-]+)?(?![\w/-])"
)


def find_unscoped_invocations(text: str) -> list[tuple[int, str]]:
    """Return (line number, matched text) for each unscoped package invocation."""
    hits: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in UNSCOPED_INVOCATION.finditer(line):
            hits.append((number, match.group(0)))
    return hits


def tracked_doc_files(repo_root: Path) -> list[str]:
    """List tracked doc and template files that the guard scans."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *SCANNED_PATTERNS],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    paths = [p for p in result.stdout.split("\0") if p]
    return [p for p in paths if not p.startswith(EXCLUDED_PREFIXES)]


@pytest.mark.parametrize(
    "text",
    [
        "npx ai-agents init",
        "Run `npx ai-agents init --pack business` first.",
        "npx -y ai-agents init",
        "npx --yes ai-agents@latest init",
        "bunx ai-agents init",
        "pnpm dlx ai-agents init",
        "pnpm add ai-agents",
        "npm install ai-agents",
        "npm i ai-agents",
        "npm install -g ai-agents",
        "npm install --global ai-agents@0.2.1",
        "npm exec ai-agents",
        "yarn dlx ai-agents init",
        "bun x ai-agents init",
        "$ npx ai-agents.",
    ],
)
def test_flags_unscoped_package_invocation(text: str) -> None:
    assert find_unscoped_invocations(text), text


@pytest.mark.parametrize(
    "text",
    [
        "npx @rjmurillo/ai-agents init --pack business",
        "npx -y @rjmurillo/ai-agents@latest init",
        "npm install -g @rjmurillo/ai-agents",
        "pnpm dlx @rjmurillo/ai-agents init",
        "bunx @rjmurillo/ai-agents init",
        "Run ai-agents init after install.",
        "The ai-agents project ships many skills.",
        "/plugin marketplace add rjmurillo/ai-agents",
        "git clone https://github.com/rjmurillo/ai-agents",
        "npm install rjmurillo/ai-agents",
        "npx ai-agents-cli init",
        "npx some-ai-agents init",
        "npx",
        "",
    ],
)
def test_allows_scoped_and_ordinary_text(text: str) -> None:
    assert find_unscoped_invocations(text) == [], text


def test_reports_line_numbers_and_every_hit() -> None:
    text = "intro\nnpx ai-agents init\nok\nnpm i ai-agents and bunx ai-agents\n"

    hits = find_unscoped_invocations(text)

    assert [number for number, _ in hits] == [2, 4, 4]


def test_exclusion_skips_internal_plans() -> None:
    files = tracked_doc_files(REPO_ROOT)

    assert not [f for f in files if f.startswith(EXCLUDED_PREFIXES)]


def test_tracked_docs_never_run_unscoped_package() -> None:
    files = tracked_doc_files(REPO_ROOT)
    # A scan of zero files would pass vacuously. docs/ and skills alone exceed this.
    assert len(files) > 100, f"scanned only {len(files)} files"

    offenders: list[str] = []
    for relative in files:
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        offenders.extend(
            f"{relative}:{number}: {snippet}" for number, snippet in find_unscoped_invocations(text)
        )

    assert not offenders, (
        "Unscoped npm package `ai-agents` belongs to a third party. "
        "Use `@rjmurillo/ai-agents` (issue #7220):\n" + "\n".join(offenders)
    )
