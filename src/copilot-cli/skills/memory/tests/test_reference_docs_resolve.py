"""Every command a memory reference doc names must resolve to real code.

Issue #3623. The memory skill docs used to teach a PowerShell API that never
shipped: `Search-Memory`, `Get-Episodes`, `Test-MemoryHealth`, and a dozen
more. `git ls-files '*.ps1' '*.psm1'` returns nothing, so every one of those
was a phantom an agent would try to run and fail on.

Two directions are checked:

1. No cmdlet-shaped token appears in a memory reference doc.
2. Every `memory_core` symbol and every skill script path a doc names really
   exists.
"""

from __future__ import annotations

import importlib
import re
import subprocess
from pathlib import Path

import pytest

def _anchor() -> tuple[Path, Path]:
    """Locate the repo root and this file's own skills tree.

    This module is mirrored into `src/copilot-cli/skills/memory/tests/`, so a
    fixed `parents[N]` index resolves correctly in only one tree and silently
    scans nothing in the other. Anchor on names instead: the `skills` directory
    is an ancestor in both trees, and the repo root is the first ancestor that
    carries `.git`.
    """
    here = Path(__file__).resolve()
    skills = next(p for p in here.parents if p.name == "skills")
    repo = next(p for p in here.parents if (p / ".git").exists())
    return repo, skills


REPO_ROOT, SKILLS_ROOT = _anchor()

MEMORY_SKILLS = (
    "memory",
    "memory-search",
    "memory-gate",
    "memory-reflexion",
    "memory-maintenance",
    "memory-enhancement",
)

DOC_SUFFIXES = (".md", ".xml")

# PowerShell approved verbs that also open ordinary English compounds. A doc
# may use these; anything else in Verb-Noun shape is treated as a phantom API.
ALLOWED_COMPOUNDS = frozenset(
    {
        "Read-Only",
        "Write-Only",
        "Read-Write",
        "Copy-Paste",
        "Set-Up",
        "Set-Theoretic",
        "Build-Measure-Learn",
    }
)

# Deliberately broad. The repo ships no PowerShell, so any Verb-Noun token in
# these docs is either a phantom cmdlet or an English compound we allowlist.
CMDLET_RE = re.compile(
    r"\b(?:Get|Set|New|Search|Test|Invoke|Merge|Measure|Write|Import|Export"
    r"|Add|Remove|Update|Start|Stop|Show|Read|Select|Extract|Convert|Copy"
    r"|Move|Clear|Enable|Disable|Register|Unregister|Resolve|Restore)"
    r"-[A-Z][A-Za-z]+\b"
)

MEMORY_CORE_RE = re.compile(r"\bmemory_core\.([a-z_]+)\.([a-z_][a-z0-9_]*)\b")

SKILL_SCRIPT_RE = re.compile(
    r"\.claude/skills/memory/(?:scripts|memory_core)/[a-z_]+\.py\b"
)


def _docs() -> list[Path]:
    found: list[Path] = []
    for skill in MEMORY_SKILLS:
        skill_dir = SKILLS_ROOT / skill
        if not skill_dir.is_dir():
            continue
        for path in sorted(skill_dir.rglob("*")):
            if path.suffix not in DOC_SUFFIXES:
                continue
            if "tests" in path.relative_to(skill_dir).parts:
                continue
            found.append(path)
    return found


DOCS = _docs()


def _doc_id(path: Path) -> str:
    return str(path.relative_to(SKILLS_ROOT))


def test_the_corpus_is_not_empty() -> None:
    """Guard against a path typo silently making every test below vacuous."""
    assert len(DOCS) >= 20, f"expected the memory doc corpus, found {len(DOCS)}"


def test_the_repo_still_ships_no_powershell() -> None:
    """The premise behind banning cmdlet tokens.

    Tracked content only. The local `.venv/` carries an `activate.ps1` that
    uv writes, and `.PSScriptAnalyzerSettings.psd1` is a linter config rather
    than a script, so neither offers a command a doc could name.

    If PowerShell ever returns to this repo, this test fails and the ban above
    has to be re-argued rather than silently enforced.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.ps1", "*.psm1"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    assert tracked == [], f"PowerShell returned: {tracked[:5]}"


@pytest.mark.parametrize("doc", DOCS, ids=_doc_id)
def test_no_phantom_cmdlets(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    hits = sorted({m for m in CMDLET_RE.findall(text) if m not in ALLOWED_COMPOUNDS})
    assert not hits, (
        f"{_doc_id(doc)} names cmdlets that do not exist anywhere in this repo: "
        f"{hits}. Use the Python API in memory_core instead."
    )


@pytest.mark.parametrize("doc", DOCS, ids=_doc_id)
def test_named_memory_core_symbols_resolve(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    missing = []
    for module_name, symbol in sorted(set(MEMORY_CORE_RE.findall(text))):
        try:
            module = importlib.import_module(f"memory_core.{module_name}")
        except ImportError:
            missing.append(f"memory_core.{module_name} (module)")
            continue
        if not hasattr(module, symbol):
            missing.append(f"memory_core.{module_name}.{symbol}")
    assert not missing, f"{_doc_id(doc)} names symbols that do not exist: {missing}"


@pytest.mark.parametrize("doc", DOCS, ids=_doc_id)
def test_named_skill_scripts_exist(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    missing = [
        rel for rel in sorted(set(SKILL_SCRIPT_RE.findall(text)))
        if not (REPO_ROOT / rel).is_file()
    ]
    assert not missing, f"{_doc_id(doc)} names scripts that do not exist: {missing}"
