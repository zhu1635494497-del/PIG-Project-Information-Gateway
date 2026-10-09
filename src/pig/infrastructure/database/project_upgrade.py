from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import stat

from pig.application.errors import ApplicationError
from pig.application.ports import ProjectUpgradeInspection
from pig.infrastructure.database.migrations import upgrade_database


V1_FACT_TABLES = (
    "projects",
    "import_sessions",
    "import_session_items",
    "original_snapshots",
    "original_artifacts",
    "original_snapshot_entries",
    "sources",
    "source_roots",
    "nodes",
    "artifacts",
    "node_relationships",
    "source_entry_locators",
    "node_lineage",
    "node_metadata",
    "processing_jobs",
    "processing_attempts",
    "processing_events",
    "workspace_items",
    "workspace_placements",
    "working_artifacts",
    "working_revisions",
    "recovery_runs",
    "recovery_items",
)


class SqliteProjectUpgradeStore:
    """SQLite backup and validation adapter for an explicit Project upgrade."""

    def inspect(self, database_path: Path) -> ProjectUpgradeInspection:
        path = self._regular_database(database_path)
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA query_only=ON")
            integrity_ok = self._integrity_ok(connection)
            project = connection.execute(
                "SELECT id, name, workspace_locator, model_version FROM projects "
                "WHERE singleton_key = 1"
            ).fetchone()
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            if project is None or revision is None:
                raise ApplicationError(
                    "INVALID_PROJECT_DATABASE",
                    "project database is missing identity or schema revision",
                    {"path": str(path)},
                )
            counts = {
                table_name: int(
                    connection.execute(
                        f'SELECT COUNT(*) FROM "{table_name}"'
                    ).fetchone()[0]
                )
                for table_name in V1_FACT_TABLES
            }
        return ProjectUpgradeInspection(
            project_id=str(project[0]),
            project_name=str(project[1]),
            workspace_locator=str(project[2]),
            model_version=str(project[3]),
            schema_revision=str(revision[0]),
            integrity_ok=integrity_ok,
            v1_row_counts=counts,
        )

    def backup(self, database_path: Path, *, occurred_at: datetime) -> Path:
        source_path = self._regular_database(database_path)
        backup_directory = source_path.parent / "backups" / "project-upgrade"
        backup_directory.mkdir(parents=True, exist_ok=True)
        timestamp = occurred_at.strftime("%Y%m%dT%H%M%S.%fZ")
        backup_path = backup_directory / f"pre-v2-{timestamp}-project.sqlite"
        if backup_path.exists():
            raise ApplicationError(
                "PROJECT_UPGRADE_BACKUP_COLLISION",
                "project upgrade backup path already exists",
                {"path": str(backup_path)},
            )
        with sqlite3.connect(source_path) as source, sqlite3.connect(backup_path) as target:
            source.backup(target)
        with sqlite3.connect(backup_path) as backup:
            if not self._integrity_ok(backup):
                raise ApplicationError(
                    "PROJECT_UPGRADE_BACKUP_INVALID",
                    "project upgrade backup failed integrity validation",
                    {"path": str(backup_path)},
                )
        return backup_path

    def migrate(self, database_path: Path) -> None:
        upgrade_database(self._regular_database(database_path))

    def validate(
        self,
        database_path: Path,
        *,
        expected_v1_row_counts: dict[str, int],
    ) -> ProjectUpgradeInspection:
        inspection = self.inspect(database_path)
        if not inspection.integrity_ok:
            raise ApplicationError(
                "PROJECT_UPGRADE_INTEGRITY_FAILED",
                "upgraded project database failed integrity validation",
            )
        mismatches = {
            table_name: {
                "expected": expected,
                "actual": inspection.v1_row_counts.get(table_name),
            }
            for table_name, expected in expected_v1_row_counts.items()
            if inspection.v1_row_counts.get(table_name) != expected
        }
        with sqlite3.connect(self._regular_database(database_path)) as connection:
            foreign_key_failures = connection.execute("PRAGMA foreign_key_check").fetchall()
        if mismatches or foreign_key_failures:
            raise ApplicationError(
                "PROJECT_UPGRADE_VALIDATION_FAILED",
                "upgraded project database did not preserve V1 facts",
                {
                    "row_count_mismatches": mismatches,
                    "foreign_key_failure_count": len(foreign_key_failures),
                },
            )
        return inspection

    @staticmethod
    def _integrity_ok(connection: sqlite3.Connection) -> bool:
        rows = connection.execute("PRAGMA integrity_check").fetchall()
        return rows == [("ok",)]

    @staticmethod
    def _regular_database(database_path: Path) -> Path:
        path = Path(database_path)
        try:
            value = path.lstat()
        except FileNotFoundError as exc:
            raise ApplicationError(
                "PROJECT_DATABASE_NOT_FOUND",
                "project database does not exist",
                {"path": str(path)},
            ) from exc
        if path.is_symlink() or not stat.S_ISREG(value.st_mode):
            raise ApplicationError(
                "UNSAFE_PROJECT_DATABASE",
                "project database must be a regular non-symlink file",
                {"path": str(path)},
            )
        return path.resolve(strict=True)
