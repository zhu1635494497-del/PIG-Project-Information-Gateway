# 当前范围与授权 / Current Scope and Authorization

状态记录更新：2026-10-16。本文件集中维护阶段、授权和验收状态；历史文档保留原记录。
新授权必须写明范围和证据，不能从“已规划”推导出“已批准实施”。

Status record updated: 2026-10-16. This file owns phase, authorization, and acceptance status;
historical documents retain their original records. Record the scope and evidence of new
authorization; planning alone never implies implementation approval.

## 1. 当前阶段 / Active phase

负责人于 2026-10-16 明确授权新的默认主流程与项目模型：关联现有 Windows 目录、
直接打开当前原文件、识别外部修改、按需固定版本、经人工确认后保存一条绑定该版本的
经验。拖入只建立关联；旧仓库、Git 历史和旧代码保留，但新项目默认不沿用 Snapshot
Workbench，也不迁移旧项目。先修订冲突规则与 [ADR-033](../decisions/ADR-033-linked-project-default-flow.md)，
再实现最小闭环。悬浮球、项目 AI、个人 AI、真实资料外发均不在本轮范围。

On 2026-10-16 the owner authorized a new default model and flow: link an existing Windows
folder, open current source files, observe external changes, capture immutable versions on demand,
and confirm one experience bound to that version. Drops create links only. Keep the repository,
Git history, and old code, but do not default new Projects to the Snapshot Workbench or migrate
older Projects. Revise conflicting rules and [ADR-033](../decisions/ADR-033-linked-project-default-flow.md)
before implementing the minimum loop. Floating UI, Project AI, Personal AI, and real-data egress
remain out of scope.

以下 V1/V2.4 记录是旧主流程的历史验收，不再定义新项目的默认所有权策略。

The V1/V2.4 record below is historical acceptance for the former flow, not the default
ownership policy for newly linked Projects.

用户已确认“轻量双栏”桌面 UI 的人工验收通过，并批准 **D133-A–D142-A** 与
**D143（OpenAI/DeepSeek）、D144-A–D146-A**，继续 V2.4。人工经验、Bundle 和
受控 AI 的源码实现已进入合成测试；用户已确认 V2.4 收尾清单第 1、2 项人工
验收完成。随后负责人将收尾范围缩为 DeepSeek 单 Provider，并选择仅本机源码桌面
对指定合成项目受限开放。真实业务资料、打包版和正式生产资格未签收；不授权厂商
工作流 Adapter。
V1 Workbench 是稳定底座；V2.1 Project Context、V2.2 Context Pack 与 V2.3 本地
内容搜索已在其上演进。

The owner confirmed manual acceptance of the light two-pane desktop UI and approved
**D133-A–D142-A** plus **D143 (OpenAI/DeepSeek) and D144-A–D146-A** for V2.4.
Source implementation for human experience, Bundle, and controlled AI is in synthetic testing;
the owner confirmed completion of manual acceptance items 1 and 2 in the V2.4 closure list.
The owner later narrowed closure to DeepSeek alone and selected bounded local source-desktop
egress for one synthetic Project. Real business data, packaged release, and formal production
qualification remain unaccepted; no vendor workflow adapter is authorized. V1 Workbench
remains the foundation, extended by V2.1 Project Context, V2.2 Context Pack, and V2.3 local
content search.

