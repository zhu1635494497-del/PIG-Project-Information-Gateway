# PIG 当前规划索引 / PIG Active Planning Index

- 状态：当前有效 / Status: Active
- 日期：2026-10-08 / Date: 2026-10-08
- 当前阶段：V2.2 Context Pack 实施与验收 / Current phase: V2.2 Context Pack implementation and acceptance
- 当前授权：D120-A 至 D126-A 已批准；V2.2.2–V2.2.4 获一次性授权 / Current authorization: D120-A through D126-A approved; V2.2.2–V2.2.4 authorized together

## 当前规范优先级 / Active authority order

1. `PIG Project Rules.md`
2. `AGENTS.md`
3. `docs/DOCUMENTATION-STYLE.md`
4. `docs/decisions/ADR-010-v1-project-file-workbench-reset.md`
5. `docs/decisions/ADR-024-v2-project-context-foundation.md`
6. `docs/decisions/ADR-025-v2.1-context-foundation-decisions.md`
7. `docs/decisions/ADR-026-v2.2-context-pack.md`
8. `docs/application/PIG-V2-scope.md`
9. `docs/domain/PIG-V2-project-context-domain-model.md`
10. `docs/domain/PIG-V2-state-machines-and-invariants.md`
11. `docs/application/PIG-V2.1-context-foundation.md`
12. `docs/application/PIG-V2.1.1-upgrade-schema.md`
13. `docs/application/PIG-V2-milestones.md`
14. `docs/PIG-V2-planning-index.md`
15. `docs/application/PIG-V2.1.2-capture-core.md`
16. `docs/application/PIG-V2.1.3-context-actions.md`
17. `docs/application/PIG-V2.1.4-minimum-ui-plan.md`
18. `docs/application/PIG-V2.1.5-acceptance.md`
19. `docs/application/PIG-V2.2-decision-gate.md`（已批准决策背景 / approved decision background）
20. `docs/application/PIG-V2.2.1-contract-schema.md`
21. `docs/application/PIG-V2.2-implementation-acceptance.md`

V1 的详细决策和实现记录继续由 `docs/PIG-V1-planning-index.md` 管理。若 V2 文档
与 V1 的不可变 Original、Source/Workspace 分离、安全或受控打开原则冲突，必须先
回到 ADR 决策，不得由实现自行覆盖。

Detailed V1 decisions and implementation history remain indexed by
`docs/PIG-V1-planning-index.md`. If a V2 document conflicts with V1 immutable
Originals, Source/Workspace separation, safety, or controlled-open principles,
the conflict must return to an ADR decision and must not be resolved silently by
implementation.

## 当前授权门 / Current authorization gate

V2.1.5 已通过本轮验收；旧 V1 数据库适配未签收。D120-A 至 D126-A 已批准，
用户明确授权一次性完成 V2.2.2–V2.2.4。内容解析器、AI/RAG、模型调用、平台
适配与 V2.3 尚未授权。真实资料和异机验收仍需用户单独执行或批准。

V2.1.5 passed this acceptance run; old V1 database adaptation was not accepted.
D120-A through D126-A are approved, and the user explicitly authorized
V2.2.2–V2.2.4 together. Content extractors, AI/RAG, model calls, platform
adapters, and V2.3 remain unauthorized. Real-data and cross-machine acceptance
still require separate user execution or approval.
