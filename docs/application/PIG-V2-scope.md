# PIG V2 Project Context 范围 / PIG V2 Project Context Scope

- 状态：V2.1 本轮验收通过；D120-A 至 D126-A 已批准，V2.2 全段获授权 / Status: V2.1 accepted in this run; D120-A through D126-A approved, all V2.2 stages authorized
- 日期：2026-10-07 / Date: 2026-10-07
- 约束决策：`ADR-010`、`ADR-024`、`ADR-025` / Governing decisions: `ADR-010`, `ADR-024`, `ADR-025`

## 1. 产品结果 / Product outcome

V1 回答“项目里有什么文件，以及如何安全处理它们”。V2 进一步回答“哪些资料真正
重要、采用哪个版本、为什么重要、结论来自哪里，以及如何把项目上下文可靠交接”。

V1 answers what files a project contains and how to work with them safely. V2
also answers which material actually matters, which version is adopted, why it
matters, where conclusions come from, and how to hand the project context over
reliably.

V2 的长期用户流程为：

The long-term V2 user flow is:

```text
All Project Files
  -> V1 Workspace
  -> User-selected Core Material
  -> Human Guidance and Sections
  -> Immutable Context Revisions
  -> Context Pack
  -> Content Extraction and Local Search
  -> Scoped AI Analysis with Citations
  -> Project Overview / Timeline / Decisions
```

## 2. 两种互补视图 / Two complementary views

**Workspace View** 继续管理全部项目资料和日常文件操作。它是项目文件底座，不因 V2
而被删除或弱化。

**Workspace View** continues to manage all project material and ordinary file
operations. It remains the project file foundation and is not removed or
weakened by V2.

**Project Context View** 只展示用户挑选的核心材料、人工说明、确定版本和派生结果。
它不是第二套文件系统，不改变 Workspace Placement，也不复制 Source Structure。

**Project Context View** presents only user-selected core material, human
guidance, fixed revisions, and derived results. It is not a second filesystem,
does not change Workspace placement, and does not duplicate Source Structure.

## 3. V2 最小闭环 / Minimum V2 loop

首个 V2 闭环必须在没有 AI、RAG 和网络的情况下完成：

The first V2 loop must complete without AI, RAG, or network access:

```text
Select Workspace Item
  -> Promote to Context
  -> Capture immutable Context Revision
  -> Add one or more Context Placements
  -> Add human Annotation
  -> Persist and reopen
  -> Export a Context Pack
```

Context Pack 至少包含项目概览、核心文件的确定版本、人工说明和机器可读 Manifest。

A Context Pack contains at least a project overview, fixed versions of core
files, human guidance, and a machine-readable manifest.

V2.1 只交付上面流程中从 Promote 到 Persist/Reopen 的基础部分；Context Pack 属于
V2.2。V2.1 使用扁平 Section、虚拟 `Unsectioned`、Project 内内容寻址对象存储和独立
`context_revision`。默认只保留当前与上一 Revision，但被引用或人工保护的 Revision
继续保留，且系统不自动清理。

V2.1 delivers only the foundation from promotion through persist/reopen;
Context Pack belongs to V2.2. V2.1 uses flat Sections, virtual `Unsectioned`, a
Project-local content-addressed object store, and independent `context_revision`.
Current and previous Revisions are retained by default, while referenced or
manually protected Revisions remain retained and cleanup is never automatic.

## 4. 内容与 AI 边界 / Content and AI boundary

内容提取只消费不可变 `ContextRevision`，不得直接把可变 Working Path 当作稳定输入。
提取结果必须使用 PIG Canonical Content，并记录 Extractor 名称和版本。第一阶段只对
Context 或用户明确选择的对象处理，不自动索引全部 Workspace。

Content extraction consumes immutable `ContextRevision` records and cannot use
a mutable Working Path as a stable input. Results use PIG Canonical Content and
record the extractor name and version. Initial processing is limited to Context
or explicit selections and does not automatically index the entire Workspace.

AI 只负责语义任务，例如摘要、比较和提取时间/任务/决定。文件 Hash、路径、版本、
状态和权限继续由确定性代码负责。所有机器可消费的 AI 结果使用 Schema，所有重要
结论必须提供 Citation。

