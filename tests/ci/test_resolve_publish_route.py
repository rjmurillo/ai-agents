"""The publish route: the dispatch route is live and the tag route is dormant.

ADR-113 Resolved Question 2: until the owner creates the v* tag ruleset, a tag
push must not publish, because it runs the tagged commit's own copy of the
workflow. A dry run is the default whenever the input is missing.
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci.resolve_publish_route import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    EXIT_REFUSED,
    TAG_ROUTE_DORMANT,
    RouteRefusedError,
    decide_route,
    main,
    package_version,
)

SHA = "a" * 40
OTHER = "b" * 40


def _decide(**overrides: str):
    values = {
        "event": "workflow_dispatch",
        "ref": "refs/heads/main",
        "run_sha": SHA,
        "default_branch": "main",
        "candidate_input": "",
        "dry_run_input": "true",
        "release_tag_input": "",
    }
    values.update(overrides)
    return decide_route(**values)


class TestDecideRoute:
    def test_a_default_branch_dispatch_uses_the_run_commit_and_is_a_dry_run_by_default(
        self,
    ) -> None:
        decision = _decide()
        assert (decision.candidate_sha, decision.dry_run, decision.mode) == (SHA, True, "advisory")

    def test_a_real_publish_runs_the_gate_enforcing(self) -> None:
        decision = _decide(dry_run_input="false", candidate_input=SHA, release_tag_input="v1.2.3")
        assert (decision.candidate_sha, decision.mode, decision.release_tag) == (
            SHA,
            "enforcing",
            "v1.2.3",
        )

    def test_a_dry_run_may_name_an_older_candidate(self) -> None:
        assert _decide(candidate_input=OTHER).candidate_sha == OTHER

    def test_a_real_publish_of_another_candidate_is_refused(self) -> None:
        with pytest.raises(RouteRefusedError, match="provenance") as caught:
            _decide(dry_run_input="false", candidate_input=OTHER)
        assert caught.value.code == EXIT_REFUSED

    def test_the_tag_route_is_refused_with_the_reason(self) -> None:
        with pytest.raises(RouteRefusedError, match="dormant") as caught:
            _decide(event="push", ref="refs/tags/v1.2.3")
        assert caught.value.code == EXIT_REFUSED
        assert "ruleset" in TAG_ROUTE_DORMANT

    @pytest.mark.parametrize("event", ["pull_request", "schedule", "push", "workflow_call", ""])
    def test_any_other_event_is_refused(self, event: str) -> None:
        with pytest.raises(RouteRefusedError) as caught:
            _decide(event=event, ref="refs/heads/main")
        assert caught.value.code == EXIT_CONFIG

    @pytest.mark.parametrize(
        "ref", ["refs/heads/feature", "refs/tags/v1", "main", "", "refs/heads/"]
    )
    def test_a_dispatch_from_anywhere_but_the_default_branch_is_refused(self, ref: str) -> None:
        with pytest.raises(RouteRefusedError) as caught:
            _decide(ref=ref)
        assert caught.value.code == EXIT_REFUSED

    @pytest.mark.parametrize("branch", ["", "a b", "-x", "a\nb"])
    def test_a_bad_default_branch_name_is_refused(self, branch: str) -> None:
        with pytest.raises(RouteRefusedError):
            _decide(default_branch=branch, ref=f"refs/heads/{branch}")

    @pytest.mark.parametrize("candidate", ["abc", "A" * 40, "g" * 40, SHA + "0", "--all"])
    def test_a_malformed_candidate_is_refused(self, candidate: str) -> None:
        with pytest.raises(RouteRefusedError) as caught:
            _decide(candidate_input=candidate)
        assert caught.value.code == EXIT_CONFIG

    @pytest.mark.parametrize("value", ["", "yes", "TRUE", "1", "false\n"])
    def test_dry_run_must_be_true_or_false(self, value: str) -> None:
        with pytest.raises(RouteRefusedError) as caught:
            _decide(dry_run_input=value)
        assert caught.value.code == EXIT_CONFIG

    @pytest.mark.parametrize(
        "tag", ["1.2.3", "v1.2", "v1.2.3.4", "vx", "v1.2.3 ", "v1.2.3/../x", "-v1.2.3"]
    )
    def test_a_malformed_release_tag_is_refused(self, tag: str) -> None:
        with pytest.raises(RouteRefusedError):
            _decide(release_tag_input=tag)

    @pytest.mark.parametrize("tag", ["v0.1.0", "v10.20.30", "v1.2.3-rc.1", "v1.2.3-beta"])
    def test_a_release_tag_is_accepted(self, tag: str) -> None:
        assert _decide(release_tag_input=tag).release_tag == tag


def _argv(**overrides: str) -> list[str]:
    values = {
        "--event": "workflow_dispatch", "--ref": "refs/heads/main", "--run-sha": SHA,
        "--default-branch": "main", "--dry-run-input": "false", "--candidate-input": "",
        "--release-tag-input": "",
    }  # fmt: skip
    values.update(overrides)
    return ["route", *[token for pair in values.items() for token in pair]]


class TestRouteCli:
    def test_the_outputs_are_written_for_the_workflow(self, tmp_path: Path) -> None:
        sink = tmp_path / "out"
        assert main([*_argv(), "--github-output", str(sink)]) == EXIT_OK
        assert sink.read_text(encoding="utf-8").splitlines() == [
            f"candidate_sha={SHA}", "release_tag=", "dry_run=false", "mode=enforcing",
        ]  # fmt: skip

    def test_a_missing_dry_run_value_means_dry_run(self, tmp_path: Path) -> None:
        sink = tmp_path / "out"
        argv = [a for a in _argv() if a not in ("--dry-run-input", "false")]
        assert main([*argv, "--github-output", str(sink)]) == EXIT_OK
        assert "dry_run=true" in sink.read_text(encoding="utf-8")

    def test_the_tag_route_exits_one_and_writes_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sink = tmp_path / "out"
        argv = _argv(**{"--event": "push", "--ref": "refs/tags/v1.2.3"})
        assert main([*argv, "--github-output", str(sink)]) == EXIT_REFUSED
        assert not sink.exists()
        assert "dormant" in capsys.readouterr().err

    def test_a_config_error_exits_two(self) -> None:
        assert main(_argv(**{"--candidate-input": "abc"})) == EXIT_CONFIG

    def test_it_runs_without_an_output_file(self) -> None:
        assert main(_argv()) == EXIT_OK

    def test_the_entry_point_guard_returns_the_exit_code(self) -> None:
        script = Path(main.__code__.co_filename)
        with patch.object(sys, "argv", [str(script), "route"]), pytest.raises(SystemExit) as stop:
            runpy.run_path(str(script), run_name="__main__")
        assert stop.value.code == EXIT_CONFIG


def _package(tmp_path: Path, version: object = "1.2.3") -> Path:
    (tmp_path / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    return tmp_path


class TestTagVersion:
    def _run(self, directory: Path, tag: str) -> int:
        return main(["tag-version", "--package-dir", str(directory), "--release-tag", tag])

    def test_a_matching_tag_passes(self, tmp_path: Path) -> None:
        assert self._run(_package(tmp_path), "v1.2.3") == EXIT_OK

    def test_no_tag_has_nothing_to_compare(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, "") == EXIT_OK

    def test_a_mismatch_exits_one(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert self._run(_package(tmp_path), "v9.9.9") == EXIT_REFUSED
        assert "does not match" in capsys.readouterr().err

    def test_a_malformed_tag_exits_two(self, tmp_path: Path) -> None:
        assert self._run(_package(tmp_path), "1.2.3") == EXIT_CONFIG

    @pytest.mark.parametrize("version", [None, "", 5, ["1"]])
    def test_a_package_with_no_usable_version_exits_two(
        self, tmp_path: Path, version: object
    ) -> None:
        assert self._run(_package(tmp_path, version), "v1.2.3") == EXIT_CONFIG

    def test_a_non_object_package_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("[]", encoding="utf-8")
        assert self._run(tmp_path, "v1.2.3") == EXIT_CONFIG

    def test_invalid_json_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{nope", encoding="utf-8")
        assert self._run(tmp_path, "v1.2.3") == EXIT_CONFIG

    def test_a_missing_package_exits_three(self, tmp_path: Path) -> None:
        assert self._run(tmp_path, "v1.2.3") == EXIT_EXTERNAL

    def test_the_version_is_read_from_package_json(self, tmp_path: Path) -> None:
        assert package_version(_package(tmp_path, "0.6.0")) == "0.6.0"