| 范围 / Scope | 当前状态 / Current status |
| --- | --- |
| ADR-024 D101-A–D112-A；ADR-025 D113-A–D119-B；ADR-026 D120-A–D126-A | 已批准设计 / Accepted design |
| ADR-028 D133-A–D142-A | 已批准 V2.4 设计与分段实施；先执行 V2.4.1，不代表具体 Provider 或真实资料外发已批准 / V2.4 design and staged implementation authorized; V2.4.1 first, without approval for a concrete provider or real-data transmission |
| V2.1.5 与 V2.2 | 用户确认合成数据源码桌面验收通过；不等于所有环境验收 / User confirmed synthetic-data source-desktop acceptance, not every environment |
| V2.2.2–V2.2.4 | 已一次性授权目录/ZIP 发布、最小 UI、合成资料验收 / Directory/ZIP publication, minimum UI, and synthetic acceptance authorized together |
| V2.3 | D127-A–D132-A 与 V2.3.1–V2.3.5 已获授权并实施；用户于 2026-10-10 确认人工验收通过。该确认不等于真实资料、异机或所有打包环境已验证 / D127-A–D132-A and V2.3.1–V2.3.5 were authorized and implemented; owner confirmed manual acceptance on 2026-10-10, without claiming real-data, cross-machine, or every packaged environment check |
| 桌面 UI 简化 / Desktop UI simplification | 已按“轻量双栏”草图修改；自动化 UI 回归 20 通过、4 历史用例跳过；用户于 2026-10-11 确认人工验收通过，不据此宣称打包或异机验收 / Implemented against the light two-pane sketch; UI regression: 20 passed, 4 historical skips; owner confirmed manual acceptance on 2026-10-11, not packaged or cross-machine acceptance |
| V2.4 | 人工经验、Bundle 2.0、AI 输入/引用/假 Provider 与最小 UI 已实施；用户确认收尾清单第 1、2 项人工验收完成。DeepSeek 合成调用成功；当前仅指定合成项目可在本机源码桌面逐次确认外发。OpenAI、其他项目、打包版与真实业务资料外发均未开放；正式 Provider/发布资格未签收 / Human experience, Bundle 2.0, AI planning/citations/fake provider, and minimum UI are implemented; the owner accepted closure items 1 and 2. A DeepSeek synthetic call succeeded; only the specified synthetic Project may transmit after per-request confirmation from the local source desktop. OpenAI, other Projects, packaged runs, and real business data remain blocked; formal provider/release qualification is unsigned |
| V2.4 工作区验收反馈（2026-10-12） / Workspace feedback | 用户授权修复 B01/B02 及拖动、展开、版本按钮和重命名；源码与合成测试完成，用户随后确认 V2.4 收尾清单第 1 项人工复测完成 / Owner authorized B01/B02, drag, expansion, version-button, and rename fixes; source and synthetic checks completed, and the owner later confirmed manual retest under V2.4 closure item 1 |
| V2.4 后续交互反馈（2026-10-12） / Subsequent interaction feedback | 用户授权右键在所选文件夹下新建、同位置拖动不报错、ZIP/7z Container View 导出当前展开结构，并修复 C04 Revision 选择；空文件夹 Snapshot 误判也已修复。源码及针对性测试完成，用户随后确认 V2.4 收尾清单第 1 项人工复测完成 / Owner authorized child-folder creation, no-op drop, ZIP/7z expanded-structure export, and C04 Revision selection; the empty-folder Snapshot false positive was fixed. Source and focused checks completed; the owner later confirmed manual retest under V2.4 closure item 1 |
| V2.4 D01 与物理位置反馈（2026-10-12） / D01 and physical-location feedback | 每个 Workspace 文件的只读物理位置查询、单字段录入及 `ExperienceKind` 类型修复已实现；用户随后确认 V2.4 收尾清单第 1、2 项人工验收完成。Excel 跨文件公式仅评估，未授权自动改写链接或重构 Working 存储 / Read-only physical-location query, single-field entry, and `ExperienceKind` conversion are implemented; the owner later confirmed V2.4 closure items 1 and 2. Excel cross-file links were assessed only, without authority to rewrite formulas or redesign Working storage |
| V2.4 导出/E01/F01 反馈（2026-10-12） / Export/E01/F01 feedback | 目录包已改为可读文件名直列及同名编号，AI 预览显式转换 `AnalysisAction`，损坏 ZIP 优先显示来源处理失败；针对性合成/离屏复测通过，用户随后确认 V2.4 收尾清单第 1 项人工复测完成 / Directory packs use readable direct filenames with collision numbering, AI preview converts `AnalysisAction`, and corrupt ZIP surfaces its source failure. Focused synthetic/offscreen checks passed; the owner later confirmed manual retest under V2.4 closure item 1 |
| V2.4 SDK 接入 / SDK integration | 用户于 2026-10-13 明确授权完成 API 接入开发。运行时已采用 OpenAI 官方 Python SDK `>=3.29,<3.30` 服务 OpenAI 与 DeepSeek 的固定端点，并补回实际 2 MB 响应上限、无自动重试/重定向及安全错误映射。最终组合合成回归 31 通过，Windows `onedir` 构建/包内合成流程通过；此前导入会话测试有间歇失败，见实施验收记录。未使用真实 Key，两个 Provider 仍未完成账号级资格，`live_enabled=False` 与业务资料外发 Gate 不变 / On 2026-10-13 the owner explicitly authorized completing API integration. Runtime now uses the official OpenAI Python SDK `>=3.29,<3.30` for the fixed OpenAI and DeepSeek origins, preserving an actual 2 MB response cap, no automatic retries/redirects, and safe error mapping. The final combined synthetic regression passed 31 cases, and the Windows `onedir` build/packaged synthetic flow passed; an earlier import-session test was intermittent (see the implementation/acceptance record). No real key was used; neither provider has account-level qualification, and `live_enabled=False` and the business-data egress gate remain unchanged |
| V2.4 Provider 资格准备 / Provider qualification preparation | 2026-10-13 已核对两家公开模型、Responses 能力与当前标价，并在本机只检查 PIG 凭据是否存在；OpenAI、DeepSeek 凭据均未发现。未进行真实调用，账号条款/留存/账单未签收，外发开关不变。步骤与来源见 V2.4 实施验收记录 / On 2026-10-13 public model, Responses, and posted prices were checked, and only the presence of PIG credentials was inspected locally; neither OpenAI nor DeepSeek entry was found. No live call occurred; account terms, retention, and billing remain unaccepted, and egress stays disabled. Steps and sources are in the V2.4 implementation/acceptance record |
| V2.4 凭据与精确预览（2026-10-16） / Credentials and exact preview | 用户报告已保存密钥；在允许读取 Windows Credential Manager 条目名称的环境中确认 OpenAI、DeepSeek 两个 PIG 目标均存在，未读取或输出密钥正文。已创建独立合成项目，固定 Revision 摘要输入 5 行，两个 Provider 的预览及费用估算通过；这是外发前检查，结果见下一行 / The owner reported saving keys; both PIG target names were visible in an environment allowed to list Windows Credential Manager entries, without reading or displaying secret values. An isolated synthetic project was created, and both providers' five-line fixed-Revision summary previews and estimates passed. This was the preflight; the outcome follows in the next row |
| V2.4 OpenAI 合成试验（2026-10-16） / OpenAI synthetic trial | 用户随后明确批准向 OpenAI `gpt-6-luna` 发送预览的五行虚构内容一次。预检通过，Provider 返回 HTTP 401；Run 为 `FAILED`，`AI_RUN_STARTED`/`AI_RUN_FAILED` 成对落库，无 Claim 或 Token 用量记录。未自动重试、未测试 DeepSeek；账号资格未通过，桌面 `live_enabled=False` 不变。实际厂商账单未核对 / The owner then explicitly approved one request of the previewed five fictional lines to OpenAI `gpt-6-luna`. Preflight passed but the provider returned HTTP 401. The Run persisted as `FAILED` with paired `AI_RUN_STARTED`/`AI_RUN_FAILED` events, no claims, and no token-usage record. There was no automatic retry or DeepSeek request; account qualification did not pass, desktop `live_enabled=False` remains, and actual provider billing was not checked |
| V2.4 DeepSeek 合成试验（2026-10-16） / DeepSeek synthetic trial | 用户另行批准向 DeepSeek 官方端点的 `deepseek-flash` 发送相同五行虚构内容一次。输入指纹、范围与 US$0.0056073 估算预检通过；Provider 返回 HTTP 402。Run 为 `FAILED`，开始/失败 Event 成对落库，无 Claim 或 Token 用量。未自动重试，官方错误表将 402 解释为余额不足；账号资格仍未通过，桌面 `live_enabled=False` 不变，实际账单未核对 / The owner separately approved one request of the same five fictional lines to the official DeepSeek `deepseek-flash` endpoint. Fingerprint, scope, and US$0.0056073 estimate passed preflight; the provider returned HTTP 402. The Run persisted as `FAILED` with paired start/failure events, no claims or token usage. There was no automatic retry. DeepSeek documents 402 as insufficient balance; account qualification remains incomplete, desktop `live_enabled=False` is unchanged, and actual billing was not checked |
| V2.4 DeepSeek 单次重试（2026-10-16） / DeepSeek one-shot retry | 用户明确要求重新发起；同一五行虚构输入、模型、指纹及费用预检通过后只发出一次请求。Run `ebddf9b5-e108-482f-bdc2-0b9086cdc223` 为 `SUCCEEDED`，记录 742 输入/841 输出 Token、3 条有 Element 引用的摘要与成对成功 Event。结果展示脚本随后出现类型错误，但只读复核确认落库成功，未因此重试。合成项目估算账本累计约 US$0.013484，实际厂商账单未核对。仅证明本次合成端到端连通与结构化结果；账号条款/留存、打包行为及生产外发尚未签收，桌面 `live_enabled=False` 不变 / The owner explicitly requested a retry; the same five fictional lines, model, fingerprint, and estimate passed preflight and exactly one request was sent. Run `ebddf9b5-e108-482f-bdc2-0b9086cdc223` is `SUCCEEDED` with 742 input/841 output tokens, three element-cited summaries, and paired success events. A later display-script type error did not affect persistence; read-only verification passed, and no further request was sent. The synthetic project's estimated-spend ledger totals approximately US$0.013484; actual provider billing was not checked. This establishes only synthetic end-to-end connectivity and structured output, not terms/retention, packaged behavior, or production-egress acceptance. Desktop `live_enabled=False` remains |
| V2.4 本机合成 DeepSeek 开关（2026-10-16） / Local synthetic DeepSeek gate | 用户选择 [ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md) 方案 A：OpenAI 401 不作为当前收尾项，真实 API 异常与桌面闭环暂缓；仅源码桌面允许已验证合成项目的固定 DeepSeek 摘要计划逐次确认外发。后端绑定项目 ID、数据库路径与 Fingerprint，其他项目和 OpenAI 拒绝，打包版保持关闭。合成服务测试 16 通过；源码组合只读预检确认 DeepSeek 计划可执行、OpenAI 不可执行。**没有因本次代码变更再次发出真实 API 请求**，源码桌面人工点击验收及打包版正式发布均未签收；真实业务资料外发仍禁止 / The owner selected option A in ADR-032: OpenAI 401 is not a current closure item; live failure/desktop-loop acceptance is deferred. Only the source desktop may send the verified synthetic Project's fixed DeepSeek summary after per-request confirmation. Backend scope binds Project ID, database path, and fingerprint; other Projects and OpenAI are denied, and packaged egress remains off. Sixteen synthetic service tests passed; a read-only source-composition check confirmed the DeepSeek plan allowed and OpenAI denied. **No additional live API request was made for this code change**. Manual source-desktop click-through and packaged release remain unsigned; real business-data egress is still prohibited |
| 旧项目兼容 / Older project compatibility | 用户于 2026-10-12 明确决定：后续代码升级默认不考虑旧项目，只有特意提醒才设计迁移；不得自动改写旧库 / Owner decided on 2026-10-12: future code changes need not support older projects unless explicitly requested; old databases must not be rewritten automatically |
| V2.2 真实资料与异机验收 / Real-data and cross-machine checks | 未签收；不得宣称已通过 / Not accepted; do not claim completion |
| 本次规则整理 | 用户授权修改规则与必要拆分；不扩大产品实现范围 / Owner authorized rule revision and splitting, without extending product implementation scope |

