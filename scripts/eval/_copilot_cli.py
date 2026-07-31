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
import re
import subprocess
import tempfile
import time
from pathlib import Path

__all__ = ["_CopilotCLIProvider"]


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

    # The CLI prints a stats block after the answer, formatted as a fixed-width
    # label column. Matching on "2+ spaces" is wrong: the widest label
    # ("AI Credits") fills the column and leaves a single space before its
    # value. Match the label, then require the padded prefix to reach the
    # column width, which is what separates a stats line from prose that
    # happens to open with the same word ("Tokens are the unit of billing").
    _FOOTER_LABEL_RE = re.compile(
        r"^(?:Changes|AI Credits|Tokens|Resume|Total duration|Wall time)( +)",
    )
    _FOOTER_COLUMN = 11

    #: A stats value is a short token ("1m2s", "12,345", "$0.04"). Prose that
    #: opens with a label longer than the column ("Total duration and latency
    #: are ...") satisfies the column test vacuously, so the remainder is
    #: checked too: real values are short and do not close a sentence.
    _FOOTER_VALUE_MAX_WORDS = 5
    _FOOTER_PROSE_ENDINGS = (".", "!", "?", ":", ",")

    #: Where the CLI records structured per-session events. Overridable so the
    #: tests can point at a fixture tree instead of the operator's real one.
    _SESSION_STATE_ENV = "COPILOT_SESSION_STATE_DIR"

    #: Opt-in to grade a reply whose model was never confirmed. Off by default:
    #: every consumer of this transport publishes model-attributed results
    #: ("4 of 4 on Opus"), and the CLI accepts `--model` without confirming it,
    #: so an unverified reply is a number attached to an unknown population.
    #: An operator whose CLI writes no session log can set this and accept that
    #: loss knowingly, which is the difference between a disclosed limit and a
    #: silent one.
    _UNVERIFIED_MODEL_ENV = "EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL"

    #: The CLI opens a tool-call trace with a bullet and indents its body with
    #: box-drawing bars. `_strip_footer` cannot remove them: it anchors at the
    #: end of the output, and traces precede the answer. Matching is anchored at
    #: the start of a line because a model answer may legitimately mention these
    #: characters mid-sentence, while the CLI only ever emits them as a prefix.
    _TRACE_LINE_PREFIXES = ("\u25cf", "\u2502", "\u251c", "\u2514")

    def __init__(self, *, executable: str = "copilot", timeout: float = 900.0) -> None:
        self.name = "copilot-cli"
        self._provider_label = "Copilot CLI"
        self._executable = executable
        self._timeout = timeout
        self.system_fingerprint: str | None = None

    @classmethod
    def _session_state_root(cls) -> Path:
        override = os.environ.get(cls._SESSION_STATE_ENV)
        if override:
            return Path(override)
        return Path.home() / ".copilot" / "session-state"

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
        """
        root = cls._session_state_root()
        try:
            candidates = sorted(root.glob("*/events.jsonl"))
        except OSError:
            return None
        for path in candidates:
            try:
                if path.stat().st_mtime < since:
                    continue
                raw = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            matched = False
            message_models: list[str] = []
            unattributed = False
            chunks: list[str] = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                kind = event.get("type")
                if kind == "session.start":
                    context = data.get("context")
                    cwd = context.get("cwd") if isinstance(context, dict) else None
                    if cwd != sandbox:
                        break
                    matched = True
                elif kind == "assistant.message" and matched:
                    if cls._is_subagent_message(event, data):
                        continue
                    content = data.get("content")
                    if isinstance(content, str) and content.strip():
                        chunks.append(content.strip())
                        spoke = data.get("model")
                        if isinstance(spoke, str) and spoke:
                            if spoke not in message_models:
                                message_models.append(spoke)
                        else:
                            unattributed = True
            if matched:
                return "\n\n".join(chunks), cls._model_that_spoke(
                    message_models, unattributed=unattributed
                )
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

        Two markers appear together in real logs, and either alone is enough:
        the CLI stamps `agentId` on the event and `parentToolCallId` on the
        message. In a sampled session both marked exactly the same 671 events,
        and every message they marked ran a different model than the primary.
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

        Walks backwards from the end, dropping blank lines and footer-shaped
        lines, and stops at the first line that is neither. Anchoring at the
        end keeps a stats-shaped line intact anywhere except the end. An
        answer whose last line is stats-shaped is truncated, because nothing
        on this path separates it from the chrome it imitates. See #4125.
        """
        lines = text.splitlines()
        end = len(lines)
        while end > 0:
            candidate = lines[end - 1]
            if not candidate.strip() or cls._is_footer_line(candidate):
                end -= 1
                continue
            break
        return "\n".join(lines[:end]).strip()

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
        del max_tokens, temperature, seed
        parts = [system.strip()] if system.strip() else []
        parts.extend(
            str(m.get("content", "")).strip()
            for m in messages
            if str(m.get("content", "")).strip()
        )
        prompt = "\n\n".join(parts)
        if not prompt:
            raise RuntimeError(
                f"{self._provider_label} requires a non-empty prompt; "
                "system and messages were both blank."
            )

        argv = [
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
        with tempfile.TemporaryDirectory(prefix="eval-copilot-") as sandbox:
            started = time.time()
            try:
                # argv is built above from literals and validated fields, and
                # shell=False is the default, so nothing here reaches a shell.
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
            transcript = self._read_session_transcript(sandbox, since=started - 5.0)

        if completed.returncode != 0:
            # CWE-200: short ascii excerpt only, never the full stderr body.
            stderr = completed.stderr or completed.stdout or ""
            excerpt = "".join(ch for ch in stderr if 32 <= ord(ch) < 127)[:200]
            raise RuntimeError(
                f"{self._provider_label} exited with code "
                f"{completed.returncode}: {excerpt}"
            )
        answer = ""
        model_verified = False
        model_used: str | None = None
        if transcript is not None:
            answer, model_used = transcript
            # The CLI accepts --model without confirming it. Silent substitution
            # would attribute one model's behavior to another, which is worse
            # than a failed run, so treat it as an error rather than a note.
            if model_used is not None and model_used != model:
                raise RuntimeError(
                    f"{self._provider_label} API returned no choices for model "
                    f"{model}: the session ran {model_used} instead."
                )
            model_verified = model_used is not None
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
        if not model_verified and not self._unverified_model_allowed():
            raise RuntimeError(
                f"{self._provider_label} could not confirm which model answered "
                f"for {model}: no session transcript was readable, and the CLI "
                "accepts --model without confirming it. This transport only "
                "feeds model-attributed results, so an unconfirmed reply is a "
                f"score for an unknown model. Point {self._SESSION_STATE_ENV} "
                "at the CLI session directory, or set "
                f"{self._UNVERIFIED_MODEL_ENV}=1 to accept that loss knowingly."
            )
        # Publish which model the transcript confirmed, reset on every call so
        # an earlier verified reply cannot vouch for a later unverified one.
        # None means nobody confirmed, which is how an archived run tells a
        # confirmed answer apart from a loss the operator opted in to.
        self.system_fingerprint = model_used
        return answer
