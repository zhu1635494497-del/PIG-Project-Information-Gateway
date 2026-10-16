# V2.4.1 人工经验与交接契约 / Human Experience and Handoff Contract

- 阶段：V2.4.1 Experience Contract / Stage: V2.4.1 Experience Contract
- 日期：2026-10-11 / Date: 2026-10-11
- 决策：[ADR-028](../decisions/ADR-028-v2.4-project-experience-controlled-ai.md) D133-A、D141-A、D142-A / Decisions: [ADR-028](../decisions/ADR-028-v2.4-project-experience-controlled-ai.md) D133-A, D141-A, D142-A
- 当前实施与验收状态以 [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md) 为准 / Current implementation and acceptance follow [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md)

## 1. 最小用户闭环 / Minimum user loop

用户在核心文件中选择已固定的版本，写下一条“判断、决定或经验”，说明为何这样做，
并显式关联一份或多份同项目的固定 Revision。记录的作者与内容可重开；更正创建新
版本而不覆写旧文；确认是人的 Action，不由 Event 或 AI 自动推断。随后用户可查看
只读交接计划：哪些记录、证据文件和说明将进入版本化 Context Bundle。

A user selects fixed core-file Revisions, authors a judgment, decision, or lesson, explains the
rationale, and explicitly links one or more same-project Revisions. Authorship and text reopen;
correction creates a new version rather than overwriting old text. Confirmation is a human
Action, never inferred from an Event or AI. A read-only handoff plan shows exactly which records,
evidence files, and guidance would enter a versioned Context Bundle.

```text
Observed PIG Event ───────────────────────────────┐
                                                   │ optional observed-action link
Human Experience Record -> immutable text version ├──> fixed Context Revision(s)
                                                   │
AI Analysis draft (later) ─ separate ownership ───┘
```

操作 Event 回答“PIG 观察到什么”，人工记录回答“人为何这样判断”，AI 草稿回答“模型建议
什么”。用户在外部 Host Application 的中间保存与没有写下的思考不在可观察范围内。

An Event answers what PIG observed, a human record explains the author's rationale, and an AI
draft states model output. Intermediate host-application saves and unrecorded thoughts are not
observable facts.

## 2. 领域身份与状态 / Domain identity and state

| 对象 / Object | 最小字段 / Minimum fields | 所有权与约束 / Ownership and constraints |
| --- | --- | --- |
| `ProjectExperienceRecord` | `id`, `project_id`, `kind`, `status`, `current_version`, `created_at`, `updated_at` | Project 拥有稳定身份；`kind` 为 `JUDGMENT`、`DECISION`、`LESSON`；`status` 为 `DRAFT`、`CONFIRMED`、`SUPERSEDED`。Project owns stable identity; kinds and states are explicit. |
| `ExperienceVersion` | `record_id`, `version`, `title`, `body`, `author`, `recorded_at` | 文本版本不可变，`version` 从 1 连续递增；每次更正产生新行并移动 current pointer。Text versions are immutable and numbered from 1. |
| `ExperienceStateChange` | `record_id`, `version`, `from_status`, `to_status`, `actor`, `occurred_at` | 状态变更的不可变历史；确认绑定具体文本版本。Immutable state history; confirmation binds to an exact text version. |
| `ExperienceRevisionLink` | `record_id`, `version`, `context_item_id`, `context_revision_id`, `role` | 每个版本显式引用同 Project、该 Item 所属的 `READY` Revision；`role` 为 `SUPPORTS`、`CONTRADICTS`、`BACKGROUND`。Links are explicit and same-project. |
| `ExperienceEventLink` | `record_id`, `version`, `event_id` | 可选关联同 Project 的既有 Event；链接不把 Event 的动作解释成理由。Optional same-project observed-action link never implies rationale. |

人工状态从 `DRAFT` 可进入 `CONFIRMED`；`CONFIRMED` 可由人标为 `SUPERSEDED`，
或在更正时创建新文本版本并回到 `DRAFT`。旧确认仍绑定其旧版本并可重开，新版本须
由人再次确认才代表新结论。`SUPERSEDED` 不再编辑，但可重开和引用，不作为当前已
确认结论。AI 草稿不得执行这些迁移。每次写入使用
预期 Record 版本/Project `context_revision` 检查并发，状态、版本、关系与结构化 Event
在同一数据库事务提交；具体 Schema/Action 属于 V2.4.2。

Human Actions move `DRAFT` to `CONFIRMED`. A confirmed record can become `SUPERSEDED`, or
correction can create a new text version and return the record to `DRAFT`. The old confirmation
remains bound to its old version and can be reopened; the new version needs fresh confirmation.
Superseded records cannot be edited but remain reopenable and citable.
AI drafts cannot transition them. Writes check expected record/project versions; state, version,
links, and safe structured Event commit together. Schema and Actions belong to V2.4.2.