V2.3 已授权范围包括 TXT、CSV、EML、XLSX 的显式 Revision 提取、子进程边界、
同库 FTS5、索引重建、定位搜索和最小 UI。PDF、DOCX、PPTX 仍只处于候选评估，
运行时解析依赖须单独批准。V2.4 最初选定 OpenAI API 和 DeepSeek API；当前仅
DeepSeek 合成试运行符合 [ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md)
的受限入口。真实业务资料外发、打包发布与平台适配不由本次批准自动放行。

The V2.3 authorization covered explicit TXT, CSV, EML, and XLSX Revision extraction, a
child-process boundary, in-project FTS5, index rebuilding, located search, and minimum UI.
PDF, DOCX, and PPTX remain evaluation candidates; parser runtime dependencies need separate
approval. OpenAI API and DeepSeek API were the initial V2.4 candidates; only DeepSeek's
synthetic trial now has the bounded entry in
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md).
Real business-data transmission, packaged release, and platform adapters remain unauthorized.

## 2. V1 保留基线 / Retained V1 baseline

V1 保留以下闭环：

V1 retains this loop:

```text
Project -> Import -> Immutable Snapshot -> Structure Discovery -> Editable Workspace
  -> Lazy Materialization -> Controlled Open -> External Edit Refresh
  -> Move / Add / Soft Delete / Restore -> SQLite Persistence -> Structural Search
  -> Current + Previous Working Version -> File / ZIP / Folder Export
```

