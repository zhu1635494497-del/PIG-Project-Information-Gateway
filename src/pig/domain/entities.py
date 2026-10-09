from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional

from pig.domain.enums import (
    ArtifactIntegrityStatus,
    ArtifactRole,
    ArtifactScope,
    AttemptStatus,
    ErrorCategory,
    ErrorCode,
    EventSeverity,
    EventType,
    ImportSessionStatus,
    ImportItemStatus,
    JobStatus,
    JobType,
    MetadataValueType,
    MaterializationLocatorKind,
    NodeFormat,
    NodeKind,
    NodeProcessingStatus,
    OriginalSnapshotStatus,
    OriginalSnapshotEntryKind,
    ProcessingStage,
    ProjectStatus,
    RecoveryAction,
    RecoveryItemKind,
    RecoveryItemStatus,
    RecoveryRunStatus,
    RelationshipType,
    SourceKind,
    SourceStatus,
    WorkingContentStatus,
    WorkingRevisionRole,
    WorkspaceItemKind,
    WorkspaceItemLifecycleStatus,
    WorkspaceMaterializationStatus,
    ContextAnnotationKind,
    ContextContentObjectStatus,
    ContextLifecycleStatus,
    ContextRevisionCaptureStatus,
    ContextRevisionSourceKind,
    ContextPackFormat,
    ContextPackExportStatus,
)


@dataclass(slots=True, kw_only=True)
class Project:
    id: str
    name: str
    status: ProjectStatus
    workspace_locator: str
    model_version: str
    created_at: datetime
    updated_at: datetime
    description: Optional[str] = None
    workspace_revision: int = 0
    context_revision: int = 0


@dataclass(slots=True, kw_only=True)
class ContextSettings:
    project_id: str
    soft_quota_bytes: int
    minimum_free_bytes: int
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, kw_only=True)
class ContextSection:
    id: str
    project_id: str
    name: str
    ordinal: int
    lifecycle_status: ContextLifecycleStatus
    created_at: datetime
    updated_at: datetime
    description: Optional[str] = None
    removed_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class ContextItem:
    id: str
    project_id: str
    workspace_item_id: str
    lifecycle_status: ContextLifecycleStatus
    created_at: datetime
    updated_at: datetime
    title_override: Optional[str] = None
    purpose: Optional[str] = None
    current_context_revision_id: Optional[str] = None
    removed_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class ContextPlacement:
    id: str
    project_id: str
    context_item_id: str
    context_section_id: str
    ordinal: int
    lifecycle_status: ContextLifecycleStatus
    created_at: datetime
    updated_at: datetime
    removed_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class ContextContentObject:
    id: str
    project_id: str
    sha256: str
    size_bytes: int
    object_key: str
    availability_status: ContextContentObjectStatus
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, kw_only=True)
class ContextRevision:
    id: str
    project_id: str
    context_item_id: str
    source_kind: ContextRevisionSourceKind
    captured_workspace_revision: int
    capture_status: ContextRevisionCaptureStatus
    is_manually_protected: bool
    created_by: str
    created_at: datetime
    updated_at: datetime
    content_object_id: Optional[str] = None
    source_working_artifact_id: Optional[str] = None
    source_node_id: Optional[str] = None
    source_observed_sha256: Optional[str] = None
    protection_reason: Optional[str] = None
    ready_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class ContextAnnotation:
    id: str
    project_id: str
    context_item_id: str
    kind: ContextAnnotationKind
    body: str
    author: str
    created_at: datetime
    updated_at: datetime
    context_revision_id: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class ContextPackExport:
    id: str
    project_id: str
    format: ContextPackFormat
    status: ContextPackExportStatus
    destination_locator: str
    actor: str
    correlation_id: str
    captured_context_revision: int
    manifest_schema_version: str
    plan_fingerprint: str
    entry_count: int
    total_bytes: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    published_sha256: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class ContextPackEntry:
    id: str
    project_id: str
    export_id: str
    context_item_id: str
    context_revision_id: str
    ordinal: int
    relative_path: str
    display_name: str
    size_bytes: int
    sha256: str
    created_at: datetime
    purpose_snapshot: Optional[str] = None
    guidance_body_snapshot: Optional[str] = None
    guidance_author_snapshot: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class ContextPackSection:
    id: str
    project_id: str
    export_id: str
    source_section_id: Optional[str]
    name_snapshot: str
    ordinal: int
    is_unsectioned: bool
    created_at: datetime
    description_snapshot: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class ContextPackPlacement:
    id: str
    project_id: str
    export_id: str
    entry_id: str
    section_id: str
    ordinal: int
    created_at: datetime


