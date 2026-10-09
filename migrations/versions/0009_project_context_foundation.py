"""V2.1 Project Context foundation schema

Revision ID: 0009_project_context_foundation
Revises: 0008_workbench_recovery
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from pig.infrastructure.database.types import UTCDateTime


revision: str = "0009_project_context_foundation"
down_revision: Union[str, None] = "0008_workbench_recovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PREVIOUS_EVENT_TYPES = (
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
    "SNAPSHOT_VERIFICATION_STARTED", "SNAPSHOT_READY",
    "SNAPSHOT_INTEGRITY_FAILED", "WORKING_FILE_MATERIALIZATION_STARTED",
    "WORKING_FILE_MATERIALIZED", "WORKING_FILE_MATERIALIZATION_FAILED",
    "WORKING_FILE_MODIFIED", "WORKING_FILE_MISSING", "WORKING_FILE_UNREADABLE",
    "WORKING_FILE_RESTORED_CLEAN", "WORKING_VERSION_CAPTURED",
    "WORKING_FILE_ROLLED_BACK", "WORKSPACE_EXPORT_REQUESTED",
    "WORKSPACE_EXPORT_COMPLETED", "WORKSPACE_EXPORT_FAILED",
    "IMPORT_ITEM_UNDO_REQUESTED", "IMPORT_ITEM_UNDO_COMPLETED",
    "IMPORT_ITEM_UNDO_FAILED", "WORKSPACE_ITEM_ADDED", "WORKSPACE_ITEM_MOVED",
    "WORKSPACE_ITEM_DELETED", "WORKSPACE_ITEM_RESTORED",
)
_UPGRADE_EVENT_TYPES = (
    "PROJECT_CONTEXT_UPGRADE_REQUESTED",
    "PROJECT_CONTEXT_UPGRADE_STARTED",
    "PROJECT_CONTEXT_UPGRADE_COMPLETED",
    "PROJECT_CONTEXT_UPGRADE_FAILED",
)
_EVENT_TYPES = _PREVIOUS_EVENT_TYPES + _UPGRADE_EVENT_TYPES


def _enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def _create_event_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_processing_events_append_only_update
        BEFORE UPDATE ON processing_events
        BEGIN
            SELECT RAISE(ABORT, 'processing events are append-only');
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_processing_events_append_only_delete
        BEFORE DELETE ON processing_events
        BEGIN
            SELECT RAISE(ABORT, 'processing events are append-only');
        END
    """)


