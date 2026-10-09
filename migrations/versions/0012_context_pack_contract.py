"""V2.2.1 Context Pack export contract and relational history.

Revision ID: 0012_context_pack_contract
Revises: 0011_context_actions
Create Date: 2026-10-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from pig.infrastructure.database.types import UTCDateTime


revision: str = "0012_context_pack_contract"
down_revision: Union[str, None] = "0011_context_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(values: tuple[str, ...], name: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "context_pack_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("format", _enum(("DIRECTORY", "ZIP"), "context_pack_format"), nullable=False),
        sa.Column("status", _enum(("PENDING", "PREFLIGHTED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED_AT_SAFE_POINT"), "context_pack_export_status"), nullable=False),
        sa.Column("destination_locator", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("captured_context_revision", sa.Integer(), nullable=False),
        sa.Column("manifest_schema_version", sa.String(32), nullable=False),
        sa.Column("plan_fingerprint", sa.String(64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
        sa.Column("started_at", UTCDateTime()),
        sa.Column("finished_at", UTCDateTime()),
        sa.Column("published_sha256", sa.String(64)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("id", "project_id", name="uq_context_pack_exports_identity"),
        sa.CheckConstraint("captured_context_revision >= 0", name="context_revision_nonnegative"),
        sa.CheckConstraint("entry_count >= 0 AND total_bytes >= 0", name="counts_nonnegative"),
        sa.CheckConstraint("length(trim(destination_locator)) > 0", name="destination_not_blank"),
        sa.CheckConstraint("length(plan_fingerprint) = 64 AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'", name="fingerprint_canonical"),
        sa.CheckConstraint("published_sha256 IS NULL OR (length(published_sha256) = 64 AND published_sha256 NOT GLOB '*[^0-9a-f]*')", name="published_sha256_canonical"),
        sa.CheckConstraint("status <> 'SUCCEEDED' OR (finished_at IS NOT NULL AND published_sha256 IS NOT NULL)", name="success_has_publication"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_context_pack_exports_project_created", "context_pack_exports", ["project_id", "created_at"])

    op.create_table(
        "context_pack_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("export_id", sa.String(36), nullable=False),
        sa.Column("context_item_id", sa.String(36), nullable=False),
        sa.Column("context_revision_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("purpose_snapshot", sa.Text()),
        sa.Column("guidance_body_snapshot", sa.Text()),
        sa.Column("guidance_author_snapshot", sa.String(255)),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("id", "project_id", "export_id", name="uq_context_pack_entries_identity"),
        sa.UniqueConstraint("export_id", "context_item_id", name="uq_context_pack_entries_item"),
        sa.UniqueConstraint("export_id", "ordinal", name="uq_context_pack_entries_ordinal"),
        sa.UniqueConstraint("export_id", "relative_path", name="uq_context_pack_entries_path"),
        sa.CheckConstraint("ordinal >= 0 AND size_bytes >= 0", name="size_and_ordinal_nonnegative"),
        sa.CheckConstraint("length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="sha256_canonical"),
        sa.CheckConstraint("substr(relative_path, 1, 6) = 'files/' AND instr(relative_path, '\\') = 0 AND instr('/' || relative_path || '/', '/../') = 0", name="relative_path_safe"),
        sa.ForeignKeyConstraint(["export_id", "project_id"], ["context_pack_exports.id", "context_pack_exports.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["context_revision_id", "project_id", "context_item_id"], ["context_revisions.id", "context_revisions.project_id", "context_revisions.context_item_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_context_pack_entries_revision", "context_pack_entries", ["project_id", "context_revision_id"])

    op.create_table(
        "context_pack_sections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("export_id", sa.String(36), nullable=False),
        sa.Column("source_section_id", sa.String(36)),
        sa.Column("name_snapshot", sa.String(255), nullable=False),
        sa.Column("description_snapshot", sa.Text()),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("is_unsectioned", sa.Boolean(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("id", "project_id", "export_id", name="uq_context_pack_sections_identity"),
        sa.UniqueConstraint("export_id", "source_section_id", name="uq_context_pack_sections_source"),
        sa.UniqueConstraint("export_id", "ordinal", name="uq_context_pack_sections_ordinal"),
        sa.CheckConstraint("ordinal >= 0 AND length(trim(name_snapshot)) > 0", name="section_valid"),
        sa.CheckConstraint("(is_unsectioned = 1 AND source_section_id IS NULL) OR (is_unsectioned = 0 AND source_section_id IS NOT NULL)", name="unsectioned_matches_source"),
        sa.ForeignKeyConstraint(["export_id", "project_id"], ["context_pack_exports.id", "context_pack_exports.project_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_section_id", "project_id"], ["context_sections.id", "context_sections.project_id"], ondelete="RESTRICT"),
    )
    op.create_index("uq_context_pack_sections_one_unsectioned", "context_pack_sections", ["export_id"], unique=True, sqlite_where=sa.text("is_unsectioned = 1"))

    op.create_table(
        "context_pack_placements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("export_id", sa.String(36), nullable=False),
        sa.Column("entry_id", sa.String(36), nullable=False),
        sa.Column("section_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.UniqueConstraint("export_id", "entry_id", "section_id", name="uq_context_pack_placements_entry_section"),
        sa.CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        sa.ForeignKeyConstraint(["entry_id", "project_id", "export_id"], ["context_pack_entries.id", "context_pack_entries.project_id", "context_pack_entries.export_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["section_id", "project_id", "export_id"], ["context_pack_sections.id", "context_pack_sections.project_id", "context_pack_sections.export_id"], ondelete="RESTRICT"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.execute(sa.text("SELECT COUNT(*) FROM context_pack_exports")).scalar_one()
    if count:
        raise RuntimeError("downgrade is disabled because Context Pack export history exists")
    op.drop_table("context_pack_placements")
    op.drop_index("uq_context_pack_sections_one_unsectioned", table_name="context_pack_sections")
    op.drop_table("context_pack_sections")
    op.drop_index("ix_context_pack_entries_revision", table_name="context_pack_entries")
    op.drop_table("context_pack_entries")
    op.drop_index("ix_context_pack_exports_project_created", table_name="context_pack_exports")
    op.drop_table("context_pack_exports")
