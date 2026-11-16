"""The script template and the test template work together, and the tests can fail.

The script template ships in skillforge's assets. The test template is the
fenced block in references/script-design-rules.md. This renders both into a
temporary directory, runs the tests against the script, then breaks the script
and checks that the same tests catch it.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "skillforge"
TEMPLATES = SKILL / "assets" / "templates"
RULES_DOC = SKILL / "references" / "script-design-rules.md"
PLACEHOLDER = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def _test_template() -> str:
    text = RULES_DOC.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- test-template:start -->\n```python\n(.*?)```\n<!-- test-template:end -->", text, re.S
    )
    assert match, "script-design-rules.md has no test template block"
    return match.group(1)


def _render(tmp_path: Path, script_edit: tuple[str, str] | None = None) -> Path:
    script = PLACEHOLDER.sub("tool", (TEMPLATES / "script-template.py").read_text(encoding="utf-8"))
    if script_edit is not None:
        old, new = script_edit
        assert script.count(old) == 1, old
        script = script.replace(old, new)
    script_path = tmp_path / "tool.py"
    script_path.write_text(script, encoding="utf-8")
    tests = _test_template()
    tests, count = re.subn(
        r"^SCRIPT = .*$", f"SCRIPT = Path({str(script_path)!r})", tests, flags=re.M
    )
    assert count == 1
    test_path = tmp_path / "test_tool.py"
    test_path.write_text(tests, encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    return test_path


def _pytest(test_path: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CI", "GITHUB_", "PYTEST_"))}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test_path)],
        cwd=test_path.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )


def test_rendered_tests_pass_against_the_rendered_script(tmp_path: Path) -> None:
    proc = _pytest(_render(tmp_path))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert re.search(r"\b7 passed\b", proc.stdout), proc.stdout


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("        return 2\n", "        return 0\n"),
        ("            return 1  # A check failed\n", "            return 0\n"),
        ("    if args.output and result.success and args.dry_run:", "    if False:"),
    ],
    ids=["missing-input-code", "failed-check-code", "dry-run-write"],
)
def test_rendered_tests_catch_a_broken_script(tmp_path: Path, old: str, new: str) -> None:
    proc = _pytest(_render(tmp_path, (old, new)))

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "failed" in proc.stdout


def test_script_template_returns_codes_from_main() -> None:
    text = (TEMPLATES / "script-template.py").read_text(encoding="utf-8")

    assert "def main(argv: list[str] | None = None) -> int:" in text
    assert 'if __name__ == "__main__":\n    sys.exit(main())' in text
    assert "5-99 are reserved" in text
