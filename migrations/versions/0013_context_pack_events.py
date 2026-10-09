"""V2.2 Context Pack structured event vocabulary.

Revision ID: 0013_context_pack_events
Revises: 0012_context_pack_contract
Create Date: 2026-10-09
"""

from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_context_pack_events"
down_revision: Union[str, None] = "0012_context_pack_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_actions = import_module("migrations.versions.0011_context_actions")
_OLD = _actions._OLD_EVENTS + _actions._ACTION_EVENTS
_NEW = (
    "CONTEXT_PACK_EXPORT_REQUESTED", "CONTEXT_PACK_EXPORT_PREFLIGHTED",
    "CONTEXT_PACK_EXPORT_STARTED", "CONTEXT_PACK_EXPORT_COMPLETED",
    "CONTEXT_PACK_EXPORT_FAILED", "CONTEXT_PACK_EXPORT_CANCELLED",
)


def _enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="processing_event_type", native_enum=False, create_constraint=True)


def _triggers() -> None:
    _actions._create_event_triggers()


def upgrade() -> None:
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_enum(_OLD), type_=_enum(_OLD + _NEW), existing_nullable=False)
    _triggers()


def downgrade() -> None:
    names = ", ".join(f"'{value}'" for value in _NEW)
    if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM processing_events WHERE event_type IN ({names})")).scalar_one():
        raise RuntimeError("downgrade is disabled because Context Pack events exist")
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column("event_type", existing_type=_enum(_OLD + _NEW), type_=_enum(_OLD), existing_nullable=False)
    _triggers()
