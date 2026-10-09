# PIG V2.1.1 Upgrade + Schema 实施记录 / PIG V2.1.1 Upgrade + Schema Implementation Record

- 状态：已完成 / Status: Complete
- 日期：2026-10-07 / Date: 2026-10-07
- 约束决策：`ADR-010`、`ADR-024`、`ADR-025` / Governing decisions: `ADR-010`, `ADR-024`, `ADR-025`
- Migration：`0009_project_context_foundation` / Migration: `0009_project_context_foundation`

## 1. 完成结果 / Completed outcome

V2.1.1 已建立 Project Context 的持久化基础和显式 V1 升级闭环。现有 V1 Project 不会
在打开时被静默迁移；系统先返回升级预检，只有用户明确确认后才备份、迁移、校验并
更新模型版本。新 Project 直接使用 `project-context-v2.1`。

V2.1.1 establishes the Project Context persistence foundation and explicit V1
upgrade loop. Existing V1 Projects are no longer silently migrated on open. PIG
returns an upgrade preflight first and performs backup, migration, validation,
and model-version advancement only after explicit confirmation. New Projects use
`project-context-v2.1` directly.

## 2. Schema 与 Mapping / Schema and mappings

`0009_project_context_foundation` 增加：

`0009_project_context_foundation` adds:

- `projects.context_revision`，独立于 `workspace_revision`；
- `context_settings`；
- `context_sections`；
- `context_items`；
- `context_placements`；
- `context_content_objects`；
- `context_revisions`；
- `context_annotations`；
- Processing Event 的 Context 外键列和升级 Event 类型。

- `projects.context_revision`, independent of `workspace_revision`;
- `context_settings`;
- `context_sections`;
- `context_items`;
- `context_placements`;
- `context_content_objects`;
- `context_revisions`;
- `context_annotations`;
- Context foreign-key columns and upgrade Event types on Processing Events.

Schema 使用显式 Project 复合外键、状态约束、Hash/Size 约束、Lifecycle/Removed Time
一致性约束和 Project 内 Content Hash 唯一性。V2.1 Section 没有 Parent Column。

The schema uses explicit Project composite foreign keys, state constraints,
hash/size constraints, lifecycle/removed-time consistency, and Project-local
content-hash uniqueness. V2.1 Sections have no parent column.

## 3. Repository 边界 / Repository boundary

新增 `ContextRepository` 和 SQLAlchemy 实现，负责 Settings、Section、Item、Placement、
Content Object、Revision 和 Annotation 的持久化。Repository 不执行 Capture、Retention、
Freshness 或 UI Workflow。

A new `ContextRepository` and SQLAlchemy implementation persist Settings,
Sections, Items, Placements, Content Objects, Revisions, and Annotations. The
repository does not execute capture, retention, freshness, or UI workflows.

`ProjectRepository` 新增：

`ProjectRepository` adds:

- `advance_context_revision`：基于期望版本的原子递增；
- `update_model_version`：基于期望模型版本的受控更新。

- `advance_context_revision`: atomic expected-version increment;
- `update_model_version`: controlled expected-model-version update.

## 4. 升级流程 / Upgrade flow

```text
Inspect V1 database read-only
  -> Validate Project path and SQLite integrity
  -> Return preflight
  -> Require explicit confirmation
  -> SQLite backup API to backups/project-upgrade/
  -> Verify backup integrity
  -> Alembic 0008 -> 0009
  -> Validate V1 table counts + foreign keys + integrity
  -> Seed Context Settings
  -> Update model version in one transaction
  -> Append upgrade Events
  -> Reopen as project-context-v2.1
```

备份文件使用 UTC Timestamp，不覆盖已有备份。Migration 或校验失败时模型版本不会推进；
系统保留备份并返回结构化错误。若新 Schema 已可安全读取，失败 Event 采用 best-effort
记录；不可安全读取的半迁移数据库不会被强制写入。

Backup files use UTC timestamps and never overwrite an existing backup. A
migration or validation failure does not advance the model version; PIG retains
the backup and returns a structured error. Failure Events are recorded on a
best-effort basis only when the new schema is safely readable; a partial schema
is never forced open for writing.

