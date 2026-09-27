# ADR-023：Project Information Gateway 产品身份 / Project Information Gateway Identity

- 状态：已接受 / Status: Accepted
- 日期：2026-09-27 / Date: 2026-09-27
- 决策：D100-B / Decision: D100-B

## 背景 / Context

产品负责人决定将 PIG 的正式名称从 **Project Ingestion Gateway** 改为
**Project Information Gateway**。新名称更准确地覆盖当前文件工作台与未来 Project
Data Layer 的整体价值，而不只强调导入环节。

The product owner decided to rename PIG from **Project Ingestion Gateway** to
**Project Information Gateway**. The new name better represents both the
current file workbench and the future Project Data Layer instead of emphasizing
only ingestion.

## 决策 / Decision

正式产品身份为：

**PIG — Project Information Gateway**

The official product identity is:

**PIG — Project Information Gateway**

D100-B 统一修改用户可见品牌、有效规范、Python Distribution、发布元数据、项目链接和
GitHub 仓库名称。长期概念 **PIG — Project Information Graph** 保留，代表未来从
项目文件向结构化关系数据演进的方向。

D100-B aligns the user-visible brand, active specifications, Python
distribution, release metadata, project links, and GitHub repository name. The
long-term concept **PIG — Project Information Graph** remains as the direction
for evolving project files into structured relationship data.

## 稳定技术标识 / Stable Technical Identifiers

以下标识保持不变，避免没有业务价值的兼容性破坏：

- Python import package：`pig`
- 桌面命令：`pig-desktop`
- Windows executable：`PIG.exe`
- SQLite Schema、表名和 Alembic Migration
- 已有领域对象、状态、Event Type 和 Project 数据
- 已发布的 `v1.0.0-rc.1` Git Tag、Release 及其历史说明

The following identifiers remain stable to avoid compatibility breaks with no
business value:

- Python import package: `pig`
- desktop command: `pig-desktop`
- Windows executable: `PIG.exe`
- SQLite schema, table names, and Alembic migrations
- existing domain objects, states, event types, and Project data
- the published `v1.0.0-rc.1` Git tag, release, and its historical notes

## 新公开标识 / New Public Identifiers

- Python Distribution：`pig-project-information-gateway`
- GitHub Repository：`PIG-Project-Information-Gateway`
- Git Remote：`https://github.com/zhu1635494497-del/PIG-Project-Information-Gateway.git`

- Python distribution: `pig-project-information-gateway`
- GitHub repository: `PIG-Project-Information-Gateway`
- Git remote: `https://github.com/zhu1635494497-del/PIG-Project-Information-Gateway.git`

## 数据与发布影响 / Data and Release Impact

本决策不新增 Migration，不修改 Project Database，不改变 Original/Working、Lineage、
权限或处理流程。`v1.0.0-rc.2` 仍受 W10 最终打包桌面人工验收和 W9 人工发布 Gate
约束；改名本身不构成发布授权。

This decision adds no migration, does not modify Project databases, and does not
change Original/Working, Lineage, permissions, or processing flows.
`v1.0.0-rc.2` remains gated by W10 final-package desktop acceptance and the W9
human release gates; the rename itself does not authorize a release.

## 验证 / Verification

- 改名后的 Python Distribution 以 editable 模式成功安装。
- 完整回归：`176 passed, 95 skipped`，另有一个既有的预期 Duplicate ZIP Warning。
- Windows `onedir` 重新构建成功，ICU 冲突数为 `0`。
- Runtime Smoke Exit Code 为 `0`；Packaged Flow 为 `PASS`。

- The renamed Python distribution installs successfully in editable mode.
- Full regression: `176 passed, 95 skipped`, plus one existing expected
  duplicate-ZIP warning.
- The Windows `onedir` package rebuild succeeds with `0` ICU conflicts.
- Runtime Smoke exits with code `0`; Packaged Flow reports `PASS`.
