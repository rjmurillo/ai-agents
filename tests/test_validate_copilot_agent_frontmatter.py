"""Tests for scripts.validation.validate_copilot_agent_frontmatter (issues #2491-#2496).

Includes a negative control: the exact unquoted-description-with-colons shape that
caused the incident MUST be detected, proving the gate fails when the artifact is
wrong (generated-artifacts.md, self-referential-test anti-pattern). Also guards the
real committed `.github/agents/*.agent.md` files.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from scripts.validation import validate_copilot_agent_frontmatter
from scripts.validation import validate_copilot_agent_frontmatter as v

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The malformed shape from #2491-#2496: an unquoted plain-scalar description whose
# embedded example carries colon-bearing lines that YAML reads as mapping keys.
_MALFORMED = (
    """---
name: code-reviewer
tier: builder
description: Use this agent to review code. Examples: Context: user did X."""
    """ user: "review" assistant: ok
---

Body.
"""
)

_VALID_BLOCK = """---
name: code-reviewer
tier: builder
description: |-
  Use this agent to review code. Examples:
  Context: user did X.
  user: "review"
  assistant: ok
---

Body.
"""

_VALID_BLOCK_WITH_INDENTED_FENCE = """---
name: code-reviewer
tier: builder
description: |-
  Use this agent when examples include fences:
    ---
  The indented fence belongs to the description.
---

Body.
"""

_VALID_QUOTED = """---
name: analyst
description: 'Investigate root causes: gather evidence first'
---

Body.
"""


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


def _agents_dir(tmp_path: Path) -> Path:
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    return agents_dir


class TestParseFrontmatter:
    def test_extracts_mapping(self):
        assert (v.parse_frontmatter(_VALID_QUOTED) or {}).get("name") == "analyst"

    def test_none_when_no_fence(self):
        assert v.parse_frontmatter("no frontmatter here\n") is None

    def test_package_import_path_works(self):
        parsed = validate_copilot_agent_frontmatter.parse_frontmatter(_VALID_QUOTED)
        assert (parsed or {}).get("name") == "analyst"


class TestFindMalformed:
    def test_detects_malformed_description(self, tmp_path):
        # Negative control: the incident shape must be flagged.
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "code-reviewer.agent.md", _MALFORMED)
        offenders = v.find_malformed(agents_dir, repo_root=tmp_path)
        assert [p.name for p, _ in offenders] == ["code-reviewer.agent.md"]

    def test_block_scalar_passes(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "code-reviewer.agent.md", _VALID_BLOCK)
        assert v.find_malformed(agents_dir, repo_root=tmp_path) == []

    def test_block_scalar_with_indented_fence_passes(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "code-reviewer.agent.md", _VALID_BLOCK_WITH_INDENTED_FENCE)
        assert v.find_malformed(agents_dir, repo_root=tmp_path) == []

    def test_quoted_passes(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "analyst.agent.md", _VALID_QUOTED)
        assert v.find_malformed(agents_dir, repo_root=tmp_path) == []

    def test_missing_name_flagged(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "x.agent.md", "---\ntier: builder\n---\nbody\n")
        assert [p.name for p, _ in v.find_malformed(agents_dir, repo_root=tmp_path)] == [
            "x.agent.md"
        ]

    def test_no_frontmatter_flagged(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "x.agent.md", "just a body, no fences\n")
        assert len(v.find_malformed(agents_dir, repo_root=tmp_path)) == 1

    def test_parser_error_in_message(self, tmp_path):
        # #2500 AC: the failure message carries the YAML parser error.
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "code-reviewer.agent.md", _MALFORMED)
        _, message = v.find_malformed(agents_dir, repo_root=tmp_path)[0]
        assert "invalid YAML frontmatter" in message

    def test_missing_description_flagged(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "x.agent.md", "---\nname: x\ntier: builder\n---\nbody\n")
        offenders = v.find_malformed(agents_dir, repo_root=tmp_path)
        assert offenders and "description" in offenders[0][1]

    def test_empty_description_flagged(self, tmp_path):
        # The .strip() branch: a whitespace-only description is not a usable string.
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "x.agent.md", "---\nname: x\ndescription: '  '\n---\nbody\n")
        offenders = v.find_malformed(agents_dir, repo_root=tmp_path)
        assert offenders and "description" in offenders[0][1]

    def test_non_string_tier_flagged(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "x.agent.md", "---\nname: x\ndescription: ok\ntier:\n  - a\n---\nb\n")
        assert [p.name for p, _ in v.find_malformed(agents_dir, repo_root=tmp_path)] == [
            "x.agent.md"
        ]

    def test_non_mapping_frontmatter_flagged(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        _write(agents_dir, "x.agent.md", "---\njust a scalar\n---\nbody\n")
        offenders = v.find_malformed(agents_dir, repo_root=tmp_path)
        assert offenders and "not a YAML mapping" in offenders[0][1]

    def test_rejects_agents_dir_that_escapes_repo_root(self, tmp_path):
        agents_dir = _agents_dir(tmp_path)
        outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
        outside_dir.mkdir()
        try:
            assert v.find_malformed(outside_dir, repo_root=tmp_path) == []
        except ValueError as exc:
            assert "escapes repository root" in str(exc)
        else:
            raise AssertionError(f"{outside_dir} should not validate against {agents_dir}")
        finally:
            shutil.rmtree(outside_dir, ignore_errors=True)


class TestRealRepoArtifacts:
    def test_all_committed_agent_files_parse(self):
        agents_dir = _PROJECT_ROOT / ".github" / "agents"
        offenders = v.find_malformed(agents_dir)
        assert offenders == [], f"malformed committed agent files: {offenders}"


class TestMain:
    def test_exit_0_when_clean(self, capsys):
        agents_dir = _PROJECT_ROOT / ".pytest-tmp" / "frontmatter-clean"
        agents_dir.mkdir(parents=True, exist_ok=True)
        for path in agents_dir.glob("*.agent.md"):
            path.unlink()
        _write(agents_dir, "code-reviewer.agent.md", _VALID_BLOCK)
        try:
            assert v.main(["--agents-dir", str(agents_dir)]) == 0
            assert "PASS" in capsys.readouterr().out
        finally:
            shutil.rmtree(agents_dir, ignore_errors=True)

    def test_exit_1_when_malformed(self, capsys):
        agents_dir = _PROJECT_ROOT / ".pytest-tmp" / "frontmatter-malformed"
        agents_dir.mkdir(parents=True, exist_ok=True)
        for path in agents_dir.glob("*.agent.md"):
            path.unlink()
        _write(agents_dir, "code-reviewer.agent.md", _MALFORMED)
        try:
            assert v.main(["--agents-dir", str(agents_dir)]) == 1
            assert "FAIL" in capsys.readouterr().out
        finally:
            shutil.rmtree(agents_dir, ignore_errors=True)

    def test_exit_2_when_dir_missing(self, capsys):
        assert v.main(["--agents-dir", ".github/agents/nope"]) == 2

    def test_exit_2_when_dir_escapes_repo(self, capsys):
        assert v.main(["--agents-dir", "../outside"]) == 2
        assert "escapes repository root" in capsys.readouterr().err
