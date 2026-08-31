"""Live-enumeration CLI paths for the bulk cancellation guard (issue #4835).

Three Copilot review findings on PR #5357 land here, all of them about the two
paths that read from GitHub rather than from a captured file:

- ``TestLiveEnumeration`` and ``TestForkIdentityAtTheCli``: the Actions
  ``branch`` filter matches a head branch name, which is not unique across
  forks, so a run belonging to a different fork's pull request could be
  attributed to the one the operator named and cancelled.
- ``TestPerPullRequestProvenance``: verifying subscriptions against one local
  workflow corpus answers for one ref. GitHub evaluates the pull request's own
  merge ref, so a pull request whose workflow omits ``reopened`` verified
  against a healthy checkout.
- ``TestPinnedContract`` and ``TestAuthenticationExit``: a non-pinned target
  planned against the wrong required-context set, and an unauthenticated ``gh``
  exited 3 rather than the reserved 4.

Split out of ``tests/ci/test_bulk_cancel_guard.py`` to keep both files under the
500-line taste ceiling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.bulk_cancel_guard import (
    EXIT_AUTH,
    EXIT_BLOCKED,
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_OK,
    main,
)
from scripts.github_core.workflow_provenance import merge_ref
from tests.ci.bulk_cancel_fixtures import OPTIONAL_CONTEXT, OPTIONAL_WORKFLOW
from tests.ci.workflow_runs_fixtures import (
    FakeClient,
    contents_endpoint,
    contents_payload,
    page_url,
    run_payload,
    runs_url,
)


class TestLiveEnumeration:
    REPOSITORY = "rjmurillo/ai-agents"
    FORK = "forker/ai-agents"
    WORKFLOW_PATH = ".github/workflows/label-pr.yml"

    def _pull_payload(self, number: int = 7, head_repository: str | None = None) -> dict:
        head: dict = {"ref": "feat/a"}
        resolved = head_repository if head_repository is not None else self.REPOSITORY
        head["repo"] = {"full_name": resolved}
        return {"number": number, "head": head}

    def _head_definition(self, pr_types: list[str] | None = None) -> dict:
        """The workflow file as the pull request's own merge ref carries it."""
        types = pr_types or ["opened", "synchronize", "reopened"]
        return contents_payload(
            {
                "name": OPTIONAL_WORKFLOW,
                "on": {"pull_request": {"types": types}},
                "jobs": {},
            }
        )

    def _pulls_client(self) -> FakeClient:
        pulls = f"repos/{self.REPOSITORY}/pulls?state=open&base=main"
        queued = runs_url(self.REPOSITORY, "feat/a", "queued")
        in_progress = runs_url(self.REPOSITORY, "feat/a", "in_progress")
        jobs = f"repos/{self.REPOSITORY}/actions/runs/11/jobs"
        return FakeClient(
            {
                page_url(pulls, 1): [self._pull_payload()],
                page_url(queued, 1): {
                    "workflow_runs": [
                        run_payload(
                            11,
                            name=OPTIONAL_WORKFLOW,
                            head_repository=self.REPOSITORY,
                            path=self.WORKFLOW_PATH,
                        )
                    ]
                },
                page_url(in_progress, 1): {"workflow_runs": []},
                page_url(jobs, 1): {"jobs": [{"name": OPTIONAL_CONTEXT}]},
                contents_endpoint(
                    self.REPOSITORY, self.WORKFLOW_PATH, merge_ref(7)
                ): self._head_definition(),
            }
        )

    def test_all_open_prs_enumerates_through_pagination(
        self, workflows: Path, capsys
    ):
        client = self._pulls_client()

        code = main(
            ["--all-open-prs", "--workflows-dir", str(workflows)], client=client
        )

        assert code == EXIT_OK
        assert "pull requests       : 1" in capsys.readouterr().out

    def test_explicit_pr_numbers_resolve_their_head_branch(self, workflows: Path):
        client = self._pulls_client()
        client.responses[f"repos/{self.REPOSITORY}/pulls/7"] = self._pull_payload()

        code = main(
            ["--pr", "7", "--workflows-dir", str(workflows)], client=client
        )

        assert code == EXIT_OK

    def test_a_fork_run_sharing_the_branch_name_is_not_cancelled_for_this_pr(
        self, tmp_path: Path, workflows: Path
    ):
        """Copilot review on PR #5357: the Actions ``branch`` filter matches a
        head branch name, which is not unique across forks. Run 12 below belongs
        to a different fork's pull request on the same branch name. Before the
        head-repository check it was attributed to PR 7 and cancelled.
        """
        client = self._pulls_client()
        client.responses[f"repos/{self.REPOSITORY}/pulls/7"] = self._pull_payload()
        queued = page_url(runs_url(self.REPOSITORY, "feat/a", "queued"), 1)
        client.responses[queued]["workflow_runs"].append(
            run_payload(
                12,
                name=OPTIONAL_WORKFLOW,
                head_repository=self.FORK,
                path=self.WORKFLOW_PATH,
            )
        )
        client.responses[page_url(f"repos/{self.REPOSITORY}/actions/runs/12/jobs", 1)] = {
            "jobs": [{"name": OPTIONAL_CONTEXT}]
        }

        code = main(
            [
                "--pr",
                "7",
                "--workflows-dir",
                str(workflows),
                "--manifest",
                str(tmp_path / "m.json"),
                "--confirm",
            ],
            client=client,
        )

        assert code == EXIT_OK
        assert client.posts == [f"repos/{self.REPOSITORY}/actions/runs/11/cancel"]

    def test_a_pr_with_no_head_branch_exits_config(self, workflows: Path, capsys):
        client = FakeClient(
            {f"repos/{self.REPOSITORY}/pulls/7": {"number": 7, "head": None}}
        )

        code = main(["--pr", "7", "--workflows-dir", str(workflows)], client=client)

        assert code == EXIT_CONFIG
        assert "no head branch" in capsys.readouterr().err

    def test_a_pr_with_no_head_repository_exits_config(
        self, workflows: Path, capsys
    ):
        """Fail closed rather than assume the base repository. Without the head
        repository there is no way to tell this pull request's runs from
        another fork's runs on the same branch name.
        """
        client = FakeClient(
            {
                f"repos/{self.REPOSITORY}/pulls/7": {
                    "number": 7,
                    "head": {"ref": "feat/a"},
                }
            }
        )

        code = main(["--pr", "7", "--workflows-dir", str(workflows)], client=client)

        assert code == EXIT_CONFIG
        assert "no head repository" in capsys.readouterr().err

    def test_a_failing_api_read_exits_external(self, workflows: Path, capsys):
        class ExplodingClient(FakeClient):
            def rest_get(self, endpoint: str):
                raise RuntimeError("gh api failed: 502")

        code = main(
            ["--all-open-prs", "--workflows-dir", str(workflows)],
            client=ExplodingClient(),
        )

        assert code == EXIT_EXTERNAL
        assert "GitHub API read failed" in capsys.readouterr().err


