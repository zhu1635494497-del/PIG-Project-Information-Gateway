"""Use cases for live-linked Projects; no SQL or external-file writes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pig.application.errors import ApplicationError
from pig.domain.linked_project import Experience, FixedRevision, LinkedEntry, Observation
from pig.domain.open_policy import OpenPolicy


class LinkedProjectService:
    def __init__(self, *, store, files, objects, opener, open_policy: OpenPolicy = OpenPolicy()):
        self._store = store
        self._files = files
        self._objects = objects
        self._opener = opener
        self._open_policy = open_policy

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def create(self, folder: Path, *, name: str | None = None):
        root = self._files.checked(folder, directory=True)
        label = (name or root.name).strip()
        if not label or len(label) > 255 or any(ord(char) < 32 for char in label):
            raise ApplicationError("INVALID_PROJECT", "项目名称无效")
        metadata = self._store.root.absolute()
        if root == metadata or root in metadata.parents or metadata in root.parents:
            raise ApplicationError("METADATA_ROOT_CONFLICT", "请选择与 PIG 元数据分离的资料目录")
        return self._store.create(str(uuid4()), label, root, self._now())

    def get(self, project_id):
        return self._store.get(project_id)

    def projects(self):
        return self._store.projects()

    def link(self, project_id: str, path: Path):
        source = self._files.checked(path)
        project = self.get(project_id)
        if source == project.root or project.root in source.parents:
            raise ApplicationError("ALREADY_LINKED", "文件已属于项目关联目录")
        if source == self._store.root or self._store.root in source.parents:
            raise ApplicationError("METADATA_ROOT_CONFLICT", "不能把 PIG 元数据关联为资料")
        value = LinkedEntry("extra:" + str(uuid4()) + ("/" if source.is_dir() else ""),
                            source.name, source, source.is_dir())
        self._store.add_link(project_id, value, self._now())
        return value

    def roots(self, project_id: str):
        project = self.get(project_id)
        return (LinkedEntry("root:", project.root.name, project.root, True),
                *self._store.extra_links(project_id))

    def _target(self, project_id: str, key: str):
        if key.startswith("root:"):
            return self.get(project_id).root, key[5:]
        if key.startswith("extra:"):
            identity, _, relative = key[6:].partition("/")
            for entry in self._store.extra_links(project_id):
                if entry.key[6:].rstrip("/") == identity:
                    return entry.path, relative
        raise ApplicationError("FILE_NOT_LINKED", "文件关联不存在")

    def path(self, project_id: str, key: str, *, directory=None):
        root, relative = self._target(project_id, key)
        return self._files.resolve(root, relative, directory=directory)

    def children(self, project_id: str, key: str, *, offset=0):
        return self._files.children(self.path(project_id, key, directory=True), key, offset=offset)

    def observe(self, project_id: str, key: str, *, control=None):
        old = self._store.previous_observation(project_id, key)
        old_hash = old["sha256"] if old is not None else None
        root, relative = self._target(project_id, key)
        source_path = root.joinpath(*relative.split("/")) if relative else root
        try:
            source_path = self.path(project_id, key, directory=False)
            size, digest = self._files.fingerprint(source_path, control=control)
            state = "CHANGED" if old_hash is not None and old_hash != digest else "CURRENT"
        except ApplicationError as exc:
            states = {"FILE_MISSING": "MISSING", "FILE_UNREADABLE": "UNREADABLE", "UNSAFE_LINK": "UNSAFE"}
            if exc.code not in states:
                raise
            size, digest, state = None, old_hash, states[exc.code]
        value = Observation(key, state, size, digest, self._now(), old_hash)
        self._store.save_observation(project_id, source_path, value)
        return value

    def open(self, project_id: str, key: str, *, control=None):
        path = self.path(project_id, key, directory=False)
        if self._files.format(path) not in self._open_policy.allowed_formats:
            raise ApplicationError("OPEN_FORMAT_BLOCKED", "此格式不能通过系统关联程序打开")
        value = self.observe(project_id, key, control=control)
        if value.status not in ("CURRENT", "CHANGED"):
            raise ApplicationError("FILE_NOT_CURRENT", "当前文件不可打开")
        self._opener.open(self.path(project_id, key, directory=False))
        self._store.record_open(project_id, key, self._now())
        return value

    def capture(self, project_id: str, key: str, *, control=None):
        project = self.get(project_id)
        path = self.path(project_id, key, directory=False)
        size, digest = self._files.fingerprint(path, control=control)
        if self._objects.available_space(project.database_path.parent) - size < self._files.policy.minimum_free_bytes:
            raise ApplicationError("CAPTURE_CAPACITY_BLOCKED", "磁盘剩余空间不足")
        operation_id = str(uuid4())
        self._store.begin_capture(project_id, operation_id, key, self._now())
        stored = None
        try:
            stored = self._objects.capture(
                project.database_path.parent, operation_id,
                lambda writer: self._files.stream(path, writer, control=control),
                maximum=self._files.policy.maximum_file_bytes, control=control)
            if (stored.size, stored.sha256) != (size, digest):
                raise ApplicationError("FILE_CHANGED_DURING_CAPTURE", "固定期间文件内容发生变化")
            checked = self.path(project_id, key, directory=False)
            if checked != path or self._files.fingerprint(checked, control=control) != (size, digest):
                raise ApplicationError("FILE_CHANGED_DURING_CAPTURE", "固定期间文件内容发生变化")
            self._objects.verified_path(project.database_path.parent, stored.object_key,
                                        expected_size=size, expected_sha256=digest)
            value = FixedRevision(str(uuid4()), key, path, digest, size, stored.object_key, self._now())
            self._store.commit_capture(project_id, operation_id, value)
            return value
        except BaseException:
            self._store.fail_capture(project_id, operation_id,
                                     stored.object_key if stored else None, self._now())
            raise

    def revisions(self, project_id: str, key: str):
        return self._store.revisions(project_id, key)

    def draft_experience(self, project_id: str, revision_id: str, body: str, *, author: str):
        text, actor = body.strip(), author.strip()
        if not text or len(text) > 10000 or not actor or len(actor) > 255:
            raise ApplicationError("INVALID_EXPERIENCE", "请填写经验内容和作者")
        self._store.revision(project_id, revision_id)
        value = Experience(str(uuid4()), revision_id, text, "DRAFT", actor, self._now(), None)
        self._store.draft(project_id, value)
        return value

    def confirm_experience(self, project_id: str, experience_id: str):
        draft = self._store.experience(project_id, experience_id)
        if draft.status != "DRAFT":
            raise ApplicationError("EXPERIENCE_ALREADY_CONFIRMED", "经验已经确认")
        revision = self._store.revision(project_id, draft.revision_id)
        project = self.get(project_id)
        self._objects.verified_path(project.database_path.parent, revision.object_key,
                                    expected_size=revision.size, expected_sha256=revision.sha256)
        return self._store.confirm(project_id, experience_id, self._now())

    def experiences(self, project_id: str, revision_id: str):
        return self._store.experiences(project_id, revision_id)

    def pending_captures(self, project_id: str):
        return self._store.pending_captures(project_id)