新项目使用 `<selected-parent>/<valid-project-name>/project.sqlite`，UUID 为内部身份。
不得因目录名字更友好而自动迁移既有项目目录。

New projects use `<selected-parent>/<valid-project-name>/project.sqlite`, with UUID identity.
Friendlier directory names do not authorize automatic relocation of existing projects.

永久移除仅限经完整影响预览和确认的顶层 `ImportSessionItem` 撤销；不得影响同批
Sibling 或外部输入。任意节点 Hard Delete、透明 Archive Repack 和 MSG/EML 回写
不属于该基线。完整 Lineage、Manifest 和审计 UI 不作为扩大 V1 的理由。

Permanent removal is limited to a confirmed top-level `ImportSessionItem` undo after complete
impact preview. It cannot affect sibling imports or external inputs. Arbitrary-node hard deletion,
transparent archive repacking, and MSG/EML write-back are excluded. Full lineage, manifests,
and audit UI do not justify enlarging V1.

## 3. 版本保护与兼容 / Version protection and compatibility

V1 的“当前 + 上一版本”只约束 Working Artifact。V2 Context Revision 按 ADR-025
保留：被引用或人工保护的 Revision 继续保留，且不得自动清理。两者不能混用。

V1's current-plus-previous limit applies only to Working Artifacts. V2 Context Revisions
follow ADR-025: referenced or manually protected revisions remain retained and cleanup is
never automatic. These policies are distinct.

