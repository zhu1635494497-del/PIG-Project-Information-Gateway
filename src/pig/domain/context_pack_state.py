"""Context Pack export state-transition invariant."""

from pig.domain.enums import ContextPackExportStatus as Status
from pig.domain.exceptions import InvariantViolationError


_NEXT = {
    Status.PENDING: frozenset({Status.PREFLIGHTED, Status.FAILED, Status.CANCELLED_AT_SAFE_POINT}),
    Status.PREFLIGHTED: frozenset({Status.RUNNING, Status.FAILED, Status.CANCELLED_AT_SAFE_POINT}),
    Status.RUNNING: frozenset({Status.SUCCEEDED, Status.FAILED, Status.CANCELLED_AT_SAFE_POINT}),
    Status.SUCCEEDED: frozenset(),
    Status.FAILED: frozenset(),
    Status.CANCELLED_AT_SAFE_POINT: frozenset(),
}


def require_export_transition(previous: Status, next_status: Status) -> None:
    if next_status not in _NEXT[previous]:
        raise InvariantViolationError(f"invalid Context Pack transition: {previous.value} -> {next_status.value}")
