"""V2.3 canonical content and per-project FTS5.

Revision ID: 0014_content_search
Revises: 0013_context_pack_events
"""

from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_content_search"
down_revision: Union[str, None] = "0013_context_pack_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_previous = import_module("migrations.versions.0013_context_pack_events")
_actions = import_module("migrations.versions.0011_context_actions")
_OLD = _previous._OLD + _previous._NEW
_NEW = (
    "CONTENT_EXTRACTION_STARTED", "CONTENT_EXTRACTION_SUCCEEDED",
    "CONTENT_EXTRACTION_PARTIAL", "CONTENT_EXTRACTION_UNSUPPORTED",
    "CONTENT_EXTRACTION_FAILED", "CONTENT_EXTRACTION_CANCELLED",
    "CONTENT_INDEX_REBUILT",
)
_STATUSES = ("RUNNING", "SUCCEEDED", "PARTIAL", "UNSUPPORTED", "FAILED",
             "CANCELLED_AT_SAFE_POINT")
_LOCATORS = ("LINE", "CSV_ROW", "EMAIL_FIELD", "SHEET_CELL")


def _event_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="processing_event_type", native_enum=False, create_constraint=True)


def upgrade() -> None:
    bind = op.get_bind()
    try:
        bind.execute(sa.text("CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(value)"))
        bind.execute(sa.text("DROP TABLE temp.fts5_probe"))
    except sa.exc.DatabaseError as exc:
        raise RuntimeError("SQLite FTS5 is required for V2.3") from exc

    op.create_table(
        "extraction_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("context_revision_id", sa.String(36), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("extractor_name", sa.String(64), nullable=False),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.Enum(*_STATUSES, name="content_extraction_status",
                                     native_enum=False, create_constraint=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("finished_at", sa.String(32)),
        sa.Column("element_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(512)),
        sa.CheckConstraint("element_count >= 0", name="element_count_nonnegative"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["context_revision_id", "project_id"],
                                ["context_revisions.id", "context_revisions.project_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "project_id", name="uq_extraction_runs_id_project"),
    )
    op.create_index("ix_extraction_runs_revision_status", "extraction_runs",
                    ["project_id", "context_revision_id", "status"])
    op.create_table(
        "content_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("extraction_run_id", sa.String(36), nullable=False),
        sa.Column("context_revision_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["extraction_run_id", "project_id"],
                                ["extraction_runs.id", "extraction_runs.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["context_revision_id", "project_id"],
                                ["context_revisions.id", "context_revisions.project_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "project_id", name="uq_content_documents_id_project"),
        sa.UniqueConstraint("extraction_run_id", name="uq_content_documents_run"),
    )
    op.create_table(
        "content_elements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("locator_kind", sa.Enum(*_LOCATORS, name="content_locator_kind",
                                             native_enum=False, create_constraint=True), nullable=False),
        sa.Column("locator_value", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id", "project_id"],
                                ["content_documents.id", "content_documents.project_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_content_elements_ordinal"),
        sa.CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        sa.CheckConstraint("length(text) > 0", name="text_not_empty"),
        sa.CheckConstraint("length(locator_value) > 0", name="locator_not_empty"),
    )
    op.create_index("ix_content_elements_document_order", "content_elements", ["document_id", "ordinal"])
    op.execute("CREATE VIRTUAL TABLE content_fts USING fts5(text, content='content_elements', content_rowid='rowid')")
    op.execute("""CREATE TRIGGER content_elements_ai AFTER INSERT ON content_elements BEGIN
        INSERT INTO content_fts(rowid, text) VALUES (new.rowid, new.text);
    END""")
    op.execute("""CREATE TRIGGER content_elements_ad AFTER DELETE ON content_elements BEGIN
        INSERT INTO content_fts(content_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
    END""")
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_event_enum(_OLD),
                           type_=_event_enum(_OLD + _NEW), existing_nullable=False)
    _actions._create_event_triggers()


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT count(*) FROM extraction_runs")).scalar_one():
        raise RuntimeError("downgrade would discard canonical content")
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM processing_events WHERE event_type IN ("
        + ",".join(f"'{name}'" for name in _NEW) + ")"
    )).scalar_one():
        raise RuntimeError("downgrade would discard V2.3 events")
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_event_enum(_OLD + _NEW),
                           type_=_event_enum(_OLD), existing_nullable=False)
    _actions._create_event_triggers()
    op.execute("DROP TRIGGER content_elements_ad")
    op.execute("DROP TRIGGER content_elements_ai")
    op.execute("DROP TABLE content_fts")
    op.drop_table("content_elements")
    op.drop_table("content_documents")
    op.drop_table("extraction_runs")
