"""Helpers for always-on membership guards."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MIRROR_DIR = REPO_ROOT / ".github" / "instructions"
PLUGIN_DIR = REPO_ROOT / "src" / "copilot-cli" / "instructions"
DOCTRINE = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "context-optimizer"
    / "references"
    / "model-context-doctrine.md"
)
LIBRARY_SKILL = REPO_ROOT / ".claude" / "skills" / "software-engineering-library" / "SKILL.md"
CANONICAL_MIRROR_RULE = REPO_ROOT / "templates" / "rules" / "canonical-source-mirror.md"
MEMBERSHIP_MEMORY = (
    REPO_ROOT
    / ".serena"
    / "memories"
    / "architecture"
    / "always-on-membership-lives-in-the-mirror.md"
)

BOOK_RULES = frozenset(
    {"code-quality", "pragmatic-programmer", "unified-software-engineering"}
)

_TABLE_HEADER = "| Form | Rules |"
_ROW_NAME = re.compile(r"`([a-z0-9-]+)`")
_LIBRARY_SENTENCE = re.compile(
    r"everyday default,\s*(?P<always>.+?)\s+loads? on every turn"
    r"\s+and\s+(?P<code>.+?)\s+loads? on code files",
    re.IGNORECASE,
)
_MEMBERSHIP_TABLE_ROW = re.compile(
    r"\|\s*`(?P<tree>\.github/instructions|src/copilot-cli/instructions)`\s*\|"
    r"[^|]*\|\s*(?P<members>[^|]+)\s*\|"
)

CORPUS_PROSE_DOCS = (
    ("canonical-source-mirror rule", CANONICAL_MIRROR_RULE),
    ("always-on-membership memory", MEMBERSHIP_MEMORY),
)


def _frontmatter(text: str) -> dict:
    """Return the YAML frontmatter mapping bounded by the leading markers."""
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    return yaml.safe_load(match.group(1)) or {}


def generated_always_on(tree: Path) -> set[str]:
    """Return rule ids whose generated mirror declares universal scope."""
    found = set()
    for path in sorted(tree.glob("*.instructions.md")):
        applyto = _frontmatter(path.read_text(encoding="utf-8")).get("applyTo")
        if isinstance(applyto, str) and applyto.strip() == "**":
            found.add(path.name.removesuffix(".instructions.md"))
    return found


def measured_always_on() -> set[str]:
    """Return always-on rule ids from the repository instruction mirror."""
    return generated_always_on(MIRROR_DIR)


def parse_doctrine_table(text: str) -> set[str]:
    """Return rule ids listed in the doctrine document's always-on table."""
    lines = text.splitlines()
    try:
        start = lines.index(_TABLE_HEADER)
    except ValueError as exc:
        raise ValueError("always-on table header not found") from exc

    names: set[str] = set()
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        names.update(_ROW_NAME.findall(line.split("|", 2)[-1]))
    if not names:
        raise ValueError("always-on table has no rule rows")
    return names


def parse_library_sentence(text: str) -> tuple[set[str], set[str]]:
    """Return (always-on, code-files) rule ids named by the library skill."""
    match = _LIBRARY_SENTENCE.search(" ".join(text.split()))
    if not match:
        raise ValueError("library loading sentence has the expected shape")

    def names(raw: str) -> set[str]:
        if raw.strip().lower() == "none":
            return set()
        return {
            name.strip()
            for name in re.split(r",\s*|\s+and\s+", raw)
            if name.strip()
        }

    return names(match.group("always")), names(match.group("code"))


def parse_corpus_membership(text: str, doc: str) -> frozenset[str]:
    """Return the membership names repeated for each generated tree."""
    rows = {
        match.group("tree"): frozenset(_ROW_NAME.findall(match.group("members")))
        for match in _MEMBERSHIP_TABLE_ROW.finditer(text)
    }
    expected = {".github/instructions", "src/copilot-cli/instructions"}
    if set(rows) != expected:
        raise ValueError(f"{doc} has no complete membership table")
    if len(set(rows.values())) != 1:
        raise ValueError(f"{doc} has divergent membership rows")
    return next(iter(rows.values()))
