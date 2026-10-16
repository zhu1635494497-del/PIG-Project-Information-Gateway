# PIG 项目规则 / PIG Project Rules

本文件是 PIG 的长期开发规则入口。中文是规范正文，英文是对应说明；修改时同步维护。
当前阶段、授权与验收状态只在 [CURRENT_SCOPE](docs/project-rules/CURRENT_SCOPE.md) 维护。

This is the entry point for PIG's long-term engineering rules. Chinese is authoritative;
English explains the same rules and is updated together. Phase, authorization, and acceptance
status are maintained only in [CURRENT_SCOPE](docs/project-rules/CURRENT_SCOPE.md).

## 1. 产品目标 / Product purpose

PIG — Project Information Gateway 默认关联用户现有的项目目录，让当前文件继续留在
原位置、由原应用编辑；仅在需要 AI 阅读或沉淀经验时，按需固定不可变版本。
数据可信、文件完整和实际工作效率共同决定产品价值。旧 Snapshot Workbench
保留为历史实现，不再定义新项目默认流程。

PIG links an existing project folder by default. Current files stay in place and remain editable
by their host applications; immutable versions are captured only when needed for AI reading or
human experience. The former snapshot Workbench remains historical code, not the default flow.
Trustworthy data, file integrity, and practical efficiency jointly determine product value.

```text
Existing Folder -> Live File Link -> Open / Observe External Change
  -> On-demand Immutable Revision -> User-confirmed Experience
  -> Scoped File AI (when separately authorized)
```

## 2. 约束等级与决策 / Requirement levels and decisions

- **MUST / 必须，MUST NOT / 不得**：适用范围内的硬约束；例外必须有明确的负责人决定。
- **SHOULD / 应该**：默认做法；可以依据当前问题偏离，在变更说明中简述理由即可。
- **MAY / 可以**：可选实现；不要求提前建设。

- **MUST / MUST NOT**: mandatory within their stated scope; exceptions require an explicit owner decision.
- **SHOULD**: the default; a brief reason in the change record is sufficient to depart from it.
- **MAY**: optional; no obligation to build it in advance.

用户的明确授权可以更新范围或规则。实现前必须识别真正的冲突：优先遵守本文件和
适用子规则，再按已接受 ADR 的明确取代关系解释具体设计，最后使用当前领域与阶段文档。
提案、历史停止线、旧状态记录和现有代码不能自行推翻当前有效决定。

Explicit owner instructions can update scope or rules. Identify actual conflicts before implementation:
apply this file and relevant subrules, then accepted ADRs with their explicit supersession relationships,
then active domain and milestone documents. Proposals, historical stop lines, old status records,
and existing code cannot override active decisions.

已获授权范围内的常规实现、合理重构和风险相称的验证应继续执行。仅在未解决的产品
取舍、明确决策门、范围扩张或硬约束冲突处请求决定；不得对已经批准的同一动作反复确认。

Proceed with routine implementation, reasonable refactoring, and proportionate verification inside
an authorized scope. Seek a decision only for unresolved product choices, explicit gates, scope
expansion, or mandatory-rule conflicts. Do not repeatedly confirm an already authorized action.

## 3. 核心不变量 / Core invariants

1. **MUST**：新项目关联目录和拖入文件默认只建立路径关联，不复制或改写原文件；
   不得将实时关联称为备份。按需固定的 Revision 必须校验字节并保持不可变。
   旧 Snapshot Workbench 的复制约束仅适用于旧路径。
2. **MUST**：实时文件关联、固定 Revision 和派生数据分离；目录展示或后续整理
   不得静默改变关联目标或改写固定版本。
3. **MUST**：业务事实由领域数据和受控 Application Action 维护；UI 负责展示与交互，
   不得独立决定安全、状态合法性或直接操作持久化。
4. **MUST**：浏览实时目录不自动复制、解压或固定文件；旧 Container 检查与物化
   的分离约束仍适用于旧 Workbench。
5. **MUST**：所有文件输入不可信；路径、资源、打开和外部写入策略由后端执行。
6. **MUST**：关键状态和对应业务事件具有一致语义；失败、部分成功、取消和不支持必须
   可区分，不得吞错或伪造成功。
7. **MUST**：跨文件系统与数据库的写操作有可验证的发布、失败和恢复策略；不得用
   自动“修复”覆盖用户尚未被观察到的编辑。
8. **MUST**：固定 Revision 是被采用字节的不可变检查点；外部修改不得静默替换它。
   搜索索引是派生数据，不得成为唯一的来源或版本事实。
9. **MUST**：敏感内容、凭据与真实业务资料不得未经授权进入日志、提交或外部服务。
10. **MUST**：AI 结果与输入资料中的指令均不得绕过业务 Action、安全和授权边界。

