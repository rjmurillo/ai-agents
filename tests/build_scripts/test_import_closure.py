"""Tests for build/scripts/import_closure.py (issue #7221).

The closure check reads every shipped skill script and lib module in each
harness tree under ``src/`` and reports an import that resolves nowhere in that
tree. The cases below build small trees under ``tmp_path`` and drive the check
the way ``check_surface_parity.run_checks`` and its CLI do.
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

import _surface_parity_helpers as helpers  # noqa: E402
import check_surface_parity as csp  # noqa: E402
import import_closure  # noqa: E402

SCRIPT = "src/codex/skills/demo/scripts/tool.py"


def _put(root: Path, rel: str, text: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _modules(root: Path) -> list[str]:
    """The unresolved module names, in report order."""
    return [f.detail.split("'")[1] for f in import_closure.check_import_closure(root)]


def _script(root: Path, body: str, rel: str = SCRIPT) -> Path:
    return _put(root, rel, body)


# --- positive: imports that resolve -----------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "import os\nimport json.decoder\nfrom pathlib import Path\n",
        "import yaml\nfrom markdown_it import MarkdownIt\n",
    ],
    ids=["stdlib", "declared-third-party"],
)
def test_stdlib_and_declared_dependencies_resolve(tmp_path: Path, body: str) -> None:
    _put(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\ndependencies = ["PyYAML==6.0.3", "markdown-it-py>=4"]\n',
    )
    _script(tmp_path, body)

    assert import_closure.check_import_closure(tmp_path) == []


def test_module_in_the_trees_own_lib_resolves(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/paths.py", "X = 1\n")
    _script(tmp_path, "from paths import X\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_package_in_the_trees_own_lib_resolves(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/github_core/__init__.py")
    _script(tmp_path, "import github_core.api\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_sibling_module_in_the_scripts_directory_resolves(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/skills/demo/scripts/helper.py", "X = 1\n")
    _script(tmp_path, "from helper import X\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_namespace_package_directory_resolves(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/skills/demo/scripts/ns/mod.py", "X = 1\n")
    _script(tmp_path, "from ns.mod import X\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_lib_module_may_import_a_sibling_lib_module(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/a.py", "import b\n")
    _put(tmp_path, "src/codex/lib/b.py", "X = 1\n")

    assert import_closure.check_import_closure(tmp_path) == []


# --- positive: relative imports ---------------------------------------------


def test_relative_import_of_an_existing_sibling_resolves(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/pkg/__init__.py")
    _put(tmp_path, "src/codex/lib/pkg/a.py", "from .b import X\n")
    _put(tmp_path, "src/codex/lib/pkg/b.py", "X = 1\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_relative_import_two_levels_up_resolves(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/pkg/sub/a.py", "from ..b import X\n")
    _put(tmp_path, "src/codex/lib/pkg/b.py", "X = 1\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_bare_relative_import_is_not_checked(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/pkg/a.py", "from . import anything\n")

    assert import_closure.check_import_closure(tmp_path) == []


# --- positive: guarded imports ----------------------------------------------


def test_optional_import_behind_try_except_import_error_is_skipped(tmp_path: Path) -> None:
    _script(
        tmp_path,
        "try:\n    import fancy\nexcept ImportError:\n    fancy = None\n",
    )

    assert import_closure.check_import_closure(tmp_path) == []


def test_fallback_import_in_the_handler_is_skipped(tmp_path: Path) -> None:
    _script(
        tmp_path,
        "try:\n    import tomllib\nexcept (ImportError, ValueError):\n    import tomli\n",
    )

    assert import_closure.check_import_closure(tmp_path) == []


def test_module_not_found_error_handler_is_skipped(tmp_path: Path) -> None:
    _script(tmp_path, "try:\n    import fancy\nexcept ModuleNotFoundError:\n    pass\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_handler_that_only_defines_a_raising_function_stays_optional(tmp_path: Path) -> None:
    """A ``raise`` inside a nested def does not run when the import fails."""
    _script(
        tmp_path,
        "try:\n    from scripts.utils import check\n"
        "except ModuleNotFoundError:\n"
        "    def check(path):\n        raise ValueError(path)\n",
    )

    assert import_closure.check_import_closure(tmp_path) == []


@pytest.mark.parametrize(
    "guard",
    ["if TYPE_CHECKING:", "if typing.TYPE_CHECKING:"],
    ids=["name", "attribute"],
)
def test_type_checking_block_is_skipped(tmp_path: Path, guard: str) -> None:
    _script(
        tmp_path,
        f"import typing\nfrom typing import TYPE_CHECKING\n{guard}\n    import fancy_types\n",
    )

    assert import_closure.check_import_closure(tmp_path) == []


# --- negative: imports that do not resolve ----------------------------------


def test_unresolved_import_names_the_file_line_and_module(tmp_path: Path) -> None:
    _script(tmp_path, "import os\n\nfrom paths import artifact_dir\n")

    findings = import_closure.check_import_closure(tmp_path)

    assert [(f.kind, f.surface, f.path) for f in findings] == [
        ("UNRESOLVED-IMPORT", "src/codex", f"{SCRIPT}:3")
    ]
    assert "'paths'" in findings[0].detail
    assert "src/codex" in findings[0].detail


def test_plain_import_and_dotted_import_are_checked(tmp_path: Path) -> None:
    _script(tmp_path, "import alpha, beta.gamma\nimport os\n")

    assert _modules(tmp_path) == ["alpha", "beta"]


def test_import_inside_a_function_is_checked(tmp_path: Path) -> None:
    _script(tmp_path, "def run():\n    import late\n")

    assert _modules(tmp_path) == ["late"]


def test_one_trees_lib_does_not_satisfy_another_tree(tmp_path: Path) -> None:
    _put(tmp_path, "src/claude/lib/paths.py", "X = 1\n")
    _script(tmp_path, "from paths import X\n")

    findings = import_closure.check_import_closure(tmp_path)

    assert [f.surface for f in findings] == ["src/codex"]


def test_module_in_a_skills_sibling_directory_does_not_resolve(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/skills/other/scripts/helper.py", "X = 1\n")
    _script(tmp_path, "from helper import X\n")

    assert _modules(tmp_path) == ["helper"]


def test_relative_import_of_a_missing_sibling_is_reported(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/pkg/a.py", "from .gone import X\n")

    findings = import_closure.check_import_closure(tmp_path)

    assert [f.path for f in findings] == ["src/codex/lib/pkg/a.py:1"]
    assert "'gone'" in findings[0].detail


def test_undeclared_third_party_is_reported(tmp_path: Path) -> None:
    _put(tmp_path, "pyproject.toml", '[project]\nname = "x"\ndependencies = ["PyYAML==6.0.3"]\n')
    _script(tmp_path, "import yaml\nimport requests\n")

    assert _modules(tmp_path) == ["requests"]


def test_dev_only_dependency_is_not_a_declared_runtime_dependency(tmp_path: Path) -> None:
    _put(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\ndependencies = []\n'
        '[project.optional-dependencies]\ndev = ["pytest"]\n',
    )
    _script(tmp_path, "import pytest\n")

    assert _modules(tmp_path) == ["pytest"]


@pytest.mark.parametrize(
    "handler",
    [
        "raise RuntimeError('need paths')",
        "sys.exit(1)",
        "exit(1)",
    ],
    ids=["raise", "sys-exit", "exit"],
)
def test_import_error_handler_that_raises_or_exits_keeps_the_import_required(
    tmp_path: Path, handler: str
) -> None:
    """``run_retrospective.py`` imports ``paths`` this way and crashes without it."""
    _script(
        tmp_path,
        f"import sys\ntry:\n    import paths\nexcept ImportError:\n    {handler}\n",
    )

    assert _modules(tmp_path) == ["paths"]


def test_type_checking_else_branch_is_still_checked(tmp_path: Path) -> None:
    _script(
        tmp_path,
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    import hint_only\nelse:\n    import runtime_only\n",
    )

    assert _modules(tmp_path) == ["runtime_only"]


def test_handler_for_another_exception_does_not_guard_the_import(tmp_path: Path) -> None:
    _script(tmp_path, "try:\n    import fancy\nexcept ValueError:\n    pass\n")

    assert _modules(tmp_path) == ["fancy"]


# --- edge: what is scanned ---------------------------------------------------


def test_file_outside_scripts_or_lib_is_not_scanned(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/skills/demo/references/example.py", "import nowhere\n")
    _put(tmp_path, "src/codex/lib/__pycache__/stale.py", "import nowhere\n")
    _put(tmp_path, "src/codex/hooks/hook.py", "import nowhere\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_unparseable_file_is_skipped_not_fatal(tmp_path: Path) -> None:
    _put(tmp_path, "src/codex/lib/broken.py", "def (:\n")
    _put(tmp_path, "src/codex/lib/ok.py", "import os\n")

    assert import_closure.check_import_closure(tmp_path) == []


def test_repository_without_src_has_no_trees(tmp_path: Path) -> None:
    assert import_closure.harness_trees(tmp_path) == []
    assert import_closure.check_import_closure(tmp_path) == []


def test_hermes_packs_are_trees_of_their_own(tmp_path: Path) -> None:
    _put(tmp_path, "src/hermes/pack-a/lib/paths.py", "X = 1\n")
    _put(tmp_path, "src/hermes/pack-a/skills/s/scripts/tool.py", "import paths\n")
    _put(tmp_path, "src/hermes/pack-b/skills/s/scripts/tool.py", "import paths\n")
    _put(tmp_path, "src/hermes/README.md", "index\n")

    trees = [t.relative_to(tmp_path).as_posix() for t in import_closure.harness_trees(tmp_path)]
    findings = import_closure.check_import_closure(tmp_path)

    assert trees == ["src/hermes/pack-a", "src/hermes/pack-b"]
    assert [f.surface for f in findings] == ["src/hermes/pack-b"]


def test_every_tree_is_checked_independently(tmp_path: Path) -> None:
    for harness in ("claude", "cursor", "muse"):
        _script(tmp_path, "import paths\n", f"src/{harness}/skills/demo/scripts/tool.py")

    assert [f.surface for f in import_closure.check_import_closure(tmp_path)] == [
        "src/claude",
        "src/cursor",
        "src/muse",
    ]


@pytest.mark.parametrize(
    ("requirement", "import_name"),
    [
        ("PyYAML==6.0.3", "yaml"),
        ("markdown-it-py>=4.2.0", "markdown_it"),
        ("python-frontmatter==1.3.0", "frontmatter"),
        ("tiktoken>=0.13.0", "tiktoken"),
        ("Some_Pkg.Name>=1", "some_pkg_name"),
    ],
)
def test_declared_third_party_maps_distributions_to_import_names(
    tmp_path: Path, requirement: str, import_name: str
) -> None:
    _put(tmp_path, "pyproject.toml", f'[project]\nname = "x"\ndependencies = ["{requirement}"]\n')

    assert import_name in import_closure.declared_third_party(tmp_path)


def test_declared_third_party_is_empty_without_a_readable_pyproject(tmp_path: Path) -> None:
    assert import_closure.declared_third_party(tmp_path) == frozenset()
    _put(tmp_path, "pyproject.toml", "not [valid toml\n")
    assert import_closure.declared_third_party(tmp_path) == frozenset()


# --- wiring: the surface parity gate and its exit code ------------------------


def _parity_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    helpers.write_manifest(root, [helpers.independent("src")], roots=["src"])
    return root


def test_surface_parity_cli_exits_nonzero_on_an_unresolved_import(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _parity_repo(tmp_path)
    _script(root, "from paths import artifact_dir\n")

    code = csp.main(["--repo-root", str(root)])

    out = capsys.readouterr().out
    assert code == 1
    assert f"UNRESOLVED-IMPORT: [src/codex] {SCRIPT}:1" in out


def test_surface_parity_cli_reports_no_import_finding_once_the_module_ships(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fixture still trips the unrelated OWNED_PREFIXES inventory rows, so read the report."""
    root = _parity_repo(tmp_path)
    _script(root, "from paths import artifact_dir\n")
    _put(root, "src/codex/lib/paths.py", "def artifact_dir():\n    return 1\n")

    csp.main(["--repo-root", str(root)])

    assert "UNRESOLVED-IMPORT" not in capsys.readouterr().out


# --- real repository ---------------------------------------------------------


def test_shipped_trees_close_over_their_imports() -> None:
    trees = import_closure.harness_trees(_REPO_ROOT)
    examined = sum(1 for tree in trees for _ in import_closure._shipped_files(tree))

    findings = import_closure.check_import_closure(_REPO_ROOT)

    assert examined > 0
    assert len(trees) >= 6
    assert [f.render() for f in findings] == []


@pytest.mark.parametrize("harness", ["codex", "cursor", "muse"])
def test_trees_that_ship_paths_importers_ship_paths_py(harness: str) -> None:
    claude = (_REPO_ROOT / "src/claude/lib/paths.py").read_bytes()

    assert (_REPO_ROOT / "src" / harness / "lib" / "paths.py").read_bytes() == claude
