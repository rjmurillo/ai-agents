"""Tests for the SkillForge SemVer pattern.

The pattern follows SemVer 2.0.0. Before this, it accepted ``01.0.0`` and
rejected the valid ``1.0.0-rc-hotfix``. ``discover_skills.py`` and
``validate-skill.py`` keep a fallback copy for when ``_constants`` cannot be
imported, so these tests also pin the copies to the same text.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillforge" / "scripts"
_SAVED_SYS_PATH = list(sys.path)
sys.path.insert(0, str(_SCRIPT_DIR))
from _constants import SEMVER_REGEX

sys.path[:] = _SAVED_SYS_PATH

_FALLBACK_FILES = ("discover_skills.py", "validate-skill.py")
_ASSIGNMENT = re.compile(r'SEMVER_REGEX = (r"[^"\n]+")')


@pytest.mark.parametrize(
    "version",
    [
        "0.0.0",
        "1.0.0",
        "10.20.30",
        "1.0.0-rc-hotfix",
        "1.0.0-beta.1",
        "1.0.0-0.3.7",
        "1.0.0-x-y-z.--",
        "1.0.0+build.5",
        "1.0.0+001",
        "2.0.0-alpha.1+sha.5114f85",
    ],
)
def test_valid_semver_matches(version: str) -> None:
    assert re.match(SEMVER_REGEX, version)


@pytest.mark.parametrize(
    "version",
    [
        "01.0.0",
        "1.01.0",
        "1.0.01",
        "1.0",
        "1.0.0.0",
        "v1.0.0",
        "1.0.0-",
        "1.0.0-01",
        "1.0.0-beta..1",
        "1.0.0+",
        "1.0.0+build..5",
        "1.0.0\n",
        "1.٠.0",
        "",
    ],
)
def test_invalid_semver_is_rejected(version: str) -> None:
    assert not re.match(SEMVER_REGEX, version)


@pytest.mark.parametrize("filename", _FALLBACK_FILES)
def test_fallback_copy_matches_constants(filename: str) -> None:
    source = (_SCRIPT_DIR / filename).read_text(encoding="utf-8")
    found = _ASSIGNMENT.findall(source)
    assert len(found) == 1, f"{filename}: expected one SEMVER_REGEX fallback, found {len(found)}"
    assert ast.literal_eval(found[0]) == SEMVER_REGEX