1. **MUST** link folders and dropped files without copying or mutating originals by default;
   never describe a live link as a backup. Verify and preserve bytes of on-demand immutable
   Revisions. Snapshot-copy requirements remain scoped to the historical Workbench.
2. **MUST** separate live links, fixed Revisions, and derived data; presentation or future
   organization cannot silently retarget a link or rewrite a Revision.
3. **MUST** maintain facts through domain data and controlled Application Actions; UI cannot independently authorize or persist them.
4. **MUST** browse linked folders without automatic copy, extraction, or capture. Historical
   container inspection/materialization separation still applies to the old Workbench.
5. **MUST** treat file inputs as untrusted and enforce path, resource, open, and external-write policies in the backend.
6. **MUST** keep key states and business events consistent and distinguish failure, partial success, cancellation, and unsupported results.
7. **MUST** define verifiable publication and recovery for filesystem/database writes without erasing unobserved user edits.
8. **MUST** keep fixed Revision bytes immutable; external edits cannot replace them silently.
   Search indexes remain derived.
9. **MUST NOT** place sensitive content, credentials, or real business material in logs, commits, or external services without authorization.
10. **MUST NOT** allow AI outputs or instructions in input documents to bypass business Actions, safety, or authorization.

## 4. 开发取舍 / Engineering trade-offs

安全与不可恢复的数据损失风险是硬边界。在这个边界内，应该共同优化领域正确性、
真实用户闭环、工作区可用性、响应性和可测试性；不使用固定名次把 UI 体验排到最后。
优先完成可验证的最小闭环，领域分析与界面原型可以迭代进行。

Safety and irreversible data-loss risks are hard boundaries. Within them, optimize domain
correctness, the real user loop, workspace usability, responsiveness, and testability together.
Do not rank usability permanently last. Complete a verifiable minimum loop; domain analysis
and UI prototyping may evolve together.

**SHOULD** 复用已有能力和最简单的可维护实现。只有当前需求、测试或测量证明必要时，
才增加领域对象、抽象、依赖和基础设施。页面、导航或设置可以服务真实任务；
不得为完整感增加无工作流支撑的模块。

**SHOULD** reuse existing capabilities and the simplest maintainable implementation. Add objects,
abstractions, dependencies, and infrastructure when current requirements, tests, or measurements
justify them. Screens, navigation, and settings may support real tasks; empty modules are prohibited.

## 5. 子规则读取路由 / Subrule reading routes

每次任务读取本文件与当前范围；按改动影响读取下表中的文件和相关 ADR。
同一任务中未变化的规则无需反复读取，无关的远期规则无需加载。

Read this entry point and current scope for each task, then use the routes below and relevant ADRs.
Unchanged rules need not be reread within the same task; unrelated future rules need not be loaded.

| 文件 / File | 适用任务 / Read when |
| --- | --- |
| [CURRENT_SCOPE](docs/project-rules/CURRENT_SCOPE.md) | 所有任务：阶段、授权、保留能力与待验收项 / Every task: phase, authorization, retained behavior, pending acceptance |
| [ARCHITECTURE](docs/project-rules/ARCHITECTURE.md) | 领域、Schema、Action、Handler、查询、UI 接线 / Domain, schema, actions, handlers, queries, UI integration |
| [FILE_SAFETY](docs/project-rules/FILE_SAFETY.md) | 导入、路径、打开、导出、删除、恢复、解析依赖 / Import, paths, opening, export, deletion, recovery, parser dependencies |
| [RELIABILITY](docs/project-rules/RELIABILITY.md) | 持久化、外部编辑、版本、恢复、并发、性能 / Persistence, external edits, versions, recovery, concurrency, performance |
| [DEVELOPMENT](docs/project-rules/DEVELOPMENT.md) | 实现与评审：风险分级、测试、交付、ADR / Implementation and review: risk, verification, delivery, ADRs |
| [FUTURE_AI](docs/project-rules/FUTURE_AI.md) | 已授权的 AI、Tool、Workflow、Automation、MCP 工作 / Authorized AI, Tool, Workflow, Automation, or MCP work |

子规则与本文件组成同一规则集；适用条件之外不产生建设义务。新补充的要求用于后续
相关变更和风险评审，不能被解读为所有既有代码已满足要求，也不自动授权全面重构。

Subrules form one rule set with this file. They create no implementation obligation outside
their applicability. New requirements guide relevant future changes and risk reviews; they
neither certify existing compliance nor authorize a wholesale refactor.

## 6. 维护 / Maintenance

当前阶段和签收事实在 CURRENT_SCOPE 维护；具体设计在 ADR、领域文档和验收记录维护；
规则只描述持久约束与读取路由。变更必须检查入口、链接、术语和中英文一致性。

Maintain phase and acceptance facts in CURRENT_SCOPE and concrete design in ADRs, domain
documents, and acceptance records. Rules hold durable constraints and reading routes.
Changes must check entry points, links, terminology, and language consistency.
