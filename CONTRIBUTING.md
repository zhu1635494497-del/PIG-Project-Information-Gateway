# 为 PIG 贡献 / Contributing to PIG

请先阅读 [主规则](PIG%20Project%20Rules.md)、[当前范围](docs/project-rules/CURRENT_SCOPE.md)
与[当前规划索引](docs/PIG-planning-index.md)，再按任务读取适用子规则和 ADR。

Read the [main rules](PIG%20Project%20Rules.md), [current scope](docs/project-rules/CURRENT_SCOPE.md),
and [active index](docs/PIG-planning-index.md), then relevant subrules and ADRs.

## 1. 贡献边界 / Contribution boundaries

- 必须遵守当前授权和已接受 ADR；已有范围授权包含正常实现与必要验证。
- 不得提交真实客户资料、Project SQLite、验收输出、日志、凭据或签名材料。
- 按 [DEVELOPMENT](docs/project-rules/DEVELOPMENT.md) 分级说明影响并执行相称验证。
- 规范 Markdown 同步中英文，中文为准；检查相对链接和入口。
- 不为当前无价值的 AI、平台或基础设施扩大范围。

- Honor current authorization and accepted ADRs; scope authorization includes normal implementation and necessary checks.
- Never commit real client material, project databases, acceptance outputs, logs, credentials, or signing materials.
- Use [DEVELOPMENT](docs/project-rules/DEVELOPMENT.md) risk-based impact reporting and verification.
- Keep normative Markdown bilingual with Chinese authoritative; check links and entry points.
- Do not expand into AI, platforms, or infrastructure without current value and authorization.

## 2. 提交与评审 / Submission and review

建议使用短生命周期分支与 Pull Request；复杂改动可以先创建 Issue 明确问题和边界，
小修复无需机械创建 Issue。PR 先说明问题与结果，再给出关键测试证据、限制和风险。
涉及长期所有权、兼容、安全、运行模型或重要依赖取舍时应该写 ADR；常规修复不需要。

Prefer short-lived branches and pull requests. An Issue may define complex changes first;
small fixes need no ritual Issue. Lead PRs with the problem and result, then key verification,
limits, and risks. Use ADRs for durable ownership, compatibility, safety, execution, or major
dependency trade-offs, not routine fixes.

行为验收与发布资格分别记录。发布相关变更沿用现有发布与安全清单，不把源码测试
通过宣称为签名发行或异机验证。

Record behavior acceptance and release qualification separately. Release changes use existing
release/security checklists; source tests do not establish signed distribution or cross-machine validation.
