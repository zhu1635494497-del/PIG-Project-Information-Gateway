"""Explicit, offline Context Pack preflight and publication workflow."""

from __future__ import annotations

import json
import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from uuid import uuid4

from pig.application.context_pack_plan_service import ContextPackPlanService
from pig.application.experience_contracts import extend_context_manifest_v2
from pig.application.contracts import (
    CancelContextPackPreflightRequest,
    RecoverInterruptedContextPackExportsRequest,
    RecoverInterruptedContextPackExportsResult,
    ExecuteContextPackExportRequest, ExecuteContextPackExportResult,
    GetContextPackExportsRequest, GetContextPackExportsResult,
    GetContextPackPlanRequest, PreflightContextPackExportRequest,
    PreflightContextPackExportResult,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationCancelled, OperationControl, OperationStage, ensure_operation_control
from pig.application.ports import ContextPackFile, ContextPackStore, ProjectDatabaseProvider
from pig.domain.context_pack_policy import ContextPackPolicy
from pig.domain.entities import ContextPackEntry, ContextPackExport, ContextPackPlacement, ContextPackSection, ProcessingEvent
from pig.domain.enums import ContextPackExportStatus, ContextPackFormat, EventSeverity, EventType
from pig.domain.exceptions import EntityNotFoundError


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ContextPackExportService:
    def __init__(
        self, *, database: ProjectDatabaseProvider, plan_service: ContextPackPlanService,
        store: ContextPackStore, policy: ContextPackPolicy = ContextPackPolicy(),
        clock: Callable[[], datetime] = _now, id_generator: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._database = database
        self._plans = plan_service
        self._store = store
        self._policy = policy
        self._clock = clock
        self._id = id_generator

    def preflight(self, request: PreflightContextPackExportRequest, *, control: OperationControl | None = None) -> PreflightContextPackExportResult:
        operation = ensure_operation_control(control)
        operation.start_stage(OperationStage.PREFLIGHT)
        operation.checkpoint()
        project_id = self._required(request.project_id)
        actor = self._required(request.actor)
        if not isinstance(request.format, ContextPackFormat):
            raise ApplicationError("INVALID_REQUEST", "Context Pack format must be DIRECTORY or ZIP")
        db = Path(request.database_path).resolve(strict=True)
        plan = self._plans.get_plan(GetContextPackPlanRequest(
            project_id=project_id, database_path=db,
            selected_item_ids=request.selected_item_ids, revision_choices=request.revision_choices,
            selected_record_ids=request.selected_record_ids,
        ))
        self._limit(plan)
        raw_target = Path(request.destination_path).expanduser()
        if not raw_target.is_absolute():
            raise ApplicationError("CONTEXT_PACK_DESTINATION_INVALID", "an absolute destination is required")
        export_id, token, now = self._id(), self._id(), self._clock()
        with self._database.unit_of_work(db) as uow:
            if uow.projects.get(project_id).context_revision != plan.context_revision:
                raise ApplicationError("CONTEXT_PACK_PLAN_STALE", "Project Context changed during preflight")
            uow.context_packs.add_export(ContextPackExport(
                id=export_id, project_id=project_id, format=request.format,
                status=ContextPackExportStatus.PENDING, destination_locator=str(raw_target),
                actor=actor, correlation_id=token, captured_context_revision=plan.context_revision,
                manifest_schema_version=plan.manifest_schema_version,
                plan_fingerprint=plan.plan_fingerprint, entry_count=len(plan.entries),
                total_bytes=plan.total_bytes, created_at=now, updated_at=now,
            ))
            self._event(uow, EventType.CONTEXT_PACK_EXPORT_REQUESTED, project_id, actor, token, export_id, new=ContextPackExportStatus.PENDING)
            uow.commit()
        try:
            target = self._store.validate_destination(db.parent, raw_target)
            files = self._files(db, project_id, plan)
            self._verify_sources(db.parent, files, operation, stage=OperationStage.PREFLIGHT)
            available, required = self._capacity(target, plan.total_bytes)
            with self._database.unit_of_work(db) as uow:
                if uow.projects.get(project_id).context_revision != plan.context_revision:
                    raise ApplicationError("CONTEXT_PACK_PLAN_STALE", "Project Context changed during preflight")
                uow.context_packs.update_export_status(export_id, ContextPackExportStatus.PENDING,
                                                       ContextPackExportStatus.PREFLIGHTED, updated_at=self._clock())
                self._event(uow, EventType.CONTEXT_PACK_EXPORT_PREFLIGHTED, project_id, actor, token, export_id,
                            old=ContextPackExportStatus.PENDING, new=ContextPackExportStatus.PREFLIGHTED,
                            details={"format": request.format.value, "entry_count": len(files), "total_bytes": plan.total_bytes,
                                     "warning_count": len(plan.warning_item_ids)})
                uow.commit()
        except BaseException as exc:
            cancelled = isinstance(exc, OperationCancelled)
            status = ContextPackExportStatus.CANCELLED_AT_SAFE_POINT if cancelled else ContextPackExportStatus.FAILED
            with self._database.unit_of_work(db) as uow:
                uow.context_packs.update_export_status(
                    export_id, ContextPackExportStatus.PENDING,
                    status, updated_at=self._clock(), finished_at=self._clock(),
                    error_code="OPERATION_CANCELLED" if cancelled else getattr(exc, "code", "CONTEXT_PACK_FAILED"),
                    error_message=self._safe_error(exc),
                )
                self._event(uow, EventType.CONTEXT_PACK_EXPORT_CANCELLED if cancelled else EventType.CONTEXT_PACK_EXPORT_FAILED, project_id, actor,
                            token, export_id, old=ContextPackExportStatus.PENDING,
                            new=status,
                            details={"error_code": "OPERATION_CANCELLED" if cancelled else getattr(exc, "code", "CONTEXT_PACK_FAILED")},
                            severity=EventSeverity.WARNING if cancelled else EventSeverity.ERROR)
                uow.commit()
            raise
        operation.complete()
        return PreflightContextPackExportResult(
            export_id=export_id, plan_token=token, plan=plan, destination_path=target,
            format=request.format, available_bytes=available, required_bytes=required,
        )

    def execute(self, request: ExecuteContextPackExportRequest, *, control: OperationControl | None = None) -> ExecuteContextPackExportResult:
        operation = ensure_operation_control(control)
        project_id = self._required(request.project_id)
        actor = self._required(request.actor)
        db = Path(request.database_path).resolve(strict=True)
        with self._database.unit_of_work(db) as uow:
            export = uow.context_packs.get_export(request.export_id)
            if export is None or export.project_id != project_id:
                raise EntityNotFoundError(f"Context Pack export not found: {request.export_id}")
            if export.actor != actor or export.correlation_id != request.plan_token:
                raise ApplicationError("CONTEXT_PACK_TOKEN_INVALID", "invalid Context Pack plan token")
            if export.status != ContextPackExportStatus.PREFLIGHTED:
                raise ApplicationError("CONTEXT_PACK_TOKEN_USED", "Context Pack plan token is no longer usable")
            uow.context_packs.update_export_status(export.id, ContextPackExportStatus.PREFLIGHTED,
                                                   ContextPackExportStatus.RUNNING, updated_at=self._clock(), started_at=self._clock())
            self._event(uow, EventType.CONTEXT_PACK_EXPORT_STARTED, project_id, actor,
                        export.correlation_id, export.id, old=ContextPackExportStatus.PREFLIGHTED,
                        new=ContextPackExportStatus.RUNNING)
            uow.commit()
        published = None
        committed = False
        try:
            operation.start_stage(OperationStage.EXPORT_PREPARATION)
            operation.checkpoint()
            plan = self._plans.get_plan(GetContextPackPlanRequest(
                project_id=project_id, database_path=db,
                selected_item_ids=request.selected_item_ids, revision_choices=request.revision_choices,
                selected_record_ids=request.selected_record_ids,
            ))
            if (plan.context_revision != export.captured_context_revision
                    or plan.plan_fingerprint != export.plan_fingerprint
                    or len(plan.entries) != export.entry_count):
                raise ApplicationError("CONTEXT_PACK_PLAN_STALE", "Context Pack selection changed after preflight")
            if plan.warning_item_ids and not request.confirm_outdated:
                raise ApplicationError("CONTEXT_PACK_CONFIRMATION_REQUIRED", "outdated Context Revisions require confirmation")
            self._limit(plan)
            target = self._store.validate_destination(db.parent, Path(export.destination_locator))
            files = self._files(db, project_id, plan)
            self._verify_sources(db.parent, files, operation, stage=OperationStage.EXPORT_PREPARATION)
            self._capacity(target, plan.total_bytes)
            readme = self._readme(plan)
            manifest = self._manifest(plan, export.id)
            published = self._store.publish(
                db.parent, target, export.id, files, readme, manifest,
                pack_format=export.format.value, chunk_size=self._policy.io_chunk_size,
                control=operation,
            )
            with self._database.unit_of_work(db) as uow:
                current = uow.projects.get(project_id)
                if current is None or current.context_revision != plan.context_revision:
                    raise ApplicationError("CONTEXT_PACK_PLAN_STALE", "Project Context changed before publication history committed")
                completed_at = self._clock()
                succeeded = uow.context_packs.update_export_status(
                    export.id, ContextPackExportStatus.RUNNING,
                    ContextPackExportStatus.SUCCEEDED, updated_at=completed_at,
                    finished_at=completed_at, published_sha256=published.sha256,
                )
                section_ids = {}
                for section in plan.sections:
                    section_id = self._id()
                    section_ids[section.source_section_id] = section_id
                    uow.context_packs.add_section(ContextPackSection(
                        id=section_id, project_id=project_id, export_id=export.id,
                        source_section_id=section.source_section_id,
                        name_snapshot=section.name, description_snapshot=section.description,
                        ordinal=section.ordinal, is_unsectioned=section.is_unsectioned,
                        created_at=completed_at,
                    ))
                for entry in plan.entries:
                    entry_id = self._id()
                    uow.context_packs.add_entry(ContextPackEntry(
                        id=entry_id, project_id=project_id, export_id=export.id,
                        context_item_id=entry.context_item_id,
                        context_revision_id=entry.context_revision_id, ordinal=entry.ordinal,
                        relative_path=entry.relative_path, display_name=entry.display_name,
                        size_bytes=entry.size_bytes, sha256=entry.sha256,
                        purpose_snapshot=entry.purpose, guidance_body_snapshot=entry.guidance_body,
                        guidance_author_snapshot=entry.guidance_author, created_at=completed_at,
                    ))
                    for ordinal, source_section_id in enumerate(entry.section_ids or (None,)):
                        uow.context_packs.add_placement(ContextPackPlacement(
                            id=self._id(), project_id=project_id, export_id=export.id,
                            entry_id=entry_id, section_id=section_ids[source_section_id],
                            ordinal=ordinal, created_at=completed_at,
                        ))
                self._event(uow, EventType.CONTEXT_PACK_EXPORT_COMPLETED, project_id, actor,
                            export.correlation_id, export.id, old=ContextPackExportStatus.RUNNING,
                            new=ContextPackExportStatus.SUCCEEDED,
                            details={"format": export.format.value, "entry_count": len(files), "sha256": published.sha256})
                uow.commit()
                committed = True
            operation.complete()
            return ExecuteContextPackExportResult(export=succeeded, destination_path=published.destination_path)
        except BaseException as exc:
            if committed:
                raise
            external_path_review_required = False
            if published is not None:
                external_path_review_required = not self._store.remove_owned_publication(
                    published.destination_path, export.id, published.sha256
                )
            cancelled = isinstance(exc, OperationCancelled)
            status = ContextPackExportStatus.CANCELLED_AT_SAFE_POINT if cancelled else ContextPackExportStatus.FAILED
            with self._database.unit_of_work(db) as uow:
                uow.context_packs.update_export_status(
                    export.id, ContextPackExportStatus.RUNNING, status,
                    updated_at=self._clock(), finished_at=self._clock(),
                    error_code=("OPERATION_CANCELLED" if cancelled else getattr(exc, "code", "CONTEXT_PACK_FAILED")),
                    error_message=self._safe_error(exc) + (
                        "; external destination requires manual review" if external_path_review_required else ""
                    ),
                )
                self._event(uow, EventType.CONTEXT_PACK_EXPORT_CANCELLED if cancelled else EventType.CONTEXT_PACK_EXPORT_FAILED,
                            project_id, actor, export.correlation_id, export.id,
                            old=ContextPackExportStatus.RUNNING, new=status,
                            details={"error_code": "OPERATION_CANCELLED" if cancelled else getattr(exc, "code", "CONTEXT_PACK_FAILED"),
                                     "external_path_review_required": external_path_review_required},
                            severity=EventSeverity.WARNING if cancelled else EventSeverity.ERROR)
                uow.commit()
            raise

    def history(self, request: GetContextPackExportsRequest) -> GetContextPackExportsResult:
        with self._database.unit_of_work(Path(request.database_path).resolve(strict=True)) as uow:
            if uow.projects.get(request.project_id) is None:
                raise EntityNotFoundError(f"project not found: {request.project_id}")
            return GetContextPackExportsResult(exports=uow.context_packs.exports_for_project(request.project_id))

    def cancel_preflight(self, request: CancelContextPackPreflightRequest) -> ContextPackExport:
        with self._database.unit_of_work(Path(request.database_path).resolve(strict=True)) as uow:
            export = uow.context_packs.get_export(request.export_id)
            if export is None or export.project_id != request.project_id:
                raise EntityNotFoundError(f"Context Pack export not found: {request.export_id}")
            if export.actor != request.actor or export.correlation_id != request.plan_token:
                raise ApplicationError("CONTEXT_PACK_TOKEN_INVALID", "invalid Context Pack plan token")
            cancelled = uow.context_packs.update_export_status(
                export.id, ContextPackExportStatus.PREFLIGHTED,
                ContextPackExportStatus.CANCELLED_AT_SAFE_POINT,
                updated_at=self._clock(), finished_at=self._clock(),
                error_code="USER_CANCELLED", error_message="user cancelled after preflight",
            )
            self._event(uow, EventType.CONTEXT_PACK_EXPORT_CANCELLED, export.project_id,
                        export.actor, export.correlation_id, export.id,
                        old=ContextPackExportStatus.PREFLIGHTED,
                        new=ContextPackExportStatus.CANCELLED_AT_SAFE_POINT,
                        details={"error_code": "USER_CANCELLED"}, severity=EventSeverity.WARNING)
            uow.commit()
            return cancelled

    def recover_interrupted(
        self, request: RecoverInterruptedContextPackExportsRequest
    ) -> RecoverInterruptedContextPackExportsResult:
        if not request.confirmed:
            raise ApplicationError("CONTEXT_PACK_CONFIRMATION_REQUIRED", "interrupted export recovery requires confirmation")
        db = Path(request.database_path).resolve(strict=True)
        external = []
        recovered = []
        with self._database.unit_of_work(db) as uow:
            for export in uow.context_packs.exports_for_project(request.project_id):
                if export.status != ContextPackExportStatus.RUNNING:
                    continue
                path = Path(export.destination_locator)
                if path.exists() or path.is_symlink():
                    external.append(path)
                uow.context_packs.update_export_status(
                    export.id, ContextPackExportStatus.RUNNING,
                    ContextPackExportStatus.FAILED,
                    updated_at=self._clock(), finished_at=self._clock(),
                    error_code="INTERRUPTED", error_message="interrupted export; inspect external destination before retry",
                )
                self._event(uow, EventType.CONTEXT_PACK_EXPORT_FAILED, request.project_id,
                            request.actor, export.correlation_id, export.id,
                            old=ContextPackExportStatus.RUNNING,
                            new=ContextPackExportStatus.FAILED,
                            details={"error_code": "INTERRUPTED", "external_path_review_required": path in external},
                            severity=EventSeverity.WARNING)
                recovered.append(export.id)
            uow.commit()
        return RecoverInterruptedContextPackExportsResult(
            recovered_export_ids=tuple(recovered), external_paths_to_review=tuple(external),
        )

    def _files(self, db: Path, project_id: str, plan) -> tuple[ContextPackFile, ...]:
        with self._database.unit_of_work(db) as uow:
            files = []
            for entry in plan.entries:
                content = uow.context.get_content_object(entry.content_object_id)
                if (content is None or content.project_id != project_id or content.sha256 != entry.sha256
                        or content.size_bytes != entry.size_bytes):
                    raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object metadata changed")
                files.append(ContextPackFile(relative_path=entry.relative_path,
                                             object_key=content.object_key,
                                             size_bytes=entry.size_bytes, sha256=entry.sha256))
            return tuple(files)

    def _verify_sources(self, project: Path, files: tuple[ContextPackFile, ...],
                        control: OperationControl, *, stage: OperationStage) -> None:
        control.start_stage(stage, total_count=len(files), total_bytes=sum(value.size_bytes for value in files))
        for entry in files:
            control.checkpoint()
            self._store.verify_source(project, entry, chunk_size=self._policy.io_chunk_size, control=control)
            control.advance(count=1, current_item=entry.relative_path)

    def _capacity(self, target: Path, total_bytes: int) -> tuple[int, int]:
        available = self._store.available_space(target)
        required = total_bytes + self._policy.metadata_reserve_bytes + self._policy.minimum_free_bytes
        if available < required:
            raise ApplicationError("CONTEXT_PACK_CAPACITY_BLOCKED", "insufficient destination capacity")
        return available, required

    def _limit(self, plan) -> None:
        if len(plan.entries) > self._policy.maximum_entries or plan.total_bytes > self._policy.maximum_total_bytes:
            raise ApplicationError("CONTEXT_PACK_LIMIT_EXCEEDED", "Context Pack exceeds configured limits")

    @staticmethod
    def _required(value: str) -> str:
        result = value.strip()
        if not result:
            raise ApplicationError("INVALID_REQUEST", "required Context Pack identity is empty")
        return result

    @staticmethod
    def _safe_error(exc: BaseException) -> str:
        return exc.message[:1000] if isinstance(exc, ApplicationError) else "Context Pack operation failed; inspect diagnostic logs"

    @staticmethod
    def _manifest(plan, export_id: str) -> bytes:
        value = {
            "schema_version": "1.0",
            "export_id": export_id,
            "project": {"id": plan.project_id, "name": plan.project_name},
            "context_revision": plan.context_revision,
            "sections": [{"id": value.source_section_id, "name": value.name,
                          "description": value.description, "ordinal": value.ordinal,
                          "unsectioned": value.is_unsectioned} for value in plan.sections],
            "entries": [{"context_item_id": value.context_item_id,
                         "context_revision_id": value.context_revision_id,
                         "relative_path": value.relative_path, "display_name": value.display_name,
                         "size_bytes": value.size_bytes, "sha256": value.sha256,
                         "section_ids": list(value.section_ids),
                         "purpose": value.purpose, "guidance_body": value.guidance_body,
                         "guidance_author": value.guidance_author,
                         "freshness_at_export": value.freshness.value} for value in plan.entries],
        }
        if plan.experience_records:
            value = extend_context_manifest_v2(
                base_manifest=value, records=plan.experience_records,
                observed_events=plan.observed_events)
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

    @staticmethod
    def _readme(plan) -> bytes:
        safe = ContextPackExportService._markdown_text
        lines = [f"# {safe(plan.project_name)}", "", "## 项目资料 / Project material", "",
                 "此包包含人工选定的固定 Context Revision；说明为用户原文，未经过 AI 翻译或总结。",
                 "This pack contains human-selected fixed Context Revisions. Human guidance is reproduced verbatim without AI translation or summary.", ""]
        for section in plan.sections:
            lines += [f"## {safe(section.name)}", ""]
            if section.description:
                lines += [safe(section.description), ""]
            entries = [entry for entry in plan.entries if (section.source_section_id in entry.section_ids if not section.is_unsectioned else not entry.section_ids)]
            if not entries:
                lines += ["（无选定文件 / No selected files）", ""]
            for entry in entries:
                lines += [f"- [{safe(entry.display_name)}]({quote(entry.relative_path, safe='/')}) — Revision `{entry.context_revision_id}`"]
                if entry.purpose:
                    lines += [f"  - 用途 / Purpose: {safe(entry.purpose)}"]
                if entry.guidance_body:
                    lines += [f"  - 人工说明 / Human guidance: {safe(entry.guidance_body)}"]
            lines.append("")
        return ("\n".join(lines).rstrip() + "\n").encode("utf-8")

    @staticmethod
    def _markdown_text(value: str) -> str:
        escaped = html.escape(value, quote=False)
        for character in ("\\", "[", "]", "*", "_", "`"):
            escaped = escaped.replace(character, "\\" + character)
        return escaped.replace("\r\n", "\n").replace("\n", "<br>")

    def _event(self, uow, kind, project_id, actor, token, export_id, *, old=None, new=None, details=None, severity=EventSeverity.INFO) -> None:
        uow.processing.append_event(ProcessingEvent(
            id=self._id(), event_type=kind, project_id=project_id, actor=actor,
            occurred_at=self._clock(), severity=severity, correlation_id=token,
            previous_status=None if old is None else old.value,
            new_status=None if new is None else new.value,
            details={"export_id": export_id, **(details or {})},
        ))
