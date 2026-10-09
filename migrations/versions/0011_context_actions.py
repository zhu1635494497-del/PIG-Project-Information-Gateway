"""V2.1.3 Context Actions vocabulary and cleanup-safe event references.

Revision ID: 0011_context_actions
Revises: 0010_context_capture_core
Create Date: 2026-10-08
"""
from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_context_actions"
down_revision: Union[str, None] = "0010_context_capture_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_previous = import_module("migrations.versions.0010_context_capture_core")
_OLD_EVENTS = _previous._OLD_EVENTS + _previous._CAPTURE_EVENTS
_OLD_ERRORS = _previous._OLD_ERRORS + _previous._CAPTURE_ERRORS
_ACTION_EVENTS = (
    "CONTEXT_ITEM_PROMOTED", "CONTEXT_ITEM_REMOVED", "CONTEXT_ITEM_RESTORED",
    "CONTEXT_REVISION_ADVANCED", "CONTEXT_REVISION_PROTECTED",
    "CONTEXT_REVISION_UNPROTECTED", "CONTEXT_REVISION_CLEANUP_PREVIEWED",
    "CONTEXT_REVISION_CLEANUP_COMPLETED", "CONTEXT_REVISION_CLEANUP_FAILED",
    "CONTEXT_SECTION_CREATED", "CONTEXT_SECTION_RENAMED", "CONTEXT_SECTION_REMOVED",
    "CONTEXT_SECTION_RESTORED", "CONTEXT_SECTION_REORDERED",
    "CONTEXT_PLACEMENT_CREATED", "CONTEXT_PLACEMENT_REMOVED",
    "CONTEXT_PLACEMENT_REORDERED", "CONTEXT_ANNOTATION_CREATED",
    "CONTEXT_ANNOTATION_UPDATED", "CONTEXT_BECAME_OUTDATED",
    "CONTEXT_WRITE_CONFLICT",
)
_ACTION_ERRORS = ("CONTEXT_ACTION_INVALID", "CONTEXT_CLEANUP_PREVIEW_STALE")


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


def upgrade() -> None:
    _drop_event_triggers()
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_processing_events_context_content_object_id_context_content_objects",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_processing_events_context_revision_id_context_revisions",
            type_="foreignkey",
        )
        batch_op.alter_column(
            "event_type",
            existing_type=_enum(_OLD_EVENTS, "processing_event_type"),
            type_=_enum(_OLD_EVENTS + _ACTION_EVENTS, "processing_event_type"),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "error_code",
            existing_type=_enum(_OLD_ERRORS, "processing_event_error_code"),
            type_=_enum(_OLD_ERRORS + _ACTION_ERRORS, "processing_event_error_code"),
            existing_nullable=True,
        )
    _create_event_triggers()
    with op.batch_alter_table("processing_attempts", schema=None) as batch_op:
        batch_op.alter_column(
            "error_code",
            existing_type=_enum(_OLD_ERRORS, "processing_error_code"),
            type_=_enum(_OLD_ERRORS + _ACTION_ERRORS, "processing_error_code"),
            existing_nullable=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    event_values = ", ".join(f"'{value}'" for value in _ACTION_EVENTS)
    error_values = ", ".join(f"'{value}'" for value in _ACTION_ERRORS)
    used = connection.execute(sa.text(
        f"SELECT COUNT(*) FROM processing_events WHERE event_type IN ({event_values}) "
        f"OR error_code IN ({error_values})"
    )).scalar_one()
    if used:
        raise RuntimeError("downgrade is disabled because V2.1.3 Context Actions exist")
    _drop_event_triggers()
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=_enum(_OLD_EVENTS + _ACTION_EVENTS, "processing_event_type"),
            type_=_enum(_OLD_EVENTS, "processing_event_type"),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "error_code",
            existing_type=_enum(_OLD_ERRORS + _ACTION_ERRORS, "processing_event_error_code"),
            type_=_enum(_OLD_ERRORS, "processing_event_error_code"),
            existing_nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_processing_events_context_content_object_id_context_content_objects",
            "context_content_objects",
            ["context_content_object_id", "project_id"], ["id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_processing_events_context_revision_id_context_revisions",
            "context_revisions",
            ["context_revision_id", "project_id"], ["id", "project_id"],
            ondelete="RESTRICT",
        )
    _create_event_triggers()
    with op.batch_alter_table("processing_attempts", schema=None) as batch_op:
        batch_op.alter_column(
            "error_code",
            existing_type=_enum(_OLD_ERRORS + _ACTION_ERRORS, "processing_error_code"),
            type_=_enum(_OLD_ERRORS, "processing_error_code"),
            existing_nullable=True,
        )
