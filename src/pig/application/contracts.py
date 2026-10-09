from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from pig.domain.entities import (
    Artifact,
    ContextAnnotation,
    ContextPackExport,
    ContextItem,
    ContextPlacement,
    ContextRevision,
    ContextSection,
    LineageRecord,
    Node,
    NodeMetadata,
    ProcessingEvent,
    Project,
    RecoveryItem,
    RecoveryRun,
    Source,
    WorkingArtifact,
    WorkingRevision,
    WorkspaceItem,
    WorkspacePlacement,
)
from pig.domain.enums import (
    ContextPackFormat,
    ContextRevisionCaptureStatus,
    ContextRevisionSourceKind,
    ContextFreshnessStatus,
    ImportSessionStatus,
    OriginalSnapshotStatus,
    JobStatus,
    NodeFormat,
    NodeKind,
    NodeProcessingStatus,
    ProjectStatus,
    RelationshipType,
    SourceKind,
    SourceStatus,
    WorkingRefreshReason,
    WorkingContentStatus,
    WorkspaceItemLifecycleStatus,
    WorkspaceExportKind,
)
from pig.domain.processing_policy import ProcessingPolicy
from pig.domain.snapshot_policy import SnapshotImportPolicy
from pig.application.ports import QuarantineRecord, RecoveryCandidate


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateProjectRequest:
    name: str
    actor: str
    description: Optional[str] = None
    workspace_root: Optional[Path] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateProjectResult:
    project_id: str
    status: ProjectStatus
    workspace_path: Path
    database_path: Path
    workspace_revision: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportProjectItemsRequest:
    project_id: str
    database_path: Path
    input_paths: Sequence[Path]
    actor: str
    idempotency_key: Optional[str] = None
    policy: SnapshotImportPolicy = SnapshotImportPolicy()
    target_workspace_parent_id: Optional[str] = None
    expected_workspace_revision: Optional[int] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportItemResult:
    input_path: Path
    snapshot_id: Optional[str]
    captured: bool
    source_id: Optional[str] = None
    root_node_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportProjectItemsResult:
    project_id: str
    import_session_id: str
    session_status: ImportSessionStatus
    requested_item_count: int
    accepted_item_count: int
    failed_item_count: int
    items: Sequence[ImportItemResult]


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyOriginalSnapshotRequest:
    project_id: str
    database_path: Path
    snapshot_id: str
    actor: str
    chunk_size: int = 1024 * 1024


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyOriginalSnapshotResult:
    project_id: str
    snapshot_id: str
    status: OriginalSnapshotStatus
    verified_artifact_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class InspectImportSessionRequest:
    project_id: str
    database_path: Path
    import_session_id: str
    actor: str
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class InspectImportSessionResult:
    project_id: str
    import_session_id: str
    session_status: ImportSessionStatus
    job_id: str
    source_count: int
    node_count: int
    workspace_item_count: int
    warning_count: int
    error_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializeWorkspaceItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class MaterializeWorkspaceItemResult:
    project_id: str
    workspace_item_id: str
    working_artifact: WorkingArtifact
    path: Path
    reused: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshWorkingArtifactRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    reason: WorkingRefreshReason = WorkingRefreshReason.EXPLICIT


