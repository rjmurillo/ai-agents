"""Fixtures for the ship driver scripts: fake CLIs on PATH and tmp git repos.

The scripts run in process so coverage counts. ``gh``, ``az``, and the
sibling-skill helpers (``new_pr.py``, ``get_pr_checks.py``,
``validate_pr_description.py``, ``validate_review_marker.py``) are fake
Python executables driven by a JSON rule file. Git is real and runs only in
``tmp_path`` repos.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import load_scripts

_FAKE = """\
import json, os, sys
prog = os.path.basename(sys.argv[0])
if prog.endswith(".py"):
    prog = prog[:-3]
argv = sys.argv[1:]
spec_path = os.environ["SHIP_FAKE_SPEC"]
with open(os.environ["SHIP_FAKE_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps([prog, *argv]) + "\\n")
with open(os.environ["SHIP_FAKE_LOG"] + ".env", "a", encoding="utf-8") as log:
    log.write(json.dumps([prog, os.environ.get("GH_HOST")]) + "\\n")
with open(spec_path, encoding="utf-8") as handle:
    rules = json.load(handle)
for index, rule in enumerate(rules):
    prefix = rule["prefix"]
    if rule["prog"] != prog or argv[: len(prefix)] != prefix:
        continue
    counter = f"{spec_path}.{rule['id']}.n"
    seen = int(open(counter).read()) if os.path.exists(counter) else 0
    with open(counter, "w") as handle:
        handle.write(str(seen + 1))
    response = rule["responses"][min(seen, len(rule["responses"]) - 1)]
    sys.stdout.write(response.get("stdout", ""))
    sys.stderr.write(response.get("stderr", ""))
    sys.exit(response.get("rc", 0))
sys.stderr.write(f"fake {prog}: no rule for {argv}\\n")
sys.exit(99)
"""

# The real seed helper: ship_pr.py prepare loads it by path on Windows, where
# new_pr.py cannot allocate the scratch file. It is stdlib only, so the fake
# skill tree gets a copy of the real one.
REAL_PREPARE_PR_BODY = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "claude"
    / "skills"
    / "github"
    / "scripts"
    / "pr"
    / "prepare_pr_body.py"
)

HELPERS = {
    ("github", "pr", "new_pr.py"),
    ("github", "pr", "get_pr_checks.py"),
    ("github", "pr", "validate_pr_description.py"),
    ("review", "validate_review_marker.py"),
}


@dataclass
class Fakes:
    root: Path
    spec: Path
    log: Path
    skills: Path
    rules: list[dict] = field(default_factory=list)

    def rule(self, prog: str, prefix: list[str], *responses: dict) -> None:
        """Add a rule; later rules win over earlier ones."""
        entry = {
            "id": len(self.rules),
            "prog": prog,
            "prefix": prefix,
            "responses": list(responses),
        }
        self.rules.insert(0, entry)
        self.spec.write_text(json.dumps(self.rules), encoding="utf-8")

    def calls(self, prog: str | None = None) -> list[list[str]]:
        if not self.log.exists():
            return []
        entries = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        return [entry for entry in entries if prog is None or entry[0] == prog]

    def no_pr_github(self) -> None:
        self.rule(
            "gh", ["pr", "view"], {"rc": 1, "stderr": 'no pull requests found for branch "x"\n'}
        )

    def no_pr_ado(self) -> None:
        self.rule("az", ["repos", "pr", "list"], {"stdout": "[]"})

    def marker(self, rc: int, axes: str = "analyst,qa") -> None:
        if rc == 0:
            self.rule(
                "validate_review_marker",
                [],
                {"stdout": f"[PASS] reviewed: /review@{axes} binds abc (2 axis/axes)\n"},
            )
        else:
            self.rule(
                "validate_review_marker",
                [],
                {"rc": rc, "stderr": "[FAIL] HEAD is not a review marker commit\n"},
            )


def _executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    path.chmod(0o755)


@pytest.fixture
def scripts():
    return load_scripts()


@pytest.fixture
def fakes(tmp_path, monkeypatch, scripts) -> Fakes:
    common = scripts[0]
    root = tmp_path / "fakes"
    bin_dir = root / "bin"
    for prog in ("gh", "az"):
        _executable(bin_dir / prog, _FAKE)
    skills = root / "skills"
    for parts in HELPERS:
        _executable(skills.joinpath(parts[0], "scripts", *parts[1:]), _FAKE)
    prepare = skills / "github" / "scripts" / "pr" / "prepare_pr_body.py"
    shutil.copyfile(REAL_PREPARE_PR_BODY, prepare)
    spec = root / "spec.json"
    spec.write_text("[]", encoding="utf-8")
    log = root / "calls.jsonl"
    monkeypatch.setenv("SHIP_FAKE_SPEC", str(spec))
    monkeypatch.setenv("SHIP_FAKE_LOG", str(log))
    # publish takes the shared push lock under HOME; keep it off the real one.
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    # Each test gets a full run budget, as each real script run does.
    monkeypatch.setattr(
        common, "_RUN_DEADLINE", common.time.monotonic() + common.RUN_BUDGET_SECONDS
    )
    monkeypatch.setattr(
        common, "skill_script", lambda skill, *parts: skills.joinpath(skill, "scripts", *parts)
    )
    return Fakes(root=root, spec=spec, log=log, skills=skills)


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def make_repo(tmp_path, monkeypatch):
    """Return a factory: make_repo(url, branch) builds a repo and chdirs into it."""
    for key, value in (
        ("GIT_AUTHOR_NAME", "Ship Test"),
        ("GIT_AUTHOR_EMAIL", "ship@example.invalid"),
        ("GIT_COMMITTER_NAME", "Ship Test"),
        ("GIT_COMMITTER_EMAIL", "ship@example.invalid"),
    ):
        monkeypatch.setenv(key, value)
    # The bare remote is built here, in the tmp_path-rooted fixture body, so the
    # temp-root guard (tests/test_bare_repo_fixtures_are_temp_rooted.py) sees it.
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)

    def factory(
        url: str | None = "https://github.com/octo/repo.git", branch: str = "feat/ship-change"
    ) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / ".gitignore").write_text(".project-toolkit/scratch/\n", encoding="utf-8")
        (repo / "README.md").write_text("hello\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "chore: seed")
        if url is not None:
            git(repo, "remote", "add", "origin", url)
            git(repo, "config", f"url.{bare.as_posix()}.pushInsteadOf", url)
            git(repo, "push", "-q", "origin", "main")
        if branch != "main":
            git(repo, "switch", "-q", "-c", branch)
        monkeypatch.chdir(repo)
        return repo

    return factory


@pytest.fixture
def body_file():
    """Return a factory that writes a PR body into the repo's scratch directory."""

    def factory(repo: Path, text: str = "## Summary\n\nChanges the ship skill.\n") -> Path:
        directory = repo / ".project-toolkit" / "scratch"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "pr-body-test.md"
        path.write_text(text, encoding="utf-8")
        return path

    return factory


@pytest.fixture
def owner(make_repo, fakes, body_file):
    """A GitHub owner repo with no PR, a valid marker, a working create, and a body file."""
    repo = make_repo("https://github.com/rjmurillo/ai-agents.git")
    fakes.no_pr_github()
    fakes.marker(0)
    fakes.rule(
        "new_pr",
        ["--title"],
        {
            # Same order as the real new_pr.py: prelude, then gh's URL.
            "stdout": "Preparing to create PR: feat/ship-change -> main\n"
            "Title: feat(ship): add the driver\n\nCreating PR...\n"
            "https://github.com/rjmurillo/ai-agents/pull/501\nPR created successfully!\n"
        },
    )
    return repo, body_file(repo)


@pytest.fixture
def base_validator():
    """Return a factory that puts a validator on origin/main, then returns to the branch."""

    def factory(repo: Path, source: str, *, closure: bool = True) -> None:
        branch = git(repo, "branch", "--show-current")
        git(repo, "switch", "-q", "main")
        validator = repo / "scripts" / "validation" / "pr_description.py"
        validator.parent.mkdir(parents=True, exist_ok=True)
        validator.write_text(source, encoding="utf-8")
        if closure:
            (repo / "scripts" / "__init__.py").write_text("", encoding="utf-8")
            package = repo / "scripts" / "github_core"
            package.mkdir(exist_ok=True)
            (package / "__init__.py").write_text("", encoding="utf-8")
        git(repo, "add", "scripts")
        git(repo, "commit", "-q", "-m", "chore: add the base validator")
        git(repo, "push", "-q", "origin", "main")
        git(repo, "switch", "-q", branch)

    return factory