def _create_project_triggers() -> None:
    op.execute("""
        CREATE TRIGGER trg_projects_workspace_immutable
        BEFORE UPDATE OF workspace_locator ON projects
        WHEN OLD.workspace_locator IS NOT NEW.workspace_locator
        BEGIN
            SELECT RAISE(ABORT, 'project workspace is immutable');
        END
    """)
    op.execute("""
        CREATE TRIGGER trg_projects_model_version_transition
        BEFORE UPDATE OF model_version ON projects
        WHEN OLD.model_version IS NOT NEW.model_version
          AND NOT (
              OLD.model_version = 'workbench-v1'
              AND NEW.model_version = 'project-context-v2.1'
          )
        BEGIN
            SELECT RAISE(ABORT, 'unsupported project model version transition');
        END
    """)


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_projects_workspace_immutable")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "context_revision",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.create_check_constraint(
            "context_revision_nonnegative", "context_revision >= 0"
        )
    _create_project_triggers()

    op.create_table(
        "context_settings",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("soft_quota_bytes", sa.Integer(), nullable=False),
        sa.Column("minimum_free_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("soft_quota_bytes > 0", name="soft_quota_bytes_positive"),
        sa.CheckConstraint("minimum_free_bytes > 0", name="minimum_free_bytes_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_table(
        "context_sections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "lifecycle_status",
            _enum(("ACTIVE", "REMOVED"), "context_section_lifecycle_status"),
            nullable=False,
        ),
        sa.Column("removed_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        sa.CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        sa.CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL) OR "
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL)",
            name="removed_at_matches_lifecycle",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_context_sections_id_project"),
    )
    op.create_index(
        "ix_context_sections_project_order",
        "context_sections",
        ["project_id", "lifecycle_status", "ordinal"],
    )
    op.create_table(
        "context_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_item_id", sa.String(length=36), nullable=False),
        sa.Column("title_override", sa.String(length=512), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column(
            "lifecycle_status",
            _enum(("ACTIVE", "REMOVED"), "context_item_lifecycle_status"),
            nullable=False,
        ),
        sa.Column("current_context_revision_id", sa.String(length=36), nullable=True),
        sa.Column("removed_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "title_override IS NULL OR length(trim(title_override)) > 0",
            name="title_override_not_blank",
        ),
        sa.CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL) OR "
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL)",
            name="removed_at_matches_lifecycle",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["workspace_item_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_context_revision_id", "project_id", "id"],
            ["context_revisions.id", "context_revisions.project_id", "context_revisions.context_item_id"],
            name="fk_context_items_current_revision",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_context_items_id_project"),
        sa.UniqueConstraint(
            "project_id", "workspace_item_id", name="uq_context_items_workspace_item"
        ),
    )
    op.create_index(
        "ix_context_items_project_lifecycle",
        "context_items",
        ["project_id", "lifecycle_status"],
    )
    op.create_table(
        "context_content_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column(
            "availability_status",
            _enum(
                ("STAGED", "AVAILABLE", "ORPHAN_CANDIDATE", "MISSING"),
                "context_content_object_status",
            ),
            nullable=False,
        ),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        sa.CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_canonical",
        ),
        sa.CheckConstraint("length(trim(object_key)) > 0", name="object_key_not_blank"),
        sa.CheckConstraint(
            "substr(object_key, 1, 1) <> '/' "
            "AND instr(object_key, '\\') = 0 "
            "AND instr('/' || object_key || '/', '/../') = 0",
            name="object_key_project_relative",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_context_content_objects_id_project"
        ),
        sa.UniqueConstraint(
            "project_id", "sha256", name="uq_context_content_objects_project_sha256"
        ),
        sa.UniqueConstraint(
            "project_id", "object_key", name="uq_context_content_objects_object_key"
        ),
    )
    op.create_index(
        "ix_context_content_objects_project_status",
        "context_content_objects",
        ["project_id", "availability_status"],
    )
    op.create_table(
        "context_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("context_item_id", sa.String(length=36), nullable=False),
        sa.Column("content_object_id", sa.String(length=36), nullable=True),
        sa.Column(
            "source_kind",
            _enum(("WORKING", "SOURCE"), "context_revision_source_kind"),
            nullable=False,
        ),
        sa.Column("source_working_artifact_id", sa.String(length=36), nullable=True),
        sa.Column("source_node_id", sa.String(length=36), nullable=True),
        sa.Column("captured_workspace_revision", sa.Integer(), nullable=False),
        sa.Column("source_observed_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "capture_status",
            _enum(
                ("PENDING", "CAPTURING", "READY", "FAILED", "CANCELLED_AT_SAFE_POINT"),
                "context_revision_capture_status",
            ),
            nullable=False,
        ),
        sa.Column("is_manually_protected", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("protection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("ready_at", UTCDateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint(
            "captured_workspace_revision >= 0",
            name="captured_workspace_revision_nonnegative",
        ),
        sa.CheckConstraint(
            "source_observed_sha256 IS NULL OR "
            "(length(source_observed_sha256) = 64 "
            "AND source_observed_sha256 NOT GLOB '*[^0-9a-f]*')",
            name="source_observed_sha256_canonical",
        ),
        sa.CheckConstraint(
            "(source_kind = 'WORKING' AND source_working_artifact_id IS NOT NULL "
            "AND source_node_id IS NULL) OR "
            "(source_kind = 'SOURCE' AND source_node_id IS NOT NULL "
            "AND source_working_artifact_id IS NULL)",
            name="source_kind_matches_reference",
        ),
        sa.CheckConstraint(
            "capture_status <> 'READY' OR "
            "(content_object_id IS NOT NULL AND source_observed_sha256 IS NOT NULL "
            "AND ready_at IS NOT NULL)",
            name="ready_revision_is_complete",
        ),
        sa.CheckConstraint(
            "(capture_status = 'FAILED' AND error_code IS NOT NULL "
            "AND error_message IS NOT NULL) OR capture_status <> 'FAILED'",
            name="failed_revision_has_error",
        ),
        sa.CheckConstraint(
            "(is_manually_protected = 0 AND protection_reason IS NULL) OR "
            "(is_manually_protected = 1 AND protection_reason IS NOT NULL "
            "AND length(trim(protection_reason)) > 0)",
            name="manual_protection_has_reason",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["content_object_id", "project_id"],
            ["context_content_objects.id", "context_content_objects.project_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_working_artifact_id", "project_id"],
            ["working_artifacts.id", "working_artifacts.project_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_context_revisions_id_project"),
        sa.UniqueConstraint(
            "id", "project_id", "context_item_id",
            name="uq_context_revisions_item_identity",
        ),
    )
    op.create_index(
        "ix_context_revisions_item_created",
        "context_revisions",
        ["project_id", "context_item_id", "created_at"],
    )
    op.create_table(
        "context_placements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("context_item_id", sa.String(length=36), nullable=False),
        sa.Column("context_section_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "lifecycle_status",
            _enum(("ACTIVE", "REMOVED"), "context_placement_lifecycle_status"),
            nullable=False,
        ),
        sa.Column("removed_at", UTCDateTime(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        sa.CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL) OR "
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL)",
            name="removed_at_matches_lifecycle",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_section_id", "project_id"],
            ["context_sections.id", "context_sections.project_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_context_placements_id_project"),
        sa.UniqueConstraint(
            "context_item_id", "context_section_id",
            name="uq_context_placements_item_section",
        ),
    )
    op.create_index(
        "ix_context_placements_section_order",
        "context_placements",
        ["project_id", "context_section_id", "lifecycle_status", "ordinal"],
    )
    op.create_table(
        "context_annotations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("context_item_id", sa.String(length=36), nullable=False),
        sa.Column("context_revision_id", sa.String(length=36), nullable=True),
        sa.Column(
            "kind",
            _enum(("GUIDANCE",), "context_annotation_kind"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(length=255), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.CheckConstraint("length(trim(body)) > 0", name="body_not_blank"),
        sa.CheckConstraint("length(trim(author)) > 0", name="author_not_blank"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["context_revision_id", "project_id", "context_item_id"],
            ["context_revisions.id", "context_revisions.project_id", "context_revisions.context_item_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_context_annotations_id_project"),
    )
    op.create_index(
        "ix_context_annotations_item_created",
        "context_annotations",
        ["project_id", "context_item_id", "created_at"],
    )

    op.execute("DROP TRIGGER IF EXISTS trg_processing_events_append_only_update")
    op.execute("DROP TRIGGER IF EXISTS trg_processing_events_append_only_delete")
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.alter_column(
            "event_type",
            existing_type=sa.String(length=35),
            type_=_enum(_EVENT_TYPES, "processing_event_type"),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("context_section_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("context_item_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("context_content_object_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("context_revision_id", sa.String(length=36)))
        batch_op.add_column(sa.Column("context_annotation_id", sa.String(length=36)))
        batch_op.create_foreign_key(
            "fk_processing_events_context_section_id_context_sections",
            "context_sections",
            ["context_section_id", "project_id"],
            ["id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_processing_events_context_item_id_context_items",
            "context_items",
            ["context_item_id", "project_id"],
            ["id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_processing_events_context_content_object_id_context_content_objects",
            "context_content_objects",
            ["context_content_object_id", "project_id"],
            ["id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_processing_events_context_revision_id_context_revisions",
            "context_revisions",
            ["context_revision_id", "project_id"],
            ["id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_processing_events_context_annotation_id_context_annotations",
            "context_annotations",
            ["context_annotation_id", "project_id"],
            ["id", "project_id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_processing_events_context_item_time",
            ["context_item_id", "occurred_at"],
            unique=False,
        )
    _create_event_triggers()


def downgrade() -> None:
    connection = op.get_bind()
    context_count = sum(
        connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
        for table_name in (
            "context_annotations",
            "context_placements",
            "context_revisions",
            "context_content_objects",
            "context_items",
            "context_sections",
            "context_settings",
        )
    )
    upgrade_event_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM processing_events "
            "WHERE event_type IN ("
            "'PROJECT_CONTEXT_UPGRADE_REQUESTED', "
            "'PROJECT_CONTEXT_UPGRADE_STARTED', "
            "'PROJECT_CONTEXT_UPGRADE_COMPLETED', "
            "'PROJECT_CONTEXT_UPGRADE_FAILED')"
        )
    ).scalar_one()
    if context_count or upgrade_event_count:
        raise RuntimeError(
            "downgrade is disabled because it would discard Project Context facts"
        )

    op.execute("DROP TRIGGER IF EXISTS trg_processing_events_append_only_update")
    op.execute("DROP TRIGGER IF EXISTS trg_processing_events_append_only_delete")
    with op.batch_alter_table("processing_events", schema=None) as batch_op:
        batch_op.drop_index("ix_processing_events_context_item_time")
        for name, column in (
            ("fk_processing_events_context_annotation_id_context_annotations", "context_annotation_id"),
            ("fk_processing_events_context_revision_id_context_revisions", "context_revision_id"),
            ("fk_processing_events_context_content_object_id_context_content_objects", "context_content_object_id"),
            ("fk_processing_events_context_item_id_context_items", "context_item_id"),
            ("fk_processing_events_context_section_id_context_sections", "context_section_id"),
        ):
            batch_op.drop_constraint(name, type_="foreignkey")
            batch_op.drop_column(column)
        batch_op.alter_column(
            "event_type",
            existing_type=sa.String(length=35),
            type_=_enum(_PREVIOUS_EVENT_TYPES, "processing_event_type"),
            existing_nullable=False,
        )
    _create_event_triggers()

    op.drop_index("ix_context_annotations_item_created", table_name="context_annotations")
    op.drop_table("context_annotations")
    op.drop_index("ix_context_placements_section_order", table_name="context_placements")
    op.drop_table("context_placements")
    op.drop_index("ix_context_revisions_item_created", table_name="context_revisions")
    op.drop_table("context_revisions")
    op.drop_index(
        "ix_context_content_objects_project_status",
        table_name="context_content_objects",
    )
    op.drop_table("context_content_objects")
    op.drop_index("ix_context_items_project_lifecycle", table_name="context_items")
    op.drop_table("context_items")
    op.drop_index("ix_context_sections_project_order", table_name="context_sections")
    op.drop_table("context_sections")
    op.drop_table("context_settings")

    op.execute("DROP TRIGGER IF EXISTS trg_projects_model_version_transition")
    op.execute("DROP TRIGGER IF EXISTS trg_projects_workspace_immutable")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_projects_context_revision_nonnegative"), type_="check"
        )
        batch_op.drop_column("context_revision")
    op.execute("""
        CREATE TRIGGER trg_projects_workspace_immutable
        BEFORE UPDATE OF workspace_locator, model_version ON projects
        WHEN OLD.workspace_locator IS NOT NEW.workspace_locator
          OR OLD.model_version IS NOT NEW.model_version
        BEGIN
            SELECT RAISE(ABORT, 'project workspace and model version are immutable');
        END
    """)
