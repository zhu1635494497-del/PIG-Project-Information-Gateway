"""Networkless SDK contract checks for PIG's two fixed provider origins."""

import json

import httpx2
import openai
import pytest

from pig.application.ai_prompts import OUTPUT_SCHEMA, PROMPT_NAME


def _client(base_url, handler):
    return openai.OpenAI(
        api_key="synthetic-key",
        base_url=base_url,
        max_retries=0,
        timeout=35.0,
        http_client=openai.DefaultHttpx2Client(
            follow_redirects=False,
            transport=httpx2.MockTransport(handler),
        ),
    )


def _response():
    return {
        "id": "resp_synthetic",
        "object": "response",
        "created_at": 0,
        "model": "synthetic-model",
        "status": "completed",
        "output": [{"id": "msg_synthetic", "type": "message", "status": "completed",
                    "role": "assistant", "content": [{"type": "output_text",
                    "text": json.dumps({"claims": []}), "annotations": []}]}],
        "usage": {"input_tokens": 70, "output_tokens": 20, "total_tokens": 90},
    }


@pytest.mark.parametrize("provider,base_url,path", [
    ("openai", "https://api.openai.com/v1", "/v1/responses"),
    ("deepseek", "https://api.deepseek.com", "/responses"),
])
def test_fixed_origin_request_and_typed_response(provider, base_url, path):
    observed = []

    def handler(request):
        observed.append(request)
        return httpx2.Response(200, json=_response())

    with _client(base_url, handler) as client:
        result = client.responses.create(
            model="synthetic-model",
            input=[{"role": "developer", "content": "Synthetic instruction"},
                   {"role": "user", "content": "Synthetic data"}],
            text={"format": {"type": "json_schema", "name": PROMPT_NAME,
                             "schema": OUTPUT_SCHEMA,
                             **({"strict": True} if provider == "openai" else {})}},
            store=False,
            max_output_tokens=4000,
        )
    assert len(observed) == 1
    request = observed[0]
    assert request.url.scheme == "https"
    assert request.url.host == base_url.split("/")[2]
    assert request.url.path == path
    assert request.headers["authorization"] == "Bearer synthetic-key"
    body = json.loads(request.content)
    assert body["store"] is False
    assert body["text"]["format"]["schema"] == OUTPUT_SCHEMA
    assert (body["text"]["format"].get("strict") is True) == (provider == "openai")
    assert json.loads(result.output_text) == {"claims": []}
    assert result.usage.input_tokens == 70


@pytest.mark.parametrize("status,expected", [(302, openai.APIStatusError),
                                               (429, openai.RateLimitError)])
def test_redirect_and_rate_limit_are_not_retried(status, expected):
    calls = []

    def handler(request):
        calls.append(request)
        headers = {"location": "https://untrusted.example/responses"} if status == 302 else {}
        return httpx2.Response(status, headers=headers, json={"error": {"message": "synthetic"}})

    with _client("https://api.openai.com/v1", handler) as client:
        with pytest.raises(expected):
            client.responses.create(model="synthetic-model", input="Synthetic data")
    assert len(calls) == 1


def test_timeout_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx2.ReadTimeout("synthetic timeout", request=request)

    with _client("https://api.deepseek.com", handler) as client:
        with pytest.raises(openai.APITimeoutError):
            client.responses.create(model="synthetic-model", input="Synthetic data")
    assert len(calls) == 1


def test_sdk_alone_does_not_preserve_pig_response_size_limit():
    oversized = _response()
    oversized["padding"] = "x" * 2_000_001
    assert len(json.dumps(oversized).encode("utf-8")) > 2_000_000

    with _client("https://api.openai.com/v1",
                 lambda request: httpx2.Response(200, json=oversized)) as client:
        result = client.responses.create(model="synthetic-model", input="Synthetic data")
    # PIG's current transport rejects bodies over 2 MB. The SDK does not do so
    # by itself; a bounded transport is required before production replacement.
    assert json.loads(result.output_text) == {"claims": []}
