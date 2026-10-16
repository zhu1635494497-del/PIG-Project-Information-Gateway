# V2.3 内容定位与本地搜索决策门 / V2.3 Content Location and Local Search Decision Gate

- 状态：D127-A–D132-A 已由负责人批准；V2.3.1–V2.3.5 一次性实施授权，人工验收未签收 / Status: D127-A–D132-A approved by owner; V2.3.1–V2.3.5 authorized together, manual acceptance pending
- 日期：2026-10-09 / Date: 2026-10-09
- 上位约束：`ADR-010`、`ADR-024`、`ADR-025`、`ADR-026` / Parent constraints: `ADR-010`, `ADR-024`, `ADR-025`, `ADR-026`

## 1. 用一句话解释 / One-sentence explanation

V2.1 选出关键文件并固定版本，V2.2 将其可靠交付。V2.3 要让用户**在这些确定版本
的内容里搜索，并看到命中内容位于哪一页、Sheet/单元格、Slide、段落或邮件字段**。
文件正文仍由程序确定性提取；本阶段不做 AI 问答。

V2.1 selects core files and fixes their versions; V2.2 delivers them reliably.
V2.3 lets users **search the content of those fixed versions and see the page,
sheet/cell, slide, paragraph, or email field containing a match**. Extraction
is deterministic and this stage does not implement AI question answering.

## 2. 最小用户故事与数据流 / Minimum user story and data flow

用户在 Project Context 选择一个或多个 `READY` Revision，点击“提取并索引”。后台
读取不可变 Context Object，通过对应 Extractor 生成 PIG 自有的有序内容元素，保存
明确的 Locator，并构建 SQLite FTS5 派生索引。用户搜索词语后看到命中片段、文件、
固定版本和位置；可以打开文件并按显示的位置核对原文。Workspace 后续修改不会
静默替换已索引版本。

In Project Context, the user selects one or more `READY` Revisions and invokes
Extract and Index. Background work reads immutable Context Objects, maps
extractor output to ordered PIG-owned content elements with typed locators,
and builds a derived SQLite FTS5 index. Search shows a snippet, file, fixed
Revision, and location; the user can open the file and verify the original
content at the displayed location. Later Workspace edits cannot silently
replace an indexed Revision.

```text
READY ContextRevision -> verified ContextContentObject -> ExtractionRun
  -> ContentDocument -> ordered ContentElement + typed SourceLocator
  -> rebuildable FTS5 index -> search result -> fixed Revision + locator
```

## 3. 实施影响预检 / Pre-implementation impact check

- **Domain / 领域**：新增 `ExtractionRun`、`ContentDocument`、`ContentElement`、
  typed `SourceLocator`；FTS5 只作派生索引，不成为来源事实。
- **Flow / 流程**：只读取用户选定的 `READY` Context Revision；不扫描全部 Workspace。
- **State / 状态**：沿用已规划的 `PENDING/RUNNING/SUCCEEDED/PARTIAL/UNSUPPORTED/
  FAILED/CANCELLED_AT_SAFE_POINT` 提取状态，以及可重建的 Index 状态。
- **Lineage / 来源**：每个命中绑定 `ContentElement -> ExtractionRun ->
  ContextRevision -> ContextItem -> WorkspaceItem`，必要时继续到 Source/Original。
- **Log / 日志**：记录开始、结果、部分成功、错误、取消、重建；业务 Event 不保存全文。
- **Permission / 安全**：本地受控读取，限制大小、时间和元素数；不改 Original、
  Working 或 Context Object；不得将正文自动外发。
- **Tool / Action**：规划类型化的 `extract_context_revisions`、
  `search_context_content` 和 `rebuild_context_index` 内部 Action；不发布 MCP。
- **AI / Automation**：均不参与；不增加模型、Embedding、RAG 或自动全盘任务。
- **UI / 界面**：现有 Project Context 内增加最小提取状态和内容搜索，不新建 Dashboard。

- **Domain**: Add `ExtractionRun`, `ContentDocument`, `ContentElement`, and
  typed `SourceLocator`; FTS5 is a derivative, not an authoritative source fact.
- **Flow**: Read only explicitly selected `READY` Context Revisions, never the
  whole Workspace by default.
- **State**: Use the planned `PENDING/RUNNING/SUCCEEDED/PARTIAL/UNSUPPORTED/
  FAILED/CANCELLED_AT_SAFE_POINT` extraction outcomes and rebuildable index state.
- **Lineage**: Bind every hit to `ContentElement -> ExtractionRun ->
  ContextRevision -> ContextItem -> WorkspaceItem`, and to Source/Original where
  applicable.
- **Log**: Record start, outcome, partial extraction, errors, cancellation, and
  rebuild; business Events do not store full text.
