"""Stable exception identities shared by script-style eval modules."""

from __future__ import annotations


class MalformedProviderMetadataError(RuntimeError):
    """A provider returned metadata that cannot be recorded truthfully."""


class TemperatureDeprecatedError(RuntimeError):
    """The model rejected `temperature` as HTTP 400 `"temperature" is deprecated
    for this model`.

    Raised by a transport's response-reading layer so the caller can retry
    once without `temperature`, per `_eval_common.call_with_temperature_fallback`.
    Carries a fixed message; the provider-controlled body text is never
    attached, matching the redaction policy the rest of this module follows.
    """

    def __init__(self) -> None:
        super().__init__("temperature is deprecated for this model")
