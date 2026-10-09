# ADR-024：V2 Project Context 基础决策 / V2 Project Context Foundation

- 状态：已接受；只授权 V2.0 文档 / Status: Accepted; V2.0 documents only
- 日期：2026-10-07 / Date: 2026-10-07
- 范围：PIG V2 产品与架构规划 / Scope: PIG V2 product and architecture planning
- 已批准决策：D101-A 至 D112-A / Approved decisions: D101-A through D112-A

## 背景 / Context

V1 已把混乱、嵌套的项目资料转化为保护原件、可整理、可打开和可持续编辑的
Workspace。V2 的目标不是把聊天框附加到文件树，而是让用户从全部 Workspace
资料中挑选真正重要的内容，形成带有确定版本、人工说明、来源引用和可交付输出的
Project Context。

V1 already turns messy, nested project material into a Workspace with protected
originals, organization, controlled opening, and continued editing. V2 does not
attach a chat panel to the file tree. It lets the user select the material that
actually matters and form a Project Context with fixed versions, human guidance,
source citations, and a deliverable output.

## 决策 / Decisions

### D101-A：V1 Workbench 是 V2 稳定底座 / V1 Workbench remains the V2 foundation

V2 在现有 `Original Snapshot -> Source Structure -> Workspace` 链路之上增加能力，
不得重新实现导入、Container 处理、Working File、打开、编辑或导出基础设施。

V2 adds capabilities above the existing `Original Snapshot -> Source Structure
-> Workspace` chain. It must not reimplement ingestion, Container handling,
Working Files, controlled opening, editing, or the existing export foundation.

### D102-A：Project Context 先于知识库和 RAG / Project Context precedes knowledge bases and RAG

Project Context 是长期领域数据；内容索引、Embedding、Vector Index 和 RAG 都是可删除、
可重建的派生能力。没有 AI 时，Context 仍必须可整理、可读、可导出和可交接。

Project Context is durable domain data. Content indexes, embeddings, vector
indexes, and RAG are disposable, rebuildable derivatives. Context must remain
organizable, readable, exportable, and transferable without AI.

### D103-A：核心文件使用不可变 Context Revision / Core files use immutable Context Revisions

把 Workspace 文件加入 Context 时，系统为被采用的字节创建不可变版本检查点并保存
SHA-256。后续 Workspace 修改不得静默改变该版本；用户明确更新后创建新 Revision。
物理存储可以按内容 Hash 去重，但不得通过可变 Working Path 冒充不可变版本。

When a Workspace file enters Context, PIG creates an immutable checkpoint of the
adopted bytes and records SHA-256. Later Workspace edits cannot silently change
that revision; an explicit update creates a new Revision. Physical storage may
deduplicate by content hash, but a mutable Working Path cannot masquerade as an
immutable revision.

### D104-A：Context Item 与展示位置分离 / Context Items and placements are separate

一个核心对象只创建一个 `ContextItem`，但可以通过显式 `ContextPlacement` 出现在多个
Section。不得复制字符串 ID 或创建互相漂移的重复业务对象。

One promoted object has one `ContextItem`, while explicit `ContextPlacement`
records may place it in multiple Sections. Delimited identifiers and drifting
duplicate business objects are prohibited.

### D105-A：先完成人工 Context 与 Context Pack / Human Context and Context Pack come first

V2.1 和 V2.2 先完成选择、分组、人工说明、版本确定和 Context Pack 导出。内容提取、
AI 或 RAG 不得成为这一最小闭环的运行前提。

V2.1 and V2.2 first deliver selection, grouping, human guidance, fixed versions,
and Context Pack export. Content extraction, AI, and RAG cannot be runtime
prerequisites for this minimum loop.

### D106-A：PIG Canonical Content 加可替换 Extractor / Canonical Content with replaceable extractors

第三方解析结果必须映射为 PIG 自有的 `ContentDocument` 和 `ContentElement`，并保留
页码、Sheet、Cell Range、段落和邮件字段等 Source Locator。Docling 只是 PDF、DOCX、
PPTX 的候选 Adapter，正式依赖需在 V2.3 前完成真实 Fixture、打包、性能和许可证评估。

Third-party parser results must map into PIG-owned `ContentDocument` and
`ContentElement` records with source locators such as page, sheet, cell range,
paragraph, and email fields. Docling is only a candidate adapter for PDF, DOCX,
and PPTX. A real-fixture, packaging, performance, and license evaluation is
required before any V2.3 dependency decision.

### D107-A：FTS5 优先，Vector 必须由证据驱动 / FTS5 first; vectors require evidence

V2.3 先使用 SQLite FTS5 和结构化 Metadata Filter。只有固定检索评测证明关键词搜索
不足，才可以提出 Embedding、`sqlite-vec` 或其他 Vector Store 决策。

