"""Read-only access to explicitly linked external paths."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

from pig.application.errors import ApplicationError
from pig.domain.detection import detect_node_format
from pig.domain.linked_project import DirectoryPage, LinkedEntry, LinkedPolicy


class LiveFileAccess:
    def __init__(self, policy: LinkedPolicy = LinkedPolicy()):
        self.policy = policy

    @staticmethod
    def checked(path: Path, *, directory: bool | None = None) -> Path:
        path = Path(path).absolute()
        try:
            for part in (path, *path.parents):
                info = part.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ApplicationError("UNSAFE_LINK", "关联路径包含链接或重解析点")
            info = path.lstat()
        except FileNotFoundError as exc:
            raise ApplicationError("FILE_MISSING", "关联文件或目录已不存在") from exc
        except OSError as exc:
            raise ApplicationError("FILE_UNREADABLE", "关联文件或目录不可访问") from exc
        if directory is True and not stat.S_ISDIR(info.st_mode):
            raise ApplicationError("INVALID_LINK", "请选择普通文件夹")
        if directory is False and not stat.S_ISREG(info.st_mode):
            raise ApplicationError("INVALID_LINK", "请选择普通文件")
        if directory is None and not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ApplicationError("INVALID_LINK", "只能关联普通文件或文件夹")
        return path.resolve(strict=True)

    def resolve(self, base: Path, relative: str, *, directory: bool | None = None) -> Path:
        if not relative:
            return self.checked(base, directory=directory)
        parts = relative.split("/")
        if (PurePosixPath(relative).is_absolute() or len(parts) > self.policy.maximum_depth
                or any(not part or part in (".", "..") or ":" in part or "\\" in part
                       for part in parts)):
            raise ApplicationError("UNSAFE_PATH", "关联路径不安全")
        root = self.checked(base, directory=True)
        target = self.checked(root.joinpath(*parts), directory=directory)
        if root not in target.parents:
            raise ApplicationError("UNSAFE_PATH", "文件超出关联目录")
        return target

    def children(self, folder: Path, key: str, *, offset: int = 0) -> DirectoryPage:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ApplicationError("INVALID_REQUEST", "目录页码无效")
        folder = self.checked(folder, directory=True)
        values = []
        skipped = 0
        has_more = False
        try:
            with os.scandir(folder) as scan:
                for entry in scan:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if entry.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                        continue
                    is_dir = stat.S_ISDIR(info.st_mode)
                    if not is_dir and not stat.S_ISREG(info.st_mode):
                        continue
                    if skipped < offset:
                        skipped += 1
                        continue
                    if len(values) == self.policy.maximum_children:
                        has_more = True
                        break
                    prefix = key if key.endswith((":", "/")) else key + "/"
                    values.append(LinkedEntry(prefix + entry.name, entry.name, Path(entry.path), is_dir))
        except OSError as exc:
            raise ApplicationError("FILE_UNREADABLE", "无法读取关联目录") from exc
        return DirectoryPage(tuple(sorted(values, key=lambda item: (not item.is_dir, item.name.casefold()))),
                             has_more, offset + len(values))

    @staticmethod
    def _signature(info):
        return info.st_size, info.st_mtime_ns, info.st_dev, info.st_ino

    def fingerprint(self, path: Path, *, control=None) -> tuple[int, str]:
        for _ in range(2):
            path = self.checked(path, directory=False)
            try:
                before = path.stat()
                if before.st_size > self.policy.maximum_file_bytes:
                    raise ApplicationError("FILE_TOO_LARGE", "文件超过当前大小上限")
                digest = hashlib.sha256()
                count = 0
                with path.open("rb") as source:
                    if self._signature(os.fstat(source.fileno())) != self._signature(before):
                        continue
                    for chunk in iter(lambda: source.read(self.policy.chunk_bytes), b""):
                        if control is not None:
                            control.checkpoint()
                        count += len(chunk)
                        if count > self.policy.maximum_file_bytes:
                            raise ApplicationError("FILE_TOO_LARGE", "文件超过当前大小上限")
                        digest.update(chunk)
                after = self.checked(path, directory=False).stat()
                if self._signature(before) == self._signature(after) and count == after.st_size:
                    return count, digest.hexdigest()
            except FileNotFoundError as exc:
                raise ApplicationError("FILE_MISSING", "关联文件已不存在") from exc
            except OSError as exc:
                raise ApplicationError("FILE_UNREADABLE", "文件不可读取") from exc
        raise ApplicationError("FILE_UNSTABLE", "文件读取期间发生变化，请稍后重试")

    def format(self, path: Path):
        path = self.checked(path, directory=False)
        with path.open("rb") as stream:
            return detect_node_format(path.name, stream.read(8)).format

    def stream(self, path: Path, writer, *, control=None):
        path = self.checked(path, directory=False)
        before = path.stat()
        with path.open("rb") as source:
            if self._signature(os.fstat(source.fileno())) != self._signature(before):
                raise ApplicationError("FILE_CHANGED_DURING_CAPTURE", "固定期间文件内容发生变化")
            count = 0
            for chunk in iter(lambda: source.read(self.policy.chunk_bytes), b""):
                if control is not None:
                    control.checkpoint()
                count += len(chunk)
                if count > self.policy.maximum_file_bytes:
                    raise ApplicationError("FILE_TOO_LARGE", "文件超过当前大小上限")
                writer.write(chunk)
        after = self.checked(path, directory=False).stat()
        if self._signature(before) != self._signature(after) or count != before.st_size:
            raise ApplicationError("FILE_CHANGED_DURING_CAPTURE", "固定期间文件内容发生变化")
