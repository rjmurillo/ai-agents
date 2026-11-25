"""One REPO_ROOT and one sha256 helper (review round 2, group D).

`actionability_io.py` owns REPO_ROOT and the hashing. A module that must seed sys.path before
its first `scripts.*` import keeps a private `_BOOTSTRAP_ROOT`, with a comment saying why it
cannot import the real one.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
from pathlib import Path

import pytest

from tests.eval._actionability_arms_test_support import (
    aa,
    make_prediction,
    make_row,
    pm,
    write_jsonl_file,
)

io_module = importlib.import_module("scripts.eval.actionability_io")

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_MODULES = sorted(
    [*_EVAL_DIR.glob("actionability_*.py"), _EVAL_DIR / "measure_actionability_band.py"]
)
_BOOTSTRAPPERS = [p for p in _MODULES if "sys.path.insert" in p.read_text(encoding="utf-8")]


def _assigned_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestRepoRootOnce:
    def test_only_the_io_module_defines_repo_root(self) -> None:
        """Every other module imports it or avoids the name."""
        definers = [p.name for p in _MODULES if "REPO_ROOT" in _assigned_names(p)]

        assert definers == ["actionability_io.py"]

    def test_predict_uses_the_io_object_for_the_prompt_path(self) -> None:
        """predict needs the root after its imports, so it imports it."""
        assert pm.REPO_ROOT is io_module.REPO_ROOT
        assert (
            pm.PROMPT_PATH
            == io_module.REPO_ROOT / "evals" / "comment-actionability" / "prompt-v1.md"
        )

    def test_the_bootstrap_copies_exist_where_sys_path_is_seeded(self) -> None:
        """Premise: five modules seed sys.path before their first scripts import."""
        assert [p.name for p in _BOOTSTRAPPERS] == [
            "actionability_arms.py",
            "actionability_corpus.py",
            "actionability_predict.py",
            "actionability_sheet.py",
            "measure_actionability_band.py",
        ]

    @pytest.mark.parametrize("path", _BOOTSTRAPPERS, ids=lambda p: p.name)
    def test_each_bootstrap_copy_says_why_it_exists(self, path: Path) -> None:
        """The line above the assignment explains that it must exist before the import."""
        lines = path.read_text(encoding="utf-8").splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith("_BOOTSTRAP_ROOT = "))
        comment = lines[index - 1]

        assert comment.startswith("# ")
        assert "before" in comment
        assert "actionability_io" in comment
        assert "_BOOTSTRAP_ROOT" in _assigned_names(path)

    @pytest.mark.parametrize("path", _BOOTSTRAPPERS, ids=lambda p: p.name)
    def test_the_bootstrap_copy_only_seeds_sys_path(self, path: Path) -> None:
        """It is used by the sys.path guard and nowhere else."""
        source = path.read_text(encoding="utf-8")

        assert source.count("_BOOTSTRAP_ROOT") == 3


class TestOneHashHelper:
    def test_only_the_io_module_imports_hashlib(self) -> None:
        """Hashing lives in one place."""
        importers = [p.name for p in _MODULES if "hashlib" in _imports(p)]

        assert importers == ["actionability_io.py"]

    def test_sha256_hex_matches_hashlib(self) -> None:
        """The empty input has a well-known digest."""
        assert io_module.sha256_hex(b"") == hashlib.sha256(b"").hexdigest()
        assert io_module.sha256_hex(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_file_sha256_hashes_the_bytes_on_disk(self, tmp_path: Path) -> None:
        """Bytes, not decoded text, so line endings count."""
        path = tmp_path / "f.bin"
        path.write_bytes(b"a\r\nb\n")

        assert io_module.file_sha256(path) == hashlib.sha256(b"a\r\nb\n").hexdigest()

    def test_file_sha256_raises_on_an_unreadable_file(self, tmp_path: Path) -> None:
        """The caller decides how to report it."""
        with pytest.raises(OSError):
            io_module.file_sha256(tmp_path / "missing")

    def test_the_prompt_digest_uses_the_shared_helper(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """predict does not hash on its own."""
        # load_prompt lives in actionability_message, so the patch targets the module that calls it.
        monkeypatch.setattr(
            importlib.import_module("scripts.eval.actionability_message"),
            "sha256_hex",
            lambda _data: "stub-digest",
        )

        _, digest = pm.load_prompt()

        assert digest == "stub-digest"

    def test_the_prompt_digest_is_the_file_digest(self) -> None:
        """Same value as hashing the file directly."""
        _, digest = pm.load_prompt()

        assert digest == io_module.file_sha256(pm.PROMPT_PATH)

    def test_the_score_report_hashes_use_the_shared_helper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """arms asks io for both input hashes."""
        rows = [
            make_row(f"H{i}", label="actionable" if i % 2 else "not_actionable") for i in range(8)
        ]
        corpus = write_jsonl_file(tmp_path / "c.jsonl", rows)
        predictions = write_jsonl_file(tmp_path / "p.jsonl", [make_prediction("H0")])
        monkeypatch.setattr(aa, "file_sha256", lambda path: f"stub-{path.name}")
        out = tmp_path / "report.json"
        argv = ["score", "--corpus", str(corpus), "--predictions", str(predictions)]

        code = aa.main([*argv, "--output", str(out), "--bootstrap", "20"])

        text = out.read_text(encoding="utf-8")
        assert code == 0
        assert '"corpus_sha256": "stub-c.jsonl"' in text
        assert '"predictions_sha256": "stub-p.jsonl"' in text

    def test_an_unreadable_input_still_exits_two(self, tmp_path: Path) -> None:
        """The OSError handling moved with the helper's caller, not away."""
        argv = ["score", "--corpus", str(tmp_path / "no.jsonl")]
        argv += ["--predictions", str(tmp_path / "no2.jsonl"), "--output", str(tmp_path / "r.json")]

        assert aa.main(argv) == 2