V2.3 starts with SQLite FTS5 and structured metadata filters. Embeddings,
`sqlite-vec`, or another vector store require a separate decision backed by a
fixed retrieval evaluation showing that lexical search is insufficient.

### D108-A：AI 是选定范围内的 Typed Action / AI is a scoped typed action

第一批 AI 能力限于用户明确选择的 Context Revision，并使用结构化输入输出。摘要、
比较和信息提取必须产生 Citation。自由 Project Chat、全 Workspace 自动扫描和可写
Agent 不属于第一批能力。

Initial AI capabilities operate only on explicitly selected Context Revisions
through typed inputs and outputs. Summaries, comparisons, and extraction must
produce Citations. Free-form project chat, automatic whole-Workspace scans, and
write-capable Agents are excluded from the initial capability set.

### D109-A：只预留平台无关交付边界 / Reserve only a vendor-neutral delivery boundary

Context Pack 是未来飞书、Notion、Microsoft 365 等 Adapter 的稳定输入。当前不实现
厂商连接、OAuth、Webhook、双向同步或 MCP；也不得在 Domain 中出现厂商 Token。

Context Pack is the stable future input for adapters such as Feishu, Notion,
and Microsoft 365. The current scope implements no vendor connector, OAuth,
webhook, bidirectional sync, or MCP, and vendor tokens cannot enter Domain.

### D110-A：当前 V1 Workbench Project 采用前向 Migration / Current V1 Workbench Projects migrate forward

与旧证据模型不同，当前 V1 Workbench Project 属于 V2 的有效基础。V2 Schema 必须通过
受控 Alembic 前向 Migration 保留 V1 Original、Source、Workspace、Working 和 Event
事实；不得用干净 Baseline 静默废弃现有 Workbench Project。

Unlike the old evidence model, current V1 Workbench Projects are valid V2
foundations. V2 schema must use controlled forward Alembic migrations that
preserve V1 Original, Source, Workspace, Working, and Event facts. A clean
baseline cannot silently discard current Workbench Projects.

### D111-A：耗时任务后台、有界、可取消 / Expensive work is bounded, background, and cancellable

Context Revision 捕获、内容提取、索引、AI 和 Context Pack 导出不得阻塞 UI。任务必须
具有 Typed Progress、安全取消点和串行受控写入；默认只处理 Context 文件或用户明确
选择的对象，不自动遍历全部 Workspace 内容。

Context Revision capture, extraction, indexing, AI, and Context Pack export
cannot block the UI. Work must expose typed progress, safe cancellation points,
and serialized controlled writes. By default it processes Context files or
explicit selections rather than automatically traversing all Workspace content.

### D112-A：开源组件通过 Adapter 复用，不 Fork 完整平台 / Reuse components through adapters; do not fork a platform

PIG 保持自己的 Domain、Persistence 和 UI。Docling、LlamaIndex、Haystack 或其他项目
只能作为可替换 Infrastructure 组件评估。当前不采用 RAGFlow、Dify 或类似完整平台
作为 PIG 基础，也不引入 Graph DB、独立 Vector DB、Agent Platform 或云协作服务。

PIG retains its own Domain, persistence, and UI. Docling, LlamaIndex, Haystack,
or another project may only be evaluated as a replaceable Infrastructure
component. PIG does not adopt RAGFlow, Dify, or another full platform as its
foundation and currently adds no graph database, standalone vector database,
Agent platform, or cloud collaboration service.

## 后果 / Consequences

- V2 可以在没有模型和网络的情况下提供有价值的 Context 整理与交付。
- AI 结果能够绑定确定文件版本并判断是否相对 Workspace 过期。
- 内容解析器、检索器和模型可以替换，但 PIG 的领域身份与引用保持稳定。
- 不提前获得完整 RAG 平台的功能；每层必须以真实工作流逐步证明价值。

- V2 can deliver valuable Context organization and handoff without a model or
  network connection.
- AI outputs can bind to exact file revisions and report whether they are stale
  relative to the Workspace.
- Extractors, retrievers, and models remain replaceable while PIG domain
  identities and citations remain stable.
- PIG does not receive a complete RAG platform up front; each layer must prove
  value through a real workflow.

## 授权边界 / Authorization boundary

本 ADR 批准 V2 产品方向和 V2.0 文档。进入 V2.1、创建 Migration、修改 Python 代码、
安装第三方解析或 AI 依赖、调用模型或修改 UI，均需要新的明确授权。

This ADR approves the V2 product direction and V2.0 documents. Entering V2.1,
creating migrations, changing Python code, installing parser or AI dependencies,
calling models, or changing UI all require new explicit authorization.
