"""Bounded, no-overwrite publication of immutable Context bytes."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

from pig.application.errors import ApplicationError
from pig.application.operation_control import OperationStage
from pig.application.ports import ContextPackFile, PublishedContextPack


_IDENTITY = re.compile(r"^[0-9a-f-]{36}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class LocalContextPackStore:
    def validate_destination(self, project_path: Path, destination: Path) -> Path:
        raw = Path(destination).expanduser()
        if not raw.is_absolute() or raw.name in ("", ".", ".."):
            raise ApplicationError("CONTEXT_PACK_DESTINATION_INVALID", "an absolute destination is required")
        for component in (raw.parent, *raw.parent.parents):
            if component.is_symlink():
                raise ApplicationError("CONTEXT_PACK_DESTINATION_INVALID", "destination traverses a symbolic link")
        parent = raw.parent.resolve(strict=True)
        if not parent.is_dir():
            raise ApplicationError("CONTEXT_PACK_DESTINATION_INVALID", "destination parent is not a directory")
        target = parent / raw.name
        try:
            target.relative_to(Path(project_path).resolve(strict=True))
        except ValueError:
            pass
        else:
            raise ApplicationError("CONTEXT_PACK_DESTINATION_INVALID", "destination must be outside the Project")
        if os.path.lexists(target):
            raise ApplicationError("CONTEXT_PACK_DESTINATION_EXISTS", "destination already exists")
        return target

    @staticmethod
    def available_space(destination: Path) -> int:
        return shutil.disk_usage(Path(destination).parent).free

    def verify_source(self, project_path: Path, entry: ContextPackFile, *, chunk_size: int, control=None) -> Path:
        if chunk_size <= 0 or not _HASH.fullmatch(entry.sha256) or entry.size_bytes < 0:
            raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "invalid Context object identity")
        relative = PurePosixPath(entry.object_key)
        if relative.parts != ("context", "objects", entry.sha256[:2], entry.sha256):
            raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object key does not match its hash")
        root = Path(project_path).resolve(strict=True)
        target = root
        for part in relative.parts:
            target = target / part
            if target.is_symlink():
                raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object path traverses a link")
        before = target.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != entry.size_bytes:
            raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object size or type changed")
        digest = hashlib.sha256()
        with target.open("rb") as source:
            for block in iter(lambda: source.read(chunk_size), b""):
                if control is not None:
                    control.checkpoint()
                digest.update(block)
                if control is not None:
                    control.advance(byte_count=len(block), current_item=entry.relative_path)
        after = target.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or digest.hexdigest() != entry.sha256:
            raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object hash changed")
        return target

    def publish(
        self, project_path: Path, destination: Path, export_id: str,
        files: tuple[ContextPackFile, ...], readme: bytes, manifest: bytes,
        *, pack_format: str, chunk_size: int, control=None,
    ) -> PublishedContextPack:
        if not _IDENTITY.fullmatch(export_id) or pack_format not in ("DIRECTORY", "ZIP"):
            raise ApplicationError("INVALID_REQUEST", "invalid Context Pack publication identity")
        target = self.validate_destination(project_path, destination)
        staging = target.parent / f".{target.name}.{export_id}.pig-pack.tmp"
        if os.path.lexists(staging):
            raise ApplicationError("CONTEXT_PACK_STAGING_COLLISION", "Context Pack staging already exists")
        used: set[str] = {"README.md", "manifest.json"}
        for entry in files:
            self._relative(entry.relative_path)
            if entry.relative_path in used:
                raise ApplicationError("CONTEXT_PACK_PATH_COLLISION", "duplicate pack path")
            used.add(entry.relative_path)
        try:
            if control is not None:
                control.start_stage(OperationStage.EXPORT_WRITE, total_count=len(files), total_bytes=sum(value.size_bytes for value in files))
            if pack_format == "DIRECTORY":
                staging.mkdir()
                self._write_directory(project_path, staging, files, readme, manifest, chunk_size, control)
                digest, size = self._directory_digest(staging, chunk_size)
            else:
                self._write_zip(project_path, staging, files, readme, manifest, chunk_size, control)
                digest, size = self._hash_file(staging, chunk_size)
            if control is not None:
                control.start_stage(OperationStage.EXPORT_VERIFICATION, total_count=len(files))
            self._verify_staged(staging, files, readme, manifest, pack_format, chunk_size, control)
            if control is not None:
                control.checkpoint()
                control.start_stage(OperationStage.FINALIZING, cancellable=False)
            self.validate_destination(project_path, target)
            self._rename_noreplace(staging, target)
            return PublishedContextPack(destination_path=target, sha256=digest, size_bytes=size)
        finally:
            if staging.is_dir() and not staging.is_symlink():
                shutil.rmtree(staging)
            elif os.path.lexists(staging):
                staging.unlink()

    def remove_owned_publication(self, destination: Path, export_id: str, expected_sha256: str) -> bool:
        target = Path(destination)
        if not _IDENTITY.fullmatch(export_id) or not _HASH.fullmatch(expected_sha256) or target.is_symlink():
            return False
        try:
            if target.is_dir():
                manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            elif target.is_file():
                with zipfile.ZipFile(target) as archive:
                    manifest = json.loads(archive.read("manifest.json"))
            else:
                return not os.path.lexists(target)
            if manifest.get("export_id") != export_id:
                return False
            if target.is_dir():
                digest, _ = self._directory_digest(target, 1024 * 1024)
                if digest != expected_sha256:
                    return False
                shutil.rmtree(target)
            else:
                digest, _ = self._hash_file(target, 1024 * 1024)
                if digest != expected_sha256:
                    return False
                target.unlink()
            return True
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            return False

    def _write_directory(self, project, staging, files, readme, manifest, chunk_size, control):
        for name, data in (("README.md", readme), ("manifest.json", manifest)):
            with (staging / name).open("xb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
        for entry in files:
            if control is not None:
                control.checkpoint()
            source = self.verify_source(project, entry, chunk_size=chunk_size)
            target = staging.joinpath(*PurePosixPath(entry.relative_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open("rb") as reader, target.open("xb") as writer:
                digest = hashlib.sha256()
                size = 0
                for block in iter(lambda: reader.read(chunk_size), b""):
                    if control is not None:
                        control.checkpoint()
                    writer.write(block)
                    digest.update(block)
                    size += len(block)
                    if control is not None:
                        control.advance(byte_count=len(block), current_item=entry.relative_path)
                writer.flush()
                os.fsync(writer.fileno())
            if (size, digest.hexdigest()) != (entry.size_bytes, entry.sha256):
                raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object changed during copy")
            if control is not None:
                control.advance(count=1, current_item=entry.relative_path)

    def _write_zip(self, project, staging, files, readme, manifest, chunk_size, control):
        with zipfile.ZipFile(staging, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("README.md", readme)
            archive.writestr("manifest.json", manifest)
            for entry in files:
                if control is not None:
                    control.checkpoint()
                source = self.verify_source(project, entry, chunk_size=chunk_size)
                digest = hashlib.sha256()
                size = 0
                with source.open("rb") as reader, archive.open(entry.relative_path, "w", force_zip64=True) as writer:
                    for block in iter(lambda: reader.read(chunk_size), b""):
                        if control is not None:
                            control.checkpoint()
                        writer.write(block)
                        digest.update(block)
                        size += len(block)
                        if control is not None:
                            control.advance(byte_count=len(block), current_item=entry.relative_path)
                if (size, digest.hexdigest()) != (entry.size_bytes, entry.sha256):
                    raise ApplicationError("CONTEXT_PACK_CONTENT_INVALID", "Context object changed during copy")
                if control is not None:
                    control.advance(count=1, current_item=entry.relative_path)
        with staging.open("rb+") as output:
            os.fsync(output.fileno())

    @staticmethod
    def _relative(value: str) -> None:
        path = PurePosixPath(value)
        if (path.is_absolute() or len(path.parts) != 3 or path.parts[0] != "files"
                or any(part in ("", ".", "..") or "\\" in part or ":" in part for part in path.parts)):
            raise ApplicationError("CONTEXT_PACK_PATH_INVALID", "unsafe relative pack path")

    @staticmethod
    def _hash_file(path: Path, chunk_size: int) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as source:
            for block in iter(lambda: source.read(chunk_size), b""):
                digest.update(block)
                size += len(block)
        return digest.hexdigest(), size

    def _directory_digest(self, root: Path, chunk_size: int) -> tuple[str, int]:
        digest = hashlib.sha256()
        total = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            file_hash, size = self._hash_file(path, chunk_size)
            digest.update(f"{relative}\0{size}\0{file_hash}\n".encode("utf-8"))
            total += size
        return digest.hexdigest(), total

    def _verify_staged(self, staging, files, readme, manifest, pack_format, chunk_size, control):
        if pack_format == "DIRECTORY":
            if (staging / "README.md").read_bytes() != readme or (staging / "manifest.json").read_bytes() != manifest:
                raise ApplicationError("CONTEXT_PACK_VERIFY_FAILED", "pack metadata changed in staging")
            for entry in files:
                if control is not None:
                    control.checkpoint()
                path = staging.joinpath(*PurePosixPath(entry.relative_path).parts)
                digest, size = self._hash_file(path, chunk_size)
                if (digest, size) != (entry.sha256, entry.size_bytes):
                    raise ApplicationError("CONTEXT_PACK_VERIFY_FAILED", "pack entry changed in staging")
                if control is not None:
                    control.advance(count=1, current_item=entry.relative_path)
            return
        with zipfile.ZipFile(staging) as archive:
            if archive.read("README.md") != readme or archive.read("manifest.json") != manifest:
                raise ApplicationError("CONTEXT_PACK_VERIFY_FAILED", "ZIP metadata changed in staging")
            for entry in files:
                if control is not None:
                    control.checkpoint()
                digest = hashlib.sha256()
                size = 0
                with archive.open(entry.relative_path) as source:
                    for block in iter(lambda: source.read(chunk_size), b""):
                        if control is not None:
                            control.checkpoint()
                        digest.update(block)
                        size += len(block)
                if (digest.hexdigest(), size) != (entry.sha256, entry.size_bytes):
                    raise ApplicationError("CONTEXT_PACK_VERIFY_FAILED", "ZIP entry changed in staging")
                if control is not None:
                    control.advance(count=1, current_item=entry.relative_path)

    @staticmethod
    def _rename_noreplace(source: Path, target: Path) -> None:
        if sys.platform == "win32":
            try:
                os.rename(source, target)  # Win32 MoveFile fails when target exists.
            except FileExistsError as exc:
                raise ApplicationError("CONTEXT_PACK_DESTINATION_EXISTS", "destination appeared during publication") from exc
            return
        libc = ctypes.CDLL(None, use_errno=True)
        if sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
            result = libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
        elif sys.platform == "darwin" and hasattr(libc, "renamex_np"):
            result = libc.renamex_np(os.fsencode(source), os.fsencode(target), 4)
        else:
            raise ApplicationError("CONTEXT_PACK_ATOMIC_UNSUPPORTED", "no-replace directory publication unavailable")
        if result != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise ApplicationError("CONTEXT_PACK_DESTINATION_EXISTS", "destination appeared during publication")
            raise OSError(error, os.strerror(error), str(target))
