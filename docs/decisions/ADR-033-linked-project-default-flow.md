# ADR-033：现有目录关联成为默认主流程 / Linked Existing Folder as the Default Flow

- 状态：已接受；负责人于 2026-10-16 明确授权规划及最小实现 / Status: Accepted; owner authorized design and minimum implementation on 2026-10-16
- 范围：新建项目；旧项目与旧代码保留，不自动迁移 / Scope: newly created Projects; old Projects and code remain without automatic migration

## 背景与取代关系 / Context and supersession

旧 Workbench 通过 Import、Original Snapshot 与 Working Copy 解决复杂资料处理，但让
现有 Windows 项目目录变成另一个副本。新默认模式以用户已经工作的目录为唯一当前文件
位置。此决定明确取代 ADR-010 的新项目默认导入、ADR-024 D101/D103、ADR-025 D118
中“必须先复制到 Workbench 才可工作”的前提。ADR-030 的旧项目不默认迁移继续有效。
ADR-028 的“AI 草稿不是人工事实、经验须绑定固定依据”继续有效；其他历史条款仅适用于
旧 Workbench。旧代码和 Git 历史不删除，不以旧运行时的存在推定新模型兼容义务。

The snapshot/working-copy Workbench solved nested-file processing but duplicated the user's
existing folder. The new default treats that folder as the sole current-file location. This
supersedes ADR-010's default import and the copy-first premises in ADR-024 D101/D103 and
ADR-025 D118 for new Projects. ADR-030 still excludes default older-Project migration.
ADR-028's human confirmation and fixed-evidence rule remains. Other historical behavior stays
scoped to the old Workbench. Old code and Git history remain without implying compatibility.

## 决定 / Decisions

1. 新项目先选择一个现有普通 Windows 目录；PIG 元数据和固定版本存在独立的应用数据
   目录，不写入关联目录。Project 拥有稳定 ID、Linked Root 和独立 Schema 版本。
2. 当前文件是关联路径处此刻的字节。拖入额外文件只记录路径关联，不复制、不 Hash 全量
   目录、不自动创建固定版本。UI 展示和项目元数据不能称为原件备份。
3. 打开前、显式刷新时观察稳定 Fingerprint。检测到变化、缺失、不可读或路径不安全时
   返回不同状态；PIG 不跟踪 Host Application 的每次保存、不自动追踪 Save As、改名或移动。
4. 文件层 AI 阅读或沉淀经验之前，用户先对选定的当前文件按需固定不可变 Revision。
   固定是受控流式复制、SHA-256 校验和项目内发布。外部文件后续修改不会改写 Revision。
5. 对话或人工整理的经验初始为草稿；只有用户显式确认后才成为确认经验。确认记录
   明确引用固定 Revision ID 和 Hash，绝不把未经确认的 AI 文本提升为人工事实。
6. 首个闭环仅涵盖普通目录/普通文件、关联、打开、刷新、固定版本和一条人工确认经验。
   旧复杂 Container 能力选择性复用，不在此次重新承诺自动递归解压。文件层真实 AI
   外发仍遵守独立数据与 Provider Gate；本闭环无需外发即可验收。

1. New Projects select an existing ordinary Windows folder. PIG metadata and fixed Revisions
   live in separate app-data storage, never inside the linked folder. Project identity, root,
   and schema version are explicit.
2. A current file means the bytes now at its linked path. Dropping another file records a link,
   without copying, hashing the full tree, or auto-capturing. Neither UI nor metadata is a backup.
3. Before open and on explicit refresh, observe a stable fingerprint. Changed, missing,
   unreadable, and unsafe paths have distinct states. PIG does not track every Host save, Save As,
   move, or rename automatically.
4. Before file-level AI reads or experience capture, the user captures an immutable Revision
   on demand via bounded streaming copy, SHA-256 verification, and project-owned publication.
   Later external edits cannot rewrite it.
5. AI- or human-organized experience starts as draft. Only explicit user confirmation produces
   confirmed experience with a fixed Revision ID and hash; AI text is never silently promoted.
6. The first loop covers ordinary folder/files, link, open, refresh, capture, and one confirmed
   human experience. Complex Container support may be reused later. Real AI egress retains its
   separate data/provider gate and is not needed for this acceptance.

## 安全、失败与恢复 / Safety, failure, and recovery

读取时重验根边界、普通文件类型与 Link/Reparse，禁止目录穿越。外部文件不由 PIG 写入。
固定前后比较稳定 Fingerprint；变化则失败，不发布错误 Revision。跨 SQLite 与对象存储
的捕获使用操作记录与受控 Staging；中断后标记需检查，不自动删除未知字节。元数据目录
与关联根严格区分。旧库不自动升级或静默重建。

Revalidate root containment, ordinary-file type, and Link/Reparse at each read; never traverse
out of root. PIG does not write external files. Compare stable fingerprints around capture; a
change fails without a false Revision. A capture operation record and controlled staging bridge
SQLite and object storage; interrupted operations require inspection rather than deleting unknown
bytes. Metadata storage is distinct from the linked root. Old databases are neither upgraded
nor silently rebuilt.

## 最小验收 / Minimum acceptance

用合成目录创建项目后，原目录无新增/修改文件；打开文件交给系统关联程序；外部修改后刷新
显示变化；固定版本后再修改原文件，Revision Hash/字节不变；草稿无法冒充确认经验，确认
经验引用固定版本；重启后状态仍可查询；缺失、Link、捕获中断与旧 Schema 均明确处理。

With a synthetic folder, Project creation leaves it untouched. OS association opens a file;
refresh detects an external edit; a fixed Revision stays byte-identical after another edit;
drafts are not confirmed and confirmed experience cites a Revision; restart preserves state;
missing files, links, interrupted captures, and unsupported old schemas have explicit outcomes.
