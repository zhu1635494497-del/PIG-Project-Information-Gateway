# V2.4 项目经验与受控 AI 决策门 / V2.4 Project Experience and Controlled AI Decision Gate

- 日期：2026-10-11 / Date: 2026-10-11
- 当前授权与签收以 [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md) 为准 / Current authorization and acceptance follow [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md)
- 上位决定：[ADR-024](../decisions/ADR-024-v2-project-context-foundation.md) D102、D103、D107、D108、D111、D112 / Parent decisions: [ADR-024](../decisions/ADR-024-v2-project-context-foundation.md) D102, D103, D107, D108, D111, D112
- 本次修订取代本文 2026-10-10 的未批准提案，不修改已接受 ADR / This revision replaces this document's unapproved 2026-10-10 proposal; it does not amend accepted ADRs
- D133-A–D142-A 已获负责人批准，具体决定见 [ADR-028](../decisions/ADR-028-v2.4-project-experience-controlled-ai.md)；本文保留备选和阶段说明 / D133-A–D142-A were approved by the owner and recorded in [ADR-028](../decisions/ADR-028-v2.4-project-experience-controlled-ai.md); this file preserves alternatives and staging

## 1. 用户要完成的事 / User job

用户已经挑选关键文件、固定版本，并能定位搜索。V2.4 的首要目标是把**人为什么选择
这些材料、做过什么判断、依据是什么、结果如何**保存为可重开、可交接的项目经验；
随后允许用户明确选择固定 Revision，用可切换的外接模型 API 生成带引用的摘要、比较
或结构化提取草稿。PIG 也要为未来外部工作流提供稳定的项目上下文契约，而不是现在
就绑定某个厂商系统。

Users already select core files, fix Revisions, and search located content. V2.4 first preserves
**why people selected material, what judgments they made, their evidence, and the outcome** as
reopenable, transferable project experience. Users may then explicitly select fixed Revisions
and use switchable external model APIs for cited summary, comparison, or structured-extraction
drafts. PIG also defines a stable project-context contract for future workflow integrations,
without coupling to a vendor now.

```text
PIG Events + user-authored guidance/judgments + linked fixed ContextRevisions
  -> reviewable Project Experience -> versioned, vendor-neutral Context Bundle
  -> explicitly selected READY ContextRevision(s) + selected human context
  -> bounded input plan -> outbound preview and consent
  -> selected provider/model -> schema and citation validation
  -> separate AI draft + freshness query -> human review
```

自动 Event 能证明 PIG 内发生的操作，但不能解释原因；外部 Host Application 中的每次
保存和人的隐性思考也无法被 PIG 完整观察。因此“保留项目经验”不等于承诺自动记录
全部工作过程。用户明确写下的理由、决定和经验与自动操作事实、AI 草稿必须分层保存。

Events prove actions inside PIG, not their rationale; PIG cannot observe every save in an
external host application or every unspoken thought. Preserving experience therefore does not
promise automatic capture of all work. User-authored rationale, decisions, and lessons remain
separate from observed action facts and AI drafts.

## 2. 对象与对接边界 / Objects and integration boundary

- **操作事实 / Observed action**：复用已有结构化 Event，只陈述实际发生的 PIG 操作；
  不从点击、打开或文件修改推断用户意图。Reuse existing structured Events only for
  observed PIG actions; do not infer intent from clicks, opening, or modified bytes.
- **人工经验 / Human experience**：候选 `ProjectExperienceRecord` 具有稳定身份、类型
  （判断、决定、经验）、正文、作者、时间、草稿/确认/被取代状态；通过显式关系引用
  同 Project 的 Context Item、不可变 Revision，必要时引用 Event。修改保留可核对
  的历史，不把旧决定原地改成“从未存在”。A candidate `ProjectExperienceRecord` has
  stable identity, kind (judgment, decision, lesson), body, author, time, and draft/confirmed/
  superseded state. Explicit same-project links reference Context Items, immutable Revisions,
  and relevant Events. Revisions to a record retain reviewable history.
