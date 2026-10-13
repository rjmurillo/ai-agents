"""Tests for distill_artifact module.

Covers kind detection, text and diff digests, caching, CLI output formats,
exit codes, and default out-dir resolution.

Exit Codes:
    0: Success - All tests passed
    1: Error - One or more tests failed (set by pytest framework)

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).parent.parent.parent
scripts_dir = repo_root / ".claude" / "skills" / "context-optimizer" / "scripts"
sys.path.insert(0, str(scripts_dir))

import distill_artifact as da  # noqa: E402

ROOT_DIRNAME = ".project-toolkit"
DASHES = ("\u2013", "\u2014")

DIFF = """diff --git a/src/a.py b/src/a.py
index 111..222 100644
--- a/src/a.py
+++ b/src/a.py
@@ -1,3 +1,3 @@
 keep
-old line
-- dashed removal
\\ No newline at end of file
+new line
+another
@@ -10 +11 @@
-x
+y
diff --git a/b.txt b/b.txt
--- a/b.txt
+++ b/b.txt
@@ -1,2 +1,2 @@
 same
-gone
+here
"""

PLAIN_DIFF = """--- old.txt
+++ new.txt
@@ -1 +1 @@
-a
+b
--- other.txt
+++ other2.txt
@@ -1 +1 @@
-c
+d
"""


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def run(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = da.main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def digest_text(out: str) -> str:
    return Path(out.strip()).read_text(encoding="utf-8")


class TestDetectKind:
    def test_diff_git_header(self) -> None:
        assert da.detect_kind(["x", "diff --git a/f b/f"]) == "diff"

    def test_diff_unified_headers(self) -> None:
        assert da.detect_kind(["--- a", "+++ b"]) == "diff"

    def test_text_only_old_header(self) -> None:
        assert da.detect_kind(["--- a", "plain"]) == "text"

    def test_text_only_new_header(self) -> None:
        assert da.detect_kind(["+++ b"]) == "text"

    def test_text_empty(self) -> None:
        assert da.detect_kind([]) == "text"


class TestClip:
    def test_short_unchanged(self) -> None:
        assert da.clip("abc") == "abc"

    def test_exact_cap_unchanged(self) -> None:
        assert da.clip("a" * 240) == "a" * 240

    def test_long_truncated(self) -> None:
        assert da.clip("a" * 500) == "a" * 240


class TestTextDigest:
    def test_signal_dedup_counts_and_first_line(self, tmp_path, capsys) -> None:
        src = write(
            tmp_path,
            "log.txt",
            "ok\nerror code 12 at 3\nok\nerror code 99 at 7\nFatal: boom\n",
        )
        code, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert code == 0
        assert "- L2 (x2): error code # at #" in body
        assert "- L5 (x1): Fatal: boom" in body
        assert body.count("error code") == 3  # one signal entry, two full-text lines

    def test_signal_counts_collapse_digits(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "error 1 x\nerror 2 x\nerror 3 x\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        assert "- L1 (x3): error # x" in digest_text(out)

    def test_signal_cap_and_omitted_note(self, tmp_path, capsys) -> None:
        lines = "".join(f"error kind{chr(97 + i)}\n" for i in range(5))
        src = write(tmp_path, "log.txt", lines)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o"), "--max-matches", "2"], capsys)
        body = digest_text(out)
        assert "- 3 more omitted" in body
        assert "kindc" not in body.split("## Full text")[0]

    def test_no_signal_lines(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "all good\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        assert "## Signal lines\n\n- none" in digest_text(out)

    def test_short_text_shown_whole(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "a\nb\nc\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o"), "--edge-lines", "3"], capsys)
        body = digest_text(out)
        assert "## Full text" in body
        assert "1: a" in body and "3: c" in body
        assert "## First" not in body

    def test_long_text_head_and_tail_numbered(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "".join(f"line{i}\n" for i in range(1, 11)))
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o"), "--edge-lines", "2"], capsys)
        body = digest_text(out)
        assert "## First 2 lines" in body and "## Last 2 lines" in body
        assert "1: line1" in body and "2: line2" in body
        assert "9: line9" in body and "10: line10" in body
        assert "5: line5" not in body

    def test_long_line_truncated_at_240(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "error " + "x" * 400 + "\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "x" * 400 not in body
        assert max(len(line) for line in body.splitlines() if "xxxx" in line) <= 240 + 40

    def test_header_fields(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "a\nb\n")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert f"- source: {src}" in body
        assert "- kind: text" in body
        assert "- raw bytes: 4" in body
        assert "- raw lines: 2" in body
        assert "- sha256: " in body and len(body.split("- sha256: ")[1].split("\n")[0]) == 64


class TestDiffDigest:
    def test_per_file_counts(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "d.diff", DIFF)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "- kind: diff" in body
        assert "| src/a.py | 3 | 3 | 2 |" in body
        assert "| b.txt | 1 | 1 | 1 |" in body

    def test_hunk_headers_with_line_numbers(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "d.diff", DIFF)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "- L5: @@ -1,3 +1,3 @@" in body
        assert "- L12: @@ -10 +11 @@" in body

    def test_hunk_cap_with_omitted(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "d.diff", DIFF)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o"), "--max-matches", "1"], capsys)
        body = digest_text(out)
        assert "- 2 more omitted" in body
        assert "@@ -10 +11 @@" not in body

    def test_plain_unified_diff_without_git_header(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "p.diff", PLAIN_DIFF)
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        body = digest_text(out)
        assert "| new.txt | 1 | 1 | 1 |" in body
        assert "| other2.txt | 1 | 1 | 1 |" in body

    def test_hunk_header_before_any_file_ignored(self) -> None:
        scan = da.scan_diff(["@@ -1 +1 @@", "-a", "+b"])
        assert scan.files == [] and scan.hunk_headers == []

    def test_git_header_without_b_prefix(self) -> None:
        assert da._path_from_git_header("diff --git weird") == "weird"

    def test_plus_header_strips_tab_suffix_and_prefix(self) -> None:
        assert da._path_from_plus_header("+++ b/x.py\t2020-01-01") == "x.py"
        assert da._path_from_plus_header("+++ raw.py") == "raw.py"


class TestCaching:
    def test_second_call_cached_and_not_rewritten(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "error a\n")
        out_dir = str(tmp_path / "o")
        _, first, _ = run([str(src), "--out-dir", out_dir, "--format", "json"], capsys)
        digest = Path(json.loads(first)["digest"])
        digest.write_text("SENTINEL", encoding="utf-8")
        mtime = digest.stat().st_mtime_ns
        _, second, _ = run([str(src), "--out-dir", out_dir, "--format", "json"], capsys)
        data = json.loads(second)
        assert json.loads(first)["cached"] is False
        assert data["cached"] is True
        assert digest.read_text(encoding="utf-8") == "SENTINEL"
        assert digest.stat().st_mtime_ns == mtime
        assert data["digest_bytes"] == len("SENTINEL")

    def test_different_options_different_key(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "error a\n")
        out_dir = str(tmp_path / "o")
        _, a, _ = run([str(src), "--out-dir", out_dir], capsys)
        _, b, _ = run([str(src), "--out-dir", out_dir, "--edge-lines", "3"], capsys)
        _, c, _ = run([str(src), "--out-dir", out_dir, "--max-matches", "3"], capsys)
        assert len({a.strip(), b.strip(), c.strip()}) == 3

    def test_different_content_different_key(self) -> None:
        assert da.cache_key(b"a", 1, 1) != da.cache_key(b"b", 1, 1)
        assert da.cache_key(b"a", 1, 1).startswith(da.cache_key(b"a", 2, 2)[:16])


class TestCli:
    def test_stdin(self, tmp_path, capsys, monkeypatch) -> None:
        class FakeStdin:
            buffer = io.BytesIO(b"fatal oops\n")

        monkeypatch.setattr(sys, "stdin", FakeStdin())
        code, out, _ = run(["-", "--out-dir", str(tmp_path / "o")], capsys)
        assert code == 0
        assert "- source: stdin" in digest_text(out)

    def test_json_fields_and_ratio(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "log.txt", "error a\n" * 50)
        code, out, _ = run([str(src), "--out-dir", str(tmp_path / "o"), "--format", "json"], capsys)
        data = json.loads(out)
        assert code == 0
        assert set(data) == {"digest", "cached", "kind", "raw_bytes", "digest_bytes", "ratio"}
        assert data["kind"] == "text"
        assert data["raw_bytes"] == 400
        assert data["ratio"] == round(data["digest_bytes"] / 400, 3)
        assert data["digest_bytes"] == Path(data["digest"]).stat().st_size

    def test_empty_input_ratio_zero(self, tmp_path, capsys) -> None:
        src = write(tmp_path, "empty.txt", "")
        _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o"), "--format", "json"], capsys)
        assert json.loads(out)["ratio"] == 0.0

    def test_invalid_utf8_replaced(self, tmp_path, capsys) -> None:
        src = tmp_path / "bin.txt"
        src.write_bytes(b"error \xff\xfe\n")
        code, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        assert code == 0
        assert "�" in digest_text(out)

    def test_missing_file_exit_2(self, tmp_path, capsys) -> None:
        code, out, err = run([str(tmp_path / "nope.txt")], capsys)
        assert code == 2 and out == "" and "not found" in err

    def test_directory_path_exit_2(self, tmp_path, capsys) -> None:
        code, _, _ = run([str(tmp_path)], capsys)
        assert code == 2

    def test_bad_option_exit_2(self, tmp_path, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            da.main([str(tmp_path), "--format", "xml"])
        assert exc.value.code == 2

    def test_negative_option_exit_2(self, tmp_path) -> None:
        with pytest.raises(SystemExit) as exc:
            da.main([str(tmp_path), "--max-matches", "-1"])
        assert exc.value.code == 2

    def test_unreadable_input_exit_3(self, tmp_path, capsys, monkeypatch) -> None:
        src = write(tmp_path, "log.txt", "x")

        def boom(self: Path) -> bytes:
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "read_bytes", boom)
        code, _, err = run([str(src)], capsys)
        assert code == 3 and "cannot read" in err

    def test_write_oserror_exit_3(self, tmp_path, capsys, monkeypatch) -> None:
        src = write(tmp_path, "log.txt", "x")

        def boom(self: Path, *a: object, **k: object) -> int:
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", boom)
        code, out, err = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
        assert code == 3 and out == "" and "cannot write" in err


@pytest.fixture(autouse=True)
def _clear_artifact_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_AGENTS_ARTIFACT_ROOT", raising=False)


class TestOutDir:
    def test_artifact_root_override_wins(self, tmp_path, monkeypatch) -> None:
        (tmp_path / ".git").mkdir()
        override = tmp_path / "custom"
        override.mkdir()
        monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(override))
        assert da.default_out_dir(tmp_path) == override.resolve() / da.DISTILL_SUBDIR

    def test_main_honors_artifact_root_override(self, tmp_path, capsys, monkeypatch) -> None:
        override = tmp_path / "custom"
        override.mkdir()
        monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(override))
        src = write(tmp_path, "log.txt", "error a\n")
        _, out, _ = run([str(src)], capsys)
        assert Path(out.strip()).parent == override.resolve() / da.DISTILL_SUBDIR

    def test_inside_repo_uses_repo_root(self, tmp_path) -> None:
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        assert da.default_out_dir(sub) == tmp_path.resolve() / ROOT_DIRNAME / da.DISTILL_SUBDIR

    def test_git_file_marks_worktree_root(self, tmp_path) -> None:
        (tmp_path / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
        assert da.find_repo_root(tmp_path.resolve()) == tmp_path.resolve()

    def test_outside_repo_falls_back_to_cwd(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(da, "find_repo_root", lambda start: None)
        monkeypatch.chdir(tmp_path)
        assert da.default_out_dir(tmp_path) == tmp_path.resolve() / ROOT_DIRNAME / da.DISTILL_SUBDIR

    def test_find_repo_root_none_when_absent(self, tmp_path) -> None:
        found = da.find_repo_root(tmp_path.resolve())
        assert found is None or (found / ".git").exists()

    def test_main_default_out_dir(self, tmp_path, capsys, monkeypatch) -> None:
        (tmp_path / ".git").mkdir()
        src = write(tmp_path, "log.txt", "error a\n")
        monkeypatch.chdir(tmp_path)
        _, out, _ = run([str(src)], capsys)
        expected = tmp_path.resolve() / ROOT_DIRNAME / da.DISTILL_SUBDIR
        assert Path(out.strip()).parent == expected


class TestNoDashes:
    def test_digests_have_no_en_or_em_dashes(self, tmp_path, capsys) -> None:
        text = write(tmp_path, "t.txt", "error x\n" + "line\n" * 60)
        diff = write(tmp_path, "d.diff", DIFF)
        for src in (text, diff):
            _, out, _ = run([str(src), "--out-dir", str(tmp_path / "o")], capsys)
            body = digest_text(out)
            assert not any(d in body for d in DASHES)
            assert "generated" not in body.lower()


def test_main_module_guard(tmp_path, monkeypatch) -> None:
    import runpy

    src = write(tmp_path, "log.txt", "x\n")
    monkeypatch.setattr(
        sys, "argv", ["distill_artifact.py", str(src), "--out-dir", str(tmp_path / "o")]
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(scripts_dir / "distill_artifact.py"), run_name="__main__")
    assert exc.value.code == 0


class TestPathsLibBootstrap:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch) -> None:
        for name in ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
            monkeypatch.delenv(name, raising=False)

    def test_plugin_root(self, tmp_path, monkeypatch) -> None:
        (tmp_path / "lib").mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
        assert da._resolve_paths_lib_dir() == (tmp_path / "lib").resolve()

    def test_default_is_sibling_lib(self) -> None:
        assert da._resolve_paths_lib_dir() == (repo_root / ".claude" / "lib").resolve()

    def test_missing_lib_dir_raises(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(tmp_path))
        with pytest.raises(RuntimeError, match="lib directory not found"):
            da._resolve_paths_lib_dir()
