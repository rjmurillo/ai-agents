"""LLM-based classifier for review comment actionability."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from scripts.ai_review_common.retry import invoke_with_retry

if TYPE_CHECKING:
    import anthropic
from scripts.llm_classification.cache import ClassificationCache
from scripts.llm_classification.config import LLMFallbackConfig

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a code review comment classifier. Your task is to determine
if a review comment is actionable (requires code changes) or non-actionable (informational,
stylistic preference, or already addressed).

Respond with a JSON object containing:
- "is_actionable": boolean - true if the comment requires action
- "confidence": float between 0 and 1 - your confidence level
- "reason": string - brief explanation (max 20 words)

Examples of ACTIONABLE comments:
- "This will cause a null pointer exception"
- "Security vulnerability: user input not sanitized"
- "Missing error handling for API failures"

Examples of NON-ACTIONABLE comments:
- "nit: consider renaming this variable"
- "This is already handled in the base class"
- "Just a suggestion, feel free to ignore"
"""


@dataclass(frozen=True)
class LLMClassificationResult:
    """Result from LLM classification.

    Attributes:
        is_actionable: Whether the comment requires action.
        confidence: Confidence level from the LLM (0-1).
        reason: Brief explanation for the classification.
        from_cache: Whether this result was served from cache.
    """

    is_actionable: bool
    confidence: float
    reason: str
    from_cache: bool = False


_default_classifier: LLMClassifier | None = None


class LLMClassifier:
    """Classifier that uses an LLM to determine comment actionability."""

    def __init__(
        self,
        config: LLMFallbackConfig | None = None,
        cache: ClassificationCache | None = None,
    ) -> None:
        """Initialize classifier with config and optional cache."""
        self._config = config or LLMFallbackConfig.from_env()
        self._cache = cache or ClassificationCache(self._config.cache_max_entries)
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> Any:
        """Lazily initialize Anthropic client."""
        if self._client is None:
            import anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def _call_llm(self, comment_body: str) -> LLMClassificationResult:
        """Make an LLM API call to classify the comment."""
        client = self._get_client()

        def _invoke() -> LLMClassificationResult:
            response = client.messages.create(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                system=_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Classify this review comment:\n\n{comment_body}",
                    }
                ],
            )

            content = response.content[0].text
            data = json.loads(content)

            return LLMClassificationResult(
                is_actionable=bool(data.get("is_actionable", False)),
                confidence=float(data.get("confidence", 0.5)),
                reason=str(data.get("reason", ""))[:100],
                from_cache=False,
            )

        return invoke_with_retry(_invoke, max_retries=2, initial_delay=1)

    def classify(self, comment_body: str) -> LLMClassificationResult | None:
        """Classify a comment using the LLM.

        Returns None if classification fails or is disabled.
        """
        if not self._config.enabled:
            logger.debug("LLM fallback disabled")
            return None

        cached = self._cache.get(comment_body)
        if cached is not None:
            logger.debug("Cache hit for comment classification")
            return LLMClassificationResult(
                is_actionable=cached.is_actionable,
                confidence=cached.confidence,
                reason=cached.reason,
                from_cache=True,
            )

        try:
            result = self._call_llm(comment_body)
            self._cache.put(comment_body, result)
            return result
        except Exception:
            logger.exception("LLM classification failed")
            return None

    def should_use_fallback(self, heuristic_score: float) -> bool:
        """Check if LLM fallback should be used for this heuristic score."""
        return (
            self._config.enabled
            and self._config.is_low_confidence(heuristic_score)
        )

    @property
    def config(self) -> LLMFallbackConfig:
        """Return the classifier configuration."""
        return self._config


def get_default_classifier() -> LLMClassifier:
    """Get the default singleton classifier instance."""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = LLMClassifier()
    return _default_classifier