- V2.4 的“决定”是带来源的人工叙述记录，不提前实现 V2.5 的结构化 Decision Record、
  Timeline Entry、关系图或多视图投影。The V2.4 decision kind is a cited human narrative,
  not the structured Decision Record, Timeline Entry, relationship graph, or multiple
  projections planned for V2.5.
- **AI 草稿 / AI draft**：`AnalysisRun/Input/Result/Citation` 独立于人工经验。生成成功
  不代表人已确认；若以后支持采纳，必须是单独的人工 Action。These remain distinct from
  human experience. Successful generation is not human approval; later adoption would require
  a separate human Action.
- **对接契约 / Integration contract**：扩展已有 Context Pack，设计版本化的机器可读
  Context Bundle（项目概览、选定文件版本、人工经验、显式关系、可选 AI 草稿及引用）；
  定义同语义的类型化只读 Application Queries。Pack 与 Queries 共享领域语义，不要求
  此时启用 HTTP、MCP 或真实厂商 Adapter。Extend the existing Context Pack with a
  versioned machine-readable Context Bundle and typed read-only Application Queries sharing
  the same domain semantics. This does not require HTTP, MCP, or a vendor adapter now.

Bundle 默认不携带整个 Workspace、未选择的正文或凭据；具体外部交付仍经过用户发起的
导出预览与目标校验。外部系统未来不能直接读取 Project SQLite 或受管文件目录，也不
自动获得写入 PIG 的权限。Context Bundle 不被称作模型训练数据，也不自动上传。

The Bundle excludes the whole Workspace, unselected text, and secrets by default. External
delivery remains user-initiated with export preview and destination checks. Future systems do
not read Project SQLite or managed paths directly and receive no implicit PIG write permission.
The Bundle is not automatically training data or uploaded anywhere.

## 3. 不可跨越的边界 / Non-negotiable boundaries

- 只消费用户明确选择、Hash 已校验且有可用 Canonical Content 的固定 Revision；不自动
  读取整个 Workspace，不以可变 Working Path 作为模型输入。未提取或 `PARTIAL` 的
  Revision 必须显式说明覆盖范围，不能装作完整分析。
- 外发前显示具体 Revision、内容范围、字节/元素估算、Provider、目的和成本上限；
  目标或输入发生变化时确认失效。未确认不得传输。凭据不进 Project SQLite、日志或 Pack。
- 模型输入与输出中的指令均不获得 Action 权限。模型不得直接改文件、Context、数据库、
  Workspace Placement 或向第三方发布。Schema 与引用校验不能证明语义结论正确。
- Citation 必须回到当前项目中存在的 `ContentElement`、typed Locator 与确定 Revision；
  无法核对的引用不伪装成可信引用。结果与输入的版本关系、生成时间和失败状态可重开检查。
- AI 是可关闭的增量能力；没有模型、网络或凭据时，V1/V2.1–V2.3 工作流仍可正常使用。
  不引入 Chat、Agent、RAG/Vector DB、MCP 或平台 Adapter。
- 不同 Provider 使用同一 PIG 输入/输出契约，但能力差异必须显式展示；不支持结构化
  输出、引用或指定 Action 的模型不能在 UI 中伪装为可用。凭据按 Provider 隔离并存入
  操作系统凭据存储；不开放任意 URL 作为默认外发目标。
- 人工经验的关系、状态和作者由受控 Action 维护；自动 Event、人工记录、AI 草稿的
  作者身份与可信度在 UI、Bundle 和查询中可区分。编辑或删除不得抹除已有引用事实。

- Consume only explicitly selected, hash-verified fixed Revisions with available Canonical
  Content; do not scan the Workspace or use mutable Working Paths as model input. Disclose the
  coverage of unextracted or `PARTIAL` Revisions rather than claiming complete analysis.
- Before outbound transfer, show exact Revisions, content scope, estimated bytes/elements,
  provider, purpose, and cost bound; input or destination changes invalidate consent. Never
  transmit without confirmation. Secrets stay out of project SQLite, logs, and packs.
- Instructions in model inputs or outputs grant no Action authority. The model cannot directly
  mutate files, Context, the database, Workspace placements, or publish elsewhere. Schema and
  citation validation do not establish semantic truth.