- **Permission and safety**: Controlled local reads with size, time, and element
  limits; no mutation of Original, Working, or Context Object bytes and no
  automatic transmission of document contents.
- **Tool/Action**: Plan typed internal `extract_context_revisions`,
  `search_context_content`, and `rebuild_context_index` Actions; no MCP exposure.
- **AI/Automation**: Neither participates; no model, embedding, RAG, or
  automatic whole-project processing.
- **UI**: Add minimal extraction status and content search inside Project
  Context, not a new dashboard.

## 4. 待批准决策 / Decisions awaiting approval

以下 A/B 为原决策门选项；**A 均已获批准**。既有 `ADR-024` 已固定 PIG Canonical Content、可替换
Extractor、FTS5 优先和后台有界可取消，因此不能用本决策门推翻这些上位约束。

The A/B options record the original gate; **all A options are approved**. `ADR-024`
already requires PIG Canonical Content, replaceable extractors, FTS5 first,
and bounded cancellable background work; this gate cannot override them.

### D127：格式交付顺序 / Format delivery sequence

- **A（推荐 / Recommended）**：先闭环 TXT、CSV、EML 和 XLSX；随后独立评估
  PDF、DOCX、PPTX 的候选 Adapter，再决定是否纳入 V2.3 的后续子阶段。
- **B**：一次性覆盖 TXT、CSV、EML、XLSX、PDF、DOCX、PPTX；用户早获更多格式，
  但依赖评估、打包和故障定位会叠在一个验收门。

- **A (recommended)**: Complete TXT, CSV, EML, and XLSX first; evaluate
  candidate PDF, DOCX, and PPTX adapters separately before adding them in a
  later V2.3 substage.
- **B**: Cover all seven formats together; users get broader coverage sooner,
  but dependency qualification, packaging, and failure diagnosis share one gate.

### D128：复杂文档解析器 / Complex-document parser selection

- **A（推荐 / Recommended）**：以真实且可公开或获授权的 Fixture 比较候选 Adapter；
  核查页码/段落/Slide 定位、包体、速度、内存、许可证和 Windows 打包后，单独批准依赖。
  Docling 只是候选，不预装进正式运行时。
- **B**：暂不接 PDF、DOCX、PPTX，先把基础格式和检索体验验收完成；依赖更少，
  但复杂文档搜索交付推迟。

- **A (recommended)**: Compare candidate adapters using real fixtures that are
  public or explicitly authorized; assess locators, package size, speed,
  memory, license, and Windows packaging before separately approving a runtime
  dependency. Docling is only a candidate.
- **B**: Defer PDF, DOCX, and PPTX until the basic formats and search experience
  pass acceptance; this reduces dependencies but delays complex-document search.

### D129：解析执行边界 / Extraction execution boundary

- **A（推荐 / Recommended）**：后台子进程运行单次解析，Application 控制超时、取消、
  输入/输出上限和异常结果；子进程不是额外常驻服务。资源限制能力需按 Windows 实测。
- **B**：在现有后台线程中运行解析；实现简单，但第三方解析器阻塞或崩溃时隔离较弱。

- **A (recommended)**: Run one extraction in a background child process with
  application-controlled timeout, cancellation, input/output bounds, and
  structured failure. It is not an always-on service; Windows resource limits
  require verification.
- **B**: Use the existing background-thread path; simpler, but weaker isolation
  if a third-party parser hangs or crashes.

### D130：FTS5 存放位置 / FTS5 storage location

- **A（推荐 / Recommended）**：每个 Project 的 `project.sqlite` 内建派生 FTS5 表；
  与内容记录同库，迁移和查询简单，但数据库会增长并保存可检索的正文副本，必须
  提供清晰告知、索引重建和容量测试。
- **B**：在 Project 内单独存放可删的索引 SQLite；清理更容易，但跨库一致性与恢复
  更复杂。两方案都必须先验证目标 Python/SQLite 构建支持 FTS5。

- **A (recommended)**: Keep a derived FTS5 table in each Project's
  `project.sqlite`; migration and queries are simpler, but searchable text is
  copied locally and database growth requires clear disclosure, rebuild, and
  capacity tests.
- **B**: Use a separate disposable index SQLite inside each Project; cleanup
  is easier but cross-database consistency and recovery are more complex. Both
  options require checking FTS5 in the target Python/SQLite build first.

### D131：触发与版本更新 / Trigger and revision update

- **A（推荐 / Recommended）**：用户选择 `READY` Revision 后显式提取；同输入、
  Extractor 版本和配置 Hash 幂等复用。Workspace 更新只显示过期提示，不自动提取
  或替换旧结果；重建由用户明确发起。
- **B**：新的 Context Revision 创建后自动排队提取；步骤少，但大文件可能持续占用
  资源，也更难解释何时产生了正文副本。

