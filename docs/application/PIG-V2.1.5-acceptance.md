# V2.1.5 验收记录 / V2.1.5 Acceptance Record

- 状态：合成数据自动测试和用户人工桌面验收通过 / Status: Synthetic automated tests and user-reported manual desktop acceptance passed
- 日期：2026-10-08 / Date: 2026-10-08
- 范围：Project Context 基础闭环，不进入 V2.2 / Scope: Project Context foundation loop; no V2.2 work

## 1. 本轮范围与决策 / Scope and decision for this run

产品负责人要求本轮不用考虑 V1 数据库适配，并选择先用合成资料。因此旧 V1
`project.sqlite` 的迁移和旧项目 GUI 打开不作为本次验收门槛；D115-A 的既有实现不删除，
但不能据本轮结果宣称旧库适配已通过人工验收。此处只调整 V2.1.5 的验收范围，不改变
Original 不可变或其它 ADR 决策。`D:\PIG测试` 不用于本轮验收。

The product owner excluded V1 database adaptation from this run and chose
synthetic inputs first. Migration of an old V1 `project.sqlite` and opening it
through the GUI are therefore not acceptance gates in this run. Existing D115-A
implementation remains, but this run cannot establish manual acceptance of
old-database compatibility. This is an acceptance-scope exception, not a change
to Original immutability or other ADR decisions. `D:\PIG测试` is not used.

## 2. 自动化证据 / Automated evidence

`tests/application/test_v215_acceptance.py` 使用隔离临时项目验证：80 MiB Working 文件、
嵌套 ZIP 的未物化 Virtual Child、不可变 Original、捕获来源与 Source Node、人工说明、
Section、陈旧写冲突、Freshness、显式新 Revision 和重启保持；另外验证容量预检及执行
阻断不产生 Revision、取消安全点留下 `CANCELLED_AT_SAFE_POINT` 而非当前 Revision。
执行结果：`3 passed`；连同 V2.1.2、V2.1.3、对象存储和 V2.1.4 UI 的相关回归为
`27 passed`。这些是自动化证据，不等于桌面流畅性人工确认。

`tests/application/test_v215_acceptance.py` uses isolated temporary Projects to
check an 80 MiB Working file, an unmaterialized virtual child in a nested ZIP,
immutable Original, capture source and Source Node, human guidance, Section,
stale-write conflict, Freshness, explicit new Revision, and persistence after
reopen. It also checks capacity preflight/execution blocking without a Revision
and safe-point cancellation leaving `CANCELLED_AT_SAFE_POINT` rather than a
current Revision. Result: `3 passed`; the related V2.1.2, V2.1.3, object-store,
and V2.1.4 UI regression totals `27 passed`. These automated tests do not
substitute for human judgment of desktop responsiveness.

先前 V2.1.4 的全量证据为 UI `17 passed, 4 skipped`、非 UI
`189 passed, 91 skipped, 1 warning`；历史跳过项和环境限制见 V2.1.4 计划。
本轮重跑的是上述 27 项相关回归；全量数字仍是上一阶段的证据，不冒充本轮结果。

The previous V2.1.4 full-suite evidence was UI `17 passed, 4 skipped` and
non-UI `189 passed, 91 skipped, 1 warning`; historical skips and host limits are
documented in the V2.1.4 plan. This run reran the 27 relevant checks above;
the full-suite figures remain prior-stage evidence rather than current totals.

## 3. 合成资料与隔离 / Synthetic data and isolation

运行以下命令可一次性生成资料；脚本拒绝覆盖已有目录。当前已生成于
`D:\PIG\acceptance\v2.1.5-synthetic-inputs`，位于 Git 忽略的 `acceptance/` 下。
新建项目建议存放于 `D:\PIG\acceptance\v2.1.5-projects`。不要把真实文件拖入
这个项目，也不要对真实资料模拟磁盘不足。

The following command generates inputs once and refuses to overwrite an existing
directory. Inputs already exist at `D:\PIG\acceptance\v2.1.5-synthetic-inputs`,
under Git-ignored `acceptance/`. Create the test Project under
`D:\PIG\acceptance\v2.1.5-projects`. Do not import real files into this
Project or simulate low disk against real materials.

