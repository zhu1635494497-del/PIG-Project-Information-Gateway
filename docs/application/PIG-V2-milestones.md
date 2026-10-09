# PIG V2 开发里程碑 / PIG V2 Development Milestones

- 状态：D120-A 至 D126-A 已批准；V2.2.2–V2.2.4 获一次性授权 / Status: D120-A through D126-A approved; V2.2.2–V2.2.4 authorized together
- 日期：2026-10-08 / Date: 2026-10-08
- 约束决策：`ADR-024`、`ADR-025`、`ADR-026` / Governing decisions: `ADR-024`, `ADR-025`, `ADR-026`

每个 Milestone 必须单独进入并完成最小可运行、最小可测试、数据流闭环后才能进入
下一阶段。路线批准不等于后续代码自动授权。

Each Milestone requires explicit entry and must complete a minimum runnable,
testable data loop before the next. Roadmap approval does not automatically
authorize later code.

## V2.0：规划基线 / Planning baseline

- **目标 / Goal**：固定 Scope、领域对象、状态、不变量、来源链和实施顺序。
- **输入 / Input**：稳定 V1 Workbench 与 D101-A 至 D112-A。
- **核心实现 / Core work**：只建立双语 ADR、Scope、Domain、State/Invariant、Milestone
  和 Planning Index。
- **数据落库 / Persistence**：无。
- **测试 / Tests**：文档链接、双语完整性、术语和授权边界检查。
- **验收 / Acceptance**：所有有效文档一致说明 Project Context 先于 RAG；没有
  Migration、Python、UI 或依赖变化。

- **Goal**: Fix scope, domain objects, states, invariants, origin chain, and
  implementation order.
- **Input**: Stable V1 Workbench and D101-A through D112-A.
- **Core work**: Bilingual ADR, Scope, Domain, State/Invariant, Milestone, and
  Planning Index documents only.
- **Persistence**: None.
- **Tests**: Document links, bilingual completeness, terminology, and
  authorization-boundary checks.
- **Acceptance**: Every active document states that Project Context precedes RAG;
  there are no migration, Python, UI, or dependency changes.

## V2.1：Project Context 基础 / Project Context foundation

- **目标 / Goal**：不用 AI 完成 Workspace 到 Context 的可靠闭环。
- **输入 / Input**：一个现有 V1 Workbench Project 和 Active Terminal Workspace Item。
- **核心实现 / Core work**：经备份的 V1 前向升级、Project 内内容寻址 Object Store、
  扁平 Section、Item、Placement、Item 级 Annotation、不可变 Context Revision、独立
  `context_revision`、Freshness Query，以及最小 Context 三栏 UI。
- **数据落库 / Persistence**：前向 Alembic Migration；Context 表、Revision 所有权、
  Event；不得修改 V1 事实。
- **测试 / Tests**：V1 Project 升级、Promote、多个 Placement、Annotation 重启保持、
  Hash/去重/原子发布、Virtual Source 捕获、Workspace 修改、并发冲突、当前与上一版本
  保留、容量门、取消、磁盘不足、Original 不变。
- **验收 / Acceptance**：从大型 Workspace 选择少量核心文件，添加说明、重启保持，
  文件变化显示 `WORKSPACE_UPDATED`，Section 删除/恢复和 `Unsectioned` 行为正确，且
  不依赖 AI 或网络。

- **Goal**: Complete a reliable Workspace-to-Context loop without AI.
- **Input**: An existing V1 Workbench Project and an active terminal Workspace Item.
- **Core work**: Backed-up V1 forward upgrade, Project-local content-addressed
  object storage, flat Sections, Items, Placements, Item-level Annotations,
  immutable Context Revisions, independent `context_revision`, freshness queries,
  and a minimum three-pane Context UI.
- **Persistence**: Forward Alembic migration, Context tables, Revision ownership,
  and Events without rewriting V1 facts.
- **Tests**: V1 Project upgrade, promotion, multiple placements, restart-safe
  annotations, hash/deduplication/atomic publication, virtual Source capture,
  Workspace changes, concurrency conflicts, current/previous retention, capacity
  gates, cancellation, disk exhaustion, and Original immutability.
- **Acceptance**: The user selects a small core set from a large Workspace, adds
  guidance, reopens it, sees `WORKSPACE_UPDATED` after file changes, and observes
  correct Section remove/restore and `Unsectioned` behavior without AI or network.

V2.1 的详细实施边界和 V2.1.1 至 V2.1.5 顺序由
`docs/application/PIG-V2.1-context-foundation.md` 定义。V2.1.5 已通过本轮验收；
范围与证据见 `PIG-V2.1.5-acceptance.md`；V2.2.2–V2.2.4 随后获一次性授权。

