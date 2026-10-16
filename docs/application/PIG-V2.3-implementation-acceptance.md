# V2.3 内容提取与搜索实施、验收 / V2.3 Content Extraction, Search, and Acceptance

- 日期：2026-10-10 / Date: 2026-10-10
- 决策：[ADR-027](../decisions/ADR-027-v2.3-canonical-content-search.md) D127-A–D132-A / Decisions: [ADR-027](../decisions/ADR-027-v2.3-canonical-content-search.md) D127-A–D132-A
- 状态与签收以 [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md) 为准；本文保留实施与各次验证证据 / Phase and acceptance follow [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md); this document preserves implementation and individual-check evidence

## 用户工作流 / User workflow

1. 在 Workspace 中将关键 TXT、CSV、XLSX 或 EML 加入 Project Context。EML 作为
   Container View，从右键菜单选择“加入 Project Context（EML 原邮件）”。
2. 在 Context 选择一个 `READY` Revision，点击“提取所选 Revision”。确认后后台只
   读取其不可变 Context Object，生成 Canonical Content 和同库索引；正文不会外发。
3. 在 Context 下方输入关键词。结果显示文件、固定 Revision、命中片段与行/CSV 行/
   邮件字段/Sheet 单元格。双击打开以原名命名的只读副本，由用户按 Locator 核对原文。
4. 数据库索引丢失时，点击“重建索引”。进程中断留下 `RUNNING` 时，确认无其他任务
   在运行后点击“恢复中断提取”，然后重新提取。Workspace 后续修改不会替换旧结果。

1. Promote a key TXT, CSV, XLSX, or EML file into Project Context. EML is a Container View;
   its context-menu action captures the original email bytes.
2. Select a `READY` Revision and explicitly extract it. Background work reads only its immutable
   Context Object, storing canonical elements and an in-project index without transmitting text.
3. Search in the Context panel. Results show file, fixed Revision, snippet, and line/CSV-row/
   email-field/sheet-cell locator. Double-click opens a read-only, original-name preview for
   manual verification at the shown locator.
4. Rebuild a missing index explicitly. If a crash leaves `RUNNING`, confirm no other worker is
   active, mark the run interrupted, and retry. Later Workspace edits do not replace old results.

## 对象、数据流与状态 / Objects, data flow, and states

`ContextRevision -> ContextContentObject -> ExtractionRun -> ContentDocument -> ContentElement`
是权威链路；`content_fts` 是从 Element 派生的 FTS5 索引。每个 Element 保存有序序号、
正文和类型化 Locator。Run 保存输入 SHA-256、Extractor 版本、配置 Hash、操作者、
关联 ID、开始/结束时间、计数、状态和安全错误码。成功同键复用；失败和取消可重试。
状态为 `RUNNING -> SUCCEEDED/PARTIAL/UNSUPPORTED/FAILED/CANCELLED_AT_SAFE_POINT`。
关键变化和 Event 在同一事务中提交；Event 不含正文、客户资料或预览路径。

The authoritative chain is `ContextRevision -> ContextContentObject -> ExtractionRun ->
ContentDocument -> ContentElement`; `content_fts` is a derived FTS5 index. Ordered elements
carry text and typed locators. Runs persist input hash, extractor/configuration version, actor,
correlation ID, timestamps, count, state, and safe error code. Equivalent successful runs are
reused; failed/cancelled runs can be retried. States are `RUNNING -> SUCCEEDED/PARTIAL/
UNSUPPORTED/FAILED/CANCELLED_AT_SAFE_POINT`. Each terminal state commits with its business Event;
Events exclude document text, customer data, and preview paths.

## 安全、升级与恢复 / Safety, upgrade, and recovery

解析使用一次性子进程、实际输入/输出/元素/时间预算，XLSX 限制 ZIP 项数和实际读取的
XML Part 大小，拒绝 XML Entity；EML 不提取附件正文。父进程校验 Context Object，
子进程读入后复验 SHA-256。当前子进程不是 Windows Job Object 沙箱；内存/CPU 峰值和
打包运行须单独测量。仅清理本次操作生成的 `.staging/content/run-*` 临时目录。

