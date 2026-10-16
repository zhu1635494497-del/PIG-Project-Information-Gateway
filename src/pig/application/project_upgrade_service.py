from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from pig.application.contracts import (
    PreflightProjectContextUpgradeRequest,
    PreflightProjectContextUpgradeResult,
    UpgradeProjectContextRequest,
    UpgradeProjectContextResult,
)
from pig.application.errors import ApplicationError
from pig.application.ports import ProjectDatabaseProvider, ProjectUpgradeInspection, ProjectUpgradeStore
from pig.domain.entities import ContextSettings, ProcessingEvent
from pig.domain.enums import EventSeverity, EventType
from pig.domain.model_version import (
    CURRENT_PROJECT_MODEL_VERSION,
    PROJECT_CONTEXT_MODEL_VERSION,
    WORKBENCH_MODEL_VERSION,
)


PROJECT_CONTEXT_SCHEMA_REVISION = "0017_workspace_rename_event"
PROJECT_CONTEXT_FOUNDATION_SCHEMA_REVISION = "0009_project_context_foundation"
PROJECT_CONTEXT_CAPTURE_SCHEMA_REVISION = "0010_context_capture_core"
DEFAULT_CONTEXT_SOFT_QUOTA_BYTES = 10 * 1024**3
DEFAULT_CONTEXT_MINIMUM_FREE_BYTES = 2 * 1024**3


