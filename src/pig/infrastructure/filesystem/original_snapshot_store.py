from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from collections import deque
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Optional
from uuid import uuid4

from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationControl, ensure_operation_control
from pig.application.ports import (
    CapturedOriginalArtifact,
    CapturedSnapshot,
    CapturedSnapshotEntry,
    SnapshotInput,
    SnapshotInputEntry,
)
from pig.domain.entities import OriginalArtifact
from pig.domain.enums import ErrorCode, OriginalSnapshotEntryKind, SourceKind
from pig.domain.snapshot_policy import SnapshotImportPolicy
from pig.infrastructure.filesystem.staging_manifest import StagingOperationManifest


Clock = Callable[[], datetime]
IdGenerator = Callable[[], str]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")
_WINDOWS_REPARSE_POINT = 0x400


@dataclass(frozen=True, slots=True)
class _PathFact:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class _Member:
    path: Path
    name: str
    kind: OriginalSnapshotEntryKind
    fact: _PathFact


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


def _is_link_like(stat_result: os.stat_result) -> bool:
    attributes = int(getattr(stat_result, "st_file_attributes", 0))
    return stat.S_ISLNK(stat_result.st_mode) or bool(
        attributes & _WINDOWS_REPARSE_POINT
    )


def _fact(stat_result: os.stat_result) -> _PathFact:
    return _PathFact(
        device=int(stat_result.st_dev),
        inode=int(stat_result.st_ino),
        mode=int(stat_result.st_mode),
        size=int(stat_result.st_size),
        modified_ns=int(stat_result.st_mtime_ns),
    )


