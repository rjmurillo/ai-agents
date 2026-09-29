"""Tests for the head materialization and review findings of verify_dispatch_closure.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from tests.ci.dispatch_closure_helpers import (  # noqa: F401
    CONFIG,
    GATE,
    HELPER,
    VERIFIER,
    git,
    rev,
    run,
    upstream_with_pr,
    vdc,
    write,
)


class TestMaterializeHead:
    def test_the_head_is_written_from_the_object_store_with_no_git_directory(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})
        dest = tmp_path / "out"

        vdc.materialize_head(base, 1, sha, dest, remote=str(upstream))

        assert (dest / HELPER).read_text(encoding="utf-8") == "X = 99\n"
        assert not (dest / ".git").exists()
        assert not (tmp_path / "out.index").exists()

    def test_export_ignore_in_the_heads_gitattributes_cannot_hide_a_file(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(
            base, {HELPER: "X = 99\n"}, attributes=f"{HELPER} export-ignore\n"
        )
        dest = tmp_path / "out"

        vdc.materialize_head(base, 1, sha, dest, remote=str(upstream))

        assert (dest / HELPER).is_file()

    def test_a_head_that_moved_since_the_event_aborts(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, _sha = upstream_with_pr(base, {HELPER: "X = 99\n"})

        with pytest.raises(vdc.DispatchClosureError, match="head moved"):
            vdc.materialize_head(base, 1, "a" * 40, tmp_path / "out", remote=str(upstream))

    @pytest.mark.parametrize("sha", ["", "HEAD", "abc", "A" * 40, "--upload-pack=x", "a" * 39])
    def test_a_malformed_sha_is_refused_before_any_git_call(
        self, trees: tuple[Path, Path], tmp_path: Path, sha: str
    ) -> None:
        base, _ = trees

        with pytest.raises(vdc.DispatchClosureError, match="not a full commit id"):
            vdc.materialize_head(base, 1, sha, tmp_path / "out")

    def test_a_missing_pull_request_ref_is_a_configuration_error(
        self, trees: tuple[Path, Path], tmp_path: Path
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})

        with pytest.raises(vdc.DispatchClosureError, match="fetch failed"):
            vdc.materialize_head(base, 7, sha, tmp_path / "out", remote=str(upstream))

    def test_every_git_call_reading_the_head_carries_the_inert_configuration(
        self, trees: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})
        spy = mock.Mock(wraps=subprocess.run)
        monkeypatch.setattr(vdc.subprocess, "run", spy)

        vdc.materialize_head(base, 1, sha, tmp_path / "out", remote=str(upstream))

        calls = [list(c.args[0]) for c in spy.call_args_list]
        git_calls = [c for c in calls if c[0] == "git"]
        assert [c[c.index("core.fsmonitor=false") - 1] for c in git_calls] == ["-c"] * len(
            git_calls
        )
        assert all("core.hooksPath=/dev/null" in c for c in git_calls)
        assert {c[5] for c in git_calls} == {"fetch", "rev-parse", "read-tree", "checkout-index"}

    def test_main_verifies_a_head_it_fetched_itself(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})

        code = vdc.main(
            [
                "--tool-root",
                str(base),
                "--head-sha",
                sha,
                "--pull-number",
                "1",
                "--remote",
                str(upstream),
                "--json",
            ]
        )

        assert code == vdc.EXIT_DIFFERS
        assert json.loads(capsys.readouterr().out)["changed"] == [HELPER]

    @pytest.mark.parametrize(
        "extra",
        [[], ["--head-sha", "a" * 40], ["--pull-number", "1"]],
    )
    def test_main_needs_a_head_root_or_a_sha_and_a_number(
        self, trees: tuple[Path, Path], extra: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees

        code = vdc.main(["--tool-root", str(base), *extra])

        assert code == vdc.EXIT_CONFIG
        assert "give --head-root" in capsys.readouterr().err


class TestSecurityReviewFindings:
    """Findings from the security review of this change, each with its fix."""

    def test_a_symlink_the_head_adds_is_reported_even_when_its_bytes_match(
        self, trees: tuple[Path, Path]
    ) -> None:
        _, head = trees
        (head / "alias.py").symlink_to(head / HELPER)

        report = run(trees)

        assert report.symlinks == ["alias.py"]
        assert not report.clean

    def test_a_symlink_the_base_already_has_is_not_reported(self, trees: tuple[Path, Path]) -> None:
        base, head = trees
        (base / "existing_link.py").symlink_to("README.md")
        git(base, "add", "-A")
        git(base, "commit", "-q", "-m", "link")
        git(head, "checkout", "--detach", "-q", "--force", rev(base))

        assert run(trees).symlinks == []

    def test_a_dispatched_file_replaced_by_a_symlink_to_identical_bytes_is_reported(
        self, trees: tuple[Path, Path]
    ) -> None:
        _, head = trees
        original = (head / HELPER).read_bytes()
        (head / HELPER).unlink()
        (head / "elsewhere.py").write_bytes(original)
        (head / HELPER).symlink_to(head / "elsewhere.py")

        assert HELPER in run(trees).symlinks

    def test_the_output_never_prints_a_control_character_raw(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = vdc.Report(
            examined=1, changed=["a.py\n::error::forged"], unresolved=["b\r\x1b[31m"]
        )

        vdc._print(report, as_json=False)

        out = capsys.readouterr().out
        assert "::error::forged" in out
        assert all(not line.startswith("::") for line in out.splitlines())
        assert "\x1b" not in out
        assert "\r" not in out

    @pytest.mark.parametrize(
        ("raw", "escaped"),
        [
            ("a\nb", "a\\x0ab"),
            ("tab\there", "tab\\x09here"),
            ("del\x7f", "del\\x7f"),
            ("caf\u00e9", "caf\\xe9"),
        ],
    )
    def test_plain_escapes_controls_and_non_ascii(self, raw: str, escaped: str) -> None:
        assert vdc._plain(raw) == escaped

    def test_a_head_gitattributes_eol_conversion_cannot_fake_a_change_or_hide_one(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Compared by blob id, an eol attribute in the head changes neither answer."""
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {}, attributes=f"{HELPER} text eol=crlf\n")

        code = vdc.main(
            [
                "--tool-root",
                str(base),
                "--head-sha",
                sha,
                "--pull-number",
                "1",
                "--remote",
                str(upstream),
                "--json",
            ]
        )

        assert code == vdc.EXIT_OK
        assert json.loads(capsys.readouterr().out)["changed"] == []

    def test_a_real_edit_is_still_reported_by_blob_id(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 2\n"})

        vdc.main(
            [
                "--tool-root",
                str(base),
                "--head-sha",
                sha,
                "--pull-number",
                "1",
                "--remote",
                str(upstream),
                "--json",
                "--advisory",
            ]
        )

        assert json.loads(capsys.readouterr().out)["changed"] == [HELPER]

    def test_head_root_and_head_sha_together_are_refused(
        self, trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
    ) -> None:
        base, head = trees

        code = vdc.main(
            [
                "--tool-root",
                str(base),
                "--head-root",
                str(head),
                "--head-sha",
                "a" * 40,
                "--pull-number",
                "1",
            ]
        )

        assert code == vdc.EXIT_CONFIG
        assert "not both" in capsys.readouterr().err

    def test_the_fetch_declines_to_recurse_into_submodules(
        self, trees: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        base, _ = trees
        upstream, sha = upstream_with_pr(base, {HELPER: "X = 99\n"})
        spy = mock.Mock(wraps=subprocess.run)
        monkeypatch.setattr(vdc.subprocess, "run", spy)

        vdc.materialize_head(base, 1, sha, tmp_path / "out", remote=str(upstream))

        seen = [list(c.args[0]) for c in spy.call_args_list]
        fetch = next(c for c in seen if "fetch" in c)
        assert "--no-recurse-submodules" in fetch