class ProjectContextUpgradeService:
    def __init__(
        self,
        *,
        database: ProjectDatabaseProvider,
        store: ProjectUpgradeStore,
        clock: Callable[[], datetime],
        id_generator: Callable[[], str],
    ) -> None:
        self._database = database
        self._store = store
        self._clock = clock
        self._new_id = id_generator

    def preflight(
        self, request: PreflightProjectContextUpgradeRequest
    ) -> PreflightProjectContextUpgradeResult:
        inspection = self._inspect_and_validate_path(request.database_path)
        requires_upgrade = not (
            inspection.model_version == PROJECT_CONTEXT_MODEL_VERSION
            and inspection.schema_revision == PROJECT_CONTEXT_SCHEMA_REVISION
        )
        self._require_supported_source(inspection, allow_current=True)
        return PreflightProjectContextUpgradeResult(
            project_id=inspection.project_id,
            project_name=inspection.project_name,
            current_model_version=inspection.model_version,
            target_model_version=PROJECT_CONTEXT_MODEL_VERSION,
            current_schema_revision=inspection.schema_revision,
            target_schema_revision=PROJECT_CONTEXT_SCHEMA_REVISION,
            requires_upgrade=requires_upgrade,
            backup_required=requires_upgrade,
            integrity_ok=inspection.integrity_ok,
        )

    def require_ready(self, database_path: Path) -> None:
        result = self.preflight(
            PreflightProjectContextUpgradeRequest(database_path=database_path)
        )
        if result.requires_upgrade:
            raise ApplicationError(
                "PROJECT_UPGRADE_REQUIRED",
                "project requires a confirmed V2.1 context upgrade",
                {
                    "project_id": result.project_id,
                    "current_model_version": result.current_model_version,
                    "target_model_version": result.target_model_version,
                    "current_schema_revision": result.current_schema_revision,
                    "target_schema_revision": result.target_schema_revision,
                },
            )

    def upgrade(
        self, request: UpgradeProjectContextRequest
    ) -> UpgradeProjectContextResult:
        actor = request.actor.strip()
        if not actor:
            raise ApplicationError("INVALID_REQUEST", "actor must not be empty")
        inspection = self._inspect_and_validate_path(request.database_path)
        self._require_supported_source(inspection, allow_current=True)
        if (
            inspection.model_version == PROJECT_CONTEXT_MODEL_VERSION
            and inspection.schema_revision == PROJECT_CONTEXT_SCHEMA_REVISION
        ):
            return UpgradeProjectContextResult(
                project_id=inspection.project_id,
                previous_model_version=inspection.model_version,
                model_version=inspection.model_version,
                schema_revision=inspection.schema_revision,
                backup_path=None,
                upgraded=False,
            )
        if not request.confirmed:
            raise ApplicationError(
                "PROJECT_UPGRADE_CONFIRMATION_REQUIRED",
                "project upgrade requires explicit confirmation",
                {"project_id": inspection.project_id},
            )
        if not inspection.integrity_ok:
            raise ApplicationError(
                "PROJECT_UPGRADE_INTEGRITY_FAILED",
                "project database failed pre-upgrade integrity validation",
            )

        started_at = self._clock()
        backup_path = self._store.backup(
            request.database_path, occurred_at=started_at
        )
        try:
            if inspection.schema_revision != PROJECT_CONTEXT_SCHEMA_REVISION:
                self._store.migrate(request.database_path)
            migrated = self._store.validate(
                request.database_path,
                expected_v1_row_counts=inspection.v1_row_counts,
            )
            if migrated.schema_revision != PROJECT_CONTEXT_SCHEMA_REVISION:
                raise ApplicationError(
                    "PROJECT_UPGRADE_SCHEMA_MISMATCH",
                    "project database did not reach the V2.1 schema revision",
                    {"actual_schema_revision": migrated.schema_revision},
                )
            completed_at = self._clock()
            correlation_id = self._new_id()
            with self._database.unit_of_work(request.database_path) as uow:
                project = uow.projects.get(inspection.project_id)
                if project is None:
                    raise ApplicationError(
                        "PROJECT_NOT_FOUND",
                        "project identity disappeared during upgrade",
                    )
                if uow.context.get_settings(project.id) is None:
                    uow.context.add_settings(
                        ContextSettings(
                            project_id=project.id,
                            soft_quota_bytes=DEFAULT_CONTEXT_SOFT_QUOTA_BYTES,
                            minimum_free_bytes=DEFAULT_CONTEXT_MINIMUM_FREE_BYTES,
                            created_at=completed_at,
                            updated_at=completed_at,
                        )
                    )
                uow.processing.append_events(
                    (
                        self._event(
                            EventType.PROJECT_CONTEXT_UPGRADE_REQUESTED,
                            project.id,
                            actor,
                            started_at,
                            correlation_id,
                            details={"confirmed": True},
                        ),
                        self._event(
                            EventType.PROJECT_CONTEXT_UPGRADE_STARTED,
                            project.id,
                            actor,
                            started_at,
                            correlation_id,
                            details={"backup_path": str(backup_path)},
                        ),
                    )
                )
                updated = uow.projects.update_model_version(
                    project.id,
                    WORKBENCH_MODEL_VERSION,
                    PROJECT_CONTEXT_MODEL_VERSION,
                    updated_at=completed_at,
                )
                uow.processing.append_event(
                    self._event(
                        EventType.PROJECT_CONTEXT_UPGRADE_COMPLETED,
                        project.id,
                        actor,
                        completed_at,
                        correlation_id,
                        details={
                            "previous_model_version": inspection.model_version,
                            "model_version": updated.model_version,
                            "schema_revision": migrated.schema_revision,
                            "backup_path": str(backup_path),
                        },
                    )
                )
                uow.commit()
        except BaseException as exc:
            self._record_failure_best_effort(
                request.database_path,
                inspection,
                actor=actor,
                occurred_at=self._clock(),
                backup_path=backup_path,
                error_code=(exc.code if isinstance(exc, ApplicationError) else type(exc).__name__),
            )
            raise

        return UpgradeProjectContextResult(
            project_id=inspection.project_id,
            previous_model_version=inspection.model_version,
            model_version=CURRENT_PROJECT_MODEL_VERSION,
            schema_revision=PROJECT_CONTEXT_SCHEMA_REVISION,
            backup_path=backup_path,
            upgraded=True,
        )

    def _inspect_and_validate_path(self, database_path: Path) -> ProjectUpgradeInspection:
        inspection = self._store.inspect(database_path)
        actual_workspace = Path(database_path).resolve(strict=False).parent.as_uri()
        if inspection.workspace_locator != actual_workspace:
            raise ApplicationError(
                "PROJECT_DATABASE_MISMATCH",
                "database path is outside the Project workspace",
                {"project_id": inspection.project_id},
            )
        return inspection

    @staticmethod
    def _require_supported_source(
        inspection: ProjectUpgradeInspection, *, allow_current: bool
    ) -> None:
        allowed_models = {WORKBENCH_MODEL_VERSION}
        allowed_schemas = {
            "0008_workbench_recovery",
            PROJECT_CONTEXT_FOUNDATION_SCHEMA_REVISION,
            PROJECT_CONTEXT_CAPTURE_SCHEMA_REVISION,
            "0011_context_actions",
            "0012_context_pack_contract",
            "0013_context_pack_events",
            "0014_content_search",
            "0015_project_experience",
            PROJECT_CONTEXT_SCHEMA_REVISION,
        }
        if allow_current:
            allowed_models.add(PROJECT_CONTEXT_MODEL_VERSION)
        if inspection.model_version not in allowed_models:
            raise ApplicationError(
                "UNSUPPORTED_PROJECT_MODEL_VERSION",
                "project model cannot be upgraded to V2.1",
                {
                    "actual_model_version": inspection.model_version,
                    "supported_model_version": PROJECT_CONTEXT_MODEL_VERSION,
                },
            )
        if inspection.schema_revision not in allowed_schemas:
            raise ApplicationError(
                "UNSUPPORTED_PROJECT_SCHEMA_REVISION",
                "project schema cannot be upgraded to V2.1",
                {"actual_schema_revision": inspection.schema_revision},
            )
        if (
            inspection.model_version == PROJECT_CONTEXT_MODEL_VERSION
            and inspection.schema_revision in {"0008_workbench_recovery"}
        ):
            raise ApplicationError(
                "PROJECT_MODEL_SCHEMA_MISMATCH",
                "Project Context model version requires the V2.1 schema revision",
                {
                    "actual_model_version": inspection.model_version,
                    "actual_schema_revision": inspection.schema_revision,
                },
            )

    def _record_failure_best_effort(
        self,
        database_path: Path,
        inspection: ProjectUpgradeInspection,
        *,
        actor: str,
        occurred_at: datetime,
        backup_path: Path,
        error_code: str,
    ) -> None:
        try:
            current = self._store.inspect(database_path)
            if current.schema_revision != PROJECT_CONTEXT_SCHEMA_REVISION:
                return
            with self._database.unit_of_work(database_path) as uow:
                uow.processing.append_event(
                    self._event(
                        EventType.PROJECT_CONTEXT_UPGRADE_FAILED,
                        inspection.project_id,
                        actor,
                        occurred_at,
                        self._new_id(),
                        severity=EventSeverity.ERROR,
                        details={
                            "error_code": error_code,
                            "backup_path": str(backup_path),
                        },
                    )
                )
                uow.commit()
        except BaseException:
            return

    def _event(
        self,
        event_type: EventType,
        project_id: str,
        actor: str,
        occurred_at: datetime,
        correlation_id: str,
        *,
        severity: EventSeverity = EventSeverity.INFO,
        details: dict[str, object],
    ) -> ProcessingEvent:
        return ProcessingEvent(
            id=self._new_id(),
            event_type=event_type,
            project_id=project_id,
            actor=actor,
            occurred_at=occurred_at,
            severity=severity,
            correlation_id=correlation_id,
            details=details,
        )
