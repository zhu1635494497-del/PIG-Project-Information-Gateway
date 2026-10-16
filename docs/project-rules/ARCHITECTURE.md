# 架构与领域规则 / Architecture and Domain Rules

适用：领域模型、Schema、Application Action、Handler、查询和 UI 接线。
约束等级与解释顺序见[主规则](../../PIG%20Project%20Rules.md)。

Applies to domain models, schemas, Application Actions, handlers, queries, and UI integration.
Requirement levels and authority are defined in the [main rules](../../PIG%20Project%20Rules.md).

## 1. 按当前行为建模 / Model current behavior

**MUST** 明确当前改动的对象身份、所有权、核心关系与不变量。已有独立生命周期、
业务约束或核心查询关系的概念应该显式建模；仅因未来可能需要权限或日志，不要求新建实体。
核心多对多关系使用显式关系模型，不得用逗号分隔 ID 或无约束 JSON 代替。

**MUST** define affected identity, ownership, relationships, and invariants. Concepts with a current
independent lifecycle, business constraint, or core queried relationship should be explicit models.
Possible future permissions or logging alone do not justify a new entity. Core many-to-many
relationships use explicit models, never delimited identifiers or unconstrained JSON.

**MAY** 使用有 Schema 或边界校验的 JSON 存放可变 Metadata、解析器原始结果、外部
Payload 和扩展字段。Enum、Value Object、DTO 和简单函数可以表达无需独立身份的概念。

**MAY** use schema-validated or boundary-validated JSON for variable metadata, raw parser results,
external payloads, and extensions. Enums, value objects, DTOs, and simple functions may represent
concepts without independent identity.

## 2. 所有权与路径 / Ownership and paths

新关联项目 **MUST** 区分 Linked Root、Live File Link、Observed Fingerprint、
Fixed Revision、Confirmed Experience 和 Derived Data。旧 Workbench 的 External Input、
Original Snapshot、Source Node、Workspace Item、Working Artifact、Context Item 仍是历史模型，
不得作为新关联项目必须复制文件的理由。

New linked projects **MUST** distinguish Linked Root, Live File Link, Observed Fingerprint,
Fixed Revision, Confirmed Experience, and derived data. External Input, Original Snapshot,
Source Node, Workspace Item, Working Artifact, and Context Item remain historical Workbench
concepts, not a requirement to copy files in the new path.

**MUST** 分离当前外部绝对路径、项目内固定对象路径及 UI 展示路径。内部身份使用
稳定 ID；根目录下相对路径只在重验根边界与非 Link 后读取。文件移动或改名使旧路径
关联显式失效，不静默追踪到其他文件。旧 Context Placement 语义仅适用于旧模型。

**MUST** separate current external absolute path, project-owned fixed-object path, and UI display
path. Stable IDs identify records; relative paths under a linked root are revalidated before
reads. Moves or renames make old path links explicitly stale rather than silently following
another file. Historical Context Placement semantics remain scoped to the old model.

## 3. 依赖与业务边界 / Dependencies and business boundaries

**MUST** 由 Application Action 编排写入、风险检查与事务，由 Query 返回展示需要的
类型化结果。UI 不执行 SQL、解压、Hash 或最终安全判定；Domain 不依赖 UI、
第三方解析器或具体数据库实现。Infrastructure 承担文件系统、数据库和解析适配。

**MUST** orchestrate writes, risk checks, and transactions through Application Actions and return
typed presentation results through queries. UI performs no SQL, extraction, hashing, or final
safety authorization. Domain has no dependency on UI, third-party parsers, or concrete database
implementations; infrastructure supplies those adapters.

**SHOULD** 按上述依赖方向组织代码；不要求每个小功能都创建四层目录、接口和转发类。
只有替换需求、隔离需求或测试收益明确时才增加抽象。开发可直接使用内部函数；
“Agent 只能通过 Tool”指未来产品 Agent 的运行时权限边界，不限制正常的仓库实现工作。

**SHOULD** follow these dependency boundaries without requiring four directories, interfaces,
and forwarding classes per small feature. Abstract when replacement, isolation, or testability
justifies it. Developers may use internal functions; the future Agent Tool restriction concerns
product runtime permissions, not normal repository implementation.

## 4. Handler 与处理控制 / Handlers and processing control

**MUST** 通过共同的类型化能力边界封装格式识别、结构检查、子项枚举与目标物化。
Processor 负责路由、限制、注册关系和状态更新，不包含具体邮件或压缩格式解析细节。
检查与物化必须分离，临时内部 Container 字节受同一资源和清理策略约束。

**MUST** encapsulate detection, inspection, child enumeration, and target materialization behind
a shared typed capability boundary. The processor routes work, enforces limits, registers
relationships, and updates state without format internals. Temporary inner-container bytes
follow the same resource and cleanup policies; inspection remains separate from materialization.

**MUST** 有界遍历、限制实际资源消耗并提供安全取消点。**MAY** 使用显式栈、队列或
迭代器；不强制引入持久 Job、Broker、Pause/Resume 或分布式 Worker。
具体并发模型遵守已批准 ADR。

**MUST** bound traversal and actual resource use and expose safe cancellation points. **MAY** use
a stack, queue, or iterator; persistent jobs, brokers, pause/resume, and distributed workers are
not required. The execution model follows accepted ADRs.

## 5. Action 与扩展 / Actions and extensions

**MUST** 为跨业务边界的 Action 明确输入、结果、错误、读写副作用和重试语义；写操作
检查目标版本或其他有效并发条件。重复请求可以复用结果、明确拒绝或幂等执行，
不要求每个内部函数都携带 idempotency key。

**MUST** define inputs, results, errors, side effects, and retry semantics for business-boundary
Actions. Writes validate expected versions or equivalent concurrency conditions. Repeated
requests may reuse results, be rejected explicitly, or execute idempotently; every internal
function does not need an idempotency key.

**SHOULD** 复用现有导入、物化、打开和导出能力。只有当前使用者需要稳定接口时才
建立公共 Tool；未来可能使用 MCP 不构成提前封装所有函数的理由。

**SHOULD** reuse existing ingestion, materialization, opening, and export capabilities. Create
public Tools when current consumers need stable contracts, not merely because MCP may use them later.
