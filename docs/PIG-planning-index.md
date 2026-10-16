# PIG 当前规划索引 / PIG Active Planning Index

本文件负责当前/历史文档导航。当前阶段、授权和验收状态集中在
[CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md)，具体约束等级与冲突处理见主规则。

This file navigates active and historical documents. Phase, authorization, and acceptance
status are maintained in [CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md); requirement levels
and conflict resolution follow the main rules.

## 1. 规则入口 / Rule entry points

1. [PIG Project Rules](../PIG%20Project%20Rules.md)：长期原则与读取路由 / Long-term principles and routing.
2. [CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md)：当前范围与授权 / Current scope and authorization.
3. [AGENTS](../AGENTS.md)：仓库执行入口 / Repository execution entry.
4. [DOCUMENTATION-STYLE](DOCUMENTATION-STYLE.md)：双语与信息维护 / Languages and information maintenance.
5. [DEVELOPMENT](project-rules/DEVELOPMENT.md)：风险分级与完成要求 / Risk-based development and completion.

其他子规则按主规则路由读取。下列 ADR 不是相互覆盖的简单排名；按主题、接受状态
和显式取代关系选取，后续阶段授权不能从历史提案自动推导。

Read other subrules by the main routing table. ADRs below are not a simple overriding ranking;
use their topic, accepted status, and explicit supersession. Historical proposals cannot imply later authorization.

## 2. 决策与基线 / Decisions and baselines

- [ADR-033](decisions/ADR-033-linked-project-default-flow.md)：新项目默认关联现有目录；明确取代旧 Snapshot 默认主流程 / New default linked-folder flow; explicitly supersedes the old snapshot default.

- [ADR-010](decisions/ADR-010-v1-project-file-workbench-reset.md)：V1 Workbench 重置 / V1 reset.
- [V1 规划索引](PIG-V1-planning-index.md)：V1 当前决定和实现历史 / V1 active decisions and history.
- [ADR-024](decisions/ADR-024-v2-project-context-foundation.md)：V2 基础 / V2 foundation.
- [ADR-025](decisions/ADR-025-v2.1-context-foundation-decisions.md)：V2.1 具体决定 / V2.1 decisions.
- [ADR-026](decisions/ADR-026-v2.2-context-pack.md)：V2.2 Context Pack / V2.2 Context Pack.
- [ADR-027](decisions/ADR-027-v2.3-canonical-content-search.md)：V2.3 内容提取与搜索 / V2.3 content extraction and search.
- [ADR-028](decisions/ADR-028-v2.4-project-experience-controlled-ai.md)：V2.4 人工经验、对接契约与受控 AI / V2.4 human experience, integration contract, and controlled AI.
- [ADR-029](decisions/ADR-029-v2.4-provider-and-budget-gate.md)：V2.4 Provider 候选、合成测试与成本 Gate / V2.4 provider candidates, synthetic tests, and budget gate.
- [ADR-030](decisions/ADR-030-default-no-legacy-project-compatibility.md)：新版本默认不兼容旧项目 / No older-project compatibility by default.
- [ADR-031](decisions/ADR-031-expanded-container-view-export.md)：Container View 当前展开结构导出 / Export current expanded Container View structure.
- [ADR-032](decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md)：V2.4 本机源码桌面 DeepSeek 合成资料受限外发 / V2.4 bounded local source-desktop synthetic DeepSeek egress.
- [V2 范围](application/PIG-V2-scope.md)与[V2 规划索引](PIG-V2-planning-index.md) / V2 scope and planning navigation.

## 3. V2 领域与实施文档 / V2 domain and implementation documents

- [领域模型](domain/PIG-V2-project-context-domain-model.md) / Domain model.
- [状态机与不变量](domain/PIG-V2-state-machines-and-invariants.md) / States and invariants.
- [Milestones](application/PIG-V2-milestones.md) / Milestones.
- [V2.1 Foundation](application/PIG-V2.1-context-foundation.md).
- [V2.1.1 Schema](application/PIG-V2.1.1-upgrade-schema.md).
- [V2.1.2 Capture](application/PIG-V2.1.2-capture-core.md).
- [V2.1.3 Actions](application/PIG-V2.1.3-context-actions.md).
- [V2.1.4 UI](application/PIG-V2.1.4-minimum-ui-plan.md).
- [V2.1.5 Acceptance](application/PIG-V2.1.5-acceptance.md).
- [V2.2 决策背景](application/PIG-V2.2-decision-gate.md) / V2.2 decision background.
- [V2.2.1 Contract](application/PIG-V2.2.1-contract-schema.md).
- [V2.2 Implementation / Acceptance](application/PIG-V2.2-implementation-acceptance.md).
- [V2.3 决策门](application/PIG-V2.3-decision-gate.md)：原始选项；当前授权以 CURRENT_SCOPE 为准 / Original options; current authorization follows CURRENT_SCOPE.
- [V2.3 实施与验收](application/PIG-V2.3-implementation-acceptance.md) / V2.3 implementation and acceptance.
- [V2.3 复杂格式评估](application/PIG-V2.3-complex-format-evaluation.md) / Complex-format evaluation gate.
- [桌面界面简化与验收](application/PIG-V2-desktop-ux-simplification.md) / Desktop UI simplification and acceptance.
- [V2.4 决策门](application/PIG-V2.4-decision-gate.md)：项目经验、对接契约与受控 AI 的选项和停止线 / Project-experience, integration-contract, and controlled-AI options and stop line.
- [V2.4.1 契约](application/PIG-V2.4.1-experience-contract.md)：人工经验、证据关系、Bundle 与只读查询 / Human experience, evidence links, Bundle, and read-only queries.
- [V2.4 实施与验收](application/PIG-V2.4-implementation-acceptance.md)：源码闭环、测试证据与未完成的真实 Provider Gate / Source loop, test evidence, and outstanding live-provider gate.
- [V2.4 工作区交互修复与复测](application/PIG-V2.4-workspace-interaction-followup.md)：B01/B02 恢复、拖动与重命名复测 / B01/B02 recovery, drag, and rename retest.

V2 不能静默覆盖 V1 的 Original、来源、受控打开和安全边界。遇到实际冲突先查
当前有效 ADR 与后续授权，再按主规则处理。

V2 cannot silently override V1 Original, origin, controlled-open, and safety boundaries.
Check active ADRs and subsequent authorization before applying the main conflict process.
