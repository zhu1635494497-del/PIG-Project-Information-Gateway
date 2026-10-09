"""V2.1.2 Context Capture Core event and error vocabulary.

Revision ID: 0010_context_capture_core
Revises: 0009_project_context_foundation
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_context_capture_core"
down_revision: Union[str, None] = "0009_project_context_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CAPTURE_EVENTS = (
    "CONTEXT_CAPTURE_PREFLIGHTED", "CONTEXT_CAPTURE_STARTED",
    "CONTEXT_CAPTURE_COMPLETED", "CONTEXT_CAPTURE_FAILED",
    "CONTEXT_CAPTURE_CANCELLED", "CONTEXT_CAPTURE_BLOCKED_BY_CAPACITY",
    "CONTEXT_CONTENT_OBJECT_REUSED", "CONTEXT_CONTENT_OBJECT_PUBLISHED",
    "CONTEXT_CONTENT_OBJECT_ORPHAN_DETECTED",
    "CONTEXT_CONTENT_OBJECT_MISSING_DETECTED", "WORKSPACE_CHANGED_DURING_CAPTURE",
)
_OLD_EVENTS = (
    "PROJECT_CREATED", "PROJECT_STATUS_CHANGED", "SOURCE_REGISTERED",
    "SOURCE_VERIFICATION_STARTED", "SOURCE_VERIFIED", "SOURCE_MISSING_DETECTED",
    "SOURCE_CHANGED_DETECTED", "SOURCE_UNREADABLE_DETECTED", "NODE_DISCOVERED",
    "NODE_FORMAT_DETECTED", "NODE_QUEUED", "NODE_PROCESSING_STARTED",
    "CONTAINER_OPENED", "CHILD_DISCOVERED", "CHILD_EXTRACTED",
    "RELATIONSHIP_CREATED", "LINEAGE_UPDATED", "NODE_PROCESSING_FINISHED",
    "NODE_PROCESSING_BLOCKED", "NODE_PROCESSING_FAILED", "JOB_CREATED",
    "JOB_STARTED", "JOB_INTERRUPTED", "JOB_FINISHED", "ATTEMPT_QUEUED",
    "ATTEMPT_STARTED", "ATTEMPT_FINISHED", "ATTEMPT_FAILED",
    "ATTEMPT_INTERRUPTED", "ATTEMPT_CANCELLED", "ARTIFACT_REGISTERED",
    "ARTIFACT_VERIFIED", "ARTIFACT_INTEGRITY_FAILED",
    "ARTIFACT_VERIFICATION_INTERRUPTED", "FILE_OPEN_REQUESTED", "FILE_OPENED",
    "FILE_OPEN_DENIED", "FILE_OPEN_FAILED", "RECOVERY_STARTED",
    "RECOVERY_FINISHED", "RECOVERY_FAILED", "JOB_CANCELLED",
    "NODE_PROCESSING_INTERRUPTED", "ORPHAN_QUARANTINED",
    "MANIFEST_EXPORT_REQUESTED", "MANIFEST_EXPORTED", "MANIFEST_EXPORT_FAILED",
    "LINEAGE_INTEGRITY_FAILED", "LINEAGE_REBUILT", "IMPORT_REQUESTED",
    "IMPORT_STARTED", "IMPORT_FINISHED", "IMPORT_FAILED", "IMPORT_INTERRUPTED",
    "IMPORT_SNAPSHOT_CAPTURE_FINISHED", "SNAPSHOT_COPY_STARTED",
    "SNAPSHOT_VERIFICATION_STARTED", "SNAPSHOT_READY", "SNAPSHOT_INTEGRITY_FAILED",
    "WORKING_FILE_MATERIALIZATION_STARTED", "WORKING_FILE_MATERIALIZED",
    "WORKING_FILE_MATERIALIZATION_FAILED", "WORKING_FILE_MODIFIED",
    "WORKING_FILE_MISSING", "WORKING_FILE_UNREADABLE", "WORKING_FILE_RESTORED_CLEAN",
    "WORKING_VERSION_CAPTURED", "WORKING_FILE_ROLLED_BACK",
    "WORKSPACE_EXPORT_REQUESTED", "WORKSPACE_EXPORT_COMPLETED",
    "WORKSPACE_EXPORT_FAILED", "IMPORT_ITEM_UNDO_REQUESTED",
    "IMPORT_ITEM_UNDO_COMPLETED", "IMPORT_ITEM_UNDO_FAILED", "WORKSPACE_ITEM_ADDED",
    "WORKSPACE_ITEM_MOVED", "WORKSPACE_ITEM_DELETED", "WORKSPACE_ITEM_RESTORED",
    "PROJECT_CONTEXT_UPGRADE_REQUESTED", "PROJECT_CONTEXT_UPGRADE_STARTED",
    "PROJECT_CONTEXT_UPGRADE_COMPLETED", "PROJECT_CONTEXT_UPGRADE_FAILED",
)
_CAPTURE_ERRORS = (
    "CONTEXT_CAPTURE_SOURCE_MISSING", "CONTEXT_CAPTURE_SOURCE_UNREADABLE",
    "CONTEXT_CAPTURE_CAPACITY_BLOCKED", "CONTEXT_CAPTURE_FAILED",
    "CONTEXT_WRITE_CONFLICT", "WORKSPACE_CHANGED_DURING_CAPTURE",
)
_OLD_ERRORS = (
    "INPUT_NOT_FOUND", "INPUT_UNREADABLE", "INPUT_CHANGED_DURING_COPY",
    "INPUT_OVERLAPS_PROJECT", "DUPLICATE_INPUT", "UNSUPPORTED_INPUT_TYPE",
    "SNAPSHOT_PUBLISH_FAILED", "MAX_IMPORT_ENTRY_COUNT_EXCEEDED",
    "MAX_IMPORT_TOTAL_SIZE_EXCEEDED", "SOURCE_NOT_FOUND",
    "SOURCE_FINGERPRINT_MISMATCH", "SOURCE_OUTSIDE_BOUNDARY", "SYMLINK_BLOCKED",
    "PATH_TRAVERSAL_BLOCKED", "ABSOLUTE_PATH_BLOCKED", "DEVICE_PATH_BLOCKED",
    "INVALID_FILENAME", "PASSWORD_REQUIRED", "CORRUPTED_CONTAINER",
    "UNSUPPORTED_FORMAT", "UNSUPPORTED_FEATURE", "DEPENDENCY_UNAVAILABLE",
    "DEPENDENCY_VERSION_UNSUPPORTED", "EXTERNAL_PROCESS_TIMEOUT",
    "EXTERNAL_PROCESS_OUTPUT_EXCEEDED", "MANIFEST_SIZE_EXCEEDED",
    "MANIFEST_EXPORT_FAILED", "MAX_DEPTH_EXCEEDED", "MAX_NODE_COUNT_EXCEEDED",
    "MAX_ARCHIVE_ENTRIES_EXCEEDED", "MAX_SINGLE_FILE_SIZE_EXCEEDED",
    "MAX_TOTAL_EXPANDED_SIZE_EXCEEDED", "MAX_COMPRESSION_RATIO_EXCEEDED",
    "ARTIFACT_MISSING", "ARTIFACT_UNREADABLE", "ARTIFACT_HASH_MISMATCH",
    "OPEN_FORMAT_DENIED", "OPEN_INTEGRITY_REQUIRED", "OPEN_HANDOFF_FAILED",
    "RECOVERY_FAILED", "WORKSPACE_INTEGRITY_FAILED", "WORKING_VERSION_NOT_FOUND",
    "WORKING_VERSION_INTEGRITY_FAILED", "EXPORT_DESTINATION_INVALID",
    "EXPORT_PATH_COLLISION", "EXPORT_FAILED", "IMPORT_ITEM_NOT_UNDOABLE",
    "IMPORT_ITEM_UNDO_FAILED", "HANDLER_FAILURE", "INTERNAL_ERROR",
)


def _enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _drop_event_triggers() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_processing_events_append_only_update")
    op.execute("DROP TRIGGER IF EXISTS trg_processing_events_append_only_delete")


def _create_event_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_processing_events_append_only_update
        BEFORE UPDATE ON processing_events BEGIN
            SELECT RAISE(ABORT, 'processing events are append-only');
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_processing_events_append_only_delete
        BEFORE DELETE ON processing_events BEGIN
            SELECT RAISE(ABORT, 'processing events are append-only');
        END
    """)


