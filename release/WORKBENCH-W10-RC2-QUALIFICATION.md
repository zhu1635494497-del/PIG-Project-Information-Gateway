# PIG Workbench W10 RC.2 资格报告 / RC.2 Qualification Report

- 日期：2026-09-28 / Date: 2026-09-28
- 状态：W10 自动 Gate、源码桌面复验和最终打包桌面人工验收均已通过；`v1.0.0-rc.2` Unsigned Pre-release 获准建立 / Status: W10 automated gates, source-desktop re-acceptance, and final-package manual desktop acceptance all pass; the `v1.0.0-rc.2` unsigned pre-release is approved for creation
- 当前版本：`1.0.0rc2` / Current version: `1.0.0rc2`
- 范围：W10.5 自动资格验证与人工验收准备 / Scope: W10.5 automated qualification and manual-acceptance preparation

## 自动资格结果 / Automated Qualification Result

| Gate / Gate | 结果 / Result | 证据 / Evidence |
| --- | --- | --- |
| 固定 Fixture 三轮基准 / Three-run fixed-fixture benchmark | 绝对 Gate 与 RC.1 相对门全部通过 / All absolute gates and RC.1 relative gates pass | `performance-baseline-v1.0.0-rc.2.json` |
| 25% 相对门 / 25% relative gate | Materialize `0.881s`，Refresh `0.811s`，均通过 / Materialize `0.881s` and Refresh `0.811s`, both pass | RC.1 comparison |
| Peak RSS | 最大约 `214.1 MiB`，通过 `≤300 MiB` / Maximum about `214.1 MiB`, passes `≤300 MiB` | Formal benchmark |
| 首次 Progress / First progress | 单文件 `0.031s`，多文件 `0.029s`，通过 `≤0.5s` / Single file `0.031s`, many files `0.029s`, pass `≤0.5s` | Formal benchmark |
| Query Plan | 现有索引足够；不创建 `0009` / Existing indexes are sufficient; no `0009` | Formal benchmark |
| Workspace UI 响应 / Workspace UI responsiveness | 10,000 行、201 个滚动步平均 `<25 ms`，无全量图标绘制 / 10,000 rows and 201 scroll steps average `<25 ms`, without eager icon painting | UI responsiveness regression |
| 全量回归 / Full regression | `176 passed, 95 skipped`，一个预期 Warning / `176 passed, 95 skipped`, one expected warning | Local test run |
| Migration | Head `0008_workbench_recovery`；`4 passed` / Head `0008_workbench_recovery`; `4 passed` | Focused migration run |
| Windows Build | PyInstaller `onedir` 构建成功；ICU 冲突检查通过 / PyInstaller `onedir` build succeeds; ICU collision check passes | `dist/workbench-w10/PIG` |
| Runtime Smoke | Exit code `0` / Exit code `0` | Current Windows host |
| Packaged Flow | Exit code `0`，Report `PASS` / Exit code `0`, report `PASS` | `acceptance/workbench-w10-final-safe` |

## 人工验收发现与修复 / Manual-Acceptance Finding and Fix

2026-09-27 的首次源码桌面验收发现：处理完成后，点击 Workspace 或使用鼠标滚轮仍有
明显卡顿。检查确认滚动没有触发数据库查询；卡顿来自 Qt Tree 展示热路径，包括重复
图标生成、重复显示值组装、线性 Row 查找，以及辅助列的全内容自动测宽。

The first source-desktop acceptance on 2026-09-27 found visible stalls when the
Workspace was clicked or scrolled after processing had completed. Inspection
confirmed that scrolling did not query the database. The stalls came from the
Qt Tree presentation hot path: repeated icon generation, repeated display-value
assembly, linear row lookup, and content-wide autosizing of secondary columns.

修复仅改变 Read/UI Projection：Model 生命周期内缓存显示值和图标，预计算 Item Row，
辅助列使用有界可调宽度，并启用像素级滚动。Domain、Original/Working、Lineage、状态、
Event、权限和 SQLite Schema 均未改变。修复后专项测试 `11 passed`，全量回归
`176 passed, 95 skipped`；重新构建包的 ICU 冲突检查、Runtime Smoke 与 Packaged Flow
均通过。

The fix changes only the Read/UI projection: display values and icons are cached
for the model lifetime, item rows are precomputed, secondary columns use bounded
user-adjustable widths, and scrolling is pixel-based. Domain, Original/Working,
Lineage, state, Events, permissions, and the SQLite schema are unchanged. The
focused suite reports `11 passed`, the full regression reports `176 passed, 95
skipped`, and the rebuilt package passes the ICU collision check, runtime smoke,
and packaged flow.

2026-09-27，产品负责人使用真实桌面交互完成滚动修复复验并确认通过；此结果只关闭
源码桌面 Gate，不替代最终打包桌面的人工操作验收。

On 2026-09-27, the product owner completed hands-on re-acceptance of the
scrolling fix and confirmed it passed. This closes only the source-desktop gate
and does not replace hands-on acceptance of the final packaged desktop.

## 数据与安全语义 / Data and Safety Semantics

本阶段未增加业务实体或 Migration。Original 仍不可变；Working 仍是唯一可编辑副本；
当前和上一版本仍显式保存。Snapshot 优化继续执行 Copy+SHA、Link 拒绝、输入稳定性、
目录成员复核、资源限制和 Staging 原子发布。Working 版本硬链接只用于不可变检查点，
完整 SHA-256 验证后发布；可编辑 Working 文件从不共享该硬链接，不支持时回退 Copy+SHA。

This phase adds no business entity or migration. Original remains immutable;
Working remains the only editable copy; current and previous versions remain
explicitly stored. Snapshot optimization retains copy-plus-hash, link rejection,
input stability, final membership verification, resource limits, and atomic
staging publication. Working-version hard links apply only to immutable
checkpoints and are published after full SHA-256 verification. The editable
Working file never shares that link, and unsupported filesystems fall back to
copy-plus-hash.

## 尚未通过的 Gate / Open Gates

- [x] 使用滚动修复重新完成源码桌面真实数据验收（2026-09-27）。 / Source-desktop real-data re-acceptance with the scrolling fix completed (2026-09-27).
- [x] 使用同一修复重新完成最终打包桌面真实数据验收（2026-09-28）。 / Final-package real-data acceptance with the same fix completed (2026-09-28).
- [ ] W9 License、Signing、Clean-host、真实 RAR 与最终签名包 Gate 继续保持。 / Keep
  the W9 license, signing, clean-host, real-RAR, and final signed-package gates.

W10 的 RC.2 资格门已经关闭，允许创建明确标记为未签名的 `v1.0.0-rc.2`
Git Tag 和 GitHub Pre-release。W9 未完成项继续阻止正式签名 V1 Release；不得把该
候选版描述为已签名、已完成许可证复核或已通过干净主机矩阵。

The W10 RC.2 qualification gate is closed, so an explicitly unsigned
`v1.0.0-rc.2` Git tag and GitHub pre-release may be created. The remaining W9
items continue to block the formal signed V1 release; this candidate must not
be described as signed, license-reviewed, or clean-host-matrix qualified.