## 5. 状态与 Event / State and Events

升级成功写入：

A successful upgrade writes:

- `PROJECT_CONTEXT_UPGRADE_REQUESTED`
- `PROJECT_CONTEXT_UPGRADE_STARTED`
- `PROJECT_CONTEXT_UPGRADE_COMPLETED`

可安全记录的失败写入 `PROJECT_CONTEXT_UPGRADE_FAILED`。Event 只保存 Actor、UTC 时间、
Correlation ID、Schema/Model Version、备份路径和安全错误码，不保存文件正文或 Secret。

A safely recordable failure writes `PROJECT_CONTEXT_UPGRADE_FAILED`. Events
store actor, UTC time, correlation ID, schema/model versions, backup path, and a
safe error code, never file content or secrets.

## 6. 权限与安全 / Permission and safety

- Preflight 是只读操作；
- Upgrade 是显式确认后的 Project 写操作；
- 数据库必须是普通非 Symlink 文件；
- 数据库目录必须匹配 Project `workspace_locator`；
- Original、Source、Workspace 和 Working 字节不被读取或改写；
- 升级不创建 Context Revision 或 Object 字节；
- 打开 V1 Project 只返回 `PROJECT_UPGRADE_REQUIRED`，不会自动迁移。

- Preflight is read-only.
- Upgrade is a confirmed Project write.
- The database must be a regular non-symlink file.
- Its directory must match Project `workspace_locator`.
- Original, Source, Workspace, and Working bytes are not read or rewritten.
- Upgrade creates no Context Revision or object bytes.
- Opening a V1 Project returns `PROJECT_UPGRADE_REQUIRED` without auto-migration.

## 7. 测试 / Tests

新增测试覆盖：

New coverage includes:

- V1 `0008` Project 预检和显式确认；
- 打开时拒绝静默升级；
- SQLite Backup 完整性、版本和模型检查；
- V1 Row Count、Foreign Key 和 Integrity 保持；
- `0009` Schema 与 SQLAlchemy Metadata 一致；
- Context Entity Repository Round-trip；
- `context_revision` 陈旧写冲突；
- Upgrade 幂等；
- 新 Project 使用当前模型并包含 Context Settings；
- 全部 V1 Workbench 回归。

- V1 `0008` Project preflight and explicit confirmation;
- rejection of silent migration during open;
- SQLite backup integrity, revision, and model checks;
- V1 row-count, foreign-key, and integrity preservation;
- `0009` schema alignment with SQLAlchemy metadata;
- Context entity repository round trips;
- stale-write conflict on `context_revision`;
- upgrade idempotency;
- current model and Context Settings for new Projects;
- full V1 Workbench regression.

执行结果：`182 passed, 95 skipped, 1 warning`。Skipped 测试为已有历史 Evidence Model
隔离测试或当前 Windows 主机不允许创建测试 Symlink；Warning 为既有重复 ZIP Member
Fixture。

Result: `182 passed, 95 skipped, 1 warning`. Skips are existing historical
Evidence Model quarantines or test-symlink restrictions on the current Windows
host. The warning comes from the existing duplicate ZIP-member fixture.

## 8. 当前边界 / Current boundary

V2.1.1 没有实现：

V2.1.1 does not implement:

- Context Object Store 文件写入；
- Working/Source Capture；
- Promote、Section、Placement 或 Annotation Application Action；
- Retention/Cleanup Workflow；
- Freshness Query；
- Project Context UI；
- Content Extraction、Search、AI、RAG、MCP 或平台 Adapter。

- Context Object Store byte publication;
- Working/Source capture;
- promotion, Section, Placement, or Annotation Application Actions;
- retention/cleanup workflow;
- freshness queries;
- Project Context UI;
- content extraction, search, AI, RAG, MCP, or platform adapters.

本记录完成时，下一阶段 V2.1.2 Capture Core 未自动获得授权；其后续授权与完成状态以
`docs/PIG-V2-planning-index.md` 为准。

When this record closed, V2.1.2 Capture Core was not automatically authorized.
Its later authorization and completion status are governed by
`docs/PIG-V2-planning-index.md`.
