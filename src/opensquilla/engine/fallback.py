"""Fallback policy for provider retry and model failover."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from enum import StrEnum


class ProviderErrorKind(StrEnum):
    RATE_LIMIT = "rate_limit"
    AUTH_FAILURE = "auth_failure"
    OVERLOADED = "overloaded"
    CONTEXT_OVERFLOW = "context_overflow"
    TRANSPORT_TRANSIENT = "transport_transient"
    UNKNOWN = "unknown"


_GATEWAY_CODES = r"(?:504|520|522|523|524)"
_GATEWAY_CONTEXT = r"(?:cloudflare|openrouter|upstream|gateway|backend)"
_GATEWAY_ERROR_TERMS = (
    r"(?:error|returned|returning|failed|failure|unreachable|timeout|timed out|"
    r"overload(?:ed)?|bad gateway|origin)"
)
_TRANSIENT_HTTP_STATUS_RE = re.compile(
    r"\b(?:http(?: status)?|status(?:[_ -]?code)?|error code|code)\s*[:=]?\s*"
    rf"{_GATEWAY_CODES}\b"
)
_TRANSIENT_GATEWAY_CONTEXT_RE = re.compile(
    rf"\b{_GATEWAY_CONTEXT}\b[^\n]{{0,80}}\b{_GATEWAY_ERROR_TERMS}\b[^\n]{{0,80}}\b{_GATEWAY_CODES}\b"
    rf"|\b{_GATEWAY_CONTEXT}\b[^\n]{{0,80}}\b{_GATEWAY_CODES}\b[^\n]{{0,80}}\b{_GATEWAY_ERROR_TERMS}\b"
    rf"|\b{_GATEWAY_CODES}\b[^\n]{{0,80}}\b{_GATEWAY_CONTEXT}\b[^\n]{{0,80}}\b{_GATEWAY_ERROR_TERMS}\b"
)


@dataclass
class FallbackPolicy:
    """Policy for retrying failed provider calls and falling back to alternate models."""

    max_retries: int = 3
    fallback_models: list[str] = field(default_factory=list)
    base_backoff_ms: int = 1000
    max_backoff_ms: int = 30_000

    @staticmethod
    def classify_error(message: str) -> ProviderErrorKind:
        """Classify a provider error message into a retry category."""
        msg = message.lower()
        if "rate_limit" in msg or "rate limit" in msg or "429" in msg:
            return ProviderErrorKind.RATE_LIMIT
        if "auth" in msg or "401" in msg or "403" in msg or "invalid api key" in msg:
            return ProviderErrorKind.AUTH_FAILURE
        if "overload" in msg or "503" in msg or "502" in msg or "capacity" in msg:
            return ProviderErrorKind.OVERLOADED
        transport_match = (
            "request error" in msg
            or "readtimeout" in msg
            or "connecttimeout" in msg
            or "connection reset" in msg
            or "connection refused" in msg
            or "connection attempts failed" in msg
            or "network is unreachable" in msg
            or "temporary failure" in msg
            or "timed out" in msg
            or "timeout" in msg
        )
        if transport_match:
            return ProviderErrorKind.TRANSPORT_TRANSIENT
        if _TRANSIENT_HTTP_STATUS_RE.search(msg) or _TRANSIENT_GATEWAY_CONTEXT_RE.search(msg):
            return ProviderErrorKind.TRANSPORT_TRANSIENT
        ctx_match = "context" in msg and (
            "exceed" in msg or "length" in msg or "too long" in msg or "overflow" in msg
        )
        if ctx_match:
            return ProviderErrorKind.CONTEXT_OVERFLOW
        return ProviderErrorKind.UNKNOWN

    def should_retry(self, kind: ProviderErrorKind, attempt: int) -> bool:
        """Whether to retry after this error kind at this attempt number."""
        if attempt >= self.max_retries:
            return False
        if kind == ProviderErrorKind.AUTH_FAILURE:
            return False  # Don't retry auth errors
        retryable = (
            ProviderErrorKind.RATE_LIMIT,
            ProviderErrorKind.OVERLOADED,
            ProviderErrorKind.CONTEXT_OVERFLOW,
            ProviderErrorKind.TRANSPORT_TRANSIENT,
        )
        if kind in retryable:
            return True
        return False  # Unknown errors: don't retry by default

    def get_fallback_model(self, current_model: str) -> str | None:
        """Return the next fallback model after current_model, or None if exhausted."""
        if not self.fallback_models:
            return None
        try:
            idx = self.fallback_models.index(current_model)
            if idx + 1 < len(self.fallback_models):
                return self.fallback_models[idx + 1]
        except ValueError:
            # Current model not in fallback list; use first fallback
            if self.fallback_models:
                return self.fallback_models[0]
        return None


def backoff_sleep(
    attempt: int,
    base_ms: int = 1000,
    max_ms: int = 30_000,
    _fake: bool = False,
) -> float:
    """Calculate exponential backoff delay with jitter.

    Args:
        attempt: 0-indexed retry attempt number.
        base_ms: Base delay in milliseconds.
        max_ms: Maximum delay cap in milliseconds.
        _fake: If True, return the delay without actually sleeping (for testing).

    Returns:
        Calculated delay in seconds.
    """
    import structlog

    jitter = random.randint(0, base_ms // 2)  # noqa: S311
    delay_ms = min(base_ms * (2**attempt) + jitter, max_ms)
    delay_s = delay_ms / 1000.0

    if not _fake:
        structlog.get_logger().info("backoff_sleep", delay_s=round(delay_s, 2), attempt=attempt)

    return float(delay_s)
