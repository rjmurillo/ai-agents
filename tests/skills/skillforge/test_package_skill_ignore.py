#!/usr/bin/env python3
"""
Regression test: package_skill must honor .skillignore patterns.
"""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
import zipfile
from collections.abc import Iterator
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillforge" / "scripts"
)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from package_skill import package_skill


@contextlib.contextmanager
def _chdir(path: Path) -> Iterator[None]:
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PackageSkillIgnoreTest(unittest.TestCase):
    """package_skill accepts only skills under ~/.claude/skills and output under cwd.

    Both guards resolve Path.home() and os.getcwd() at call time (CWE-22), so the
    fixture points HOME at a temp home and chdirs into a temp work directory.
    """

    def test_skillignore_excludes_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skillforge-test-") as tmp:
            root = Path(os.path.realpath(tmp))
            home = root / "home"
            work = root / "work"
            skill_dir = home / ".claude" / "skills" / "my-skill"
            out_dir = work / "dist"
            skill_dir.mkdir(parents=True)
            out_dir.mkdir(parents=True)
            self.enterContext(mock.patch.dict(os.environ, {"HOME": str(home)}))
            self.enterContext(_chdir(work))

            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: my-skill\n"
                "description: test packaging behavior for skillignore exclusions\n"
                "---\n",
                encoding="utf-8",
            )
            (skill_dir / ".skillignore").write_text("*.env\nnotes\n", encoding="utf-8")

            (skill_dir / "public.txt").write_text("ok", encoding="utf-8")
            (skill_dir / "secret.env").write_text("PRIVATE=1", encoding="utf-8")
            (skill_dir / "notes").mkdir()
            (skill_dir / "notes" / "internal.txt").write_text("internal", encoding="utf-8")

            result = package_skill(skill_dir, out_dir)
            self.assertTrue(result.success, result.message)
            self.assertIsNotNone(result.output_path)

            with zipfile.ZipFile(result.output_path) as zf:
                names = set(zf.namelist())

            self.assertIn("my-skill/public.txt", names)
            self.assertNotIn("my-skill/secret.env", names)
            self.assertNotIn("my-skill/notes/internal.txt", names)


if __name__ == "__main__":
    unittest.main()