@dataclass(slots=True, kw_only=True)
class ImportSession:
    id: str
    project_id: str
    status: ImportSessionStatus
    requested_item_count: int
    accepted_item_count: int
    failed_item_count: int
    requested_at: datetime
    actor: str
    correlation_id: str
    policy_snapshot: Mapping[str, Any] = field(default_factory=dict)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    target_workspace_parent_id: Optional[str] = None
    expected_workspace_revision: Optional[int] = None


@dataclass(slots=True, kw_only=True)
class ImportSessionItem:
    id: str
    project_id: str
    import_session_id: str
    ordinal: int
    input_locator: str
    status: ImportItemStatus
    created_at: datetime
    updated_at: datetime
    snapshot_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class OriginalSnapshot:
    id: str
    project_id: str
    import_session_id: str
    input_kind: SourceKind
    original_display_name: str
    external_locator_at_import: str
    status: OriginalSnapshotStatus
    created_at: datetime
    verified_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class OriginalArtifact:
    id: str
    project_id: str
    snapshot_id: str
    storage_key: str
    size: int
    sha256: str
    integrity_status: ArtifactIntegrityStatus
    created_at: datetime
    source_node_id: Optional[str] = None
    observed_modified_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class OriginalSnapshotEntry:
    id: str
    project_id: str
    snapshot_id: str
    kind: OriginalSnapshotEntryKind
    original_name: str
    ordinal: int
    created_at: datetime
    parent_entry_id: Optional[str] = None
    artifact_id: Optional[str] = None
    source_node_id: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class WorkspaceItem:
    id: str
    project_id: str
    item_kind: WorkspaceItemKind
    display_name: str
    lifecycle_status: WorkspaceItemLifecycleStatus
    materialization_status: WorkspaceMaterializationStatus
    created_at: datetime
    updated_at: datetime
    origin_source_node_id: Optional[str] = None
    deleted_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class WorkspacePlacement:
    workspace_item_id: str
    project_id: str
    parent_workspace_item_id: Optional[str]
    ordinal: int
    updated_at: datetime
    previous_parent_id: Optional[str] = None
    previous_ordinal: Optional[int] = None


@dataclass(slots=True, kw_only=True)
class WorkingArtifact:
    id: str
    project_id: str
    workspace_item_id: str
    storage_key: str
    baseline_size: int
    baseline_sha256: str
    current_size: int
    current_sha256: str
    content_status: WorkingContentStatus
    materialized_at: datetime
    updated_at: datetime
    last_checked_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class WorkingRevision:
    id: str
    project_id: str
    working_artifact_id: str
    role: WorkingRevisionRole
    storage_key: str
    size: int
    sha256: str
    file_modified_at: datetime
    detected_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, kw_only=True)
