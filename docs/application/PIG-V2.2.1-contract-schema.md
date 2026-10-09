# V2.2.1 Context Pack 契约与 Schema / Context Pack Contract and Schema

- 状态：V2.2.1 已实现并通过自动测试；V2.2.2–V2.2.4 随后获授权 / Status: V2.2.1 implemented and tested; V2.2.2–V2.2.4 subsequently authorized
- 日期：2026-10-08 / Date: 2026-10-08
- 决策：`ADR-026` 的 D120-A 至 D126-A / Decisions: D120-A through D126-A in `ADR-026`

## 范围与停止线 / Scope and stop line

本阶段只建立领域契约、SQLite 关系表、Repository 和只读 Pack Plan Action。
Plan 告诉调用者“拟交付哪些固定 Revision、如何分组、预估多少字节”，但不代表
磁盘预检通过，也不产生导出包或 Export 历史。V2.2.2 才负责重新验证对象字节、
目标与容量，生成包并原子发布。V2.2.3 才接入 ZIP 和 UI。

This stage adds domain contracts, SQLite relational tables, repositories, and
a read-only Pack Plan Action only. The plan identifies fixed Revisions,
grouping, and estimated bytes; it does not certify physical preflight or
create a pack or export history. V2.2.2 must revalidate object bytes,
destination, and capacity before atomic publication. V2.2.3 adds ZIP and UI.

## 数据流 / Data flow

`get_context_pack_plan` 读取 Project、Active Context Items、READY Revisions、
AVAILABLE Content Objects、Active Sections/Placements、Item Annotation 和 Workspace
来源信息。默认选择全部 Active Item 的当前 Revision；可显式选择某些 Item 的历史
READY Revision。结果包括确定性的 `plan_fingerprint`、每个 Item 一条文件 Entry、
用途/人工说明快照、多 Section 归属、空 Section、必要时的虚拟 `Unsectioned`、
Freshness 和警告。查询不推进 `context_revision`，不写文件、数据库或 Event。

`get_context_pack_plan` reads the Project, active Context Items, READY
Revisions, AVAILABLE Content Objects, active Sections/Placements, Item
Annotations, and Workspace origin. It defaults to each active Item's current
Revision and permits explicit historical READY choices. The result includes a
deterministic `plan_fingerprint`, one file Entry per Item, purpose/human-guidance
snapshots, multiple Section memberships, empty Sections, virtual `Unsectioned`
when needed, Freshness, and warnings. The query does not advance
`context_revision` or write files, database rows, or Events.

## 关系与状态 / Relationships and state

Migration `0012_context_pack_contract` 增加四张表：

Migration `0012_context_pack_contract` adds four tables:

| 表 / Table | 职责 / Responsibility |
| --- | --- |
| `context_pack_exports` | 一次交付尝试的格式、目标、操作者、上下文版本、状态和结果；one delivery attempt, format, destination, actor, context version, status, and outcome. |
| `context_pack_entries` | 每个选定 Item 一条固定 Revision 引用及文件/说明快照；one fixed Revision reference and file/guidance snapshot per selected Item. |
| `context_pack_sections` | 交付时的 Section 快照，包括空 Section 和虚拟 `Unsectioned`；Section snapshots including empty Sections and virtual `Unsectioned`. |
| `context_pack_placements` | Entry 与 Section 的显式多对多关系；explicit many-to-many relationship between Entries and Sections. |

状态词汇为 `PENDING`、`PREFLIGHTED`、`RUNNING`、`SUCCEEDED`、`FAILED`、
`CANCELLED_AT_SAFE_POINT`。Schema 限制成功状态必须有完成时间和发布 Hash；
状态迁移、预检 Token、Event 和执行 Action 将在 V2.2.2 完成。Repository 提供
乐观状态更新和重启后查询，但 V2.2.1 不启动任何 Export。

The status vocabulary is `PENDING`, `PREFLIGHTED`, `RUNNING`, `SUCCEEDED`,
`FAILED`, and `CANCELLED_AT_SAFE_POINT`. The schema requires a completion time
and published hash for success. V2.2.2 adds transition policy, preflight
token, Events, and execution Actions. The repository supports compare-and-set
updates and reopen queries, but V2.2.1 starts no Export.