Schema `0014_content_search` 通过已有的受控升级入口安装：用户确认、一致性备份、
迁移和事实校验。降级若存在 Canonical Content 或 V2.3 Event 会拒绝，以免删除事实。
`project.sqlite` 及升级后的备份包含可检索正文；不自动同步或上传。固定版本预览位于
`context/previews/<revision-id>/<original-safe-name>`，只读、可再生；若被 Host 修改，
下一次打开明确报错而不覆盖它。未实施自动清理预览，也不宣称安全擦除。

Extraction uses a one-shot subprocess with actual input/output/element/time limits. XLSX bounds
ZIP entry counts and read XML parts and rejects entity declarations; EML attachments are not indexed.
The parent verifies the Context Object and the worker checks the hash after reading. This is not a
Windows Job Object sandbox; packaged peak memory/CPU still need measurement. Only operation-owned
`.staging/content/run-*` temporary directories are removed.

Schema `0014_content_search` follows the existing confirmed upgrade: consistent backup, migration,
and fact validation. Downgrade refuses to discard canonical content or V2.3 Events. The database
and subsequent backups contain searchable text; no automatic synchronization or upload occurs.
Read-only previews live in `context/previews/<revision-id>/<original-safe-name>`. If a host modifies
a preview, PIG reports a conflict rather than overwriting it. Automatic preview cleanup and secure
erasure are not claimed.

## 当前验证与剩余停止线 / Verification and remaining gates

合成测试覆盖四种格式的已知命中与 Locator、同键复用、原外部文件变化后固定结果保持、
索引清空/删除重建、中文短语、明确 `UNSUPPORTED`、取消与重试、中断恢复、预览冲突、
损坏/Hash 错误、V1/V2 升级与 Context UI 回归。2026-10-10 首次全量回归为
**235 passed、95 skipped、3 failed**；3 个失败均为新 Migration 类型/表元数据差异，
修正后完整回归 **241 passed、95 skipped、1 warning、0 failed**。此后补充的旧 Schema
拒绝、重启读取与最终迁移定向回归 **16 passed**；源码自动测试不等于人工签收。

Synthetic checks cover all four format/locator paths, equivalent-run reuse, fixed results after
external changes, empty/dropped index rebuilding, Chinese phrase search, explicit `UNSUPPORTED`,
cancellation/retry, interrupted recovery, preview conflict, corruption/hash failures, upgrade,
and Context UI regression. The first full run on 2026-10-10 reported **235 passed,
95 skipped, 3 failed**; all three failures were new Migration/ORM metadata mismatches.
After repair, the full suite reported **241 passed, 95 skipped, 1 warning, 0 failed**.
Additional old-schema rejection, restart-read, and final Migration checks reported
**16 passed**. Automated source tests are not manual acceptance.

使用可重复脚本 `python -m scripts.benchmark_v23_content --base-dir <workspace>`，在本机
三轮合成约 1.2 MiB / 8,001 行 TXT 的中位数：提取 **1.819 秒**、搜索 **0.0097 秒**；
三轮进程树 Peak RSS 为 **156.8–163.1 MiB**，SQLite 大小 **5.0 MiB** 左右。离屏 Qt
25 ms Timer 在提取期间继续触发。无签名 Windows onedir 包构建成功，包内
`--runtime-smoke-test` 返回 0；包内 `--content-worker` 读取仓库 README 并输出
246 个元素（31,531 字节），返回 0。该数字是 2026-10-10 的本机参考基线，不是跨设备
SLA；尚未测超大多 Revision、中文短语扫描和正式 Windows 打包峰值。

