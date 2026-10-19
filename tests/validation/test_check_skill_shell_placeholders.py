"""Guards for the skill shell placeholder gate (issue #6743).

The skill loader rewrites a bare ``$<digit>`` into the invocation arguments.
pr-autofix held ``awk '{substr($0, 10)}'`` in a bash fence, which became
``substr(6676, 10)`` when the skill ran with args.

Coverage:

- positive: the real tree passes, ``$(0)`` awk fields pass, and ``$0`` in prose
  or in a non-shell fence passes.
- negative: ``$0``, ``$1``, ``$2`` in bash, sh, zsh, and tilde fences fail.
- edge: nested fences, an unlabeled fence, a fence closed by a longer run, an
  empty tree (config error), and the CLI exit codes.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import check_skill_shell_placeholders as gate


def _skill(repo: Path, name: str, body: str) -> Path:
    path = repo / ".claude" / "skills" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(body, encoding="utf-8")
    return path


def _fenced(lang: str, code: str, fence: str = "```") -> str:
    return f"intro\n\n{fence}{lang}\n{code}\n{fence}\n\noutro\n"


def test_real_repository_tree_passes():
    assert gate.find_skill_findings(REPO_ROOT) == []


def test_pr_autofix_awk_fields_use_parenthesized_form():
    text = (REPO_ROOT / ".claude/skills/pr-autofix/SKILL.md").read_text(encoding="utf-8")
    assert gate.find_placeholders(text) == []
    assert "substr($(0), 10)" in text


def test_parenthesized_awk_fields_pass():
    code = "awk '/^worktree /{p=substr($(0), 10)} $(1) == \"branch\" {print p}'"
    assert gate.find_placeholders(_fenced("bash", code)) == []


def test_placeholder_in_prose_passes():
    text = "| PR title | `$0`, or stated in conversation |\n| PR body | `$1` as a path |\n"
    assert gate.find_placeholders(text) == []


def test_placeholder_in_markdown_fence_passes():
    text = _fenced("markdown", "| [SaaS A] | 10min | $25 | Free tier |\n| DIY | $0 |")
    assert gate.find_placeholders(text) == []


def test_placeholder_in_unlabeled_fence_is_skipped():
    assert gate.find_placeholders(_fenced("", "echo $1")) == []


def test_dollar_without_digit_passes():
    assert gate.find_placeholders(_fenced("bash", 'echo "$HOME" "${PR}" $# $@ $?')) == []


def test_bash_placeholder_fails_with_line_number():
    text = _fenced("bash", "echo ok\nawk '{print $0}' file")
    assert gate.find_placeholders(text) == [(5, "awk '{print $0}' file")]


def test_each_digit_and_shell_language_fails():
    for lang in ("bash", "sh", "shell", "zsh", "console", "BASH"):
        for ref in ("$0", "$1", "$2", "$9"):
            found = gate.find_placeholders(_fenced(lang, f"echo {ref}"))
            assert len(found) == 1, (lang, ref)


def test_tilde_fence_fails():
    assert len(gate.find_placeholders(_fenced("bash", "echo $1", fence="~~~"))) == 1


def test_info_string_with_extra_words_still_shell():
    assert len(gate.find_placeholders(_fenced("bash title=x", "echo $1"))) == 1


def test_longer_outer_fence_holds_inner_fence():
    text = "````markdown\n```bash\necho $1\n```\n````\nafter\n"
    assert gate.find_placeholders(text) == []


def test_shell_fence_closes_before_later_prose():
    text = _fenced("bash", "echo ok") + "price is $25\n"
    assert gate.find_placeholders(text) == []


def test_findings_across_skills_carry_relative_path(tmp_path):
    _skill(tmp_path, "alpha", _fenced("bash", "echo $1"))
    _skill(tmp_path, "beta", _fenced("bash", "echo ok"))

    findings = gate.find_skill_findings(tmp_path)

    assert findings == [(Path(".claude/skills/alpha/SKILL.md"), 4, "echo $1")]
    assert gate.validate_skill_shell_placeholders(tmp_path) is False


def test_clean_tree_passes_and_main_returns_zero(tmp_path):
    _skill(tmp_path, "alpha", _fenced("bash", "echo ok"))

    assert gate.validate_skill_shell_placeholders(tmp_path) is True
    assert gate.main([str(tmp_path)]) == 0


def test_main_returns_one_and_reports(tmp_path, capsys):
    _skill(tmp_path, "alpha", _fenced("bash", "echo $0"))

    assert gate.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert ".claude/skills/alpha/SKILL.md:4" in err
    assert "#6743" in err


def test_empty_tree_is_config_error(tmp_path, capsys):
    (tmp_path / ".claude" / "skills").mkdir(parents=True)

    assert gate.main([str(tmp_path)]) == 2
    assert gate.validate_skill_shell_placeholders(tmp_path) is False
    assert "no SKILL.md" in capsys.readouterr().err


def test_missing_tree_is_config_error(tmp_path):
    assert gate.main([str(tmp_path)]) == 2


def test_invalid_root_is_config_error(tmp_path):
    assert gate.main([str(tmp_path / "missing")]) == 2
