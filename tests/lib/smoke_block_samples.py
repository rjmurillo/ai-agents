"""Sample CLI block outputs for the smoke skip-or-fail policy tests.

Real Copilot output shapes: a 402 quota block as prose and as a JSON event, plus
the auth, rate-limit, and transport blocks that must never carry the quota
marker.
"""

from __future__ import annotations

import subprocess

QUOTA_STDERR = (
    "\nYou have exceeded your monthly quota (Request ID: C612:60CD4:E4E4F:1063A0:6AA0928A)\n"
    "\n\nChanges    +0 -0\n"
    "AI Credits 0 (3s)\n"
    "Resume     copilot --resume=e3d31814-eee1-4944-9d77-c27710b7b0b7\n"
)
# The agent path emits JSON events instead of prose.
QUOTA_AGENT_STDOUT = (
    '{"type":"error","data":{"statusCode":402,'
    '"providerCallId":"A52E:26C4B7:FF31F:12203A:6AA092B1",'
    '"errorCode":"quota_exceeded"},"id":"1726daed"}\n'
    '{"type":"result","exitCode":1}\n'
)
NON_QUOTA_STDERR = {
    "auth_absent": "No authentication information found.\nSet COPILOT_GITHUB_TOKEN",
    "auth_rejected": "GitHub returned: Bad credentials",
    "rate_limit": "API rate limit exceeded for user ID 12345.",
    "transport": "Failed to fetch PAT user login: connection reset by peer.",
}


def completed(
    *, stdout: str | None = "", stderr: str | None = "", returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["copilot"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def claude_run(stdout: str, returncode: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["claude"], returncode, stdout=stdout, stderr="")
