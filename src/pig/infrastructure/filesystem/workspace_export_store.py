from __future__ import annotations

import hashlib
import os
import shutil
import stat
import zipfile
from pathlib import Path

from pig.application.errors import ApplicationError
from pig.application.operation_control import (
    OperationControl,
    OperationStage,
    ensure_operation_control,
)
from pig.application.ports import (
    StoredWorkspaceExport,
    WorkspaceExportDirectory,
    WorkspaceExportEntry,
)
from pig.domain.enums import ErrorCode, WorkspaceExportKind
from pig.infrastructure.filesystem.workbench_storage import LocalInspectionCache


class LocalWorkspaceExportStore:
    """Atomically publish user-selected Workspace bytes outside the Project."""

    @staticmethod
    def available_space(destination: Path) -> int:
        target = Path(destination).expanduser().resolve(strict=False)
        return int(shutil.disk_usage(target.parent.resolve(strict=True)).free)

    def write(
        self,
        destination: Path,
        operation_id: str,
        entries: tuple[WorkspaceExportEntry, ...],
        directories: tuple[WorkspaceExportDirectory, ...] = (),
        *,
        export_kind: WorkspaceExportKind,
        allow_replace: bool,
        maximum_total_size: int,
        chunk_size: int,
        control: OperationControl | None = None,
    ) -> StoredWorkspaceExport:
        operation = ensure_operation_control(control)
        if (
            export_kind == WorkspaceExportKind.FILE
            and (len(entries) != 1 or directories)
        ) or (
            export_kind == WorkspaceExportKind.ZIP and not entries
        ):
            raise ApplicationError("INVALID_REQUEST", "invalid export entry selection")
        LocalInspectionCache._safe_id(operation_id)
        target = Path(destination).expanduser().resolve(strict=False)
        parent = target.parent.resolve(strict=True)
        if parent.is_symlink() or not parent.is_dir():
            raise ApplicationError(
                ErrorCode.EXPORT_DESTINATION_INVALID.value,
                "export destination parent must be a regular directory",
            )
        try:
            existing = target.lstat()
        except FileNotFoundError:
            existing = None
        if existing is not None:
            if stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode):
                raise ApplicationError(
                    ErrorCode.EXPORT_DESTINATION_INVALID.value,
                    "unsafe export destination will not be replaced",
                )
            if export_kind == WorkspaceExportKind.DIRECTORY:
                raise ApplicationError(
                    ErrorCode.EXPORT_DESTINATION_INVALID.value,
                    "an existing directory export destination is never merged or replaced",
                )
            if not allow_replace:
                raise ApplicationError(
                    "EXPORT_CONFIRMATION_REQUIRED",
                    "replacing an existing export requires confirmation",
                )
        staging = parent / f".{target.name}.{operation_id}.pig-export.tmp"
        if staging.exists() or staging.is_symlink():
            raise ApplicationError("EXPORT_STAGING_COLLISION", "export staging exists")
        try:
            operation.start_stage(
                OperationStage.EXPORT_WRITE,
                total_count=len(entries),
                total_bytes=sum(entry.size for entry in entries),
                current_item=(None if not entries else entries[0].relative_path),
            )
            operation.checkpoint()
            if export_kind == WorkspaceExportKind.ZIP:
                total = self._write_zip(
                    staging,
                    entries,
                    directories,
                    maximum_total_size,
                    chunk_size,
                    operation,
                )
                operation.start_stage(
                    OperationStage.FINALIZING,
                    total_bytes=staging.stat().st_size,
                    current_item=target.name,
                )
                sha256, size = self._hash_file(staging, chunk_size, operation)
                if size != total:
                    raise ApplicationError(
                        ErrorCode.EXPORT_FAILED.value,
                        "export size changed before publication",
                    )
            elif export_kind == WorkspaceExportKind.DIRECTORY:
                size, sha256 = self._write_directory(
                    staging,
                    entries,
                    directories,
                    maximum_total_size,
                    chunk_size,
                    operation,
                )
            else:
                size, sha256 = self._copy_file(
                    entries[0],
                    staging,
                    maximum_total_size,
                    chunk_size,
                    synchronize=True,
                    control=operation,
                )
                operation.advance(count=1, current_item=entries[0].relative_path)
            operation.checkpoint()
            if operation.latest is None or operation.latest.stage != OperationStage.FINALIZING:
                operation.start_stage(
                    OperationStage.FINALIZING,
                    current_item=target.name,
                    cancellable=False,
                )
            else:
                operation.update(cancellable=False, current_item=target.name)
            if existing is None and not allow_replace:
                if export_kind == WorkspaceExportKind.DIRECTORY:
                    try:
                        os.replace(staging, target)
                    except FileExistsError as exc:
                        raise ApplicationError(
                            "EXPORT_CONFIRMATION_REQUIRED",
                            "export destination appeared during publication",
                        ) from exc
                else:
                    try:
                        os.link(staging, target)
                        staging.unlink()
                    except FileExistsError as exc:
                        raise ApplicationError(
                            "EXPORT_CONFIRMATION_REQUIRED",
                            "export destination appeared during publication",
                        ) from exc
            else:
                os.replace(staging, target)
            return StoredWorkspaceExport(
                path=target,
                size=size,
                sha256=sha256,
                entry_count=len(entries),
            )
        except BaseException:
            if staging.exists() and staging.is_dir() and not staging.is_symlink():
                shutil.rmtree(staging)
            else:
                staging.unlink(missing_ok=True)
            raise

    def _write_zip(
        self,
        staging: Path,
        entries: tuple[WorkspaceExportEntry, ...],
        directories: tuple[WorkspaceExportDirectory, ...],
        maximum_total_size: int,
        chunk_size: int,
        control: OperationControl,
    ) -> int:
        total_input = 0
        with zipfile.ZipFile(
            staging, mode="x", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as archive:
            for directory in directories:
                control.checkpoint()
                relative = self._safe_relative(directory.relative_path)
                archive.writestr(relative.rstrip("/") + "/", b"")
            for entry in entries:
                control.checkpoint()
                total_input += entry.size
                if total_input > maximum_total_size:
                    raise ApplicationError(
                        ErrorCode.MAX_TOTAL_EXPANDED_SIZE_EXCEEDED.value,
                        "export selection exceeds the configured resource limit",
                )
                relative = self._safe_relative(entry.relative_path)
                before = self._regular_stat(entry.source_path)
                digest = hashlib.sha256()
                size = 0
                with entry.source_path.open("rb") as source, archive.open(
                    relative, mode="w", force_zip64=True
                ) as output:
                    while True:
                        control.checkpoint()
                        block = source.read(chunk_size)
                        if not block:
                            break
                        size += len(block)
                        if size > maximum_total_size:
                            raise ApplicationError(
                                ErrorCode.MAX_TOTAL_EXPANDED_SIZE_EXCEEDED.value,
                                "export selection exceeds the configured resource limit",
                            )
                        output.write(block)
                        digest.update(block)
                        control.advance(
                            byte_count=len(block), current_item=entry.relative_path
                        )
                self._verify_copied_source(entry, before, size, digest.hexdigest())
                control.advance(count=1, current_item=entry.relative_path)
        return staging.stat().st_size

    def _write_directory(
        self,
        staging: Path,
        entries: tuple[WorkspaceExportEntry, ...],
        directories: tuple[WorkspaceExportDirectory, ...],
        maximum_total_size: int,
        chunk_size: int,
        control: OperationControl,
    ) -> tuple[int, str]:
        staging.mkdir()
        for directory in sorted(
            directories, key=lambda value: (value.relative_path.count("/"), value.relative_path)
        ):
            control.checkpoint()
            relative = self._safe_relative(directory.relative_path)
            staging.joinpath(*relative.split("/")).mkdir(parents=True, exist_ok=True)
        total = 0
        digest = hashlib.sha256()
        for entry in sorted(entries, key=lambda value: value.relative_path):
            control.checkpoint()
            relative = self._safe_relative(entry.relative_path)
            total += entry.size
            if total > maximum_total_size:
                raise ApplicationError(
                    ErrorCode.MAX_TOTAL_EXPANDED_SIZE_EXCEEDED.value,
                    "export selection exceeds the configured resource limit",
                )
            output = staging.joinpath(*relative.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            self._copy_file(
                entry,
                output,
                maximum_total_size,
                chunk_size,
                synchronize=False,
                control=control,
            )
            control.advance(count=1, current_item=entry.relative_path)
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(entry.sha256.encode("ascii"))
            digest.update(b"\0")
        for directory in sorted(value.relative_path for value in directories):
            digest.update(self._safe_relative(directory).encode("utf-8"))
            digest.update(b"/\0")
        return total, digest.hexdigest()

    def _copy_file(
        self,
        entry: WorkspaceExportEntry,
        staging: Path,
        maximum_total_size: int,
        chunk_size: int,
        *,
        synchronize: bool,
        control: OperationControl,
    ) -> tuple[int, str]:
        if entry.size > maximum_total_size:
            raise ApplicationError(
                ErrorCode.MAX_TOTAL_EXPANDED_SIZE_EXCEEDED.value,
                "export selection exceeds the configured resource limit",
            )
        before = self._regular_stat(entry.source_path)
        digest = hashlib.sha256()
        size = 0
        with entry.source_path.open("rb") as source, staging.open("xb") as output:
            while True:
                control.checkpoint()
                block = source.read(chunk_size)
                if not block:
                    break
                size += len(block)
                if size > maximum_total_size:
                    raise ApplicationError(
                        ErrorCode.MAX_TOTAL_EXPANDED_SIZE_EXCEEDED.value,
                        "export selection exceeds the configured resource limit",
                    )
                output.write(block)
                digest.update(block)
                control.advance(
                    byte_count=len(block), current_item=entry.relative_path
                )
            output.flush()
            if synchronize:
                os.fsync(output.fileno())
        sha256 = digest.hexdigest()
        self._verify_copied_source(entry, before, size, sha256)
        return size, sha256

    def _verify_copied_source(
        self,
        entry: WorkspaceExportEntry,
        before,
        size: int,
        sha256: str,
    ) -> None:
        after = self._regular_stat(entry.source_path)
        if (
            self._fact(before) != self._fact(after)
            or size != entry.size
            or sha256 != entry.sha256
        ):
            raise ApplicationError(
                ErrorCode.EXPORT_FAILED.value,
                "export source changed or does not match its expected fingerprint",
            )

    @staticmethod
    def _safe_relative(value: str) -> str:
        normalized = value.replace("\\", "/")
        parts = normalized.split("/")
        if (
            not normalized
            or normalized.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or ":" in parts[0]
        ):
            raise ApplicationError(
                ErrorCode.EXPORT_DESTINATION_INVALID.value,
                "invalid Workspace-relative export path",
            )
        return "/".join(parts)

    @staticmethod
    def _regular_stat(path: Path):
        try:
            value = path.lstat()
        except OSError as exc:
            raise ApplicationError(
                ErrorCode.EXPORT_FAILED.value, "export source is unavailable"
            ) from exc
        if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
            raise ApplicationError(
                ErrorCode.EXPORT_FAILED.value,
                "export source is not a regular non-link file",
            )
        return value

    @staticmethod
    def _fact(value) -> tuple[int, int, int, int]:
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns

    @staticmethod
    def _hash_file(
        path: Path,
        chunk_size: int,
        control: OperationControl,
    ) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            while True:
                control.checkpoint()
                block = source.read(chunk_size)
                if not block:
                    break
                size += len(block)
                digest.update(block)
                control.advance(byte_count=len(block), current_item=path.name)
        return digest.hexdigest(), size
