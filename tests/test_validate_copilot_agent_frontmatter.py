"""Tests for scripts.validation.validate_copilot_agent_frontmatter (issues #2491-#2496).

Includes a negative control: the exact unquoted-description-with-colons shape that
caused the incident MUST be detected, proving the gate fails when the artifact is
wrong (generated-artifacts.md, self-referential-test anti-pattern). Also guards the
real committed `.github/agents/*.agent.md` files.
"""

from __future__ import annotations

from pathlib import Path

from scripts.validation import validate_copilot_agent_frontmatter as v

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The malformed shape from #2491-#2496: an unquoted plain-scalar description whose
# embedded example carries colon-bearing lines that YAML reads as mapping keys.
_MALFORMED = """---
name: code-reviewer
tier: builder
description: Use this agent to review code. Examples: Context: user did X. user: "review" assistant: ok
---

Body.
"""

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

_VALID_QUOTED = """---
name: analyst
description: 'Investigate root causes: gather evidence first'
---

Body.
"""


def _write(d: Path, name: str, text: str) -> None:
    (d / name).write_text(text, encoding="utf-8")


class TestParseFrontmatter:
    def test_extracts_mapping(self):
        assert (v.parse_frontmatter(_VALID_QUOTED) or {}).get("name") == "analyst"

    def test_none_when_no_fence(self):
        assert v.parse_frontmatter("no frontmatter here\n") is None


class TestFindMalformed:
    def test_detects_malformed_description(self, tmp_path):
        # Negative control: the incident shape must be flagged.
        _write(tmp_path, "code-reviewer.agent.md", _MALFORMED)
        offenders = v.find_malformed(tmp_path)
        assert [p.name for p, _ in offenders] == ["code-reviewer.agent.md"]

    def test_block_scalar_passes(self, tmp_path):
        _write(tmp_path, "code-reviewer.agent.md", _VALID_BLOCK)
        assert v.find_malformed(tmp_path) == []

    def test_quoted_passes(self, tmp_path):
        _write(tmp_path, "analyst.agent.md", _VALID_QUOTED)
        assert v.find_malformed(tmp_path) == []

    def test_missing_name_flagged(self, tmp_path):
        _write(tmp_path, "x.agent.md", "---\ntier: builder\n---\nbody\n")
        assert [p.name for p, _ in v.find_malformed(tmp_path)] == ["x.agent.md"]

    def test_no_frontmatter_flagged(self, tmp_path):
        _write(tmp_path, "x.agent.md", "just a body, no fences\n")
        assert len(v.find_malformed(tmp_path)) == 1


class TestRealRepoArtifacts:
    def test_all_committed_agent_files_parse(self):
        agents_dir = _PROJECT_ROOT / ".github" / "agents"
        offenders = v.find_malformed(agents_dir)
        assert offenders == [], f"malformed committed agent files: {offenders}"


class TestMain:
    def test_exit_0_when_clean(self, tmp_path, capsys):
        _write(tmp_path, "code-reviewer.agent.md", _VALID_BLOCK)
        assert v.main(["--agents-dir", str(tmp_path)]) == 0
        assert "PASS" in capsys.readouterr().out

    def test_exit_1_when_malformed(self, tmp_path, capsys):
        _write(tmp_path, "code-reviewer.agent.md", _MALFORMED)
        assert v.main(["--agents-dir", str(tmp_path)]) == 1
        assert "FAIL" in capsys.readouterr().out

    def test_exit_2_when_dir_missing(self, tmp_path, capsys):
        assert v.main(["--agents-dir", str(tmp_path / "nope")]) == 2