class RecoveryRun:
    id: str
    project_id: str
    status: RecoveryRunStatus
    actor: str
    correlation_id: str
    detected_count: int
    recovered_count: int
    failed_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class RecoveryItem:
    id: str
    recovery_run_id: str
    project_id: str
    kind: RecoveryItemKind
    action: RecoveryAction
    status: RecoveryItemStatus
    storage_key: str
    reason: str
    created_at: datetime
    operation_id: Optional[str] = None
    size: Optional[int] = None
    sha256: Optional[str] = None
    recovery_storage_key: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    updated_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class Source:
    id: str
    project_id: str
    snapshot_id: str
    kind: SourceKind
    display_name: str
    status: SourceStatus
    created_at: datetime
    root_node_id: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class Node:
    id: str
    project_id: str
    source_id: str
    kind: NodeKind
    format: NodeFormat
    original_name: str
    display_name: str
    logical_path: str
    depth: int
    status: NodeProcessingStatus
    discovery_key: str
    created_at: datetime
    updated_at: datetime
    media_type: Optional[str] = None
    declared_size: Optional[int] = None
    detection_method: Optional[str] = None
    detection_confidence: Optional[float] = None
    detection_details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class Artifact:
    id: str
    project_id: str
    node_id: str
    role: ArtifactRole
    scope: ArtifactScope
    locator: str
    integrity_status: ArtifactIntegrityStatus
    created_at: datetime
    size: Optional[int] = None
    sha256: Optional[str] = None
    observed_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class NodeRelationship:
    id: str
    project_id: str
    parent_node_id: str
    child_node_id: str
    type: RelationshipType
    ordinal: int
    discovery_key: str
    created_by_job_id: str
    created_at: datetime


@dataclass(slots=True, kw_only=True)
class SourceEntryLocator:
    relationship_id: str
    project_id: str
    child_node_id: str
    kind: MaterializationLocatorKind
    created_at: datetime
    snapshot_entry_id: Optional[str] = None
    member_ordinal: Optional[int] = None
    expected_name: Optional[str] = None
    member_role: Optional[str] = None

    @property
    def zip_member_ordinal(self) -> Optional[int]:
        """Read-only W3 compatibility view; new code uses member_ordinal."""

        if self.kind != MaterializationLocatorKind.ZIP_MEMBER:
            return None
        return self.member_ordinal


@dataclass(slots=True, kw_only=True)
class LineageRecord:
    project_id: str
    ancestor_node_id: str
    descendant_node_id: str
    distance: int


@dataclass(slots=True, kw_only=True)
class NodeMetadata:
    id: str
    project_id: str
    node_id: str
    namespace: str
    key: str
    value_type: MetadataValueType
    provenance: str
    created_at: datetime
    value_text: Optional[str] = None
    value_integer: Optional[int] = None
    value_real: Optional[float] = None
    value_boolean: Optional[bool] = None
    value_datetime: Optional[datetime] = None
    value_json: Optional[Any] = None
    observed_at: Optional[datetime] = None


@dataclass(slots=True, kw_only=True)
class ProcessingJob:
    id: str
    project_id: str
    type: JobType
    status: JobStatus
    requested_by: str
    policy_snapshot: Mapping[str, Any]
    created_at: datetime
    import_session_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    warning_count: int = 0
    error_count: int = 0


@dataclass(slots=True, kw_only=True)
class ProcessingError:
    code: ErrorCode
    category: ErrorCategory
    stage: ProcessingStage
    message: str
    retryable: bool
    technical_reference: Optional[str] = None


@dataclass(slots=True, kw_only=True)
class ProcessingAttempt:
    id: str
    project_id: str
    job_id: str
    node_id: str
    attempt_number: int
    status: AttemptStatus
    stage: ProcessingStage
    queued_at: datetime
    handler_name: Optional[str] = None
    handler_version: Optional[str] = None
    backend_name: Optional[str] = None
    backend_version: Optional[str] = None
    backend_sha256: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[ProcessingError] = None


@dataclass(slots=True, kw_only=True)
class ProcessingEvent:
    id: str
    event_type: EventType
    project_id: str
    actor: str
    occurred_at: datetime
    severity: EventSeverity
    correlation_id: str
    details: Mapping[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None
    node_id: Optional[str] = None
    job_id: Optional[str] = None
    attempt_id: Optional[str] = None
    import_session_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    workspace_item_id: Optional[str] = None
    working_artifact_id: Optional[str] = None
    context_section_id: Optional[str] = None
    context_item_id: Optional[str] = None
    context_content_object_id: Optional[str] = None
    context_revision_id: Optional[str] = None
    context_annotation_id: Optional[str] = None
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    error_code: Optional[ErrorCode] = None
