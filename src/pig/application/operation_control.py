from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from threading import Event, RLock
from typing import Callable, Optional
from uuid import uuid4

from pig.application.errors import ApplicationError


class OperationStage(str, Enum):
    PREFLIGHT = "PREFLIGHT"
    SNAPSHOT_COPY = "SNAPSHOT_COPY"
    STRUCTURE_INSPECTION = "STRUCTURE_INSPECTION"
    EXPORT_PREPARATION = "EXPORT_PREPARATION"
    EXPORT_WRITE = "EXPORT_WRITE"
    FINALIZING = "FINALIZING"
    COMPLETED = "COMPLETED"


_STAGE_ORDER = {stage: index for index, stage in enumerate(OperationStage)}


@dataclass(frozen=True, slots=True, kw_only=True)
class OperationProgressSnapshot:
    operation_id: str
    sequence: int
    stage: OperationStage
    completed_count: int = 0
    total_count: int = 0
    completed_bytes: int = 0
    total_bytes: int = 0
    current_item: Optional[str] = None
    cancellable: bool = True
    cancellation_requested: bool = False
    warning: Optional[str] = None

    @property
    def ratio(self) -> Optional[float]:
        if self.total_bytes > 0:
            return min(1.0, self.completed_bytes / self.total_bytes)
        if self.total_count > 0:
            return min(1.0, self.completed_count / self.total_count)
        return None


class OperationCancelled(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            code="OPERATION_CANCELLED",
            message="operation was cancelled at a safe checkpoint",
        )


class CancellationToken:
    def __init__(self) -> None:
        self._requested = Event()

    @property
    def is_cancellation_requested(self) -> bool:
        return self._requested.is_set()

    def cancel(self) -> None:
        self._requested.set()

    def checkpoint(self) -> None:
        if self.is_cancellation_requested:
            raise OperationCancelled()


ProgressCallback = Callable[[OperationProgressSnapshot], None]


class OperationControl:
    """Transient progress and cooperative cancellation for one foreground action."""

    def __init__(
        self,
        *,
        operation_id: Optional[str] = None,
        callback: Optional[ProgressCallback] = None,
        token: Optional[CancellationToken] = None,
    ) -> None:
        self.operation_id = operation_id or str(uuid4())
        self.token = token or CancellationToken()
        self._callback = callback
        self._lock = RLock()
        self._latest: Optional[OperationProgressSnapshot] = None

    @property
    def latest(self) -> Optional[OperationProgressSnapshot]:
        with self._lock:
            return self._latest

    def cancel(self) -> None:
        self.token.cancel()
        with self._lock:
            if self._latest is None:
                return
            self._publish(
                replace(
                    self._latest,
                    sequence=self._latest.sequence + 1,
                    cancellation_requested=True,
                )
            )

    def checkpoint(self) -> None:
        self.token.checkpoint()

    def start_stage(
        self,
        stage: OperationStage,
        *,
        total_count: int = 0,
        total_bytes: int = 0,
        current_item: Optional[str] = None,
        cancellable: bool = True,
        warning: Optional[str] = None,
    ) -> None:
        if total_count < 0 or total_bytes < 0:
            raise ValueError("operation progress totals must be nonnegative")
        with self._lock:
            if (
                self._latest is not None
                and _STAGE_ORDER[stage] < _STAGE_ORDER[self._latest.stage]
            ):
                raise ValueError("operation stage cannot move backwards")
            sequence = 1 if self._latest is None else self._latest.sequence + 1
            same_stage = self._latest is not None and self._latest.stage == stage
            completed_count = self._latest.completed_count if same_stage else 0
            completed_bytes = self._latest.completed_bytes if same_stage else 0
            if total_count and completed_count > total_count:
                raise ValueError("operation count total cannot move below progress")
            if total_bytes and completed_bytes > total_bytes:
                raise ValueError("operation byte total cannot move below progress")
            self._publish(
                OperationProgressSnapshot(
                    operation_id=self.operation_id,
                    sequence=sequence,
                    stage=stage,
                    completed_count=completed_count,
                    total_count=total_count,
                    completed_bytes=completed_bytes,
                    total_bytes=total_bytes,
                    current_item=current_item,
                    cancellable=cancellable,
                    cancellation_requested=self.token.is_cancellation_requested,
                    warning=warning,
                )
            )

    def advance(
        self,
        *,
        count: int = 0,
        byte_count: int = 0,
        current_item: Optional[str] = None,
        warning: Optional[str] = None,
    ) -> None:
        if count < 0 or byte_count < 0:
            raise ValueError("operation progress increments must be nonnegative")
        with self._lock:
            if self._latest is None:
                raise ValueError("operation stage must start before progress advances")
            completed_count = self._latest.completed_count + count
            completed_bytes = self._latest.completed_bytes + byte_count
            if (
                self._latest.total_count
                and completed_count > self._latest.total_count
            ):
                raise ValueError("operation count progress exceeds its total")
            if (
                self._latest.total_bytes
                and completed_bytes > self._latest.total_bytes
            ):
                raise ValueError("operation byte progress exceeds its total")
            self._publish(
                replace(
                    self._latest,
                    sequence=self._latest.sequence + 1,
                    completed_count=completed_count,
                    completed_bytes=completed_bytes,
                    current_item=(
                        self._latest.current_item
                        if current_item is None
                        else current_item
                    ),
                    cancellation_requested=self.token.is_cancellation_requested,
                    warning=self._latest.warning if warning is None else warning,
                )
            )

    def update(
        self,
        *,
        current_item: Optional[str] = None,
        cancellable: Optional[bool] = None,
        warning: Optional[str] = None,
    ) -> None:
        with self._lock:
            if self._latest is None:
                raise ValueError("operation stage must start before progress updates")
            self._publish(
                replace(
                    self._latest,
                    sequence=self._latest.sequence + 1,
                    current_item=(
                        self._latest.current_item
                        if current_item is None
                        else current_item
                    ),
                    cancellable=(
                        self._latest.cancellable
                        if cancellable is None
                        else cancellable
                    ),
                    cancellation_requested=self.token.is_cancellation_requested,
                    warning=self._latest.warning if warning is None else warning,
                )
            )

    def complete(self) -> None:
        self.start_stage(OperationStage.COMPLETED, cancellable=False)

    def _publish(self, snapshot: OperationProgressSnapshot) -> None:
        self._latest = snapshot
        if self._callback is not None:
            self._callback(snapshot)


def ensure_operation_control(
    value: Optional[OperationControl],
) -> OperationControl:
    return value if value is not None else OperationControl()
