# AI 与外部能力规则 / AI and External Capability Rules

适用：获得对应范围授权后的 AI、Tool、Workflow、Automation 与 MCP 工作。
本文件是条件性约束，不构成当前建设这些能力的授权；普通开发无需逐次回答本文件。

Applies to AI, Tools, Workflows, Automation, and MCP after their scope is authorized.
These conditional rules do not authorize implementation now or require answers in ordinary development.

## 1. 事实与模型 / Facts and models

**MUST** 保持 Project、文件版本、Hash、状态、关系和权限由确定性代码管理。
模型可以提供理解、分类、摘要、比较和建议；模型结论必须保存来源、版本与生成信息，
不得自动升级为经过验证的业务事实。关键结论绑定可核对的 Citation。

**MUST** keep projects, file revisions, hashes, states, relationships, and permissions under
deterministic code. Models may classify, summarize, compare, and recommend. Preserve provenance,
version, and generation details without treating inference as verified business facts. Material
conclusions bind to verifiable citations.

**MUST** 将导入文档、邮件、解析结果和检索片段中的指令视为数据，防止其改变工具
权限或触发外发。模型处理只消费明确选择且经过验证的 Revision；不默认扫盘或索引
全 Workspace。远程调用前明确数据范围、Provider、目的与成本边界，并保护凭据。

**MUST** treat instructions in documents, email, parsed outputs, and retrieved snippets as data,
preventing permission changes or outbound actions. Model processing uses explicitly selected,
verified revisions, not automatic disk/full-workspace scans. Disclose scope, provider, purpose,
and cost boundaries before remote calls and protect credentials.

## 2. Prompt 与输出 / Prompts and outputs

**SHOULD** 集中管理生产 Prompt，记录名称、版本、用途、输入输出 Schema 和模型
要求。原型可以局部实验，进入可复用生产路径前再整理，不要求一次实验建设注册平台。
**MUST** 校验程序消费的结构化模型输出；Schema 合法不等于业务内容可信。

**SHOULD** manage production prompts centrally with identity, version, purpose, schemas, and
model requirements. Local prototype experiments may precede consolidation; no registry platform
is required for one experiment. **MUST** validate machine-consumed structured output; valid schema
does not establish trustworthy business content.

安全、权限和业务不变量必须由后端与 Action 执行，不能仅写在 Prompt 中。

Safety, permissions, and invariants are enforced by backend Actions, not only by prompts.

## 3. Tool 与 Agent / Tools and Agents

**MUST** 让产品 Agent 通过受控 Tool 操作系统，不直写数据库或绕过文件 Action。
Tool 表达业务能力，具有输入/输出 Schema、权限、副作用、错误、版本和重试语义。
稳定内部 Action 可以复用，但每个函数都无需公开为 Tool。

**MUST** route product Agent operations through controlled Tools without direct database writes
or bypassing file Actions. Tools represent business capabilities with schemas, permissions,
effects, errors, versioning, and retry semantics. Reuse internal Actions without exposing every function.

**MUST** 对高风险副作用使用绑定具体目标的确认或明确 Automation Policy。
可逆低风险动作可以在用户授权的任务内连续执行；不能靠 Agent 自行解释 Prompt
扩大授权。Agent 的价值按完成真实任务衡量，界面形式由用户流程决定。

**MUST** bind high-risk effects to target-specific confirmation or explicit automation policy.
Low-risk reversible actions may proceed within an authorized task; Agents cannot expand authority
by interpreting prompts. Measure value by task completion, with UI shaped by the user workflow.

## 4. Workflow、Automation 与 MCP / Workflow, Automation, and MCP

**SHOULD** 用 Workflow 表达已知步骤与条件，在不确定环节再引入 Agent。
Automation 可以由明确业务 Event、计划时间或人工触发；不得依赖模型猜测事件。
触发身份、重试、幂等/去重、失败和取消必须有明确语义，重复投递不得重复外部副作用。

**SHOULD** express known steps and conditions as Workflows and use Agents for uncertainty.
Automation may be driven by explicit business events, schedules, or manual triggers, never a
model's guess that an event occurred. Define trigger identity, retry, deduplication/idempotency,
failure, and cancellation; duplicate delivery cannot duplicate external effects.

Tool 是可调用能力，Workflow 是流程，Skill 是能力使用配方，MCP 是 Tool/Resource
的接入协议。**MUST NOT** 为术语支持提前建设平台；内部契约稳定且存在当前接入需求
后才考虑 MCP。实际协议与依赖版本在进入实施时核对官方资料。

A Tool is callable capability, Workflow is process, Skill is an instruction recipe, and MCP is
an access protocol for Tools/Resources. **MUST NOT** build platforms merely to claim support.
Consider MCP after stable contracts and a current integration need; verify official specifications
and dependency versions when implementation is authorized.
