"""Shared fixtures and builders for the code-review catch-rate runner tests (issue #7149).

A throwaway git repository holds four introducing/fixing commit pairs. The model seam is a
plain callable, so every path runs with no API spend and no network.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
EVAL_DIR = _REPO / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from _adr_catch_rate_stats import wilson_interval  # noqa: E402,F401  (re-exported to tests)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "eval_code_review_catch_rate", EVAL_DIR / "eval_code_review_catch_rate.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cli = _load_cli()

CLASSES = ["logic-error", "edge-case", "error-handling", "resource-handling"]


def _run(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return done.stdout.strip()


def build_repo(tmp_path: Path) -> dict:
    """Four bug/fix pairs. Pair i edits pkg/mod{i}.py; the fix swaps a distinctive line."""
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init", "-q")
    (root / "pkg").mkdir()
    pairs = []
    for i in range(4):
        path = root / "pkg" / f"mod{i}.py"
        path.write_text(
            f"def f{i}(value):\n    return value + {i}  # BUGGY_LINE_{i}_not_checked_at_all\n",
            encoding="utf-8",
        )
        (root / "docs").mkdir(exist_ok=True)
        (root / "docs" / f"note{i}.md").write_text(f"note {i}\n", encoding="utf-8")
        _run(root, "add", "-A")
        _run(root, "commit", "-q", "-m", f"feat: add module {i}")
        introducer = _run(root, "rev-parse", "HEAD")
        path.write_text(
            f"def f{i}(value):\n    return value - {i}  # REPAIRED_LINE_{i}_now_checked\n",
            encoding="utf-8",
        )
        _run(root, "commit", "-q", "-am", f"fix: repair module {i} arithmetic")
        pairs.append((introducer, _run(root, "rev-parse", "HEAD")))
    return {"root": root, "pairs": pairs}


def _git(root: Path):
    def run(args):
        done = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return done.stdout if done.returncode == 0 else None

    return run


def _write_corpus(tmp_path: Path, repo: dict, **override) -> Path:
    entries = []
    for i, (introducer, fix) in enumerate(repo["pairs"]):
        entries.append(
            {
                "id": f"CR{i + 1:02d}",
                "introducer": introducer,
                "fix": fix,
                "introducer_ref": f"commit {introducer[:12]}",
                "link_evidence": f"fix: repair module {i} arithmetic",
                "defect": f"Module {i} adds where it should subtract.",
                "defect_files": [f"pkg/mod{i}.py"],
                "defect_class": CLASSES[i],
                "confidence": "high",
                **override,
            }
        )
    path = tmp_path / "corpus.json"
    path.write_text(
        json.dumps(
            {"schema_version": 1, "selection": {"rule": "test fixture"}, "entries": entries}
        ),
        encoding="utf-8",
    )
    return path


def _stub(prompts: list[str] | None = None):
    """Catch pairs 0 and 1, right file with the wrong class for 2, nothing for 3."""

    def call(system: str, user: str) -> str:
        if prompts is not None:
            prompts.append(system + "\n" + user)
        if "pkg/mod0.py" in user:
            return (
                "FINDING: pkg/mod0.py:2 | logic-error | Adds instead of subtracting.\nVERDICT: WARN"
            )
        if "pkg/mod1.py" in user:
            return "FINDING: pkg/mod1.py:2 | edge-case | Wrong operator.\nVERDICT: WARN"
        if "pkg/mod2.py" in user:
            return "FINDING: pkg/mod2.py:2 | security | Looks unsafe.\nVERDICT: WARN"
        return "NO FINDINGS\nVERDICT: PASS"

    return call


def _argv(corpus: Path, *extra: str) -> list[str]:
    return ["--corpus", str(corpus), "--workers", "1", *extra]
