"""GitHub Copilot CLI transport for the eval harness.

Split out of `_providers.py` because that module crossed the 500-line taste
ceiling once this provider landed. The provider shares no helpers with the
HTTP-based providers, so the seam is clean: nothing here imports `_providers`,
which keeps the dependency one-directional and rules out an import cycle.

`_providers.resolve_provider("copilot-cli")` remains the only supported entry
point. Import the class directly only from tests.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from _copilot_cli_constants import (
    FOOTER_COLUMN,
    FOOTER_LABEL_RE,
    FOOTER_PROSE_ENDINGS,
    FOOTER_VALUE_MAX_WORDS,
    PROVIDER_LABEL,
    SESSION_STATE_ENV,
    TRACE_LINE_PREFIXES,
    UNVERIFIED_MODEL_ENV,
)
from _eval_common import require_str_or_none

__all__ = ["_CopilotCLIProvider"]

_ERROR_CLASSIFICATION_CHARS = 4096
_AUTH_ERROR_HINTS = (
    "authentication failed",
    "not logged in",
    "not signed in",
    "login required",
)


def _safe_process_error(returncode: int, stderr: str) -> RuntimeError:
    """Describe a failed CLI process without serializing its output."""
    lowered = stderr[:_ERROR_CLASSIFICATION_CHARS].lower()
    if "rate limit" in lowered:
        error_code = "rate limit"
    elif "timed out" in lowered or "timeout" in lowered:
        error_code = "request timed out"
    elif any(hint in lowered for hint in _AUTH_ERROR_HINTS):
        error_code = "authentication failed"
    else:
        error_code = "provider process failure"
    return RuntimeError(
        f"{PROVIDER_LABEL} exited with code {returncode}: error={error_code}; "
        "process output redacted"
    )


class _CopilotCLIProvider:
    """GitHub Copilot CLI transport, driven as a subprocess.

    Distinct from every other provider here in one way that matters: it needs
    no API key. It reuses the operator's existing Copilot authentication, so an
    eval can run against the models the owner actually works in
    (`claude-opus-5`, `gpt-5.6-sol`) without separate Anthropic or OpenAI
    billing. That is why it is the preferred transport for this repository.

    Three isolation decisions, all load-bearing:

    1. `cwd` is a caller-supplied empty directory, not the repository. The CLI
       loads `AGENTS.md`, `CLAUDE.md`, and `.github/instructions/**` from its
       working directory. In this repo those files are frequently the variable
       under test, so running from the repo root would put the treatment into
       the control cell and silently destroy the comparison.
    2. `--no-custom-instructions` drops ambient user-level instructions from
       `~/.copilot/`. Measured 2026-07-29 against `claude-opus-5` from an empty
       directory: 54.7k input tokens with them, 41.2k without. That is 13,500
       tokens of behavioral instruction riding along in every cell, several
       times the size of the rule bodies these evals compare, and it overlaps
       them semantically. Being constant within a run makes a paired contrast
       valid, not clean; the overlap compresses deltas toward zero. Runs
       archived before this flag was added carry that compression, which biases
       against finding an effect rather than manufacturing one.
    3. Built-in MCP servers are disabled. Their tool definitions occupy the
       same context the eval is measuring, and they add latency for no signal
       on a text-completion eval.

    Authentication is unaffected: the token lives in `~/.copilot/` but is read
    separately from the instruction files, verified by a live call with the
    flag set. What remains un-isolated is the CLI's own system prompt and tool
    schema, roughly 41k tokens, which no flag removes. It is a constant across
    every cell of a single run, the same control argument ADR-058 makes for not
    comparing scores across providers. Do not compare a copilot-cli score to an
    HTTP-provider score.
    """

    _FOOTER_LABEL_RE = FOOTER_LABEL_RE
    _FOOTER_COLUMN: int = FOOTER_COLUMN
    _FOOTER_VALUE_MAX_WORDS: int = FOOTER_VALUE_MAX_WORDS
    _FOOTER_PROSE_ENDINGS: tuple[str, ...] = FOOTER_PROSE_ENDINGS
    _SESSION_STATE_ENV: str = SESSION_STATE_ENV
    _UNVERIFIED_MODEL_ENV: str = UNVERIFIED_MODEL_ENV
    _TRACE_LINE_PREFIXES: tuple[str, ...] = TRACE_LINE_PREFIXES
    _PROVIDER_LABEL: str = PROVIDER_LABEL

    def __init__(self, *, executable: str = "copilot", timeout: float = 900.0) -> None:
        self.name = "copilot-cli"
        self._provider_label = self._PROVIDER_LABEL
        self._executable = executable
        self._timeout = timeout
        self.system_fingerprint: str | None = None

    @classmethod
    def _session_state_root(cls) -> Path:
        override = os.environ.get(cls._SESSION_STATE_ENV)
        if not override:
            return Path.home() / ".copilot" / "session-state"
        root = Path(override)
        if not root.is_absolute():
            # The CLI inherits this variable but runs with cwd set to a
            # per-call sandbox, so it resolves a relative value there while
            # this process resolves it here. The two never agree, so every
            # transcript reads as missing, and that refusal blames the
            # transcript and invites the opt-in that grades raw stdout. Name
            # the real cause instead of failing the same way each call.
            raise RuntimeError(
                f"{cls._PROVIDER_LABEL} needs {cls._SESSION_STATE_ENV} to be "
                f"absolute; got {override!r}, which the CLI resolves against a "
                "per-call sandbox this process cannot read."
            )
        return root

    @staticmethod
    def _read_candidate(path: Path, since: float) -> str | None:
        """Read one current transcript candidate, or skip an unusable file."""
        try:
            if path.stat().st_mtime < since:
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    @staticmethod
    def _parse_event(
        line: str,
    ) -> tuple[str, dict[str, object], dict[str, object]] | None:
        """Return one object-shaped event and data mapping."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        data = event.get("data")
        if not isinstance(data, dict):
            return None
        kind = event.get("type")
        if not isinstance(kind, str):
            return None
        return kind, data, event

    @classmethod
    def _read_assistant_message(
        cls,
        event: dict[str, object],
        data: dict[str, object],
    ) -> tuple[str, str | None] | None:
        """Return accepted text and validated model metadata."""
        if cls._is_subagent_message(event, data):
            return None
        content = data.get("content")
        if not isinstance(content, str):
            raise RuntimeError(
                f"{cls._PROVIDER_LABEL} session transcript is malformed: "
                "an assistant message carries content of type "
                f"{type(content).__name__}, not text. Reading past it "
                "would grade a truncated answer as whole, so the run is refused."
            )
        if not content.strip():
            return None
        spoke = require_str_or_none(data.get("model"), "model")
        return content.strip(), spoke

    @classmethod
    def _read_matching_session(
        cls,
        raw: str,
        sandbox: str,
    ) -> tuple[str, str | None] | None:
        """Read accepted assistant messages from one matching session."""
        matched = False
        message_models: list[str] = []
        unattributed = False
        chunks: list[str] = []
        for raw_line in raw.splitlines():
            parsed = cls._parse_event(raw_line.strip())
            if parsed is None:
                continue
            kind, data, event = parsed
            if kind == "session.start":
                context = data.get("context")
                cwd = context.get("cwd") if isinstance(context, dict) else None
                if cwd != sandbox:
                    return None
                matched = True
                continue
            if kind != "assistant.message" or not matched:
                continue
            accepted = cls._read_assistant_message(event, data)
            if accepted is None:
                continue
            content, spoke = accepted
            chunks.append(content)
            if spoke and spoke not in message_models:
                message_models.append(spoke)
            if not spoke:
                unattributed = True
        if not matched:
            return None
        return "\n\n".join(chunks), cls._model_that_spoke(
            message_models, unattributed=unattributed
        )

    @classmethod
    def _read_session_transcript(
        cls, sandbox: str, *, since: float
    ) -> tuple[str, str | None] | None:
        """Return ``(answer, model_actually_used)`` from the session event log.

        The CLI writes one `events.jsonl` per session under its session-state
        directory, where `assistant.message` carries the reply text and tool
        calls sit in a sibling `toolRequests` field. Reading that is strictly
        better than scraping stdout, where tool-call traces and the stats
        footer are interleaved with the answer and have to be guessed apart.

        Sessions are matched on `session.start.data.context.cwd`, which is the
        unique temp directory this call created. That is race-free when several
        models run at once, unlike picking the newest file. ``since`` bounds the
        scan to logs touched by this call, so the cost does not grow with the
        operator's session history.

        Returns ``None`` when no matching session is found, which leaves the
        caller on the stdout path. That path no longer grades silently: it
        refuses a reply carrying tool traces, and refuses an unconfirmed model
        unless the operator opts in, because the `model` field read here is the
        only evidence about which model actually answered.

        A matched session whose message content is not text raises instead of
        returning ``None``. Skipping the message would grade a truncated answer
        as whole. Returning ``None`` would report a log this reader could not
        decode as a log that does not exist, and the operator who opted in to a
        missing transcript did not opt in to a corrupt one. Absence and
        corruption are different answers, so they take different exits.
        """
        root = cls._session_state_root()
        try:
            candidates = sorted(root.glob("*/events.jsonl"))
        except OSError:
            return None
        for path in candidates:
            raw = cls._read_candidate(path, since)
            if raw is None:
                continue
            transcript = cls._read_matching_session(raw, sandbox)
            if transcript is not None:
                return transcript
        return None

    @staticmethod
    def _is_subagent_message(
        event: dict[str, object], data: dict[str, object]
    ) -> bool:
        """Say whether this message came from a sub-agent, not the model asked.

        A sub-agent runs its own model and writes into the parent session's
        log, so its text is internal working output that no user ever sees.
        Joining it into the answer grades text the requested model did not
        write, and its model would either taint the attribution or refuse a run
        whose real answer was fine.

        Two markers are available and either alone is enough: the CLI stamps
        `agentId` on the event and `parentToolCallId` on the message. They
        usually travel together but not always. One scan of 3777 session logs
        found 2576 messages, across three sessions, carrying `agentId` alone,
        and none carrying `parentToolCallId` alone. Requiring both, or reading
        only the second, would have joined those 2576 into a graded answer. No
        marker in that scan was null, so testing for the key and testing its
        value agreed on every message.

        The markers are not a proxy for the model field. In the same scan 36%
        of marked messages named a model that an unmarked message in the same
        log also used, so classifying by "ran a different model than the
        primary" would have accepted tens of thousands of sub-agent messages.
        """
        return "agentId" in event or "parentToolCallId" in data

    @staticmethod
    def _model_that_spoke(
        message_models: list[str], *, unattributed: bool
    ) -> str | None:
        """Return the single model that produced every accepted message.

        `assistant.message` carries the model that generated that specific
        text. The session's opening `selectedModel` does not: a
        `session.model_change` event can supersede it mid-session, and it is
        absent entirely from most observed session logs, so reading it would
        both miss substitutions and refuse the common case.

        Returns ``None`` unless exactly one model accounts for the whole
        answer. More than one model means the answer is a blend that no single
        model produced. ``unattributed`` means some message contributed text
        while naming no model, so a second message naming one would otherwise
        vouch for text it did not write.
        """
        if unattributed or len(message_models) != 1:
            return None
        return message_models[0]

    @classmethod
    def _is_footer_line(cls, line: str) -> bool:
        match = cls._FOOTER_LABEL_RE.match(line)
        if match is None:
            return False
        # Either the label is padded out to the value column, or it is followed
        # by a run of spaces no prose would use. Both are stats formatting.
        if len(match.group(0)) < cls._FOOTER_COLUMN and len(match.group(1)) < 2:
            return False
        return cls._is_footer_value(line[match.end() :])

    @classmethod
    def _is_footer_value(cls, value: str) -> bool:
        """Reject a stats-shaped prefix whose remainder reads as prose.

        Labels longer than the value column ("Total duration") pass the column
        test no matter what follows, so a sentence opening with one would be
        stripped off the end of a real answer. Stats values are a few short
        tokens and never close a sentence.
        """
        stripped = value.strip()
        if not stripped:
            return True
        if stripped.endswith(cls._FOOTER_PROSE_ENDINGS):
            return False
        return len(stripped.split()) <= cls._FOOTER_VALUE_MAX_WORDS

    @classmethod
    def _strip_footer(cls, text: str) -> str:
        """Remove the CLI's trailing stats block.

        Footer chrome must be separated from the answer by a blank line. When
        stdout ends in footer-shaped lines without that separator, the fallback
        path cannot tell chrome from model text, so it refuses the run instead
        of silently truncating the answer. See #4125.
        """
        lines = text.splitlines()
        end = len(lines)
        while end > 0 and not lines[end - 1].strip():
            end -= 1
        footer_start = end
        while footer_start > 0 and cls._is_footer_line(lines[footer_start - 1]):
            footer_start -= 1
        if footer_start == end:
            return "\n".join(lines[:end]).strip()
        if footer_start > 0 and lines[footer_start - 1].strip():
            raise RuntimeError(
                f"{cls._PROVIDER_LABEL} stdout ends with a stats-shaped line, "
                "but no blank line separates it from the answer. Nothing on "
                "this fallback path can tell CLI stats from model text, so the "
                "run is refused rather than truncated."
            )
        answer_end = footer_start
        while answer_end > 0 and not lines[answer_end - 1].strip():
            answer_end -= 1
        return "\n".join(lines[:answer_end]).strip()

    @classmethod
    def _unverified_model_allowed(cls) -> bool:
        """Report whether the operator opted in to an unconfirmed model.

        Anything other than an explicit affirmative reads as off, so a stray
        empty or "0" value fails closed rather than silently loosening the
        check it exists to guard.
        """
        raw = os.environ.get(cls._UNVERIFIED_MODEL_ENV, "")
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @classmethod
    def _may_carry_tool_trace(cls, text: str) -> bool:
        """Report whether a line in stdout opens the way a CLI trace opens.

        Only meaningful on the stdout fallback. When the structured transcript
        is readable the answer comes from `assistant.message`, which never
        carries a trace.

        This deliberately cannot tell a real trace apart from an answer that
        happens to begin with the same marker, and it refuses both. On the
        fallback there is no boundary between a trace and the reply, so the
        choice is a visible refusal an operator can clear by pointing at the
        session directory, or silently scoring the harness as the model. Only
        one of those leaves a mark, so the name says `may`.
        """
        return any(
            line.lstrip().startswith(cls._TRACE_LINE_PREFIXES)
            for line in text.splitlines()
        )

    def _run_process(
        self,
        argv: list[str],
        sandbox: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run one isolated CLI process and return only successful output."""
        try:
            # argv is built from literals and validated fields. shell=False is
            # the default, so nothing here reaches a shell.
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self._timeout,
                cwd=sandbox,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{self._provider_label} API request timed out after "
                f"{self._timeout:.0f}s. The service may be slow or unreachable."
            ) from exc
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"{self._provider_label} network error: executable "
                f"{self._executable!r} not found on PATH. Install the "
                "GitHub Copilot CLI or pass a different executable."
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"{self._provider_label} API network error: {type(exc).__name__}. "
                "Check that the Copilot CLI is installed and authenticated."
            ) from exc
        if completed.returncode != 0:
            stderr = completed.stderr or completed.stdout or ""
            raise _safe_process_error(completed.returncode, stderr)
        return completed

    def _build_prompt(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> str:
        """Fold supported messages into the CLI's single prompt channel."""
        for message in messages:
            role = message.get("role", "")
            if role not in ("user", "system"):
                raise RuntimeError(
                    f"{self._provider_label} API does not support message role "
                    f"{role!r}. Copilot CLI can only fold user/system messages "
                    "into its single prompt channel."
                )
        parts = [system.strip()] if system.strip() else []
        parts.extend(
            str(message.get("content", "")).strip()
            for message in messages
            if str(message.get("content", "")).strip()
        )
        prompt = "\n\n".join(parts)
        if not prompt:
            raise RuntimeError(
                f"{self._provider_label} requires a non-empty prompt; "
                "system and messages were both blank."
            )
        return prompt

    def _build_argv(self, prompt: str, model: str) -> list[str]:
        """Build the fixed, shell-free Copilot CLI invocation."""
        return [
            self._executable,
            "--prompt",
            prompt,
            "--model",
            model,
            "--allow-all-tools",
            "--no-custom-instructions",
            "--disable-builtin-mcps",
            "--no-ask-user",
            "--no-color",
            "--log-level",
            "none",
        ]

    def _read_answer(
        self,
        completed: subprocess.CompletedProcess[str],
        transcript: tuple[str, str | None] | None,
        model: str,
    ) -> tuple[str, str | None]:
        """Return answer text and confirmed model, or refuse attribution loss."""
        answer = ""
        model_used: str | None = None
        if transcript is not None:
            answer, model_used = transcript
            if model_used is not None and model_used != model:
                raise RuntimeError(
                    f"{self._provider_label} API returned no choices for model "
                    f"{model}: the session ran {model_used} instead."
                )
        if not answer:
            answer = self._strip_footer(completed.stdout or "")
            if answer and self._may_carry_tool_trace(answer):
                raise RuntimeError(
                    f"{self._provider_label} could not read a reply for model "
                    f"{model}: the session transcript was unavailable and a line "
                    "in stdout opens with a CLI trace marker. Nothing on this "
                    "path can tell a trace apart from an answer that starts the "
                    "same way, so the run is refused rather than graded. Point "
                    f"{self._SESSION_STATE_ENV} at the CLI session directory so "
                    "the structured transcript can be read."
                )
        if not answer:
            raise RuntimeError(
                f"{self._provider_label} API returned no choices for model {model}."
            )
        if model_used is None and not self._unverified_model_allowed():
            raise RuntimeError(
                f"{self._provider_label} could not confirm which model answered "
                f"for {model}: no session transcript was readable, and the CLI "
                "accepts --model without confirming it. This transport only "
                "feeds model-attributed results, so an unconfirmed reply is a "
                f"score for an unknown model. Point {self._SESSION_STATE_ENV} "
                "at the CLI session directory, or set "
                f"{self._UNVERIFIED_MODEL_ENV}=1 to accept that loss knowingly."
            )
        return answer, model_used

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
        # Copilot CLI takes a single prompt with no separate system channel and
        # no sampling controls. Fold the system text in as a leading block;
        # ignore max_tokens/temperature/seed rather than failing, so the same
        # fixture runs unchanged across providers. Callers that need sampling
        # determinism must use an HTTP provider.
        #
        # Roles go with them: every message contributes its content and nothing
        # records who said it. The one caller builds a single user message, so
        # nothing is lost today. A multi-turn caller would hand the model its
        # own prior replies as user instructions, and this signature accepts
        # that input without complaint, so the loss would be silent. See #4128.
        del max_tokens, temperature, seed

        prompt = self._build_prompt(messages, system)
        argv = self._build_argv(prompt, model)
        with tempfile.TemporaryDirectory(prefix="eval-copilot-") as sandbox:
            started = time.time()
            completed = self._run_process(argv, sandbox)
            transcript = self._read_session_transcript(sandbox, since=started - 5.0)
        answer, model_used = self._read_answer(completed, transcript, model)
        # Publish which model the transcript confirmed, reset on every call so
        # an earlier verified reply cannot vouch for a later unverified one.
        # None means nobody confirmed, which is how an archived run tells a
        # confirmed answer apart from a loss the operator opted in to.
        self.system_fingerprint = model_used
        return answer
