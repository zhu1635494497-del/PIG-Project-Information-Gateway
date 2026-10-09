# V2.2 Context Pack 实施与验收 / Context Pack Implementation and Acceptance

- 状态：源码功能、合成自动验收与合成数据桌面人工验收已完成；真实资料与异机人工验收未执行 / Status: Source feature, synthetic automated acceptance, and synthetic-data desktop manual acceptance complete; real-data and cross-machine manual acceptance not performed
- 日期：2026-10-09 / Date: 2026-10-09
- 决策：`ADR-026` D120-A 至 D126-A / Decisions: `ADR-026` D120-A through D126-A

## 用户闭环 / User loop

在 Project Context 页点击“导出 Context Pack”，选择核心 Item、逐 Item 的 READY
Revision、普通目录或 ZIP，以及 Project 受管目录外尚不存在的目标。预检返回文件数、
估计大小、可用空间和过期警告；用户确认后后台流式生成。完成后 UI 显示交付位置，
“交付历史”可查看状态。取消发生在安全检查点；已有目标不会被覆盖或自动改名。

In Project Context, the user chooses core Items, a READY Revision per Item,
directory or ZIP, and a non-existing destination outside managed Project
storage. Preflight returns entry count, estimated bytes, available space, and
freshness warnings. After confirmation, a background action streams the pack.
The UI shows the destination and a delivery-history view. Cancellation occurs
at safe checkpoints; existing targets are never overwritten or silently
renamed.

## 后端数据流 / Backend data flow

`get_context_pack_plan` → `preflight_context_pack_export` →
`execute_context_pack_export` → `get_context_pack_exports`。预检固定当前
`context_revision`、所选 Revision 指纹和一次性 Token，并验证受管对象的实际大小/
SHA-256、外部目标及容量。执行用状态 CAS 消耗 Token，再验证同一计划和字节；
`WORKSPACE_UPDATED` 等 Freshness 警告需再次确认，但缺失或 Hash 错误一律阻断，
绝不回退到 Working/Original。

The typed Actions are `get_context_pack_plan` →
`preflight_context_pack_export` → `execute_context_pack_export` →
`get_context_pack_exports`. Preflight freezes the Context revision, selected
Revision fingerprint, and a one-use token, then verifies actual managed-object
size/hash, destination, and capacity. Execution consumes the token with a
compare-and-set status transition and rechecks plan and bytes. Freshness
warnings require confirmation; missing or mismatched objects always block,
with no Working/Original fallback.

Infrastructure 在目标同卷建立生成 ID 命名的 staging。目录和 ZIP 共用 Manifest/
README/Entry 语义，`files/<item-id>/<safe-name>` 中每 Item 仅一份字节。复制过程
逐块校验 SHA-256，发布前再次确认目标未出现，再用不覆盖的原子移动发布。成功后在
同一 SQLite 事务写入 `SUCCEEDED`、Entry、Section/Placement 快照和完成 Event；
失败或取消只保留失败历史，不建立成功 Revision 保护引用。

Infrastructure stages on the destination volume under a generated ID.
Directory and ZIP share Manifest/README/Entry semantics and store each Item's
bytes once under `files/<item-id>/<safe-name>`. Streaming copy verifies SHA-256
and publication uses an atomic no-replace move. After publication, one SQLite
transaction records `SUCCEEDED`, Entry, Section/Placement snapshots, and the
completion Event. Failure or cancellation retains failure history but creates
no successful Revision-protection reference.

## 包格式与来源 / Pack format and origin

包内 `README.md` 是中英双语固定模板，来自 Project 名称、Section 描述、Item 用途
和人工 Annotation；用户原文不自动翻译，不生成业务结论。`manifest.json` 记录版本、
Project ID、固定 Context Revision ID、Section 与 Placement、文件相对路径、
字节数和 SHA-256。包不包含 Source/Working 绝对物理路径、模型输出、AI 摘要或平台
专有字段。接收方可独立用 Manifest 校验每个文件。

The `README.md` uses a fixed bilingual template from Project name, Section
description, Item purpose, and human Annotation. User text is not translated;
no business conclusion is invented. `manifest.json` records schema version,
Project ID, fixed Context Revision IDs, Sections and Placements, relative file
paths, sizes, and SHA-256 hashes. The pack excludes absolute Source/Working
paths, model output, AI summaries, and vendor-specific fields. A recipient can
verify every file independently from the manifest.

## 状态、事件与恢复 / State, Events, and recovery

