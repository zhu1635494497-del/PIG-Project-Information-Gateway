from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, event, insert

from pig.application import (
    CreateProjectRequest,
    GetWorkspaceTreeRequest,
    SearchWorkspaceItemsRequest,
)
from pig.bootstrap import create_local_application
from pig.domain.enums import (
    WorkspaceItemKind,
    WorkspaceItemLifecycleStatus,
    WorkspaceMaterializationStatus,
)
from pig.infrastructure.database.engine import create_project_engine
from pig.infrastructure.database.models import (
    WorkspaceItemModel,
    WorkspacePlacementModel,
)


def _seed_flat_workspace(database_path, project_id: str, count: int) -> None:
    now = datetime.now(timezone.utc)
    items = []
    placements = []
    for index in range(count):
        item_id = f"item-{index:05d}"
        items.append(
            {
                "id": item_id,
                "project_id": project_id,
                "origin_source_node_id": None,
                "item_kind": WorkspaceItemKind.FOLDER,
                "display_name": f"folder-{index:05d}",
                "lifecycle_status": WorkspaceItemLifecycleStatus.ACTIVE,
                "materialization_status": WorkspaceMaterializationStatus.VIRTUAL,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            }
        )
        placements.append(
            {
                "workspace_item_id": item_id,
                "project_id": project_id,
                "parent_workspace_item_id": None,
                "ordinal": index,
                "previous_parent_id": None,
                "previous_ordinal": None,
                "updated_at": now,
            }
        )
    engine = create_project_engine(database_path)
    try:
        with engine.begin() as connection:
            connection.execute(insert(WorkspaceItemModel), items)
            connection.execute(insert(WorkspacePlacementModel), placements)
    finally:
        engine.dispose()


def _count_sql(action) -> tuple[object, int]:
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        return action(), len(statements)
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def test_workspace_read_model_uses_bounded_query_count(tmp_path) -> None:
    application = create_local_application(tmp_path / "projects")
    project = application.create_project(
        CreateProjectRequest(name="W10 Read Model", actor="tester")
    )
    _seed_flat_workspace(project.database_path, project.project_id, 250)

    tree, tree_query_count = _count_sql(
        lambda: application.get_workspace_tree(
            GetWorkspaceTreeRequest(
                project_id=project.project_id,
                database_path=project.database_path,
            )
        )
    )
    search, search_query_count = _count_sql(
        lambda: application.search_workspace_items(
            SearchWorkspaceItemsRequest(
                project_id=project.project_id,
                database_path=project.database_path,
                query="folder-00249",
                limit=20,
            )
        )
    )

    assert len(tree.items) == 250
    assert search.total == 1
    assert tree_query_count <= 3
    assert search_query_count <= 4