Detailed V2.1 boundaries and the V2.1.1 through V2.1.5 sequence are defined in
`docs/application/PIG-V2.1-context-foundation.md`. V2.1.5 passed this
acceptance run; its scope and evidence are in `PIG-V2.1.5-acceptance.md`.
V2.2.2–V2.2.4 were subsequently authorized together.

## V2.2：Context Pack 交付 / Context Pack delivery

本阶段 D120-A 至 D126-A 已批准，见 `ADR-026`。V2.2.1–V2.2.4 分段见
`PIG-V2.2-decision-gate.md`；用户随后授权一次性完成 V2.2.2–V2.2.4。

D120-A through D126-A are approved in `ADR-026`. See
`PIG-V2.2-decision-gate.md` for V2.2.1–V2.2.4 stages. The user subsequently
authorized V2.2.2–V2.2.4 together.

- **目标 / Goal**：证明 Project Context 在没有 AI 时已经可以可靠交接。
- **输入 / Input**：有 Section、Item、Revision 和 Annotation 的 Context。
- **核心实现 / Core work**：Export Preflight、版本选择、结构化 Manifest、项目概览、
  原子目录/ZIP 发布和失败清理；只保留平台无关 Contract。
- **数据落库 / Persistence**：ContextPackExport、Entry、状态和 Event。
- **测试 / Tests**：同名、安全路径、空 Section、大文件、取消、目标冲突、磁盘不足、
  Hash 验证、重启后历史可查。
- **验收 / Acceptance**：另一台机器上的用户可以从导出包理解项目说明、核心文件和
  每个文件的确定版本。

- **Goal**: Prove that Project Context is transferable without AI.
- **Input**: Context containing Sections, Items, Revisions, and Annotations.
- **Core work**: Export preflight, version selection, structured manifest,
  overview, atomic directory/ZIP publication, and failure cleanup, with only a
  vendor-neutral contract reserved.
- **Persistence**: ContextPackExport, Entries, states, and Events.
- **Tests**: Duplicates, safe paths, empty Sections, large files, cancellation,
  destination conflicts, disk exhaustion, hash verification, and restart-safe
  history.
- **Acceptance**: A user on another machine can understand the project guidance,
  core files, and exact version of each file from the exported pack.

## V2.3：Canonical Content 与本地搜索 / Canonical Content and local search

- **目标 / Goal**：将确定的 Context Revision 转换为可定位、可搜索的内容。
- **输入 / Input**：用户选择的 READY Context Revision。
- **核心实现 / Core work**：Extractor Port、候选 Docling Spike、自有 XLSX/CSV/Email
  Extractor、Canonical Content、Source Locator、FTS5、后台进度与重建。
- **数据落库 / Persistence**：ExtractionRun、ContentDocument、ContentElement、FTS5
  派生索引和 Event。
- **测试 / Tests**：PDF 页码、DOCX 段落、PPTX Slide、XLSX Sheet/Cell、邮件字段、
  Unsupported/Partial、同版本幂等、Extractor 升级、删除重建、UI 心跳和资源上限。
- **验收 / Acceptance**：用户可以搜索 Context 内容，并从结果直接定位到文件和
  页码、Sheet/Cell、Slide 或邮件字段；不需要 Vector DB。

- **Goal**: Convert fixed Context Revisions into addressable, searchable content.
- **Input**: Explicitly selected READY Context Revisions.
- **Core work**: Extractor port, candidate Docling spike, native XLSX/CSV/email
  extractors, Canonical Content, source locators, FTS5, background progress, and
  rebuild.
- **Persistence**: ExtractionRun, ContentDocument, ContentElement, derived FTS5
  index, and Events.
- **Tests**: PDF pages, DOCX paragraphs, PPTX slides, XLSX sheets/cells, email
  fields, unsupported/partial outcomes, same-version idempotency, extractor
  upgrades, delete/rebuild, UI heartbeat, and resource limits.
- **Acceptance**: The user searches Context content and opens a result at its file
  and page, sheet/cell, slide, or email field without a vector database.

## V2.4：受控 AI Actions / Controlled AI actions

- **目标 / Goal**：为明确选择的 Revision 提供可信、有引用的语义辅助。
- **输入 / Input**：READY Context Revision、Canonical Content、人工 Annotation 和用户
  选择的 Typed Action。
- **核心实现 / Core work**：Model Provider Port、集中 Prompt Registry、Outbound
  Preview、结构化输出校验、Summary/Compare/Extract、Citation 和 Freshness。
