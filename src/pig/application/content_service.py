from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable
from uuid import uuid4

from pig.application.content_contracts import (
    ContentSearchHit, ExtractContextRevisionsRequest, ExtractContextRevisionsResult,
    RebuildContextIndexRequest, RebuildContextIndexResult,
    SearchContextContentRequest, SearchContextContentResult,
    OpenContextRevisionRequest, OpenContextRevisionResult,
    RecoverInterruptedContentRequest, RecoverInterruptedContentResult,
)
from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationCancelled, OperationControl, OperationStage, ensure_operation_control
from pig.application.project_upgrade_service import PROJECT_CONTEXT_SCHEMA_REVISION
from pig.domain.entities import ContentDocument, ContentElement, ExtractionRun, ProcessingEvent
from pig.domain.enums import (ContentExtractionStatus, ContentLocatorKind,
                              ContextContentObjectStatus, ContextLifecycleStatus,
                              ContextRevisionCaptureStatus,
                              EventSeverity, EventType)
from pig.infrastructure.filesystem.context_object_store import LocalContextObjectStore
from pig.domain.paths import safe_filesystem_segment


EXTRACTOR_VERSION = "basic-1"
CONFIG_SHA256 = hashlib.sha256(
    b"basic-v1:input=64MiB:output=32MiB:elements=10000:chars=4000:"
    b"part=8MiB:entries=2000:email-parts=5000:timeout=45s"
).hexdigest()
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_ELEMENTS = 10_000
TIMEOUT_SECONDS = 45
_FORMAT_BY_SUFFIX = {".txt": "txt", ".csv": "csv", ".eml": "eml", ".xlsx": "xlsx"}
_SEARCH_WORD = re.compile(r"[^\s\"']+", re.UNICODE)