class TestPerPullRequestProvenance:
    """Subscriptions are verified against the PR's own workflow definition.

    The local ``--workflows-dir`` corpus describes one ref: whichever commit
    that checkout sits on. For a pull_request-family event GitHub evaluates the
    pull request's merge ref instead, so each open pull request can carry its
    own version of the same file. A pull request that drops ``reopened`` from
    its ``types:`` list therefore verified against a healthy local definition,
    passed, and was cancelled with no working recovery route.
    """

    REPOSITORY = "rjmurillo/ai-agents"
    WORKFLOW = "PR Validation"
    CONTEXT = "Validate PR"
    WORKFLOW_PATH = ".github/workflows/pr-validation.yml"

    def _definition(self, types: list[str]) -> dict:
        return {
            "name": self.WORKFLOW,
            "on": {"pull_request": {"types": types}},
            "jobs": {"validate": {"name": self.CONTEXT}},
        }

    def _client(self, head_types: list[str]) -> FakeClient:
        queued = runs_url(self.REPOSITORY, "feat/a", "queued")
        in_progress = runs_url(self.REPOSITORY, "feat/a", "in_progress")
        return FakeClient(
            {
                f"repos/{self.REPOSITORY}/pulls/7": {
                    "number": 7,
                    "head": {
                        "ref": "feat/a",
                        "repo": {"full_name": self.REPOSITORY},
                    },
                },
                page_url(queued, 1): {
                    "workflow_runs": [
                        run_payload(
                            11,
                            name=self.WORKFLOW,
                            head_repository=self.REPOSITORY,
                            path=self.WORKFLOW_PATH,
                        )
                    ]
                },
                page_url(in_progress, 1): {"workflow_runs": []},
                page_url(f"repos/{self.REPOSITORY}/actions/runs/11/jobs", 1): {
                    "jobs": [{"name": self.CONTEXT}]
                },
                contents_endpoint(
                    self.REPOSITORY, self.WORKFLOW_PATH, merge_ref(7)
                ): contents_payload(self._definition(head_types)),
            }
        )

    def _run(self, client: FakeClient, workflows: Path) -> int:
        return main(
            [
                "--pr",
                "7",
                "--workflows-dir",
                str(workflows),
                "--recovery-event",
                "reopened",
            ],
            client=client,
        )

    def test_a_pr_whose_own_workflow_omits_reopened_is_blocked(
        self, workflows: Path, capsys
    ):
        """The ``workflows`` fixture corpus declares ``reopened`` for every
        workflow, so this run verifies against the local checkout and blocks
        only when the pull request's own definition is read.
        """
        code = self._run(self._client(["opened", "synchronize"]), workflows)

        assert code == EXIT_BLOCKED
        assert "does not subscribe to 'reopened'" in capsys.readouterr().out

    def test_control_the_same_pr_declaring_reopened_verifies(self, workflows: Path):
        """Without this, a fix that blocked every live run would pass the case
        above while making the tool useless.
        """
        code = self._run(
            self._client(["opened", "synchronize", "reopened"]), workflows
        )

        assert code == EXIT_OK

    def test_an_unreadable_head_definition_blocks_rather_than_falling_back(
        self, workflows: Path, capsys
    ):
        """Fail closed. An unfetchable head definition must not silently fall
        back to the local corpus, which would clear the run.
        """
        client = self._client(["opened", "synchronize", "reopened"])
        del client.responses[
            contents_endpoint(self.REPOSITORY, self.WORKFLOW_PATH, merge_ref(7))
        ]

        code = self._run(client, workflows)

        assert code == EXIT_BLOCKED
        assert "no workflow definition found" in capsys.readouterr().out

    def test_a_run_with_no_workflow_path_blocks(self, workflows: Path):
        """Without the file name there is nothing to fetch, and the workflow
        ``name:`` cannot stand in for it because two files may declare one name.
        """
        client = self._client(["opened", "synchronize", "reopened"])
        queued = page_url(runs_url(self.REPOSITORY, "feat/a", "queued"), 1)
        client.responses[queued] = {
            "workflow_runs": [
                run_payload(
                    11, name=self.WORKFLOW, head_repository=self.REPOSITORY
                )
            ]
        }

        assert self._run(client, workflows) == EXIT_BLOCKED

    def test_the_head_definition_is_fetched_at_the_merge_ref(self, workflows: Path):
        """Pins the ref, not just the outcome. Reading any other ref would
        produce the same exit code on the control case above.
        """
        client = self._client(["opened", "synchronize", "reopened"])

        self._run(client, workflows)

        assert (
            contents_endpoint(self.REPOSITORY, self.WORKFLOW_PATH, merge_ref(7))
            in client.gets
        )


