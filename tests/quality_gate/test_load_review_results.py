"""Tests for scripts/quality_gate/load_review_results.py.

Pins the verdict/infra loading of the extracted ``Load review results``
workflow step, including the empty-file and missing-file edge cases that the
original Get-Content -Raw + Trim() pwsh code produced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.quality_gate.load_review_results import (
    _read_raw,
    collect,
    main,
    read_infra,
    read_verdict,
    write_outputs,
)

_AGENTS = (
    "security",
    "qa",
    "analyst",
    "architect",
    "devops",
    "roadmap",
    "reliability",
    "observability",
    "agent-safety",
    "decision-rigor",
)


def _seed(results_dir: Path, verdict: str = "PASS", infra: str | None = None) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    for agent in _AGENTS:
        (results_dir / f"{agent}-verdict.txt").write_text(verdict, encoding="utf-8")
        if infra is not None:
            (results_dir / f"{agent}-infrastructure-failure.txt").write_text(
                infra, encoding="utf-8"
            )


# ---------------------------------------------------------------------------
# read_verdict
# ---------------------------------------------------------------------------


class TestReadVerdict:
    def test_trims_content(self, tmp_path: Path) -> None:
        (tmp_path / "security-verdict.txt").write_text("  PASS\n", encoding="utf-8")
        assert read_verdict(tmp_path, "security") == "PASS"

    def test_missing_file_yields_needs_review(self, tmp_path: Path) -> None:
        assert read_verdict(tmp_path, "security") == "NEEDS_REVIEW"

    def test_empty_file_yields_needs_review(self, tmp_path: Path) -> None:
        (tmp_path / "qa-verdict.txt").write_text("", encoding="utf-8")
        assert read_verdict(tmp_path, "qa") == "NEEDS_REVIEW"

    def test_unreadable_file_raises(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "qa-verdict.txt").write_text("PASS", encoding="utf-8")

        def unreadable(*_args, **_kwargs):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "read_text", unreadable)
        try:
            read_verdict(tmp_path, "qa")
        except RuntimeError as exc:
            assert "Unable to read review result file" in str(exc)
        else:  # pragma: no cover - assertion clarity
            raise AssertionError("unreadable verdict must not pass")

    def test_whitespace_only_file_yields_empty(self, tmp_path: Path) -> None:
        # Mirrors pwsh: Get-Content -Raw returns the whitespace (truthy),
        # then Trim() empties it.
        (tmp_path / "qa-verdict.txt").write_text("   \n", encoding="utf-8")
        assert read_verdict(tmp_path, "qa") == ""


# ---------------------------------------------------------------------------
# read_infra
# ---------------------------------------------------------------------------


class TestReadInfra:
    def test_trims_content(self, tmp_path: Path) -> None:
        (tmp_path / "security-infrastructure-failure.txt").write_text(
            "true\n", encoding="utf-8"
        )
        assert read_infra(tmp_path, "security") == "true"

    def test_missing_file_yields_false(self, tmp_path: Path) -> None:
        assert read_infra(tmp_path, "security") == "false"

    def test_empty_file_yields_false(self, tmp_path: Path) -> None:
        (tmp_path / "qa-infrastructure-failure.txt").write_text("", encoding="utf-8")
        assert read_infra(tmp_path, "qa") == "false"


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------


class TestCollect:
    def test_collects_ten_agents_in_order(self, tmp_path: Path) -> None:
        _seed(tmp_path, verdict="PASS", infra="false")
        rows = collect(tmp_path)
        assert [agent for agent, _, _ in rows] == list(_AGENTS)
        assert all(verdict == "PASS" for _, verdict, _ in rows)
        assert all(infra == "false" for _, _, infra in rows)

    def test_mixed_present_and_missing(self, tmp_path: Path) -> None:
        (tmp_path / "security-verdict.txt").write_text("FAIL", encoding="utf-8")
        (tmp_path / "security-infrastructure-failure.txt").write_text(
            "true", encoding="utf-8"
        )
        rows = dict((agent, (v, i)) for agent, v, i in collect(tmp_path))
        assert rows["security"] == ("FAIL", "true")
        # Missing files for other agents fall back to the defaults.
        assert rows["qa"] == ("NEEDS_REVIEW", "false")


# ---------------------------------------------------------------------------
# write_outputs / main
# ---------------------------------------------------------------------------


class TestWriteOutputs:
    def test_writes_verdict_and_infra_lines(self, tmp_path: Path) -> None:
        output = tmp_path / "out"
        output.touch()
        write_outputs(output, [("security", "PASS", "false")])
        text = output.read_text(encoding="utf-8")
        assert "security_verdict=PASS" in text
        assert "security_infra=false" in text


class TestMain:
    def test_writes_all_outputs_and_returns_zero(self, tmp_path, monkeypatch) -> None:
        results = tmp_path / "ai-review-results"
        _seed(results, verdict="PASS", infra="false")
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main(["--results-dir", str(results)])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        for agent in _AGENTS:
            assert f"{agent}_verdict=PASS" in text
            assert f"{agent}_infra=false" in text

    def test_missing_github_output_returns_two(self, tmp_path, monkeypatch) -> None:
        results = tmp_path / "ai-review-results"
        _seed(results)
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = main(["--results-dir", str(results)])
        assert rc == 2

    def test_missing_verdict_files_use_defaults(self, tmp_path, monkeypatch) -> None:
        results = tmp_path / "ai-review-results"
        results.mkdir()
        output = tmp_path / "gh_output"
        output.touch()
        monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        rc = main(["--results-dir", str(results)])
        assert rc == 0
        text = output.read_text(encoding="utf-8")
        assert "security_verdict=NEEDS_REVIEW" in text
        assert "security_infra=false" in text


# ---------------------------------------------------------------------------
# _read_raw fail-loud on unreadable files (issue #2809)
# ---------------------------------------------------------------------------


class TestReadRawFailLoud:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert _read_raw(tmp_path / "absent.txt") is None

    def test_present_readable_file_returns_text(self, tmp_path: Path) -> None:
        target = tmp_path / "verdict.txt"
        target.write_text("PASS", encoding="utf-8")
        assert _read_raw(target) == "PASS"

    def test_unreadable_file_raises_oserror(self, tmp_path: Path) -> None:
        # Directory read raises IsADirectoryError (OSError subclass): a
        # present-but-unreadable file must not be swallowed into None.
        unreadable = tmp_path / "verdict.txt"
        unreadable.mkdir()
        with pytest.raises(RuntimeError):
            _read_raw(unreadable)

    def test_read_infra_missing_still_false(self, tmp_path: Path) -> None:
        # Genuinely missing infra file keeps the intended default.
        assert read_infra(tmp_path, "security") == "false"

    def test_collect_propagates_unreadable_infra(self, tmp_path: Path) -> None:
        (tmp_path / "security-infrastructure-failure.txt").mkdir()
        with pytest.raises(RuntimeError):
            collect(tmp_path)

    def test_main_returns_three_on_unreadable_file(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        results = tmp_path / "ai-review-results"
        results.mkdir()
        (results / "security-infrastructure-failure.txt").mkdir()
        # GITHUB_OUTPUT is irrelevant: collect() fails before it is read.
        monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
        rc = main(["--results-dir", str(results)])
        assert rc == 3
        err = capsys.readouterr().err
        assert "cannot read verdict/infra file" in err
