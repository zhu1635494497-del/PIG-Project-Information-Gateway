from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationCancelled, OperationControl, OperationStage
from pig.infrastructure.filesystem.context_object_store import LocalContextObjectStore


def test_context_object_store_publishes_by_hash_and_deduplicates(tmp_path: Path) -> None:
    store = LocalContextObjectStore()
    payload = b"same immutable context bytes"

    first = store.capture(tmp_path, "capture-1", lambda output: output.write(payload), maximum=1024)
    second = store.capture(tmp_path, "capture-2", lambda output: output.write(payload), maximum=1024)

    digest = hashlib.sha256(payload).hexdigest()
    assert first.sha256 == digest
    assert first.object_key == f"context/objects/{digest[:2]}/{digest}"
    assert first.path.read_bytes() == payload
    assert first.reused is False
    assert second.reused is True


def test_context_object_store_rejects_corrupt_existing_object(tmp_path: Path) -> None:
    store = LocalContextObjectStore()
    payload = b"expected"
    digest = hashlib.sha256(payload).hexdigest()
    destination = tmp_path / "context" / "objects" / digest[:2] / digest
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"corrupt!")

    with pytest.raises(ApplicationError, match="integrity|content address"):
        store.capture(tmp_path, "capture-corrupt", lambda output: output.write(payload), maximum=1024)


def test_context_object_store_inspection_reports_orphan_and_missing(tmp_path: Path) -> None:
    store = LocalContextObjectStore()
    stored = store.capture(tmp_path, "capture-scan", lambda output: output.write(b"orphan"), maximum=1024)
    missing = "context/objects/aa/" + "a" * 64

    orphans, missing_keys = store.inspect(tmp_path, known_object_keys=frozenset({missing}))

    assert orphans == (stored.object_key,)
    assert missing_keys == (missing,)


def test_context_object_store_cancellation_removes_staging_before_publish(tmp_path: Path) -> None:
    store = LocalContextObjectStore()
    control = OperationControl(
        callback=lambda snapshot: control.token.cancel() if snapshot.completed_bytes else None
    )
    control.start_stage(OperationStage.CONTEXT_CAPTURE)

    with pytest.raises(OperationCancelled):
        store.capture(
            tmp_path,
            "capture-cancel",
            lambda output: output.write(b"cancel me"),
            maximum=1024,
            control=control,
        )

    assert not (tmp_path / "context" / "objects").exists()
    assert not (tmp_path / ".staging").exists()
