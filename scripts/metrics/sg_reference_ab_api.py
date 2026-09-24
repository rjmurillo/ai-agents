"""Anthropic Messages API transport and plugin-contract loading for the
inline-vs-referenced diff A/B harness (#5856).

Evaluation harness support module only. Not wired to any hook. Split out of
``scripts/metrics/sg_reference_ab.py`` under the taste-lints file-size gate:
this module owns everything that talks to the outside world or to the
installed plugin: credential and model resolution, reading the plugin's
system prompt and findings schema (read only), the HTTP transport, and
classifying what a failed request means for one run. The investigate tool
loop built on top of this transport (tool-confined filesystem handlers, tool
definitions/dispatch, the per-turn loop) lives in the sibling module
``sg_reference_ab_toolloop.py``, split out for the same reason. Fixture
repositories live in ``sg_reference_ab_fixtures.py``; orchestration,
aggregation, and the CLI live in ``sg_reference_ab.py``.

Canonical sources cited per ``.claude/rules/canonical-source-mirror.md``:

1. Usage field names (``input_tokens``, ``output_tokens``,
   ``cache_read_input_tokens``, ``cache_creation_input_tokens``) mirror
   ``_record_usage`` at ``<plugin>/hooks/_base.py:147-177``, verified by
   reading that function in the session that first wrote this harness.
   Verbatim excerpt::

       i = int(u.get("input_tokens") or 0)
       o = int(u.get("output_tokens") or 0)
       cr = int(u.get("cache_read_input_tokens") or 0)
       cw = int(u.get("cache_creation_input_tokens") or 0)

   (``UsageTotals``, the dataclass that carries these fields, lives in
   ``sg_reference_ab_toolloop.py``, which accumulates it turn by turn; this
   module has no independent usage-accounting logic of its own.)

2. ``.env``-file API key parsing mirrors ``load_api_key`` at
   ``scripts/eval/_anthropic_api.py:39-93`` in this repository: only a
   repo-root ``.env`` is consulted (no parent-directory walk), and a
   symlinked ``.env`` is refused, both preserved here as the same CWE-22
   defense against an attacker-planted credential file.

3. The HTTP error body shape parsed by :func:`_parse_anthropic_error` and
   the auth/billing status codes in :data:`_INFRA_HTTP_STATUS` mirror the
   Claude API's documented error contract (fetched 2026-09-24,
   https://platform.claude.com/docs/en/api/errors, "HTTP errors" and
   "Error shapes" sections). Verbatim excerpt of the documented shape::

       {
         "type": "error",
         "error": {
           "type": "not_found_error",
           "message": "The requested resource could not be found."
         },
         "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"
       }

   and the documented status-to-type mapping this module treats as an
   infrastructure (operator/environment, not review-quality) failure:
   401 ``authentication_error``, 402 ``billing_error``, 403
   ``permission_error``. The same page documents that a 400
   ``invalid_request_error`` is also returned "when usage reaches an
   organization or workspace spend limit", which is why
   :func:`_is_infra_failure` additionally checks ``error.message`` for a
   credit-balance mention regardless of status: a live run failed with
   exactly this shape, ``{"type":"error","error":{"type":
   "invalid_request_error","message":"Your credit balance is too low..."}}``
   over HTTP 400, and the pre-existing bare ``classify_failure`` recorded
   only ``"http_400"``, indistinguishable from an ordinary malformed
   request.

Stricter/looser/different than canonical
-----------------------------------------

402 is not in the task that motivated this module's failure-classification
rework (401, 403, and a credit-balance message match), but it is documented
as the Claude API's dedicated billing-error status; omitting it would leave
exactly the inverse gap this rework exists to close (a real billing 402
silently NOT counted as an infrastructure failure), so it is included here
alongside 401/403.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
REQUEST_TIMEOUT_S = 120
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_BASE_DELAY_S = 2.0
RETRY_MAX_DELAY_S = 60.0
FALLBACK_MODEL = "claude-sonnet-5"

_MAX_ERROR_BODY_BYTES = 4_096
_MAX_FAILURE_DETAIL_CHARS = 200
# See module docstring citation 3.
_INFRA_HTTP_STATUS = frozenset({401, 402, 403})
_CREDIT_BALANCE_MARKER = "credit balance"


# ---------------------------------------------------------------------------
# Model / API key resolution
# ---------------------------------------------------------------------------


def default_model(eval_dir: Path | None = None) -> str:
    """``DEFAULT_MODEL`` from ``scripts/eval/_anthropic_api.py`` when cleanly
    importable, else the literal fallback. That module does a bare
    ``from _eval_common import (...)``, a sibling import that only resolves
    when ``scripts/eval`` is on ``sys.path``, so this adds it temporarily
    rather than importing the dotted package path. ``eval_dir`` is
    overridable for tests; real callers always use the repository's own
    ``scripts/eval``.
    """
    eval_dir = eval_dir or (Path(__file__).resolve().parents[1] / "eval")
    if not (eval_dir / "_anthropic_api.py").is_file():
        return FALLBACK_MODEL
    eval_dir_str = str(eval_dir)
    inserted = eval_dir_str not in sys.path
    if inserted:
        sys.path.insert(0, eval_dir_str)
    try:
        module = importlib.import_module("_anthropic_api")
        return str(getattr(module, "DEFAULT_MODEL", FALLBACK_MODEL))
    except Exception:
        return FALLBACK_MODEL
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(eval_dir_str)


def load_api_key(repo_root: Path) -> str | None:
    """``ANTHROPIC_API_KEY`` from the environment, else a repo-root ``.env``."""
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key.strip()
    env_path = repo_root / ".env"
    if env_path.is_symlink() or not env_path.is_file():
        return None
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() != "ANTHROPIC_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        return value
    return None


# ---------------------------------------------------------------------------
# Plugin contract loading (provenance)
# ---------------------------------------------------------------------------


class PluginContractError(Exception):
    """The plugin directory, or an expected symbol inside it, is missing."""


@dataclass(frozen=True, slots=True)
class PluginContract:
    system: str
    findings_schema: dict[str, Any]
    review_api_sha256: str
    llm_sha256: str
    plugin_version: str | None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_plugin_version(plugin_json_path: Path) -> str | None:
    if not plugin_json_path.is_file():
        return None
    try:
        data = json.loads(plugin_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return str(version) if version is not None else None


def _exec_review_api(plugin_dir: Path, review_api_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "sg_reference_ab_plugin_review_api", review_api_path
    )
    if spec is None or spec.loader is None:
        raise PluginContractError(f"could not load review_api.py from {plugin_dir}")
    module = importlib.util.module_from_spec(spec)
    hooks_dir_str = str(plugin_dir)
    inserted = hooks_dir_str not in sys.path
    if inserted:
        sys.path.insert(0, hooks_dir_str)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise PluginContractError(f"failed importing review_api.py: {exc}") from exc
    finally:
        if inserted:
            sys.path.remove(hooks_dir_str)
    return module


def load_plugin_contract(plugin_dir: Path) -> PluginContract:
    """Load the investigate system prompt and findings schema, read only."""
    review_api_path = plugin_dir / "review_api.py"
    llm_path = plugin_dir / "llm.py"
    if not review_api_path.is_file() or not llm_path.is_file():
        raise PluginContractError(
            f"plugin directory {plugin_dir} is missing review_api.py or llm.py"
        )
    module = _exec_review_api(plugin_dir, review_api_path)
    system = getattr(module, "AGENTIC_INVESTIGATE_SYSTEM", None)
    schema = getattr(module, "FINDINGS_SCHEMA", None)
    if not isinstance(system, str) or not isinstance(schema, dict):
        raise PluginContractError(
            "review_api.py did not define AGENTIC_INVESTIGATE_SYSTEM/FINDINGS_SCHEMA"
        )
    plugin_version = _read_plugin_version(plugin_dir.parent / ".claude-plugin" / "plugin.json")
    return PluginContract(
        system=system,
        findings_schema=schema,
        review_api_sha256=_sha256_file(review_api_path),
        llm_sha256=_sha256_file(llm_path),
        plugin_version=plugin_version,
    )


# ---------------------------------------------------------------------------
# Messages API transport
# ---------------------------------------------------------------------------


def _send_once(request: urllib.request.Request) -> dict[str, Any]:
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        return dict(json.loads(response.read().decode("utf-8", errors="replace")))


def retry_delay_s(exc: Exception, jitter: float) -> float | None:
    """Seconds to wait before the single retry, or None when ``exc`` is not retryable.

    A 429 or 5xx honors a numeric ``Retry-After`` header, capped at
    ``RETRY_MAX_DELAY_S``. Otherwise the wait is ``RETRY_BASE_DELAY_S`` scaled by
    ``jitter`` in [0.5, 1.5). A network error or timeout is retried too: the
    Messages API call is read-only, so a repeat cannot double an effect.
    """
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code not in _RETRYABLE_STATUS:
            return None
        header = exc.headers.get("Retry-After") if exc.headers else None
        if header is not None and header.strip().isdigit():
            return min(float(header.strip()), RETRY_MAX_DELAY_S)
    elif not isinstance(exc, (urllib.error.URLError, TimeoutError)):
        return None
    return RETRY_BASE_DELAY_S * (0.5 + jitter)


def _send_with_one_retry(request: urllib.request.Request) -> dict[str, Any]:
    try:
        return _send_once(request)
    except (urllib.error.URLError, TimeoutError) as exc:
        delay = retry_delay_s(exc, random.random())
        if delay is None:
            raise
    time.sleep(delay)
    return _send_once(request)


def post_messages(
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    body = {
        "model": model,
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
        "tools": tools,
    }
    request = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    return _send_with_one_retry(request)


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """What a request exception means for one run row.

    ``failure`` is the compact machine-readable code stored on
    ``ToolLoopResult`` / ``RunResult``: ``http_{code}`` when the body could
    not be parsed into the documented shape, ``http_{code}:{error.type}``
    when it could (module docstring citation 3). ``failure_detail`` is the
    documented ``error.message``, truncated to ``_MAX_FAILURE_DETAIL_CHARS``
    characters; it is never the raw request body, the response body beyond
    that truncation, or the API key. ``infra_failure`` is True for the
    documented auth/billing statuses or a credit-balance message (citation 3).
    """

    failure: str
    failure_detail: str | None
    infra_failure: bool


def _read_http_error_body(exc: urllib.error.HTTPError) -> str:
    """Read up to ``_MAX_ERROR_BODY_BYTES`` of an HTTPError's response body.

    Guarded: ``exc.fp`` can be ``None`` (observed to make ``.read()`` return
    ``b""`` rather than raise, e.g. an HTTPError built without a real
    response), and a live socket can still fail mid-read. Both resolve to
    ``""`` here rather than propagating, since a body this module cannot read
    is equivalent to no body for classification purposes; the caller already
    has the exact status from ``exc.code`` regardless.
    """
    try:
        raw = exc.read(_MAX_ERROR_BODY_BYTES)
    except (OSError, ValueError):
        return ""
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")


def _parse_anthropic_error(body: str) -> tuple[str | None, str | None]:
    """Extract ``(error.type, error.message)`` from a Claude API error body.

    Matches the documented shape in module docstring citation 3. Returns
    ``(None, None)`` when the body is not JSON, is not a JSON object, or
    lacks an ``error`` object carrying string ``type``/``message`` fields:
    this is best-effort classification, and every caller falls back to the
    bare ``http_{code}`` shape (with no detail, not counted as infra by
    message) when parsing fails.
    """
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(parsed, dict):
        return None, None
    error = parsed.get("error")
    if not isinstance(error, dict):
        return None, None
    error_type = error.get("type")
    message = error.get("message")
    return (
        error_type if isinstance(error_type, str) else None,
        message if isinstance(message, str) else None,
    )


def _is_infra_failure(status: int, message: str | None) -> bool:
    """True when a failure reflects an operator/environment problem (auth,
    billing) rather than a service or request-shape problem the review
    prompts themselves could be responsible for. See module docstring
    citation 3 and its Stricter/looser/different section for the status set
    and the message-based fallback.
    """
    if status in _INFRA_HTTP_STATUS:
        return True
    return message is not None and _CREDIT_BALANCE_MARKER in message.lower()


def _classify_http_error(exc: urllib.error.HTTPError) -> FailureClassification:
    body = _read_http_error_body(exc)
    error_type, message = _parse_anthropic_error(body)
    failure = f"http_{exc.code}:{error_type}" if error_type else f"http_{exc.code}"
    detail = message[:_MAX_FAILURE_DETAIL_CHARS] if message else None
    return FailureClassification(
        failure=failure,
        failure_detail=detail,
        infra_failure=_is_infra_failure(exc.code, message),
    )


def classify_failure(exc: Exception) -> FailureClassification:
    """Classify a request exception raised by :func:`post_messages`.

    Public (not module-private) because
    ``sg_reference_ab_toolloop.run_investigate_loop`` calls it across the
    module boundary this file was split from.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return _classify_http_error(exc)
    if isinstance(exc, urllib.error.URLError):
        return FailureClassification("network_error", None, False)
    if isinstance(exc, TimeoutError):
        return FailureClassification("timeout", None, False)
    return FailureClassification(f"error_{type(exc).__name__}", None, False)
