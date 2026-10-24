"""Tests for whole-bundle hashing and bundle-directory apply (issue 6655 gap 2)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
import skillopt
from skillopt_helpers import Capture, valid_eval, write_json


def make_bundle(root: Path, script: str = "print('old')\n") -> Path:
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_bytes(b"a\nb")
    (root / "scripts" / "check.py").write_text(script, encoding="utf-8")
    (root / "references").mkdir()
    (root / "references" / "r.md").write_text("ref\n", encoding="utf-8")
    return root


def expected_digest(entries: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for rel in sorted(entries):
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(entries[rel]).hexdigest().encode("ascii") + b"\n")
    return h.hexdigest()


def symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")


class TestBundleHash:
    def test_digest_matches_documented_construction(self, tmp_path: Path) -> None:
        bundle = make_bundle(tmp_path / "b")
        want = expected_digest(
            {
                "SKILL.md": b"a\nb",
                "scripts/check.py": b"print('old')\n",
                "references/r.md": b"ref\n",
            }
        )
        assert skillopt.bundle_sha256(bundle) == want

    def test_hash_cli_prints_directory_digest(self, tmp_path: Path, capsys: Capture) -> None:
        bundle = make_bundle(tmp_path / "b")
        assert skillopt.main(["hash", str(bundle)]) == 0
        assert capsys.readouterr().out == f"{skillopt.bundle_sha256(bundle)}  {bundle}\n"

    def test_script_change_changes_digest_when_skill_md_is_identical(self, tmp_path: Path) -> None:
        old = make_bundle(tmp_path / "old")
        new = make_bundle(tmp_path / "new", script="print('new')\n")
        assert (old / "SKILL.md").read_bytes() == (new / "SKILL.md").read_bytes()
        assert skillopt.bundle_sha256(old) != skillopt.bundle_sha256(new)

    def test_same_content_same_digest_regardless_of_creation_order(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        for root, names in ((first, ("a", "b", "c")), (second, ("c", "b", "a"))):
            root.mkdir()
            for name in names:
                (root / f"{name}.txt").write_text(name, encoding="utf-8")
        assert skillopt.bundle_sha256(first) == skillopt.bundle_sha256(second)

    def test_path_is_part_of_the_digest(self, tmp_path: Path) -> None:
        one, two = tmp_path / "one", tmp_path / "two"
        one.mkdir()
        two.mkdir()
        (one / "a.txt").write_text("x", encoding="utf-8")
        (two / "b.txt").write_text("x", encoding="utf-8")
        assert skillopt.bundle_sha256(one) != skillopt.bundle_sha256(two)

    def test_pycache_is_ignored(self, tmp_path: Path) -> None:
        bundle = make_bundle(tmp_path / "b")
        before = skillopt.bundle_sha256(bundle)
        cache = bundle / "scripts" / "__pycache__"
        cache.mkdir()
        (cache / "check.cpython-314.pyc").write_bytes(b"\x00junk")
        assert skillopt.bundle_sha256(bundle) == before

    def test_symlink_in_bundle_is_refused(self, tmp_path: Path, capsys: Capture) -> None:
        bundle = make_bundle(tmp_path / "b")
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        symlink_or_skip(bundle / "link.txt", outside)
        assert skillopt.main(["hash", str(bundle)]) == 2
        assert "symlink" in capsys.readouterr().err

    def test_symlinked_directory_in_bundle_is_refused(self, tmp_path: Path) -> None:
        bundle = make_bundle(tmp_path / "b")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        symlink_or_skip(bundle / "dirlink", elsewhere)
        with pytest.raises(skillopt.SkillOptError, match="symlink"):
            skillopt.bundle_sha256(bundle)

    def test_expect_accepts_directory_digest(self, tmp_path: Path) -> None:
        bundle = make_bundle(tmp_path / "b")
        digest = skillopt.bundle_sha256(bundle)
        assert skillopt.main(["hash", str(bundle), "--expect", digest]) == 0

    def test_expect_mismatch_on_directory_exits_one(self, tmp_path: Path, capsys: Capture) -> None:
        bundle = make_bundle(tmp_path / "b")
        assert skillopt.main(["hash", str(bundle), "--expect", "0" * 64]) == 1
        assert "MISMATCH" in capsys.readouterr().out

    def test_empty_directory_hashes_without_error(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        assert skillopt.bundle_sha256(empty) == hashlib.sha256(b"").hexdigest()


class TestApplyBundle:
    @staticmethod
    def argv(tmp_path: Path, skill: Path, out: Path | None, *extra: str) -> list[str]:
        patches = write_json(tmp_path / "p.json", [{"op": "append", "text": "c"}])
        argv = [
            "apply",
            "--eval",
            str(valid_eval(tmp_path)),
            "--skill",
            str(skill),
            "--patches",
            str(patches),
            "--budget",
            "1",
        ]
        if out is not None:
            argv += ["--out", str(out)]
        return [*argv, *extra]

    def test_patches_skill_md_and_carries_the_rest_of_the_bundle(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        before = skillopt.bundle_sha256(incumbent)
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 0
        assert (out / "SKILL.md").read_bytes() == b"a\nb\nc"
        assert (out / "scripts" / "check.py").read_text(encoding="utf-8") == "print('old')\n"
        assert (out / "references" / "r.md").read_text(encoding="utf-8") == "ref\n"
        assert skillopt.bundle_sha256(incumbent) == before
        assert (incumbent / "SKILL.md").read_bytes() == b"a\nb"

    def test_reports_candidate_bundle_digest(self, tmp_path: Path, capsys: Capture) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 0
        assert f"bundle sha256 {skillopt.bundle_sha256(out)}" in capsys.readouterr().err

    def test_script_edit_in_candidate_changes_whole_bundle_digest(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 0
        applied = skillopt.bundle_sha256(out)
        (out / "scripts" / "check.py").write_text("print('new')\n", encoding="utf-8")
        assert skillopt.bundle_sha256(out) != applied

    def test_refuses_existing_out_directory(self, tmp_path: Path, capsys: Capture) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        out = tmp_path / "cand"
        out.mkdir()
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2
        assert "already exists" in capsys.readouterr().err

    def test_refuses_out_equal_to_incumbent(self, tmp_path: Path, capsys: Capture) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        assert skillopt.main(self.argv(tmp_path, incumbent, incumbent)) == 2
        assert "refusing to overwrite the incumbent" in capsys.readouterr().err
        assert (incumbent / "SKILL.md").read_bytes() == b"a\nb"

    def test_refuses_out_inside_incumbent(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        out = incumbent / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2
        assert not out.exists()

    def test_refuses_incumbent_inside_out(self, tmp_path: Path) -> None:
        out = tmp_path / "cand"
        incumbent = make_bundle(out / "inc")
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2

    def test_refuses_bundle_with_symlink_before_writing(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        outside = tmp_path / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        symlink_or_skip(incumbent / "link.txt", outside)
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2
        assert not out.exists()

    def test_missing_skill_md_in_bundle_exits_two(self, tmp_path: Path) -> None:
        incumbent = tmp_path / "inc"
        incumbent.mkdir()
        (incumbent / "other.md").write_text("x", encoding="utf-8")
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2
        assert not out.exists()

    def test_bad_anchor_leaves_no_candidate_directory(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        patches = write_json(tmp_path / "bad.json", [{"op": "delete", "anchor": "missing"}])
        out = tmp_path / "cand"
        argv = self.argv(tmp_path, incumbent, out)
        argv[argv.index("--patches") + 1] = str(patches)
        assert skillopt.main(argv) == 2
        assert not out.exists()

    def test_failed_copy_leaves_no_partial_candidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shutil

        incumbent = make_bundle(tmp_path / "inc")
        real_copy = shutil.copy
        calls = {"n": 0}

        def flaky(src: Path, dst: Path) -> object:
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("disk full")
            return real_copy(src, dst)

        monkeypatch.setattr(shutil, "copy", flaky)
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2
        assert not out.exists()
        assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []

    def test_unwritable_skill_md_cannot_leave_an_unpatched_candidate(self, tmp_path: Path) -> None:
        if os.name != "posix":
            pytest.skip("POSIX file modes")
        incumbent = make_bundle(tmp_path / "inc")
        (incumbent / "SKILL.md").chmod(0o444)
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 0
        assert (out / "SKILL.md").read_bytes() == b"a\nb\nc"

    def test_missing_out_parent_is_refused_without_creating_it(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        out = tmp_path / "new" / "deep" / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 2
        assert not (tmp_path / "new").exists()

    def test_requires_out_unless_dry_run(self, tmp_path: Path) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        assert skillopt.main(self.argv(tmp_path, incumbent, None)) == 2

    def test_dry_run_writes_nothing(self, tmp_path: Path, capsys: Capture) -> None:
        incumbent = make_bundle(tmp_path / "inc")
        assert skillopt.main(self.argv(tmp_path, incumbent, None, "--dry-run")) == 0
        assert "apply cleanly" in capsys.readouterr().err
        assert sorted(p.name for p in tmp_path.iterdir()) == ["evals", "inc", "p.json"]

    def test_single_file_apply_still_works(self, tmp_path: Path) -> None:
        skill = tmp_path / "SKILL.md"
        skill.write_bytes(b"a\nb")
        out = tmp_path / "cand.md"
        assert skillopt.main(self.argv(tmp_path, skill, out)) == 0
        assert out.read_bytes() == b"a\nb\nc"

    def test_copy_keeps_executable_bit(self, tmp_path: Path) -> None:
        if os.name != "posix":
            pytest.skip("POSIX file modes")
        incumbent = make_bundle(tmp_path / "inc")
        tool = incumbent / "scripts" / "check.py"
        tool.chmod(0o755)
        out = tmp_path / "cand"
        assert skillopt.main(self.argv(tmp_path, incumbent, out)) == 0
        assert os.access(out / "scripts" / "check.py", os.X_OK)
        assert sorted(p.name for p in out.iterdir()) == ["SKILL.md", "references", "scripts"]