已有 Item `Annotation` 继续只负责文件阅读说明；它不自动变成项目级经验记录。已有
Context Revision 字节、Source、Workspace 和 Original 均不因关联而复制或修改。

Existing Item Annotations remain reading guidance and do not silently become project-level
experience. Linking never copies or modifies Context Revision bytes, Source, Workspace, or Original.

## 3. 只读契约与 Bundle / Read-only contracts and Bundle

候选 Application Queries 为 `list_project_experience(project_id, status, cursor, limit)`、
`get_experience_record(project_id, record_id)`（含版本与关系）和
`get_context_bundle_plan(project_id, selected_item_ids, selected_record_ids)`。这些是
进程内类型化能力，不是公开 HTTP/MCP endpoint。查询不得写库、物化文件或推断事实。

Candidate Application Queries list records with bounded paging, get one record with versions
and links, and prepare a Bundle plan for explicit Item/Record selections. They are typed
in-process capabilities, not public HTTP/MCP endpoints. Queries do not write, materialize, or
infer facts.

现有 Context Pack `schema_version=1.0` 保持原语义。扩展版 Bundle 拟使用 `2.0`，
保留旧字段并新增 `experience_records` 与 `observed_events`，其中每条经验记录包含当前
选定文本版本、作者、状态及显式 Revision/Event 链接；被引用的 Event 只输出安全类型、
时间、操作者和必要 ID，不输出正文或敏感 Metadata。AI 草稿仅在未来被用户选中时
作为独立区段加入，不得混入 `experience_records`。消费者按 `schema_version` 解析，
未知主版本拒绝，
不靠文件名猜 Schema。此处是契约，不在 V2.4.1 改 Pack 的运行逻辑。

Existing Context Pack `schema_version=1.0` retains its meaning. The extended Bundle proposes
`2.0`, preserving old fields and adding `experience_records` and `observed_events`. A selected
record includes its text version, author, status, and explicit links. Referenced Events expose
only safe type, time, actor, and necessary IDs, not body text or sensitive metadata. Future
user-selected AI drafts use a separate section, never `experience_records`. Consumers parse
`schema_version` and reject unknown major
versions rather than guessing from filenames. V2.4.1 does not alter Pack runtime behavior.

`2.0` 的每条 `experience_records[]` 最小字段固定为：`id`、`version`（正整数）、
`kind`、`status`、`title`、`body`、`author`、`recorded_at`（UTC ISO 8601）、
`revision_links[]`（`context_item_id`、`context_revision_id`、`role`）和 `event_ids[]`。
`observed_events[]` 最小字段为 `id`、`type`、`occurred_at`、`actor`，仅包含被选定
记录引用的安全 Event 快照。已有 `project`、`sections`、`entries` 等 `1.0` 字段保持
语义。`revision_links` 指向
同一 Bundle `entries` 的固定 Revision；`event_ids` 指向同包 `observed_events`。
Event 链接只表示 PIG 观察到的操作，消费者不得由其生成判断正文。当前导出快照只含
选中的文本版本，不把全部更正历史或未选择
资料悄悄加入包。

Each `2.0` `experience_records[]` entry minimally includes `id`, positive `version`, `kind`,
`status`, `title`, `body`, `author`, UTC ISO-8601 `recorded_at`, `revision_links[]` with
`context_item_id`/`context_revision_id`/`role`, and `event_ids[]`. Each `observed_events[]`
entry minimally has `id`, `type`, `occurred_at`, and `actor`, and only referenced safe Events
are included. Existing `1.0` project, sections, and entries retain their meaning. Revision
links resolve to fixed Revisions in the
same Bundle entries; event IDs resolve to its `observed_events` section. Event links represent
observed PIG actions only; consumers cannot infer record text from them. An export snapshots
the selected text version, not all edit history or
unselected material.

若选定记录关联的 Revision 未进入拟导出的文件 Entry，预检必须列出缺失证据并阻止
“可核对交接”发布；不能静默附加文件，也不能只输出看似有效的悬空引用。用户调整
选定范围后重做计划与外部目标预检。Bundle 默认不带整个 Workspace、未选正文、
Secret 或完整模型 Payload。实际 Pack 发布遵守 V2.2 的目标、安全、确认与恢复策略。

If a selected record refers to a Revision absent from planned file entries, preflight reports
missing evidence and blocks a supposedly verifiable handoff. It neither silently adds files nor
emits apparently valid dangling references. The user changes selection and reruns plan and
destination preflight. The Bundle excludes the entire Workspace, unselected text, secrets, and
full model payloads by default. Publication follows V2.2 target, safety, consent, and recovery
policies.

