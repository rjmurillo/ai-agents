"""`plugin_run_fix.py` inventories legacy sites read-only and rewrites authored files (ADR-121).

The pure rewrite has its own tests in `test_plugin_run_rewrite.py`. These cover the
command: path checks, the generated-tree refusal, exit codes, idempotence, the
read-only guarantee of `--inventory`, and that a fixed file passes the validator.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import plugin_run_fix as fix  # noqa: E402
import plugin_run_launcher  # noqa: E402

from scripts.validation import check_plugin_root_interpreter as checker  # noqa: E402
from scripts.validation import plugin_root_interpreter_allowances as allowances  # noqa: E402
from tests.validation.test_check_plugin_root_interpreter import make_repo  # noqa: E402

ROOT = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
SCRIPT = "skills/memory/scripts/search_memory.py"
STDLIB = {f".claude/{SCRIPT}": "import json\n"}
TEMPLATE = "templates/skills/demo.SKILL.md.tmpl"


def _legacy(args: str = "") -> str:
    return f'python3 "{ROOT}/{SCRIPT}"' + (f" {args}" if args else "")


def _locator(args: str = "") -> str:
    return plugin_run_launcher.render_locator(SCRIPT, args)


def _doc(*lines: str) -> str:
    return "# Demo\n\n```bash\n" + "\n".join(lines) + "\n```\n"


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    return make_repo(tmp_path, {**STDLIB, **files})


def _run_fix(repo: Path, *paths: str | Path) -> int:
    return fix.main(["--fix", *map(str, paths), "--repo-root", str(repo)])


# --- --fix: round trip, idempotence, the validator ------------------------


def test_fix_rewrites_an_authored_template_and_the_validator_accepts_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy('"topic"'), _legacy())})
    assert checker.scan(repo) == []
    assert _run_fix(repo, repo / TEMPLATE) == 0
    assert (repo / TEMPLATE).read_text(encoding="utf-8") == _doc(_locator('"topic"'), _locator())
    assert f"{(repo / TEMPLATE).resolve()}: 2 fixed, 0 left" in capsys.readouterr().out
    assert checker.scan(repo) == []


def test_a_fixed_file_names_its_target_for_rule_2(tmp_path: Path) -> None:
    """Negative control: the locator is read, not skipped, so a bad target still fails."""
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy())})
    assert _run_fix(repo, repo / TEMPLATE) == 0
    (repo / f".claude/{SCRIPT}").write_text("import yaml\n", encoding="utf-8")
    [offense] = checker.scan(repo)
    assert "imports yaml" in offense


def test_fix_is_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy("a"), _legacy("b | c"))})
    path = repo / TEMPLATE
    assert _run_fix(repo, path) == 1
    first = path.read_bytes()
    assert _run_fix(repo, path) == 1
    assert path.read_bytes() == first


def test_fix_does_not_touch_a_file_with_nothing_to_fix(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(_locator("a"))})
    path = repo / TEMPLATE
    before = path.stat().st_mtime_ns
    assert _run_fix(repo, path) == 0
    assert path.stat().st_mtime_ns == before


def test_fix_keeps_the_file_mode(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy())})
    path = repo / TEMPLATE
    path.chmod(0o755)
    assert _run_fix(repo, path) == 0
    assert path.stat().st_mode & 0o777 == 0o755


def test_fix_reports_a_site_it_cannot_parse_and_still_fixes_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy("ok"), _legacy("x | head"))})
    assert _run_fix(repo, repo / TEMPLATE) == 1
    assert (repo / TEMPLATE).read_text(encoding="utf-8") == _doc(
        _locator("ok"), _legacy("x | head")
    )
    err = capsys.readouterr().err
    assert f"{(repo / TEMPLATE).resolve()}:5: left for a person" in err
    assert "operator '|'" in err


def test_fix_reports_an_assignment_site(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(f'SCRIPTS_DIR="{ROOT}/skills/memory/scripts"')})
    assert _run_fix(repo, repo / TEMPLATE) == 1
    assert "assignment from the nested form" in capsys.readouterr().err


def test_fix_follows_a_symlink_to_the_authored_file(tmp_path: Path) -> None:
    support = "src/claude/skills/demo/references/notes.md"
    repo = _repo(tmp_path, {support: _doc(_legacy())})
    link = repo / ".claude" / "skills" / "demo"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(repo / "src/claude/skills/demo", target_is_directory=True)
    assert _run_fix(repo, link / "references" / "notes.md") == 0
    assert (repo / support).read_text(encoding="utf-8") == _doc(_locator())


# --- --fix: refusals, and nothing is written when any path is refused -----

_GENERATED = [
    "src/claude/skills/demo/SKILL.md",
    "src/claude/agents/architect.md",
    "src/claude/rules/universal.md",
    "src/copilot-cli/skills/demo/references/notes.md",
    "src/codex/skills/demo/references/notes.md",
    "src/vs-code-agents/architect.agent.md",
    ".claude/hooks/README.md",
]


@pytest.mark.parametrize("rel", _GENERATED)
def test_fix_refuses_a_generated_tree_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rel: str
) -> None:
    repo = _repo(tmp_path, {rel: _doc(_legacy()), TEMPLATE: _doc(_legacy())})
    before = {p: (repo / p).read_bytes() for p in (rel, TEMPLATE)}
    assert _run_fix(repo, repo / TEMPLATE, repo / rel) == 2
    assert {p: (repo / p).read_bytes() for p in (rel, TEMPLATE)} == before
    err = capsys.readouterr().err
    assert "generated" in err
    assert "build_all.py" in err


def test_fix_refuses_a_generated_file_reached_through_a_symlink(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"src/claude/agents/a.md": _doc(_legacy())})
    link = repo / ".claude" / "agents"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(repo / "src/claude/agents", target_is_directory=True)
    before = (repo / "src/claude/agents/a.md").read_bytes()
    assert _run_fix(repo, link / "a.md") == 2
    assert "generated" in capsys.readouterr().err, "the link must be followed to the render"
    assert (repo / "src/claude/agents/a.md").read_bytes() == before


@pytest.mark.parametrize(
    ("rel", "reason"),
    [
        ("src/claude/skills/demo/demo-config.yaml", "Class G"),
        ("src/claude/skills/demo/scripts/run.py", "Python bootstraps itself"),
        ("docs/guide.md", "not an authored file"),
        (".claude/skills/local/references/x.md", "not an authored file"),
    ],
)
def test_fix_refuses_a_path_that_is_not_an_authored_markdown_or_template(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], rel: str, reason: str
) -> None:
    repo = _repo(tmp_path, {rel: _doc(_legacy())})
    before = (repo / rel).read_bytes()
    assert _run_fix(repo, repo / rel) == 2
    assert reason in capsys.readouterr().err
    assert (repo / rel).read_bytes() == before


def test_fix_refuses_a_path_outside_the_repository(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "repo", {TEMPLATE: _doc(_legacy())})
    outside = tmp_path / "outside.md"
    outside.write_text(_doc(_legacy()), encoding="utf-8")
    assert _run_fix(repo, outside) == 2
    assert "outside the repository" in capsys.readouterr().err
    assert outside.read_text(encoding="utf-8") == _doc(_legacy())


def test_fix_refuses_a_missing_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo(tmp_path, {})
    assert _run_fix(repo, repo / "templates" / "skills" / "absent.tmpl") == 2
    assert "not a file" in capsys.readouterr().err


def test_fix_refuses_a_file_that_is_not_utf8(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {})
    path = repo / "src/claude/skills/demo/references/bad.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00")
    assert _run_fix(repo, path) == 2
    assert "not UTF-8 text" in capsys.readouterr().err


def test_fix_reports_a_template_the_build_cannot_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The render-target list reads every template, so an unreadable one stops the run."""
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy())})
    bad = repo / "templates/skills/broken.SKILL.md.tmpl"
    bad.write_bytes(b"\xff\xfe\x00")
    assert _run_fix(repo, repo / TEMPLATE) == 2
    assert "could not list the files the build renders" in capsys.readouterr().err
    assert (repo / TEMPLATE).read_text(encoding="utf-8") == _doc(_legacy())


