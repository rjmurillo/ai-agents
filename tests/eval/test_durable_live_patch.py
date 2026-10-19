"""Tests for the live driver's saved patch and reviewer prompt (issue #5768).

The corpus stores `initial/` as `<path>.fixture` files, so the patch must be taken
against a materialized copy. A fake process runner stands in for `claude`.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.eval._durable_live_test_support import (
    BASE,
    CLEAN_REVIEW,
    GOOD_TASK,
    fake_runner,
    grader_mod,
    live_mod,
    load,
    record_mod,
    reviewer_settings,
    stream_text,
)


class TestRunPatch:
    """The saved patch must diff against the real `initial/` files, not the `.fixture` names."""

    def _run(self, tmp_path: Path) -> Any:
        scenario = load(GOOD_TASK)
        inner = fake_runner(scenario, ["known_good"])

        def deleting(argv: list[str], **kwargs: Any) -> Any:
            done = inner(argv, **kwargs)
            (Path(kwargs["cwd"]) / "slugger" / "__init__.py").unlink()
            return done

        control_file = tmp_path / "control.md"
        control_file.write_text("rules", encoding="utf-8")
        settings = live_mod.RunSettings("haiku", "low", retry_budget=0)
        return live_mod.run_task(
            scenario,
            "current",
            control_file,
            BASE,
            settings,
            live_mod.InvocationBudget(10),
            runner=deleting,
        )

    def test_a_modified_file_shows_its_removed_lines_against_the_original(
        self, tmp_path: Path
    ) -> None:
        patch = self._run(tmp_path).patch
        core = patch[patch.index("--- a/slugger/core.py") :]
        assert "--- a/slugger/core.py\n+++ b/slugger/core.py\n" in core
        assert '-    raise NotImplementedError("slugify is not implemented yet")' in core
        assert "/dev/null" not in core

    def test_a_deleted_file_diffs_to_dev_null_with_its_lines_removed(self, tmp_path: Path) -> None:
        patch = self._run(tmp_path).patch
        deleted = patch[patch.index("--- a/slugger/__init__.py") :].split("--- a/slugger/core.py")[
            0
        ]
        assert deleted.startswith("--- a/slugger/__init__.py\n+++ /dev/null\n")
        assert "-from slugger.core import slugify" in deleted

    def test_an_added_file_diffs_from_dev_null(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        inner = fake_runner(scenario, ["known_good"])

        def adding(argv: list[str], **kwargs: Any) -> Any:
            done = inner(argv, **kwargs)
            (Path(kwargs["cwd"]) / "slugger" / "extra.py").write_text("x = 1\n", encoding="utf-8")
            return done

        control_file = tmp_path / "control.md"
        control_file.write_text("rules", encoding="utf-8")
        run = live_mod.run_task(
            scenario,
            "current",
            control_file,
            BASE,
            live_mod.RunSettings("haiku", "low", retry_budget=0),
            live_mod.InvocationBudget(10),
            runner=adding,
        )
        assert "--- /dev/null\n+++ b/slugger/extra.py\n" in run.patch
        assert "+x = 1" in run.patch


class TestReviewPrompt:
    def test_the_review_prompt_omits_paths_the_review_copy_dropped(self, tmp_path: Path) -> None:
        scenario = load(GOOD_TASK)
        workdir = tmp_path / "work"
        live_mod.materialize(scenario, workdir)
        secret = tmp_path / "host-secret.txt"
        secret.write_text("HOST-SECRET-CONTENT\n", encoding="utf-8")
        (workdir / "slugger" / "planted.py").symlink_to(secret)
        (workdir / "slugger" / "added.py").write_text("x = 1\n", encoding="utf-8")
        changed = grader_mod.changed_paths(scenario, workdir)
        assert {"slugger/planted.py", "slugger/added.py"} <= set(changed)
        session = SimpleNamespace(grades=[SimpleNamespace(changed_paths=changed)], invocations=[])
        control_file = tmp_path / "control.md"
        control_file.write_text("rules", encoding="utf-8")
        inner = fake_runner(scenario, [None], stdout=lambda _i: stream_text(text=CLEAN_REVIEW))
        seen: list[list[str]] = []

        def runner(argv: list[str], **kwargs: Any) -> Any:
            seen.append(list(argv))
            return inner(argv, **kwargs)

        live_mod._run_review(
            scenario,
            "current",
            session,
            workdir,
            reviewer_settings(),
            live_mod.InvocationBudget(10),
            runner,
        )

        prompt = seen[0][2]
        assert "- slugger/added.py" in prompt
        assert "planted.py" not in prompt


def test_without_links_drops_dotdot_and_absolute_paths_that_leave_the_workdir(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.py").write_text("SECRET\n", encoding="utf-8")
    work = tmp_path / "work"
    (work / "pkg" / "sub").mkdir(parents=True)
    (work / "pkg" / "sub" / "b.py").write_text("ok\n", encoding="utf-8")
    kept = record_mod.without_links(
        work,
        (
            "pkg/sub/b.py",
            "../outside/a.py",
            "pkg/../../outside/a.py",
            str(outside / "a.py"),
            "pkg/../pkg/sub/b.py",
        ),
    )
    assert kept == ("pkg/sub/b.py", "pkg/../pkg/sub/b.py")
