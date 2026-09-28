# PIG v1.0.0-rc.2 发布说明 / Release Notes

> **候选版 / Pre-release:** 这是未签名的 Windows x64 便携候选版，用于公开测试和反馈。
> 它不是已完成 Authenticode 签名、第三方许可人工复核和干净主机矩阵验收的正式版。
>
> **Pre-release:** This is an unsigned Windows x64 portable candidate for public
> testing and feedback. It is not the final release qualified through
> Authenticode signing, human third-party-license review, and the clean-host
> acceptance matrix.

## 版本标识 / Version Identity

- Git Tag / GitHub Pre-release: `v1.0.0-rc.2`
- Python package version: `1.0.0rc2`
- Target: Windows x64 portable `onedir` ZIP
- Signature: Unsigned / 未签名

## 本次重点：性能与响应优化 / Focus: Performance and Responsiveness

RC.2 对大文件和大批量文件工作流进行了系统性性能优化。导入、结构树查询、搜索、
Working 物化、外部修改刷新与导出从同步全量工作调整为有界批处理、分页读取和后台任务；
Qt Tree 热路径增加显示值、图标和行定位缓存，并改用像素级滚动，显著减少点击 Workspace、
滚动大型文件树和处理约 80 MiB 输入时的界面停顿。

RC.2 systematically improves large-file and high-file-count workflows. Import,
tree queries, search, Working materialization, external-save refresh, and export
now use bounded batches, paged reads, and background work instead of synchronous
full-set operations. The Qt Tree hot path caches display values, icons, and row
lookups and uses pixel-based scrolling, substantially reducing UI stalls when
opening or scrolling large workspaces and processing inputs around 80 MiB.

正式基准在固定 Fixture 上通过全部绝对门和 RC.1 相对回归门：10,000 行结构树加载约
`0.895s`，搜索约 `0.225s`，80 MiB 单文件导入约 `0.960s`，首次进度约 `0.031s`；
2,000 文件 / 78 MiB 导入首次进度约 `0.029s`，峰值 RSS 约 `214.1 MiB`。

The formal fixed-fixture benchmark passes every absolute gate and RC.1 relative
regression gate: a 10,000-row tree loads in about `0.895s`, search in `0.225s`,
an 80 MiB single-file import in `0.960s` with first progress in `0.031s`, and a
2,000-file / 78 MiB import reports first progress in `0.029s`; peak RSS is about
`214.1 MiB`.

## 当前能力 / Current Capabilities

- 拖入多个文件或文件夹并建立不可变 Original Snapshot。
- 发现 Folder、ZIP、7z、RAR、MSG 和 EML 的嵌套结构。
- 在 Workspace Tree 中新增、移动、软删除、恢复和撤销误导入。
- 按需物化文件，通过 Windows 关联应用打开，并识别外部保存。
- 保留当前和上一 Working 版本，支持确认回滚。
- 按名称、格式和状态搜索，并导出单文件、多选 ZIP 或保留结构的文件夹。

- Import multiple files or folders into an immutable Original Snapshot.
- Discover nested Folder, ZIP, 7z, RAR, MSG, and EML structures.
- Add, move, soft-delete, restore, and undo mistaken imports in the Workspace Tree.
- Materialize files lazily, open them with Windows-associated applications, and
  detect external saves.
- Retain the current and previous Working versions with confirmed rollback.
- Search by name, format, and state, then export one file, a multi-selection ZIP,
  or a structure-preserving folder.

## 安装与运行 / Install and Run

1. 下载 `PIG-v1.0.0-rc.2-windows-x64-unsigned.zip`。
2. 使用同名 `.sha256` 文件校验下载包。
3. 将 ZIP 完整解压到本地文件夹；不要直接在 ZIP 内运行。
4. 运行解压目录中的 `PIG.exe`。
5. Windows 可能显示 SmartScreen 警告；这是未签名候选版，请先核对 SHA-256。

1. Download `PIG-v1.0.0-rc.2-windows-x64-unsigned.zip`.
2. Verify it against the accompanying `.sha256` file.
3. Extract the complete ZIP locally; do not run it from inside the ZIP.
4. Run `PIG.exe` from the extracted directory.
5. Windows may display a SmartScreen warning because this candidate is unsigned;
   verify the SHA-256 first.

RAR 支持需要在 Windows 标准位置安装兼容的 7-Zip；PIG 不捆绑 `7z.exe`。

RAR support requires a compatible 7-Zip installation in a standard Windows
location. PIG does not bundle `7z.exe`.

## 已知边界 / Known Boundaries

- 当前只验证 Windows x64，没有 Installer 或应用内自动更新。
- 不回写或重新打包 ZIP、RAR、7z、MSG 或 EML。
- 不追踪通过 **Save As** 保存到 Project 之外的文件。
- 安全资源上限不是性能 SLA；极端规模仍可能需要较长处理时间。
- 当前不包含 OCR、RAG、AI Chat、Agent、MCP、云同步或多人协作。

- Only Windows x64 is currently qualified; there is no installer or in-app updater.
- PIG does not write back or repack ZIP, RAR, 7z, MSG, or EML.
- Files saved outside the Project through **Save As** are not tracked.
- Safety resource limits are not performance SLAs; extreme workloads may still
  require extended processing time.
- OCR, RAG, AI chat, Agents, MCP, cloud sync, and multi-user collaboration are
  not included.

## 反馈与安全 / Feedback and Security

请通过 GitHub Issues 提交可复现的问题，但不要上传真实客户文件、Project 数据库、邮件、
附件、访问令牌、证书或密钥。安全问题请遵循 `SECURITY.md`。

Use GitHub Issues for reproducible problems, but never upload real customer
files, Project databases, email, attachments, access tokens, certificates, or
keys. Follow `SECURITY.md` for security reports.
