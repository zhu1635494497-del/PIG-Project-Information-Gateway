# V2.2 Context Pack 决策门 / V2.2 Context Pack Decision Gate

- 状态：D120-A 至 D126-A 已批准；V2.2 全段随后获一次性授权 / Status: D120-A through D126-A approved; all V2.2 stages subsequently authorized together
- 日期：2026-10-08 / Date: 2026-10-08
- 上位约束：`ADR-010`、`ADR-024`、`ADR-025` / Parent constraints: `ADR-010`, `ADR-024`, `ADR-025`

## 1. 要解决的问题 / Problem to solve

V2.1 已让用户挑选核心文件、添加 Section 与人工说明，并锁定不可变 Revision，但
这些信息只在本机 Project 中。V2.2 要交付一个离线、可复制、可校验的 Context Pack，
让另一台机器上的收件人理解项目概览、核心材料、选定版本和人工说明。它不是 V1 的
当前 Workspace 文件导出，也不是备份、同步或向飞书等平台发送。

V2.1 lets users select core files, organize Sections, add human guidance, and
fix immutable Revisions, but those facts remain in the local Project. V2.2
delivers an offline, portable, verifiable Context Pack so a recipient on another
machine can understand the project overview, selected material, exact versions,
and human guidance. It is not V1's current Workspace export, a backup, sync,
or delivery to Feishu or another platform. V2.2 includes human Annotations but
no Analysis Results, because AI Analysis is not implemented yet.

## 2. 实施前影响 / Pre-implementation impact

| 维度 / Dimension | V2.2 影响 / V2.2 impact |
| --- | --- |
| Domain | `ContextPackExport`、显式 `ContextPackEntry` 引用所采用的 `ContextRevision`；不新增第二套 Project。<br>`ContextPackExport` and explicit `ContextPackEntry` reference adopted `ContextRevision` records; no second Project. |
| Flow | 用户选择范围 → 预检并冻结计划 → 读取不可变对象 → 生成概览/Manifest/文件 → 原子发布 → 记录结果。<br>User scope → preflight and freeze plan → read immutable objects → generate overview/manifest/files → atomic publish → record outcome. |
| State | `PENDING → PREFLIGHTED → RUNNING → SUCCEEDED`，或安全点 `CANCELLED_AT_SAFE_POINT` / `FAILED`；不推进 Workspace/Context Revision。<br>The same export state machine; no Workspace or Context Revision increment. |
| Lineage | Entry 显式引用 Context Item 与固定 Revision；Manifest 保存可迁移的最小来源 ID，不把物理路径当身份。<br>Entries reference Context Items and fixed Revisions; the manifest carries portable origin IDs, not physical paths as identity. |
| Log | 请求、预检、成功、失败、取消采用结构化 Event；不记录文件正文或敏感绝对路径。<br>Structured requested, preflighted, completed, failed, and cancelled Events; no document body or sensitive absolute paths. |
| Permission | 导出是用户明确发起的外部写入；目标、覆盖、符号链接、容量和文件名须由后端校验。<br>Export is an explicit user-initiated external write; backend validates destination, overwrite, symlinks, capacity, and names. |
| Tool | 形成 typed `preflight_context_pack_export`、`export_context_pack`、`get_context_pack_export` Application Actions；不建设 MCP。<br>Typed reusable Application Actions; no MCP. |
| AI / Automation | 均不使用；项目概览由确定性数据生成，不调用模型或自动外发。<br>Neither is used; overview is deterministic and no model or automatic send is involved. |
| UI | Context 视图增加最小导出入口、预检摘要、进度/取消和结果；不建设新 Dashboard。<br>Minimum Context export entry, preflight summary, progress/cancel, and result; no new dashboard. |

## 3. 待确认决策 / Decisions awaiting approval

以下 A/B 为原始决策对比；产品负责人现已批准全部 A 方案，正式结果见 `ADR-026`。

The A/B options below preserve the original comparison. The product owner has
now approved every A option; `ADR-026` is the authoritative decision record.

### D120：交付形式 / Delivery formats

