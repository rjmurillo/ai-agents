"""Regression tests for issue #2796: dead cross-reference links in SKILL.md.

`.claude/skills/orphan-ref-validator/scripts/scan.py` checks two link
classes today: `skill_name` (cross-skill prose mentions) and
`script_path` (backticked `.py` references). It does not resolve
general Markdown links (`[text](path)`) that point at other `.md`
files, so a handful of `Cross-References`/`References` links drifted to
paths that do not resolve when read the way every Markdown renderer
(GitHub included) reads them: relative to the *containing file's own
directory*, not the repo root. `scripts/validation/check_adr_links.py`
covers `ADR-*.md` targets specifically, but not the non-ADR governance
doc link.

The 2026-08-05 issue #2796 comment reports this defect across four
skills: `golden-principles`, `memory-enhancement`, `session-init`, and
`guard-maturity`. This PR repairs the first two; the other two are out
of scope here. This module pins the two it repairs:

- `.claude/skills/golden-principles/SKILL.md:138-140` linked
  `.agents/governance/golden-principles.md`,
  `.claude/skills/taste-lints/SKILL.md`, and
  `.claude/skills/quality-grades/SKILL.md` as if those paths were
  repo-root-relative. Resolved from the file's own directory
  (`.claude/skills/golden-principles/`), none of the three existed.
- `.claude/skills/memory-enhancement/SKILL.md:319-320` linked
  `../../.agents/architecture/ADR-007-...` and `ADR-038-...`, one `../`
  short of the depth needed to reach the repo root from
  `.claude/skills/memory-enhancement/` (three levels, not two).

Two different fixes apply depending on what the link crosses:

- A link to a **sibling skill** (`golden-principles` -> `taste-lints`)
  stays a real relative Markdown link (`../taste-lints/SKILL.md`): both
  `.claude/skills/` and its generated `src/copilot-cli/skills/` mirror
  nest skills the same way, so the same relative path resolves in both
  trees regardless of how deep `skills/` itself sits.
- A link that escapes the skill tree to reach `.agents/` (governance or
  architecture docs, which live outside both plugin roots and are not
  themselves mirrored) cannot be a depth-correct relative link at all:
  `.claude/skills/<name>/` sits three directories below repo root, but
  the generated `src/copilot-cli/skills/<name>/` mirror sits four
  (`src/copilot-cli/skills/<name>/`), and the mirror is a byte-for-byte
  copy of the source. One `../` count cannot resolve correctly in both
  trees at once (confirmed: `scripts/validation/check_adr_links.py`
  flagged the mirror as `unresolved` even after the source-tree depth
  was corrected). The working, pre-existing repo convention for this
  case is a backtick path citation, not a real link (see
  `.claude/skills/agent-harness-reference/SKILL.md:346-347`):
  depth-independent because nothing resolves it against the containing
  file's directory.

This module checks both fix shapes stay correct, and documents the
depth-mismatch discovery with a dedicated unit test so it does not get
silently "fixed" back into a real link later.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_BACKTICK_PATH_RE = re.compile(r"`([^`]+\.md)`")


def _resolve_markdown_link(source_file: Path, link_target: str) -> Path:
    """Resolve a Markdown relative link the way a renderer would.

    Markdown (CommonMark/GFM) resolves a relative link against the
    directory of the file that contains it, never against the repo
    root. This mirrors that rule exactly so the test fails the same
    way a human clicking the link on GitHub would notice.
    """
    return (source_file.parent / link_target).resolve()


def _section_lines(file_path: Path, heading: str) -> list[str]:
    """Return the lines belonging to a Markdown ``## heading`` section.

    Locating content by heading and label instead of an absolute line
    number keeps these regression tests immune to unrelated prose landing
    above the section (Copilot review, PR #5372).
    """
    lines = file_path.read_text(encoding="utf-8").splitlines()
    heading_re = re.compile(rf"^##\s+{re.escape(heading)}\s*$")
    start = next((i for i, line in enumerate(lines) if heading_re.match(line)), None)
    assert start is not None, f"heading '## {heading}' not found in {file_path}"
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^#{1,2}(?!#)", lines[i])),
        len(lines),
    )
    return lines[start + 1 : end]


def _line_with(file_path: Path, heading: str, needle: str) -> str:
    """Return the one line in ``heading``'s section that contains ``needle``."""
    matches = [line for line in _section_lines(file_path, heading) if needle in line]
    assert len(matches) == 1, (
        f"expected exactly one line containing {needle!r} in '## {heading}' "
        f"of {file_path}, found {len(matches)}"
    )
    return matches[0]


def _links_in(line: str) -> list[str]:
    return _MD_LINK_RE.findall(line)


def _backtick_paths_in(line: str) -> list[str]:
    return _BACKTICK_PATH_RE.findall(line)


class TestGoldenPrinciplesCrossReferences:
    """The three `## Cross-References` entries in golden-principles/SKILL.md."""

    SKILL_MD = _REPO_ROOT / ".claude" / "skills" / "golden-principles" / "SKILL.md"

    def test_golden_principles_document_citation_resolves_repo_root_relative(self):
        # Now a backtick path citation, not a Markdown link (the .agents/
        # escape cannot be a depth-correct link; see module docstring).
        # Resolved against the repo root, not this file's dir.
        line = _line_with(self.SKILL_MD, "Cross-References", "golden-principles.md")
        paths = _backtick_paths_in(line)
        assert paths, f"expected a backtick-quoted path on: {line!r}"
        resolved = (_REPO_ROOT / paths[0]).resolve()
        assert resolved.is_file(), f"{paths[0]!r} does not resolve to a real file: {resolved}"
        assert resolved.name == "golden-principles.md"

    def test_golden_principles_document_is_not_a_markdown_link(self):
        # Regression guard: converting this back to `[text](path)` would
        # reintroduce the exact depth-mismatch bug this fix avoids.
        line = _line_with(self.SKILL_MD, "Cross-References", "golden-principles.md")
        assert _links_in(line) == []

    def test_taste_lints_link_resolves(self):
        line = _line_with(self.SKILL_MD, "Cross-References", "taste-lints")
        links = _links_in(line)
        assert links, f"expected a Markdown link on: {line!r}"
        resolved = _resolve_markdown_link(self.SKILL_MD, links[0])
        assert resolved.is_file(), f"{links[0]!r} does not resolve to a real file: {resolved}"
        assert resolved == (_REPO_ROOT / ".claude" / "skills" / "taste-lints" / "SKILL.md")

    def test_quality_grades_link_resolves(self):
        line = _line_with(self.SKILL_MD, "Cross-References", "quality-grades")
        links = _links_in(line)
        assert links, f"expected a Markdown link on: {line!r}"
        resolved = _resolve_markdown_link(self.SKILL_MD, links[0])
        assert resolved.is_file(), f"{links[0]!r} does not resolve to a real file: {resolved}"
        assert resolved == (_REPO_ROOT / ".claude" / "skills" / "quality-grades" / "SKILL.md")


class TestMemoryEnhancementAdrCitations:
    """The two ADR citations in memory-enhancement/SKILL.md `## References`."""

    SKILL_MD = _REPO_ROOT / ".claude" / "skills" / "memory-enhancement" / "SKILL.md"

    def test_adr_007_citation_resolves_repo_root_relative(self):
        line = _line_with(self.SKILL_MD, "References", "ADR-007-memory-first")
        paths = _backtick_paths_in(line)
        assert paths, f"expected a backtick-quoted path on: {line!r}"
        resolved = (_REPO_ROOT / paths[0]).resolve()
        assert resolved.is_file(), f"{paths[0]!r} does not resolve to a real file: {resolved}"
        assert resolved.name == "ADR-007-memory-first-architecture.md"

    def test_adr_038_citation_resolves_repo_root_relative(self):
        line = _line_with(self.SKILL_MD, "References", "ADR-038-reflexion-memory-schema")
        paths = _backtick_paths_in(line)
        assert paths, f"expected a backtick-quoted path on: {line!r}"
        resolved = (_REPO_ROOT / paths[0]).resolve()
        assert resolved.is_file(), f"{paths[0]!r} does not resolve to a real file: {resolved}"
        assert resolved.name == "ADR-038-reflexion-memory-schema.md"

    def test_adr_citations_are_not_markdown_links(self):
        # Regression guard: a real `[ADR-007](../../../.agents/...)` link
        # here resolves in the .claude source tree but NOT in the
        # generated src/copilot-cli mirror (see
        # TestMirrorDepthMismatch below), so it must stay a citation.
        adr_007_line = _line_with(self.SKILL_MD, "References", "ADR-007-memory-first")
        adr_038_line = _line_with(self.SKILL_MD, "References", "ADR-038-reflexion-memory-schema")
        assert _links_in(adr_007_line) == []
        assert _links_in(adr_038_line) == []


class TestCopilotMirrorStaysInSync:
    """The generated `src/copilot-cli/skills/` mirror must carry the same fix."""

    @pytest.mark.parametrize(
        "skill_name",
        ["golden-principles", "memory-enhancement"],
    )
    def test_mirror_matches_source(self, skill_name: str):
        source = _REPO_ROOT / ".claude" / "skills" / skill_name / "SKILL.md"
        mirror = _REPO_ROOT / "src" / "copilot-cli" / "skills" / skill_name / "SKILL.md"
        assert mirror.is_file(), f"mirror missing: {mirror}"
        assert source.read_text(encoding="utf-8") == mirror.read_text(encoding="utf-8")


class TestMirrorDepthMismatch:
    """Proves why a real relative link cannot fix the `.agents/` citations.

    `.claude/skills/<name>/SKILL.md` and the generated
    `src/copilot-cli/skills/<name>/SKILL.md` are byte-identical (enforced
    above), but they do not sit at the same depth below repo root. A fixed
    `../` count that resolves in one tree is therefore guaranteed wrong in
    the other whenever the target lives outside both trees.
    """

    def test_claude_and_copilot_skill_dirs_differ_in_depth(self):
        claude_dir = _REPO_ROOT / ".claude" / "skills" / "memory-enhancement"
        copilot_dir = _REPO_ROOT / "src" / "copilot-cli" / "skills" / "memory-enhancement"
        claude_depth = len(claude_dir.relative_to(_REPO_ROOT).parts)
        copilot_depth = len(copilot_dir.relative_to(_REPO_ROOT).parts)
        assert claude_depth == 3
        assert copilot_depth == 4
        assert claude_depth != copilot_depth

    def test_single_relative_depth_cannot_satisfy_both_trees(self, tmp_path: Path):
        # Recreate both trees' shapes under tmp_path and show that whatever
        # `../` count resolves the .claude copy, the copilot-cli copy (one
        # level deeper) is one hop short of the same target.
        (tmp_path / ".claude" / "skills" / "demo").mkdir(parents=True)
        (tmp_path / "src" / "copilot-cli" / "skills" / "demo").mkdir(parents=True)
        target_dir = tmp_path / ".agents" / "governance"
        target_dir.mkdir(parents=True)
        (target_dir / "golden-principles.md").write_text("stub\n", encoding="utf-8")

        claude_md = tmp_path / ".claude" / "skills" / "demo" / "SKILL.md"
        copilot_md = tmp_path / "src" / "copilot-cli" / "skills" / "demo" / "SKILL.md"

        same_link_text = "../../../.agents/governance/golden-principles.md"
        claude_resolved = _resolve_markdown_link(claude_md, same_link_text)
        copilot_resolved = _resolve_markdown_link(copilot_md, same_link_text)

        assert claude_resolved.is_file(), "3-level-up link should resolve in the .claude tree"
        assert not copilot_resolved.is_file(), (
            "the same 3-level-up link must NOT resolve in the one-level-deeper "
            "copilot-cli mirror tree; if this starts passing, the mirror "
            "generator started rewriting relative link depth per platform "
            "and the backtick-citation workaround above may no longer be needed"
        )


class TestMarkdownLinkResolutionHelper:
    """Unit coverage for `_resolve_markdown_link` itself (edge + negative)."""

    def test_correct_repo_root_depth_resolves(self, tmp_path: Path):
        # tmp_path/.claude/skills/demo/SKILL.md -> ../../../.agents/x.md
        skill_dir = tmp_path / ".claude" / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("stub\n", encoding="utf-8")
        target_dir = tmp_path / ".agents" / "governance"
        target_dir.mkdir(parents=True)
        (target_dir / "golden-principles.md").write_text("stub\n", encoding="utf-8")

        resolved = _resolve_markdown_link(
            skill_md, "../../../.agents/governance/golden-principles.md"
        )
        assert resolved.is_file()

    def test_one_level_short_does_not_resolve(self, tmp_path: Path):
        """The original bug class: one `../` short of repo root."""
        skill_dir = tmp_path / ".claude" / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("stub\n", encoding="utf-8")
        target_dir = tmp_path / ".agents" / "governance"
        target_dir.mkdir(parents=True)
        (target_dir / "golden-principles.md").write_text("stub\n", encoding="utf-8")

        # Only two `../` (the original memory-enhancement / golden-principles
        # bug), one short of the three needed to reach tmp_path from skill_dir.
        resolved = _resolve_markdown_link(
            skill_md, "../../.agents/governance/golden-principles.md"
        )
        assert not resolved.is_file()

    def test_missing_target_does_not_resolve(self, tmp_path: Path):
        skill_dir = tmp_path / ".claude" / "skills" / "demo"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("stub\n", encoding="utf-8")

        resolved = _resolve_markdown_link(skill_md, "../sibling/SKILL.md")
        assert not resolved.is_file()
