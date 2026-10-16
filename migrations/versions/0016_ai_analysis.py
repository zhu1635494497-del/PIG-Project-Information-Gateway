"""Cited AI drafts with explicit immutable input and claim relationships.

Revision ID: 0016_ai_analysis
Revises: 0015_project_experience
"""

from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_ai_analysis"
down_revision: Union[str, None] = "0015_project_experience"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_previous = import_module("migrations.versions.0015_project_experience")
_actions = import_module("migrations.versions.0011_context_actions")
_OLD = _previous._OLD + _previous._NEW
_NEW = ("AI_RUN_STARTED", "AI_RUN_SUCCEEDED", "AI_RUN_FAILED", "AI_RUN_INTERRUPTED")


def _event_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="processing_event_type", native_enum=False,
                   create_constraint=True)


def upgrade() -> None:
    op.create_table(
        "ai_analysis_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("action", sa.Enum("SUMMARY", "COMPARE", "KEY_FACTS", name="ai_action",
                                      native_enum=False, create_constraint=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("workspace_revision_at_plan", sa.Integer(), nullable=False),
        sa.Column("coverage", sa.String(20), nullable=False),
        sa.Column("status", sa.Enum("RUNNING", "SUCCEEDED", "FAILED", "INTERRUPTED",
                                      name="ai_run_status", native_enum=False,
                                      create_constraint=True), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("consented_at", sa.String(32), nullable=False),
        sa.Column("started_at", sa.String(32), nullable=False),
        sa.Column("finished_at", sa.String(32)),
        sa.Column("estimated_max_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("error_code", sa.String(80)),
        sa.CheckConstraint("coverage IN ('COMPLETE_INPUT','PARTIAL_INPUT')", name="coverage_valid"),
        sa.CheckConstraint("estimated_max_usd >= 0", name="estimate_nonnegative"),
        sa.CheckConstraint("workspace_revision_at_plan >= 0", name="workspace_revision_nonnegative"),
        sa.UniqueConstraint("id", "project_id", name="uq_ai_runs_identity"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ai_runs_project_started", "ai_analysis_runs",
                    ["project_id", "started_at", "id"])
    op.create_table(
        "ai_analysis_inputs",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("element_id", sa.String(36), nullable=False),
        sa.Column("context_revision_id", sa.String(36), nullable=False),
        sa.Column("locator_kind", sa.String(32), nullable=False),
        sa.Column("locator_value", sa.String(255), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "element_id"),
        sa.ForeignKeyConstraint(["run_id", "project_id"],
                                ["ai_analysis_runs.id", "ai_analysis_runs.project_id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["element_id"], ["content_elements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["context_revision_id", "project_id"],
                                ["context_revisions.id", "context_revisions.project_id"],
                                ondelete="RESTRICT"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_ai_inputs_order"),
    )
    op.create_index("ix_ai_inputs_revision", "ai_analysis_inputs",
                    ["project_id", "context_revision_id"])
    op.create_table(
        "ai_analysis_claims",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(200)),
        sa.Column("time", sa.String(200)),
        sa.PrimaryKeyConstraint("run_id", "ordinal"),
        sa.ForeignKeyConstraint(["run_id"], ["ai_analysis_runs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("ordinal >= 0 AND length(trim(text)) > 0", name="claim_valid"),
    )
    op.create_table(
        "ai_analysis_citations",
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("claim_ordinal", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.String(36), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "claim_ordinal", "element_id"),
        sa.ForeignKeyConstraint(["run_id", "claim_ordinal"],
                                ["ai_analysis_claims.run_id", "ai_analysis_claims.ordinal"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id", "element_id"],
                                ["ai_analysis_inputs.run_id", "ai_analysis_inputs.element_id"],
                                ondelete="RESTRICT"),
    )
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_event_enum(_OLD),
                           type_=_event_enum(_OLD + _NEW), existing_nullable=False)
    _actions._create_event_triggers()


def downgrade() -> None:
    for table in ("ai_analysis_runs", "ai_analysis_inputs", "ai_analysis_claims",
                  "ai_analysis_citations"):
        if op.get_bind().execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one():
            raise RuntimeError("downgrade would discard AI analysis history")
    if op.get_bind().execute(sa.text(
        "SELECT count(*) FROM processing_events WHERE event_type IN ("
        + ",".join(f"'{name}'" for name in _NEW) + ")"
    )).scalar_one():
        raise RuntimeError("downgrade would discard AI analysis events")
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_event_enum(_OLD + _NEW),
                           type_=_event_enum(_OLD), existing_nullable=False)
    _actions._create_event_triggers()
    op.drop_table("ai_analysis_citations")
    op.drop_table("ai_analysis_claims")
    op.drop_index("ix_ai_inputs_revision", table_name="ai_analysis_inputs")
    op.drop_table("ai_analysis_inputs")
    op.drop_index("ix_ai_runs_project_started", table_name="ai_analysis_runs")
    op.drop_table("ai_analysis_runs")
