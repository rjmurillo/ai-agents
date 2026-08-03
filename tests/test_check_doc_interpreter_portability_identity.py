"""Identity-based ratchet tests for check_doc_interpreter_portability (issue #4292).

Mutation proof: removing one bare-python3 invocation and adding a different one in the
same file at equal count must fire the ratchet. A count-only baseline misses this swap.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.check_doc_interpreter_portability import (
    diff_against_baseline,
    main,
)
from tests.test_check_doc_interpreter_portability import make_repo, write_baseline


def test_same_count_swap_is_detected_with_identity_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Remove script_a, add script_b at equal count -- ratchet must fire.

    This is the exact reproducer from issue #4292. Seed the baseline with
    script_a.py. Replace the documented invocation with script_b.py (same
    count: 1). The checker must exit 1 because script_b.py is not in the
    baseline set.
    """
    repo = make_repo(
        tmp_path,
        {
            "script_a.py": "import yaml\n",
            "script_b.py": "import yaml\n",
        },
    )
    baseline = write_baseline(repo, {"README.md": ["script_a.py"]})
    (repo / "README.md").write_text("Run `python3 script_b.py`.\n", encoding="utf-8")
    import subprocess

    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "swap doc"], cwd=repo, check=True)

    rc = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert rc == 1, "swap of same-count offense must be detected"
    assert "script_b.py" in capsys.readouterr().err


def test_no_swap_passes(tmp_path: Path) -> None:
    """Negative control: same script in baseline and scan exits 0."""
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "README.md": "Run `python3 tool.py`.\n",
        },
    )
    baseline = write_baseline(repo, {"README.md": ["tool.py"]})

    rc = main(["--repo-root", str(repo), "--baseline", str(baseline)])

    assert rc == 0


def test_legacy_int_baseline_accepted(tmp_path: Path) -> None:
    """A baseline with int values (old format) still loads and passes when count unchanged."""
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "README.md": "Run `python3 tool.py`.\n",
        },
    )
    baseline_path = repo / "baseline.json"
    baseline_path.write_text(
        json.dumps({"files": {"README.md": 1}}, indent=2), encoding="utf-8"
    )

    rc = main(["--repo-root", str(repo), "--baseline", str(baseline_path)])

    assert rc == 0


def test_legacy_int_baseline_fires_on_count_rise(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A legacy int baseline still blocks when a new script is added above the baseline."""
    repo = make_repo(
        tmp_path,
        {
            "tool.py": "import yaml\n",
            "other.py": "import yaml\n",
            "README.md": "Run `python3 tool.py` and `python3 other.py`.\n",
        },
    )
    baseline_path = repo / "baseline.json"
    baseline_path.write_text(
        json.dumps({"files": {"README.md": 1}}, indent=2), encoding="utf-8"
    )

    rc = main(["--repo-root", str(repo), "--baseline", str(baseline_path)])

    assert rc == 1
    assert "README.md" in capsys.readouterr().err


def test_diff_against_baseline_swap_detection() -> None:
    """Unit-level: diff_against_baseline fires when baseline has list values and current swaps."""
    current: dict[str, list[str]] = {"doc.md": ["script_b.py"]}
    base: dict[str, list[str] | int] = {"doc.md": ["script_a.py"]}
    regressions, improvements = diff_against_baseline(current, base)
    assert regressions, "swap must produce a regression"
    assert "script_b.py" in regressions[0]
    # script_b.py is present (count 1) and baseline has script_a.py (count 1).
    # cur == limit, so no improvement entry is generated.
    assert improvements == []