## 4. 边界验证与威胁 / Boundary checks and threats

- **归属与版本**：拒绝跨 Project、错误 Item 所属、非 `READY` Revision、重复关系、
  已过期编辑条件和缺失证据。Reject cross-project, wrong-Item, non-`READY`, duplicate,
  stale-write, and missing-evidence links.
- **输入是不可信文本**：标题、正文、Event Metadata 和导出内容均视为数据；限制长度，
  转义 Markdown/HTML 展示，绝不把其中“请上传资料”等文字当成 PIG 指令。Treat text as
  untrusted data, bound length, escape presentation, and never execute embedded instructions.
- **隐私**：业务 Event 只保存安全类型、ID、状态与计数，不写人工正文、客户资料、
  Secret、完整物理路径或模型输入。正文在 Project SQLite/备份中，需要项目级保护。
  Events omit sensitive bodies; Project SQLite and backups contain authored text and need
  project-level protection.
- **保留与清理**：被经验记录引用的 Context Revision 不自动清理；记录更正与被取代
  不抹除历史。未来清理需预览引用影响并由受控 Action 执行。Referenced Revisions are
  retained; corrections/supersession do not erase history. Cleanup previews impact.
- **性能**：列表分页，详情按需读取；Bundle 计划与导出后台处理，不把正文扫描或
  Pack 生成放进 UI 线程。Page lists, load details on demand, and keep plans/exports off
  the UI thread.

## 5. 合成案例与验收 / Synthetic case and acceptance

“新品发布”项目中，用户把 `预算.xlsx` 的固定 Revision `R1` 和 `报价.csv` 的 `R2`
加入核心文件。系统 Event `E1` 只能证明 `R2` 被固定。用户创建判断 `J1`：
“选择供应商 B；虽非最低价，但可在发布日期前交付”，以 `R1` 和 `R2` 为支持依据，
并可选地关联 `E1`。更正日期后产生 `J1` 的第 2 版；第 1 版仍可重开。只选择
`R1` 导出时，Bundle 预检显示 `R2` 缺失并阻止可核对交接；补选 `R2` 后，合成
消费者能根据 ID、版本和关系重建判断及两份依据。Event 自身不生成判断内容。

In a synthetic product-launch project, fixed Revisions `R1` (budget) and `R2` (quote) support
judgment `J1`: supplier B can meet the launch date despite not being cheapest. Event `E1`
proves only that `R2` was fixed and is an optional link. Correcting the date creates version 2
of `J1` while version 1 remains reopenable. Exporting only `R1` reports missing `R2` and blocks
verifiable handoff; adding `R2` lets a synthetic consumer reconstruct judgment and evidence.
The Event never invents the rationale.

V2.4.1 仅固定上述契约并验证合成关系与拒绝案例；不创建 Migration、Repository、
UI、真实 Bundle 文件或模型请求。V2.4.2 才实现人工写入、重开和导出闭环。

V2.4.1 fixes and checks these contracts and synthetic rejection cases only. It creates no
migration, repository, UI, real Bundle file, or model request. V2.4.2 implements authoring,
reopening, and export.

## 6. 本次验证 / Verification in this run

领域契约实现于 `src/pig/domain/experience_policy.py`，以纯确定性校验限制文本与关系、
确认状态迁移和 Bundle 缺失证据；`src/pig/application/experience_contracts.py` 提供
内存中的 `1.0 -> 2.0` Manifest 扩展和安全 Event 快照契约。它们不读取文件、不操作
数据库或网络。合成用例覆盖
两份固定依据、一条可选 Event、错误 Project、非 READY/重复 Revision、Event 不能代替
判断理由、已确认更正回到草稿、导出缺失依据、旧 Manifest 不变和合成消费者读取。
`tests/domain` 加新 Bundle 契约用例本次 **51 passed**；
文档相对链接和 `git diff --check` 通过。源码桌面、打包桌面及人工业务验收未执行，
且不属于此纯契约阶段的完成证据。

The pure policy in `src/pig/domain/experience_policy.py` bounds text and links, validates
human state transitions, and identifies missing Bundle evidence. The in-memory `1.0 -> 2.0`
manifest extension and safe Event snapshot contract are in
`src/pig/application/experience_contracts.py`; neither module accesses the filesystem,
database, or network. Synthetic cases cover two fixed sources, an optional Event, wrong project,
non-READY/duplicate Revisions, Event-versus-rationale separation, correction after confirmation,
missing export evidence, unchanged legacy manifests, and a synthetic consumer. `tests/domain`
plus the new Bundle-contract cases reported **51 passed**; relative links and
`git diff --check` passed. Source desktop, packaged desktop, and human business acceptance were
not run and are not claimed as evidence for this pure-contract stage.