AI handles semantic tasks such as summarization, comparison, and extracting
dates, tasks, or decisions. Deterministic code remains responsible for hashes,
paths, versions, state, and permission. Machine-consumed AI outputs use schemas,
and every material conclusion must provide a Citation.

## 5. 用户可见能力 / User-visible capabilities

V2 按阶段提供：

V2 provides, in stages:

1. 从 Workspace 添加或移除 Context Item；
2. 创建 Section，并在多个 Section 中引用同一 Item；
3. 添加和修改人工 Annotation；
4. 查看 Context 使用的 Revision 和 Workspace 是否已有更新；
5. 导出 Context Pack；
6. 对 Context 内容进行本地全文搜索；
7. 对明确选择的 Revision 执行摘要、比较和结构化提取；
8. 查看 Citation、过期提示和重新分析入口；
9. 用列表、主题、时间线和决定视图呈现同一底层 Context 数据。

1. Promote or remove Context Items from the Workspace.
2. Create Sections and reference one Item from multiple Sections.
3. Add and edit human Annotations.
4. See the adopted Context Revision and whether the Workspace has a newer state.
5. Export a Context Pack.
6. Search extracted Context content locally.
7. Summarize, compare, or extract structured facts from explicit Revisions.
8. Inspect Citations, stale indicators, and re-analysis actions.
9. Render the same Context facts as lists, themes, timelines, and decisions.

## 6. 安全与权限 / Safety and permission

- Original Snapshot 继续不可变。
- Context Revision 必须通过 staging、Hash 校验和原子发布创建。
- 删除 Context Item 不得删除 Workspace、Source 或 Original。
- 远程模型调用前必须显示将外发的 Revision、大小、Provider 和目的。
- API Secret 只能保存到操作系统凭据存储，不得写入 Project SQLite。
- AI 不得直接改文件、数据库或 Workspace Placement。
- 导出和远程发送属于 External Write，必须由用户明确发起。

- Original Snapshots remain immutable.
- Context Revisions use staging, hash verification, and atomic publication.
- Removing a Context Item cannot delete Workspace, Source, or Original data.
- Before a remote model call, PIG shows the revisions, size, provider, and
  purpose of the outbound data.
- API secrets belong in the operating-system credential store, never Project
  SQLite.
- AI cannot directly modify files, the database, or Workspace placement.
- Export and remote transmission are external writes explicitly initiated by
  the user.

## 7. 明确不做 / Explicit exclusions

V2 初期不实现：

Initial V2 excludes:

- 飞书、Notion、Microsoft 365 或其他真实平台 Adapter；
- 双向同步、Webhook Gateway 或云端常驻服务；
- 自动索引全部 Workspace；
- 自由 Project Chat 作为主界面；
- 可写 Agent、Agent Platform、Automation Engine 或 MCP Server；
- Graph Database、独立 Vector Database 或完整 RAG 平台；
- AI 自动接受关键决定、时间线或业务事实；
- AI 自动修改、移动、删除或外发文件；
- 默认 OCR；
- Container Write-back、Archive Repack 或 MSG/EML 回写。

- real adapters for Feishu, Notion, Microsoft 365, or another platform;
- bidirectional sync, webhook gateways, or an always-on cloud service;
- automatic indexing of the full Workspace;
- free-form Project Chat as the primary UI;
- write-capable Agents, an Agent platform, Automation engine, or MCP server;
- a graph database, standalone vector database, or full RAG platform;
- automatic acceptance of AI-proposed decisions, timelines, or business facts;
- AI-driven modification, movement, deletion, or transmission of files;
- OCR by default;
- Container write-back, archive repack, or MSG/EML write-back.

## 8. V2 成功判断 / V2 success test

对于一个拥有大量底层资料的真实 Project，用户必须能够在不改变 Workspace 和 Original
的情况下，选出少量核心材料，解释其用途，锁定确定版本，形成可搜索且可交付的项目
上下文，并在使用 AI 时验证每个重要结论的来源。

For a real Project with a large amount of underlying material, the user can
select a small core set without changing Workspace or Original data, explain its
purpose, fix exact versions, build a searchable and transferable project
context, and verify the source of every material AI conclusion.