旧 Evidence-era、V1 Workbench 和任何早于当前 Schema 的项目，后续开发均无默认
兼容或迁移义务。现有历史迁移能力不需主动删除，但不得因它们存在而推定新版本
必须兼容旧项目。旧库可明确拒绝；不得双写、长期混合模型读取或静默重建丢弃事实。
如负责人日后明确指定旧版本迁移，再按 ADR-025 的备份、安全和验证边界实施。

Older Evidence-era, V1 Workbench, and any pre-current-schema project have no default
compatibility or migration obligation in future development. Existing historical migration
code need not be removed, but does not imply that new releases must support old projects.
Reject unsupported databases explicitly; never dual-write, indefinitely mix models, or
silently reset facts. If the owner later requests migration for specified versions, apply
ADR-025 backup, safety, and validation boundaries.

## 4. 当前不扩展的能力 / Current exclusions

未经新范围授权，不增加 OCR、AI Chat、全 Workspace 内容自动索引、知识图谱、
云同步、多用户协作、复杂 RBAC、真实平台 Adapter、可写 Agent、Automation Engine、
MCP Server、独立 Vector DB 或完整 RAG 平台。

Without new scope authorization, do not add OCR, AI chat, automatic whole-Workspace content
indexing, knowledge graphs, cloud sync, multi-user collaboration, complex RBAC, real platform
adapters, write-capable Agents, an Automation engine, an MCP server, a standalone vector database,
or a complete RAG platform.

