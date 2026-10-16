"""Replaceable provider and credential contracts; Application knows no HTTP details."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pig.domain.ai_policy import AnalysisAction, AnalysisElement


class ProviderFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProviderResult:
    output: object
    input_tokens: int | None
    output_tokens: int | None


class AIProvider(Protocol):
    def invoke(self, *, model: str, key: str, action: AnalysisAction,
               elements: tuple[AnalysisElement, ...], timeout: float = 35.0) -> ProviderResult: ...


class CredentialStore(Protocol):
    def get(self, provider: str) -> str | None: ...
    def put(self, provider: str, secret: str) -> None: ...
    def delete(self, provider: str) -> None: ...
