"""Central resource limits for offline Context Pack publication."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContextPackPolicy:
    io_chunk_size: int = 1024 * 1024
    maximum_entries: int = 10000
    maximum_total_bytes: int = 100 * 1024**3
    minimum_free_bytes: int = 128 * 1024**2
    metadata_reserve_bytes: int = 8 * 1024**2

    def __post_init__(self) -> None:
        if min(
            self.io_chunk_size, self.maximum_entries, self.maximum_total_bytes,
            self.minimum_free_bytes, self.metadata_reserve_bytes,
        ) <= 0:
            raise ValueError("Context Pack resource limits must be positive")
