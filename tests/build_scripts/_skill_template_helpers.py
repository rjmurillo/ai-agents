"""Shared fixtures for the skill-template compile test suite.

Not a test module itself (no ``test_`` prefix, so pytest's ``python_files =
["test_*.py"]`` never collects it; see ``pyproject.toml``). Imported by both
``test_skill_template_grammar.py`` and ``test_generate_skills_template_compile.py``,
split out of a single ~950-line test file (taste-lint file-size ceiling; ADR
review round for #5706) so the two suites do not each redefine the same
handful of tiny fixture-writing helpers.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

_GENERATE_SKILLS_PATH = REPO_ROOT / "build" / "scripts" / "generate_skills.py"


def write_template(repo: Path, name: str, body: str) -> Path:
    templates_dir = repo / "templates" / "skills"
    templates_dir.mkdir(parents=True, exist_ok=True)
    path = templates_dir / f"{name}.SKILL.md.tmpl"
    path.write_text(body, encoding="utf-8")
    return path


def write_partial(repo: Path, slug: str, body: str) -> Path:
    partials_dir = repo / "templates" / "skills" / "partials"
    partials_dir.mkdir(parents=True, exist_ok=True)
    path = partials_dir / f"{slug}.mustache"
    path.write_text(body, encoding="utf-8")
    return path


def target(repo: Path, name: str) -> Path:
    return repo / ".claude" / "skills" / name / "SKILL.md"


def seed_target_dir(repo: Path, name: str) -> Path:
    dst = target(repo, name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    return dst


def minimal_platform_config(tmp_path: Path) -> Path:
    config = tmp_path / "platform.yaml"
    config.write_text(
        'schemaVersion: "1.0"\n'
        "provider: copilot-cli\n"
        "artifacts:\n"
        "  skills:\n"
        "    mode: directory-copy\n"
        "    sourceDir: .claude/skills\n"
        "    outputDir: out/skills\n",
        encoding="utf-8",
    )
    return config


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    # timeout=60: CodeRabbit review, PR #5726. generate_skills.py on a
    # tmp_path fixture (a handful of templates at most) returns in well
    # under a second; 60s is margin for a loaded CI runner, not an expected
    # runtime, and turns a hung child process into a reported test failure
    # instead of a wedged test job. Mirrors the same-purpose 60s timeout on
    # the python3 subprocess in test_generate_pr_quality_prompts.py:586.
    return subprocess.run(
        [sys.executable, str(_GENERATE_SKILLS_PATH), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def apply_html_comment_sentinel(dst: Path) -> None:
    dst.write_text("<!-- NO-REGEN: manual edit -->\nhand edited\n", encoding="utf-8")


def apply_hash_comment_sentinel(dst: Path) -> None:
    dst.write_text("# NO-REGEN: manual edit\nhand edited\n", encoding="utf-8")


def apply_sidecar_sentinel(dst: Path) -> None:
    dst.write_text("hand edited\n", encoding="utf-8")
    dst.with_suffix(dst.suffix + ".noregen").write_text("", encoding="utf-8")


NO_REGEN_SENTINEL_APPLIERS = (
    apply_html_comment_sentinel,
    apply_hash_comment_sentinel,
    apply_sidecar_sentinel,
)
NO_REGEN_SENTINEL_IDS = ("html-comment", "hash-comment", "sidecar")
