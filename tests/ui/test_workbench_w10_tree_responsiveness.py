from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QHeaderView

from pig.domain.enums import WorkspaceItemKind, WorkspaceMaterializationStatus
from pig.ui.main_window import WorkspaceTree, WorkspaceTreeModel


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _view(item_id: str, *, parent_id: str | None, ordinal: int):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        item=SimpleNamespace(
            id=item_id,
            display_name=f"文件-{ordinal}.txt",
            item_kind=WorkspaceItemKind.FILE,
            materialization_status=WorkspaceMaterializationStatus.VIRTUAL,
            created_at=now,
            updated_at=now,
        ),
        placement=SimpleNamespace(
            parent_workspace_item_id=parent_id,
            ordinal=ordinal,
        ),
        source_node=None,
        working_artifact=None,
        workspace_path=f"目录/{ordinal}.txt",
    )


def test_tree_model_caches_icons_across_repaints(qt_app) -> None:
    calls = 0

    def icon_provider(_view):
        nonlocal calls
        calls += 1
        return QIcon()

    model = WorkspaceTreeModel(icon_provider)
    model.set_views((_view("item-1", parent_id=None, ordinal=0),))
    index = model.index(0, 0)

    for _ in range(100):
        model.data(index, Qt.ItemDataRole.DisplayRole)
        model.data(index, Qt.ItemDataRole.DecorationRole)

    assert calls == 1


def test_tree_model_keeps_constant_time_row_lookup(qt_app) -> None:
    model = WorkspaceTreeModel()
    model.set_views(
        _view(f"item-{ordinal}", parent_id=None, ordinal=ordinal)
        for ordinal in range(10_000)
    )

    assert model.index_for_id("item-9999").row() == 9_999
    assert model._row_by_id["item-9999"] == 9_999


def test_workspace_tree_uses_bounded_header_sizing_and_pixel_scroll(qt_app) -> None:
    tree = WorkspaceTree()

    assert tree.header().sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert tree.header().sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert tree.header().sectionResizeMode(3) == QHeaderView.ResizeMode.Interactive
    assert (
        tree.verticalScrollMode()
        == tree.ScrollMode.ScrollPerPixel
    )


def test_workspace_tree_scrolls_10k_rows_without_eager_repaint(qt_app) -> None:
    icon_calls = 0

    def icon_provider(_view):
        nonlocal icon_calls
        icon_calls += 1
        return QIcon()

    tree = WorkspaceTree(icon_provider=icon_provider)
    tree.resize(900, 600)
    tree.set_views(
        _view(f"item-{ordinal}", parent_id=None, ordinal=ordinal)
        for ordinal in range(10_000)
    )
    tree.show()
    qt_app.processEvents()

    scrollbar = tree.verticalScrollBar()
    maximum = scrollbar.maximum()
    started = time.perf_counter()
    for step in range(201):
        scrollbar.setValue(min(maximum, step * 30))
        qt_app.processEvents()
    elapsed = time.perf_counter() - started
    tree.close()

    assert maximum > 0
    assert elapsed / 201 < 0.025
    assert icon_calls < 1_000
