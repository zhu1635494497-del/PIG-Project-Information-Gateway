# PIG Workbench W10 RC.2 资格报告 / RC.2 Qualification Report

- 日期：2026-09-27 / Date: 2026-09-27
- 状态：自动 Gate 已通过；人工桌面验收前仍不得建立 `v1.0.0-rc.2` / Status: Automated gates pass; `v1.0.0-rc.2` must not be created before manual desktop acceptance
- 当前版本：`1.0.0rc1` / Current version: `1.0.0rc1`
- 范围：W10.5 自动资格验证与人工验收准备 / Scope: W10.5 automated qualification and manual-acceptance preparation

## 自动资格结果 / Automated Qualification Result

| Gate / Gate | 结果 / Result | 证据 / Evidence |
| --- | --- | --- |
| 固定 Fixture 三轮基准 / Three-run fixed-fixture benchmark | 绝对 Gate 与 RC.1 相对门全部通过 / All absolute gates and RC.1 relative gates pass | `performance-baseline-v1.0.0-rc.2.json` |
| 25% 相对门 / 25% relative gate | Materialize `0.881s`，Refresh `0.811s`，均通过 / Materialize `0.881s` and Refresh `0.811s`, both pass | RC.1 comparison |
| Peak RSS | 最大约 `214.1 MiB`，通过 `≤300 MiB` / Maximum about `214.1 MiB`, passes `≤300 MiB` | Formal benchmark |
| 首次 Progress / First progress | 单文件 `0.031s`，多文件 `0.029s`，通过 `≤0.5s` / Single file `0.031s`, many files `0.029s`, pass `≤0.5s` | Formal benchmark |
| Query Plan | 现有索引足够；不创建 `0009` / Existing indexes are sufficient; no `0009` | Formal benchmark |
| 全量回归 / Full regression | `172 passed, 95 skipped`，一个预期 Warning / `172 passed, 95 skipped`, one expected warning | Local test run |
| Migration | Head `0008_workbench_recovery`；`4 passed` / Head `0008_workbench_recovery`; `4 passed` | Focused migration run |
| Windows Build | PyInstaller `onedir` 构建成功；ICU 冲突检查通过 / PyInstaller `onedir` build succeeds; ICU collision check passes | `dist/workbench-w10/PIG` |
| Runtime Smoke | Exit code `0` / Exit code `0` | Current Windows host |
| Packaged Flow | Exit code `0`，Report `PASS` / Exit code `0`, report `PASS` | `acceptance/workbench-w10-final-safe` |

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

- [ ] 完成源码桌面真实数据验收。 / Complete source-desktop real-data acceptance.
- [ ] 完成最终打包桌面真实数据验收。 / Complete final-package real-data acceptance.
- [ ] W9 License、Signing、Clean-host、真实 RAR 与最终签名包 Gate 继续保持。 / Keep
  the W9 license, signing, clean-host, real-RAR, and final signed-package gates.

在以上 Gate 全部通过前，不得把代码版本改为 `1.0.0rc2`，不得创建
`v1.0.0-rc.2` Tag，也不得发布对应 GitHub Pre-release。

Until every gate above passes, the code version must not change to `1.0.0rc2`,
the `v1.0.0-rc.2` tag must not be created, and the corresponding GitHub
pre-release must not be published.
