from __future__ import annotations

import pytest

from opensquilla.engine.fallback import FallbackPolicy, ProviderErrorKind
from opensquilla.provider.failures import ProviderFailureKind, classify_provider_error


@pytest.mark.parametrize(
    "provider",
    [
        "deepseek",
        "gemini",
        "dashscope",
        "bailian_coding",
        "moonshot",
        "mistral",
        "groq",
        "zhipu",
        "siliconflow",
        "volcengine",
        "byteplus",
        "qianfan",
        "aihubmix",
        "minimax_openai",
        "vllm",
        "lm_studio",
        "ovms",
    ],
)
def test_openai_compatible_providers_share_common_failure_classification(provider: str) -> None:
    assert (
        classify_provider_error(provider, 401, message="invalid api key")
        is ProviderFailureKind.AUTH_INVALID
    )
    assert (
        classify_provider_error(provider, 429, message="rate limit exceeded")
        is ProviderFailureKind.RATE_LIMITED
    )
    assert (
        classify_provider_error(provider, 404, message="model not found")
        is ProviderFailureKind.MODEL_NOT_FOUND
    )
    assert (
        classify_provider_error(provider, 400, message="unsupported parameter")
        is ProviderFailureKind.UNSUPPORTED_FEATURE
    )


@pytest.mark.parametrize("provider", ["minimax", "minimax_cn", "minimax_global"])
def test_minimax_region_profiles_use_anthropic_failure_classification(provider: str) -> None:
    assert (
        classify_provider_error(provider, 401, raw_code="authentication_error")
        is ProviderFailureKind.AUTH_INVALID
    )


@pytest.mark.parametrize(
    "message",
    [
        "Request error: connection reset by peer",
        "Request error: All connection attempts failed",
        "ReadTimeout while contacting provider",
        "ConnectTimeout while contacting provider",
    ],
)
def test_agent_fallback_retries_transport_transient_errors(message: str) -> None:
    policy = FallbackPolicy(max_retries=2)

    kind = policy.classify_error(message)

    assert kind is ProviderErrorKind.TRANSPORT_TRANSIENT
    assert policy.should_retry(kind, attempt=0) is True


@pytest.mark.parametrize(
    "message",
    [
        "HTTP 520: upstream provider returned an unknown error",
        "HTTP 522",
        "HTTP 523",
        "HTTP 524",
        "HTTP 504",
        "status_code: 523",
    ],
)
def test_agent_fallback_retries_gateway_transient_http_errors(message: str) -> None:
    policy = FallbackPolicy(max_retries=2)

    kind = policy.classify_error(message)

    assert kind is ProviderErrorKind.TRANSPORT_TRANSIENT
    assert policy.should_retry(kind, attempt=0) is True


@pytest.mark.parametrize(
    "message",
    [
        "Cloudflare returned 520",
        "upstream returned 522",
        "OpenRouter upstream error 520",
        "provider backend returned 524",
        "524 from backend failure",
    ],
)
def test_agent_fallback_retries_gateway_context_transient_codes(message: str) -> None:
    policy = FallbackPolicy(max_retries=2)

    kind = policy.classify_error(message)

    assert kind is ProviderErrorKind.TRANSPORT_TRANSIENT
    assert policy.should_retry(kind, attempt=0) is True


@pytest.mark.parametrize(
    "message",
    [
        "random value 520",
        "line 520",
        "520 tokens",
        "issue 520",
        "the provider sent 520 tokens",
        "edge case 520",
        "proxy line 520",
        "gateway request id 520",
        "openrouter model id 520",
        "upstream metadata 520",
        "Cloudflare is configured. " + ("x" * 120) + " value 520",
    ],
)
def test_agent_fallback_does_not_retry_unscoped_gateway_numbers(message: str) -> None:
    policy = FallbackPolicy(max_retries=2)

    kind = policy.classify_error(message)

    assert kind is ProviderErrorKind.UNKNOWN
    assert policy.should_retry(kind, attempt=0) is False


@pytest.mark.parametrize("provider", ["openrouter", "deepseek"])
@pytest.mark.parametrize(
    "message",
    [
        "Cloudflare returned 520",
        "upstream returned 522",
        "OpenRouter upstream error 520",
        "provider backend returned 524",
        "HTTP 523",
    ],
)
def test_provider_failure_classifies_gateway_transient_errors(
    provider: str, message: str
) -> None:
    assert (
        classify_provider_error(provider, None, message=message)
        is ProviderFailureKind.PROVIDER_OVERLOADED
    )


@pytest.mark.parametrize(
    "message",
    [
        "random value 520",
        "line 520",
        "520 tokens",
        "the provider sent 520 tokens",
        "edge case 520",
        "proxy line 520",
        "gateway request id 520",
        "openrouter model id 520",
        "upstream metadata 520",
        "Cloudflare is configured. " + ("x" * 120) + " value 520",
    ],
)
def test_provider_failure_does_not_classify_unscoped_gateway_numbers(message: str) -> None:
    assert (
        classify_provider_error("openrouter", None, message=message)
        is ProviderFailureKind.UNKNOWN
    )


def test_agent_fallback_still_does_not_retry_auth_failures() -> None:
    policy = FallbackPolicy(max_retries=2)

    kind = policy.classify_error("invalid api key")

    assert kind is ProviderErrorKind.AUTH_FAILURE
    assert policy.should_retry(kind, attempt=0) is False