def _alter(events, errors, old_events, old_errors) -> None:
    _drop_event_triggers()
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=_enum(old_events, "processing_event_type"),
            type_=_enum(events, "processing_event_type"),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "error_code",
            existing_type=_enum(old_errors, "processing_event_error_code"),
            type_=_enum(errors, "processing_event_error_code"),
            existing_nullable=True,
        )
    _create_event_triggers()
    with op.batch_alter_table("processing_attempts", schema=None) as batch_op:
        batch_op.alter_column(
            "error_code",
            existing_type=_enum(old_errors, "processing_error_code"),
            type_=_enum(errors, "processing_error_code"),
            existing_nullable=True,
        )


def upgrade() -> None:
    _alter(
        _OLD_EVENTS + _CAPTURE_EVENTS,
        _OLD_ERRORS + _CAPTURE_ERRORS,
        _OLD_EVENTS,
        _OLD_ERRORS,
    )


def downgrade() -> None:
    connection = op.get_bind()
    placeholders = ", ".join(f"'{value}'" for value in _CAPTURE_EVENTS)
    event_count = connection.execute(sa.text(
        f"SELECT COUNT(*) FROM processing_events WHERE event_type IN ({placeholders})"
    )).scalar_one()
    error_placeholders = ", ".join(f"'{value}'" for value in _CAPTURE_ERRORS)
    error_count = connection.execute(sa.text(
        "SELECT "
        f"(SELECT COUNT(*) FROM processing_events WHERE error_code IN ({error_placeholders})) + "
        f"(SELECT COUNT(*) FROM processing_attempts WHERE error_code IN ({error_placeholders}))"
    )).scalar_one()
    if event_count or error_count:
        raise RuntimeError("downgrade is disabled because it would discard V2.1.2 vocabulary")
    _alter(
        _OLD_EVENTS,
        _OLD_ERRORS,
        _OLD_EVENTS + _CAPTURE_EVENTS,
        _OLD_ERRORS + _CAPTURE_ERRORS,
    )
