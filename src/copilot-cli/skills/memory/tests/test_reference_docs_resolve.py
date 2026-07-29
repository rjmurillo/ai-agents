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

# Matched on the path tail, not on a leading ``.claude``. The docs name these
# scripts in two shapes: the literal ``.claude/skills/...`` path and the
# portable ``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/...``
# expansion. Anchoring on ``.claude`` checked only the first, which left 28 of
# the 68 references in these docs unverified.
SKILL_SCRIPT_RE = re.compile(
    r"\bskills/memory/(?:scripts|memory_core)/[a-z_]+\.py\b"
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


def test_skill_script_re_matches_both_documented_path_shapes() -> None:
    """The guard must see the portable plugin-root form, not just `.claude/`.

    Review of the Issue #3623 fix: `SKILL_SCRIPT_RE` was anchored on a literal
    leading `.claude`, but these docs name scripts in two shapes. Anchoring on
    the tail covers both, which took the checked reference count in this tree
    from 40 to 68.
    """
    tail = "skills/memory/scripts/search_memory.py"
    portable = (
        "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/" + tail
    )
    assert SKILL_SCRIPT_RE.findall(portable) == [tail]
    assert SKILL_SCRIPT_RE.findall(".claude/" + tail) == [tail]
    assert SKILL_SCRIPT_RE.findall("src/copilot-cli/" + tail) == [tail]


def test_skill_script_guard_rejects_a_phantom_portable_path() -> None:
    """Negative control: a nonexistent script in the portable form must not resolve."""
    phantom = "${COPILOT_PLUGIN_ROOT:-.claude}/skills/memory/scripts/no_such_script.py"
    found = SKILL_SCRIPT_RE.findall(phantom)
    assert found == ["skills/memory/scripts/no_such_script.py"]
    assert not (SKILLS_ROOT.parent / found[0]).is_file()


def test_docs_do_not_hard_code_a_tree_specific_sys_path() -> None:
    """No doc may teach `sys.path.insert(0, ".claude/skills/memory")`.

    That path does not exist in the `src/copilot-cli` tree or in an installed
    plugin, so the recipe fails for every reader outside one tree.
    """
    offenders = [
        _doc_id(doc)
        for doc in DOCS
        if any(
            "sys.path" in line and ".claude/skills" in line
            for line in doc.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert not offenders, f"docs hard-code a tree-specific path: {offenders}"


@pytest.mark.parametrize("doc", DOCS, ids=_doc_id)
def test_named_skill_scripts_exist(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    # Resolve against the tree that owns the doc, not the repo root. Both trees
    # ship the same scripts, and a doc in ``src/copilot-cli`` naming a path is
    # making a claim about its own tree.
    tree_root = SKILLS_ROOT.parent
    missing = [
        rel for rel in sorted(set(SKILL_SCRIPT_RE.findall(text)))
        if not (tree_root / rel).is_file()
    ]
    assert not missing, f"{_doc_id(doc)} names scripts that do not exist: {missing}"
