from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable

from pig.application.errors import ApplicationError
from pig.application.ports import StoredContextObject
from pig.domain.enums import ErrorCode


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _CaptureWriter:
    def __init__(self, raw: BinaryIO, maximum: int, control) -> None:
        self._raw = raw
        self._maximum = maximum
        self._control = control
        self._digest = hashlib.sha256()
        self.size = 0

    def write(self, value: bytes) -> int:
        if self._control is not None:
            self._control.checkpoint()
        if self.size + len(value) > self._maximum:
            raise ApplicationError(
                ErrorCode.MAX_SINGLE_FILE_SIZE_EXCEEDED.value,
                "Context capture exceeds the configured file-size limit",
                {"maximum": self._maximum},
            )
        written = self._raw.write(value)
        self.size += written
        self._digest.update(value[:written])
        if self._control is not None:
            self._control.advance(byte_count=written)
        return written

    @property
    def sha256(self) -> str:
        return self._digest.hexdigest()


class LocalContextObjectStore:
    """Per-Project, content-addressed, immutable Context object storage."""

    def verified_path(self, project_path: Path, object_key: str, *,
                      expected_size: int, expected_sha256: str) -> Path:
        project = Path(project_path).resolve(strict=True)
        relative = PurePosixPath(object_key)
        if (
            not _SHA256.fullmatch(expected_sha256)
            or relative.is_absolute()
            or relative.parts != ("context", "objects", expected_sha256[:2], expected_sha256)
        ):
            raise ApplicationError("UNSAFE_WORKSPACE", "invalid Context object key")
        target = project.joinpath(*relative.parts)
        self._safe_parent(project, target.parent, create=False)
        self._verify_existing(target, expected_size, expected_sha256)
        return target

    def available_space(self, project_path: Path) -> int:
        project = Path(project_path).resolve(strict=True)
        return shutil.disk_usage(project).free

    def capture(
        self,
        project_path: Path,
        operation_id: str,
        producer: Callable[[BinaryIO], None],
        *,
        maximum: int,
        control=None,
    ) -> StoredContextObject:
        project = Path(project_path).resolve(strict=True)
        if not _SAFE_ID.fullmatch(operation_id):
            raise ApplicationError("INVALID_STORAGE_ID", "unsafe generated identity")
        staging = project / ".staging" / "context" / operation_id / "content"
        self._safe_parent(project, staging.parent, create=True)
        if staging.exists() or staging.is_symlink():
            raise ApplicationError("CONTEXT_STAGING_COLLISION", "capture staging already exists")
        writer = None
        try:
            with staging.open("xb") as raw:
                writer = _CaptureWriter(raw, maximum, control)
                producer(writer)  # type: ignore[arg-type]
                if control is not None:
                    control.checkpoint()
                raw.flush()
                os.fsync(raw.fileno())
            digest = writer.sha256
            object_key = str(PurePosixPath("context") / "objects" / digest[:2] / digest)
            destination = project.joinpath(*PurePosixPath(object_key).parts)
            self._safe_parent(project, destination.parent, create=True)
            reused = False
            try:
                os.link(staging, destination)
                staging.unlink()
            except FileExistsError:
                self._verify_existing(destination, writer.size, digest)
                reused = True
                staging.unlink(missing_ok=True)
            return StoredContextObject(
                object_key=object_key,
                path=destination,
                size=writer.size,
                sha256=digest,
                reused=reused,
            )
        except BaseException:
            staging.unlink(missing_ok=True)
            raise
        finally:
            self._remove_empty(staging.parent, project / ".staging")

    def inspect(
        self,
        project_path: Path,
        *,
        known_object_keys: frozenset[str],
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        project = Path(project_path).resolve(strict=True)
        root = project / "context" / "objects"
        disk_keys: set[str] = set()
        if root.exists() and not root.is_symlink():
            for prefix in root.iterdir():
                if prefix.is_symlink() or not prefix.is_dir():
                    continue
                for candidate in prefix.iterdir():
                    if candidate.is_symlink() or not candidate.is_file():
                        continue
                    relative = candidate.relative_to(project).as_posix()
                    disk_keys.add(relative)
        return (
            tuple(sorted(disk_keys - known_object_keys)),
            tuple(sorted(known_object_keys - disk_keys)),
        )

    def remove(
        self,
        project_path: Path,
        object_key: str,
        *,
        expected_size: int,
        expected_sha256: str,
    ) -> bool:
        project = Path(project_path).resolve(strict=True)
        relative = PurePosixPath(object_key)
        if (
            relative.is_absolute()
            or len(relative.parts) != 4
            or relative.parts[:2] != ("context", "objects")
            or relative.parts[2] != expected_sha256[:2]
            or relative.parts[3] != expected_sha256
            or not _SHA256.fullmatch(expected_sha256)
        ):
            raise ApplicationError("UNSAFE_WORKSPACE", "invalid Context object key")
        target = project.joinpath(*relative.parts)
        try:
            self._verify_existing(target, expected_size, expected_sha256)
        except FileNotFoundError:
            return False
        target.unlink()
        self._remove_empty(target.parent, project / "context" / "objects")
        return True

    @staticmethod
    def _verify_existing(path: Path, expected_size: int, expected_sha256: str) -> None:
        value = path.lstat()
        if stat.S_ISLNK(value.st_mode) or not stat.S_ISREG(value.st_mode):
            raise ApplicationError(
                ErrorCode.WORKSPACE_INTEGRITY_FAILED.value,
                "Context object destination is not a regular non-link file",
            )
        if value.st_size != expected_size or not _SHA256.fullmatch(path.name):
            raise ApplicationError(
                ErrorCode.ARTIFACT_HASH_MISMATCH.value,
                "Existing Context object does not match its content address",
            )
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected_sha256:
            raise ApplicationError(
                ErrorCode.ARTIFACT_HASH_MISMATCH.value,
                "Existing Context object failed integrity verification",
            )

    @staticmethod
    def _safe_parent(project: Path, parent: Path, *, create: bool) -> None:
        current = project
        for part in parent.relative_to(project).parts:
            current = current / part
            if current.is_symlink():
                raise ApplicationError("UNSAFE_WORKSPACE", "Context path traverses a link")
            if current.exists() and not current.is_dir():
                raise ApplicationError("UNSAFE_WORKSPACE", "Context parent is not a directory")
            if create and not current.exists():
                current.mkdir()

    @staticmethod
    def _remove_empty(path: Path, stop: Path) -> None:
        current = path
        while current != stop.parent and current.exists() and current.is_dir():
            if any(current.iterdir()):
                break
            current.rmdir()
            if current == stop:
                break
            current = current.parent
