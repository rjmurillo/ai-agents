"""Wiring tests for .github/workflows/publish-wiki.yml (issue #7202).

The workflow is a thin caller (ADR-006). These tests parse the YAML and assert on
the object graph, so a deleted step, a floating action tag, or a credential in
the dry-run job fails here.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-wiki.yml"
SHA_PIN = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(scope="module")
def doc() -> dict:
    loaded = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as boolean True.
    loaded["on"] = loaded.pop(True)
    return loaded


@pytest.fixture(scope="module")
def dry(doc: dict) -> dict:
    return doc["jobs"]["dry-run"]


@pytest.fixture(scope="module")
def publish(doc: dict) -> dict:
    return doc["jobs"]["publish"]


def runs(job: dict) -> list[dict]:
    return [s for s in job["steps"] if "run" in s]


def test_only_the_two_expected_jobs_exist(doc: dict) -> None:
    assert sorted(doc["jobs"]) == ["dry-run", "publish"]


def test_runs_on_main_pushes_that_touch_the_training_tree(doc: dict) -> None:
    push = doc["on"]["push"]
    assert push["branches"] == ["main"]
    assert "docs/training/**" in push["paths"]
    assert "scripts/ci/publish_wiki.py" in push["paths"]
    assert "scripts/ci/_wiki_links.py" in push["paths"]


def _imported_modules(tree: ast.Module, package: str) -> list[str]:
    """Every ``scripts`` module a parsed file names, in any import shape."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                anchor = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join([*anchor, node.module] if node.module else anchor)
            else:
                base = node.module or ""
            names.append(base)
            # `from scripts.pkg import mod` may name a submodule, not an attribute.
            names.extend(f"{base}.{a.name}" for a in node.names if a.name != "*")
        elif (
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "import_module")
                or (isinstance(node.func, ast.Name) and node.func.id == "import_module")
            )
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.append(node.args[0].value)
    return [n for n in names if n == "scripts" or n.startswith("scripts.")]


def _repo_import_closure(module: str) -> set[str]:
    """Repo-relative paths of every ``scripts`` module ``module`` loads, transitively."""
    found: set[str] = set()
    seen: set[str] = set()
    pending = [module]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        parts = name.split(".")
        # Importing a submodule runs every parent package's __init__ first.
        pending.extend(".".join(parts[:depth]) for depth in range(1, len(parts)))
        for path in (
            ROOT.joinpath(*parts).with_suffix(".py"),
            ROOT.joinpath(*parts, "__init__.py"),
        ):
            if not path.is_file():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if all(
                isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) for n in tree.body
            ):
                continue  # a docstring-only package marker runs no code
            found.add(str(path.relative_to(ROOT)))
            package = name if path.name == "__init__.py" else ".".join(parts[:-1])
            pending.extend(_imported_modules(tree, package))
    return found


def _github_path_match(path: str, pattern: str) -> bool:
    """Match like a GitHub path filter: `*` stays in one segment, `**` spans them.

    `?` makes the preceding character optional, as GitHub's filter syntax says.
    """
    regex = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            regex += ".*"
            i += 2
        elif pattern[i] == "*":
            regex += "[^/]*"
            i += 1
        elif pattern[i] == "?":
            regex += "?"  # GitHub: zero or one of the preceding character
            i += 1
        else:
            regex += re.escape(pattern[i])
            i += 1
    return re.fullmatch(regex, path) is not None


def test_the_path_filter_covers_every_repo_module_the_script_imports(doc: dict) -> None:
    """A change to any module publish_wiki.py loads must trigger the workflow."""
    patterns = doc["on"]["push"]["paths"]
    closure = _repo_import_closure("scripts.ci.publish_wiki")

    assert "scripts/hook_utilities/frontmatter_block.py" in closure
    uncovered = sorted(p for p in closure if not any(_github_path_match(p, g) for g in patterns))
    assert uncovered == []


def test_manual_run_defaults_to_dry_run(doc: dict) -> None:
    inputs = doc["on"]["workflow_dispatch"]["inputs"]["dry_run"]
    assert inputs["type"] == "boolean"
    assert inputs["default"] is True


def test_every_action_in_every_job_is_pinned_to_a_full_sha(doc: dict) -> None:
    uses = [s["uses"] for j in doc["jobs"].values() for s in j["steps"] if "uses" in s]
    assert len(uses) == 4
    assert all(SHA_PIN.match(u) for u in uses), uses


