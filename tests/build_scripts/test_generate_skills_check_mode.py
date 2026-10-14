"""generate_skills(validate=True) never writes the Copilot skill mirror.

``build_all.py --check`` passes ``validate=True``. The copy loop used to
ignore it and write the mirror, leaving the working tree changed by a gate
that should only inspect it (issue #6558). Under ``validate`` the loop now
compares each file against its source and returns 1 when any file differs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TEST_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TEST_DIR.parent.parent
for _extra_path in (_TEST_DIR, _REPO_ROOT / "build" / "scripts"):
    if str(_extra_path) not in sys.path:
        sys.path.insert(0, str(_extra_path))

import generate_skills  # noqa: E402
from _skill_template_helpers import minimal_platform_config  # noqa: E402

_BODY = "---\nname: alpha\ndescription: fixture\n---\n# alpha\n"


def _seed_skill(repo: Path) -> Path:
    """Seed a plain skill with a SKILL.md and one support file; return its dir."""
    skill_dir = repo / ".claude" / "skills" / "alpha"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_BODY, encoding="utf-8")
    (skill_dir / "references" / "notes.md").write_text("notes\n", encoding="utf-8")
    return skill_dir


def _snapshot(root: Path) -> dict[str, bytes]:
    """Return every file under ``root`` keyed by relative path."""
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _synced(tmp_path: Path) -> tuple[Path, Path]:
    """Seed a skill and run a normal build so the plugin tree and mirror match.

    The plugin support-file sync runs before the copy loop and returns 1 on its
    own drift, so each test below drifts only the Copilot mirror to prove the
    copy loop is what reports it.
    """
    _seed_skill(tmp_path)
    config = minimal_platform_config(tmp_path)
    assert generate_skills.generate_skills(config, tmp_path) == 0
    return config, tmp_path / "out" / "skills" / "alpha"


def test_validate_with_missing_mirror_file_returns_one_and_does_not_recreate_it(
    tmp_path: Path,
) -> None:
    config, mirror = _synced(tmp_path)
    (mirror / "references" / "notes.md").unlink()

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 1
    assert not (mirror / "references" / "notes.md").exists()


def test_validate_with_stale_mirror_support_file_returns_one_and_leaves_it_untouched(
    tmp_path: Path,
) -> None:
    config, mirror = _synced(tmp_path)
    (mirror / "references" / "notes.md").write_text("hand edited\n", encoding="utf-8")
    before = _snapshot(tmp_path / "out")

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 1
    assert _snapshot(tmp_path / "out") == before


def test_validate_with_stale_mirror_skill_md_returns_one_and_leaves_it_untouched(
    tmp_path: Path,
) -> None:
    config, mirror = _synced(tmp_path)
    (mirror / "SKILL.md").write_text("hand edited\n", encoding="utf-8")
    before = _snapshot(tmp_path / "out")

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 1
    assert _snapshot(tmp_path / "out") == before


def test_validate_with_in_sync_mirror_returns_zero_and_writes_nothing(tmp_path: Path) -> None:
    config, _ = _synced(tmp_path)
    before = _snapshot(tmp_path / "out")

    rc = generate_skills.generate_skills(config, tmp_path, validate=True)

    assert rc == 0
    assert _snapshot(tmp_path / "out") == before


def test_validate_reports_drift_count_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, mirror = _synced(tmp_path)
    (mirror / "SKILL.md").write_text("hand edited\n", encoding="utf-8")
    (mirror / "references" / "notes.md").unlink()
    capsys.readouterr()

    generate_skills.generate_skills(config, tmp_path, validate=True)

    assert "Skill mirror files drifted from their source: 2" in capsys.readouterr().out


def test_normal_run_still_writes_the_mirror(tmp_path: Path) -> None:
    _seed_skill(tmp_path)
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path)

    assert rc == 0
    base = tmp_path / "out" / "skills" / "alpha"
    assert (base / "SKILL.md").is_file()
    assert (base / "references" / "notes.md").read_text(encoding="utf-8") == "notes\n"


def test_what_if_run_writes_nothing_and_returns_zero(tmp_path: Path) -> None:
    _seed_skill(tmp_path)
    config = minimal_platform_config(tmp_path)

    rc = generate_skills.generate_skills(config, tmp_path, what_if=True)

    assert rc == 0
    assert not (tmp_path / "out").exists()
