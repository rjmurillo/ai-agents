"""Guard: live files must not cite a ``.claude/rules/*.md`` path that is gone.

Issue #7658. Five rules moved out of ``.claude/rules/`` into skill reference
files, and dozens of live citations kept the old paths. No gate saw them:
``orphan-ref-validator`` has a ``rule_path`` kind, but it runs only as a
``/build`` exit gate, not in CI or lefthook, and it never reads ``.toml``.

This test reuses that validator's matcher (``RULE_REF_RE``) and its line-scope
``orphan-ref-ignore`` directive from
``.claude/skills/orphan-ref-validator/scripts/patterns.py``, so there is one
definition of a rule citation, not two. It scans tracked files under the
roots the issue names. ``tests/``, ``.project-toolkit/``, and ``.serena/`` are
outside those roots on purpose: fixtures and dated records cite old paths.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATTERNS_PATH = (
    _REPO_ROOT / ".claude" / "skills" / "orphan-ref-validator" / "scripts" / "patterns.py"
)
_spec = importlib.util.spec_from_file_location("_orphan_ref_patterns_7658", _PATTERNS_PATH)
assert _spec is not None and _spec.loader is not None
_patterns = importlib.util.module_from_spec(_spec)
sys.modules["_orphan_ref_patterns_7658"] = _patterns
_spec.loader.exec_module(_patterns)

SCAN_ROOTS: tuple[str, ...] = (
    "pyproject.toml",
    "lefthook.yml",
    ".github",
    "scripts",
    "build",
    "src",
    "templates",
    ".claude/skills",
    ".claude/lib",
)

# Rules whose old path is cited on purpose. Each entry needs a reason.
ALLOWED_MISSING: dict[str, str] = {
    ".claude/rules/claude-model-patches.md": (
        "retired rule; citing lines record its retirement (issue #7658 scope)"
    ),
}


def _tracked_files(root: Path, *pathspecs: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", *pathspecs],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [p for p in result.stdout.split("\0") if p]


def find_missing_rule_citations(
    root: Path, paths: list[str], tracked: frozenset[str] | None = None
) -> tuple[list[str], int, int]:
    """Return (findings, files examined, citations examined).

    A finding is ``path:line: cited`` for a rule path that does not resolve.
    With ``tracked``, a rule resolves only when it is in that set, so an
    untracked local file at a deleted path cannot pass here and fail in CI.
    Without it, a rule resolves when it exists under ``root``. Lines with the
    ``orphan-ref-ignore`` directive are skipped.
    """
    findings: list[str] = []
    files = 0
    citations = 0
    for rel in paths:
        full = root / rel
        if not full.is_file():
            continue
        data = full.read_bytes()
        if b"\0" in data:
            continue
        files += 1
        lines = data.decode("utf-8", errors="replace").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if _patterns.IGNORE_DIRECTIVE_RE.search(line):
                continue
            cited_paths = [m.group(1) for m in _patterns.RULE_REF_RE.finditer(line)]
            wrapped = _wrapped_citation(line, lines[lineno] if lineno < len(lines) else "")
            if wrapped:
                cited_paths.append(wrapped)
            for cited in cited_paths:
                citations += 1
                present = cited in tracked if tracked is not None else (root / cited).exists()
                if cited in ALLOWED_MISSING or present:
                    continue
                findings.append(f"{rel}:{lineno}: {cited}")
    return findings, files, citations


# A comment rewrap can split a citation after ``.claude/rules/``, leaving the
# file name at the start of the next line. RULE_REF_RE reads one line, so it
# sees neither half. lefthook.yml carried one such split (issue #7658 review).
_WRAP_HEAD_RE = re.compile(r"(?<![\w/])\.claude/rules/$", re.IGNORECASE)
_WRAP_TAIL_RE = re.compile(r"^\s*(?:#|//|\*|<!--)?\s*`?([a-zA-Z0-9_.-]+\.md)(?!\w)")


def _wrapped_citation(line: str, next_line: str) -> str | None:
    """Return the rule path split across ``line`` and ``next_line``, if any."""
    if not _WRAP_HEAD_RE.search(line.rstrip()):
        return None
    if _patterns.IGNORE_DIRECTIVE_RE.search(next_line):
        return None
    tail = _WRAP_TAIL_RE.match(next_line)
    return f".claude/rules/{tail.group(1)}" if tail else None


def test_no_live_file_cites_a_missing_rule() -> None:
    findings, files, citations = find_missing_rule_citations(
        _REPO_ROOT,
        _tracked_files(_REPO_ROOT, *SCAN_ROOTS),
        tracked=frozenset(_tracked_files(_REPO_ROOT)),
    )
    # A scan that read nothing must not pass as clean.
    assert files > 1000, f"examined only {files} files"
    assert citations > 0, "examined zero rule citations"
    assert not findings, "citations of missing .claude/rules files:\n" + "\n".join(findings)


def test_negative_control_flags_a_missing_rule(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "present.md").write_text("x\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text(
        "See .claude/rules/present.md.\nSee `.claude/rules/gone.md` MUST 3.\n",
        encoding="utf-8",
    )
    findings, files, citations = find_missing_rule_citations(tmp_path, ["doc.md"])
    assert files == 1
    assert citations == 2
    assert findings == ["doc.md:2: .claude/rules/gone.md"]


def test_ignore_directive_and_allowlist_suppress(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text(
        "| `.claude/rules/gone.md` moved | <!-- orphan-ref-ignore -->\n"
        "Retired: .claude/rules/claude-model-patches.md\n",
        encoding="utf-8",
    )
    findings, _files, citations = find_missing_rule_citations(tmp_path, ["doc.md"])
    assert findings == []
    assert citations == 1


def test_citation_wrapped_across_lines_is_flagged(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "present.md").write_text("x\n", encoding="utf-8")
    doc = tmp_path / "doc.yml"
    doc.write_text(
        "  # see `.claude/rules/\n  # gone.md`'s section\n"
        "  # and .claude/rules/\n  # present.md for more\n"
        "  # trailing .claude/rules/\n",
        encoding="utf-8",
    )
    findings, _files, citations = find_missing_rule_citations(tmp_path, ["doc.yml"])
    assert findings == ["doc.yml:1: .claude/rules/gone.md"]
    assert citations == 2


def test_untracked_rule_file_does_not_satisfy_a_citation(tmp_path: Path) -> None:
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "local.md").write_text("x\n", encoding="utf-8")
    (tmp_path / ".claude" / "rules" / "kept.md").write_text("x\n", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("See .claude/rules/local.md and .claude/rules/kept.md.\n", encoding="utf-8")
    tracked = frozenset({"doc.md", ".claude/rules/kept.md"})
    findings, _files, citations = find_missing_rule_citations(tmp_path, ["doc.md"], tracked)
    assert citations == 2
    assert findings == ["doc.md:1: .claude/rules/local.md"]


def test_binary_and_missing_paths_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\0.claude/rules/gone.md")
    findings, files, _ = find_missing_rule_citations(tmp_path, ["blob.bin", "absent.md"])
    assert findings == []
    assert files == 0


def test_every_allowlist_entry_has_a_reason_and_is_missing() -> None:
    for path, reason in ALLOWED_MISSING.items():
        assert reason.strip(), path
        assert not (_REPO_ROOT / path).exists(), f"{path} exists; drop it from the allowlist"
