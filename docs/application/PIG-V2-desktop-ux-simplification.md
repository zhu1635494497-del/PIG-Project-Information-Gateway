# 桌面界面简化与验收 / Desktop UI Simplification and Acceptance

- 范围 / Scope：已选“轻量双栏”草图在现有 PySide6 桌面端的呈现与交互。
  The selected light two-pane sketch applied to the existing PySide6 desktop UI.
- 边界 / Boundary：仅改变展示、导航和既有 Action 的入口；不新增领域事实、Schema、
  格式 Handler、AI 功能或任意节点硬删除。Presentation, navigation, and entry points
  for existing Actions only; no new domain fact, schema, format Handler, AI feature, or
  arbitrary-node hard deletion.

## 1. 用户路径 / User path

工作区默认显示文件树与简洁搜索；顶部是项目、导入、导出和更多操作。选中文件后，
右侧显示文件名、工作区位置、状态和可执行的主要操作。来源、版本与恢复操作按需展开；
活动记录、回收站和搜索结果仍可进入，但不占用默认内容区。

The Workspace defaults to the file tree and a compact search. The top contains project,
import, export, and overflow actions. Selection reveals the filename, Workspace location,
status, and primary available Actions on the right. Origin, versions, and recovery expand
on demand. Events, trash, and search results remain accessible without occupying the
default view.

核心文件页默认展示清单、用途、状态和选中文件的人工阅读说明。分组管理、固定版本、
内容提取及搜索、交付历史和索引维护仍可进入，但不同时常驻。界面使用中文任务语言，
内部 ID、Hash 等技术字段只保留在按需展开的详细信息中。

The Core Files page defaults to the selected file list, purpose, state, and human reading
guidance. Section management, fixed versions, extraction/search, delivery history, and index
maintenance remain reachable but are not all permanently visible. Task-oriented Chinese
labels replace most internal terms; IDs and hashes are shown only in expanded details.

## 2. 保留行为与限制 / Preserved behavior and limits

- 导入、原始副本保护、懒物化、受控打开、外部编辑刷新、回滚、软删除、误导入撤销、
  导出、Context 捕获及内容搜索继续由现有 Application Actions 执行。Import,
  Original protection, lazy materialization, controlled open, refresh, rollback, soft
  delete, import undo, export, Context capture, and content search still use the existing
  Application Actions.
- 草图中的“重命名”没有现有受控 Action，本轮不呈现一个假按钮，也不增加未经设计的
  文件改名功能。The sketch's rename control has no existing controlled Action; this pass
  neither shows a fake button nor adds an undesigned rename feature.
- 右键菜单及键盘快捷键保留；隐藏工具栏不能移除 Ctrl+N、Ctrl+O 和 F5。Context
  menus and keyboard shortcuts remain; hiding the toolbar must not remove Ctrl+N,
  Ctrl+O, or F5.
- 无 V2.4 AI 实施或资料外发。No V2.4 AI implementation or outbound data transfer.

## 3. 验收检查 / Acceptance checks

1. 新建或打开项目后，导入文件/文件夹，树结构、选中详情与双击打开正常。
   Create/open a project, import files/folders, and verify the tree, selected details,
   and double-click open.
2. 搜索、筛选、返回工作区、回收站/恢复、活动记录、导出与错误/恢复提示均可找到。
   Find and use search/filter, return, trash/restore, events, export, and error/recovery notices.
3. 选定文件加入核心文件，阅读/编辑说明，按需展开分组、版本和内容搜索，并导出交付包。
   Promote a selected file, read/edit guidance, expand sections/versions/content search
   when needed, and export a Context Pack.
4. 大树滚动和后台处理保持响应；UI 改动不让解析或 Hash 回到主线程。
   Keep large-tree scrolling and background operations responsive; no parsing or hashing
   returns to the UI thread.

自动化回归、源码桌面人工测试、打包桌面测试及用户签收分别记录，不能互相替代。
Record automated regression, source-desktop manual testing, packaged-desktop testing, and
owner acceptance separately; one does not substitute for another.
