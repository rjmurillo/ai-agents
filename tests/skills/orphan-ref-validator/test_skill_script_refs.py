"""CI-collected tests for the issue #1987 skill-script reference check.

testpaths = ["tests", "test"] (pyproject), so the skill-local
.claude/skills/orphan-ref-validator/tests/test_scan.py is not collected by the
default CI pytest run. This file lives under tests/ so the #1987 guard has CI
coverage. It loads scan.py via the same importlib shim the skill-local suite
uses, to avoid colliding with the copilot mirror's bare-name import.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT_DIR = (
    Path(__file__).resolve().parents[3]
    / ".claude" / "skills" / "orphan-ref-validator" / "scripts"
)
sys.path.insert(0, str(_SCRIPT_DIR))
_spec = importlib.util.spec_from_file_location(
    "_orphan_ref_validator_scan_ci", _SCRIPT_DIR / "scan.py"
)
assert _spec is not None and _spec.loader is not None
_scan = importlib.util.module_from_spec(_spec)
sys.modules["_orphan_ref_validator_scan_ci"] = _scan
_spec.loader.exec_module(_scan)

extract_skill_script_refs = _scan.extract_skill_script_refs
_check_skill_script_refs = _scan._check_skill_script_refs
_check_script_refs = _scan._check_script_refs
_script_ref_resolves = _scan._script_ref_resolves


class TestExtractSkillScriptRefs:
    def test_bare_command_form(self):
        text = (
            "Run python3 .claude/skills/github/scripts/pr/"
            "get_unresolved_threads.py --pull-request 1979"
        )
        refs = list(extract_skill_script_refs(text))
        assert refs == [(1, ".claude/skills/github/scripts/pr/get_unresolved_threads.py")]

    def test_backticked_form(self):
        text = "Use `.claude/skills/github/scripts/pr/get_unresolved_review_threads.py` instead"
        refs = list(extract_skill_script_refs(text))
        assert refs == [(1, ".claude/skills/github/scripts/pr/get_unresolved_review_threads.py")]

    def test_copilot_mirror_prefix(self):
        text = "src/copilot-cli/skills/github/scripts/pr/foo.py"
        assert list(extract_skill_script_refs(text)) == [
            (1, "src/copilot-cli/skills/github/scripts/pr/foo.py")
        ]

    def test_deduped_per_line(self):
        path = ".claude/skills/x/scripts/y.py"
        text = f"`{path}` then python3 {path}"
        assert list(extract_skill_script_refs(text)) == [(1, path)]

    def test_ignore_directive_skips_line(self):
        text = ".claude/skills/x/scripts/missing.py <!-- orphan-ref-ignore -->"
        assert list(extract_skill_script_refs(text)) == []

    def test_non_skill_path_not_matched(self):
        # build/scripts paths are the existing SCRIPT_REF_RE's job, not this one.
        assert list(extract_skill_script_refs("`build/scripts/foo.py`")) == []


class TestCheckSkillScriptRefs:
    def test_wrong_name_flagged(self, tmp_path):
        # The real script exists; a misspelled sibling does not.
        scripts = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        scripts.mkdir(parents=True)
        (scripts / "get_unresolved_review_threads.py").write_text("# real\n")
        text = "python3 .claude/skills/github/scripts/pr/get_unresolved_threads.py"
        findings, checked = _check_skill_script_refs(text, "doc.md", tmp_path)
        assert checked == 1
        assert len(findings) == 1
        assert findings[0].kind == "script_path"
        assert findings[0].severity == "critical"
        assert findings[0].referenced_entity.endswith("get_unresolved_threads.py")

    def test_correct_name_not_flagged(self, tmp_path):
        scripts = tmp_path / ".claude" / "skills" / "github" / "scripts" / "pr"
        scripts.mkdir(parents=True)
        (scripts / "get_unresolved_review_threads.py").write_text("# real\n")
        text = "`.claude/skills/github/scripts/pr/get_unresolved_review_threads.py`"
        findings, checked = _check_skill_script_refs(text, "doc.md", tmp_path)
        assert checked == 1
        assert findings == []


class TestSkillRelativeResolution:
    """Issue #2796: skill SKILL.md refs resolve relative to the skill dir too."""

    def test_skill_relative_script_ref_resolves(self, tmp_path):
        # A SKILL.md citing `scripts/foo.py` means the skill's own scripts/.
        skill = tmp_path / ".claude" / "skills" / "demo"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts" / "foo.py").write_text("# real\n")
        rel = ".claude/skills/demo/SKILL.md"
        assert _script_ref_resolves("scripts/foo.py", rel, tmp_path) is True
        text = "Run `scripts/foo.py` to do the thing."
        findings, checked = _check_script_refs(text, rel, tmp_path)
        assert checked == 1
        assert findings == []

    def test_repo_relative_still_resolves(self, tmp_path):
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "bar.py").write_text("# real\n")
        rel = ".claude/skills/demo/SKILL.md"
        assert _script_ref_resolves("scripts/bar.py", rel, tmp_path) is True

    def test_non_skill_target_keeps_repo_relative_only(self, tmp_path):
        # A spec at .agents/specs/X.md does NOT get skill-relative resolution.
        spec_dir = tmp_path / ".agents" / "specs"
        (spec_dir / "scripts").mkdir(parents=True)
        (spec_dir / "scripts" / "baz.py").write_text("# real\n")
        rel = ".agents/specs/X.md"
        assert _script_ref_resolves("scripts/baz.py", rel, tmp_path) is False

    def test_truly_missing_still_flagged(self, tmp_path):
        rel = ".claude/skills/demo/SKILL.md"
        (tmp_path / ".claude" / "skills" / "demo").mkdir(parents=True)
        assert _script_ref_resolves("scripts/nope.py", rel, tmp_path) is False
        text = "See `scripts/nope.py`."
        findings, checked = _check_script_refs(text, rel, tmp_path)
        assert checked == 1
        assert len(findings) == 1
        assert findings[0].referenced_entity == "scripts/nope.py"

    def test_skill_relative_symlink_escape_stays_flagged(self, tmp_path):
        outside = tmp_path.parent / "outside.py"
        outside.write_text("# outside\n")
        rel = ".claude/skills/demo/SKILL.md"
        skill = tmp_path / ".claude" / "skills" / "demo"
        (skill / "scripts").mkdir(parents=True)
        (skill / "scripts" / "outside.py").symlink_to(outside)
        assert _script_ref_resolves("scripts/outside.py", rel, tmp_path) is False
        text = "See `scripts/outside.py`."
        findings, checked = _check_script_refs(text, rel, tmp_path)
        assert checked == 1
        assert len(findings) == 1
        assert findings[0].referenced_entity == "scripts/outside.py"