## 5. 证据与更新 / Evidence and updates

当前状态依据[规划索引](../PIG-planning-index.md)、[工作区交互复测](../application/PIG-V2.4-workspace-interaction-followup.md)、[V2.1.5 验收](../application/PIG-V2.1.5-acceptance.md)、
[V2.2 验收](../application/PIG-V2.2-implementation-acceptance.md)、[V2.3 决策门](../application/PIG-V2.3-decision-gate.md)、
[V2.3 实施验收](../application/PIG-V2.3-implementation-acceptance.md)与
[V2.4 决策门](../application/PIG-V2.4-decision-gate.md)与
[V2.4 实施验收](../application/PIG-V2.4-implementation-acceptance.md)。
具体决定见 [ADR-030](../decisions/ADR-030-default-no-legacy-project-compatibility.md)、[ADR-024](../decisions/ADR-024-v2-project-context-foundation.md)、
[ADR-025](../decisions/ADR-025-v2.1-context-foundation-decisions.md)、
[ADR-026](../decisions/ADR-026-v2.2-context-pack.md)、[ADR-027](../decisions/ADR-027-v2.3-canonical-content-search.md)
及[ADR-028](../decisions/ADR-028-v2.4-project-experience-controlled-ai.md)、
[ADR-029](../decisions/ADR-029-v2.4-provider-and-budget-gate.md)、
[ADR-031](../decisions/ADR-031-expanded-container-view-export.md)与
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md)。此前简化桌面 UI 的人工
验收由用户明确确认；V2.4 收尾清单第 1、2 项亦由用户确认，真实 Provider、打包及异机
验收仍未签收。

Status is grounded in the [planning index](../PIG-planning-index.md),
[Workspace interaction retest](../application/PIG-V2.4-workspace-interaction-followup.md),
[V2.1.5 acceptance](../application/PIG-V2.1.5-acceptance.md),
[V2.2 acceptance](../application/PIG-V2.2-implementation-acceptance.md), and
[V2.3 gate](../application/PIG-V2.3-decision-gate.md), and
[V2.3 implementation/acceptance](../application/PIG-V2.3-implementation-acceptance.md), and
[V2.4 gate](../application/PIG-V2.4-decision-gate.md), and
[V2.4 implementation/acceptance](../application/PIG-V2.4-implementation-acceptance.md).
Concrete decisions are in
[ADR-030](../decisions/ADR-030-default-no-legacy-project-compatibility.md),
[ADR-024](../decisions/ADR-024-v2-project-context-foundation.md),
[ADR-025](../decisions/ADR-025-v2.1-context-foundation-decisions.md), and
[ADR-026](../decisions/ADR-026-v2.2-context-pack.md), and
[ADR-027](../decisions/ADR-027-v2.3-canonical-content-search.md), and
[ADR-028](../decisions/ADR-028-v2.4-project-experience-controlled-ai.md), and
[ADR-029](../decisions/ADR-029-v2.4-provider-and-budget-gate.md).
[ADR-031](../decisions/ADR-031-expanded-container-view-export.md) records the later Container
View export authorization.
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md) narrows the current
source-desktop synthetic DeepSeek outbound scope.
The owner accepted the earlier simplified desktop UI, V2.4 decisions, and closure items 1 and 2;
live-provider, packaged, and cross-machine checks remain unsigned.

新授权到达时，应更新本文件的日期、允许动作、停止线和证据；规划索引只维护读取路径。
不反复修改长期主规则，不批量改写历史 ADR 的原始授权记录。

When authorization changes, update this file's date, allowed actions, stop line, and evidence.
The planning index maintains reading paths. Do not repeatedly edit long-term rules or rewrite
historical ADR authorization records.
