from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import pytest

from pig.application.contracts import (
    LoadProjectRequest,
    PreflightProjectContextUpgradeRequest,
    UpgradeProjectContextRequest,
)
from pig.application.errors import ApplicationError
from pig.application.project_upgrade_service import (
    DEFAULT_CONTEXT_MINIMUM_FREE_BYTES,
    DEFAULT_CONTEXT_SOFT_QUOTA_BYTES,
    PROJECT_CONTEXT_SCHEMA_REVISION,
    ProjectContextUpgradeService,
)
from pig.bootstrap import create_local_application
from pig.domain.model_version import (
    PROJECT_CONTEXT_MODEL_VERSION,
    WORKBENCH_MODEL_VERSION,
)
from pig.infrastructure.database.migrations import upgrade_database
from pig.infrastructure.database.project_upgrade import SqliteProjectUpgradeStore
from pig.infrastructure.database.provider import SqlAlchemyProjectDatabase


NOW = datetime(2026, 10, 7, 10, 0, tzinfo=timezone.utc)


def _create_v1_project(project_path: Path) -> Path:
    project_path.mkdir()
    database_path = project_path / "project.sqlite"
    upgrade_database(database_path, "0008_workbench_recovery")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO projects "
            "(id, singleton_key, name, description, status, workspace_locator, "
            "model_version, created_at, updated_at, workspace_revision) "
            "VALUES (?, 1, ?, NULL, 'READY', ?, ?, ?, ?, 0)",
            (
                "v1-project",
                "V1 Project",
                project_path.resolve().as_uri(),
                WORKBENCH_MODEL_VERSION,
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )
    return database_path


def test_v1_upgrade_requires_confirmation_and_preserves_backup(tmp_path: Path) -> None:
    database_path = _create_v1_project(tmp_path / "V1 Project")
    application = create_local_application(
        tmp_path,
        clock=lambda: NOW,
        id_generator=iter(f"id-{index}" for index in range(20)).__next__,
    )

    preflight = application.preflight_project_context_upgrade(
        PreflightProjectContextUpgradeRequest(database_path=database_path)
    )
    assert preflight.requires_upgrade
    assert preflight.backup_required
    assert preflight.current_model_version == WORKBENCH_MODEL_VERSION
    assert preflight.current_schema_revision == "0008_workbench_recovery"
    assert preflight.target_schema_revision == PROJECT_CONTEXT_SCHEMA_REVISION

    with pytest.raises(ApplicationError) as load_error:
        application.load_project(LoadProjectRequest(database_path=database_path))
    assert load_error.value.code == "PROJECT_UPGRADE_REQUIRED"

    with pytest.raises(ApplicationError) as confirm_error:
        application.upgrade_project_context(
            UpgradeProjectContextRequest(
                database_path=database_path,
                actor="tester",
                confirmed=False,
            )
        )
    assert confirm_error.value.code == "PROJECT_UPGRADE_CONFIRMATION_REQUIRED"

    result = application.upgrade_project_context(
        UpgradeProjectContextRequest(
            database_path=database_path,
            actor="tester",
            confirmed=True,
        )
    )

    assert result.upgraded
    assert result.model_version == PROJECT_CONTEXT_MODEL_VERSION
    assert result.schema_revision == PROJECT_CONTEXT_SCHEMA_REVISION
    assert result.backup_path is not None and result.backup_path.is_file()
    assert result.backup_path.parent == database_path.parent / "backups" / "project-upgrade"

    with sqlite3.connect(result.backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert backup.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0008_workbench_recovery",
        )
        assert backup.execute("SELECT model_version FROM projects").fetchone() == (
            WORKBENCH_MODEL_VERSION,
        )

    loaded = application.load_project(LoadProjectRequest(database_path=database_path))
    assert loaded.project.model_version == PROJECT_CONTEXT_MODEL_VERSION
    assert loaded.project.context_revision == 0
    assert [event.event_type.value for event in loaded.events] == [
        "PROJECT_CONTEXT_UPGRADE_REQUESTED",
        "PROJECT_CONTEXT_UPGRADE_STARTED",
        "PROJECT_CONTEXT_UPGRADE_COMPLETED",
    ]
    with sqlite3.connect(database_path) as connection:
        settings = connection.execute(
            "SELECT soft_quota_bytes, minimum_free_bytes FROM context_settings"
        ).fetchone()
    assert settings == (
        DEFAULT_CONTEXT_SOFT_QUOTA_BYTES,
        DEFAULT_CONTEXT_MINIMUM_FREE_BYTES,
    )


def test_upgrade_is_idempotent_after_project_reaches_v21(tmp_path: Path) -> None:
    database_path = _create_v1_project(tmp_path / "V1 Project")
    application = create_local_application(tmp_path, clock=lambda: NOW)
    first = application.upgrade_project_context(
        UpgradeProjectContextRequest(
            database_path=database_path,
            actor="tester",
            confirmed=True,
        )
    )
    second = application.upgrade_project_context(
        UpgradeProjectContextRequest(
            database_path=database_path,
            actor="tester",
            confirmed=True,
        )
    )

    assert first.upgraded
    assert not second.upgraded
    assert second.backup_path is None
    assert not application.preflight_project_context_upgrade(
        PreflightProjectContextUpgradeRequest(database_path=database_path)
    ).requires_upgrade


def test_failed_post_migration_validation_does_not_advance_model_version(
    tmp_path: Path,
) -> None:
    class FailingValidationStore(SqliteProjectUpgradeStore):
        def validate(self, database_path, *, expected_v1_row_counts):
            raise ApplicationError(
                "PROJECT_UPGRADE_VALIDATION_FAILED",
                "injected validation failure",
            )

    database_path = _create_v1_project(tmp_path / "V1 Project")
    service = ProjectContextUpgradeService(
        database=SqlAlchemyProjectDatabase(),
        store=FailingValidationStore(),
        clock=lambda: NOW,
        id_generator=iter(f"failure-{index}" for index in range(10)).__next__,
    )

    with pytest.raises(ApplicationError) as failure:
        service.upgrade(
            UpgradeProjectContextRequest(
                database_path=database_path,
                actor="tester",
                confirmed=True,
            )
        )

    assert failure.value.code == "PROJECT_UPGRADE_VALIDATION_FAILED"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT model_version FROM projects").fetchone() == (
            WORKBENCH_MODEL_VERSION,
        )
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            PROJECT_CONTEXT_SCHEMA_REVISION,
        )
        assert connection.execute(
            "SELECT event_type FROM processing_events"
        ).fetchall() == [("PROJECT_CONTEXT_UPGRADE_FAILED",)]
    assert list((database_path.parent / "backups" / "project-upgrade").glob("*.sqlite"))
