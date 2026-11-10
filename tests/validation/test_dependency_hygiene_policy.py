"""Tests for dependency_hygiene_policy.py (policy value model and loader)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO / "scripts" / "validation" / "dependency_hygiene_policy.py"
_spec = importlib.util.spec_from_file_location("dependency_hygiene_policy", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
dhp = importlib.util.module_from_spec(_spec)
sys.modules["dependency_hygiene_policy"] = dhp
_spec.loader.exec_module(dhp)


def _policy(tmp: Path, body: str) -> Path:
    path = tmp / "policy.toml"
    path.write_text(body, encoding="utf-8")
    return path


# --- policy parsing --------------------------------------------------------


def test_load_policy_reads_all_sections(tmp_path):
    policy = _policy(
        tmp_path,
        """
[[manifest]]
path = "."
extend_exclude = ["packages/x"]
[manifest.module_map]
"PyYAML" = "yaml"
[[manifest.tool_only]]
package = "ruff"
reason = "cli"
evidence_file = "lefthook.yml"
evidence_pattern = "ruff"
[[manifest.transitive_ok]]
module = "grimp"
via = "Import_Linter"
only_under = "tests/"
reason = "r"
[[manifest.fixture_module]]
module = "fixture_mod"
used_in = "tests/t.py"
reason = "r"
""",
    )
    (manifest,) = dhp.load_policy(policy)
    assert manifest.extend_exclude == ("packages/x",)
    assert manifest.module_map == {"pyyaml": ("yaml",)}
    assert manifest.tool_only[0].package == "ruff"
    assert manifest.transitive_ok[0].via == "import-linter"
    assert manifest.fixture_modules[0].module == "fixture_mod"
    assert manifest.fixture_modules[0].used_in == "tests/t.py"


@pytest.mark.parametrize(
    "body",
    [
        "",
        '[[manifest]]\npath = "."\n[[manifest]]\npath = "."\n',
        '[[manifest]]\npath = "."\n[[manifest.tool_only]]\npackage = "x"\nreason = ""\n'
        'evidence_file = "a"\nevidence_pattern = "b"\n',
        "not = [valid",
        "manifest = 3\n",
        'manifest = ["x"]\n',
        '[[manifest]]\npath = "."\ntool_only = "ruff"\n',
        '[[manifest]]\npath = "."\ntool_only = ["ruff"]\n',
        '[[manifest]]\npath = "."\nextend_exclude = "x"\n',
        '[[manifest]]\npath = "."\ndev_groups = [1]\n',
        '[[manifest]]\npath = "."\nmodule_map = ["x"]\n',
        '[[manifest]]\npath = "."\n[manifest.module_map]\nx = 3\n',
        '[[manifest]]\npath = "."\n[manifest.module_map]\nx = []\n',
        '[[manifest]]\npath = "."\ntransitive_ok = {module = "m"}\n',
        '[[manifest]]\npath = "."\n[[manifest.fixture_module]]\nmodule = "m"\nreason = "r"\n',
        '[[manifest]]\npath = "."\n[[manifest.tool_only]]\npackage = "x"\nreason = "r"\n'
        'evidence_file = "a"\nevidence_pattern = "("\n',
    ],
)
def test_load_policy_rejects_bad_input(tmp_path, body):
    with pytest.raises(dhp.PolicyError):
        dhp.load_policy(_policy(tmp_path, body))


def test_load_policy_missing_file(tmp_path):
    with pytest.raises(dhp.PolicyError, match="not found"):
        dhp.load_policy(tmp_path / "absent.toml")
