"""Fixed-origin Responses adapters backed by the official OpenAI Python SDK."""

from __future__ import annotations

import json

import httpx2
from openai import (
    APIConnectionError, APIResponseValidationError, APIStatusError,
    APITimeoutError, DefaultHttpx2Client, OpenAI,
)

from pig.application.ai_prompts import OUTPUT_SCHEMA, PROMPT_NAME, instruction_for
from pig.application.ai_ports import ProviderFailure, ProviderResult
from pig.domain.ai_policy import AnalysisAction, AnalysisElement


_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com",
}
_MAX_RESPONSE_BYTES = 2_000_000


class _BoundedResponseStream(httpx2.SyncByteStream):
    """Count actual response bytes, including when Content-Length is absent or false."""

    def __init__(self, stream: httpx2.SyncByteStream) -> None:
        self._stream = stream

    def __iter__(self):
        remaining = _MAX_RESPONSE_BYTES
        for chunk in self._stream:
            remaining -= len(chunk)
            if remaining < 0:
                raise ProviderFailure("PROVIDER_RESPONSE_TOO_LARGE")
            yield chunk

    def close(self) -> None:
        self._stream.close()


def _bound_response(response: httpx2.Response) -> None:
    # Count raw bytes safely only when the server has not compressed the body.
    # HTTPX2 otherwise decodes after the transport stream has been consumed.
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding not in ("", "identity"):
        raise ProviderFailure("PROVIDER_RESPONSE_ENCODING_UNSUPPORTED")
    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > _MAX_RESPONSE_BYTES:
                raise ProviderFailure("PROVIDER_RESPONSE_TOO_LARGE")
        except ValueError:
            pass  # The actual byte count below remains authoritative.
    response.stream = _BoundedResponseStream(response.stream)


class ResponsesAdapter:
    def __init__(self, *, provider: str,
                 transport: httpx2.BaseTransport | None = None) -> None:
        if provider not in _BASE_URLS:
            raise ValueError("unsupported provider")
        self.provider = provider
        self._base_url = _BASE_URLS[provider]
        self._transport = transport

    def invoke(self, *, model: str, key: str, action: AnalysisAction,
               elements: tuple[AnalysisElement, ...], timeout: float = 35.0) -> ProviderResult:
        if not key or not key.strip():
            raise ProviderFailure("CREDENTIAL_MISSING")
        schema_format = {"type": "json_schema", "name": PROMPT_NAME,
                         "schema": OUTPUT_SCHEMA}
        if self.provider == "openai":
            schema_format["strict"] = True
        input_items = [
            {"role": "developer", "content": instruction_for(action)},
            {"role": "user", "content": json.dumps({
                "action": action.value,
                "elements": [{"id": e.id, "revision_id": e.revision_id,
                              "locator_kind": e.locator_kind,
                              "locator_value": e.locator_value, "text": e.text}
                             for e in elements],
            }, ensure_ascii=False)},
        ]
        client_options = {
            "follow_redirects": False,
            "event_hooks": {"response": [_bound_response]},
        }
        if self._transport is not None:
            client_options["transport"] = self._transport
        try:
            with OpenAI(
                api_key=key, base_url=self._base_url,
                organization="", project="",
                timeout=timeout, max_retries=0,
                default_headers={"Accept-Encoding": "identity"},
                http_client=DefaultHttpx2Client(**client_options),
            ) as client:
                response = client.responses.create(
                    model=model, input=input_items,
                    text={"format": schema_format}, store=False,
                    max_output_tokens=4000,
                )
            if response.status != "completed":
                raise ProviderFailure("PROVIDER_INCOMPLETE")
            texts = [part.text for item in response.output
                     if item.type == "message" for part in item.content
                     if part.type == "output_text"]
            if len(texts) != 1 or not isinstance(texts[0], str):
                raise ProviderFailure("PROVIDER_OUTPUT_MISSING")
            output = json.loads(texts[0])
            usage = response.usage
            return ProviderResult(output,
                                  usage.input_tokens if usage else None,
                                  usage.output_tokens if usage else None)
        except ProviderFailure:
            raise
        except APIStatusError as exc:
            code = ("PROVIDER_REDIRECT_BLOCKED" if 300 <= exc.status_code < 400
                    else f"PROVIDER_HTTP_{exc.status_code}")
            raise ProviderFailure(code) from None
        except (APITimeoutError, APIConnectionError):
            raise ProviderFailure("PROVIDER_UNAVAILABLE") from None
        except APIResponseValidationError:
            raise ProviderFailure("PROVIDER_OUTPUT_INVALID") from None
        except (TypeError, ValueError, KeyError, AttributeError):
            raise ProviderFailure("PROVIDER_OUTPUT_INVALID") from None
