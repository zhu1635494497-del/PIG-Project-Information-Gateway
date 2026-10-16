# 开发与验收规则 / Development and Acceptance Rules

适用：规划、实现、评审、测试和交付。按风险执行；无需为所有任务机械填写十项清单。

Applies to planning, implementation, review, testing, and delivery. Apply according to risk;
every task does not require a mechanical ten-item checklist.

## 1. 风险分级 / Risk classification

| 等级 / Level | 典型改动 / Examples | 实现前 / Before | 完成后 / After |
| --- | --- | --- | --- |
| 低 / Low | 文案、规则整理、展示样式、无语义变化的局部重构 / Copy, rules, styling, local refactor without behavior changes | 说明目标与范围 / State goal and scope | 改了什么、如何验证、实质限制 / Changes, verification, material limits |
| 中 / Medium | 新可逆 Action、UI 行为、Handler 修复、查询变化 / Reversible actions, UI behavior, handler fixes, queries | 说明受影响对象、数据流/状态、错误与验收 / Objects, flow/state, errors, acceptance | 结果、关键影响、验证证据、未闭环项 / Outcome, key impact, evidence, remaining gaps |
| 高 / High | Schema/Migration、Snapshot、删除/覆盖、版本轮换、恢复、路径/权限、外发 / Schema, snapshots, delete/overwrite, rotation, recovery, paths/permissions, transmission | 完整相关影响检查与失败恢复方案；满足已有决策门 / Relevant full impact check, failure recovery, existing gates | 关键不变量、失败验证、升级/回退、安全、待验收项 / Invariants, failure checks, upgrade/fallback, safety, pending acceptance |

等级由实际行为决定，不能只看文件类型或改动行数。修改规则若改变高风险产品行为，
按高风险处理；仅整理文档且不改变运行时行为可按低风险验证。

Risk follows actual behavior, not file type or line count. Rule changes that alter high-risk product
behavior need high-risk handling; documentation restructuring without runtime changes may use low-risk checks.

## 2. 影响检查与批准 / Impact checks and approval

中高风险任务应该只说明相关事项：Domain、Flow/State、Origin/Lineage、Event、
Permission/Safety、Action、UI/Performance、失败恢复。AI 或 Automation 未参与时
可以一句话说明或省略无关项。已有设计明确时引用，不重复写整套架构。

For medium/high risk, explain relevant domain, flow/state, origin, events, permissions/safety,
actions, UI/performance, and recovery. When AI or automation does not participate, omit unrelated
items or use one sentence. Reference established design rather than rewriting the architecture.

**MUST** 遵守当前明确决策门。用户授权完成一个范围时，包括其正常实现、合理的内部
选择和必要验证；历史“逐段授权”记录不覆盖后续一次性授权。
**SHOULD** 只为长期且有实质取舍的决定写 ADR，如所有权、兼容策略、安全边界、
运行模型、核心存储或重要依赖。普通 Bug、命名、局部重构无需单独 ADR。

**MUST** honor active explicit gates. Authorization for a scope includes normal implementation,
reasonable internal choices, and necessary verification; historical stage-by-stage records cannot
override later combined authorization. **SHOULD** reserve ADRs for durable trade-offs in ownership,
compatibility, safety, execution, storage, or major dependencies, not every bug or local refactor.

仅当现有授权无法解决实际冲突时请求决定；说明冲突、影响和推荐方案。
SHOULD 的合理例外记录理由即可，不自动升级为批准流程。

Seek a decision only when existing authorization cannot resolve a real conflict. Explain the
conflict, impact, and recommendation. A justified SHOULD exception needs a reason, not an approval ritual.

## 3. 风险相称的验证 / Proportionate verification

**MUST** 验证实际改变的行为与关键回归；报告执行证据，明确区分未运行、自动化通过、
源码桌面通过、打包通过与用户签收。不得把单元测试通过扩展成真实资料或异机验收。

**MUST** verify changed behavior and key regressions, report evidence, and distinguish unrun checks,
automated success, source-desktop success, packaged success, and user acceptance. Unit tests do
not establish real-data or cross-machine acceptance.

- 文档/文案：校验 UTF-8、链接、术语、入口与规范一致性；不需要为此运行完整应用测试。
- 领域/Action：覆盖不变量、合法与非法状态、错误和重复/过期请求。
- Handler：覆盖共同契约、嵌套、损坏、密码、不支持、边界和安全合成 Fixture。
- Schema/Recovery/版本：覆盖备份、升级、事实保留、中断窗口、补偿与重启恢复。
- 路径安全：覆盖 Traversal、Windows 名称、大小写碰撞、Link/Reparse 与资源上限；
  复杂名称/解析边界可以增加属性测试或 Fuzz，按风险安排。
- UI/性能/打包：验证用户闭环、后台响应、取消；按相关基准或发布清单执行。

- Documents/copy: check UTF-8, links, terms, entry points, and rule consistency; no full application suite is required.
- Domain/actions: cover invariants, legal/illegal states, errors, duplicate/stale requests.
- Handlers: cover shared contracts, nesting, corruption, passwords, unsupported cases, limits, and safe synthetic fixtures.
- Schema/recovery/versions: cover backup, migration, fact preservation, interruption, compensation, and restart recovery.
- Paths: cover traversal, Windows names, case collisions, links/reparse points, and resource limits; add property/fuzz tests when justified.
- UI/performance/package: verify the user loop, responsiveness, cancellation, and relevant benchmark/release checklist.

**SHOULD** 默认使用合成且可提交的资料。真实业务 Fixture 的读取、保留、外发和提交
须分别有适当授权；不得因测试需要推定可公开。测试关注外部可观察行为，不逐行镜像实现。
相关检查通过后，仅在新改动、失败或未解决风险出现时扩大验证。

**SHOULD** default to synthetic committable fixtures. Real fixture access, retention, transmission,
and committing require appropriate authorization; testing does not imply publication permission.
Test observable behavior rather than mirroring implementation. Expand checks after success only
when changes, failures, or unresolved risks justify it.

## 4. 完成说明 / Completion report

先说明结果，再给出与风险相称的变更、验证和限制。没有领域/状态/事件改动时不强制
逐项填“无”。高风险改动补充失败与恢复证据；未完成的人工验收必须显式标记。
新技术债务只报告具体影响、原因与处理条件，不为每次任务编造一项。

Lead with the result, then proportionate changes, verification, and limits. Do not fill every
unaffected domain/state/event field with “none.” High-risk changes include failure/recovery
evidence and identify pending manual acceptance. Report concrete new debt rather than inventing it.

## 5. 文档与维护 / Documents and maintenance

**MUST** 使用真实存在的相对链接并检查路由；规范变更同步中英文，中文为准。
阶段和授权只更新 CURRENT_SCOPE；规划索引只负责当前/历史文档导航。
更新入口或文件结构时同步 AGENTS、贡献指南和对应索引，不能保留失效章节引用。

**MUST** use existing relative link targets and verify routes. Update both languages for normative
changes, with Chinese authoritative. Update phase/authorization in CURRENT_SCOPE and use planning
indexes for navigation. Entry-point changes update AGENTS, contribution guidance, and relevant
indexes without obsolete section references.

**MUST NOT** 随规则整理自动更改运行时行为、Schema、依赖、版本或签收状态。
发现既有实现差距时记录具体待办，相关开发授权到达后处理。

**MUST NOT** use rule maintenance to silently alter runtime behavior, schemas, dependencies,
versions, or acceptance status. Record concrete implementation gaps for relevant authorized work.