class TestPinnedContract:
    """A target the pinned contract does not describe is refused.

    ``REQUIRED_CONTEXTS`` is the ruleset contract for ``rjmurillo/ai-agents``
    ``main``. Pointed elsewhere, a context the real target requires and this
    contract does not is classified as optional, and an optional run is
    cancelled with no recovery event at all.
    """

    def test_another_repository_exits_config(self, workflows: Path, capsys):
        code = main(
            [
                "--pr",
                "7",
                "--repository",
                "someone/else",
                "--workflows-dir",
                str(workflows),
            ],
            client=FakeClient(),
        )

        assert code == EXIT_CONFIG
        assert "pinned to rjmurillo/ai-agents main" in capsys.readouterr().err

    def test_another_branch_exits_config(self, workflows: Path, capsys):
        code = main(
            ["--pr", "7", "--branch", "develop", "--workflows-dir", str(workflows)],
            client=FakeClient(),
        )

        assert code == EXIT_CONFIG
        assert "pinned to rjmurillo/ai-agents main" in capsys.readouterr().err

    def test_control_the_pinned_target_is_accepted(self, workflows: Path):
        """Naming the pinned values explicitly must still work, or the check is
        refusing on the presence of the flag rather than on its value.
        """
        client = FakeClient(
            {
                page_url(
                    "repos/rjmurillo/ai-agents/pulls?state=open&base=main", 1
                ): []
            }
        )

        code = main(
            [
                "--all-open-prs",
                "--repository",
                "rjmurillo/ai-agents",
                "--branch",
                "main",
                "--workflows-dir",
                str(workflows),
            ],
            client=client,
        )

        assert code == EXIT_OK