- Each citation resolves to a project `ContentElement`, typed Locator, and exact Revision.
  Invalid references cannot be presented as trusted. Reopenable results retain input versions,
  generation metadata, and explicit failure state.
- AI is optional: V1/V2.1–V2.3 remain usable without model, network, or credentials. No Chat,
  Agent, RAG/vector database, MCP, or platform adapter is part of this milestone.
- Providers use a common PIG input/output contract while capability differences remain visible.
  A model lacking required structured output, citations, or an Action cannot appear supported.
  Secrets are isolated per provider in the OS credential store; arbitrary URLs are not default
  outbound destinations.
- Controlled Actions own human-record links, states, and authorship. UI, Bundle, and queries
  distinguish observed Events, human records, and AI drafts; edits/removal cannot erase
  already referenced facts.

## 4. 决策对照 / Decision comparison

负责人已采用以下 D133-A–D142-A，B 保留为未采纳备选。D133、D139、D140 已按
项目经验与多模型目标修订；D141、D142 为新增决策。具体 Provider、模型、服务条款、
数据保留和成本参数仍须在首次真实外发前记录并核验；本批准不授权试传业务资料。

The owner accepted D133-A–D142-A below; B options remain unselected alternatives. D133, D139,
and D140 were revised for project experience and multiple models, while D141 and D142 were added.
Before the first real outbound request, record and verify the provider, model, terms, retention,
and cost limits. Approval does not authorize trial transmission of business material.

### D133：V2.4 用户闭环顺序 / V2.4 user-loop order

- **A（推荐 / Recommended）**：先完成“人工记录判断 → 关联固定 Revision → 重开与
  Bundle 交接”的无 AI 闭环，再分段交付引用式摘要、双 Revision 比较和一种明确 Schema
  的提取。每段独立验收；V2.4 最终仍覆盖三类 AI Action。
- **B**：先交付三类 AI Action，人工经验记录与 Bundle 扩展后置；AI 更早可用，但项目
  经验仍主要散落在文件、Event 和 Item 说明中，不符合本轮提出的首要价值。

- **A (recommended)**: First close the no-AI loop of authoring a judgment, linking fixed
  Revisions, reopening it, and handing it off in a Bundle. Then stage cited single-Revision
  summary, two-Revision comparison, and one explicitly schematized extraction, accepting each
  independently while retaining all three AI Actions as V2.4 targets.
- **B**: Deliver the three AI Actions first and defer human experience and Bundle extension.
  AI arrives sooner, but experience remains scattered across files, Events, and Item guidance.

### D134：模型运行来源 / Model execution source

- **A（推荐 / Recommended）**：先接一个用户自备凭据的远程 Provider，经可替换 Port；
  每次外发仍需 D135 确认。最小可用质量更容易检验，但有隐私、网络和费用成本。
- **B**：先只接本机模型；没有文件内容外发，但模型体积、设备性能、质量和 Windows
  打包成本需先评估，首个可用版本可能推迟。

- **A (recommended)**: Start with one remote provider using user-supplied credentials behind a
  replaceable port, with per-request D135 consent. Quality is easier to evaluate initially,
  at the cost of privacy, connectivity, and fees.
- **B**: Start with a local model only; file content stays on-device, but model size, device
  performance, quality, and Windows packaging require qualification and may delay delivery.

### D135：外发授权粒度 / Outbound consent granularity

- **A（推荐 / Recommended）**：每次请求展示输入计划并绑定一次性确认；重试若输入、
  Provider 或模型变化，重新确认。操作稍多，但用户知道本次哪些内容离开设备。
- **B**：对完全相同的固定输入集合、Provider、模型和目的签发有期限的可复用授权；
  后续同一计划少一次点击，但授权管理和失效校验更复杂，任何范围变化仍须重新确认。

- **A (recommended)**: Preview and confirm each request; a retry with changed input, provider,
  or model needs fresh consent. More interaction, but the user sees what leaves the device.
- **B**: Reuse time-limited consent only for the exact same fixed input set, provider, model,
  and purpose; fewer clicks on identical retries, but more complex consent expiry and validation.
  Any changed scope still requires fresh confirmation.

### D136：长内容处理 / Long-input handling

