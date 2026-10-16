# PIG 文档双语规范 / PIG Bilingual Documentation Standard

- 状态：当前有效 / Status: Active
- 更新：2026-10-09 / Updated: 2026-10-09

## 1. 适用范围 / Scope

PIG 自有 Markdown 提供中文和英文。代码标识符、枚举、路径、命令、Schema 和
第三方名称保持原样；第三方许可证、版权声明和生成 Notice 不翻译或改写。

First-party Markdown provides Chinese and English. Keep identifiers, enums, paths, commands,
schemas, and third-party names unchanged. Do not translate or rewrite third-party licenses,
copyright notices, or generated notices.

## 2. 唯一规范正文 / Single authoritative text

中文是 PIG 项目自有规范的权威正文，英文是同步维护的说明，不形成第二套独立规则。
新文档使用中文在前、英文紧随的结构；不再追加一份完整的 English Normative Translation。
发现差异时以中文解释，并尽快修正英文。若歧义涉及已批准 ADR、不可逆操作或安全
边界，按主规则解决实际冲突，不能借语言差异自行扩大授权。

Chinese is authoritative for first-party PIG specifications. English is maintained explanation,
not an independent rule set. New documents use Chinese followed by English rather than a second
full normative translation. Resolve translation differences using Chinese and correct English.
Ambiguity affecting accepted ADRs, irreversible actions, or safety follows the main conflict
process; language differences cannot expand authorization.

既有文档在下次相关修改时逐步对齐格式；不要求本次批量重写全部文档。
历史文档保留原始正文与中英文状态、适用范围说明；它们只供追溯，不能覆盖当前决定。

Align existing documents when next relevantly edited; no wholesale rewrite is required now.
Historical documents retain original text with bilingual status and applicability and cannot
override active decisions.

## 3. 写作格式 / Writing format

- 标题：`中文标题 / English Title`；段落或短清单先中文、后英文。
- 表格列标题双语，单元格可使用 `<br>` 或简短双语说明。
- 代码块只出现一次，两种语言共同引用。
- 使用 MUST/必须、MUST NOT/不得、SHOULD/应该、MAY/可以区分约束等级。
- 使用可验证的相对链接；避免仅写失效章节号或散落绝对本机路径。

- Titles use `Chinese / English`; paragraphs or short lists present Chinese first.
- Table headers are bilingual; cells may use `<br>` or concise bilingual descriptions.
- Code blocks appear once, shared by both languages.
- Distinguish MUST, MUST NOT, SHOULD, and MAY with their corresponding Chinese terms.
- Use verifiable relative links; avoid obsolete section-only references or local absolute paths.

## 4. 信息归属与检查 / Information ownership and checks

当前阶段、授权与签收状态在 [CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md) 维护。
规划索引负责导航，ADR 保存具体决定与历史，不反复复制状态段落。
规范修改必须检查两种语言的术语、状态名、范围、链接和验收条件一致。

Maintain phase, authorization, and acceptance status in [CURRENT_SCOPE](project-rules/CURRENT_SCOPE.md).
Indexes provide navigation and ADRs preserve decisions/history without repeated status paragraphs.
Normative changes verify alignment of terms, states, scope, links, and acceptance conditions.
