"""One scan analyzes each invoked script once (issue #6854).

``scan`` checks every plugin-root invocation for third-party imports. The tree
had 976 invocations of 45 scripts on 2026-10-23, and each check parsed the
script and everything it imports, so the self-apply test took about 40s.
These tests pin the per-scan cache that replaced that. They live apart from
test_check_plugin_root_interpreter.py to keep it under the 500-line limit.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from scripts.validation import check_plugin_root_interpreter as checker
from tests.validation.test_check_plugin_root_interpreter import make_repo

_INVOKE = 'Run `python3 "${{COPILOT_PLUGIN_ROOT:-${{CLAUDE_PLUGIN_ROOT:-.claude}}}}/{tail}"`.\n'
_BAR = "skills/foo/scripts/bar.py"
_BAZ = "skills/foo/scripts/baz.py"


def _count_analyses(monkeypatch: pytest.MonkeyPatch) -> Counter[str]:
    calls: Counter[str] = Counter()
    real = checker.third_party_imports

    def counting(
        rel_path: str, repo_root: Path, tracked_py: set[str], seen: set[str] | None = None
    ) -> set[str]:
        calls[rel_path] += 1
        return real(rel_path, repo_root, tracked_py, seen)

    monkeypatch.setattr(checker, "third_party_imports", counting)
    return calls


def test_a_script_invoked_from_many_files_is_analyzed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(
        tmp_path,
        {
            f".claude/{_BAR}": "import yaml\n",
            "README.md": _INVOKE.format(tail=_BAR),
            "docs/a.md": _INVOKE.format(tail=_BAR),
            "docs/b.md": _INVOKE.format(tail=_BAR) + _INVOKE.format(tail=_BAR),
        },
    )
    calls = _count_analyses(monkeypatch)

    offenses = checker.scan(repo)

    assert len(offenses) == 4, "every invocation is still reported"
    assert all("imports yaml" in offense for offense in offenses)
    assert calls == Counter({f".claude/{_BAR}": 1})


def test_each_script_is_analyzed_once_and_clean_ones_stay_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(
        tmp_path,
        {
            f".claude/{_BAR}": "import yaml\n",
            f".claude/{_BAZ}": "import json\n",
            "README.md": _INVOKE.format(tail=_BAZ) + _INVOKE.format(tail=_BAR),
            "docs/a.md": _INVOKE.format(tail=_BAZ) + _INVOKE.format(tail=_BAR),
        },
    )
    calls = _count_analyses(monkeypatch)

    offenses = checker.scan(repo)

    assert len(offenses) == 2
    assert all(f".claude/{_BAR} imports yaml" in offense for offense in offenses)
    assert calls == Counter({f".claude/{_BAR}": 1, f".claude/{_BAZ}": 1})


def test_each_scan_starts_with_a_fresh_cache(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        {f".claude/{_BAR}": "import json\n", "README.md": _INVOKE.format(tail=_BAR)},
    )
    assert checker.scan(repo) == []

    (repo / ".claude" / _BAR).write_text("import yaml\n", encoding="utf-8")

    assert len(checker.scan(repo)) == 1, "an edited script is analyzed again"


def test_find_offenses_without_a_cache_still_checks_dependencies(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, {f".claude/{_BAR}": "import yaml\n"})
    text = _INVOKE.format(tail=_BAR)

    offenses = checker.find_offenses(text, "README.md", repo, {f".claude/{_BAR}"})

    assert len(offenses) == 1
    assert "imports yaml" in offenses[0][1]
