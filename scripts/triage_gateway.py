"""GitHub gateway implementations for the triage batch executor.

Extracted from ``triage_batch_apply.py`` to keep the executor under the
file-size limit. Contains the production ``CliGitHubGateway`` and the offline
fallback ``OfflineGateway``.

The ``pr_is_merged`` and ``commit_exists`` predicates delegate to
``verify_issue_close`` so there is exactly one implementation of each
decision. A divergence between the CLI spot-check and the batch executor
is how issue 4624 shipped: the CLI had the ancestry check but the
executor's own copy did not.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
from collections.abc import Sequence

from scripts.triage_batch_apply import IssueState
from scripts.validation.verify_issue_close import (
    IssueComment,
    verify_commit_exists,
    verify_pr_merged,
)


class CliGitHubGateway:
    """Production gateway. Talks to issues through the gh CLI.

    Reuses the gh issue surface the github skill scripts use. Reads go through
    ``gh issue view``; mutations through ``gh issue close`` and ``gh issue edit``.
    """

    def __init__(self, owner: str, repo: str, *, timeout: float = 30.0) -> None:
        self._repo = f"{owner}/{repo}"
        self._timeout = timeout

    def get_issue_state(self, issue: int) -> IssueState | None:
        result = self._run(
            ["gh", "issue", "view", str(issue), "--repo", self._repo,
             "--json", "number,state,labels"],
        )
        if result is None or result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None
        raw_labels = data.get("labels")
        labels_list = raw_labels if isinstance(raw_labels, list) else []
        labels = frozenset(
            str(label.get("name") or "")
            for label in labels_list
            if isinstance(label, dict)
        )
        raw_number = data.get("number")
        number = int(raw_number) if raw_number is not None else issue
        raw_state = data.get("state")
        state = str(raw_state) if raw_state is not None else ""
        return IssueState(number=number, state=state, labels=labels)

    def close_issue(self, issue: int) -> bool:
        result = self._run(
            ["gh", "issue", "close", str(issue), "--repo", self._repo],
        )
        return result is not None and result.returncode == 0

    def add_labels(self, issue: int, labels: Sequence[str]) -> bool:
        command = ["gh", "issue", "edit", str(issue), "--repo", self._repo]
        for label in labels:
            command.extend(["--add-label", label])
        result = self._run(command)
        return result is not None and result.returncode == 0

    def commit_exists(self, sha: str) -> bool:
        """Delegate to verify_issue_close.verify_commit_exists.

        Single implementation for both CLI and batch paths, fixing the
        divergence where the batch executor had its own copy.
        """
        return verify_commit_exists(sha, repo=self._repo, runner=self._subprocess_runner)

    def pr_is_merged(self, pr: int) -> bool:
        """Delegate to verify_issue_close.verify_pr_merged.

        Single implementation for both CLI and batch paths. This is the
        fix for issue 4624: the batch executor now uses the same
        ancestry-checking predicate as the CLI, instead of a duplicate
        that only checked the state field.
        """
        return verify_pr_merged(pr, self._repo, runner=self._subprocess_runner)

    def get_issue_comments(self, issue: int) -> list[IssueComment] | None:
        """Return issue comments, or None on API failure.

        None means the fetch failed (rate-limited, network error). The caller
        must treat None as blocking (issue 4640 principle: a failed lookup
        must never be treated as "no data found").
        """
        # --paginate or the scope check only ever sees the first page. An
        # issue with 101 comments could carry the blocking one at 101 and
        # close anyway, which is the failure this check exists to stop.
        result = self._run(
            ["gh", "api", "--paginate",
             f"repos/{self._repo}/issues/{issue}/comments?per_page=100"],
        )
        if result is None or result.returncode != 0:
            return None
        try:
            raw = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(raw, list):
            return None
        comments: list[IssueComment] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            user = item.get("user") or {}
            created = item.get("created_at", "")
            if not created:
                continue
            try:
                ts = datetime.datetime.fromisoformat(
                    created.replace("Z", "+00:00"),
                )
            except (ValueError, AttributeError):
                continue
            comments.append(IssueComment(
                author=user.get("login", ""),
                author_type=user.get("type", ""),
                created_at=ts,
                url=item.get("html_url", ""),
                body=item.get("body", ""),
            ))
        return comments

    def get_commit_time(self, sha: str) -> datetime.datetime | None:
        """Return a commit's committer timestamp, or None if unavailable.

        A rationale may cite a commit and no pull request. Without this the
        scope gate had no timestamp to compare comments against and was
        skipped entirely, so a commit-only closure never checked for
        unresolved scope. Refs #4625.
        """
        result = self._run(
            ["git", "show", "-s", "--format=%cI", sha],
        )
        if result is None or result.returncode != 0:
            return None
        stamp = result.stdout.strip()
        if not stamp:
            return None
        try:
            return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def get_pr_merge_time(self, pr: int) -> datetime.datetime | None:
        """Return the merge timestamp of a PR, or None if unavailable."""
        result = self._run(
            ["gh", "pr", "view", str(pr), "--repo", self._repo,
             "--json", "mergedAt"],
        )
        if result is None or result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        merged_at = data.get("mergedAt", "")
        if not merged_at:
            return None
        try:
            return datetime.datetime.fromisoformat(
                str(merged_at).replace("Z", "+00:00"),
            )
        except (ValueError, AttributeError):
            return None

    def _subprocess_runner(
        self,
        cmd: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Adapter matching the runner signature verify_issue_close expects.

        verify_pr_merged and verify_commit_exists call
        ``runner(cmd, capture_output=True, ...)``. This adapter delegates to
        ``_run`` for the actual subprocess call, applying the caller's keyword
        arguments (timeout, encoding) on top of the gateway's defaults.
        """
        result = self._run(cmd)
        if result is None:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="timeout")
        return result

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                command,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env=dict(os.environ, LC_ALL="C"),
                check=False,
                timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None


class OfflineGateway:
    """Fallback gateway when no repository is configured.

    Returns None for state so close/relabel actions plan against an unknown
    issue; refuses every mutation. ``main`` never selects this when mutation
    is authorized because that path requires owner and repo.
    """

    def get_issue_state(self, issue: int) -> IssueState | None:
        return None

    def close_issue(self, issue: int) -> bool:  # pragma: no cover
        raise RuntimeError("offline gateway must not mutate")

    def add_labels(self, issue: int, labels: Sequence[str]) -> bool:  # pragma: no cover
        raise RuntimeError("offline gateway must not mutate")

    def commit_exists(self, sha: str) -> bool:  # pragma: no cover
        return False

    def pr_is_merged(self, pr: int) -> bool:  # pragma: no cover
        return False

    def get_issue_comments(self, issue: int) -> list[IssueComment] | None:  # pragma: no cover
        return None

    def get_commit_time(self, sha: str) -> datetime.datetime | None:  # pragma: no cover
        return None

    def get_pr_merge_time(self, pr: int) -> datetime.datetime | None:  # pragma: no cover
        return None
