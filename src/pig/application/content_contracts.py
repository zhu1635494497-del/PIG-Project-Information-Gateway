from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pig.domain.entities import ExtractionRun


@dataclass(frozen=True, slots=True)
class ExtractContextRevisionsRequest:
    project_id: str
    database_path: Path
    revision_ids: tuple[str, ...]
    actor: str


@dataclass(frozen=True, slots=True)
class ExtractContextRevisionsResult:
    runs: tuple[ExtractionRun, ...]


@dataclass(frozen=True, slots=True)
class SearchContextContentRequest:
    project_id: str
    database_path: Path
    query: str
    revision_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ContentSearchHit:
    element_id: str
    context_item_id: str
    context_revision_id: str
    title: str
    snippet: str
    locator_kind: str
    locator_value: str


@dataclass(frozen=True, slots=True)
class SearchContextContentResult:
    hits: tuple[ContentSearchHit, ...]
    total: int


@dataclass(frozen=True, slots=True)
class RebuildContextIndexRequest:
    project_id: str
    database_path: Path
    actor: str


@dataclass(frozen=True, slots=True)
class RebuildContextIndexResult:
    element_count: int


@dataclass(frozen=True, slots=True)
class OpenContextRevisionRequest:
    project_id: str
    database_path: Path
    revision_id: str


@dataclass(frozen=True, slots=True)
class OpenContextRevisionResult:
    preview_path: Path
    context_revision_id: str


@dataclass(frozen=True, slots=True)
class RecoverInterruptedContentRequest:
    project_id: str
    database_path: Path
    actor: str
    confirmed_no_active_extraction: bool


@dataclass(frozen=True, slots=True)
class RecoverInterruptedContentResult:
    recovered_run_ids: tuple[str, ...]
