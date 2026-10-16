# V2.4 工作区交互修复与复测 / V2.4 Workspace Interaction Follow-up

## 范围 / Scope

本次针对人工验收到 B02 时发现的工作区问题：拖动撤销、展开状态、目标提示、文件夹
双击、版本按钮布局、右键重命名，以及 B01/B02 遇到 `RECOVERY_REQUIRED` 的引导。
不改变 Original、Source、Working 文件字节，也不新增自动恢复或静默删除。

This follow-up covers the Workspace issues found during manual acceptance through B02: move
undo, expansion state, destination guidance, folder double-click, version-button layout,
context-menu rename, and `RECOVERY_REQUIRED` guidance for B01/B02. It changes no Original,
Source, or Working bytes and adds no automatic recovery or silent deletion.

## 行为 / Behavior

- 拖动后可用“更多 → 撤销上次移动”或 `Ctrl+Z` 撤回最近一次移动；仅在项目与 Workspace
  Revision 未变化时有效。落点与原位置相同则不执行写入。撤销后活动记录只显示
  “已撤销移动”；底层追加事件仍保留移动与补偿事实，不删除历史。
- 树刷新保留已展开/折叠的文件夹；拖动悬停不自动展开。目标文件夹高亮，临时提示
  明确“放入文件夹”或“放在某项之前/之后”。双击文件夹只切换其展开状态。
- “回滚到上一版本”移到版本表下方，与刷新/恢复按钮同行。
- 右键“重命名”只修改工作区逻辑名称与导出名称；文件扩展名必须保持。来源名称和已
  生成的 Working 文件物理文件名不改变。`0017_workspace_rename_event` 记录重命名事件。
- 按 [ADR-030](../decisions/ADR-030-default-no-legacy-project-compatibility.md)，使用新建
  测试项目重新导入测试包；旧 Schema 项目明确拒绝，不自动升级或改写。新项目若遇到
  `RECOVERY_REQUIRED`，展示候选项与既有确认恢复流程，恢复后重试 B01/B02。

- The latest move can be undone through More → Undo last move or `Ctrl+Z`, only while the
  project and Workspace Revision are unchanged. A no-op drop writes nothing. The activity view
  shows “Move undone”; append-only underlying move and compensation events remain intact.
- Reload preserves expanded/collapsed folders; drag hover does not auto-expand them. The target
  folder is highlighted and a temporary hint distinguishes dropping inside from before/after.
  Double-click toggles a folder's expansion only.
- Rollback sits below the version table beside Refresh and Restore.
- Context-menu Rename changes the logical Workspace/export name only and preserves the file
  extension. Source names and already-materialized Working basenames remain unchanged.
  `0017_workspace_rename_event` records the action.
- Under [ADR-030](../decisions/ADR-030-default-no-legacy-project-compatibility.md), create a
  fresh test project and reimport the test kit. An old-schema project is rejected explicitly,
  not automatically upgraded or modified. If the fresh project reports `RECOVERY_REQUIRED`,
  review the candidates and confirm recovery before retrying B01/B02.

## 人工复测 / Manual retest

1. 关闭旧源码窗口，从当前源码重新启动；新建测试项目并重新导入测试包。旧项目保持
   原样。若新项目提示恢复，查看候选项并决定是否执行；不要跳过后继续写入。
2. B01：搜索 `项目简报`，双击结果打开；如果恢复刚完成，请重新双击。确认右侧
   “打开”也可成功交接系统程序。
3. B02：新建文件夹 `待确认`，拖入两个文件；观察目标提示，展开/折叠文件夹后再
   拖动一次，确认状态未被重置。故意拖错后按 `Ctrl+Z`，检查位置回到原处。
4. 右键重命名普通文件夹和一个文件（保留扩展名）；确认树、搜索、导出名称变化，
   来源名称与 Original 不变。打开“来源与版本”确认版本表完整可见。

1. Close the old source window, relaunch current source, create a new test project, and reimport
   the test kit. Leave the old project untouched. Review any recovery candidates in the new
   project before authorizing recovery; do not bypass a write block.
2. B01: search `项目简报` and double-click the result. Retry the double-click after recovery
   completes. Confirm the detail pane's Open action also hands off to the host application.
3. B02: create `待确认`, move two files into it, inspect destination guidance, and confirm
   expansion stays unchanged across moves. Deliberately misplace one file and press `Ctrl+Z`.
4. Rename an ordinary folder and one file from the context menu (preserve extension). Verify
   tree/search/export names while Source/Original stay unchanged, and inspect the version table.

自动化用例只证明合成资料与离屏 UI；此文档不宣称旧项目已迁移或人工复测通过。