def test_fix_reports_a_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {TEMPLATE: _doc(_legacy())})

    def refuse(path: Path, content: bytes) -> None:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(fix, "publish_bytes_preserving_mode", refuse)
    assert _run_fix(repo, repo / TEMPLATE) == 2
    assert "could not write" in capsys.readouterr().err


# --- the generated set comes from the build's own lists ------------------


def test_every_render_target_of_the_build_is_refused() -> None:
    targets = fix._generated_targets(REPO_ROOT)
    assert len(targets) > 150, "the build lists far more render targets than this"
    leaked = sorted(rel for rel in targets if fix.generated_reason(rel, targets) is None)
    assert leaked == []


def test_a_render_target_is_refused_by_the_command(capsys: pytest.CaptureFixture[str]) -> None:
    rel = "src/claude/skills/build/SKILL.md"
    assert fix.main(["--fix", str(REPO_ROOT / rel), "--repo-root", str(REPO_ROOT)]) == 2
    assert "generated" in capsys.readouterr().err


def test_every_tracked_template_and_support_file_is_accepted() -> None:
    """Negative control for the refusal: nothing authored is refused as generated."""
    targets = fix._generated_targets(REPO_ROOT)
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "templates", "src/claude/skills"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    refused = []
    for rel in filter(lambda item: item.endswith(fix.FIXABLE_SUFFIXES), listing):
        if rel.endswith("/SKILL.md") and rel.count("/") == 4:
            continue
        try:
            fix.check_target(REPO_ROOT, str(REPO_ROOT / rel), targets)
        except fix.FixError as exc:
            refused.append(str(exc))
    assert refused == []


