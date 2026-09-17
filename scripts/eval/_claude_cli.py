"""Claude Code CLI transport: the claude/subscription cell of the matrix.

Sibling of `_copilot_cli`, same job, different binary. `_providers`
`resolve_provider("claude-cli")` is the supported entry point; import the
class directly only from tests.

What this transport is for, and what it is not: it answers "does this change
help the Claude models I already pay a seat for", by driving the binary the
operator's own sessions run in. It is not the claude/api cell. That cell is
the urllib path in `_anthropic_api` and stays where it is, because every
checked-in baseline was measured there and moving it would move them.

## Billing is the whole point, so it is enforced, not assumed

Claude Code's documented credential precedence puts the metered credentials
above the subscription one: cloud-provider variables, then
`ANTHROPIC_AUTH_TOKEN`, then `ANTHROPIC_API_KEY`, then `apiKeyHelper`, and
only then `CLAUDE_CODE_OAUTH_TOKEN` and an interactive login
(https://code.claude.com/docs/en/iam, read 2026-09-16). The same page is
explicit about the non-interactive case: in `--print` mode the API key is
always used when present. An operator with a key exported would therefore get
an API-billed run out of the subscription column, and nothing in the report
would say so.

So `_BLOCKED_BILLING_ENV` is removed from the child environment and
`--setting-sources ""` drops the settings files an `apiKeyHelper` could come
from. What is left for the CLI to authenticate with is
`CLAUDE_CODE_OAUTH_TOKEN`, which is what the matrix says this cell costs.

## Isolation

`CLAUDE_CONFIG_DIR` relocates every `~/.claude` path, credentials included
(https://code.claude.com/docs/en/claude-directory, read 2026-09-16). Pointing
it at a fresh directory is what keeps user-level CLAUDE.md, settings, and
plugins out of a cell whose subject is usually those very files, and it is
also why this transport needs the token in the environment: a relocated
config directory has no stored login in it. That is a deliberate trade, the
same one `eval_runtime_parity.py` already makes, and the refusal names the
command that produces a token.

Working directory is a fresh empty temporary directory, so the repository's
own `CLAUDE.md` and `AGENTS.md` cannot leak into the cell. Tools and MCP are
off. What no flag removes is the CLI's own system prompt, which is constant
within a run: the same control argument ADR-058 makes, and the same reason
not to compare a `claude-cli` score against an HTTP provider's.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from _cli_transport import (
    BASE_ENV_ALLOWLIST,
    build_envelope,
    minimal_process_env,
    run_cli,
    validate_timeout,
)

__all__ = ["_ClaudeCLIProvider"]

PROVIDER_LABEL = "Claude CLI"

#: The subscription credential this cell runs on.
OAUTH_TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"

#: Credentials that would silently move the run onto metered billing. Removed
#: from the child environment; see the module docstring for the precedence
#: that makes each of them outrank the subscription token.
_BLOCKED_BILLING_ENV = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_FOUNDRY",
        "CLAUDE_CODE_USE_VERTEX",
    }
)

_ENV_ALLOWLIST = BASE_ENV_ALLOWLIST | {OAUTH_TOKEN_ENV}

#: Every built-in that can touch the filesystem, the network, a shell, or
#: another agent. A text eval needs none of them, and each one that stays
#: enabled is tool schema occupying the context the eval is measuring.
_DISALLOWED_TOOLS = (
    "Agent Bash BashOutput Edit Glob Grep KillShell NotebookEdit Read "
    "SlashCommand Task TodoWrite WebFetch WebSearch Write mcp__*"
)

#: An empty MCP configuration plus --strict-mcp-config means no server is
#: started, whatever the operator has configured elsewhere.
_EMPTY_MCP_CONFIG = json.dumps({"mcpServers": {}}, separators=(",", ":"))


class _ClaudeCLIProvider:
    """Claude Code CLI driven as a one-shot `--print` subprocess."""

    name = "claude-cli"

    def __init__(self, *, executable: str = "claude", timeout: float = 900.0) -> None:
        self._executable = executable
        self._timeout = validate_timeout(timeout)
        self._provider_label = PROVIDER_LABEL
        self.system_fingerprint: str | None = None

    def _build_argv(self, model: str) -> list[str]:
        """Build the fixed, shell-free Claude Code CLI invocation."""
        return [
            self._executable,
            "--print",
            "--output-format",
            "json",
            "--model",
            model,
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            _EMPTY_MCP_CONFIG,
            "--disallowed-tools",
            _DISALLOWED_TOOLS,
            "--disable-slash-commands",
            "--no-session-persistence",
        ]

    def _build_env(self, config_dir: Path) -> dict[str, str]:
        # `_cli_transport` is a flat sibling module, so mypy resolves it to Any
        # under `ignore_missing_imports`. Pin the contract at this boundary
        # rather than letting Any leak into the subprocess call.
        env: dict[str, str] = minimal_process_env(
            allow=_ENV_ALLOWLIST,
            blocked=_BLOCKED_BILLING_ENV,
            overrides={"CLAUDE_CONFIG_DIR": str(config_dir)},
        )
        return env

    @staticmethod
    def _require_subscription_credential(env: dict[str, str]) -> None:
        """Refuse a run that has no subscription credential to spend.

        Without this the CLI would fail somewhere inside its own auth flow and
        report a generic non-zero exit, which reads as a provider outage and
        gets retried. The cell's contract is one specific variable, so say so.
        """
        if env.get(OAUTH_TOKEN_ENV):
            return
        raise RuntimeError(
            f"{PROVIDER_LABEL} needs {OAUTH_TOKEN_ENV} to bill this run to a "
            "Claude subscription. This transport relocates CLAUDE_CONFIG_DIR "
            "to an isolated profile so user-level memory and settings stay "
            "out of the measurement, and a relocated profile carries no "
            "stored login. Run `claude setup-token` and export the result, "
            "or select the claude-api cell to run on ANTHROPIC_API_KEY "
            "instead."
        )

    def _read_answer(self, stdout: str, model: str) -> tuple[str, str | None]:
        """Return answer text and the model the CLI reported answering with.

        `--output-format json` is used rather than `text` precisely so this
        can be read: the `modelUsage` keys are the CLI's own record of which
        model served the turn, so a run cannot score an unrequested model
        without the mismatch surfacing here.
        """
        try:
            payload = json.loads(stdout)
        except (TypeError, ValueError):
            raise RuntimeError(
                f"{PROVIDER_LABEL} returned output that is not the JSON "
                "envelope --output-format json promises; response redacted"
            ) from None
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"{PROVIDER_LABEL} returned a JSON value that is not an "
                "object; response redacted"
            )
        if payload.get("is_error"):
            raise RuntimeError(
                f"{PROVIDER_LABEL} reported an error result: "
                f"error={payload.get('subtype') or 'unknown'}; "
                "response redacted"
            )
        answer = payload.get("result")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError(
                f"{PROVIDER_LABEL} API returned no choices; "
                "model identifier redacted"
            )
        model_used = self._confirm_model(payload, model)
        return answer, model_used

    def _confirm_model(self, payload: dict[str, Any], model: str) -> str | None:
        """Return the served model id, or raise when it is not the one asked for.

        None means the envelope carried no usage record to check against. That
        is reported rather than treated as agreement, the same way the Copilot
        transport reports an unreadable transcript.

        `modelUsage` can carry more than one key for a single turn. Measured
        2026-09-16 against CLI 2.1.273: `--model claude-haiku-4-5-20251001`
        produced one key, and `--model claude-haiku-4-5` produced two, the
        alias and the dated id it resolved to. So the check is that *every*
        key belongs to the requested family, not that there is exactly one.
        Requiring one would have failed every run made with an alias, and
        ignoring the extras would have let a second, unrequested model bill a
        turn without the report saying so.
        """
        usage = payload.get("modelUsage")
        if not isinstance(usage, dict) or not usage:
            return None
        served = sorted((str(key) for key in usage), key=len, reverse=True)
        if not all(self._model_matches(key, model) for key in served):
            raise RuntimeError(
                f"{PROVIDER_LABEL} model attribution mismatch; "
                "model identifiers redacted"
            )
        # The longest id is the most specific one the CLI resolved, which is
        # what an archived run should record rather than the alias typed in.
        return served[0]

    @staticmethod
    def _model_matches(served: str, requested: str) -> bool:
        """Accept a served id that resolves the requested one.

        `--model` takes an alias or a partial id and the CLI answers with the
        dated id it resolved to, so an equality check would reject every
        legitimate run made with an alias. Prefix matching in either direction
        is the narrowest rule that accepts `claude-haiku-4-5` against
        `claude-haiku-4-5-20251001` and still rejects a different family.
        """
        return served.startswith(requested) or requested.startswith(served)

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        system: str = "",
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        seed: int | None = None,
    ) -> str:
        # The CLI exposes no sampling controls, so these are discarded rather
        # than silently ignored further down. A fixture that needs sampling
        # determinism belongs on an HTTP provider.
        del max_tokens, temperature, seed

        prompt = build_envelope(PROVIDER_LABEL, messages, system)
        self.system_fingerprint = None
        with tempfile.TemporaryDirectory(prefix="eval-claude-cli-") as profile:
            env = self._build_env(Path(profile))
            self._require_subscription_credential(env)
            completed = run_cli(
                self._build_argv(model),
                prompt,
                provider_label=PROVIDER_LABEL,
                env=env,
                timeout=self._timeout,
            )
        answer, model_used = self._read_answer(completed.stdout, model)
        # None records that nobody confirmed, which is how an archived run
        # tells a confirmed answer apart from an unconfirmed one.
        self.system_fingerprint = model_used
        return answer