Automated checks establish synthetic-data and offscreen-UI behavior only. This document does
not claim an old project has been migrated or manual retesting has passed.

## 后续人工验收反馈 / Subsequent manual-acceptance feedback

用户随后要求：右键在普通文件夹内新建子文件夹；拖到自身或原位置不报错、不增加 Revision；
单选 ZIP/7z Container View 按 [ADR-031](../decisions/ADR-031-expanded-container-view-export.md)
导出当前展开目录；Context 版本表默认选中当前 Revision，使 READY 版本的“提取所选
Revision”可直接点击。提取仍需用户主动按键；不会因默认选中而自动执行。

The owner subsequently requested child-folder creation from an ordinary folder's context menu;
no error or new revision for a self/same-position drop; export of a single ZIP/7z Container View
as its current expanded directory under [ADR-031](../decisions/ADR-031-expanded-container-view-export.md);
and default selection of the current Context Revision so Extract Selected Revision is available
when it is READY. Selection never starts extraction without an explicit user click.

复测：在文件夹右键新建子文件夹；把文件夹放回自身和原位置；分别单选 ZIP、7z 导出并
检查层级、当前修改字节及原包未变化；在 C04 打开核心文件并确认当前 READY Revision
高亮、按钮可点击、点击后内容提取成功。既有目录不得被合并或覆盖。人工结果仍须用户确认。

Retest: create a child from a folder's context menu; drop a folder on itself and its original
position; export ZIP and 7z individually and inspect hierarchy, current edited bytes, and
unchanged source archives; open a C04 Context Item and confirm the current READY Revision is
highlighted, the button is enabled, and an explicit click completes extraction. Existing
destination directories must not be merged or overwritten. Manual acceptance remains with the owner.

合成测试还发现：合法的已导入空文件夹拥有 `READY` Snapshot 根目录，但没有文件
Artifact；此前恢复扫描把它误判为孤立 Original。现在只把这种已登记的空 Snapshot 根
视为已知路径，未登记目录仍保留隔离候选。该修复不自动执行恢复或删除文件。

Synthetic testing also found that a valid imported empty folder has a `READY` Snapshot root
but no file Artifact. Recovery inspection previously mistook it for an orphan Original. The
inspector now recognizes only that registered empty Snapshot root; unregistered directories
remain quarantine candidates. This change neither runs recovery automatically nor deletes files.

## D01 与物理位置 / D01 and physical location

每个活动工作区 File 的右键菜单新增“查看物理位置”。只读查询分别显示已有 Working 文件、
Original Snapshot 文件（对于压缩包内虚拟成员则显示所在原始容器）及工作区相对路径。
尚未物化的成员明确标注没有独立 Working 路径；查询不触发解压、物化或刷新，也不把
逻辑位置伪装为磁盘路径。D01 的 `invalid experience kind` 来自 Qt 将下拉选项的字符串
传给要求 `ExperienceKind` 的 Action；创建时现在显式转换。记录/更正只输入一段内容，
首行自动生成内部列表摘要；固定 Revision 依据仍明确选择。“关联操作事实”不再出现于
录入界面；已有版本中的 Event 关系在更正时保留，历史不删除。

The context menu of each active Workspace File now offers View Physical Location. A read-only
query distinguishes an existing Working file, an Original Snapshot file (or the enclosing
original Container for a virtual archive member), and the Workspace relative path. A virtual
member has no independent Working path until materialized; this query does not extract, refresh,
or confuse logical placement with a disk path. D01's invalid-kind error was caused by Qt passing
the selection as a string to an Action expecting `ExperienceKind`; creation now converts it.
Create/correct uses one text field with a first-line derived list summary and still requires
explicit fixed-Revision evidence. Operation-event choices are removed from the editor; existing
Event links are preserved on correction and history is not deleted.

Excel 跨文件公式仍是未解决限制：Working 文件按独立 Item ID 存放，不按工作区树构成
同一磁盘目录；树中移动文件不会更新 Excel 的外部链接。当前不得承诺链接自动有效，也不
自动修改公式或原始文件。后续若要支持，应先用真实但获授权的双工作簿 Fixture 验证
相对/绝对链接、重命名、移动、另存及导出，再决定是否新增受控“关联文件编辑会话”。

Excel cross-file formulas remain an open limitation. Working files are stored under separate
Item IDs, not in the Workspace tree's physical directory layout, so moving a tree node cannot
update Excel external links. PIG must not promise automatic link stability or silently rewrite
formulas or originals. A future controlled linked-file editing session requires authorized
two-workbook fixtures covering relative/absolute links, rename, move, Save As, and export before
an architecture decision.