- **A（推荐）**：V2.2 同时完成普通目录包和 ZIP 包，先实现目录发布，再复用同一 Pack Plan
  实现 ZIP。用户明确选择格式。优点是便于人工查看和单文件传送；代价是两套发布 Adapter
  与测试，但 Manifest/Entry 语义保持一套。
- **B**：V2.2 只做 ZIP，目录包推迟。交付入口更简单，但与现有里程碑的目录/ZIP 验收范围
  不一致，需要同步收缩里程碑。

- **A (recommended)**: Deliver both a normal directory pack and a ZIP pack in
  V2.2, implementing directory publication first and reusing the same Pack Plan
  for ZIP. The user selects the format. This supports browsing and single-file
  transfer, at the cost of two publication adapters and test paths.
- **B**: Deliver only ZIP in V2.2 and defer directory output. The entry point is
  simpler, but the existing directory/ZIP milestone scope must be narrowed.

### D121：Revision 选择 / Revision selection

- **A（推荐）**：默认采用每个 Active Context Item 的当前 READY Revision；预检时允许
  逐 Item 显式选择仍可用的历史 READY Revision，并在 Entry 中固定选择结果。
- **B**：仅允许当前 Revision。实现较窄，但无法有意交付经核准的上一版。

- **A (recommended)**: Default to the current READY Revision of every active
  Context Item; preflight allows an explicit per-Item choice of another available
  READY Revision, frozen in Entries.
- **B**: Current Revision only. Narrower implementation, but users cannot
  intentionally deliver an approved previous version.

### D122：项目概览来源 / Project overview source

- **A（推荐）**：用 Project 名称、Section 名称/说明、Item 用途和人工 Annotation 确定性
  生成双语模板的 `README.md`；用户原文保持原样，不自动翻译；不新增项目级自由文本
  字段。避免凭空生成业务结论，用户需先在 Context 填写有效说明。
- **B**：V2.2 新增持久化项目级 Overview 字段和编辑 Action。可表达项目整体背景，
  但扩大 Schema、并发和 UI 范围。

- **A (recommended)**: Deterministically generate a bilingual-template
  `README.md` from Project name, Section names/descriptions, Item purposes, and
  human Annotations. Preserve user text verbatim without automatic translation.
  Add no project-level free-text field and invent no business conclusions.
- **B**: Add a persistent Project-level Overview field and edit Action in V2.2.
  This better expresses overall context but expands schema, concurrency, and UI.

### D123：包内文件组织 / Pack file organization

- **A（推荐）**：一个选定 Context Item 的字节只放一份；`files/` 下使用稳定 ID 加安全
  文件名，Section/Placement 的多对多关系在 Manifest 和概览中表达。避免跨 Section
  重复文件、同名冲突与物理路径泄漏。
- **B**：按 Section 镜像目录；同一 Item 可在多个 Section 下重复出现。更像文件夹，
  但体积增加，收件人可能误认副本为不同版本。

- **A (recommended)**: Include selected bytes once per Context Item under
  `files/` with a stable ID and safe filename. Express many-to-many Section
  Placements in the manifest and overview, avoiding duplicate bytes, name
  collisions, and physical-path disclosure.
- **B**: Mirror Section directories and duplicate an Item when it has multiple
  Placements. Familiar as folders, but larger and potentially misleading.

### D124：过期与缺失 / Freshness and missing bytes

- **A（推荐）**：`WORKSPACE_UPDATED` 仅在预检中警告；用户明确确认后仍可导出已锁定
  Revision。缺失或 Hash 不匹配的 Context Object 一律阻断，不回退 Working/Original。
- **B**：只允许 `CURRENT`。规则简单，但会阻止有意交付已核准历史版本。

- **A (recommended)**: `WORKSPACE_UPDATED` produces a preflight warning, and
  an explicit user confirmation may still export the fixed Revision. A missing
  or hash-mismatched Context Object always blocks; never fall back to Working
  or Original bytes.
- **B**: Require `CURRENT`. Simpler, but blocks deliberate delivery of an
  approved historical version.

