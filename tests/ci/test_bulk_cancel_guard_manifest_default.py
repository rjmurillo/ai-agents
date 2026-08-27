"""Tests for the --confirm-without---manifest default recovery path.

Issue #4835 acceptance criteria: "Emit a recovery manifest that can
regenerate each cancelled context" is a hard requirement, not an opt-in.
Before this fix, ``--confirm`` without ``--manifest`` cancelled every run
and wrote a manifest nowhere: ``main`` only wrote one when ``args.manifest``
was explicitly given. Split into its own file (rather than growing
``test_bulk_cancel_guard.py`` past the file-size taste-lint ceiling) per
``.claude/rules/ci-scripts.md`` MUST-4, which forbids raising the count
ratchet baseline to clear a self-inflicted regression.

Shared fixtures and helpers (``workflows``, ``write_runs``, ``argv``) are
imported from ``test_bulk_cancel_guard`` rather than duplicated; this
cross-module fixture import is the same pattern already used elsewhere in
``tests/ci`` (for example ``test_merge_tree_ratchet_check`` imported into
three sibling test files).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from scripts import bulk_cancel_guard
from scripts.bulk_cancel_guard import EXIT_OK, main
from tests.ci.bulk_cancel_fixtures import incident_runs
from tests.ci.test_bulk_cancel_guard import FakeClient, argv, workflows, write_runs

# `workflows` is a fixture imported for pytest's injection-by-name lookup;
# it is never referenced as an expression, only as a test parameter name.
__all__ = ["workflows"]


@pytest.fixture
def default_manifest_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Redirect the production default manifest path into tmp_path.

    ``scripts/bulk_cancel_guard.py:_DEFAULT_MANIFEST_PATH`` resolves under
    this repo's own ``.agents/scratch/`` so a real ``--confirm`` run always
    leaves a manifest. Left unpatched, a test that exercises ``--confirm``
    without ``--manifest`` would write into the actual working tree
    (testing.md MUST 4). Nested under a subdirectory so tests also exercise
    ``write_manifest``'s ``mkdir(parents=True)``.
    """
    path = tmp_path / "default-manifests" / "bulk-cancel-recovery.json"
    monkeypatch.setattr(bulk_cancel_guard, "_DEFAULT_MANIFEST_PATH", path)
    return path


class TestResolveManifestPath:
    """Unit coverage for the pure decision function, no I/O."""

    def test_explicit_manifest_always_wins(self):
        args = argparse.Namespace(manifest=Path("explicit.json"), confirm=True)

        assert bulk_cancel_guard.resolve_manifest_path(args) == Path("explicit.json")

    def test_explicit_manifest_wins_even_without_confirm(self):
        args = argparse.Namespace(manifest=Path("explicit.json"), confirm=False)

        assert bulk_cancel_guard.resolve_manifest_path(args) == Path("explicit.json")

    def test_confirm_without_manifest_falls_back_to_the_default(
        self, default_manifest_path: Path
    ):
        args = argparse.Namespace(manifest=None, confirm=True)

        assert bulk_cancel_guard.resolve_manifest_path(args) == default_manifest_path

    def test_dry_run_without_manifest_resolves_to_nothing(self):
        args = argparse.Namespace(manifest=None, confirm=False)

        assert bulk_cancel_guard.resolve_manifest_path(args) is None


class TestConfirmEmitsADefaultManifest:
    """CLI-level coverage: (a) new durable-manifest guarantee, (b) prior
    explicit-manifest behavior unchanged, (c) negative control proving the
    old code would fail case (a).

    Negative control (c) is not a permanent test: it is verified by reverting
    ``resolve_manifest_path`` to ``return args.manifest`` (the pre-fix body)
    and confirming only the tests below fail while the rest of the suite
    stays green. See the PR description for the recorded run.
    """

    def test_confirm_without_manifest_still_emits_a_default_recovery_manifest(
        self, tmp_path: Path, workflows: Path, default_manifest_path: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))
        client = FakeClient()

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened", "--confirm"),
            client=client,
        )

        assert code == EXIT_OK
        assert default_manifest_path.exists()
        payload = json.loads(default_manifest_path.read_text(encoding="utf-8"))
        assert payload["safe"] is True
        assert len(payload["entries"]) == 3
        assert len(client.posts) == 3

    def test_confirm_with_explicit_manifest_is_unchanged_and_skips_the_default(
        self, tmp_path: Path, workflows: Path, default_manifest_path: Path
    ):
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))
        explicit_path = tmp_path / "explicit-recovery.json"

        code = main(
            argv(
                runs_file,
                workflows,
                "--recovery-event",
                "reopened",
                "--manifest",
                str(explicit_path),
                "--confirm",
            ),
            client=FakeClient(),
        )

        assert code == EXIT_OK
        assert explicit_path.exists()
        assert not default_manifest_path.exists()

    def test_dry_run_without_manifest_writes_no_default(
        self, tmp_path: Path, workflows: Path, default_manifest_path: Path
    ):
        """A dry run (no --confirm) mutates nothing, so it must not gain a
        default manifest either. Only --confirm triggers the fallback."""
        runs_file = write_runs(tmp_path / "runs.json", incident_runs(pr_count=1))

        code = main(
            argv(runs_file, workflows, "--recovery-event", "reopened"), client=FakeClient()
        )

        assert code == EXIT_OK
        assert not default_manifest_path.exists()