The repeatable `python -m scripts.benchmark_v23_content --base-dir <workspace>` benchmark
used three synthetic ~1.2 MiB / 8,001-line TXT runs on this host. Median extraction was
**1.819 s**, median search **0.0097 s**; process-tree peak RSS ranged **156.8–163.1 MiB**
and SQLite was about **5.0 MiB**. An offscreen Qt 25 ms timer continued ticking during
extraction. An unsigned Windows onedir package built successfully; its
`--runtime-smoke-test` exited 0, and its `--content-worker` extracted 246 elements
(31,531 bytes) from this repository's README and exited 0. This is a 2026-10-10 local
reference baseline, not a cross-device SLA. Many-Revision projects, Chinese substring scans,
and packaged Windows peaks remain unmeasured.

PDF/DOCX/PPTX 的真实 Fixture、定位准确率、候选依赖许可证/包体/性能和 Windows 包装
评估仍是 D128-A 独立 Gate；未经该 Gate 不加入运行时依赖。真实资料、异机、打包桌面
人工流程和用户验收须另行记录。中文短语走本地子串查询，面对大量已提取元素可能比 FTS5
慢，需用大规模合成数据三轮测量后再决定是否引入专用中文倒排词元。

Real-fixture locator quality, candidate licensing/package size/performance, and Windows packaged
evaluation for PDF/DOCX/PPTX remain the separate D128-A gate; no runtime dependency is adopted
before it. Real-data, cross-machine, packaged-desktop manual flow, and user acceptance require separate records.
Short Chinese phrases use a local substring query and may be slower than FTS5 at large element
counts; measure three synthetic runs before considering a dedicated Chinese token index.

## 2026-10-10 源码桌面人工验收记录 / Source-Desktop Manual Check

本次仅使用 `D:\PIG\.v23-manual` 下的合成资料和独立测试项目；不涉及用户真实资料。
桌面端从源码启动，打开测试项目、导入文件夹，并分别将 TXT、CSV 和 EML 原邮件加入
Project Context。三者的显式固定 Revision 提取均显示 `SUCCEEDED`：TXT 3 个元素、CSV
3 个元素、EML 5 个元素。搜索分别命中 `LINE: 2`、`CSV_ROW: 2` 和
`EMAIL_FIELD: body:1:1`。TXT 搜索结果双击后以 `brief.txt` 原名在记事本打开；
`context/previews/<revision-id>/brief.txt` 已核实为只读文件。手动重建索引报告 3 个
元素，重搜同一中文短语仍命中第 2 行。

This check used only synthetic files and an isolated project under `D:\PIG\.v23-manual`,
not customer data. The source desktop imported the folder and promoted TXT, CSV, and the
original EML message to Project Context. Explicit extraction of their fixed Revisions showed
`SUCCEEDED` with 3, 3, and 5 elements respectively. Searches located `LINE: 2`,
`CSV_ROW: 2`, and `EMAIL_FIELD: body:1:1`. Double-clicking the TXT result opened an
original-name `brief.txt` preview in Notepad; its preview file was verified read-only.
Manual index rebuilding reported 3 elements, and the same Chinese phrase still located line 2.

桌面“新建项目”在所选测试父目录下两次显示通用失败提示；同一路径由应用服务建立的
独立项目可从桌面端打开并完成上述流程。因此本次只能证明已打开项目的 V2.3 主流程，
**不能签收从零新建项目的完整桌面闭环**。失败根因尚未确认，不将其归因于 V2.3。
XLSX、只读预览冲突、取消/中断恢复、打包桌面、真实资料、异机与用户最终签收尚未在
本次人工流程中验证；已有自动化测试不替代这些人工检查。

The desktop “New Project” action showed a generic failure twice under the selected test
parent. An isolated project created through the application service at that path could be
opened in the desktop and used for the workflow above. This verifies V2.3 within an opened
project, **not the full new-project desktop path**. The cause is unconfirmed and is not
attributed to V2.3. XLSX, preview conflicts, cancellation/interruption recovery, packaged
desktop, real data, another machine, and final owner acceptance were not manually checked
in this run; automated tests do not replace these checks.
