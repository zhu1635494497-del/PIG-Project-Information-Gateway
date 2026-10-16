"""V2.4 human-authored experience and explicit immutable evidence links.

Revision ID: 0015_project_experience
Revises: 0014_content_search
"""

from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_project_experience"
down_revision: Union[str, None] = "0014_content_search"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_previous = import_module("migrations.versions.0014_content_search")
_actions = import_module("migrations.versions.0011_context_actions")
_OLD = _previous._OLD + _previous._NEW
_NEW = (
    "EXPERIENCE_CREATED", "EXPERIENCE_CORRECTED",
    "EXPERIENCE_CONFIRMED", "EXPERIENCE_SUPERSEDED",
)


def _event_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="processing_event_type", native_enum=False,
                   create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "experience_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.Enum("JUDGMENT", "DECISION", "LESSON", name="experience_kind",
                                   native_enum=False, create_constraint=True), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "CONFIRMED", "SUPERSEDED",
                                     name="experience_status", native_enum=False,
                                     create_constraint=True), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("current_version >= 1", name="current_version_positive"),
        sa.UniqueConstraint("id", "project_id", name="uq_experience_records_id_project"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_experience_records_project_updated", "experience_records",
                    ["project_id", "updated_at", "id"])
    op.create_table(
        "experience_versions",
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("recorded_at", sa.String(32), nullable=False),
        sa.PrimaryKeyConstraint("record_id", "version"),
        sa.UniqueConstraint("record_id", "project_id", "version",
                            name="uq_experience_versions_identity"),
        sa.CheckConstraint("version >= 1 AND length(trim(title)) > 0 "
                           "AND length(trim(body)) > 0 AND length(trim(author)) > 0",
                           name="content_valid"),
        sa.ForeignKeyConstraint(["record_id", "project_id"],
                                ["experience_records.id", "experience_records.project_id"],
                                ondelete="RESTRICT"),
    )
    op.create_table(
        "experience_state_changes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(16)),
        sa.Column("to_status", sa.Enum("DRAFT", "CONFIRMED", "SUPERSEDED",
                                        name="experience_status", native_enum=False,
                                        create_constraint=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("occurred_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["record_id", "project_id", "version"],
                                ["experience_versions.record_id", "experience_versions.project_id",
                                 "experience_versions.version"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(actor)) > 0", name="actor_not_blank"),
    )
    op.create_index("ix_experience_state_changes_record", "experience_state_changes",
                    ["record_id", "occurred_at", "id"])
    op.create_table(
        "experience_revision_links",
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("context_item_id", sa.String(36), nullable=False),
        sa.Column("context_revision_id", sa.String(36), nullable=False),
        sa.Column("role", sa.Enum("SUPPORTS", "CONTRADICTS", "BACKGROUND",
                                   name="experience_evidence_role", native_enum=False,
                                   create_constraint=True), nullable=False),
        sa.PrimaryKeyConstraint("record_id", "version", "context_revision_id"),
        sa.ForeignKeyConstraint(["record_id", "project_id", "version"],
                                ["experience_versions.record_id", "experience_versions.project_id",
                                 "experience_versions.version"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["context_revision_id", "project_id", "context_item_id"],
                                ["context_revisions.id", "context_revisions.project_id",
                                 "context_revisions.context_item_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_experience_revision_links_revision", "experience_revision_links",
                    ["project_id", "context_revision_id"])
    op.create_table(
        "experience_event_links",
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("record_id", "version", "event_id"),
        sa.ForeignKeyConstraint(["record_id", "project_id", "version"],
                                ["experience_versions.record_id", "experience_versions.project_id",
                                 "experience_versions.version"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["event_id", "project_id"],
                                ["processing_events.id", "processing_events.project_id"],
                                ondelete="RESTRICT"),
    )
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_event_enum(_OLD),
                           type_=_event_enum(_OLD + _NEW), existing_nullable=False)
    _actions._create_event_triggers()


def downgrade() -> None:
    for table in ("experience_records", "experience_versions", "experience_state_changes",
                  "experience_revision_links", "experience_event_links"):
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one():
            raise RuntimeError("downgrade would discard human experience")
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM processing_events WHERE event_type IN ("
        + ",".join(f"'{name}'" for name in _NEW) + ")"
    )).scalar_one():
        raise RuntimeError("downgrade would discard experience events")
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_event_enum(_OLD + _NEW),
                           type_=_event_enum(_OLD), existing_nullable=False)
    _actions._create_event_triggers()
    op.drop_table("experience_event_links")
    op.drop_index("ix_experience_revision_links_revision", table_name="experience_revision_links")
    op.drop_table("experience_revision_links")
    op.drop_index("ix_experience_state_changes_record", table_name="experience_state_changes")
    op.drop_table("experience_state_changes")
    op.drop_table("experience_versions")
    op.drop_index("ix_experience_records_project_updated", table_name="experience_records")
    op.drop_table("experience_records")
