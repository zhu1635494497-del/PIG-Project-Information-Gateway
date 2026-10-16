# ADR-030 新版本默认不兼容旧项目 / No Legacy Project Compatibility by Default

- 状态：已接受，负责人于 2026-10-12 明确决定 / Status: Accepted by owner on 2026-10-12

## 决定 / Decision

后续代码升级默认只保证由该代码创建的项目可用；不为以前版本的项目数据库、
Workspace 或 Context 数据设计兼容读取或迁移，除非负责人对具体旧版本特意提出。
不支持的旧项目必须明确拒绝，不能自动升级、重建、删除或覆盖其资料。

Future code changes need only support projects created by that code. No compatibility reader
or migration is required for databases, Workspace data, or Context data from earlier versions
unless the owner explicitly requests it for specified versions. Unsupported projects must be
rejected explicitly, not automatically upgraded, rebuilt, deleted, or overwritten.

## 范围与取舍 / Scope and trade-off

此决定取代 ADR-024/025 中可被理解为“每次新版本都必须兼容当前旧项目”的默认义务；
不删除已有历史升级实现，也不改变已签收的历史事实。新项目仍须具备正确 Schema、
安全恢复、原件保护和充分测试。若将来批准特定旧库迁移，仍须遵守 ADR-025 的
确认、完整备份、验证和失败停止线。

This supersedes any interpretation of ADR-024/025 that every new release must carry forward
the previous project's database by default. It does not remove existing migration code or
rewrite historical acceptance. New projects still require correct schemas, safe recovery,
Original protection, and tests. A specifically authorized migration must still follow
ADR-025 confirmation, consistent backup, validation, and stop-on-failure boundaries.