def test_every_skill_md_render_is_refused() -> None:
    targets = fix._generated_targets(REPO_ROOT)
    skills = sorted((REPO_ROOT / "src/claude/skills").glob("*/SKILL.md"))
    assert skills, "no SKILL.md renders found"
    for path in skills:
        with pytest.raises(fix.FixError, match="generated"):
            fix.check_target(REPO_ROOT, str(path), targets)


# --- --inventory ------------------------------------------------------------

INVENTORY_FILES = {
    TEMPLATE: _doc(_legacy("a"), _legacy("b"), f'SCRIPTS_DIR="{ROOT}/skills/memory"'),
    "templates/agents/a.claude.md.tmpl": _doc(_legacy()),
    "src/claude/skills/demo/SKILL.md": _doc(_legacy("x")),
    "src/claude/skills/demo/references/r.md": f"See {ROOT}/skills/memory for files.\n",
    "docs/outside.md": _doc(_legacy()),
}


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    found: dict[str, tuple[bytes, int]] = {}
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in names:
            path = Path(current) / name
            found[path.relative_to(root).as_posix()] = (path.read_bytes(), path.stat().st_mtime_ns)
    return found


def _file_rows(out: str) -> dict[str, list[str]]:
    """Map each path in the per-file table to its [invocations, assignments, mentions]."""
    table = out.split("\nfile ", 1)[1].splitlines()[1:]
    return {line.split()[0]: line.split()[-3:] for line in table if line.strip()}