- **A（推荐 / Recommended）**：由后端生成有界、可预览的元素集合；超预算明确显示
  `PARTIAL_INPUT`、遗漏范围和预计成本，用户确认后才发送。绝不静默截断并宣称全篇摘要。
- **B**：超预算直接拒绝，请用户手工缩小 Revision 或元素范围；语义简单、覆盖可控，
  但长文件的核心用例会较难完成。

- **A (recommended)**: Build a bounded, previewable element set. If it is incomplete, show
  `PARTIAL_INPUT`, omitted range, and estimated cost before consent; never silently truncate
  while claiming a full-document summary.
- **B**: Reject over-budget requests until the user narrows the selected range; simpler and
  precise, but less useful for long core files.

### D137：结果引用与可信标记 / Citations and trust labeling

- **A（推荐 / Recommended）**：结构化结果中的每项实质陈述携带一个或多个 Element
  引用；后端验证 Revision、Element、Locator 属于本次输入。引用错误的结果不能标为
  成功，保留可诊断的失败/待核对状态；人仍需判断陈述是否真实。
- **B**：允许部分陈述没有有效引用，但逐项标为“未核对”，整个结果不得标为
  `SUCCEEDED` 或作为可引用结论；模型兼容性更强，用户核对负担更高。

- **A (recommended)**: Each material statement in structured output carries one or more
  element citations. The backend verifies that Revision, Element, and Locator belong to the
  request. Invalid citations cannot yield a successful result; humans still assess truth.
- **B**: Allow uncited statements only when individually labeled unverified; the whole result
  cannot be `SUCCEEDED` or used as a citable conclusion. This is more model-compatible but
  shifts more checking to the user.

### D138：AI 草稿保存范围 / Persistence of AI drafts

- **A（推荐 / Recommended）**：Project 内保存经校验的结构化草稿、引用、输入 ID/Hash、
  Prompt/模型版本、状态与最少必要用量；不保存 Secret、完整外发 Payload 或 Debug 正文。
  草稿可重开；默认保留至用户显式清理，已被人工记录或交付引用的草稿不能被静默清理，
  清理前预览影响并确认。
- **B**：只在当前会话显示，用户明确保存才落库；默认暴露更少，但关闭后无法复核
  来源、错误或过期状态，且验收跨重启流程较弱。

- **A (recommended)**: Persist validated structured drafts, citations, input IDs/hashes,
  prompt/model versions, status, and minimal usage within the project. Never persist secrets,
  full outbound payloads, or document text in debug logs. Retain drafts until explicit user
  cleanup; referenced drafts cannot be silently removed, and cleanup previews impact and
  requires confirmation.
- **B**: Display session-only results until the user saves them; less default persistence,
  but weaker reopening, provenance review, and stale-result inspection.

### D139：Provider 适配数量 / Provider adapter count

- **A（推荐 / Recommended）**：稳定一个 Provider Port，先验收一个真实 Adapter 的
  完整闭环，再接第二个真实 Adapter；V2.4 完成时用户可在至少两个合格 Provider 的
  模型之间切换。逐个验证能力、凭据、失败、超时、取消、无网和费用展示。本选项以
  D134-A 的远程 API 路线为前提；若选 D134-B，须另定本机模型选择与打包 Gate。
- **B**：V2.4 只交付一个真实 Provider，但保留可替换 Port；首版成本较低，暂时不能
  满足用户在 PIG 内选择不同外接模型的目标。

- **A (recommended)**: Stabilize one provider port, accept one real adapter's full loop, then
  qualify a second. By V2.4 completion users can switch between models from at least two
  qualified providers. Verify capabilities, secrets, failures, timeouts, cancellation, offline
  behavior, and cost display for each adapter. This option assumes D134-A's remote-API route;
  D134-B requires a separate local-model selection and packaging gate.
- **B**: Deliver one real provider in V2.4 with a replaceable port. This costs less initially
  but does not yet satisfy in-app choice among external models.

### D140：最小 UI 位置 / Minimum UI location