def test_no_permissions_at_workflow_level(doc: dict) -> None:
    assert doc["permissions"] == {}


def test_dry_run_job_holds_no_credential_and_no_environment(dry: dict) -> None:
    assert dry["permissions"] == {"contents": "read"}
    assert "environment" not in dry
    for step in dry["steps"]:
        assert "env" not in step
        assert "secrets." not in str(step)


def test_dry_run_job_runs_only_on_a_dry_manual_dispatch(dry: dict) -> None:
    assert dry["if"] == "${{ github.event_name == 'workflow_dispatch' && inputs.dry_run }}"
    assert [s["run"] for s in runs(dry)] == ["python3 scripts/ci/publish_wiki.py --dry-run"]


def test_publish_job_runs_on_push_or_a_non_dry_dispatch_from_main(publish: dict) -> None:
    assert publish["if"] == (
        "${{ github.event_name == 'push' || (!inputs.dry_run && github.ref == 'refs/heads/main') }}"
    )


def test_publish_job_names_the_environment_that_scopes_the_secret(publish: dict) -> None:
    assert publish["environment"] == "wiki-publish"
    assert publish["permissions"] == {"contents": "write"}


def test_publish_step_is_the_only_one_with_the_credential(publish: dict) -> None:
    step = runs(publish)[0]
    assert step["run"] == "python3 scripts/ci/publish_wiki.py"
    assert step["env"] == {"WIKI_TOKEN": "${{ secrets.WIKI_PUSH_TOKEN || github.token }}"}
    assert len(runs(publish)) == 1


def test_checkout_never_persists_credentials(doc: dict) -> None:
    checkouts = [
        s for j in doc["jobs"].values() for s in j["steps"] if "checkout@" in s.get("uses", "")
    ]
    assert len(checkouts) == 2
    assert all(c["with"]["persist-credentials"] is False for c in checkouts)


def test_concurrency_is_per_ref_and_queues(doc: dict) -> None:
    assert doc["concurrency"] == {
        "group": "publish-wiki-${{ github.ref }}",
        "cancel-in-progress": False,
    }


def test_the_closure_follows_every_import_shape(tmp_path, monkeypatch) -> None:
    """Submodule, relative, bare-package, and import_module() imports all count."""
    pkg = tmp_path / "scripts" / "pkg"
    pkg.mkdir(parents=True)
    (tmp_path / "scripts" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "entry.py").write_text(
        "import importlib\nfrom importlib import import_module\nfrom scripts.pkg import sub\n"
        "from .rel import y\nimportlib.import_module('scripts.pkg.dyn')\n"
        "import_module('scripts.pkg.dyn2')\n",
        encoding="utf-8",
    )
    for leaf in ("sub", "rel", "dyn", "dyn2"):
        (pkg / f"{leaf}.py").write_text("V = 1\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    closure = _repo_import_closure("scripts.pkg.entry")

    assert closure == {
        "scripts/__init__.py",
        "scripts/pkg/entry.py",
        "scripts/pkg/sub.py",
        "scripts/pkg/rel.py",
        "scripts/pkg/dyn.py",
        "scripts/pkg/dyn2.py",
    }


def test_the_closure_follows_a_bare_package_import(tmp_path, monkeypatch) -> None:
    """`import scripts` from outside the package runs the package's __init__."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "entry.py").write_text("import scripts\n", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert _repo_import_closure("tools.entry") == {"tools/entry.py", "scripts/__init__.py"}


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("scripts/hook_utilities/guards.py", "scripts/hook_utilities/**", True),
        ("scripts/hook_utilities/sub/x.py", "scripts/hook_utilities/**", True),
        ("scripts/ci/sub/x.py", "scripts/ci/*", False),
        ("scripts/ci/x.py", "scripts/ci/*", True),
        ("docs/training/a/b.md", "docs/training/**", True),
        ("scripts/ci/publish_wiki.py", "scripts/ci/publish_wiki.py", True),
        ("a.py", "**/a.py", True),
        ("x/y/a.py", "**/a.py", True),
        ("xa.py", "**/a.py", False),
        ("ac", "ab?c", True),
        ("abc", "ab?c", True),
        ("axc", "ab?c", False),
    ],
)
def test_path_matching_follows_github_glob_rules(path: str, pattern: str, expected: bool) -> None:
    assert _github_path_match(path, pattern) is expected
