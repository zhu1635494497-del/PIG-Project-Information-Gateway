"""Record logical Workspace rename without changing Original or Working bytes.

Revision ID: 0017_workspace_rename_event
Revises: 0016_ai_analysis
"""

from importlib import import_module
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_workspace_rename_event"
down_revision: Union[str, None] = "0016_ai_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_previous = import_module("migrations.versions.0016_ai_analysis")
_actions = import_module("migrations.versions.0011_context_actions")
_OLD = _previous._OLD + _previous._NEW
_NEW = ("WORKSPACE_ITEM_RENAMED",)


def _event_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values, name="processing_event_type", native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column(
            "event_type", existing_type=_event_enum(_OLD),
            type_=_event_enum(_OLD + _NEW), existing_nullable=False,
        )
    _actions._create_event_triggers()


def downgrade() -> None:
    count = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM processing_events "
        "WHERE event_type = 'WORKSPACE_ITEM_RENAMED'"
    )).scalar_one()
    if count:
        raise RuntimeError("downgrade would discard Workspace rename events")
    _actions._drop_event_triggers()
    with op.batch_alter_table("processing_events") as batch:
        batch.alter_column(
            "event_type", existing_type=_event_enum(_OLD + _NEW),
            type_=_event_enum(_OLD), existing_nullable=False,
        )
    _actions._create_event_triggers()
