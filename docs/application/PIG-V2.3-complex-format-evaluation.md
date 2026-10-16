# V2.3 复杂格式候选评估 / V2.3 Complex-format Candidate Evaluation

- 决策约束：[ADR-027](../decisions/ADR-027-v2.3-canonical-content-search.md) D127-A、D128-A / Decision boundary: [ADR-027](../decisions/ADR-027-v2.3-canonical-content-search.md) D127-A and D128-A
- 状态：评估协议已建立；真实 Fixture 和运行时依赖尚未批准，不表示 PDF/DOCX/PPTX 已支持 / Status: Evaluation protocol established; real fixtures and runtime dependency remain unapproved, so PDF/DOCX/PPTX support is not claimed

## 为什么单独评估 / Why this is a separate gate

PDF 页码、DOCX 段落、PPTX Slide 必须能由用户在原文件核对。只提取字符串但 Locator
漂移、遗漏表格/页眉/备注，或在打包版引入数百 MiB 新依赖，都不能视为可交付能力。
当前首批仅支持 TXT、CSV、EML、XLSX；复杂格式提取返回明确 `UNSUPPORTED`。

PDF pages, DOCX paragraphs, and PPTX slides must be verifiable in the source file.
Plain strings with unstable locators, omitted tables/headers/notes, or an unexpectedly large
packaged dependency do not constitute shippable support. The first batch covers TXT, CSV,
EML, and XLSX; complex formats explicitly return `UNSUPPORTED`.

## 候选与证据矩阵 / Candidates and evidence matrix

候选只作为实验对象，不预装、不写入运行时依赖：Office Open XML 可先比较标准库 ZIP/XML
最小 Adapter 与专用文档库；PDF 可比较轻量文本解析库与具布局结构的 Adapter；Docling
仅是跨格式候选。每一种候选须在相同获授权 Fixture 上填满下列证据，再提出依赖决定。

Candidates are experimental, not runtime dependencies: compare a minimal standard-library
ZIP/XML adapter with a dedicated document library for Office Open XML; compare a lightweight
PDF text parser with a layout-aware adapter; Docling is only a cross-format candidate. Use
the same authorized fixtures and fill every evidence field before requesting dependency approval.

| 证据 / Evidence | 最低记录内容 / Minimum record |
| --- | --- |
| Fixture 来源 / Fixture provenance | 公开许可证或负责人明确授权；禁止提交真实客户资料 / Public license or explicit owner authorization; no customer data committed |
| 内容正确性 / Text fidelity | 正文、表格、页眉、备注、编码与遗漏清单 / Body, tables, headers, notes, encoding, omissions |
| Locator 可信度 / Locator fidelity | PDF 页、DOCX 段落、PPTX Slide 的人工核对比例与失败样例 / Human-checked page, paragraph, slide accuracy and failures |
| 资源 / Resources | 三轮中位数、Peak RSS、CPU、临时磁盘、超时/取消 / Three-run medians, peak RSS, CPU, temp disk, timeout/cancel |
| 发布 / Packaging | Windows 源码与 PyInstaller 干净主机、包体增量、启动问题 / Source and clean-host PyInstaller, size delta, startup failures |
| 法律与维护 / License and maintenance | 主包与转依赖许可证、再分发义务、更新/安全维护 / Package and transitive licenses, redistribution, update/security maintenance |

## 进入后续批次的条件 / Entry condition for a later batch

需要先提交 Fixture 清单、候选版本、可复现命令、定量结果、失败样例与推荐取舍，明确
新依赖和许可影响，由负责人单独批准后才更改运行时依赖、打包配置和 `SUPPORTED` 结果。
没有这些证据时保持 `UNSUPPORTED` 是正确结果，不以“无搜索命中”伪装。

Before a later batch, submit fixture provenance, candidate versions, repeatable commands,
measurements, failures, and a recommendation including dependency/license impact. The owner
must separately approve a runtime dependency before packaging or changing support status.
Until then `UNSUPPORTED` is correct and must not be shown as an ordinary zero-hit search.
