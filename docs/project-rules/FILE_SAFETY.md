# 文件安全与隐私规则 / File Safety and Privacy Rules

适用：导入、路径、Container、物化、打开、导出、删除、恢复和解析依赖。
本文件约束相关变更；既有实现是否满足要求必须以测试与评审为证。

Applies to imports, paths, containers, materialization, opening, export, deletion, recovery,
and parser dependencies. Compliance of existing implementations requires tests and review evidence.

## 1. 输入与 Snapshot / Inputs and snapshots

**MUST** 将所有文件、归档成员名、邮件字段和 Metadata 视为不可信。新关联流程只
记录外部路径，不在建立关联时复制或 Hash 全部文件。按需固定版本时才执行受控 Copy
+ SHA-256，验证稳定性、容量与发布结果后报告完成；不稳定、不可读或空间不足须明确失败。
旧 Snapshot Import 的复制与 Hash 规则仅适用于旧 Workbench。

**MUST** treat files, archive members, email fields, and metadata as untrusted. New links record
paths without copying or hashing every file. On-demand capture performs controlled copy plus
SHA-256 and verifies stability, capacity, and publication before success. Unstable or unreadable
files and insufficient space fail explicitly. Historical snapshot import retains its old rules.

## 2. 路径与 Windows 边界 / Paths and Windows boundaries

**MUST** 在文件操作处校验最终受管位置和目标类型；不得仅靠字符串前缀或 UI 校验。
拒绝 Traversal、绝对成员路径、盘符/UNC 注入和超出受管根的解析结果。Symlink、
Junction、Reparse Point 与其他非普通文件按明确策略拒绝或受控处理，不默认跟随。

**MUST** validate the final managed destination and target type at the file-operation boundary,
not just by string prefix or UI checks. Reject traversal, absolute member paths, injected drive/UNC
paths, and resolutions outside the managed root. Links, junctions, reparse points, and non-regular
files require explicit handling and are never followed by default.

**MUST** 处理 Windows 保留名、尾随点/空格、大小写不敏感冲突、非法字符、ADS 语法
和路径长度限制。Unicode 名称碰撞必须具有确定语义；显示原名可以保留，安全转换
不得静默改变来源事实。同名处理和导出冲突遵守对应 ADR，不全局自动改名。

**MUST** handle Windows reserved names, trailing dots/spaces, case-insensitive collisions,
invalid characters, alternate-data-stream syntax, and path-length limits. Unicode collisions have
deterministic behavior. Original display names may remain visible; safe conversion never rewrites
origin facts. Duplicate/export policies follow the relevant ADR rather than universal auto-renaming.

## 3. 资源与解析器 / Resources and parsers

**MUST** 集中配置深度、数量、单文件/累计展开字节、临时磁盘与时间预算，并在实际
读取和输出时执行限制；不能只相信归档声明大小。子 Container 共享累计预算，不得
每层重置。超限、密码需求、损坏和不支持必须返回可区分结果。

**MUST** centralize depth, count, single/aggregate expanded bytes, temporary-disk, and time budgets.
Enforce them during actual reads and writes, not only against archive headers. Inner containers
share aggregate budgets. Limits, password requirements, corruption, and unsupported formats
have distinct outcomes.

**SHOULD** 对可能挂起或崩溃的第三方解析器评估隔离、超时与取消能力；线程/子进程
等具体方案仍由当前决策门确定。新依赖应评估真实 Fixture、许可证、Windows 打包、
资源和维护成本；不得仅为格式支持数量引入完整平台。

**SHOULD** assess isolation, timeout, and cancellation for parsers that can hang or crash. Concrete
thread/process choices remain subject to the active gate. Evaluate new dependencies with real
fixtures, licensing, Windows packaging, resource use, and maintenance cost.

## 4. 打开与外部写入 / Opening and external writes

**MUST** 在后端执行允许格式策略，再通过已批准的 OS 关联交接；不得借打开资料
执行任意命令。`FILE_OPENED` 只表示 OS Handoff，不表示用户编辑或保存已成功。

**MUST** enforce format policy before the accepted OS handoff and never turn opening material
into arbitrary command execution. `FILE_OPENED` means handoff, not successful editing or saving.

**MUST** 区分 Read、Project Write 和 External Write。导出由用户明确发起并校验目标；
V1 单文件覆盖按 ADR-018 确认，多选 ZIP/文件夹及 V2 Context Pack 按各自冲突策略
执行。缺失或不可读的 Working 文件不得静默退回 Original；Context Pack 不得退回
Working 或 Original。目标检查、计划失效和执行重验属于后端责任。

**MUST** distinguish reads, Project writes, and external writes. Export is user-initiated and
validates destinations. V1 single-file replacement follows ADR-018 confirmation; ZIP/folder and
V2 Context Pack follow their specific collision rules. Missing Working bytes never silently fall
back to Original, and Context Pack never falls back to Working or Original. The backend checks
targets, invalidates stale plans, and revalidates execution.

## 5. 删除、恢复与确认 / Deletion, recovery, and confirmation

**MUST** 对不可逆移除、覆盖用户修改、外发或权限变化显示真实影响并取得对应授权。
确认必须绑定目标和操作，执行时重验条件；过期预览不能授权不同字节或新增受影响对象。
已明确发起的普通整理和可逆操作不要求无差别二次确认。

**MUST** show actual impact and obtain appropriate authorization for irreversible removal,
overwriting user edits, external transmission, and permission changes. Confirmation binds to the
target and operation; revalidate conditions so stale previews cannot authorize different bytes
or additional affected objects. Ordinary explicit organization and reversible actions do not
require blanket second confirmations.

顶层 Import Undo 的范围遵守 ADR-019。**MUST** 校验全部受影响字节、同批隔离和当前
引用/保留约束；若现有 ADR 未定义新的跨 Context 影响，不得静默级联删除，应在该
具体功能任务中解决冲突。Recovery 不自动覆盖已知 Working 文件或版本槽。

Top-level import undo follows ADR-019. **MUST** validate affected bytes, sibling isolation,
and active references/retention constraints. New cross-Context effects not defined by existing
ADRs cannot trigger silent cascading deletion; resolve them in the relevant feature task.
Recovery never automatically replaces known Working files or version slots.

## 6. 敏感数据与临时文件 / Sensitive data and temporary files

**MUST NOT** 将正文、密码、API Secret、完整外部 Payload 或可识别客户的资料写入
Debug Log、业务 Event、提交或未授权远程服务。诊断使用安全错误码和最少 Metadata；
必要的项目内部来源路径可以保留，导出诊断时须脱敏。

**MUST NOT** place document text, passwords, API secrets, full external payloads, or identifying
client data in debug logs, business events, commits, or unauthorized remote services. Use safe
error codes and minimal metadata. Necessary internal origin paths may remain, but exported
diagnostics require redaction.

**MUST** 明确缓存、临时文件和正文索引的存放、生命周期与清理边界。失败或取消只清理
可证明属于本操作的可再生残留；未知字节或未提交删除的字节遵守 Recovery 分类，
不得当垃圾直接删除。没有经过验证的安全擦除能力时，不声称文件无法恢复。

**MUST** define locations, lifecycle, and cleanup boundaries for caches, temporary files, and text
indexes. Failure/cancel cleanup covers only provably operation-owned reproducible residue.
Unknown bytes and uncommitted removals follow recovery classification, never generic deletion.
Do not claim irrecoverable erasure without verified capabilities.