class ContentService:
    """Explicit fixed-Revision extraction; never reads mutable Workspace bytes."""

    def __init__(self, *, database, object_store: LocalContextObjectStore, opener,
                 clock: Callable[[], datetime] | None = None,
                 id_generator: Callable[[], str] | None = None) -> None:
        self._database = database
        self._objects = object_store
        self._opener = opener
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._new_id = id_generator or (lambda: str(uuid4()))

    def extract(self, request: ExtractContextRevisionsRequest, *,
                control: OperationControl | None = None) -> ExtractContextRevisionsResult:
        operation = ensure_operation_control(control)
        if not request.revision_ids or len(request.revision_ids) > 100 or len(set(request.revision_ids)) != len(request.revision_ids):
            raise ApplicationError("INVALID_REQUEST", "select 1 to 100 distinct Revisions")
        project_id, database_path = self._project_path(request.project_id, request.database_path)
        actor = request.actor.strip()
        if not actor:
            raise ApplicationError("INVALID_REQUEST", "actor is required")
        operation.start_stage(OperationStage.CONTENT_EXTRACTION, total_count=len(request.revision_ids))
        results = []
        for revision_id in request.revision_ids:
            operation.checkpoint()
            results.append(self._extract_one(project_id, database_path, revision_id, actor, operation))
            operation.advance(count=1)
        operation.start_stage(OperationStage.FINALIZING, cancellable=False)
        operation.start_stage(OperationStage.COMPLETED, cancellable=False)
        return ExtractContextRevisionsResult(runs=tuple(results))

    def _extract_one(self, project_id: str, database_path: Path, revision_id: str,
                     actor: str, control: OperationControl) -> ExtractionRun:
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            revision = uow.context.get_revision(revision_id)
            if (revision is None or revision.project_id != project_id or
                revision.capture_status != ContextRevisionCaptureStatus.READY or
                revision.content_object_id is None):
                raise ApplicationError("CONTENT_REVISION_NOT_READY", "selected Revision is not READY")
            item = uow.context.get_item(revision.context_item_id)
            workspace_item = None if item is None else uow.workspace.get_item(item.workspace_item_id)
            content = uow.context.get_content_object(revision.content_object_id)
            if (item is None or item.lifecycle_status != ContextLifecycleStatus.ACTIVE or
                workspace_item is None or content is None or
                content.availability_status != ContextContentObjectStatus.AVAILABLE):
                raise ApplicationError("CONTENT_SOURCE_MISSING", "Context source is unavailable")
            if revision.source_observed_sha256 != content.sha256:
                raise ApplicationError("CONTENT_SOURCE_INTEGRITY", "Revision and Context object hashes differ")
            source_node = (uow.catalog.get_node(workspace_item.origin_source_node_id)
                           if workspace_item.origin_source_node_id else None)
            source_suffix = (Path(source_node.original_name).suffix.lower()
                             if source_node is not None else "")
            fmt = _FORMAT_BY_SUFFIX.get(source_suffix) or _FORMAT_BY_SUFFIX.get(
                Path(workspace_item.display_name).suffix.lower()
            )
            previous = uow.content.latest_equivalent(
                project_id, revision_id, content.sha256, fmt or "unsupported",
                EXTRACTOR_VERSION, CONFIG_SHA256,
            )
            if previous is not None:
                self._objects.verified_path(database_path.parent, content.object_key,
                                            expected_size=content.size_bytes,
                                            expected_sha256=content.sha256)
                return previous
            if any(value.status == ContentExtractionStatus.RUNNING for value in uow.content.runs_for_revision(project_id, revision_id)):
                raise ApplicationError("CONTENT_RUN_IN_PROGRESS", "an extraction run is still RUNNING; recover it before retry")
            run = ExtractionRun(
                id=self._new_id(), project_id=project_id, context_revision_id=revision_id,
                input_sha256=content.sha256, extractor_name=fmt or "unsupported",
                extractor_version=EXTRACTOR_VERSION, config_sha256=CONFIG_SHA256,
                status=ContentExtractionStatus.RUNNING, actor=actor,
                correlation_id=control.operation_id, started_at=self._clock(),
            )
            uow.content.add_run(run)
            self._event(uow, EventType.CONTENT_EXTRACTION_STARTED, run)
            uow.commit()

        try:
            if fmt is None:
                status, code, elements = ContentExtractionStatus.UNSUPPORTED, "CONTENT_FORMAT_UNSUPPORTED", ()
            elif content.size_bytes > MAX_INPUT_BYTES:
                status, code, elements = ContentExtractionStatus.FAILED, "CONTENT_INPUT_LIMIT", ()
            else:
                source = self._objects.verified_path(database_path.parent, content.object_key,
                                                     expected_size=content.size_bytes,
                                                     expected_sha256=content.sha256)
                status, code, elements = self._run_worker(source, fmt, database_path.parent, control)
            with self._database.unit_of_work(database_path) as uow:
                self._check_project(uow, project_id, database_path)
                if status in (ContentExtractionStatus.SUCCEEDED, ContentExtractionStatus.PARTIAL):
                    document = ContentDocument(id=self._new_id(), project_id=project_id,
                        extraction_run_id=run.id, context_revision_id=revision_id, created_at=self._clock())
                    canonical = tuple(ContentElement(
                        id=self._new_id(), project_id=project_id, document_id=document.id,
                        ordinal=index, text=value["text"],
                        locator_kind=ContentLocatorKind(value["locator_kind"]),
                        locator_value=value["locator_value"],
                    ) for index, value in enumerate(elements))
                    uow.content.add_document(document, canonical)
                uow.content.finish_run(run.id, status, finished_at=self._clock(),
                                       element_count=len(elements), error_code=code,
                                       error_message=None if code is None else code)
                self._event(uow, {
                    ContentExtractionStatus.SUCCEEDED: EventType.CONTENT_EXTRACTION_SUCCEEDED,
                    ContentExtractionStatus.PARTIAL: EventType.CONTENT_EXTRACTION_PARTIAL,
                    ContentExtractionStatus.UNSUPPORTED: EventType.CONTENT_EXTRACTION_UNSUPPORTED,
                    ContentExtractionStatus.FAILED: EventType.CONTENT_EXTRACTION_FAILED,
                }[status], run, status=status, code=code, count=len(elements))
                uow.commit()
                result = uow.content.get_run(run.id)
            return result
        except BaseException as exc:
            cancelled = isinstance(exc, OperationCancelled)
            code = "OPERATION_CANCELLED" if cancelled else (
                exc.code if isinstance(exc, ApplicationError) else "CONTENT_EXTRACTOR_FAILED")
            with self._database.unit_of_work(database_path) as uow:
                status = (ContentExtractionStatus.CANCELLED_AT_SAFE_POINT if cancelled
                          else ContentExtractionStatus.FAILED)
                uow.content.finish_run(run.id, status, finished_at=self._clock(),
                                       error_code=code, error_message=code)
                self._event(uow, EventType.CONTENT_EXTRACTION_CANCELLED if cancelled
                            else EventType.CONTENT_EXTRACTION_FAILED, run, status=status, code=code)
                uow.commit()
            if cancelled:
                raise
            if isinstance(exc, ApplicationError):
                raise
            raise ApplicationError(code, "content extraction failed") from exc

    def _run_worker(self, source: Path, fmt: str, project_root: Path,
                    control: OperationControl) -> tuple[ContentExtractionStatus, str | None, tuple[dict, ...]]:
        staging_root = project_root / ".staging" / "content"
        self._objects._safe_parent(project_root, staging_root, create=True)
        temporary = Path(tempfile.mkdtemp(prefix="run-", dir=staging_root))
        target = temporary / "elements.jsonl"
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--content-worker", str(source), fmt, str(target), source.name]
        else:
            command = [sys.executable, "-m", "pig.infrastructure.content.worker",
                       str(source), fmt, str(target), source.name]
        env = os.environ.copy()
        if not getattr(sys, "frozen", False):
            package_root = str(Path(__file__).resolve().parents[2])
            env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
        process = None
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=env,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            started = time.monotonic()
            while process.poll() is None:
                control.checkpoint()
                if time.monotonic() - started > TIMEOUT_SECONDS:
                    raise ApplicationError("CONTENT_TIMEOUT", "content extraction exceeded its time budget")
                if target.exists() and target.stat().st_size > MAX_OUTPUT_BYTES:
                    raise ApplicationError("CONTENT_OUTPUT_LIMIT", "content extraction exceeded its output budget")
                time.sleep(0.1)
            stdout, _ = process.communicate(timeout=2)
            if len(stdout) > 4096:
                raise ApplicationError("CONTENT_WORKER_PROTOCOL", "content worker returned invalid status")
            try:
                outcome = json.loads(stdout.decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                raise ApplicationError("CONTENT_WORKER_PROTOCOL", "content worker returned invalid status") from exc
            if outcome.get("status") not in ("SUCCEEDED", "PARTIAL"):
                code = outcome.get("code", "CONTENT_EXTRACTOR_FAILED")
                return (ContentExtractionStatus.UNSUPPORTED if outcome.get("status") == "UNSUPPORTED"
                        else ContentExtractionStatus.FAILED), str(code)[:64], ()
            if process.returncode != 0 or not target.exists() or target.stat().st_size > MAX_OUTPUT_BYTES:
                raise ApplicationError("CONTENT_WORKER_PROTOCOL", "content worker output is incomplete")
            rows = []
            with target.open("rb") as stream:
                for raw in stream:
                    if len(rows) >= MAX_ELEMENTS or len(raw) > 20_000:
                        raise ApplicationError("CONTENT_OUTPUT_LIMIT", "content worker output is too large")
                    try:
                        value = json.loads(raw.decode("utf-8"))
                        if (not isinstance(value["text"], str) or not value["text"] or
                            len(value["text"]) > 4000 or not isinstance(value["locator_value"], str) or
                            len(value["locator_value"]) > 255):
                            raise ValueError("invalid element")
                        ContentLocatorKind(value["locator_kind"])
                    except (ValueError, KeyError, UnicodeError, TypeError) as exc:
                        raise ApplicationError("CONTENT_WORKER_PROTOCOL", "content worker element is invalid") from exc
                    rows.append(value)
            if len(rows) != outcome.get("elements"):
                raise ApplicationError("CONTENT_WORKER_PROTOCOL", "content worker element count disagrees")
            return (ContentExtractionStatus.PARTIAL if outcome.get("status") == "PARTIAL"
                    else ContentExtractionStatus.SUCCEEDED), None, tuple(rows)
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            shutil.rmtree(temporary)

    def search(self, request: SearchContextContentRequest) -> SearchContextContentResult:
        project_id, database_path = self._project_path(request.project_id, request.database_path)
        words = _SEARCH_WORD.findall(request.query.strip())
        if not words or len(words) > 8 or len(request.query) > 200:
            raise ApplicationError("INVALID_REQUEST", "search requires 1 to 8 terms, up to 200 characters")
        if request.limit < 1 or request.limit > 100 or request.offset < 0:
            raise ApplicationError("INVALID_REQUEST", "invalid search page")
        expression = " AND ".join('"' + word.replace('"', '""') + '"' for word in words)
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            if re.search(r"[\u3400-\u9fff]", request.query) and len(words) == 1:
                rows, total = uow.content.search_cjk_substring(
                    project_id, words[0], limit=request.limit, offset=request.offset,
                    revision_id=request.revision_id,
                )
            else:
                rows, total = uow.content.search(project_id, expression, limit=request.limit,
                                                  offset=request.offset, revision_id=request.revision_id)
        return SearchContextContentResult(
            hits=tuple(ContentSearchHit(**row) for row in rows), total=total,
        )

    def runs_for_revision(self, project_id: str, database_path: Path,
                          revision_id: str) -> tuple[ExtractionRun, ...]:
        project_id, database_path = self._project_path(project_id, database_path)
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            revision = uow.context.get_revision(revision_id)
            if revision is None or revision.project_id != project_id:
                raise ApplicationError("CONTENT_REVISION_NOT_FOUND", "Revision not found")
            return tuple(uow.content.runs_for_revision(project_id, revision_id))

    def runs_for_item(self, project_id: str, database_path: Path,
                      context_item_id: str) -> tuple[ExtractionRun, ...]:
        project_id, database_path = self._project_path(project_id, database_path)
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            item = uow.context.get_item(context_item_id)
            if item is None or item.project_id != project_id:
                raise ApplicationError("CONTENT_ITEM_NOT_FOUND", "Context Item not found")
            return tuple(uow.content.runs_for_item(project_id, context_item_id))

    def rebuild_index(self, request: RebuildContextIndexRequest) -> RebuildContextIndexResult:
        project_id, database_path = self._project_path(request.project_id, request.database_path)
        actor = request.actor.strip()
        if not actor:
            raise ApplicationError("INVALID_REQUEST", "actor is required")
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            count = uow.content.rebuild_index()
            uow.processing.append_event(ProcessingEvent(
                id=self._new_id(), event_type=EventType.CONTENT_INDEX_REBUILT,
                project_id=project_id, actor=actor, occurred_at=self._clock(),
                severity=EventSeverity.INFO, correlation_id=self._new_id(),
                details={"element_count": count},
            ))
            uow.commit()
        return RebuildContextIndexResult(element_count=count)

    def open_revision(self, request: OpenContextRevisionRequest) -> OpenContextRevisionResult:
        project_id, database_path = self._project_path(request.project_id, request.database_path)
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            revision = uow.context.get_revision(request.revision_id)
            if (revision is None or revision.project_id != project_id or
                revision.capture_status != ContextRevisionCaptureStatus.READY or
                revision.content_object_id is None):
                raise ApplicationError("CONTENT_REVISION_NOT_READY", "selected Revision is not READY")
            item = uow.context.get_item(revision.context_item_id)
            workspace_item = None if item is None else uow.workspace.get_item(item.workspace_item_id)
            content = uow.context.get_content_object(revision.content_object_id)
            if workspace_item is None or content is None or content.availability_status != ContextContentObjectStatus.AVAILABLE:
                raise ApplicationError("CONTENT_SOURCE_MISSING", "Context source is unavailable")
            if revision.source_observed_sha256 != content.sha256:
                raise ApplicationError("CONTENT_SOURCE_INTEGRITY", "Revision and Context object hashes differ")
            source_node = (uow.catalog.get_node(workspace_item.origin_source_node_id)
                           if workspace_item.origin_source_node_id else None)
            filename = safe_filesystem_segment(
                source_node.original_name if source_node is not None else workspace_item.display_name
            )
            if Path(filename).suffix.lower() not in _FORMAT_BY_SUFFIX:
                raise ApplicationError("CONTENT_PREVIEW_UNSUPPORTED", "this file type cannot be opened from content search")
        source = self._objects.verified_path(database_path.parent, content.object_key,
                                            expected_size=content.size_bytes,
                                            expected_sha256=content.sha256)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,127}", revision.id):
            raise ApplicationError("UNSAFE_WORKSPACE", "invalid Revision identity for preview")
        preview_dir = database_path.parent / "context" / "previews" / revision.id
        self._objects._safe_parent(database_path.parent, preview_dir, create=True)
        preview = preview_dir / filename
        if preview.exists():
            value = preview.lstat()
            if not stat.S_ISREG(value.st_mode) or value.st_size != content.size_bytes:
                raise ApplicationError("CONTENT_PREVIEW_CHANGED", "existing preview is not the fixed Revision")
            digest = hashlib.sha256()
            with preview.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != content.sha256:
                raise ApplicationError("CONTENT_PREVIEW_CHANGED", "existing preview was edited; it will not be overwritten")
        else:
            temporary = preview_dir / (".pending-" + self._new_id())
            try:
                digest = hashlib.sha256()
                size = 0
                with source.open("rb") as readable, temporary.open("xb") as writable:
                    for chunk in iter(lambda: readable.read(1024 * 1024), b""):
                        writable.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    writable.flush()
                    os.fsync(writable.fileno())
                if digest.hexdigest() != content.sha256 or size != content.size_bytes:
                    raise ApplicationError("CONTENT_PREVIEW_INTEGRITY", "preview copy failed verification")
                temporary.rename(preview)
                preview.chmod(0o444)
            finally:
                temporary.unlink(missing_ok=True)
        self._opener.open(preview)
        return OpenContextRevisionResult(preview_path=preview, context_revision_id=revision.id)

    def recover_interrupted(self, request: RecoverInterruptedContentRequest) -> RecoverInterruptedContentResult:
        if not request.confirmed_no_active_extraction:
            raise ApplicationError("CONTENT_RECOVERY_CONFIRMATION_REQUIRED",
                                   "confirm that no extraction is still running")
        project_id, database_path = self._project_path(request.project_id, request.database_path)
        actor = request.actor.strip()
        if not actor:
            raise ApplicationError("INVALID_REQUEST", "actor is required")
        with self._database.unit_of_work(database_path) as uow:
            self._check_project(uow, project_id, database_path)
            running = uow.content.running_runs(project_id)
            for run in running:
                uow.content.finish_run(run.id, ContentExtractionStatus.FAILED,
                                       finished_at=self._clock(), error_code="CONTENT_INTERRUPTED",
                                       error_message="CONTENT_INTERRUPTED")
                self._event(uow, EventType.CONTENT_EXTRACTION_FAILED, run,
                            status=ContentExtractionStatus.FAILED, code="CONTENT_INTERRUPTED")
            uow.commit()
        return RecoverInterruptedContentResult(tuple(run.id for run in running))

    def _event(self, uow, kind: EventType, run: ExtractionRun, *,
               status: ContentExtractionStatus | None = None, code: str | None = None,
               count: int = 0) -> None:
        uow.processing.append_event(ProcessingEvent(
            id=self._new_id(), event_type=kind, project_id=run.project_id,
            actor=run.actor, occurred_at=self._clock(), severity=(
                EventSeverity.ERROR if status == ContentExtractionStatus.FAILED else EventSeverity.INFO),
            correlation_id=run.correlation_id, context_revision_id=run.context_revision_id,
            new_status=None if status is None else status.value,
            details={"run_id": run.id, "element_count": count,
                     "error_code": code, "extractor": run.extractor_name},
        ))

    @staticmethod
    def _project_path(project_id: str, database_path: Path) -> tuple[str, Path]:
        if not project_id.strip():
            raise ApplicationError("INVALID_REQUEST", "project_id is required")
        path = Path(database_path).resolve(strict=True)
        return project_id, path

    @staticmethod
    def _check_project(uow, project_id: str, database_path: Path) -> None:
        project = uow.projects.get(project_id)
        if project is None or project.workspace_locator != database_path.parent.as_uri():
            raise ApplicationError("PROJECT_DATABASE_MISMATCH", "project identity or path differs")
        if uow.content.schema_revision() != PROJECT_CONTEXT_SCHEMA_REVISION:
            raise ApplicationError("PROJECT_UPGRADE_REQUIRED", "project must be upgraded before content actions")