状态流为 `PENDING → PREFLIGHTED → RUNNING → SUCCEEDED`，也可进入 `FAILED` 或
`CANCELLED_AT_SAFE_POINT`。追加式结构化事件记录请求、预检、开始、成功、失败、
取消；事件仅含 Export ID、计数、Hash 和安全错误码，不记录文件正文或外部绝对路径。
未完成的 `RUNNING` 记录不会假装成功；在确认无任务运行后，用户可从交付历史显式
标记为中断失败。若外部目标已出现，PIG 保留它并提示人工检查，不静默覆盖或删除。

The state flow is `PENDING → PREFLIGHTED → RUNNING → SUCCEEDED`, with `FAILED`
or `CANCELLED_AT_SAFE_POINT` terminal outcomes. Append-only structured Events
record request, preflight, start, completion, failure, and cancellation;
they carry Export ID, counts, hashes, and safe error codes rather than document
body or absolute destination paths. An interrupted `RUNNING` record never
pretends to have succeeded. After confirming no task is live, the user may
explicitly mark it failed from delivery history. If an external destination
already exists, it is retained for manual review, never silently overwritten
or removed.

## 自动测试与人工验收 / Automated and manual acceptance

合成测试覆盖目录/ZIP 内容、Manifest Hash、空 Section、固定历史 Revision、过期确认、
计划失效、一次性 Token、目标冲突、Project 内目标拒绝、对象篡改、取消、同名文件、
12 MiB 文件进度、可取消的逐块预检 Hash、重启读取历史、Event、独立接收目录解包
校验和离屏桌面流程。
全量回归为 **223 passed、95 skipped、1 warning**；在后续加固后，最新 V2.2 定向
测试 **19 passed**，增量迁移与取消清理检查 **6 passed**。真实资料和异机解包尚未
运行，不得记为通过。
2026-10-09，用户确认合成数据源码桌面人工测试通过；此确认不等于真实资料或异机验收。

Synthetic tests cover directory/ZIP content, manifest hashes, empty Sections,
fixed historical Revisions, freshness confirmation, stale plans, one-use
tokens, destination conflicts, managed-target rejection, tampering,
cancellation, duplicate names, 12 MiB progress, cancellable chunked preflight
hashing, reopen history, Events, unpacking into an independent recipient
directory with manifest hash checks, and offscreen desktop flow. Full regression
reported **223 passed, 95 skipped, 1 warning**. After further hardening, the
latest V2.2 targeted run reported **19 passed** and incremental-migration plus
cancellation-cleanup checks reported **6 passed**. Real-data and cross-machine
unpacking have not been run and must not be marked accepted.
On 2026-10-09, the user confirmed that the synthetic-data source-desktop
manual test passed. This does not constitute real-data or cross-machine
acceptance.

人工步骤：在源码桌面端打开测试 Project → 准备至少两个核心文件及人工说明 → 分别
导出目录包和 ZIP 到不同空目标 → 在另一台机器解包 ZIP → 对照两个 `manifest.json`
逐项核查所选 Revision、Section/说明、相对路径及 SHA-256 → 修改 Workspace 后尝试
旧 Revision 并确认警告 → 测试已有目标拒绝、取消与重启后的交付历史。全过程不应改动
Original、Working 或 Context Object 字节。

Manual steps: open a test Project in the source desktop; prepare at least two
core files and human guidance; export directory and ZIP to distinct empty
destinations; unpack ZIP on another machine; compare each manifest's selected
Revisions, Sections/guidance, relative paths, and SHA-256 hashes; change a
Workspace file and explicitly export an older Revision after warning; test
existing-target rejection, cancellation, and delivery history after restart.
Original, Working, and Context Object bytes must remain unchanged throughout.

## 尚未闭环 / Remaining boundaries

外部文件系统原子发布与 SQLite 提交不能形成跨介质事务。正常数据库失败时系统仅在
确认为本次生成且 Hash 未变时尝试移除外部包；进程崩溃可能留下未登记的外部包，
恢复时必须人工核对。当前没有签名、加密、收件人权限、平台发送、内容解析或 AI；
这些不是 V2.2 的隐含功能。

Filesystem publication and SQLite commit cannot form one cross-medium
transaction. On an ordinary database failure, PIG removes the external pack
only if it is confirmed as this export's unchanged output. A process crash may
leave an unregistered external pack requiring manual review. Signing,
encryption, recipient permissions, platform sending, content extraction, and
AI are not implicit V2.2 features.
