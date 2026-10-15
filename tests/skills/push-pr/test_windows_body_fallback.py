"""push-pr documents the Windows PR-body fallback that new_pr.py supports.

Issue #6571: the secure allocator refuses Windows, and new_pr.py accepts
``--body`` without the allocator. The skill must name both facts.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = REPO_ROOT / "templates" / "skills" / "push-pr.SKILL.md.tmpl"
ALLOCATOR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "prepare_pr_body.py"
_ERROR_RE = re.compile(r'PreparePrBodyError\("([^"]*Windows[^"]*)"\)')


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _windows_section() -> str:
    text = _template()
    match = re.search(r"^## Windows PR Body Fallback\n(.*?)(?=^## )", text, re.M | re.S)
    assert match, "push-pr must carry a '## Windows PR Body Fallback' section"
    return match.group(1)


def test_fallback_names_the_allocator_refusal_verbatim() -> None:
    found = _ERROR_RE.search(ALLOCATOR.read_text(encoding="utf-8"))
    assert found, "allocator Windows refusal message moved; update this test"
    assert found.group(1) in _windows_section()


def test_fallback_uses_body_flag_on_new_pr() -> None:
    section = _windows_section()
    assert "new_pr.py" in section
    assert "--body '" in section
    assert "--prepare-body-file" in section


def test_fallback_keeps_validation_and_stdin_handoff() -> None:
    section = _windows_section()
    assert "stdin" in section
    assert "--skip-validation" in section
    assert "pr_description.py" in section


def test_allocator_stays_mandatory_off_windows() -> None:
    section = _windows_section()
    assert "only on Windows" in section
    step3 = _template().split("3. Run the secure path allocator", 1)[1].split("\n4. ", 1)[0]
    assert "Windows PR Body Fallback" in step3


def test_fallback_names_shell_safe_quoting() -> None:
    section = _windows_section()
    assert '--body "' not in section
    assert "'\\''" in section
    assert "@'" in section
    assert "'@" in section


def test_fallback_creates_scratch_dir_and_names_the_file() -> None:
    section = _windows_section()
    assert "mkdir -p .project-toolkit/scratch" in section
    assert "`pr-body-windows.md` in it" in section
    assert "Write" in section


def test_fallback_sends_the_checked_file_unchanged() -> None:
    assert "final contents, unchanged" in _windows_section()


def test_fallback_names_newline_and_length_limits() -> None:
    section = _windows_section()
    assert "never `\\n`" in section
    assert "8191" in section
    assert "validate_pr_description.py" in section