class LocalOriginalSnapshotWriteSession(AbstractContextManager):
    def __init__(
        self,
        project_path: Path,
        import_session_id: str,
        snapshot_id: str,
        *,
        project_id: str,
        clock: Clock,
        id_generator: IdGenerator,
    ) -> None:
        self._project_path = project_path.resolve(strict=True)
        self._session_id = self._validate_id(import_session_id)
        self._snapshot_id = self._validate_id(snapshot_id)
        self._project_id = self._validate_id(project_id)
        self._clock = clock
        self._new_id = id_generator
        self._staging_root = (
            self._project_path
            / ".staging"
            / "imports"
            / self._session_id
            / self._snapshot_id
        )
        self._destination = self._project_path / "originals" / self._snapshot_id
        self._captured = False
        self._published = False
        self._completed = False
        self._manifest: StagingOperationManifest | None = None

    def __enter__(self) -> "LocalOriginalSnapshotWriteSession":
        self._assert_project_root()
        self._manifest = StagingOperationManifest(
            self._project_path,
            self._snapshot_id,
            "SNAPSHOT_IMPORT",
            self._project_id,
            target_keys=(f"originals/{self._snapshot_id}",),
        )
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if not self._completed:
            self._rollback()

    def capture(
        self,
        source: SnapshotInput,
        *,
        policy: SnapshotImportPolicy,
        prior_session_size: int,
        control: OperationControl | None = None,
    ) -> CapturedSnapshot:
        if self._captured:
            raise ApplicationError(
                code="INVALID_SNAPSHOT_STATE",
                message="snapshot session captured more than once",
            )
        self._ensure_staging_root()
        assert self._manifest is not None
        self._manifest.update("WRITING")
        operation = ensure_operation_control(control)
        operation.checkpoint()
        if source.kind == SourceKind.FILE:
            captured = self._capture_file_input(
                source,
                policy=policy,
                prior_session_size=prior_session_size,
                control=operation,
            )
        else:
            captured = self._capture_folder_input(
                source,
                policy=policy,
                prior_session_size=prior_session_size,
                control=operation,
            )
        self._make_staged_files_read_only(captured.artifacts)
        self._manifest.update("WRITTEN", expected_size=captured.total_size)
        self._captured = True
        return captured

    def publish(self) -> None:
        if not self._captured or self._published:
            raise ApplicationError(
                code="INVALID_SNAPSHOT_STATE",
                message="snapshot must be captured exactly once before publish",
            )
        originals = self._project_path / "originals"
        self._ensure_controlled_parent(originals)
        if not originals.exists():
            originals.mkdir()
        if originals.is_symlink() or not originals.is_dir():
            raise ApplicationError(
                code="UNSAFE_WORKSPACE",
                message="Original storage root is not a controlled directory",
            )
        if self._destination.exists() or self._destination.is_symlink():
            raise ApplicationError(
                code="SNAPSHOT_COLLISION",
                message="snapshot destination already exists",
                details={"snapshot_id": self._snapshot_id},
            )
        try:
            os.replace(self._staging_root, self._destination)
        except OSError as exc:
            raise ApplicationError(
                code=ErrorCode.SNAPSHOT_PUBLISH_FAILED.value,
                message="snapshot could not be atomically published",
                details={"snapshot_id": self._snapshot_id},
            ) from exc
        self._remove_empty_staging_parents()
        self._published = True
        assert self._manifest is not None
        self._manifest.update("PUBLISHED")

    def complete(self) -> None:
        if not self._published:
            raise ApplicationError(
                code="INVALID_SNAPSHOT_STATE",
                message="snapshot must be published before completion",
            )
        self._completed = True
        assert self._manifest is not None
        self._manifest.update("DATABASE_COMMITTED")
        self._manifest.complete()

    def _capture_file_input(
        self,
        source: SnapshotInput,
        *,
        policy: SnapshotImportPolicy,
        prior_session_size: int,
        control: OperationControl,
    ) -> CapturedSnapshot:
        artifact_id = self._validated_generated_id()
        entry_id = self._validated_generated_id()
        current = self._safe_lstat(source.path)
        if _is_link_like(current) or not stat.S_ISREG(current.st_mode):
            self._raise_input_changed(source.path)
        artifact = self._copy_file(
            source.path,
            artifact_id,
            policy=policy,
            prior_total=prior_session_size,
            control=control,
            current_item=source.display_name,
            expected_fact=_fact(current),
            synchronize=True,
        )
        entry = CapturedSnapshotEntry(
            id=entry_id,
            parent_entry_id=None,
            artifact_id=artifact_id,
            kind=OriginalSnapshotEntryKind.FILE,
            original_name=source.display_name,
            ordinal=0,
            created_at=self._clock(),
        )
        return CapturedSnapshot(
            root_entry_id=entry_id,
            artifacts=(artifact,),
            entries=(entry,),
            total_size=artifact.size,
        )

    def _capture_folder_input(
        self,
        source: SnapshotInput,
        *,
        policy: SnapshotImportPolicy,
        prior_session_size: int,
        control: OperationControl,
    ) -> CapturedSnapshot:
        root_id = self._validated_generated_id()
        entries: list[CapturedSnapshotEntry] = [
            CapturedSnapshotEntry(
                id=root_id,
                parent_entry_id=None,
                artifact_id=None,
                kind=OriginalSnapshotEntryKind.FOLDER,
                original_name=source.display_name,
                ordinal=0,
                created_at=self._clock(),
            )
        ]
        artifacts: list[CapturedOriginalArtifact] = []
        observed: dict[Path, _PathFact] = {}
        directory_members: dict[
            Path, tuple[tuple[str, OriginalSnapshotEntryKind], ...]
        ] = {}
        root_stat = self._safe_lstat(source.path)
        if _is_link_like(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
            self._raise_input_changed(source.path)
        observed[source.path] = _fact(root_stat)
        prepared_by_parent: dict[tuple[str, ...], list[SnapshotInputEntry]] = {}
        for prepared in source.entries[1:]:
            prepared_by_parent.setdefault(prepared.relative_parts[:-1], []).append(
                prepared
            )
        queue = deque([(source.path, root_id, ())])
        total_size = 0
        control.advance(count=1, current_item=source.display_name)

        while queue:
            control.checkpoint()
            directory, parent_entry_id, relative_parent = queue.popleft()
            members = (
                self._scan_directory(directory)
                if not source.entries
                else [
                    _Member(
                        path=source.path.joinpath(*prepared.relative_parts),
                        name=prepared.relative_parts[-1],
                        kind=prepared.kind,
                        fact=_PathFact(0, 0, 0, prepared.size, 0),
                    )
                    for prepared in prepared_by_parent.get(relative_parent, ())
                ]
            )
            if source.entries:
                current_members = []
                for member in members:
                    current = self._safe_lstat(member.path)
                    if _is_link_like(current):
                        self._raise_input_changed(member.path)
                    current_kind = (
                        OriginalSnapshotEntryKind.FOLDER
                        if stat.S_ISDIR(current.st_mode)
                        else (
                            OriginalSnapshotEntryKind.FILE
                            if stat.S_ISREG(current.st_mode)
                            else None
                        )
                    )
                    if current_kind != member.kind:
                        self._raise_input_changed(member.path)
                    current_members.append(
                        _Member(
                            path=member.path,
                            name=member.name,
                            kind=member.kind,
                            fact=_fact(current),
                        )
                    )
                members = current_members
            for member in members:
                observed[member.path] = member.fact
            directory_members[directory] = tuple(
                (member.name, member.kind) for member in members
            )
            for ordinal, member in enumerate(members):
                control.checkpoint()
                if len(entries) >= policy.max_entry_count:
                    raise ApplicationError(
                        code=ErrorCode.MAX_IMPORT_ENTRY_COUNT_EXCEEDED.value,
                        message="folder snapshot exceeds the configured entry limit",
                        details={"maximum": policy.max_entry_count},
                    )
                entry_id = self._validated_generated_id()
                if member.kind == OriginalSnapshotEntryKind.FOLDER:
                    entries.append(
                        CapturedSnapshotEntry(
                            id=entry_id,
                            parent_entry_id=parent_entry_id,
                            artifact_id=None,
                            kind=member.kind,
                            original_name=member.name,
                            ordinal=ordinal,
                            created_at=self._clock(),
                        )
                    )
                    queue.append(
                        (
                            member.path,
                            entry_id,
                            relative_parent + (member.name,),
                        )
                    )
                    control.advance(count=1, current_item=member.name)
                    continue
                artifact_id = self._validated_generated_id()
                artifact = self._copy_file(
                    member.path,
                    artifact_id,
                    policy=policy,
                    prior_total=prior_session_size + total_size,
                    control=control,
                    current_item=member.name,
                    expected_fact=member.fact,
                    synchronize=False,
                )
                total_size += artifact.size
                artifacts.append(artifact)
                entries.append(
                    CapturedSnapshotEntry(
                        id=entry_id,
                        parent_entry_id=parent_entry_id,
                        artifact_id=artifact_id,
                        kind=member.kind,
                        original_name=member.name,
                        ordinal=ordinal,
                        created_at=self._clock(),
                    )
                )

        self._verify_folder_unchanged(observed, directory_members)
        return CapturedSnapshot(
            root_entry_id=root_id,
            artifacts=tuple(artifacts),
            entries=tuple(entries),
            total_size=total_size,
        )

    def _copy_file(
        self,
        source: Path,
        artifact_id: str,
        *,
        policy: SnapshotImportPolicy,
        prior_total: int,
        control: OperationControl,
        current_item: str,
        expected_fact: _PathFact | None = None,
        synchronize: bool = True,
    ) -> CapturedOriginalArtifact:
        before = (
            _fact(self._safe_lstat(source))
            if expected_fact is None
            else expected_fact
        )
        if stat.S_ISLNK(before.mode):
            raise ApplicationError(
                code=ErrorCode.SYMLINK_BLOCKED.value,
                message="symbolic links and reparse points are not imported",
                details={"path": str(source)},
            )
        if not stat.S_ISREG(before.mode):
            raise ApplicationError(
                code=ErrorCode.UNSUPPORTED_INPUT_TYPE.value,
                message="snapshot input member is not a regular file",
                details={"path": str(source)},
            )
        if before.size > policy.max_single_file_size:
            raise ApplicationError(
                code=ErrorCode.MAX_SINGLE_FILE_SIZE_EXCEEDED.value,
                message="input file exceeds the configured single-file limit",
                details={"path": str(source), "maximum": policy.max_single_file_size},
            )
        if prior_total + before.size > policy.max_total_size:
            raise ApplicationError(
                code=ErrorCode.MAX_IMPORT_TOTAL_SIZE_EXCEEDED.value,
                message="snapshot import exceeds the configured total-size limit",
                details={"maximum": policy.max_total_size},
            )
        destination = self._artifact_path(artifact_id)
        destination.parent.mkdir()
        digest = hashlib.sha256()
        written = 0
        report_chunks = before.size > policy.io_chunk_size
        try:
            with source.open("rb") as input_stream, destination.open("xb") as output:
                opened = os.fstat(input_stream.fileno())
                if _is_link_like(opened) or _fact(opened) != before:
                    self._raise_input_changed(source)
                while True:
                    control.checkpoint()
                    chunk = input_stream.read(policy.io_chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > policy.max_single_file_size:
                        raise ApplicationError(
                            code=ErrorCode.MAX_SINGLE_FILE_SIZE_EXCEEDED.value,
                            message="input file grew beyond the configured limit",
                            details={"path": str(source)},
                        )
                    if prior_total + written > policy.max_total_size:
                        raise ApplicationError(
                            code=ErrorCode.MAX_IMPORT_TOTAL_SIZE_EXCEEDED.value,
                            message="snapshot import exceeds the configured total-size limit",
                        )
                    output.write(chunk)
                    digest.update(chunk)
                    if report_chunks:
                        control.advance(
                            byte_count=len(chunk), current_item=current_item
                        )
                output.flush()
                if synchronize:
                    os.fsync(output.fileno())
                after_open = os.fstat(input_stream.fileno())
        except PermissionError as exc:
            destination.unlink(missing_ok=True)
            raise ApplicationError(
                code=ErrorCode.INPUT_UNREADABLE.value,
                message="input file is not readable",
                details={"path": str(source)},
            ) from exc
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        after_path = self._safe_lstat(source)
        if (
            before != _fact(after_open)
            or before != _fact(after_path)
            or written != before.size
        ):
            destination.unlink(missing_ok=True)
            self._raise_input_changed(source)
        control.advance(
            count=1,
            byte_count=0 if report_chunks else written,
            current_item=current_item,
        )
        return CapturedOriginalArtifact(
            id=artifact_id,
            storage_key=self.storage_key(self._snapshot_id, artifact_id),
            size=written,
            sha256=digest.hexdigest(),
            observed_modified_at=datetime.fromtimestamp(
                before.modified_ns / 1_000_000_000, timezone.utc
            ),
        )

    def _scan_directory(self, directory: Path) -> list[_Member]:
        members: list[_Member] = []
        try:
            with os.scandir(directory) as iterator:
                values = sorted(iterator, key=lambda entry: entry.name)
        except PermissionError as exc:
            raise ApplicationError(
                code=ErrorCode.INPUT_UNREADABLE.value,
                message="input folder is not readable",
                details={"path": str(directory)},
            ) from exc
        for value in values:
            path = Path(value.path)
            # On Windows DirEntry.stat() may report zero device/inode values,
            # while a later lstat() reports the stable file identity. Use one
            # observation mechanism for both capture and re-verification.
            stat_result = self._safe_lstat(path)
            if _is_link_like(stat_result):
                raise ApplicationError(
                    code=ErrorCode.SYMLINK_BLOCKED.value,
                    message="folder snapshot contains a symbolic link or reparse point",
                    details={"path": str(path)},
                )
            if stat.S_ISDIR(stat_result.st_mode):
                kind = OriginalSnapshotEntryKind.FOLDER
            elif stat.S_ISREG(stat_result.st_mode):
                kind = OriginalSnapshotEntryKind.FILE
            else:
                raise ApplicationError(
                    code=ErrorCode.UNSUPPORTED_INPUT_TYPE.value,
                    message="folder snapshot contains an unsupported filesystem entry",
                    details={"path": str(path)},
                )
            members.append(
                _Member(path=path, name=value.name, kind=kind, fact=_fact(stat_result))
            )
        return members

    def _verify_folder_unchanged(
        self,
        observed: dict[Path, _PathFact],
        directory_members: dict[
            Path, tuple[tuple[str, OriginalSnapshotEntryKind], ...]
        ],
    ) -> None:
        for path, expected in observed.items():
            try:
                current = self._safe_lstat(path)
            except ApplicationError:
                self._raise_input_changed(path)
            if _is_link_like(current) or _fact(current) != expected:
                self._raise_input_changed(path)
        for directory, expected in directory_members.items():
            actual = self._scan_directory_membership(directory)
            if actual != expected:
                self._raise_input_changed(directory)

    @staticmethod
    def _scan_directory_membership(
        directory: Path,
    ) -> tuple[tuple[str, OriginalSnapshotEntryKind], ...]:
        try:
            with os.scandir(directory) as iterator:
                values = sorted(iterator, key=lambda entry: entry.name)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            raise ApplicationError(
                code=ErrorCode.INPUT_CHANGED_DURING_COPY.value,
                message="snapshot folder membership could not be verified",
                details={"path": str(directory)},
            ) from exc
        result = []
        for value in values:
            if value.is_symlink():
                LocalOriginalSnapshotWriteSession._raise_input_changed(
                    Path(value.path)
                )
            if value.is_dir(follow_symlinks=False):
                kind = OriginalSnapshotEntryKind.FOLDER
            elif value.is_file(follow_symlinks=False):
                kind = OriginalSnapshotEntryKind.FILE
            else:
                LocalOriginalSnapshotWriteSession._raise_input_changed(
                    Path(value.path)
                )
            result.append((value.name, kind))
        return tuple(result)

    def _artifact_path(self, artifact_id: str) -> Path:
        return self._staging_root / "objects" / artifact_id / "content"

    def _make_staged_files_read_only(
        self, artifacts: tuple[CapturedOriginalArtifact, ...]
    ) -> None:
        for artifact in artifacts:
            path = self._artifact_path(artifact.id)
            path.chmod(stat.S_IREAD)

    def _ensure_staging_root(self) -> None:
        if self._staging_root.exists() or self._staging_root.is_symlink():
            raise ApplicationError(
                code="SNAPSHOT_STAGING_COLLISION",
                message="snapshot staging directory already exists",
            )
        self._ensure_controlled_parent(self._staging_root.parent)
        self._staging_root.mkdir()
        (self._staging_root / "objects").mkdir()

    def _ensure_controlled_parent(self, target: Path) -> None:
        relative = target.relative_to(self._project_path)
        current = self._project_path
        for segment in relative.parts:
            current = current / segment
            if current.is_symlink():
                raise ApplicationError(
                    code="UNSAFE_WORKSPACE",
                    message="snapshot path traverses a symbolic link",
                    details={"path": str(current)},
                )
            if current.exists() and not current.is_dir():
                raise ApplicationError(
                    code="UNSAFE_WORKSPACE",
                    message="snapshot path component is not a directory",
                    details={"path": str(current)},
                )
            if not current.exists():
                current.mkdir()

    def _assert_project_root(self) -> None:
        stat_result = os.lstat(self._project_path)
        if _is_link_like(stat_result) or not stat.S_ISDIR(stat_result.st_mode):
            raise ApplicationError(
                code="UNSAFE_WORKSPACE",
                message="Project workspace must be a controlled directory",
            )

    def _rollback(self) -> None:
        if self._staging_root.exists() and not self._staging_root.is_symlink():
            self._remove_tree(self._staging_root)
        if self._published and self._destination.exists() and not self._destination.is_symlink():
            self._remove_tree(self._destination)
        self._remove_empty_staging_parents()
        originals = self._project_path / "originals"
        if originals.exists() and originals.is_dir() and not any(originals.iterdir()):
            originals.rmdir()
        if self._manifest is not None:
            self._manifest.complete()

    def _remove_empty_staging_parents(self) -> None:
        current = self._staging_root.parent
        stop = self._project_path / ".staging"
        while current != self._project_path:
            if current.is_symlink() or not current.exists() or any(current.iterdir()):
                break
            current.rmdir()
            if current == stop:
                break
            current = current.parent

    @staticmethod
    def _remove_tree(path: Path) -> None:
        def make_writable_and_retry(function, value, exc_info) -> None:
            Path(value).chmod(stat.S_IWRITE)
            function(value)

        shutil.rmtree(path, onerror=make_writable_and_retry)

    def _validated_generated_id(self) -> str:
        return self._validate_id(self._new_id())

    @staticmethod
    def _validate_id(value: str) -> str:
        if not _SAFE_ID.fullmatch(value):
            raise ApplicationError(
                code="INVALID_STORAGE_ID",
                message="snapshot storage identity is not a safe path segment",
            )
        return value

    @staticmethod
    def _safe_lstat(path: Path) -> os.stat_result:
        try:
            return os.lstat(path)
        except FileNotFoundError as exc:
            raise ApplicationError(
                code=ErrorCode.INPUT_NOT_FOUND.value,
                message="snapshot input disappeared",
                details={"path": str(path)},
            ) from exc
        except PermissionError as exc:
            raise ApplicationError(
                code=ErrorCode.INPUT_UNREADABLE.value,
                message="snapshot input is not readable",
                details={"path": str(path)},
            ) from exc
        except OSError as exc:
            raise ApplicationError(
                code=ErrorCode.INPUT_UNREADABLE.value,
                message="snapshot input could not be inspected",
                details={"path": str(path)},
            ) from exc

    @staticmethod
    def _raise_input_changed(path: Path) -> None:
        raise ApplicationError(
            code=ErrorCode.INPUT_CHANGED_DURING_COPY.value,
            message="snapshot input changed while it was being copied",
            details={"path": str(path)},
        )

    @staticmethod
    def storage_key(snapshot_id: str, artifact_id: str) -> str:
        safe_snapshot = LocalOriginalSnapshotWriteSession._validate_id(snapshot_id)
        safe_artifact = LocalOriginalSnapshotWriteSession._validate_id(artifact_id)
        return str(
            PurePosixPath("originals")
            / safe_snapshot
            / "objects"
            / safe_artifact
            / "content"
        )


class LocalOriginalSnapshotStore:
    def __init__(
        self,
        *,
        clock: Clock = _utc_now,
        id_generator: IdGenerator = _new_id,
    ) -> None:
        self._clock = clock
        self._new_id = id_generator
        self._project_id_context = "UNKNOWN"

    def set_project_context(self, project_id: str) -> None:
        self._project_id_context = LocalOriginalSnapshotWriteSession._validate_id(
            project_id
        )

    def preflight(
        self,
        project_path: Path,
        input_path: Path,
        *,
        policy: SnapshotImportPolicy,
        control: OperationControl | None = None,
    ) -> SnapshotInput:
        operation = ensure_operation_control(control)
        operation.checkpoint()
        project = Path(project_path)
        candidate = Path(input_path)
        if not project.is_absolute() or not candidate.is_absolute():
            raise ApplicationError(
                code="INVALID_REQUEST",
                message="Project and input paths must be absolute",
            )
        project = project.resolve(strict=True)
        self._assert_no_link_components(candidate)
        stat_result = LocalOriginalSnapshotWriteSession._safe_lstat(candidate)
        if _is_link_like(stat_result):
            raise ApplicationError(
                code=ErrorCode.SYMLINK_BLOCKED.value,
                message="symbolic links and reparse points are not imported",
                details={"path": str(candidate)},
            )
        resolved = candidate.resolve(strict=True)
        if resolved.is_relative_to(project) or project.is_relative_to(resolved):
            raise ApplicationError(
                code=ErrorCode.INPUT_OVERLAPS_PROJECT.value,
                message="snapshot input must not overlap the Project workspace",
                details={"path": str(candidate)},
            )
        if stat.S_ISREG(stat_result.st_mode):
            kind = SourceKind.FILE
            entry_count = 1
            total_size = int(stat_result.st_size)
            self._validate_preflight_size(
                candidate, total_size, total_size, policy
            )
            entries = (
                self._input_entry((), OriginalSnapshotEntryKind.FILE, stat_result),
            )
        elif stat.S_ISDIR(stat_result.st_mode):
            kind = SourceKind.FOLDER
            entry_count, total_size, entries = self._measure_folder(
                resolved,
                root_stat=stat_result,
                policy=policy,
                control=operation,
            )
        else:
            raise ApplicationError(
                code=ErrorCode.UNSUPPORTED_INPUT_TYPE.value,
                message="snapshot input must be a regular file or folder",
                details={"path": str(candidate)},
            )
        display_name = candidate.name
        if not display_name or any(
            ord(character) < 32 or ord(character) == 127
            for character in display_name
        ):
            raise ApplicationError(
                code=ErrorCode.INVALID_FILENAME.value,
                message="snapshot input has an invalid display name",
                details={"path": str(candidate)},
            )
        return SnapshotInput(
            path=resolved,
            locator=resolved.as_uri(),
            kind=kind,
            display_name=display_name,
            entry_count=entry_count,
            total_size=total_size,
            entries=entries,
        )

    @staticmethod
    def available_space(project_path: Path) -> int:
        return int(shutil.disk_usage(Path(project_path).resolve(strict=True)).free)

    def _measure_folder(
        self,
        root: Path,
        *,
        root_stat: os.stat_result,
        policy: SnapshotImportPolicy,
        control: OperationControl,
    ) -> tuple[int, int, tuple[SnapshotInputEntry, ...]]:
        entry_count = 1
        total_size = 0
        entries = [
            self._input_entry((), OriginalSnapshotEntryKind.FOLDER, root_stat)
        ]
        queue = deque([root])
        while queue:
            control.checkpoint()
            directory = queue.popleft()
            for member in self._scan_members_for_preflight(directory):
                control.checkpoint()
                entry_count += 1
                if entry_count > policy.max_entry_count:
                    raise ApplicationError(
                        code=ErrorCode.MAX_IMPORT_ENTRY_COUNT_EXCEEDED.value,
                        message="folder snapshot exceeds the configured entry limit",
                        details={"maximum": policy.max_entry_count},
                    )
                if member.kind == OriginalSnapshotEntryKind.FOLDER:
                    queue.append(member.path)
                else:
                    self._validate_preflight_size(
                        member.path,
                        member.fact.size,
                        total_size + member.fact.size,
                        policy,
                    )
                    total_size += member.fact.size
                entries.append(
                    SnapshotInputEntry(
                        relative_parts=member.path.relative_to(root).parts,
                        kind=member.kind,
                        size=member.fact.size,
                    )
                )
        return entry_count, total_size, tuple(entries)

    @staticmethod
    def _input_entry(
        relative_parts: tuple[str, ...],
        kind: OriginalSnapshotEntryKind,
        stat_result: os.stat_result,
    ) -> SnapshotInputEntry:
        fact = _fact(stat_result)
        return SnapshotInputEntry(
            relative_parts=relative_parts,
            kind=kind,
            size=fact.size,
        )

    def _scan_members_for_preflight(self, directory: Path) -> list[_Member]:
        try:
            with os.scandir(directory) as iterator:
                values = sorted(iterator, key=lambda entry: entry.name)
        except PermissionError as exc:
            raise ApplicationError(
                code=ErrorCode.INPUT_UNREADABLE.value,
                message="input folder is not readable",
                details={"path": str(directory)},
            ) from exc
        members: list[_Member] = []
        for value in values:
            path = Path(value.path)
            try:
                current = value.stat(follow_symlinks=False)
            except FileNotFoundError as exc:
                raise ApplicationError(
                    code=ErrorCode.INPUT_NOT_FOUND.value,
                    message="snapshot input disappeared during preflight",
                    details={"path": str(path)},
                ) from exc
            except (PermissionError, OSError) as exc:
                raise ApplicationError(
                    code=ErrorCode.INPUT_UNREADABLE.value,
                    message="snapshot input could not be inspected during preflight",
                    details={"path": str(path)},
                ) from exc
            if _is_link_like(current):
                raise ApplicationError(
                    code=ErrorCode.SYMLINK_BLOCKED.value,
                    message="folder snapshot contains a symbolic link or reparse point",
                    details={"path": str(path)},
                )
            if stat.S_ISDIR(current.st_mode):
                kind = OriginalSnapshotEntryKind.FOLDER
            elif stat.S_ISREG(current.st_mode):
                kind = OriginalSnapshotEntryKind.FILE
            else:
                raise ApplicationError(
                    code=ErrorCode.UNSUPPORTED_INPUT_TYPE.value,
                    message="folder snapshot contains an unsupported filesystem entry",
                    details={"path": str(path)},
                )
            members.append(_Member(path=path, name=value.name, kind=kind, fact=_fact(current)))
        return members

    @staticmethod
    def _validate_preflight_size(
        path: Path,
        single_size: int,
        total_size: int,
        policy: SnapshotImportPolicy,
    ) -> None:
        if single_size > policy.max_single_file_size:
            raise ApplicationError(
                code=ErrorCode.MAX_SINGLE_FILE_SIZE_EXCEEDED.value,
                message="input file exceeds the configured single-file limit",
                details={"path": str(path), "maximum": policy.max_single_file_size},
            )
        if total_size > policy.max_total_size:
            raise ApplicationError(
                code=ErrorCode.MAX_IMPORT_TOTAL_SIZE_EXCEEDED.value,
                message="snapshot import exceeds the configured total-size limit",
                details={"maximum": policy.max_total_size},
            )

    def begin(
        self,
        project_path: Path,
        import_session_id: str,
        snapshot_id: str,
    ) -> LocalOriginalSnapshotWriteSession:
        return self.begin_with_project(
            project_path,
            import_session_id,
            snapshot_id,
            project_id=self._project_id_context,
        )

    def begin_with_project(
        self,
        project_path: Path,
        import_session_id: str,
        snapshot_id: str,
        *,
        project_id: str,
    ) -> LocalOriginalSnapshotWriteSession:
        return LocalOriginalSnapshotWriteSession(
            project_path,
            import_session_id,
            snapshot_id,
            project_id=project_id,
            clock=self._clock,
            id_generator=self._new_id,
        )

    def verify_artifact(
        self,
        project_path: Path,
        artifact: OriginalArtifact,
        *,
        chunk_size: int,
    ) -> None:
        if chunk_size <= 0:
            raise ApplicationError(
                code="INVALID_REQUEST", message="chunk_size must be positive"
            )
        expected = LocalOriginalSnapshotWriteSession.storage_key(
            artifact.snapshot_id, artifact.id
        )
        if artifact.storage_key != expected:
            raise ApplicationError(
                code=ErrorCode.ARTIFACT_HASH_MISMATCH.value,
                message="Original Artifact storage key does not match its identity",
            )
        root = Path(project_path).resolve(strict=True)
        path = root.joinpath(*PurePosixPath(artifact.storage_key).parts)
        current = root
        for segment in path.relative_to(root).parts:
            current = current / segment
            try:
                current_stat = os.lstat(current)
            except FileNotFoundError as exc:
                raise ApplicationError(
                    code=ErrorCode.ARTIFACT_MISSING.value,
                    message="Original Artifact is missing",
                    details={"artifact_id": artifact.id},
                ) from exc
            except PermissionError as exc:
                raise ApplicationError(
                    code=ErrorCode.ARTIFACT_UNREADABLE.value,
                    message="Original Artifact path is unreadable",
                    details={"artifact_id": artifact.id},
                ) from exc
            if _is_link_like(current_stat):
                raise ApplicationError(
                    code=ErrorCode.SYMLINK_BLOCKED.value,
                    message="Original Artifact path traverses a link",
                )
        digest = hashlib.sha256()
        size = 0
        try:
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(chunk_size)
                    if not chunk:
                        break
                    size += len(chunk)
                    digest.update(chunk)
        except PermissionError as exc:
            raise ApplicationError(
                code=ErrorCode.ARTIFACT_UNREADABLE.value,
                message="Original Artifact is unreadable",
                details={"artifact_id": artifact.id},
            ) from exc
        except OSError as exc:
            raise ApplicationError(
                code=ErrorCode.ARTIFACT_UNREADABLE.value,
                message="Original Artifact could not be read",
                details={"artifact_id": artifact.id},
            ) from exc
        if size != artifact.size or digest.hexdigest() != artifact.sha256:
            raise ApplicationError(
                code=ErrorCode.ARTIFACT_HASH_MISMATCH.value,
                message="Original Artifact fingerprint does not match",
                details={"artifact_id": artifact.id},
            )

    def artifact_path(
        self, project_path: Path, artifact: OriginalArtifact
    ) -> Path:
        expected = LocalOriginalSnapshotWriteSession.storage_key(
            artifact.snapshot_id, artifact.id
        )
        if artifact.storage_key != expected:
            raise ApplicationError(
                code=ErrorCode.ARTIFACT_HASH_MISMATCH.value,
                message="Original Artifact storage key does not match its identity",
            )
        root = Path(project_path).resolve(strict=True)
        path = root.joinpath(*PurePosixPath(expected).parts)
        current = root
        for segment in path.relative_to(root).parts:
            current = current / segment
            try:
                value = os.lstat(current)
            except FileNotFoundError as exc:
                raise ApplicationError(
                    ErrorCode.ARTIFACT_MISSING.value,
                    "Original Artifact is missing",
                    {"artifact_id": artifact.id},
                ) from exc
            if _is_link_like(value):
                raise ApplicationError(
                    ErrorCode.SYMLINK_BLOCKED.value,
                    "Original Artifact path traverses a link",
                )
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise ApplicationError(
                ErrorCode.ARTIFACT_UNREADABLE.value,
                "Original Artifact is not a regular file",
            )
        return path

    @staticmethod
    def _assert_no_link_components(path: Path) -> None:
        absolute = path.absolute()
        current = Path(absolute.anchor)
        for segment in absolute.parts[1:]:
            current = current / segment
            try:
                value = os.lstat(current)
            except FileNotFoundError:
                break
            except PermissionError as exc:
                raise ApplicationError(
                    code=ErrorCode.INPUT_UNREADABLE.value,
                    message="snapshot input path cannot be inspected",
                    details={"path": str(current)},
                ) from exc
            if _is_link_like(value):
                raise ApplicationError(
                    code=ErrorCode.SYMLINK_BLOCKED.value,
                    message="snapshot input path traverses a link",
                    details={"path": str(current)},
                )