def test_inventory_counts_each_group_and_states_its_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, INVENTORY_FILES)
    assert fix.main(["--inventory", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "scope: tracked files under templates/ and src/claude/" in out
    assert "git grep -nE '^\\s*[A-Za-z_]+=.*COPILOT_PLUGIN_ROOT:-" in out
    rows = _file_rows(out)
    assert rows[TEMPLATE] == ["2", "1", "3"]
    assert rows["templates/agents/a.claude.md.tmpl"] == ["1", "0", "1"]
    assert rows["src/claude/skills/demo/SKILL.md"] == ["1", "0", "1"]
    assert rows["src/claude/skills/demo/references/r.md"] == ["0", "0", "1"]
    assert "docs/outside.md" not in rows
    assert "inventory at no commit yet" in out


def test_inventory_puts_a_render_apart_from_the_groups_the_baseline_counts(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path, INVENTORY_FILES)
    rows = {row.path: row.group for row in fix.collect_inventory(repo)}
    assert rows[TEMPLATE] == "templates/skills"
    assert rows["templates/agents/a.claude.md.tmpl"] == "templates/agents"
    assert rows["src/claude/skills/demo/references/r.md"] == "src/claude"
    assert rows["src/claude/skills/demo/SKILL.md"] == fix.RENDER_GROUP


def test_inventory_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _repo(tmp_path, INVENTORY_FILES)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("--inventory must not write")

    monkeypatch.setattr(fix, "publish_bytes_preserving_mode", forbidden)
    before = _snapshot(repo)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert fix.main(["--inventory", "--repo-root", str(repo)]) == 0
    assert _snapshot(repo) == before
    after = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert after == status


def _grep_count(repo: Path) -> int:
    done = subprocess.run(
        ["git", "grep", "-nE", fix.ADR_ASSIGNMENT_GREP, "--", *fix.INVENTORY_SCOPE],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    return len(done.stdout.splitlines())


@pytest.mark.parametrize("which", ["fixture", "this checkout"])
def test_assignment_count_equals_the_adr_git_grep_count(tmp_path: Path, which: str) -> None:
    repo = _repo(tmp_path, INVENTORY_FILES) if which == "fixture" else REPO_ROOT
    rows = fix.collect_inventory(repo)
    assert sum(row.assignments for row in rows) == _grep_count(repo)
    assert _grep_count(repo) > 0


def test_inventory_of_this_checkout_matches_the_validators_baseline() -> None:
    """One definition of a site: the inventory and the ratchet count the same population."""
    totals: dict[str, tuple[int, int]] = {}
    for row in fix.collect_inventory(REPO_ROOT):
        if row.group == fix.RENDER_GROUP:
            continue
        inv, asg = totals.get(row.group, (0, 0))
        totals[row.group] = (inv + row.invocations, asg + row.assignments)
    expected = {
        group: (inv, asg) for group, (inv, asg, _reason) in allowances.LEGACY_SITE_BASELINE.items()
    }
    assert {g: t for g, t in totals.items() if t != (0, 0)} == expected


def test_inventory_outside_a_repository_is_an_external_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert fix.main(["--inventory", "--repo-root", str(plain)]) == 3
    assert "git" in capsys.readouterr().err


# --- command line -----------------------------------------------------------


@pytest.mark.parametrize(
    "argv", [[], ["--fix"], ["--inventory", "--fix", "x.md"], ["--bogus"]], ids=str
)
def test_a_bad_command_line_exits_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        fix.main(argv)
    assert raised.value.code == 2


def test_the_script_runs_as_a_program_from_another_directory(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(REPO_ROOT / "build" / "scripts" / "plugin_run_fix.py"), "--inventory"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("plugin-run-fix inventory at ")


def test_inventory_skips_a_symlink_and_a_binary_file(tmp_path: Path) -> None:
    files = {**INVENTORY_FILES, "src/claude/skills/demo/references/blob.md": ""}
    repo = _repo(tmp_path, files)
    (repo / "src/claude/skills/demo/references/blob.md").write_bytes(
        b"\xff\xfe" + _legacy().encode()
    )
    link = repo / "templates/skills/linked.tmpl"
    link.symlink_to(repo / TEMPLATE)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    paths = {row.path for row in fix.collect_inventory(repo)}
    assert TEMPLATE in paths
    assert "templates/skills/linked.tmpl" not in paths
    assert "src/claude/skills/demo/references/blob.md" not in paths


def test_fix_reports_a_file_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    support = "src/claude/skills/demo/references/notes.md"
    repo = _repo(tmp_path, {support: _doc(_legacy())})
    real_read = Path.read_text

    def deny(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "notes.md":
            raise PermissionError(13, "denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny)
    assert _run_fix(repo, repo / support) == 2
    assert "could not read" in capsys.readouterr().err