- **A（推荐 / Recommended）**：在简洁的核心文件视图中，文件旁提供“为什么重要／
  使用提醒”和关联的判断；另用克制的“项目脉络”列表查看跨文件人工记录。AI Action
  仍从选定 Revision 旁按需展开，包含模型选择、外发预览、进度、引用与过期标记。
  不新增 AI 主页或自由聊天入口。
- **B**：独立的项目叙事画布和 AI 工作台；展示空间更大，但首版导航、状态同步与
  用户认知成本明显增加。

- **A (recommended)**: Keep file-specific guidance and linked judgments beside core files;
  show cross-file human records in a restrained Project Journey list. Expand AI Actions only
  beside selected Revisions, with model choice, outbound preview, progress, citations, and
  stale labels. No AI home page or free chat entry.
- **B**: Build a separate narrative canvas and AI workbench; there is more room, but more
  navigation, synchronization, and cognitive cost in the first release.

### D141：人工经验的事实模型 / Human-experience fact model

- **A（推荐 / Recommended）**：新增最小 `ProjectExperienceRecord` 与显式关系，先支持
  判断、决定、经验三种类型、草稿/确认/被取代状态和可核对修改历史。复用已有 Event
  作为操作事实，保留现有 Item Annotation 的文件阅读说明职责；不把三者混成一张日志。
- **B**：只扩展现有 Annotation 和 Event；Schema 变化较少，但项目级跨文件判断、
  后续更正与外部交接会受 Item 所有权和 Event 语义限制。

- **A (recommended)**: Add a minimal `ProjectExperienceRecord` with explicit links, initially
  supporting judgment, decision, and lesson kinds; draft/confirmed/superseded states; and
  reviewable edit history. Reuse Events for observed actions and existing Item Annotations for
  file-reading guidance rather than collapsing all three into a log.
- **B**: Extend only Annotations and Events. This limits schema changes but strains Item
  ownership and Event meaning for cross-file judgments, corrections, and handoff.

### D142：外部工作流接入边界 / External workflow integration boundary

- **A（推荐 / Recommended）**：V2.4 扩展 Context Pack 为有 Schema 版本的机器可读
  Bundle，并稳定相同语义的只读 Application Query Contract；先验证导出、再导入的
  合成消费者流程。真实飞书等 Adapter、HTTP Server、OAuth、Webhook、双向同步和
  外部写入不在本阶段。
- **B**：V2.4 同时实现一个真实平台 Adapter；可较早验证某个系统的体验，但服务
  认证、权限、版本和平台约束会提前进入 PIG，扩大部署与测试范围。

- **A (recommended)**: Extend Context Pack into a schema-versioned machine-readable Bundle
  and stabilize read-only Application Queries with the same semantics. Test export and import
  with a synthetic consumer. Real vendor adapters, HTTP servers, OAuth, webhooks, two-way sync,
  and external writes remain out of scope.
- **B**: Implement one real platform adapter in V2.4. It validates one integration earlier but
  imports service authentication, permissions, versions, and vendor constraints into this phase.

## 5. 分段与验收建议 / Proposed stages and acceptance

每段先完成可运行、可测试、可重开的最小闭环；后段不能把前段的人工事实降格为模型草稿。

Each stage closes a runnable, testable, reopenable loop. Later model drafts cannot demote
earlier human-authored facts.

1. **V2.4.1 Experience Contract**：明确 Record 身份、作者、状态、修改历史、与
   Revision/Event 的显式关系，以及 Bundle Schema 与只读 Query；用合成案例验证
   “操作事实≠判断理由”。不调用模型。
2. **V2.4.2 Human Experience Loop**：受控 Migration、Application Actions、简洁的
   记录/关联/更正 UI，重启重开与 Context Pack 扩展。合成消费者能读取 Bundle；
   不实现真实工作流系统连接。
3. **V2.4.3 AI Contract + Provider Gate**：Typed Actions、输入计划、Citation、
   Run 状态和威胁模型；假 Provider 验证失败、超时、取消和无网。首个真实 Provider
   的模型、条款、数据保留、凭据与成本上限需单独核验。
4. **V2.4.4 Cited Summary**：单固定 Revision 摘要、逐项引用、每次外发预览/确认、
   后台进度、失败/重试和重启后的草稿检查；无凭据时人工经验闭环仍正常。
