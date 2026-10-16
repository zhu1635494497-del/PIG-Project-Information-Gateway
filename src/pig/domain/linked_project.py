"""Facts for live-linked Projects, independent of UI, storage and parsers."""

from dataclasses import dataclass
from pathlib import Path


LINKED_MODEL_VERSION = "linked-project-1"
LINKED_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class LinkedPolicy:
    maximum_file_bytes: int = 2 * 1024 * 1024 * 1024
    minimum_free_bytes: int = 2 * 1024 * 1024 * 1024
    maximum_children: int = 500
    maximum_depth: int = 32
    chunk_bytes: int = 1024 * 1024

    def __post_init__(self):
        if min(self.maximum_file_bytes, self.maximum_children,
               self.maximum_depth, self.chunk_bytes) <= 0 or self.minimum_free_bytes < 0:
            raise ValueError("linked-project limits must be positive")


@dataclass(frozen=True, slots=True)
class LinkedProject:
    id: str
    name: str
    root: Path
    database_path: Path


@dataclass(frozen=True, slots=True)
class LinkedEntry:
    key: str
    name: str
    path: Path
    is_dir: bool
    status: str = "CURRENT"


@dataclass(frozen=True, slots=True)
class DirectoryPage:
    entries: tuple[LinkedEntry, ...]
    has_more: bool
    next_offset: int


@dataclass(frozen=True, slots=True)
class Observation:
    file_key: str
    status: str
    size: int | None
    sha256: str | None
    observed_at: str
    previous_sha256: str | None


@dataclass(frozen=True, slots=True)
class FixedRevision:
    id: str
    file_key: str
    source_path: Path
    sha256: str
    size: int
    object_key: str
    captured_at: str


@dataclass(frozen=True, slots=True)
class Experience:
    id: str
    revision_id: str
    body: str
    status: str
    author: str
    created_at: str
    confirmed_at: str | None