```powershell
.venv\Scripts\python.exe scripts\prepare_v215_acceptance.py D:\PIG\acceptance\v2.1.5-synthetic-inputs
.venv\Scripts\python.exe -m pig.ui.app --workspace-root D:\PIG\acceptance\v2.1.5-projects
```

## 4. 源码桌面人工流程 / Source-desktop manual flow

1. 新建 `V215 合成验收` 项目，并一次性导入 `input-folder`、`nested.zip`、
   `large-80m.bin`。确认 Workspace Tree 中能展开 ZIP 的
   `mail/attachments/core.txt`，且原输入仍可独立打开。
2. 在 `large-80m.bin` 和 `core.txt` 上使用右键 `加入 Project Context`。
   记录预检来源、预计大小和容量提示；确认大文件捕获期间窗口可切换视图、滚动和取消，
   而不是长期“未响应”。`core.txt` 不应被强制生成 Working Artifact。
3. 在 Context 创建 `Decisions` Section，把两个 Item 放入 Section；为一个 Item 写说明。
   如 UI 允许，再把同一 Item 放入第二个 Section。删除 Section 后检查虚拟
   `Unsectioned`，随后恢复 Section 和 Placement。
4. 在 Workspace 中打开 `input-folder/notes/decision.txt`，通过宿主程序修改并保存。
   将其加入 Context，修改 Working 后刷新并检查 `WORKSPACE_UPDATED`；明确创建新
   Revision 后再检查 `CURRENT`。不得因保存 Working 而自动覆盖 Context 版本。
5. 关闭并重启桌面端，重新打开项目，确认 Section、Placement、说明、当前 Revision
   和 Freshness 保持。检查 Original 文件未变化。
6. 对合成项目尝试取消一次长文件捕获，确认没有假成功提示；如有错误，记录可见错误码
   与日志。容量阻断、并发冲突和取消后的数据库状态已有自动化覆盖，人工不需要真填满磁盘。

1. Create a `V215 synthetic acceptance` Project and import `input-folder`,
   `nested.zip`, and `large-80m.bin` together. Expand
   `mail/attachments/core.txt` in the Workspace Tree and verify that the input
   files remain independently readable.
2. Use `Add to Project Context` on `large-80m.bin` and `core.txt`. Record the
   preflight source, estimated size, and capacity message. While the large file
   is captured, switch views, scroll, and try cancellation; the window should
   not remain unresponsive. `core.txt` must not be forced into a Working Artifact.
3. Create a `Decisions` Section, place both Items in it, and add guidance to one
   Item. If the UI permits it, place one Item in a second Section. Remove the
   first Section, check virtual `Unsectioned`, then restore the Section and
   Placement.
4. Open `input-folder/notes/decision.txt` from Workspace and edit/save it in
   its host application. Promote it, change Working again, refresh, and verify
   `WORKSPACE_UPDATED`; explicitly capture a new Revision and verify `CURRENT`.
   Saving Working must not silently overwrite the Context version.
5. Close and relaunch the desktop app, reopen the Project, and verify Sections,
   Placements, guidance, current Revision, and Freshness persist. Verify that
   Original inputs have not changed.
6. Attempt to cancel a long-file capture in this synthetic Project and ensure
   no false success appears. Record any visible error code and log. Automated
   tests already cover capacity blocking, concurrent conflicts, and post-cancel
   database state; there is no need to fill a real disk manually.

## 5. 验收结论 / Acceptance result

2026-10-08，用户反馈“测试通过”，确认本轮源码桌面人工验收通过；此前相关自动化回归
为 `27 passed`。该反馈未提供逐步计时、录屏或独立问题清单，因此只记录用户签收结论，
不虚构性能指标。V2.1.5 在本轮约定范围内关闭。旧 V1 数据库兼容性未纳入本轮，未来
如需正式支持须单独验收。V2.2 仍需另行授权。

On 2026-10-08, the user reported that testing passed, confirming manual
source-desktop acceptance for this run. The preceding related automated
regression was `27 passed`. No step-by-step timings, recording, or separate
issue list was supplied, so this record captures the user's sign-off without
inventing performance metrics. V2.1.5 is closed within the agreed scope. Old
V1 database compatibility was excluded and needs separate acceptance if formal
support is required. V2.2 still requires separate authorization.