- **A (recommended)**: Extract selected `READY` Revisions explicitly; reuse
  equivalent input/extractor-version/configuration-hash runs. Workspace changes
  only show freshness and do not replace old results; rebuild is explicit.
- **B**: Queue extraction automatically after a new Context Revision; fewer
  clicks, but large files may occupy resources unexpectedly and duplicate text
  is less visible to the user.

### D132：搜索结果定位体验 / Search-result location experience

- **A（推荐 / Recommended）**：结果显示固定 Revision、命中片段和结构化 Locator，
  并能打开对应文件；只有对特定 Host Application 验证可靠后才支持自动跳转页/单元格。
- **B**：将自动跳转到精确页/单元格列为首版硬验收；体验更直接，但不同 Office/PDF
  应用的定位能力不一致，可能产生虚假的“已定位”承诺。

- **A (recommended)**: Show fixed Revision, snippet, and typed locator and open
  the corresponding file. Enable automatic page/cell jumps only where a host
  application has been proven reliable.
- **B**: Require automatic exact jumps in the first release; more direct when
  supported, but host-app differences risk a misleading navigation promise.

## 5. 建议的分段与验收 / Proposed stages and acceptance

1. **V2.3.1 Contract + Schema**：固定 Canonical Content/Locator/Run 模型、
   Migration、Repository 和无损升级测试；不解析正文。
2. **V2.3.2 Basic Extraction**：按 D127 批次实现 Extractor、资源限制、后台进度、
   取消与状态/Event，先在无 UI 的类型化 Action 中跑通。
3. **V2.3.3 Search Core**：FTS5、结构化过滤、索引重建、幂等与升级规则；索引丢失
   不得损坏 Canonical Content 或 Context Revision。
4. **V2.3.4 Minimum UI**：在 Project Context 中显示提取状态、搜索片段、Locator、
   文件打开入口和明确错误；滚动与搜索不阻塞。
5. **V2.3.5 Acceptance**：合成与获授权的真实 Fixture 覆盖格式、定位、部分成功、
   不支持、损坏、取消、资源上限、重启和重建；复杂格式依赖经单独 Gate 才进入包。

1. **V2.3.1 Contract + Schema**: Fix canonical content, locator, and run
   contracts; migration, repositories, and lossless-upgrade tests; no parsing.
2. **V2.3.2 Basic Extraction**: Deliver approved extractor batches, resource
   bounds, background progress, cancellation, states, and Events through typed
   Actions before adding UI.
3. **V2.3.3 Search Core**: FTS5, structured filters, rebuild, idempotency, and
   extractor-upgrade rules; lost indexes cannot damage canonical content or
   Context Revisions.
4. **V2.3.4 Minimum UI**: Show extraction state, snippets, locators, file-open
   action, and explicit errors in Project Context without blocking interaction.
5. **V2.3.5 Acceptance**: Use synthetic and authorized real fixtures for format,
   locator, partial/unsupported/corrupt outcomes, cancellation, bounds, restart,
   and rebuild. Complex-format dependencies require a separate gate before
   shipping.

最小验收是：一个用户从选定 Revision 中检索一个已知词语，看到正确文件、固定版本和
可信 Locator；打开文件后能够核对原文。索引删掉后可以重建，Original、Working、
Context Object 与 V2.2 Pack 不被改写。对于尚未支持的格式必须显示明确结果，不得
伪装为“无搜索命中”。

The minimum acceptance is that a user searches a known term in a selected
Revision, sees the correct file, fixed version, and trustworthy locator, then
opens the file to verify the source. Deleting the index allows a rebuild without
rewriting Original, Working, Context Object, or V2.2 Pack bytes. Unsupported
formats report an explicit outcome rather than masquerading as zero hits.

## 6. 本轮边界 / Boundary of this entry

本文件原为 V2.3 提案；2026-10-10 用户批准 D127-A–D132-A 并要求一次性完成 V2.3。
PDF/DOCX/PPTX 的候选评估不等于运行时依赖批准。V2.2 真实资料与异机验收、旧 V1
数据库人工适配仍独立待办。
V2.4 的模型调用、AI 摘要、RAG、Vector DB、OCR、平台 Adapter、Agent 和 MCP
均不在本轮。

This was the original V2.3 proposal; on 2026-10-10 the owner approved D127-A–D132-A
and authorized V2.3 as a combined implementation. Candidate PDF/DOCX/PPTX evaluation
does not approve a runtime dependency. V2.2 real-data/cross-machine acceptance and
old-V1-database manual compatibility remain separate work. V2.4 model calls,
AI summaries, RAG, vector databases, OCR, platform adapters, Agents, and MCP
are outside this entry.
