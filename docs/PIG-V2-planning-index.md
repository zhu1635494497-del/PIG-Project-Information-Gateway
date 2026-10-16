# PIG V2 规划索引 / PIG V2 Planning Index

本文件只维护 V2 读取路径。当前阶段、授权、未签收项与下一步停止线以
[CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md) 为准；不在这里复制第二份状态。

This file maintains V2 reading paths. Phase, authorization, unaccepted items, and the active
stop line follow [CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md), without a duplicated status record.

## 1. 总入口 / Entry points

- [主规则](../PIG%20Project%20Rules.md) / Main rules.
- [跨版本规划索引](PIG-planning-index.md) / Cross-version planning index.
- [V1 决策与实现历史](PIG-V1-planning-index.md) / V1 decisions and implementation history.

## 2. V2 决策与范围 / V2 decisions and scope

- [ADR-024](decisions/ADR-024-v2-project-context-foundation.md)：D101–D112 基础决定 / Foundation decisions.
- [ADR-025](decisions/ADR-025-v2.1-context-foundation-decisions.md)：D113–D119 Context 决定 / Context decisions.
- [ADR-026](decisions/ADR-026-v2.2-context-pack.md)：D120–D126 Pack 决定 / Pack decisions.
- [ADR-027](decisions/ADR-027-v2.3-canonical-content-search.md)：D127–D132 内容与搜索决定 / Content and search decisions.
- [V2 Scope](application/PIG-V2-scope.md).
- [V2 Domain](domain/PIG-V2-project-context-domain-model.md).
- [V2 States / Invariants](domain/PIG-V2-state-machines-and-invariants.md).
- [V2 Milestones](application/PIG-V2-milestones.md).

## 3. 阶段文档 / Milestone documents

V2.1 与 V2.2 的完整实施、验收文档见[跨版本索引](PIG-planning-index.md)。
V2.3 的原始选择见[V2.3 决策门](application/PIG-V2.3-decision-gate.md)，
当前授权与停止线以 CURRENT_SCOPE 为准。

The [cross-version index](PIG-planning-index.md) lists V2.1/V2.2 implementation and acceptance
documents. The [V2.3 gate](application/PIG-V2.3-decision-gate.md) preserves the original
choices; current authorization and stop lines follow CURRENT_SCOPE.

[V2.3 实施与验收](application/PIG-V2.3-implementation-acceptance.md)记录代码、测试与人工停止线。

[V2.3 implementation and acceptance](application/PIG-V2.3-implementation-acceptance.md)
records implementation evidence, tests, and remaining manual gates.

[V2.3 复杂格式评估](application/PIG-V2.3-complex-format-evaluation.md)保留 D128-A 的
Fixture、许可证、定位、性能与打包证据门。

[V2.3 complex-format evaluation](application/PIG-V2.3-complex-format-evaluation.md)
preserves the D128-A fixture, licensing, locator, performance, and packaging gate.

[V2.4 决策门](application/PIG-V2.4-decision-gate.md)保留 D133–D142 的方案对照；
[ADR-028](decisions/ADR-028-v2.4-project-experience-controlled-ai.md)记录已批准的 A 方案，
[V2.4.1 契约](application/PIG-V2.4.1-experience-contract.md)记录首段实施边界。
[ADR-029](decisions/ADR-029-v2.4-provider-and-budget-gate.md)记录 D143–D146，
[实施验收](application/PIG-V2.4-implementation-acceptance.md)记录源码与剩余 Gate。
阶段与验收仍以 CURRENT_SCOPE 为准。

The [V2.4 decision gate](application/PIG-V2.4-decision-gate.md) preserves the D133–D142
alternatives; [ADR-028](decisions/ADR-028-v2.4-project-experience-controlled-ai.md) records
the accepted A choices, and the [V2.4.1 contract](application/PIG-V2.4.1-experience-contract.md)
defines the first implementation boundary. Phase and acceptance still follow CURRENT_SCOPE.
[ADR-029](decisions/ADR-029-v2.4-provider-and-budget-gate.md) records D143–D146;
[implementation/acceptance](application/PIG-V2.4-implementation-acceptance.md) tracks
source behavior and remaining gates.