- **数据落库 / Persistence**：AnalysisRun/Input/Result/Citation、模型元数据、状态和
  Event；Secret 不落库。
- **测试 / Tests**：Provider 失败、超时、取消、Schema 无效、Citation 越界、文件更新、
  敏感数据确认、重试幂等、无网络降级。
- **验收 / Acceptance**：摘要、比较和提取均能回到确定 Revision 和具体 Locator；
  Workspace 更新后旧结果清楚显示过期但不被篡改。

- **Goal**: Provide trustworthy cited semantic assistance for explicit Revisions.
- **Input**: READY Context Revisions, Canonical Content, human Annotations, and a
  user-selected typed action.
- **Core work**: Model-provider port, centralized prompt registry, outbound
  preview, structured-output validation, summary/compare/extract actions,
  Citations, and freshness.
- **Persistence**: AnalysisRun/Input/Result/Citation, model metadata, states, and
  Events; secrets remain outside the database.
- **Tests**: Provider failure, timeout, cancellation, invalid schema, out-of-scope
  citations, file updates, sensitive-data confirmation, retry idempotency, and
  offline degradation.
- **Acceptance**: Summaries, comparisons, and extractions resolve to exact
  Revisions and Locators; older results clearly become stale after Workspace
  updates without being rewritten.

## V2.5：项目叙事视图 / Project narrative views

- **目标 / Goal**：用主题、时间线和决定视图表达同一 Context，而不把 UI 画布当事实。
- **输入 / Input**：Context、Annotation、Citation，以及用户确认的 AI 建议。
- **核心实现 / Core work**：人工优先的 Timeline Entry、Decision Record 和 typed
  Relationship；List/Outline/Timeline 投影；AI 只能建议，用户确认后落库。
- **数据落库 / Persistence**：显式 Timeline/Decision/Relationship 表和确认 Event；
  不使用 Graph DB。
- **测试 / Tests**：人工创建、AI 建议拒绝/接受、排序、重复关系、引用完整性、不同视图
  一致性和重启。
- **验收 / Acceptance**：用户能看清项目目标、过程、决定和结论来源，同时随时返回
  Workspace 文件和确定 Revision。

- **Goal**: Present the same Context as themes, timelines, and decisions without
  treating a UI canvas as fact.
- **Input**: Context, Annotations, Citations, and user-confirmed AI suggestions.
- **Core work**: Human-first Timeline Entries, Decision Records, typed
  Relationships, List/Outline/Timeline projections, and explicit acceptance of
  AI suggestions.
- **Persistence**: Explicit Timeline/Decision/Relationship tables and confirmation
  Events, with no graph database.
- **Tests**: Manual creation, AI suggestion reject/accept, ordering, duplicate
  relationships, citation integrity, cross-view consistency, and restart.
- **Acceptance**: The user can understand project goals, process, decisions, and
  conclusion sources and return to the Workspace file and fixed Revision.

## V2.6：检索与集成资格评估 / Retrieval and integration qualification

- **目标 / Goal**：只在证据充分时决定 Vector/RAG 或真实平台 Adapter。
- **输入 / Input**：V2.3 固定检索评测、V2.4 使用数据和 V2.2 Context Pack Contract。
- **核心实现 / Core work**：对比 FTS5 与候选 Hybrid Retrieval；验证平台无关发布
  Contract；形成新 ADR，而不是直接引入依赖。
- **数据落库 / Persistence**：默认无；任何新 Index/Connection 表必须由新决策批准。
- **测试 / Tests**：固定问题集的 Recall、Citation Accuracy、Latency、内存、包体和
  离线退化；平台 Adapter 只做隔离 Spike 时不得进入发布包。
- **验收 / Acceptance**：有数据证明继续保持 FTS5，或有数据支持一个明确、可撤回的
  Vector/RAG/Adapter 决策。

- **Goal**: Decide on vectors/RAG or a real platform adapter only with evidence.
- **Input**: Fixed V2.3 retrieval evaluation, V2.4 usage evidence, and the V2.2
  Context Pack contract.
- **Core work**: Compare FTS5 with candidate hybrid retrieval, validate the
  vendor-neutral publication contract, and create a new ADR rather than adding
  dependencies directly.
- **Persistence**: None by default; any new index or connection table requires a
  newly approved decision.
- **Tests**: Fixed-query recall, citation accuracy, latency, memory, package size,
  offline degradation, and isolated adapter spikes excluded from release builds.
- **Acceptance**: Evidence supports either retaining FTS5 or one explicit,
  reversible vector/RAG/adapter decision.