约定的合法迁移是 `PENDING → PREFLIGHTED → RUNNING → SUCCEEDED`；预检、执行
过程中可进入 `FAILED`，在安全点可进入 `CANCELLED_AT_SAFE_POINT`。三个终态不得
再迁移。V2.2.1 仅固定状态词汇与乐观更新接口，不提供状态变更 Action；V2.2.2 必须
在 Application 层实施合法迁移和结构化 Event，不得让 UI 直接更新状态。

The intended transitions are `PENDING → PREFLIGHTED → RUNNING → SUCCEEDED`.
Preflight or execution may enter `FAILED`; safe points may enter
`CANCELLED_AT_SAFE_POINT`. All three terminal states are final. V2.2.1 fixes
the vocabulary and compare-and-set repository interface only; V2.2.2 must
enforce transitions and structured Events in Application, never through UI SQL.

复合外键保证 Export、Entry、Revision、Section/Placement 归属同一 Project，且 Entry
引用的 Revision 属于其 Item。唯一约束保证每 Export 每 Item 仅一份字节、相对路径和
序号不冲突；成功 Export 的 Revision 在清理候选查询中受保护。Entry/Section/
Placement 是未来成功发布时的历史快照，不随之后的 Context 编辑变化。

Composite foreign keys enforce same-Project ownership and ensure an Entry's
Revision belongs to its Item. Unique constraints allow one byte copy per Item
and prevent path/ordinal collisions. Successful Export Revisions are protected
from cleanup. Entry/Section/Placement rows are historical snapshots at future
successful publication and do not change with later Context edits.

## 安全和后续执行约束 / Safety and later execution constraints

Plan 中的相对路径使用 `files/<item-id>/<safe-name>`；不会输出 Source/Working 的
绝对物理路径。它只检查数据库中的对象状态，不读取对象文件或验证 Hash；因此
V2.2.2 必须再次校验实际字节。外部目标路径不会在本阶段写入。未来执行应仅在
成功发布的同一数据库事务中固定 Entry/Section/Placement 与 `SUCCEEDED` 状态；
失败/取消不得留下引用并阻断 Revision 清理。发布与数据库提交之间的崩溃窗口
也须在 V2.2.2 设计恢复策略。

Plan paths use `files/<item-id>/<safe-name>` and expose no absolute Source or
Working path. The plan checks database availability only, not physical bytes
or hashes; V2.2.2 must reverify them. No external destination is written in
this stage. Future execution should freeze Entry/Section/Placement and
`SUCCEEDED` in one database transaction after successful publication; failed
or cancelled attempts must leave no references that obstruct Revision cleanup.
V2.2.2 must also address the crash window between filesystem publication and
database commit.

后续 V2.2.2–V2.2.4 的实现与验收记录见 `PIG-V2.2-implementation-acceptance.md`；
本文件保留 V2.2.1 的阶段边界，不再代表当前授权门。

The later V2.2.2–V2.2.4 implementation and acceptance record is in
`PIG-V2.2-implementation-acceptance.md`. This document preserves the V2.2.1
stage boundary and no longer defines the current authorization gate.

## 测试与验收 / Tests and acceptance

覆盖迁移与 ORM 一致性、Plan 的版本选择和不写入、空 Section/Placement/说明快照、
历史重启读取、同 Item Revision 外键以及成功引用保留。相关回归测试 19 项通过，
补充空 Section 断言后的 V2.2.1 两项测试再次通过；`compileall`、Alembic head 与
`git diff --check` 通过。本阶段不进行人工桌面或异机包验收。

Tests cover migration/ORM parity, plan version choice and no writes, empty
Section/Placement/guidance snapshots, reopen reads, same-Item Revision foreign
keys, and successful-reference retention. Nineteen related regression tests
passed; both V2.2.1 tests passed again after adding the empty-Section assertion.
`compileall`, Alembic head, and `git diff --check` passed. This stage has no
manual desktop or cross-machine pack acceptance.
