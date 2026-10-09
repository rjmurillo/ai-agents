"""The merge step feeds the save, and the cache actions stay pinned."""

from __future__ import annotations

import re

from scripts.ci import run_pytest_partition as runner
from tests.ci.pytest_split_workflow_helpers import (
    WORKFLOW,
    durations_saves,
    merge_step,
    steps_using,
    workflow_jobs,
)

_CACHE_USES = re.compile(r"^\s*(?:- )?uses:\s*actions/cache/(?:restore|save)@(\S+)\s*(#.*)?$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


def _merge_command() -> str:
    return " ".join(str(merge_step()["run"]).split())


class TestMergeFeedsTheSave:
    def test_the_merge_reads_every_leg_file_the_runner_writes(self) -> None:
        for name in runner.split_names():
            assert runner._leg_durations_path(name) in _merge_command()

    def test_the_save_path_is_the_merge_output(self) -> None:
        ((_, save),) = durations_saves()
        assert f"--output {save['with']['path']}" in _merge_command()

    def test_each_leg_file_is_uploaded_with_its_artifacts(self) -> None:
        uploads = [
            s
            for s in steps_using("test", "actions/upload-artifact")
            if str(s["with"]["name"]).startswith("pytest-results-")
        ]
        assert [s["with"]["path"] for s in uploads] == [f"{runner.LEG_DURATIONS_DIR}/"]

    def test_the_merge_job_downloads_the_leg_artifacts(self) -> None:
        downloads = steps_using("test-durations", "actions/download-artifact")
        assert [d["with"]["pattern"] for d in downloads] == ["pytest-results-*"]


class TestCacheActionsArePinned:
    def test_every_cache_action_pins_one_sha_with_a_version_comment(self) -> None:
        found = [
            m
            for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
            if (m := _CACHE_USES.match(line))
        ]
        assert len(found) >= 3
        assert {m.group(1) for m in found} == {found[0].group(1)}
        assert _SHA.match(found[0].group(1))
        assert all(m.group(2) and m.group(2).startswith("# v") for m in found)

    def test_the_workflow_still_defines_the_merge_job(self) -> None:
        assert "test-durations" in workflow_jobs()
