# PIG 仓库指令 / PIG Repository Instructions

`PIG Project Rules.md` 是本仓库具有最高约束力的项目级长期规则。

`PIG Project Rules.md` is the authoritative, project-wide, long-term rule set
for this repository.

在规划、设计、编码、评审或测试任何非 trivial 变更前：

Before planning, designing, coding, reviewing, or testing any non-trivial change:

1. 使用 UTF-8 完整读取 `PIG Project Rules.md`。
   Read `PIG Project Rules.md` in full using UTF-8.
2. 将它视为持续约束，而不是某次任务的背景材料。
   Treat it as a persistent constraint, not as one task's background material.
3. 实现前说明 Domain、Flow、State、Lineage、Log、Permission、Tool、AI、
   Automation 和 UI 影响。
   State the Domain, Flow, State, Lineage, Log, Permission, Tool, AI,
   Automation, and UI impact before implementation.
4. 遵守 `ADR-001`、V1 Workbench 重置 `ADR-010`、V2 基础决策 `ADR-024` 和
   V2.1 决策 `ADR-025`；使用
   `docs/PIG-planning-index.md` 判断当前文档和历史文档。
   Respect `ADR-001`, the V1 Workbench reset `ADR-010`, the V2 foundation
   decision `ADR-024`, and the V2.1 decision `ADR-025`; use
   `docs/PIG-planning-index.md` to resolve active versus historical documents.
5. 未经用户明确批准不得越过当前 Milestone。V2.1.5 已通过本轮验收；D120-A 至
   D126-A 已批准。用户随后明确授权一次性完成 V2.2.2–V2.2.4，包括目录/ZIP
   发布、最小 UI 与合成数据验收。不得提前实施内容解析、AI/RAG 依赖或 V2.3。
   旧 V1 数据库适配未在 V2.1.5 验收。
   Do not advance beyond the explicitly authorized milestone. V2.1.5 passed
   this acceptance run and D120-A through D126-A are approved. The user then
   explicitly authorized V2.2.2–V2.2.4 together: directory/ZIP publication,
   minimum UI, and synthetic-data acceptance. Do not implement content
   extraction, AI/RAG dependencies, or V2.3 early. Old V1 database adaptation
   was not accepted in V2.1.5.
6. 完成有意义的工作后，按照 `PIG Project Rules.md` 第十五节汇报。
   After meaningful work, report the completion items required by section 15 of
   `PIG Project Rules.md`.
7. PIG 自有 Markdown 遵循 `docs/DOCUMENTATION-STYLE.md` 的双语规范。
   First-party PIG Markdown follows the bilingual standard in
   `docs/DOCUMENTATION-STYLE.md`.

如果请求与项目规则或已批准 ADR 冲突，必须指出冲突并请求明确决策，不得静默覆盖。

If a request conflicts with the project rules or an approved architecture
decision, identify the conflict and ask for an explicit decision instead of
silently overriding it.
