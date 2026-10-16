from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Type

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SAEnum,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pig.domain import enums
from pig.domain.enums import StringEnum
from pig.domain.experience_policy import ExperienceEvidenceRole, ExperienceKind, ExperienceStatus
from pig.domain.ai_policy import AnalysisAction, AnalysisStatus
from pig.infrastructure.database.base import Base
from pig.infrastructure.database.types import UTCDateTime


def enum_type(enum_class: Type[StringEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda items: [item.value for item in items],
    )


class ProjectModel(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("singleton_key = 1", name="singleton_key_is_one"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("workspace_revision >= 0", name="workspace_revision_nonnegative"),
        CheckConstraint("context_revision >= 0", name="context_revision_nonnegative"),
        UniqueConstraint("singleton_key", name="uq_projects_singleton"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    singleton_key: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[enums.ProjectStatus] = mapped_column(
        enum_type(enums.ProjectStatus, "project_status"), nullable=False
    )
    workspace_locator: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    workspace_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    context_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class ContextSettingsModel(Base):
    __tablename__ = "context_settings"
    __table_args__ = (
        CheckConstraint("soft_quota_bytes > 0", name="soft_quota_bytes_positive"),
        CheckConstraint("minimum_free_bytes > 0", name="minimum_free_bytes_positive"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
    )

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    soft_quota_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_free_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextSectionModel(Base):
    __tablename__ = "context_sections"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_context_sections_id_project"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL) OR "
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL)",
            name="removed_at_matches_lifecycle",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        Index(
            "ix_context_sections_project_order",
            "project_id",
            "lifecycle_status",
            "ordinal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_status: Mapped[enums.ContextLifecycleStatus] = mapped_column(
        enum_type(enums.ContextLifecycleStatus, "context_section_lifecycle_status"),
        nullable=False,
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextItemModel(Base):
    __tablename__ = "context_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_context_items_id_project"),
        UniqueConstraint(
            "project_id", "workspace_item_id",
            name="uq_context_items_workspace_item",
        ),
        CheckConstraint(
            "title_override IS NULL OR length(trim(title_override)) > 0",
            name="title_override_not_blank",
        ),
        CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL) OR "
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL)",
            name="removed_at_matches_lifecycle",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["workspace_item_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["current_context_revision_id", "project_id", "id"],
            [
                "context_revisions.id",
                "context_revisions.project_id",
                "context_revisions.context_item_id",
            ],
            name="fk_context_items_current_revision",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_context_items_project_lifecycle", "project_id", "lifecycle_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title_override: Mapped[Optional[str]] = mapped_column(String(512))
    purpose: Mapped[Optional[str]] = mapped_column(Text)
    lifecycle_status: Mapped[enums.ContextLifecycleStatus] = mapped_column(
        enum_type(enums.ContextLifecycleStatus, "context_item_lifecycle_status"),
        nullable=False,
    )
    current_context_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    removed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextPlacementModel(Base):
    __tablename__ = "context_placements"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_context_placements_id_project"),
        UniqueConstraint(
            "context_item_id", "context_section_id",
            name="uq_context_placements_item_section",
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND removed_at IS NULL) OR "
            "(lifecycle_status = 'REMOVED' AND removed_at IS NOT NULL)",
            name="removed_at_matches_lifecycle",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["context_section_id", "project_id"],
            ["context_sections.id", "context_sections.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_context_placements_section_order",
            "project_id",
            "context_section_id",
            "lifecycle_status",
            "ordinal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_section_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    lifecycle_status: Mapped[enums.ContextLifecycleStatus] = mapped_column(
        enum_type(enums.ContextLifecycleStatus, "context_placement_lifecycle_status"),
        nullable=False,
    )
    removed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextContentObjectModel(Base):
    __tablename__ = "context_content_objects"
    __table_args__ = (
        UniqueConstraint(
            "id", "project_id", name="uq_context_content_objects_id_project"
        ),
        UniqueConstraint(
            "project_id", "sha256", name="uq_context_content_objects_project_sha256"
        ),
        UniqueConstraint(
            "project_id", "object_key", name="uq_context_content_objects_object_key"
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_canonical",
        ),
        CheckConstraint("length(trim(object_key)) > 0", name="object_key_not_blank"),
        CheckConstraint(
            "substr(object_key, 1, 1) <> '/' "
            "AND instr(object_key, '\\') = 0 "
            "AND instr('/' || object_key || '/', '/../') = 0",
            name="object_key_project_relative",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        Index(
            "ix_context_content_objects_project_status",
            "project_id",
            "availability_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    availability_status: Mapped[enums.ContextContentObjectStatus] = mapped_column(
        enum_type(enums.ContextContentObjectStatus, "context_content_object_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextRevisionModel(Base):
    __tablename__ = "context_revisions"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_context_revisions_id_project"),
        UniqueConstraint(
            "id", "project_id", "context_item_id",
            name="uq_context_revisions_item_identity",
        ),
        CheckConstraint(
            "captured_workspace_revision >= 0",
            name="captured_workspace_revision_nonnegative",
        ),
        CheckConstraint(
            "source_observed_sha256 IS NULL OR "
            "(length(source_observed_sha256) = 64 "
            "AND source_observed_sha256 NOT GLOB '*[^0-9a-f]*')",
            name="source_observed_sha256_canonical",
        ),
        CheckConstraint(
            "(source_kind = 'WORKING' AND source_working_artifact_id IS NOT NULL "
            "AND source_node_id IS NULL) OR "
            "(source_kind = 'SOURCE' AND source_node_id IS NOT NULL "
            "AND source_working_artifact_id IS NULL)",
            name="source_kind_matches_reference",
        ),
        CheckConstraint(
            "capture_status <> 'READY' OR "
            "(content_object_id IS NOT NULL AND source_observed_sha256 IS NOT NULL "
            "AND ready_at IS NOT NULL)",
            name="ready_revision_is_complete",
        ),
        CheckConstraint(
            "(capture_status = 'FAILED' AND error_code IS NOT NULL "
            "AND error_message IS NOT NULL) OR capture_status <> 'FAILED'",
            name="failed_revision_has_error",
        ),
        CheckConstraint(
            "(is_manually_protected = 0 AND protection_reason IS NULL) OR "
            "(is_manually_protected = 1 AND protection_reason IS NOT NULL "
            "AND length(trim(protection_reason)) > 0)",
            name="manual_protection_has_reason",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["content_object_id", "project_id"],
            ["context_content_objects.id", "context_content_objects.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_working_artifact_id", "project_id"],
            ["working_artifacts.id", "working_artifacts.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_context_revisions_item_created",
            "project_id",
            "context_item_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    content_object_id: Mapped[Optional[str]] = mapped_column(String(36))
    source_kind: Mapped[enums.ContextRevisionSourceKind] = mapped_column(
        enum_type(enums.ContextRevisionSourceKind, "context_revision_source_kind"),
        nullable=False,
    )
    source_working_artifact_id: Mapped[Optional[str]] = mapped_column(String(36))
    source_node_id: Mapped[Optional[str]] = mapped_column(String(36))
    captured_workspace_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    source_observed_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    capture_status: Mapped[enums.ContextRevisionCaptureStatus] = mapped_column(
        enum_type(enums.ContextRevisionCaptureStatus, "context_revision_capture_status"),
        nullable=False,
    )
    is_manually_protected: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    protection_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    ready_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExtractionRunModel(Base):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_extraction_runs_id_project"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["context_revision_id", "project_id"],
            ["context_revisions.id", "context_revisions.project_id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("element_count >= 0", name="element_count_nonnegative"),
        Index("ix_extraction_runs_revision_status", "project_id", "context_revision_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[enums.ContentExtractionStatus] = mapped_column(
        enum_type(enums.ContentExtractionStatus, "content_extraction_status"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    element_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(String(512))


class ContentDocumentModel(Base):
    __tablename__ = "content_documents"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_content_documents_id_project"),
        UniqueConstraint("extraction_run_id", name="uq_content_documents_run"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["extraction_run_id", "project_id"],
            ["extraction_runs.id", "extraction_runs.project_id"], ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["context_revision_id", "project_id"],
            ["context_revisions.id", "context_revisions.project_id"], ondelete="CASCADE",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    extraction_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContentElementModel(Base):
    __tablename__ = "content_elements"
    __table_args__ = (
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["document_id", "project_id"],
            ["content_documents.id", "content_documents.project_id"], ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "ordinal", name="uq_content_elements_ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("length(text) > 0", name="text_not_empty"),
        CheckConstraint("length(locator_value) > 0", name="locator_not_empty"),
        Index("ix_content_elements_document_order", "document_id", "ordinal"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    locator_kind: Mapped[enums.ContentLocatorKind] = mapped_column(
        enum_type(enums.ContentLocatorKind, "content_locator_kind"), nullable=False
    )
    locator_value: Mapped[str] = mapped_column(String(255), nullable=False)


class ContextAnnotationModel(Base):
    __tablename__ = "context_annotations"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_context_annotations_id_project"),
        CheckConstraint("length(trim(body)) > 0", name="body_not_blank"),
        CheckConstraint("length(trim(author)) > 0", name="author_not_blank"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["context_revision_id", "project_id", "context_item_id"],
            [
                "context_revisions.id",
                "context_revisions.project_id",
                "context_revisions.context_item_id",
            ],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_context_annotations_item_created",
            "project_id",
            "context_item_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    kind: Mapped[enums.ContextAnnotationKind] = mapped_column(
        enum_type(enums.ContextAnnotationKind, "context_annotation_kind"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExperienceRecordModel(Base):
    __tablename__ = "experience_records"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_experience_records_id_project"),
        CheckConstraint("current_version >= 1", name="current_version_positive"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        Index("ix_experience_records_project_updated", "project_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[ExperienceKind] = mapped_column(enum_type(ExperienceKind, "experience_kind"), nullable=False)
    status: Mapped[ExperienceStatus] = mapped_column(enum_type(ExperienceStatus, "experience_status"), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExperienceVersionModel(Base):
    __tablename__ = "experience_versions"
    __table_args__ = (
        PrimaryKeyConstraint("record_id", "version"),
        UniqueConstraint("record_id", "project_id", "version", name="uq_experience_versions_identity"),
        CheckConstraint("version >= 1 AND length(trim(title)) > 0 AND length(trim(body)) > 0 "
                        "AND length(trim(author)) > 0", name="content_valid"),
        ForeignKeyConstraint(["record_id", "project_id"],
                             ["experience_records.id", "experience_records.project_id"], ondelete="RESTRICT"),
    )

    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExperienceStateChangeModel(Base):
    __tablename__ = "experience_state_changes"
    __table_args__ = (
        ForeignKeyConstraint(["record_id", "project_id", "version"],
                             ["experience_versions.record_id", "experience_versions.project_id",
                              "experience_versions.version"], ondelete="RESTRICT"),
        CheckConstraint("length(trim(actor)) > 0", name="actor_not_blank"),
        Index("ix_experience_state_changes_record", "record_id", "occurred_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(16))
    to_status: Mapped[ExperienceStatus] = mapped_column(enum_type(ExperienceStatus, "experience_status"), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ExperienceRevisionLinkModel(Base):
    __tablename__ = "experience_revision_links"
    __table_args__ = (
        PrimaryKeyConstraint("record_id", "version", "context_revision_id"),
        ForeignKeyConstraint(["record_id", "project_id", "version"],
                             ["experience_versions.record_id", "experience_versions.project_id",
                              "experience_versions.version"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["context_revision_id", "project_id", "context_item_id"],
                             ["context_revisions.id", "context_revisions.project_id",
                              "context_revisions.context_item_id"], ondelete="RESTRICT"),
        Index("ix_experience_revision_links_revision", "project_id", "context_revision_id"),
    )

    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    context_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[ExperienceEvidenceRole] = mapped_column(
        enum_type(ExperienceEvidenceRole, "experience_evidence_role"), nullable=False)


class ExperienceEventLinkModel(Base):
    __tablename__ = "experience_event_links"
    __table_args__ = (
        PrimaryKeyConstraint("record_id", "version", "event_id"),
        ForeignKeyConstraint(["record_id", "project_id", "version"],
                             ["experience_versions.record_id", "experience_versions.project_id",
                              "experience_versions.version"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["event_id", "project_id"],
                             ["processing_events.id", "processing_events.project_id"], ondelete="RESTRICT"),
    )

    record_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)


class ContextPackExportModel(Base):
    __tablename__ = "context_pack_exports"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_context_pack_exports_identity"),
        CheckConstraint("captured_context_revision >= 0", name="context_revision_nonnegative"),
        CheckConstraint("entry_count >= 0 AND total_bytes >= 0", name="counts_nonnegative"),
        CheckConstraint("length(trim(destination_locator)) > 0", name="destination_not_blank"),
        CheckConstraint("length(plan_fingerprint) = 64 AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'", name="fingerprint_canonical"),
        CheckConstraint("published_sha256 IS NULL OR (length(published_sha256) = 64 AND published_sha256 NOT GLOB '*[^0-9a-f]*')", name="published_sha256_canonical"),
        CheckConstraint("status <> 'SUCCEEDED' OR (finished_at IS NOT NULL AND published_sha256 IS NOT NULL)", name="success_has_publication"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        Index("ix_context_pack_exports_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    format: Mapped[enums.ContextPackFormat] = mapped_column(
        enum_type(enums.ContextPackFormat, "context_pack_format"), nullable=False
    )
    status: Mapped[enums.ContextPackExportStatus] = mapped_column(
        enum_type(enums.ContextPackExportStatus, "context_pack_export_status"), nullable=False
    )
    destination_locator: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    captured_context_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    published_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)


class ContextPackEntryModel(Base):
    __tablename__ = "context_pack_entries"
    __table_args__ = (
        UniqueConstraint("id", "project_id", "export_id", name="uq_context_pack_entries_identity"),
        UniqueConstraint("export_id", "context_item_id", name="uq_context_pack_entries_item"),
        UniqueConstraint("export_id", "ordinal", name="uq_context_pack_entries_ordinal"),
        UniqueConstraint("export_id", "relative_path", name="uq_context_pack_entries_path"),
        CheckConstraint("ordinal >= 0 AND size_bytes >= 0", name="size_and_ordinal_nonnegative"),
        CheckConstraint("length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'", name="sha256_canonical"),
        CheckConstraint("substr(relative_path, 1, 6) = 'files/' AND instr(relative_path, '\\') = 0 AND instr('/' || relative_path || '/', '/../') = 0", name="relative_path_safe"),
        ForeignKeyConstraint(["export_id", "project_id"], ["context_pack_exports.id", "context_pack_exports.project_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["context_revision_id", "project_id", "context_item_id"], ["context_revisions.id", "context_revisions.project_id", "context_revisions.context_item_id"], ondelete="RESTRICT"),
        Index("ix_context_pack_entries_revision", "project_id", "context_revision_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    export_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    guidance_body_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    guidance_author_snapshot: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextPackSectionModel(Base):
    __tablename__ = "context_pack_sections"
    __table_args__ = (
        UniqueConstraint("id", "project_id", "export_id", name="uq_context_pack_sections_identity"),
        UniqueConstraint("export_id", "source_section_id", name="uq_context_pack_sections_source"),
        UniqueConstraint("export_id", "ordinal", name="uq_context_pack_sections_ordinal"),
        CheckConstraint("ordinal >= 0 AND length(trim(name_snapshot)) > 0", name="section_valid"),
        CheckConstraint("(is_unsectioned = 1 AND source_section_id IS NULL) OR (is_unsectioned = 0 AND source_section_id IS NOT NULL)", name="unsectioned_matches_source"),
        ForeignKeyConstraint(["export_id", "project_id"], ["context_pack_exports.id", "context_pack_exports.project_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_section_id", "project_id"], ["context_sections.id", "context_sections.project_id"], ondelete="RESTRICT"),
        Index("uq_context_pack_sections_one_unsectioned", "export_id", unique=True, sqlite_where=text("is_unsectioned = 1")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    export_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_section_id: Mapped[Optional[str]] = mapped_column(String(36))
    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    description_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    is_unsectioned: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ContextPackPlacementModel(Base):
    __tablename__ = "context_pack_placements"
    __table_args__ = (
        UniqueConstraint("export_id", "entry_id", "section_id", name="uq_context_pack_placements_entry_section"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        ForeignKeyConstraint(["entry_id", "project_id", "export_id"], ["context_pack_entries.id", "context_pack_entries.project_id", "context_pack_entries.export_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["section_id", "project_id", "export_id"], ["context_pack_sections.id", "context_pack_sections.project_id", "context_pack_sections.export_id"], ondelete="RESTRICT"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    export_id: Mapped[str] = mapped_column(String(36), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False)
    section_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ImportSessionModel(Base):
    __tablename__ = "import_sessions"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_import_sessions_id_project"),
        UniqueConstraint(
            "project_id",
            "correlation_id",
            name="uq_import_sessions_project_correlation",
        ),
        CheckConstraint(
            "requested_item_count >= 0", name="requested_item_count_nonnegative"
        ),
        CheckConstraint(
            "accepted_item_count >= 0", name="accepted_item_count_nonnegative"
        ),
        CheckConstraint(
            "failed_item_count >= 0", name="failed_item_count_nonnegative"
        ),
        CheckConstraint(
            "accepted_item_count + failed_item_count <= requested_item_count",
            name="result_counts_within_requested",
        ),
        CheckConstraint(
            "expected_workspace_revision IS NULL OR expected_workspace_revision >= 0",
            name="expected_workspace_revision_nonnegative",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["target_workspace_parent_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            name="fk_import_sessions_target_workspace_parent_id_workspace_items",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        Index("ix_import_sessions_project_status", "project_id", "status"),
        Index(
            "ix_import_sessions_workspace_target",
            "project_id",
            "target_workspace_parent_id",
        ),
        Index(
            "uq_import_sessions_one_active_project",
            "project_id",
            unique=True,
            sqlite_where=text(
                "status IN ('QUEUED', 'SNAPSHOTTING', 'INSPECTING')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[enums.ImportSessionStatus] = mapped_column(
        enum_type(enums.ImportSessionStatus, "import_session_status"), nullable=False
    )
    requested_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    target_workspace_parent_id: Mapped[Optional[str]] = mapped_column(String(36))
    expected_workspace_revision: Mapped[Optional[int]] = mapped_column(Integer)


class ImportSessionItemModel(Base):
    __tablename__ = "import_session_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_import_session_items_id_project"),
        UniqueConstraint(
            "import_session_id", "ordinal", name="uq_import_session_items_session_ordinal"
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint("length(trim(input_locator)) > 0", name="input_locator_not_blank"),
        CheckConstraint(
            "(status = 'FAILED' AND error_code IS NOT NULL AND error_message IS NOT NULL) "
            "OR (status <> 'FAILED')",
            name="failed_item_has_error",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["import_session_id", "project_id"],
            ["import_sessions.id", "import_sessions.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["original_snapshots.id", "original_snapshots.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_import_session_items_session_status",
            "import_session_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    import_session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    input_locator: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[enums.ImportItemStatus] = mapped_column(
        enum_type(enums.ImportItemStatus, "import_item_status"), nullable=False
    )
    snapshot_id: Mapped[Optional[str]] = mapped_column(String(36))
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class OriginalSnapshotModel(Base):
    __tablename__ = "original_snapshots"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_original_snapshots_id_project"),
        CheckConstraint(
            "length(trim(original_display_name)) > 0",
            name="original_display_name_not_blank",
        ),
        CheckConstraint(
            "length(trim(external_locator_at_import)) > 0",
            name="external_locator_at_import_not_blank",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["import_session_id", "project_id"],
            ["import_sessions.id", "import_sessions.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_original_snapshots_project_status", "project_id", "status"),
        Index(
            "ix_original_snapshots_import_session",
            "project_id",
            "import_session_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    import_session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    input_kind: Mapped[enums.SourceKind] = mapped_column(
        enum_type(enums.SourceKind, "original_snapshot_input_kind"), nullable=False
    )
    original_display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    external_locator_at_import: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[enums.OriginalSnapshotStatus] = mapped_column(
        enum_type(enums.OriginalSnapshotStatus, "original_snapshot_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class OriginalArtifactModel(Base):
    __tablename__ = "original_artifacts"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_original_artifacts_id_project"),
        UniqueConstraint(
            "id",
            "project_id",
            "snapshot_id",
            name="uq_original_artifacts_id_project_snapshot",
        ),
        UniqueConstraint("project_id", "storage_key", name="uq_original_artifacts_storage_key"),
        CheckConstraint("size >= 0", name="size_nonnegative"),
        CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_canonical",
        ),
        CheckConstraint("length(trim(storage_key)) > 0", name="storage_key_not_blank"),
        CheckConstraint("size IS NULL OR size >= 0", name="size_nonnegative"),
        CheckConstraint(
            "sha256 IS NULL OR "
            "(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*')",
            name="sha256_canonical",
        ),
        CheckConstraint(
            "substr(storage_key, 1, 1) <> '/' "
            "AND instr(storage_key, '\\\\') = 0 "
            "AND instr('/' || storage_key || '/', '/../') = 0",
            name="storage_key_project_relative",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["original_snapshots.id", "original_snapshots.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_original_artifacts_snapshot", "project_id", "snapshot_id"),
        Index("ix_original_artifacts_sha256", "sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_node_id: Mapped[Optional[str]] = mapped_column(String(36))
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_modified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    integrity_status: Mapped[enums.ArtifactIntegrityStatus] = mapped_column(
        enum_type(enums.ArtifactIntegrityStatus, "original_artifact_integrity_status"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class OriginalSnapshotEntryModel(Base):
    __tablename__ = "original_snapshot_entries"
    __table_args__ = (
        UniqueConstraint(
            "id", "project_id", "snapshot_id",
            name="uq_original_snapshot_entries_identity",
        ),
        UniqueConstraint(
            "snapshot_id", "parent_entry_id", "ordinal",
            name="uq_original_snapshot_entries_sibling_ordinal",
        ),
        CheckConstraint("length(original_name) > 0", name="original_name_not_empty"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint(
            "(kind = 'FILE' AND artifact_id IS NOT NULL) OR "
            "(kind = 'FOLDER' AND artifact_id IS NULL)",
            name="kind_matches_artifact",
        ),
        CheckConstraint(
            "parent_entry_id IS NULL OR parent_entry_id <> id",
            name="parent_not_self",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["original_snapshots.id", "original_snapshots.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_entry_id", "project_id", "snapshot_id"],
            [
                "original_snapshot_entries.id",
                "original_snapshot_entries.project_id",
                "original_snapshot_entries.snapshot_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["artifact_id", "project_id", "snapshot_id"],
            [
                "original_artifacts.id",
                "original_artifacts.project_id",
                "original_artifacts.snapshot_id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_original_snapshot_entries_parent",
            "project_id",
            "snapshot_id",
            "parent_entry_id",
            "ordinal",
        ),
        Index(
            "uq_original_snapshot_entries_one_root",
            "snapshot_id",
            unique=True,
            sqlite_where=text("parent_entry_id IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_entry_id: Mapped[Optional[str]] = mapped_column(String(36))
    artifact_id: Mapped[Optional[str]] = mapped_column(String(36))
    source_node_id: Mapped[Optional[str]] = mapped_column(String(36))
    kind: Mapped[enums.OriginalSnapshotEntryKind] = mapped_column(
        enum_type(enums.OriginalSnapshotEntryKind, "original_snapshot_entry_kind"),
        nullable=False,
    )
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkspaceItemModel(Base):
    __tablename__ = "workspace_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_workspace_items_id_project"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_not_blank"),
        CheckConstraint(
            "(lifecycle_status = 'ACTIVE' AND deleted_at IS NULL) OR "
            "(lifecycle_status IN ('DELETED', 'PURGED') AND deleted_at IS NOT NULL)",
            name="deleted_at_matches_lifecycle",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["origin_source_node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_workspace_items_project_lifecycle",
            "project_id",
            "lifecycle_status",
        ),
        Index("ix_workspace_items_origin", "project_id", "origin_source_node_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    origin_source_node_id: Mapped[Optional[str]] = mapped_column(String(36))
    item_kind: Mapped[enums.WorkspaceItemKind] = mapped_column(
        enum_type(enums.WorkspaceItemKind, "workspace_item_kind"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    lifecycle_status: Mapped[enums.WorkspaceItemLifecycleStatus] = mapped_column(
        enum_type(enums.WorkspaceItemLifecycleStatus, "workspace_item_lifecycle_status"),
        nullable=False,
    )
    materialization_status: Mapped[enums.WorkspaceMaterializationStatus] = mapped_column(
        enum_type(
            enums.WorkspaceMaterializationStatus,
            "workspace_materialization_status",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class WorkspacePlacementModel(Base):
    __tablename__ = "workspace_placements"
    __table_args__ = (
        PrimaryKeyConstraint("workspace_item_id", name="pk_workspace_placements"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        CheckConstraint(
            "previous_ordinal IS NULL OR previous_ordinal >= 0",
            name="previous_ordinal_nonnegative",
        ),
        CheckConstraint(
            "parent_workspace_item_id IS NULL "
            "OR parent_workspace_item_id <> workspace_item_id",
            name="parent_not_self",
        ),
        CheckConstraint(
            "previous_parent_id IS NULL OR previous_parent_id <> workspace_item_id",
            name="previous_parent_not_self",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["workspace_item_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_workspace_item_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["previous_parent_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "ix_workspace_placements_parent_order",
            "project_id",
            "parent_workspace_item_id",
            "ordinal",
        ),
    )

    workspace_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_workspace_item_id: Mapped[Optional[str]] = mapped_column(String(36))
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_parent_id: Mapped[Optional[str]] = mapped_column(String(36))
    previous_ordinal: Mapped[Optional[int]] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkingArtifactModel(Base):
    __tablename__ = "working_artifacts"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_working_artifacts_id_project"),
        UniqueConstraint("workspace_item_id", name="uq_working_artifacts_workspace_item"),
        UniqueConstraint("project_id", "storage_key", name="uq_working_artifacts_storage_key"),
        CheckConstraint("baseline_size >= 0", name="baseline_size_nonnegative"),
        CheckConstraint("current_size >= 0", name="current_size_nonnegative"),
        CheckConstraint(
            "length(baseline_sha256) = 64 "
            "AND baseline_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="baseline_sha256_canonical",
        ),
        CheckConstraint(
            "length(current_sha256) = 64 "
            "AND current_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="current_sha256_canonical",
        ),
        CheckConstraint("length(trim(storage_key)) > 0", name="storage_key_not_blank"),
        CheckConstraint(
            "substr(storage_key, 1, 1) <> '/' "
            "AND instr(storage_key, '\\\\') = 0 "
            "AND instr('/' || storage_key || '/', '/../') = 0",
            name="storage_key_project_relative",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["workspace_item_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_working_artifacts_project_status", "project_id", "content_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    workspace_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_size: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    current_size: Mapped[int] = mapped_column(Integer, nullable=False)
    current_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_status: Mapped[enums.WorkingContentStatus] = mapped_column(
        enum_type(enums.WorkingContentStatus, "working_content_status"), nullable=False
    )
    materialized_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class WorkingRevisionModel(Base):
    __tablename__ = "working_revisions"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_working_revisions_id_project"),
        UniqueConstraint(
            "working_artifact_id",
            "role",
            name="uq_working_revisions_artifact_role",
        ),
        UniqueConstraint(
            "project_id", "storage_key", name="uq_working_revisions_storage_key"
        ),
        CheckConstraint("size >= 0", name="size_nonnegative"),
        CheckConstraint(
            "length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'",
            name="sha256_canonical",
        ),
        CheckConstraint("length(trim(storage_key)) > 0", name="storage_key_not_blank"),
        CheckConstraint(
            "substr(storage_key, 1, 1) <> '/' "
            "AND instr(storage_key, '\\\\') = 0 "
            "AND instr('/' || storage_key || '/', '/../') = 0",
            name="storage_key_project_relative",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["working_artifact_id", "project_id"],
            ["working_artifacts.id", "working_artifacts.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_working_revisions_artifact", "working_artifact_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    working_artifact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[enums.WorkingRevisionRole] = mapped_column(
        enum_type(enums.WorkingRevisionRole, "working_revision_role"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_modified_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class RecoveryRunModel(Base):
    __tablename__ = "recovery_runs"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_recovery_runs_id_project"),
        CheckConstraint("detected_count >= 0", name="detected_count_nonnegative"),
        CheckConstraint("recovered_count >= 0", name="recovered_count_nonnegative"),
        CheckConstraint("failed_count >= 0", name="failed_count_nonnegative"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        Index("ix_recovery_runs_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[enums.RecoveryRunStatus] = mapped_column(
        enum_type(enums.RecoveryRunStatus, "recovery_run_status"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class RecoveryItemModel(Base):
    __tablename__ = "recovery_items"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_recovery_items_id_project"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["recovery_run_id", "project_id"],
            ["recovery_runs.id", "recovery_runs.project_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(trim(storage_key)) > 0", name="storage_key_not_blank"),
        CheckConstraint(
            "substr(storage_key, 1, 1) <> '/' "
            "AND instr(storage_key, '\\\\') = 0 "
            "AND instr('/' || storage_key || '/', '/../') = 0",
            name="storage_key_project_relative",
        ),
        Index("ix_recovery_items_run_status", "recovery_run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recovery_run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[enums.RecoveryItemKind] = mapped_column(
        enum_type(enums.RecoveryItemKind, "recovery_item_kind"), nullable=False
    )
    action: Mapped[enums.RecoveryAction] = mapped_column(
        enum_type(enums.RecoveryAction, "recovery_action"), nullable=False
    )
    status: Mapped[enums.RecoveryItemStatus] = mapped_column(
        enum_type(enums.RecoveryItemStatus, "recovery_item_status"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[Optional[str]] = mapped_column(String(128))
    size: Mapped[Optional[int]] = mapped_column(Integer)
    sha256: Mapped[Optional[str]] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_storage_key: Mapped[Optional[str]] = mapped_column(Text)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())


class SourceModel(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_sources_id_project"),
        UniqueConstraint("snapshot_id", name="uq_sources_snapshot"),
        CheckConstraint("length(trim(display_name)) > 0", name="display_name_not_blank"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["original_snapshots.id", "original_snapshots.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_sources_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[enums.SourceKind] = mapped_column(
        enum_type(enums.SourceKind, "source_kind"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[enums.SourceStatus] = mapped_column(
        enum_type(enums.SourceStatus, "source_status"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProcessingJobModel(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_processing_jobs_id_project"),
        CheckConstraint("warning_count >= 0", name="warning_count_nonnegative"),
        CheckConstraint("error_count >= 0", name="error_count_nonnegative"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["import_session_id", "project_id"],
            ["import_sessions.id", "import_sessions.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_processing_jobs_one_active_project",
            "project_id",
            unique=True,
            sqlite_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
        Index(
            "uq_processing_jobs_import_session",
            "import_session_id",
            unique=True,
            sqlite_where=text("import_session_id IS NOT NULL"),
        ),
        Index("ix_processing_jobs_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    import_session_id: Mapped[Optional[str]] = mapped_column(String(36))
    type: Mapped[enums.JobType] = mapped_column(
        enum_type(enums.JobType, "processing_job_type"), nullable=False
    )
    status: Mapped[enums.JobStatus] = mapped_column(
        enum_type(enums.JobStatus, "processing_job_status"), nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class NodeModel(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_nodes_id_project"),
        UniqueConstraint("id", "project_id", "source_id", name="uq_nodes_id_project_source"),
        CheckConstraint("depth >= 0", name="depth_nonnegative"),
        CheckConstraint(
            "declared_size IS NULL OR declared_size >= 0",
            name="declared_size_nonnegative",
        ),
        CheckConstraint(
            "detection_confidence IS NULL OR "
            "(detection_confidence >= 0 AND detection_confidence <= 1)",
            name="detection_confidence_range",
        ),
        CheckConstraint("length(logical_path) > 0", name="logical_path_not_empty"),
        CheckConstraint("length(discovery_key) > 0", name="discovery_key_not_empty"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["source_id", "project_id"],
            ["sources.id", "sources.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_nodes_project_source", "project_id", "source_id"),
        Index("ix_nodes_project_status", "project_id", "status"),
        Index("ix_nodes_project_format", "project_id", "format"),
        Index("ix_nodes_project_logical_path", "project_id", "logical_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[enums.NodeKind] = mapped_column(
        enum_type(enums.NodeKind, "node_kind"), nullable=False
    )
    format: Mapped[enums.NodeFormat] = mapped_column(
        enum_type(enums.NodeFormat, "node_format"), nullable=False
    )
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    logical_path: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[Optional[str]] = mapped_column(String(255))
    declared_size: Mapped[Optional[int]] = mapped_column(Integer)
    status: Mapped[enums.NodeProcessingStatus] = mapped_column(
        enum_type(enums.NodeProcessingStatus, "node_processing_status"), nullable=False
    )
    detection_method: Mapped[Optional[str]] = mapped_column(String(100))
    detection_confidence: Mapped[Optional[float]] = mapped_column(Float)
    detection_details: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    discovery_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class SourceRootModel(Base):
    __tablename__ = "source_roots"
    __table_args__ = (
        PrimaryKeyConstraint("source_id", name="pk_source_roots"),
        UniqueConstraint("node_id", name="uq_source_roots_node"),
        ForeignKeyConstraint(
            ["source_id", "project_id"],
            ["sources.id", "sources.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["node_id", "project_id", "source_id"],
            ["nodes.id", "nodes.project_id", "nodes.source_id"],
            ondelete="RESTRICT",
        ),
    )

    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)


class ArtifactModel(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_artifacts_id_project"),
        UniqueConstraint(
            "node_id", "role", "locator", name="uq_artifacts_node_role_locator"
        ),
        CheckConstraint("size IS NULL OR size >= 0", name="size_nonnegative"),
        CheckConstraint(
            "sha256 IS NULL OR "
            "(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*')",
            name="sha256_length",
        ),
        CheckConstraint(
            "(role = 'ORIGINAL_REFERENCE' AND scope = 'EXTERNAL_SOURCE') OR "
            "(role IN ('EXTRACTED_ARTIFACT', 'WORKSPACE_COPY') "
            "AND scope = 'PROJECT_WORKSPACE')",
            name="role_scope_compatible",
        ),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_artifacts_project_node", "project_id", "node_id"),
        Index("ix_artifacts_sha256", "sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[enums.ArtifactRole] = mapped_column(
        enum_type(enums.ArtifactRole, "artifact_role"), nullable=False
    )
    scope: Mapped[enums.ArtifactScope] = mapped_column(
        enum_type(enums.ArtifactScope, "artifact_scope"), nullable=False
    )
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    size: Mapped[Optional[int]] = mapped_column(Integer)
    sha256: Mapped[Optional[str]] = mapped_column(String(64))
    integrity_status: Mapped[enums.ArtifactIntegrityStatus] = mapped_column(
        enum_type(enums.ArtifactIntegrityStatus, "artifact_integrity_status"),
        nullable=False,
    )
    observed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class NodeRelationshipModel(Base):
    __tablename__ = "node_relationships"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_node_relationships_id_project"),
        UniqueConstraint(
            "project_id", "child_node_id", name="uq_node_relationships_structural_child"
        ),
        UniqueConstraint(
            "project_id",
            "parent_node_id",
            "type",
            "discovery_key",
            name="uq_node_relationships_discovery",
        ),
        CheckConstraint("parent_node_id <> child_node_id", name="different_nodes"),
        CheckConstraint("ordinal >= 0", name="ordinal_nonnegative"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["parent_node_id", "project_id", "source_id"],
            ["nodes.id", "nodes.project_id", "nodes.source_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["child_node_id", "project_id", "source_id"],
            ["nodes.id", "nodes.project_id", "nodes.source_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_job_id", "project_id"],
            ["processing_jobs.id", "processing_jobs.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_node_relationships_parent", "project_id", "parent_node_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    child_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    type: Mapped[enums.RelationshipType] = mapped_column(
        enum_type(enums.RelationshipType, "node_relationship_type"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    discovery_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_by_job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class SourceEntryLocatorModel(Base):
    __tablename__ = "source_entry_locators"
    __table_args__ = (
        PrimaryKeyConstraint("relationship_id", name="pk_source_entry_locators"),
        UniqueConstraint(
            "project_id", "child_node_id", name="uq_source_entry_locators_child"
        ),
        CheckConstraint(
            "(kind = 'SNAPSHOT_ENTRY' AND snapshot_entry_id IS NOT NULL "
            "AND member_ordinal IS NULL AND expected_name IS NULL "
            "AND member_role IS NULL) OR "
            "(kind IN ('ZIP_MEMBER', 'EML_PART', 'MSG_ATTACHMENT', "
            "'SEVEN_Z_MEMBER', 'RAR_MEMBER') AND snapshot_entry_id IS NULL "
            "AND member_ordinal IS NOT NULL AND expected_name IS NOT NULL "
            "AND member_role IS NOT NULL)",
            name="kind_matches_target",
        ),
        CheckConstraint(
            "member_ordinal IS NULL OR member_ordinal >= 0",
            name="member_ordinal_nonnegative",
        ),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["relationship_id", "project_id"],
            ["node_relationships.id", "node_relationships.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["child_node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_entry_id"],
            ["original_snapshot_entries.id"],
            ondelete="RESTRICT",
        ),
        Index("ix_source_entry_locators_child", "project_id", "child_node_id"),
    )

    relationship_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    child_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    kind: Mapped[enums.MaterializationLocatorKind] = mapped_column(
        enum_type(
            enums.MaterializationLocatorKind, "materialization_locator_kind"
        ),
        nullable=False,
    )
    snapshot_entry_id: Mapped[Optional[str]] = mapped_column(String(36))
    member_ordinal: Mapped[Optional[int]] = mapped_column(Integer)
    expected_name: Mapped[Optional[str]] = mapped_column(String(1024))
    member_role: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class LineageRecordModel(Base):
    __tablename__ = "node_lineage"
    __table_args__ = (
        PrimaryKeyConstraint(
            "project_id", "ancestor_node_id", "descendant_node_id", name="pk_node_lineage"
        ),
        CheckConstraint(
            "(distance = 0 AND ancestor_node_id = descendant_node_id) OR "
            "(distance > 0 AND ancestor_node_id <> descendant_node_id)",
            name="distance_matches_identity",
        ),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["ancestor_node_id", "project_id", "source_id"],
            ["nodes.id", "nodes.project_id", "nodes.source_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["descendant_node_id", "project_id", "source_id"],
            ["nodes.id", "nodes.project_id", "nodes.source_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_node_lineage_descendant", "project_id", "descendant_node_id", "distance"),
    )

    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ancestor_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    descendant_node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    distance: Mapped[int] = mapped_column(Integer, nullable=False)


class NodeMetadataModel(Base):
    __tablename__ = "node_metadata"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_node_metadata_id_project"),
        UniqueConstraint(
            "node_id", "namespace", "key", name="uq_node_metadata_key"
        ),
        CheckConstraint("length(trim(namespace)) > 0", name="namespace_not_blank"),
        CheckConstraint("length(trim(key)) > 0", name="key_not_blank"),
        CheckConstraint(
            "(value_type = 'TEXT' AND value_text IS NOT NULL "
            "AND value_integer IS NULL AND value_real IS NULL "
            "AND value_boolean IS NULL AND value_datetime IS NULL AND value_json IS NULL) OR "
            "(value_type = 'INTEGER' AND value_text IS NULL "
            "AND value_integer IS NOT NULL AND value_real IS NULL "
            "AND value_boolean IS NULL AND value_datetime IS NULL AND value_json IS NULL) OR "
            "(value_type = 'REAL' AND value_text IS NULL "
            "AND value_integer IS NULL AND value_real IS NOT NULL "
            "AND value_boolean IS NULL AND value_datetime IS NULL AND value_json IS NULL) OR "
            "(value_type = 'BOOLEAN' AND value_text IS NULL "
            "AND value_integer IS NULL AND value_real IS NULL "
            "AND value_boolean IS NOT NULL AND value_datetime IS NULL AND value_json IS NULL) OR "
            "(value_type = 'DATETIME' AND value_text IS NULL "
            "AND value_integer IS NULL AND value_real IS NULL "
            "AND value_boolean IS NULL AND value_datetime IS NOT NULL AND value_json IS NULL) OR "
            "(value_type = 'JSON' AND value_text IS NULL "
            "AND value_integer IS NULL AND value_real IS NULL "
            "AND value_boolean IS NULL AND value_datetime IS NULL AND value_json IS NOT NULL)",
            name="exactly_one_typed_value",
        ),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_node_metadata_node", "project_id", "node_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    namespace: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[enums.MetadataValueType] = mapped_column(
        enum_type(enums.MetadataValueType, "metadata_value_type"), nullable=False
    )
    value_text: Mapped[Optional[str]] = mapped_column(Text)
    value_integer: Mapped[Optional[int]] = mapped_column(Integer)
    value_real: Mapped[Optional[float]] = mapped_column(Float)
    value_boolean: Mapped[Optional[bool]] = mapped_column(Boolean)
    value_datetime: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    value_json: Mapped[Optional[Any]] = mapped_column(JSON(none_as_null=True))
    provenance: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class ProcessingAttemptModel(Base):
    __tablename__ = "processing_attempts"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_processing_attempts_id_project"),
        UniqueConstraint(
            "node_id", "attempt_number", name="uq_processing_attempts_node_number"
        ),
        CheckConstraint("attempt_number > 0", name="attempt_number_positive"),
        CheckConstraint(
            "(error_code IS NULL AND error_category IS NULL AND error_message IS NULL "
            "AND error_stage IS NULL AND error_retryable IS NULL) OR "
            "(error_code IS NOT NULL AND error_category IS NOT NULL "
            "AND error_stage IS NOT NULL AND error_message IS NOT NULL "
            "AND error_retryable IS NOT NULL)",
            name="error_fields_complete",
        ),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["job_id", "project_id"],
            ["processing_jobs.id", "processing_jobs.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        Index(
            "uq_processing_attempts_one_active_node",
            "project_id",
            "node_id",
            unique=True,
            sqlite_where=text("status IN ('QUEUED', 'RUNNING')"),
        ),
        Index("ix_processing_attempts_job", "project_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    node_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[enums.AttemptStatus] = mapped_column(
        enum_type(enums.AttemptStatus, "processing_attempt_status"), nullable=False
    )
    stage: Mapped[enums.ProcessingStage] = mapped_column(
        enum_type(enums.ProcessingStage, "processing_stage"), nullable=False
    )
    handler_name: Mapped[Optional[str]] = mapped_column(String(255))
    handler_version: Mapped[Optional[str]] = mapped_column(String(100))
    backend_name: Mapped[Optional[str]] = mapped_column(String(255))
    backend_version: Mapped[Optional[str]] = mapped_column(String(100))
    backend_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    queued_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    error_code: Mapped[Optional[enums.ErrorCode]] = mapped_column(
        enum_type(enums.ErrorCode, "processing_error_code")
    )
    error_category: Mapped[Optional[enums.ErrorCategory]] = mapped_column(
        enum_type(enums.ErrorCategory, "processing_error_category")
    )
    error_stage: Mapped[Optional[enums.ProcessingStage]] = mapped_column(
        enum_type(enums.ProcessingStage, "processing_error_stage")
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_retryable: Mapped[Optional[bool]] = mapped_column(Boolean)
    technical_reference: Mapped[Optional[str]] = mapped_column(String(255))


class ProcessingEventModel(Base):
    __tablename__ = "processing_events"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_processing_events_id_project"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["source_id", "project_id"],
            ["sources.id", "sources.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["node_id", "project_id"],
            ["nodes.id", "nodes.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["job_id", "project_id"],
            ["processing_jobs.id", "processing_jobs.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["attempt_id", "project_id"],
            ["processing_attempts.id", "processing_attempts.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["import_session_id", "project_id"],
            ["import_sessions.id", "import_sessions.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "project_id"],
            ["original_snapshots.id", "original_snapshots.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["workspace_item_id", "project_id"],
            ["workspace_items.id", "workspace_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["working_artifact_id", "project_id"],
            ["working_artifacts.id", "working_artifacts.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["context_section_id", "project_id"],
            ["context_sections.id", "context_sections.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["context_item_id", "project_id"],
            ["context_items.id", "context_items.project_id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["context_annotation_id", "project_id"],
            ["context_annotations.id", "context_annotations.project_id"],
            ondelete="RESTRICT",
        ),
        Index("ix_processing_events_project_time", "project_id", "occurred_at"),
        Index("ix_processing_events_node_time", "node_id", "occurred_at"),
        Index("ix_processing_events_job_time", "job_id", "occurred_at"),
        Index(
            "ix_processing_events_import_session_time",
            "import_session_id",
            "occurred_at",
        ),
        Index(
            "ix_processing_events_workspace_item_time",
            "workspace_item_id",
            "occurred_at",
        ),
        Index(
            "ix_processing_events_context_item_time",
            "context_item_id",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[enums.EventType] = mapped_column(
        enum_type(enums.EventType, "processing_event_type"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_id: Mapped[Optional[str]] = mapped_column(String(36))
    node_id: Mapped[Optional[str]] = mapped_column(String(36))
    job_id: Mapped[Optional[str]] = mapped_column(String(36))
    attempt_id: Mapped[Optional[str]] = mapped_column(String(36))
    import_session_id: Mapped[Optional[str]] = mapped_column(String(36))
    snapshot_id: Mapped[Optional[str]] = mapped_column(String(36))
    workspace_item_id: Mapped[Optional[str]] = mapped_column(String(36))
    working_artifact_id: Mapped[Optional[str]] = mapped_column(String(36))
    context_section_id: Mapped[Optional[str]] = mapped_column(String(36))
    context_item_id: Mapped[Optional[str]] = mapped_column(String(36))
    context_content_object_id: Mapped[Optional[str]] = mapped_column(String(36))
    context_revision_id: Mapped[Optional[str]] = mapped_column(String(36))
    context_annotation_id: Mapped[Optional[str]] = mapped_column(String(36))
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    severity: Mapped[enums.EventSeverity] = mapped_column(
        enum_type(enums.EventSeverity, "processing_event_severity"), nullable=False
    )
    previous_status: Mapped[Optional[str]] = mapped_column(String(64))
    new_status: Mapped[Optional[str]] = mapped_column(String(64))
    error_code: Mapped[Optional[enums.ErrorCode]] = mapped_column(
        enum_type(enums.ErrorCode, "processing_event_error_code")
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)


class AIAnalysisRunModel(Base):
    __tablename__ = "ai_analysis_runs"
    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_ai_runs_identity"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        CheckConstraint("coverage IN ('COMPLETE_INPUT','PARTIAL_INPUT')", name="coverage_valid"),
        CheckConstraint("estimated_max_usd >= 0", name="estimate_nonnegative"),
        CheckConstraint("workspace_revision_at_plan >= 0", name="workspace_revision_nonnegative"),
        Index("ix_ai_runs_project_started", "project_id", "started_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[AnalysisAction] = mapped_column(enum_type(AnalysisAction, "ai_action"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_revision_at_plan: Mapped[int] = mapped_column(Integer, nullable=False)
    coverage: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[AnalysisStatus] = mapped_column(enum_type(AnalysisStatus, "ai_run_status"), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime())
    estimated_max_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    error_code: Mapped[Optional[str]] = mapped_column(String(80))


class AIAnalysisInputModel(Base):
    __tablename__ = "ai_analysis_inputs"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "element_id"),
        ForeignKeyConstraint(["run_id", "project_id"],
                             ["ai_analysis_runs.id", "ai_analysis_runs.project_id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["element_id"], ["content_elements.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["context_revision_id", "project_id"],
                             ["context_revisions.id", "context_revisions.project_id"], ondelete="RESTRICT"),
        UniqueConstraint("run_id", "ordinal", name="uq_ai_inputs_order"),
        Index("ix_ai_inputs_revision", "project_id", "context_revision_id"),
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    element_id: Mapped[str] = mapped_column(String(36), nullable=False)
    context_revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    locator_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    locator_value: Mapped[str] = mapped_column(String(255), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class AIAnalysisClaimModel(Base):
    __tablename__ = "ai_analysis_claims"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "ordinal"),
        ForeignKeyConstraint(["run_id"], ["ai_analysis_runs.id"], ondelete="RESTRICT"),
        CheckConstraint("ordinal >= 0 AND length(trim(text)) > 0", name="claim_valid"),
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(200))
    time: Mapped[Optional[str]] = mapped_column(String(200))


class AIAnalysisCitationModel(Base):
    __tablename__ = "ai_analysis_citations"
    __table_args__ = (
        PrimaryKeyConstraint("run_id", "claim_ordinal", "element_id"),
        ForeignKeyConstraint(["run_id", "claim_ordinal"],
                             ["ai_analysis_claims.run_id", "ai_analysis_claims.ordinal"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["run_id", "element_id"],
                             ["ai_analysis_inputs.run_id", "ai_analysis_inputs.element_id"], ondelete="RESTRICT"),
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    claim_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    element_id: Mapped[str] = mapped_column(String(36), nullable=False)