@dataclass(frozen=True, slots=True, kw_only=True)
class RefreshWorkingArtifactResult:
    project_id: str
    workspace_item_id: str
    working_artifact: WorkingArtifact
    path: Path
    reason: WorkingRefreshReason
    changed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenWorkspaceItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenWorkspaceItemResult:
    project_id: str
    workspace_item_id: str
    working_artifact: WorkingArtifact
    format: NodeFormat
    path: Path
    materialized: bool
    handed_off_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class RestoreWorkingArtifactRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    confirmed_replace: bool = False
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class RestoreWorkingArtifactResult:
    project_id: str
    workspace_item_id: str
    working_artifact: WorkingArtifact
    path: Path
    replaced: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RollbackWorkingArtifactRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    confirmed_replace: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RollbackWorkingArtifactResult:
    project_id: str
    workspace_item_id: str
    working_artifact: WorkingArtifact
    previous_revision: WorkingRevision
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportWorkspaceItemsRequest:
    project_id: str
    database_path: Path
    workspace_item_ids: Sequence[str]
    destination_path: Path
    actor: str
    confirmed_replace: bool = False
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportWorkspaceItemsResult:
    project_id: str
    workspace_item_ids: Sequence[str]
    destination_path: Path
    export_kind: WorkspaceExportKind
    entry_count: int
    size: int
    sha256: str

    @property
    def archive(self) -> bool:
        return self.export_kind == WorkspaceExportKind.ZIP


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateWorkspaceFolderRequest:
    project_id: str
    database_path: Path
    display_name: str
    actor: str
    expected_workspace_revision: int
    parent_workspace_item_id: Optional[str] = None
    ordinal: Optional[int] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MoveWorkspaceItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    expected_workspace_revision: int
    new_parent_workspace_item_id: Optional[str] = None
    new_ordinal: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class SoftDeleteWorkspaceItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    expected_workspace_revision: int
    confirmed: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RestoreWorkspaceItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    expected_workspace_revision: int


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceMutationResult:
    project_id: str
    workspace_revision: int
    item: WorkspaceItem
    placement: WorkspacePlacement
    restore_fallback: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AddWorkspaceInputsRequest:
    project_id: str
    database_path: Path
    input_paths: Sequence[Path]
    actor: str
    expected_workspace_revision: int
    target_workspace_parent_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    snapshot_policy: SnapshotImportPolicy = SnapshotImportPolicy()
    processing_policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class AddWorkspaceInputsResult:
    project_id: str
    workspace_revision: int
    import_result: ImportProjectItemsResult
    inspection_result: Optional[InspectImportSessionResult]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewImportUndoRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ImportUndoImpact:
    project_id: str
    workspace_item_id: str
    snapshot_id: str
    source_id: str
    display_name: str
    workspace_item_count: int
    working_file_count: int
    modified_working_file_count: int
    original_byte_count: int
    working_byte_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class UndoImportedItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    expected_workspace_revision: int
    confirmed: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class UndoImportedItemResult:
    project_id: str
    workspace_item_id: str
    snapshot_id: str
    source_id: str
    workspace_revision: int
    purged_workspace_item_count: int
    removed_byte_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceItemView:
    item: WorkspaceItem
    placement: WorkspacePlacement
    workspace_path: str
    effectively_active: bool
    source_node: Optional[Node] = None
    source: Optional[Source] = None
    working_artifact: Optional[WorkingArtifact] = None
    current_revision: Optional[WorkingRevision] = None
    previous_revision: Optional[WorkingRevision] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetWorkspaceTreeRequest:
    project_id: str
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class GetWorkspaceTreeResult:
    project: Project
    workspace_revision: int
    items: Sequence[WorkspaceItemView]
    deleted_items: Sequence[WorkspaceItemView]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetWorkspaceItemRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetWorkspaceItemResult:
    project: Project
    view: WorkspaceItemView


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchWorkspaceItemsRequest:
    project_id: str
    database_path: Path
    query: Optional[str] = None
    formats: Sequence[NodeFormat] = ()
    content_statuses: Sequence[WorkingContentStatus] = ()
    lifecycle_statuses: Sequence[WorkspaceItemLifecycleStatus] = (
        WorkspaceItemLifecycleStatus.ACTIVE,
    )
    limit: int = 200
    offset: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchWorkspaceItemsResult:
    project_id: str
    items: Sequence[WorkspaceItemView]
    total: int
    limit: int
    offset: int
    has_more: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterSourceRequest:
    project_id: str
    database_path: Path
    source_path: Path
    source_kind: SourceKind
    actor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterSourceResult:
    project_id: str
    source_id: str
    source_status: SourceStatus
    root_node_id: str
    artifact_id: Optional[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectOverviewRequest:
    project_id: str
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceOverview:
    source: Source
    root_node: Node
    artifacts: Sequence[Artifact]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectOverview:
    project: Project
    sources: Sequence[SourceOverview]
    events: Sequence[ProcessingEvent]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetRecentProjectEventsRequest:
    project_id: str
    database_path: Path
    limit: int = 300


@dataclass(frozen=True, slots=True, kw_only=True)
class GetRecentProjectEventsResult:
    project_id: str
    events: Sequence[ProcessingEvent]


@dataclass(frozen=True, slots=True, kw_only=True)
class LoadProjectRequest:
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightProjectContextUpgradeRequest:
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightProjectContextUpgradeResult:
    project_id: str
    project_name: str
    current_model_version: str
    target_model_version: str
    current_schema_revision: str
    target_schema_revision: str
    requires_upgrade: bool
    backup_required: bool
    integrity_ok: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class UpgradeProjectContextRequest:
    database_path: Path
    actor: str
    confirmed: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class UpgradeProjectContextResult:
    project_id: str
    previous_model_version: str
    model_version: str
    schema_revision: str
    backup_path: Optional[Path]
    upgraded: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureContextRevisionRequest:
    project_id: str
    database_path: Path
    context_item_id: str
    actor: str
    expected_workspace_revision: int
    expected_context_revision: int
    correlation_id: Optional[str] = None
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class CaptureContextRevisionResult:
    project_id: str
    context_item_id: str
    context_revision_id: str
    content_object_id: str
    source_kind: ContextRevisionSourceKind
    capture_status: ContextRevisionCaptureStatus
    workspace_revision: int
    context_revision: int
    size_bytes: int
    sha256: str
    object_key: str
    object_reused: bool
    quota_warning: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class InspectContextObjectStoreRequest:
    project_id: str
    database_path: Path
    actor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextObjectStoreIssue:
    object_key: str
    issue: str
    content_object_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class InspectContextObjectStoreResult:
    project_id: str
    orphan_keys: Sequence[str]
    missing_object_ids: Sequence[str]
    issues: Sequence[ContextObjectStoreIssue]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightContextPromotionRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    expected_workspace_revision: int
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightContextPromotionResult:
    project_id: str
    workspace_item_id: str
    workspace_revision: int
    context_revision: int
    source_kind: ContextRevisionSourceKind
    estimated_size_bytes: int
    context_store_bytes: int
    available_bytes: int
    soft_quota_bytes: int
    minimum_free_bytes: int
    quota_warning: bool
    capture_allowed: bool
    blocking_code: Optional[str]
    existing_context_item_id: Optional[str]
    already_active: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PromoteWorkspaceItemToContextRequest:
    project_id: str
    database_path: Path
    workspace_item_id: str
    actor: str
    expected_workspace_revision: int
    expected_context_revision: int
    title_override: Optional[str] = None
    purpose: Optional[str] = None
    correlation_id: Optional[str] = None
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class PromoteWorkspaceItemToContextResult:
    item: ContextItem
    capture: Optional[CaptureContextRevisionResult]
    restored: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class AdvanceContextRevisionRequest:
    project_id: str
    database_path: Path
    context_item_id: str
    actor: str
    expected_workspace_revision: int
    expected_context_revision: int
    correlation_id: Optional[str] = None
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextItemLifecycleRequest:
    project_id: str
    database_path: Path
    context_item_id: str
    actor: str
    expected_context_revision: int
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextItemMutationResult:
    project_id: str
    context_revision: int
    item: ContextItem


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateContextSectionRequest:
    project_id: str
    database_path: Path
    name: str
    actor: str
    expected_context_revision: int
    description: Optional[str] = None
    ordinal: Optional[int] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateContextSectionRequest:
    project_id: str
    database_path: Path
    context_section_id: str
    actor: str
    expected_context_revision: int
    name: Optional[str] = None
    description: Optional[str] = None
    ordinal: Optional[int] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextSectionLifecycleRequest:
    project_id: str
    database_path: Path
    context_section_id: str
    actor: str
    expected_context_revision: int
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextSectionMutationResult:
    project_id: str
    context_revision: int
    section: ContextSection


@dataclass(frozen=True, slots=True, kw_only=True)
class PlaceContextItemRequest:
    project_id: str
    database_path: Path
    context_item_id: str
    context_section_id: str
    actor: str
    expected_context_revision: int
    ordinal: Optional[int] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextPlacementMutationResult:
    project_id: str
    context_revision: int
    placement: ContextPlacement


@dataclass(frozen=True, slots=True, kw_only=True)
class UpsertContextAnnotationRequest:
    project_id: str
    database_path: Path
    context_item_id: str
    body: str
    actor: str
    expected_context_revision: int
    context_revision_id: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextAnnotationMutationResult:
    project_id: str
    context_revision: int
    annotation: ContextAnnotation
    created: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SetContextRevisionProtectionRequest:
    project_id: str
    database_path: Path
    context_revision_id: str
    protected: bool
    actor: str
    expected_context_revision: int
    reason: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextRevisionProtectionResult:
    project_id: str
    context_revision: int
    revision: ContextRevision


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewContextRevisionCleanupRequest:
    project_id: str
    database_path: Path
    actor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextRevisionCleanupCandidate:
    revision_id: str
    context_item_id: str
    content_object_id: str
    size_bytes: int
    object_shared: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewContextRevisionCleanupResult:
    project_id: str
    context_revision: int
    preview_token: str
    candidates: Sequence[ContextRevisionCleanupCandidate]
    reclaimable_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecuteContextRevisionCleanupRequest:
    project_id: str
    database_path: Path
    actor: str
    expected_context_revision: int
    preview_token: str
    confirmed: bool = False
    correlation_id: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecuteContextRevisionCleanupResult:
    project_id: str
    context_revision: int
    deleted_revision_ids: Sequence[str]
    deleted_content_object_ids: Sequence[str]
    reclaimed_bytes: int
    orphaned_object_keys: Sequence[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectContextRequest:
    project_id: str
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextItemView:
    item: ContextItem
    workspace_item: WorkspaceItem
    current_revision: Optional[ContextRevision]
    freshness: ContextFreshnessStatus
    effective_placements: Sequence[ContextPlacement]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectContextResult:
    project: Project
    sections: Sequence[ContextSection]
    items: Sequence[ContextItemView]
    placements: Sequence[ContextPlacement]
    unsectioned_item_ids: Sequence[str]
    removed_sections: Sequence[ContextSection] = ()
    removed_items: Sequence[ContextItemView] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class GetContextItemDetailsRequest:
    project_id: str
    database_path: Path
    context_item_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetContextItemDetailsResult:
    project: Project
    view: ContextItemView
    revisions: Sequence[ContextRevision]
    annotations: Sequence[ContextAnnotation]


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextPackRevisionChoice:
    context_item_id: str
    context_revision_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class GetContextPackPlanRequest:
    project_id: str
    database_path: Path
    selected_item_ids: Sequence[str] = ()
    revision_choices: Sequence[ContextPackRevisionChoice] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextPackPlanSection:
    source_section_id: Optional[str]
    name: str
    ordinal: int
    description: Optional[str] = None
    is_unsectioned: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextPackPlanEntry:
    context_item_id: str
    context_revision_id: str
    content_object_id: str
    display_name: str
    relative_path: str
    size_bytes: int
    sha256: str
    ordinal: int
    freshness: ContextFreshnessStatus
    section_ids: Sequence[str]
    purpose: Optional[str] = None
    guidance_body: Optional[str] = None
    guidance_author: Optional[str] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetContextPackPlanResult:
    project_id: str
    project_name: str
    context_revision: int
    manifest_schema_version: str
    plan_fingerprint: str
    total_bytes: int
    sections: Sequence[ContextPackPlanSection]
    entries: Sequence[ContextPackPlanEntry]
    warning_item_ids: Sequence[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightContextPackExportRequest:
    project_id: str
    database_path: Path
    destination_path: Path
    format: ContextPackFormat
    actor: str
    selected_item_ids: Sequence[str] = ()
    revision_choices: Sequence[ContextPackRevisionChoice] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PreflightContextPackExportResult:
    export_id: str
    plan_token: str
    plan: GetContextPackPlanResult
    destination_path: Path
    format: ContextPackFormat
    available_bytes: int
    required_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecuteContextPackExportRequest:
    project_id: str
    database_path: Path
    export_id: str
    plan_token: str
    actor: str
    selected_item_ids: Sequence[str] = ()
    revision_choices: Sequence[ContextPackRevisionChoice] = ()
    confirm_outdated: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecuteContextPackExportResult:
    export: ContextPackExport
    destination_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class GetContextPackExportsRequest:
    project_id: str
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class GetContextPackExportsResult:
    exports: Sequence[ContextPackExport]


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelContextPackPreflightRequest:
    project_id: str
    database_path: Path
    export_id: str
    plan_token: str
    actor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverInterruptedContextPackExportsRequest:
    project_id: str
    database_path: Path
    actor: str
    confirmed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverInterruptedContextPackExportsResult:
    recovered_export_ids: Sequence[str]
    external_paths_to_review: Sequence[Path]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetNodeRequest:
    project_id: str
    database_path: Path
    node_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class NodeDetails:
    node: Node
    source: Source
    artifacts: Sequence[Artifact]
    metadata: Sequence[NodeMetadata]
    lineage: Sequence[LineageRecord]
    children: Sequence[Node] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessNodeRequest:
    project_id: str
    database_path: Path
    node_id: str
    actor: str
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessNodeResult:
    project_id: str
    node_id: str
    node_status: NodeProcessingStatus
    job_id: str
    job_status: JobStatus
    attempt_id: str
    child_node_ids: Sequence[str]
    warning_count: int
    error_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessProjectRequest:
    project_id: str
    database_path: Path
    actor: str
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProcessProjectResult:
    project_id: str
    job_id: str
    job_status: JobStatus
    project_status: ProjectStatus
    processed_node_ids: Sequence[str]
    attempt_ids: Sequence[str]
    warning_count: int
    error_count: int
    total_expanded_size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverProjectRequest:
    project_id: str
    database_path: Path
    actor: str
    policy: ProcessingPolicy = ProcessingPolicy()


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverProjectResult:
    project_id: str
    recovery_job_id: str
    job_status: JobStatus
    project_status: ProjectStatus
    interrupted_job_ids: Sequence[str]
    cancelled_job_ids: Sequence[str]
    interrupted_attempt_ids: Sequence[str]
    cancelled_attempt_ids: Sequence[str]
    recovered_node_ids: Sequence[str]
    processed_node_ids: Sequence[str]
    attempt_ids: Sequence[str]
    quarantine_records: Sequence[QuarantineRecord]
    warning_count: int
    error_count: int
    total_expanded_size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class InspectProjectRecoveryRequest:
    project_id: str
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class InspectProjectRecoveryResult:
    project_id: str
    inspection_token: str
    recovery_required: bool
    candidates: Sequence[RecoveryCandidate]


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverWorkbenchProjectRequest:
    project_id: str
    database_path: Path
    actor: str
    inspection_token: str
    confirmed: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class RecoverWorkbenchProjectResult:
    project_id: str
    recovery_run: RecoveryRun
    recovery_items: Sequence[RecoveryItem]
    remaining_candidate_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchNodesRequest:
    project_id: str
    database_path: Path
    query: Optional[str] = None
    source_id: Optional[str] = None
    kinds: Sequence[NodeKind] = ()
    formats: Sequence[NodeFormat] = ()
    statuses: Sequence[NodeProcessingStatus] = ()
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchNodeHit:
    node: Node
    parent_node_id: Optional[str]
    relationship_type: Optional[RelationshipType]


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchNodesResult:
    project_id: str
    items: Sequence[SearchNodeHit]
    total: int
    limit: int
    offset: int
    has_more: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportManifestRequest:
    project_id: str
    database_path: Path
    actor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExportManifestResult:
    project_id: str
    manifest_id: str
    schema_version: str
    generated_at: datetime
    storage_key: str
    manifest_path: Path
    size: int
    sha256: str
    included_event_count: int
    last_included_event_id: Optional[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class GetProjectTreeRequest:
    project_id: str
    database_path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectTreeItem:
    node: Node
    parent_node_id: Optional[str]
    relationship_type: Optional[RelationshipType]
    ordinal: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ProjectTreeResult:
    project: Project
    sources: Sequence[Source]
    items: Sequence[ProjectTreeItem]


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenNodeRequest:
    project_id: str
    database_path: Path
    node_id: str
    actor: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OpenNodeResult:
    project_id: str
    node_id: str
    artifact_id: str
    format: NodeFormat
    path: Path
    handed_off_at: datetime
