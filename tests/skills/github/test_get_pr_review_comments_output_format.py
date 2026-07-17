"""#3092: get_pr_review_comments.py must accept --output-format like its siblings.

The sibling scripts (get_pr_context.py, get_issue_comments.py) expose
``--output-format {json,human,auto}``; get_pr_review_comments.py rejected it with
exit 2. These tests pin the flag onto its argparse surface.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_LIB = _REPO / ".claude" / "lib"
_SCRIPT = _REPO / ".claude" / "skills" / "github" / "scripts" / "pr" / "get_pr_review_comments.py"


def _load():
    if str(_LIB) not in sys.path:
        sys.path.insert(0, str(_LIB))
    spec = importlib.util.spec_from_file_location("grc_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_format_flag_parses():
    module = _load()
    args = module.build_parser().parse_args(
        ["--pull-request", "1", "--output-format", "json"]
    )
    assert args.output_format == "json"


def test_output_format_defaults_to_auto():
    module = _load()
    args = module.build_parser().parse_args(["--pull-request", "1"])
    assert args.output_format == "auto"


@pytest.mark.parametrize("value", ["json", "human", "auto"])
def test_output_format_accepts_each_choice(value):
    module = _load()
    args = module.build_parser().parse_args(
        ["--pull-request", "1", "--output-format", value]
    )
    assert args.output_format == value


def test_output_format_rejects_unknown_choice():
    module = _load()
    with pytest.raises(SystemExit):
        module.build_parser().parse_args(
            ["--pull-request", "1", "--output-format", "xml"]
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
