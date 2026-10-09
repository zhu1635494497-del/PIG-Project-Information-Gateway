# PIG V2 当前规划索引 / PIG V2 Active Planning Index

- 状态：当前有效 / Status: Active
- 日期：2026-10-08 / Date: 2026-10-08
- 当前阶段：V2.2 Context Pack 实施与验收 / Current phase: V2.2 Context Pack implementation and acceptance
- 代码授权：D120-A 至 D126-A 已批准；V2.2.2–V2.2.4 获一次性授权 / Code authorization: D120-A through D126-A approved; V2.2.2–V2.2.4 authorized together

## 有效 V2 文档 / Active V2 documents

1. `docs/decisions/ADR-024-v2-project-context-foundation.md`
2. `docs/decisions/ADR-025-v2.1-context-foundation-decisions.md`
3. `docs/decisions/ADR-026-v2.2-context-pack.md`
4. `docs/application/PIG-V2-scope.md`
5. `docs/domain/PIG-V2-project-context-domain-model.md`
6. `docs/domain/PIG-V2-state-machines-and-invariants.md`
7. `docs/application/PIG-V2.1-context-foundation.md`
8. `docs/application/PIG-V2.1.1-upgrade-schema.md`
9. `docs/application/PIG-V2-milestones.md`
10. `docs/application/PIG-V2.1.2-capture-core.md`
11. `docs/application/PIG-V2.1.3-context-actions.md`
12. `docs/application/PIG-V2.1.4-minimum-ui-plan.md`
13. `docs/application/PIG-V2.1.5-acceptance.md`
14. `docs/application/PIG-V2.2-decision-gate.md`（已批准决策背景 / approved decision background）
15. `docs/application/PIG-V2.2.1-contract-schema.md`
16. `docs/application/PIG-V2.2-implementation-acceptance.md`

跨版本优先级由 `docs/PIG-planning-index.md` 定义。V1 详细实现历史由
`docs/PIG-V1-planning-index.md` 保留。

Cross-version priority is defined by `docs/PIG-planning-index.md`. Detailed V1
implementation history remains in `docs/PIG-V1-planning-index.md`.

## 已批准基础决策 / Approved foundation decisions

- D101-A：V1 Workbench 是 V2 稳定底座；
  V1 Workbench remains the stable V2 foundation.
- D102-A：Project Context 先于知识库和 RAG；
  Project Context precedes knowledge bases and RAG.
- D103-A：核心文件使用不可变 Context Revision；
  core files use immutable Context Revisions.
- D104-A：Context Item 与多 Section Placement 分离；
  Context Items are separate from multiple Section placements.
- D105-A：先完成人工 Context 与 Context Pack；
  human Context and Context Pack come before AI.
- D106-A：PIG Canonical Content 加可替换 Extractor；
  PIG Canonical Content uses replaceable extractors.
- D107-A：SQLite FTS5 优先，Vector 由评测证据驱动；
  SQLite FTS5 comes first and vectors require evaluation evidence.
- D108-A：AI 是选定 Revision 范围内、有 Citation 的 Typed Action；
  AI is a cited typed action over selected Revisions.
- D109-A：只预留平台无关交付边界；
  reserve only a vendor-neutral delivery boundary.
- D110-A：当前 V1 Workbench Project 使用前向 Migration；
  current V1 Workbench Projects use forward migrations.
- D111-A：耗时任务后台、有界、可取消；
  expensive work is bounded, background, and cancellable.
- D112-A：开源组件通过 Adapter 复用，不 Fork 完整平台；
  reuse open-source components through adapters rather than forking a platform.

## 已批准 V2.1 决策 / Approved V2.1 decisions

- D113-A：每个 Project 使用内容寻址 Context Object Store；
  each Project uses a content-addressed Context Object Store.
- D114-B：默认保留当前和上一 Revision，并保护被引用或人工保护的 Revision；
  retain current and previous Revisions by default and protect referenced or
  manually protected Revisions.
- D115-A：当前 V1 Project 经确认、备份和校验后原地前向升级；
  current V1 Projects use a confirmed, backed-up, validated in-place forward upgrade.
- D116-A：V2.1 只支持扁平有序 Section，软删除后使用虚拟 `Unsectioned`；
  V2.1 uses flat ordered Sections with soft deletion and virtual `Unsectioned`.
- D117-A：同窗口 `[Workspace] [Project Context]` 和最小三栏 Context UI；
  same-window `[Workspace] [Project Context]` with a minimum three-pane Context UI.
- D118-B：Materialized Item 捕获 Working，Virtual Item 直接从 Source 捕获；
  materialized Items capture Working bytes and virtual Items capture directly from Source.
- D119-B：Project 使用独立 `context_revision` 乐观并发版本；
  Projects use an independent `context_revision` optimistic-concurrency version.

## 当前授权门 / Current authorization gate

V2.1.5 已通过本轮验收；旧 V1 数据库适配未签收。D120-A 至 D126-A 已批准，
用户明确授权一次性完成 V2.2.2–V2.2.4。现有 D115-A 实现不因本轮范围缩小而删除。

V2.1.5 passed this acceptance run; old V1 database adaptation remains
unaccepted. D120-A through D126-A are approved and the user explicitly
authorized V2.2.2–V2.2.4 together. Existing D115-A implementation is not removed.

Docling、其他解析器、模型 Provider、Embedding、Vector Store、RAG Framework、平台
Adapter、MCP、Agent 和 Automation 均未获得实现授权。

Docling, other parsers, model providers, embeddings, vector stores, RAG
frameworks, platform adapters, MCP, Agents, and Automation are not authorized
for implementation.

## 下一步建议 / Next minimum recommendation

完成 V2.2 合成数据自动验收后，请用户决定是否进行真实资料与异机人工验收。
当前授权不得解释为 V2.3、Docling、内容提取、模型接入或平台适配授权。

After synthetic automated V2.2 acceptance, the user decides whether to perform
real-data and cross-machine manual acceptance. Current authorization does not
include V2.3, Docling, content extraction, models, or platform adapters.