5. **V2.4.5 Model Choice + Compare/Extract**：资格评估后接第二个真实 Provider，
   展示可用模型及能力差异；再完成双 Revision 比较和一种明确 Schema 的提取。
   不支持的模型/Action 不提供假入口。
6. **V2.4.6 Acceptance**：合成数据验证关系与历史、Bundle 兼容、正确/错误引用、
   过期、Provider 切换、无网、拒绝外发、预算上限与 UI 响应。真实资料的读取、
   外发和异机/打包验收分别授权与记录。

1. **V2.4.1 Experience Contract**: Define Record identity, author, state, edit history,
   explicit Revision/Event links, Bundle schema, and read-only queries. Synthetic examples
   distinguish observed action from rationale; no model calls.
2. **V2.4.2 Human Experience Loop**: Controlled migration, Actions, compact author/link/correct
   UI, restart-safe reopening, and Context Pack extension. A synthetic consumer reads the Bundle;
   no real workflow-system connection.
3. **V2.4.3 AI Contract + Provider Gate**: Typed Actions, input plans, citations, Run states,
   and threat model; a fake provider tests failures, timeouts, cancellation, and offline behavior.
   Separately qualify the first real provider/model, terms, retention, secrets, and cost bounds.
4. **V2.4.4 Cited Summary**: Single fixed-Revision summary, per-claim citations, per-request
   outbound preview/consent, background progress, failure/retry, and restart-safe drafts.
   Human experience still works without credentials.
5. **V2.4.5 Model Choice + Compare/Extract**: Qualify a second real provider and expose
   model/capability differences; then deliver two-Revision comparison and one explicit extraction
   schema. Unsupported model/Action combinations have no false entry points.
6. **V2.4.6 Acceptance**: Synthetic checks for links/history, Bundle compatibility, valid/invalid
   citations, freshness, switching, offline behavior, denied transmission, budgets, and UI
   responsiveness. Record separate authorization and evidence for real data, outbound use,
   cross-machine, and packaged-desktop acceptance.

V2.4 的无 AI 验收：用户记录一项判断，关联两个固定文件版本和可选操作事实；重启后
可读、更正后可见历史，导出的 Bundle 能由合成消费者按 Schema 重建该判断与依据。
V2.4 的 AI 验收：用户选择固定 Revision、Provider/模型和 Action，预览并确认确切外发
范围；至少两个合格 Provider 可切换，结果引用能回到本次输入的 Revision 与 Locator，
错误引用被拒绝。Workspace 变化只标记旧草稿过期。没有模型、网络或凭据时，前一闭环、
Context Pack 和本地搜索仍可用。

No-AI acceptance: a user records a judgment linked to two fixed file Revisions and an optional
observed Event; it reopens after restart, corrections retain history, and a synthetic consumer
reconstructs the judgment and evidence from the schema-versioned Bundle. AI acceptance: the user
selects a fixed Revision, provider/model, and Action; previews and confirms the exact outbound
scope; switches between at least two qualified providers; verifies result citations against
the selected Revision and Locator; and sees invalid citations rejected. Workspace changes only
mark old drafts stale. Human records, Context Pack, and local search remain usable offline.

## 6. 后续停止线 / Remaining gates

D133-A–D142-A 已批准分段实施，先完成 V2.4.1 的契约与合成验证。首个真实 Provider
进入发布路径前必须单独核验模型、条款、数据保留、凭据、费用与打包行为；真实业务资料
外发需要对应的用户授权和逐次确认。厂商工作流 Adapter、HTTP/MCP Server、外部写入、
RAG/Vector DB 不在本阶段。V2.3 PDF/DOCX/PPTX 解析器资格评估仍为独立 Gate。

D133-A–D142-A authorize staged implementation, beginning with V2.4.1 contracts and synthetic
validation. Before a real provider enters the release path, separately qualify its model,
terms, retention, secrets, costs, and packaged behavior. Real business-data transmission needs
the corresponding user authorization and per-request consent. Vendor workflow adapters,
HTTP/MCP servers, external writes, and RAG/vector databases remain out of scope. The V2.3
PDF/DOCX/PPTX parser-qualification gate remains separate.