### D125：目标冲突与原子发布 / Destination conflict and atomic publication

- **A（推荐）**：仅允许 Project 受管目录之外的绝对目标；目标已存在则失败，不覆盖或
  自动改名。同一目标卷内 staging，验证后原子发布；失败/取消清理 staging。
- **B**：可由 UI 选择覆盖已有目标。减少改名操作，但覆盖外部文件的风险和恢复复杂度
  明显更高。

- **A (recommended)**: Accept only an absolute destination outside the managed
  Project tree. Fail if it exists; neither overwrite nor silently rename.
  Stage on the destination volume and publish atomically after verification,
  cleaning staging on failure/cancel.
- **B**: Allow user-confirmed overwrite. Fewer rename steps but materially
  higher external-data and recovery risk.

### D126：历史与并发 / History and concurrency

- **A（推荐）**：持久化 Export 与 Entry；成功包的 Revision 引用受到保留保护。预检返回
  一次性计划 Token，执行时重验 `context_revision`、Entry、容量和目标状态；状态/事件支持
  重启后查看。失败或取消不伪装成功，也不保留无效保护引用。
- **B**：只生成包，不记录完整 Entry 历史。Schema 较小，但不能证明过去交付了哪些
  Revision，且会削弱已有保留策略。

- **A (recommended)**: Persist Export and Entry records; successful packs
  protect referenced Revisions. Preflight returns a one-use plan token;
  execution revalidates `context_revision`, Entries, capacity, and destination.
  Status/events remain queryable after restart. Failure/cancel never masquerades
  as success or protect invalid references.
- **B**: Generate a pack without full Entry history. Smaller schema, but no
  reliable record of which Revisions were delivered and weaker retention rules.

## 4. 最小分段 / Minimum staged delivery

决策批准后，仍分段实现，每段需有最小可运行、可测试、数据流闭环：

After decisions are approved, implementation still proceeds in independently
runnable, testable, closed-loop stages:

1. **V2.2.1 Contract + Schema**：Export/Entry、状态、Repository、Migration 和
   只读 Pack Plan 查询；测试关系、约束和重启读取。
2. **V2.2.2 Directory Pack Core**：预检、固定 Revision、生成概览/Manifest、流式复制、
   Hash 验证、原子目录发布、失败/取消；测试路径、同名、大文件、冲突与恢复。
3. **V2.2.3 ZIP + Minimum UI**：复用同一计划生成 ZIP，在 Context 视图提供选择、
   预检、后台进度/取消与结果；测试 GUI 心跳和两个格式内容等价。
4. **V2.2.4 Acceptance**：合成数据先行，再由用户决定是否使用真实资料；异机解包
   验证文件 Hash、Manifest、概览、人工说明和固定版本。

1. **V2.2.1 Contract + Schema**: Export/Entry records, state, repositories,
   migration, and read-only Pack Plan query; test relationships, constraints,
   and reopen.
2. **V2.2.2 Directory Pack Core**: Preflight, frozen Revisions,
   overview/manifest, streaming copy, hash check, atomic directory publication,
   failure/cancel; test paths, duplicate names, large files, conflict, recovery.
3. **V2.2.3 ZIP + Minimum UI**: Reuse the plan for ZIP and add Context selection,
   preflight, background progress/cancel, and result; test GUI heartbeat and
   content equivalence across formats.
4. **V2.2.4 Acceptance**: Synthetic inputs first; the user then decides whether
   real data is needed. On another machine verify hashes, manifest, overview,
   human guidance, and fixed versions.

## 5. 本轮停止线 / Stop line for this turn

D120-A 至 D126-A 已获批准。原停止线只授权 V2.2.1；2026-10-09 用户明确
一次性授权 V2.2.2–V2.2.4。不得扩展至 V2.3、内容解析、AI 或平台适配。

D120-A through D126-A are approved. The original stop line authorized only
V2.2.1; on 2026-10-09 the user explicitly authorized V2.2.2–V2.2.4 together.
V2.3, content extraction, AI, and platform adapters remain outside scope.
