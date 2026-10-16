import json

import httpx2
import pytest

from pig.domain.ai_policy import AnalysisAction, AnalysisElement
from pig.infrastructure.ai.responses import ProviderFailure, ResponsesAdapter


ELEMENT = AnalysisElement("element-1", "revision-1", "LINE", "1", "Synthetic only")


@pytest.mark.parametrize("provider,url", [
    ("openai", "https://api.openai.com/v1/responses"),
    ("deepseek", "https://api.deepseek.com/responses"),
])
def test_fixed_provider_endpoint_and_structured_request(provider, url, monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_ORG_ID", "unrelated-organization")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "unrelated-project")

    def handler(request):
        captured.update(url=str(request.url), key=request.headers["authorization"],
                        accept_encoding=request.headers["accept-encoding"],
                        organization=request.headers.get("OpenAI-Organization"),
                        project=request.headers.get("OpenAI-Project"),
                        timeout=request.extensions.get("timeout"),
                        request=json.loads(request.content))
        return httpx2.Response(200, json={"id": "resp_test", "object": "response",
            "created_at": 0, "model": "synthetic-model", "status": "completed",
            "output": [{"id": "msg_test", "type": "message", "status": "completed",
            "role": "assistant", "content": [{"type": "output_text", "text": json.dumps({
                "claims": [{"kind": "SUMMARY", "text": "Synthetic claim",
                            "element_ids": [ELEMENT.id], "subject": None, "time": None}]
            }), "annotations": []}]}],
            "usage": {"input_tokens": 70, "output_tokens": 20,
                      "total_tokens": 90}})

    result = ResponsesAdapter(provider=provider,
                              transport=httpx2.MockTransport(handler)).invoke(
        model="synthetic-model", key="synthetic-key", action=AnalysisAction.SUMMARY,
        elements=(ELEMENT,))
    assert captured["url"] == url
    assert captured["key"] == "Bearer synthetic-key"
    assert captured["accept_encoding"] == "identity"
    assert captured["organization"] == ""
    assert captured["project"] == ""
    assert set(captured["timeout"].values()) == {35.0}
    assert captured["request"]["store"] is False
    assert captured["request"]["text"]["format"]["type"] == "json_schema"
    assert (captured["request"]["text"]["format"].get("strict") is True) == (provider == "openai")
    assert captured["request"]["input"][1]["content"]
    assert result.output["claims"][0]["element_ids"] == [ELEMENT.id]
    assert result.input_tokens == 70


def test_provider_rejects_missing_key_and_incomplete_response():
    adapter = ResponsesAdapter(provider="openai",
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json={
            "id": "resp_incomplete", "object": "response", "created_at": 0,
            "model": "synthetic-model", "status": "incomplete", "output": []})))
    with pytest.raises(ProviderFailure, match="CREDENTIAL_MISSING"):
        adapter.invoke(model="synthetic-model", key="", action=AnalysisAction.SUMMARY,
                       elements=(ELEMENT,))
    with pytest.raises(ProviderFailure, match="PROVIDER_INCOMPLETE"):
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))


@pytest.mark.parametrize("content,code", [
    ([], "PROVIDER_OUTPUT_MISSING"),
    ([{"type": "output_text", "text": "not-json", "annotations": []}],
     "PROVIDER_OUTPUT_INVALID"),
])
def test_missing_or_malformed_output_has_safe_error(content, code):
    response = {"id": "resp_test", "object": "response", "created_at": 0,
                "model": "synthetic-model", "status": "completed",
                "output": [{"id": "msg_test", "type": "message", "status": "completed",
                            "role": "assistant", "content": content}]}
    adapter = ResponsesAdapter(provider="openai", transport=httpx2.MockTransport(
        lambda request: httpx2.Response(200, json=response)))
    with pytest.raises(ProviderFailure) as error:
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))
    assert error.value.code == code


def test_malformed_provider_json_has_safe_error():
    adapter = ResponsesAdapter(provider="deepseek", transport=httpx2.MockTransport(
        lambda request: httpx2.Response(200, content=b"not-json",
                                        headers={"content-type": "application/json"})))
    with pytest.raises(ProviderFailure) as error:
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))
    assert error.value.code == "PROVIDER_OUTPUT_INVALID"


@pytest.mark.parametrize("status,code", [
    (302, "PROVIDER_REDIRECT_BLOCKED"),
    (401, "PROVIDER_HTTP_401"),
    (429, "PROVIDER_HTTP_429"),
    (500, "PROVIDER_HTTP_500"),
])
def test_status_errors_are_safe_and_never_retried(status, code):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(status,
                               headers={"location": "https://untrusted.example/steal"},
                               json={"error": {"message": "private provider detail"}})

    adapter = ResponsesAdapter(provider="openai",
                               transport=httpx2.MockTransport(handler))
    with pytest.raises(ProviderFailure) as error:
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))
    assert error.value.code == code
    assert len(calls) == 1


def test_timeout_maps_to_safe_failure_without_retry():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx2.ReadTimeout("private network detail", request=request)

    adapter = ResponsesAdapter(provider="deepseek",
                               transport=httpx2.MockTransport(handler))
    with pytest.raises(ProviderFailure) as error:
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))
    assert error.value.code == "PROVIDER_UNAVAILABLE"
    assert len(calls) == 1


@pytest.mark.parametrize("declared_length", [True, False])
def test_response_size_is_bounded_by_actual_bytes(declared_length):
    body = json.dumps({"id": "resp_large", "object": "response", "status": "completed",
                       "padding": "x" * 2_000_001}).encode()

    class Chunks(httpx2.SyncByteStream):
        def __iter__(self):
            yield body[:1_000_000]
            yield body[1_000_000:]

    def handler(request):
        headers = {"content-length": str(len(body))} if declared_length else {}
        return httpx2.Response(200, headers=headers, stream=Chunks())

    adapter = ResponsesAdapter(provider="openai",
                               transport=httpx2.MockTransport(handler))
    with pytest.raises(ProviderFailure) as error:
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))
    assert error.value.code == "PROVIDER_RESPONSE_TOO_LARGE"


def test_compressed_response_is_rejected_before_decompression():
    class CompressedBytes(httpx2.SyncByteStream):
        def __iter__(self):
            yield b"synthetic bytes"

    adapter = ResponsesAdapter(provider="openai", transport=httpx2.MockTransport(
        lambda request: httpx2.Response(
            200, stream=CompressedBytes(), headers={"content-encoding": "gzip"})))
    with pytest.raises(ProviderFailure) as error:
        adapter.invoke(model="synthetic-model", key="synthetic-key",
                       action=AnalysisAction.SUMMARY, elements=(ELEMENT,))
    assert error.value.code == "PROVIDER_RESPONSE_ENCODING_UNSUPPORTED"