class TestAuthenticationExit:
    """Exit 4 is reserved for authentication failures (AGENTS.md,
    ``.claude/rules/ci-scripts.md`` MUST 4). Folding an unauthenticated ``gh``
    into the generic external code left the operator unable to tell missing
    credentials from a GitHub outage.
    """

    class Unauthenticated(FakeClient):
        def is_authenticated(self) -> bool:
            return False

    class ProbeExplodes(FakeClient):
        def is_authenticated(self) -> bool:
            raise RuntimeError("gh auth status: connection reset")

    @pytest.mark.parametrize("source", [["--all-open-prs"], ["--pr", "7"]])
    def test_a_live_read_without_credentials_exits_auth(
        self, workflows: Path, capsys, source: list[str]
    ):
        code = main(
            [*source, "--workflows-dir", str(workflows)],
            client=self.Unauthenticated(),
        )

        assert code == EXIT_AUTH
        assert "gh is not authenticated" in capsys.readouterr().err

    def test_a_confirmed_write_from_a_runs_file_still_needs_credentials(
        self, tmp_path: Path, workflows: Path
    ):
        runs_file = tmp_path / "runs.json"
        runs_file.write_text("[]", encoding="utf-8")

        code = main(
            [
                "--runs-file",
                str(runs_file),
                "--workflows-dir",
                str(workflows),
                "--confirm",
                "--manifest",
                str(tmp_path / "m.json"),
            ],
            client=self.Unauthenticated(),
        )

        assert code == EXIT_AUTH

    def test_control_an_offline_dry_run_needs_no_credentials(
        self, tmp_path: Path, workflows: Path
    ):
        """A ``--runs-file`` dry run touches nothing, so it must stay usable on
        a machine with no ``gh`` login. Without this control, gating every
        invocation on auth would pass both cases above.
        """
        runs_file = tmp_path / "runs.json"
        runs_file.write_text("[]", encoding="utf-8")

        code = main(
            ["--runs-file", str(runs_file), "--workflows-dir", str(workflows)],
            client=self.Unauthenticated(),
        )

        assert code == EXIT_OK

    def test_a_failing_auth_probe_is_treated_as_unauthenticated(
        self, workflows: Path
    ):
        code = main(
            ["--all-open-prs", "--workflows-dir", str(workflows)],
            client=self.ProbeExplodes(),
        )

        assert code == EXIT_AUTH

    def test_an_authenticated_client_reaches_the_api_error_path(
        self, workflows: Path
    ):
        """Control proving the auth gate is not swallowing transport failures:
        an authenticated client whose read fails still exits 3, not 4.
        """

        class Exploding(FakeClient):
            def rest_get(self, endpoint: str):
                raise RuntimeError("gh api failed: 502")

        code = main(
            ["--all-open-prs", "--workflows-dir", str(workflows)],
            client=Exploding(),
        )

        assert code == EXIT_EXTERNAL
