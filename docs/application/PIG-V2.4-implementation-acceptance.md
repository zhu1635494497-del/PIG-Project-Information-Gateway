# V2.4 实施与验收记录 / V2.4 Implementation and Acceptance Record

当前签收状态以 [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md) 为准。本记录区分代码可运行、合成测试、真实 Provider 资格和人工桌面验收；不得将其互相替代。

Current acceptance status follows [CURRENT_SCOPE](../project-rules/CURRENT_SCOPE.md). This record separates runnable code, synthetic tests, live-provider qualification, and manual desktop acceptance; none substitutes for another.

下文早期“外发关闭”段落保留当时实施状态；后续本机合成 DeepSeek 例外见
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md) 和本记录末尾。

Earlier "egress disabled" paragraphs preserve their implementation-time state. The later
bounded local synthetic DeepSeek exception is in
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md) and the final section below.

## 用户闭环 / User loop

用户在核心文件的固定 Revision 旁建立判断、决定或经验，显式选择依据；之后可以确认、更正、标记被取代并查看历史。导出时可以选择附带这些记录；只有所选文件版本完整覆盖依据，Bundle 2.0 才能发布。未选择经验记录时仍产生原有 Pack 1.0。

A user creates a judgment, decision, or lesson beside fixed core-file Revisions with explicit evidence links; then confirms, corrects, supersedes, or reviews history. Export optionally includes those records only when selected file Revisions fully cover their evidence. Without selected experience, the original Pack 1.0 remains unchanged.

AI 辅助从一个或两个固定 Revision 开始，支持摘要、比较和关键事实卡。后端只读取有界 `ContentElement`，给出 `COMPLETE_INPUT` 或 `PARTIAL_INPUT`、精确文本预览、Provider/模型和成本估算。确认令牌一次有效；输入变化使确认失效。估算超过 US$0.50/次或合成资格活动账本超过 US$5 时拒绝发送；估算并不限制厂商实际账单。模型输出逐条绑定本次元素 ID，错误引用整体失败。草稿和最少必要用量留在项目 SQLite，密钥留在系统凭据库；不保存完整外发 Payload。

引用校验仅证明 ID 与固定版本位置属于本次输入，不证明模型陈述在语义上成立；结果始终是待人工核对的草稿。
桌面草稿列出 Locator，双击引用可打开对应的只读固定 Revision；外部 Host Application
是否能自动跳到精确页、行或单元格取决于其能力，当前只保证展示 Locator 与打开版本。

AI assistance starts from one or two fixed Revisions for summary, comparison, and key-fact cards. The backend reads bounded `ContentElement` rows only and previews exact text, `COMPLETE_INPUT` or `PARTIAL_INPUT`, provider/model, and estimated cost. Consent is one-shot and invalidated by changed input. Requests over US$0.50 estimated or over the US$5 synthetic-qualification ledger are denied; estimates do not cap the provider's actual bill. Each model claim must cite an element in that request; invalid citations fail the run. Drafts and minimal usage remain in Project SQLite, credentials in the OS store, and full outbound payloads are not persisted.

Citation validation proves that an ID and fixed-Revision locator belong to this request, not that a model statement is semantically true; every result remains a draft for human review.
The desktop draft displays each locator and can open its read-only fixed Revision. Jumping to
the exact page, line, or cell inside a Host Application depends on that application's support;
this stage guarantees locator display and Revision opening only.

## 数据与事件 / Data and events

- `0015_project_experience`：Record、不可变文本版本、状态变更、Revision/Event 显式关系；人工修改和确认推进 Context Revision，并发结构化 Event。
- `0016_ai_analysis`：Run、固定输入元素、结构化 Claim、Citation 关系；`RUNNING → SUCCEEDED/FAILED/INTERRUPTED`，状态与相应 Event 同事务保存。
- Context Revision 清理必须保护所有人工经验历史版本引用；AI 输入外键阻止被引用内容元素静默删除。

- `0015_project_experience`: records, immutable text versions, state transitions, and explicit Revision/Event links; human mutations advance Context Revision and emit structured Events.
- `0016_ai_analysis`: runs, fixed input elements, structured claims, and citation links; `RUNNING → SUCCEEDED/FAILED/INTERRUPTED` is persisted with its Event in one transaction.
- Context Revision cleanup protects all historical human-experience references; AI input foreign keys prevent silent removal of referenced content elements.

## 安全停止线 / Safety stop line

桌面生产配置的 `live_enabled=False`：UI 能预览，但不能发送。OpenAI 和 DeepSeek Adapter 已有固定 HTTPS 端点、无重定向、限时/限长响应和假 Transport 测试；这**不是**真实账号、协议、留存和打包资格验收。用户尚未提供 API 凭据，本次没有真实网络调用，也没有发送任何项目资料。真实业务资料外发、外部工作流 Adapter、HTTP/MCP Server、RAG、Agent 均不在本次验收范围。

核心文件“更多”菜单可以设置或清除本机 Windows 凭据管理器中的 Provider 密钥；保存密钥本身不会放开外发 Gate，也不会写入项目 SQLite。中断的 `RUNNING` 草稿可由用户确认后标记为 `INTERRUPTED`，不会自动重试或再次发送。

Desktop production uses `live_enabled=False`: the UI can preview but cannot transmit. The OpenAI and DeepSeek adapters have fixed HTTPS endpoints, no redirects, bounded time/response sizes, and fake-transport tests; this is **not** live account, protocol, retention, or packaged qualification. No API credential was supplied; this work made no live API call and sent no Project material. Real business-data egress, workflow-platform adapters, HTTP/MCP servers, RAG, and agents are outside this acceptance.

The Core Files “More” menu can save or clear a Provider key in the local Windows Credential Manager; saving alone never unlocks egress or writes the key to Project SQLite. After explicit user confirmation, interrupted `RUNNING` drafts can become `INTERRUPTED` without automatic retry or retransmission.

## 自动验证 / Automated verification

本轮自动验证：全量回归曾在 Event 排序修复后达到 **279 通过、95 跳过、0 失败**；
随后对最新 V2.4 改动重新运行的针对性组合为 **38 通过**。跳过项主要是已被
Workbench 取代的历史契约及当前主机不允许创建 Symbolic Link 的用例。这些数字
不代表真实 Provider、打包或人工桌面签收。

Automated evidence: after the Event-ordering fix, the full suite reached **279 passed,
95 skipped, 0 failed**; a later targeted run over the latest V2.4 changes had **38 passed**.
Skips are primarily superseded historical Workbench contracts and host-restricted symbolic-link
cases. These counts do not constitute live-provider, packaged, or manual-desktop acceptance.

## 官方 SDK 无网络评估（2026-10-13） / Networkless official SDK evaluation (2026-10-13)

依据用户“优先使用现成 API 接口”的选择，本机开发虚拟环境安装 OpenAI 官方 Python
SDK `3.29.0`，仅以 `httpx2.MockTransport` 和合成文本执行
`tests/infrastructure/test_v246_sdk_compatibility.py`：**6 通过**。两固定 `base_url`
分别生成 `/v1/responses` 和 `/responses` 请求，PIG 的 `json_schema` 可由 SDK
序列化，返回对象能读取 `output_text` 与 Token 用量。显式设置 `max_retries=0`、
`timeout=35`、`follow_redirects=False` 后，302、429 和超时都只发生一次请求，
重定向没有跟随到其他主机。这验证的是客户端请求形状与控制选项，**不证明**两个
厂商实际接受 Schema、模型可用、费用准确或数据留存条件。

发现一个替换阻断项：现有手写 Adapter 拒绝超过 **2 MB** 的响应体，SDK 默认客户端
却能接收并解析超过此大小的合成响应。替换前必须在受控 Transport/流读取层保留
这个上限，并验证异常映射、Windows 打包体积及取消行为。此次没有修改
`pyproject.toml`、运行时 Adapter 或 `live_enabled=False`；SDK 仅安装在本机开发
`.venv`，不是可发布依赖。没有使用 API Key，也没有发出模型 API 请求。
新增 SDK 测试、现有手写 Adapter 测试及 AI Application 回归合并运行：
**20 通过**。首次运行的 11 个 Application 用例被当前 Windows 沙盒的临时项目
目录重命名/路径解析权限拦截；使用工作区内的合成临时目录并在允许的测试环境重跑后
全部通过。初次失败不计为产品行为验收通过的证据，也未用修改业务代码掩盖。

Following the owner's SDK-first preference, the official OpenAI Python SDK `3.29.0` was
installed only in the local development venv. Six tests in
`tests/infrastructure/test_v246_sdk_compatibility.py` passed using synthetic text and
`httpx2.MockTransport`, with no network. The fixed `base_url` values produced
`/v1/responses` and `/responses`; the SDK serialized PIG's `json_schema` and exposed
`output_text` and token usage. With explicit `max_retries=0`, `timeout=35`, and
`follow_redirects=False`, 302, 429, and timeout cases made one request each without
following a redirect to another host. This proves client-side request shape and controls,
**not** actual provider acceptance, model access, pricing, or retention.

One blocker remains before replacing production transport: PIG's current adapter rejects
responses over **2 MB**, while the SDK default accepted and parsed a larger synthetic body.
A bounded transport/streaming layer must retain that limit, followed by error-mapping,
Windows packaging-size, and cancellation checks. This evaluation changed neither
`pyproject.toml` nor the runtime adapter or `live_enabled=False`. The SDK exists only in
the local development `.venv`, not as a distributable dependency. No API key or model API
request was used.
The new SDK tests, existing hand-written adapter tests, and AI Application regressions
passed together: **20 passed**. The first run's 11 Application cases were blocked by
Windows sandbox permissions during temporary-project directory rename/path resolution.
They all passed when rerun with a synthetic temporary directory in the workspace and
an allowed test environment. The first failure is not product-acceptance evidence and
was not hidden with a business-code change.

## 官方 SDK 运行时接入（2026-10-13） / Official SDK runtime integration (2026-10-13)

用户随后授权完成 API 接入开发。`ResponsesAdapter` 已改用 OpenAI 官方 Python SDK
`>=3.29,<3.30`，由同一个 Provider Port 服务 OpenAI 与 DeepSeek 固定 HTTPS 端点。
SDK 负责请求序列化、协议响应与连接管理；PIG 在响应 Hook 与实际流读取中限制
**2,000,000 字节**，显式设置 35 秒超时、`max_retries=0`、
`follow_redirects=False`，请求未压缩响应并拒绝意外压缩响应，以免解码后绕过
字节上限；状态码、超时和无效输出映射为不含远端正文的错误码。
系统凭据、逐次输入计划、一次性确认、预算、引用校验、Run/Event 状态逻辑不变。
项目依赖与发布锁文件已加入 SDK；此前评估段落中的“仅开发环境安装”仅描述当时状态。

无网络 `MockTransport` 测试 **20 通过**，覆盖两个端点、Schema、凭据缺失、
302/401/429/500、无重试、超时、缺失/无效输出、意外压缩响应，以及有/无
`Content-Length` 的超限响应。AI Application 11 项合成用例在组合运行时出现过一项间歇性
`IMPORT_SESSION_NOT_INSPECTABLE`（失败位置在导入会话、尚未调用 SDK）；相应
失败用例独立重跑通过；最终组合重跑 **31/31 通过**。此前两次 28/29 运行的
间歇失败仍保留为测试稳定性观察项，不将其抹去。

Windows `onedir` 包成功构建，目录约 **145 MB**；包内合成工作区流程在允许的
测试环境退出码为 **0**。首次受 Windows 沙盒文件权限影响退出码为 1，且尚未
创建项目；在沙盒外重跑通过。该包是本地验证产物，未签名、未发布，未进行人工
桌面或干净主机验收。没有使用真实 API Key，也没有发出模型请求；
`live_enabled=False` 保持不变。发布前仍需重新生成第三方声明、SBOM 与漏洞审计。

The owner subsequently authorized API integration. `ResponsesAdapter` now uses the official
OpenAI Python SDK `>=3.29,<3.30` for the fixed OpenAI and DeepSeek HTTPS origins behind the
same Provider Port. The SDK owns request serialization, protocol response handling, and
connections. PIG enforces **2,000,000 actual response bytes** with a response hook and
bounded stream, explicitly sets a 35-second timeout, `max_retries=0`, and
`follow_redirects=False`, requests an uncompressed response, and rejects unexpected
compression so decoded bytes cannot bypass the cap. Status, timeout, and invalid-output
failures map to safe codes without remote body text. Credential storage, per-request plan/consent, budget, citation
validation, and Run/Event semantics are unchanged. The project dependency and release lock
now include the SDK; the earlier evaluation-only statement describes that earlier phase.

Twenty networkless `MockTransport` tests passed across both origins, schema, missing key,
302/401/429/500, no retries, timeout, missing/invalid output, unexpected compression,
and oversized responses with or without `Content-Length`. In combined runs, one of the 11 synthetic AI Application cases
intermittently failed with `IMPORT_SESSION_NOT_INSPECTABLE` during import, before any SDK call;
that case passed in isolation, and the final combined rerun had **31/31 passed**. The two
earlier 28/29 runs remain recorded as test-stability observations rather than being erased.

The Windows `onedir` package built successfully at approximately **145 MB**, and its packaged
synthetic workspace flow exited **0** in an allowed test environment. The initial sandboxed
run exited 1 before project creation due to filesystem permissions; the rerun passed.
This is an unsigned local validation artifact, not a published, manually accepted, or
clean-host package. No real API key or model request was used; `live_enabled=False` remains.
Third-party notices, SBOM, and vulnerability audit must be regenerated before release.

## 真实 Provider 资格准备（2026-10-13） / Live-provider qualification preparation (2026-10-13)

本步仅核对公开资料和本机凭据**是否存在**，不读取或输出密钥正文，也不发出模型请求。
Windows Credential Manager 中没有发现 PIG 专用的 `openai` 或 `deepseek` 凭据；
因此两家均尚不能进行真实合成调用，桌面生产开关继续为 `live_enabled=False`。

公开文档核对结果：OpenAI 的 `gpt-6-luna` 支持 Responses API 与结构化输出；
当前公布的标准短上下文文本价格为每百万输入/输出 Token **US$0.10/0.50**。
DeepSeek 的 `deepseek-flash` 支持 Responses API 与 `json_schema` 输出；当前公布的
峰时未命中缓存输入/输出价格为每百万 Token **US$0.30/1.20**。两组数字与
`MODEL_PROFILES` 的保守估算一致，但实际账号可用性、计费层级与账单尚未验证。
OpenAI 公布的默认 Abuse Monitoring Log 可能保留客户内容最长 30 天，`store:false`
不能被表述为零留存。DeepSeek 的公开隐私政策明确提示下游应用终端用户的数据处理
不由该政策覆盖；具体 API 账号/合同的数据处理、留存和跨境条件仍需账号持有者核对。
因此**不得**据公开文档宣称两家 Provider 已满足真实业务资料外发条件。

首次真实资格验收必须逐家独立执行：账号持有者通过桌面端将对应 Key 存入 Windows
Credential Manager；先确认账号模型权限、条款、留存与当日价格，再仅用独立合成项目
的一份固定 Revision 执行一次摘要。请求前核对精确输入预览、Provider/模型与单次
估算不超过 US$0.50；执行后核对 Schema、引用、状态/Event、Token 用量和账号账单。
若首个请求失败，不自动重试或转向另一家；记录安全错误码后停止。需要比较或事实卡
试验时逐次重新预览和确认，合成验收活动累计估算不超过 US$5。取消/超时及失败
恢复继续由无网络测试覆盖；真实请求不刻意制造超时以免产生不确定费用。
通过后仍须单独决定是否开启**对应 Provider** 的生产外发；真实业务资料发送另需授权。

参考： [OpenAI 模型与价格](https://developers.openai.com/api/docs/models/gpt-6-luna)、
[OpenAI 数据控制](https://developers.openai.com/api/docs/guides/your-data)、
[DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)、
[DeepSeek Responses API](https://api-docs.deepseek.com/api/create-response/)、
[DeepSeek 隐私政策](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)。

This step checked public documentation and only the **presence** of local credentials. It did
not read or display secret values and made no model request. No PIG-specific `openai` or
`deepseek` entry was found in Windows Credential Manager. Neither provider can yet undergo a
live synthetic trial, and desktop production remains `live_enabled=False`.

The published OpenAI `gpt-6-luna` model supports Responses and structured output; its current
standard short-context text rates are **US$0.10/0.50** per million input/output tokens.
DeepSeek publishes `deepseek-flash` with Responses and `json_schema` support at peak,
uncached rates of **US$0.30/1.20**. These match PIG's conservative `MODEL_PROFILES`, but account
access, billing tier, and actual charges are unverified. OpenAI's default abuse-monitoring
logs may retain customer content for up to 30 days; `store:false` does not establish zero
retention. DeepSeek's public privacy policy states that downstream-app end-user processing is
not covered by that policy; API-account contractual processing, retention, and transfer terms
still require owner review. Public documentation alone cannot qualify real business-data egress.

Qualify each provider independently. The account owner stores its key through the desktop UI
in Windows Credential Manager, confirms account access, terms, retention, and current rates,
then runs one summary over a fixed Revision in an isolated synthetic project. Verify the exact
input preview, provider/model, and estimate at or below US$0.50 before consent; afterward,
check schema, citations, state/event, token usage, and provider billing. On failure, record
the safe error code and stop without automatic retry or switching providers. Any comparison
or key-fact trial needs its own preview and consent, with no more than US$5 aggregate estimated
synthetic-exercise cost. Networkless tests cover timeout/cancel and recovery; do not deliberately
force a live timeout with uncertain charges. Production egress enablement remains a separate
decision **per provider**, and real business-data transmission requires separate authorization.

References: [OpenAI model/pricing](https://developers.openai.com/api/docs/models/gpt-6-luna),
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data),
[DeepSeek models/pricing](https://api-docs.deepseek.com/quick_start/pricing/),
[DeepSeek Responses](https://api-docs.deepseek.com/api/create-response/), and
[DeepSeek privacy policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html).

## 凭据与合成输入预览（2026-10-16） / Credentials and synthetic input preview (2026-10-16)

用户报告已保存密钥。在允许访问当前 Windows 用户凭据目录的环境中，只列出
Credential Manager **目标名称**，确认 PIG 的 `openai`、`deepseek` 两项均存在；
没有读取、输出或记录密钥正文。初次受限环境列出零项，是凭据目录隔离导致，
不能解读为用户没有保存。

在 `acceptance/v24-provider-qualification-20261016/` 创建全新合成资料与项目，
通过正式 Project → Import → Inspect → Context Capture → Revision Extract → AI Plan
链路得到 `COMPLETE_INPUT`。输入仅为五行虚构事实：项目名称、日期、场地容量、
预算上限和雨天备用场地待确认。OpenAI `gpt-6-luna` 单次上限估算 US$0.0022691；
DeepSeek `deepseek-flash` 为 US$0.0056073，均低于 US$0.50。两家只共享固定
Revision 内容；Provider、模型与 Fingerprint 各自独立。首次受限环境在导入阶段
遇到 Windows 路径访问拒绝，未触及 API；改用新的合成项目并在允许的环境中完成预览。
保留失败项目以免误删未知字节。

此时仍**未发出真实 API 请求**，未核验账号可用模型或账单，也未签收账号条款与
留存。外发前必须将五行正文、Locator/Revision 元数据、Provider、模型、用途与
费用估算向用户逐次展示并确认。生产 `live_enabled=False` 不变；合成资格试验
仅能在受控的测试服务实例中临时启用，不能作为生产外发许可。

The owner reported saving keys. In an environment permitted to list the current Windows
user's Credential Manager **target names**, both PIG `openai` and `deepseek` entries were
present. Secret values were neither read, displayed, nor recorded. An initial restricted
environment showed zero entries because its credential view was isolated, not because the
owner had failed to save them.

An entirely synthetic source and project were created under
`acceptance/v24-provider-qualification-20261016/`. The normal Project → Import → Inspect →
Context Capture → Revision Extract → AI Plan path yielded `COMPLETE_INPUT`: five fictional
lines about a project name, date, venue capacity, budget ceiling, and unresolved rain venue.
The per-request upper estimates were US$0.0022691 for OpenAI `gpt-6-luna` and
US$0.0056073 for DeepSeek `deepseek-flash`, both below US$0.50. The providers share only
the fixed Revision content; each has its own model and fingerprint. The first restricted
run failed on Windows path access during import, before any API activity. A new synthetic
project completed the preview in an allowed environment; the failed project was retained
to avoid deleting unknown bytes.

No live API request has yet occurred. Account model access, billing, terms, and retention
remain unverified. Each outbound request requires a fresh user preview and confirmation
of all five lines, locator/revision metadata, provider, model, purpose, and estimate.
Production stays `live_enabled=False`; a synthetic qualification trial may temporarily
enable only an isolated test service instance, not production egress.

## OpenAI 首次合成请求（2026-10-16） / First OpenAI synthetic request (2026-10-16)

用户选择 OpenAI 并逐次批准**仅一次**向 `gpt-6-luna` 发送上述五行虚构内容，
包含固定 Revision/Element ID、行号及防指令注入的版本化说明。发送前正式
`AIAnalysisService.plan` 重算结果为 `COMPLETE_INPUT`、5 个元素、
US$0.0022691 估算，且 Fingerprint 与用户预览时一致。独立测试服务实例临时设置
`live_enabled=True` 并调用正式 `execute`；桌面生产 Bootstrap 未改变。

Provider 返回 **HTTP 401**。PIG 将单个 Run `1a92e4ca-ad3f-4fae-8e60-b4375342a343`
落为 `FAILED`、`PROVIDER_HTTP_401`；只读复核得到 `AI_RUN_STARTED →
AI_RUN_FAILED` 两条关联 Event、0 条 Claim、无 Token 用量记录。PIG 的合成活动
估算账本计入约 US$0.002269；这不是厂商实际账单。没有自动重试、没有改测
DeepSeek、没有发送任何真实业务资料，也未签收 OpenAI 账号资格。

401 仅能说明认证/访问失败，不能单凭状态码判定具体原因。账号持有者需自行检查
OpenAI Platform 中的项目 API Key 是否有效、属于正确项目、具备 Responses
权限，以及 IP Allowlist/组织成员资格；不得把 Key 发到聊天或写入仓库。
本轮停止，不使用第二个请求试探。官方解释见
[OpenAI 错误码](https://developers.openai.com/api/docs/guides/error-codes)。

The owner selected OpenAI and gave per-request consent to send the five fictional lines,
fixed Revision/Element IDs, line locators, and versioned anti-injection instruction to
`gpt-6-luna` **once**. Immediately before execution, the normal `AIAnalysisService.plan`
recomputed `COMPLETE_INPUT`, five elements, the US$0.0022691 estimate, and the same
fingerprint seen in the preview. Only an isolated test-service instance temporarily used
`live_enabled=True`; desktop production Bootstrap was unchanged.

The provider returned **HTTP 401**. PIG persisted one Run
`1a92e4ca-ad3f-4fae-8e60-b4375342a343` as `FAILED` with
`PROVIDER_HTTP_401`. A read-only check found paired `AI_RUN_STARTED → AI_RUN_FAILED`
events, zero claims, and no token-usage record. The synthetic-exercise estimated-spend
ledger includes approximately US$0.002269; this is not an actual provider bill.
There was no automatic retry, no DeepSeek request, no real business-data transmission, and
no OpenAI account qualification sign-off.

A 401 establishes an authentication/access failure, not its exact cause. The account
owner should check in OpenAI Platform that the project API key is valid, belongs to the
intended project, permits Responses, and satisfies any IP allowlist or organization-membership
requirements. Never send the key in chat or commit it to the repository. This run stopped
without a second probe. See the [official OpenAI error guide](https://developers.openai.com/api/docs/guides/error-codes).

## DeepSeek 首次合成请求（2026-10-16） / First DeepSeek synthetic request (2026-10-16)

用户单独批准向 DeepSeek 官方固定端点的 `deepseek-flash` 发送上述五行虚构内容
**一次**，用于带引用摘要。请求另含固定 Revision/Element ID、行号与防指令注入
说明。发送前重新计划并核对 `COMPLETE_INPUT`、五个元素、预览 Fingerprint
`acfc8dc0efbbb84ea4af72cf91b566366aab2a2584e4426263b0ac4774f81ecd`
及 US$0.0056073 估算，均与用户确认的范围一致。仅独立测试服务实例临时启用
`live_enabled=True`；生产 Bootstrap 未改变。

Provider 返回 **HTTP 402**。PIG 将 Run
`43533bbd-20cb-45d6-b489-f5d7e8a66c84` 落为 `FAILED`、
`PROVIDER_HTTP_402`；只读复核得到 `AI_RUN_STARTED → AI_RUN_FAILED` 两条关联
Event、0 条 Claim、无 Token 用量。合成项目估算账本累计 US$0.007876，包含此前
失败的 OpenAI 试验；这是预留估算，不是厂商实际账单。未自动重试、未发送真实业务
资料，也未签收 DeepSeek 账号资格。DeepSeek [官方错误码](https://api-docs.deepseek.com/quick_start/error_codes/)
将 402 解释为余额不足；账号持有者须自行核对余额和充值状态，密钥不得发到聊天或
提交到仓库。余额处理后若需重试，应重新预览并获得新的单次批准。

The owner separately approved **one** cited-summary request to the official DeepSeek
`deepseek-flash` endpoint with the same five fictional lines, fixed Revision/Element IDs,
line locators, and anti-injection instruction. Fresh planning verified `COMPLETE_INPUT`,
five elements, the previewed fingerprint
`acfc8dc0efbbb84ea4af72cf91b566366aab2a2584e4426263b0ac4774f81ecd`,
and the US$0.0056073 estimate. Only an isolated test-service instance temporarily used
`live_enabled=True`; production Bootstrap was unchanged.

The provider returned **HTTP 402**. PIG persisted Run
`43533bbd-20cb-45d6-b489-f5d7e8a66c84` as `FAILED` with
`PROVIDER_HTTP_402`. A read-only check found paired `AI_RUN_STARTED → AI_RUN_FAILED`
events, zero claims, and no token-usage record. The synthetic project's estimated-spend
ledger totals US$0.007876 including the earlier failed OpenAI trial; this is a reserved
estimate, not the provider bill. There was no automatic retry or real business-data
transmission, and DeepSeek account qualification remains incomplete. DeepSeek's
[official error table](https://api-docs.deepseek.com/quick_start/error_codes/) identifies 402
as insufficient balance. The account owner should check balance and top-up status without
sharing or committing the key. Any retry after resolving the balance requires a fresh
preview and separate one-shot approval.

## DeepSeek 单次重试成功（2026-10-16） / DeepSeek one-shot retry succeeded (2026-10-16)

用户明确要求重新发起。重新核对 [官方模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)
后，`AIAnalysisService.plan` 对同一固定 Revision 生成 `COMPLETE_INPUT`、5 个元素、
Fingerprint `acfc8dc0efbbb84ea4af72cf91b566366aab2a2584e4426263b0ac4774f81ecd`
及 US$0.0056073 峰时未缓存估算；请求范围和费用已在发送前再次展示。只向 DeepSeek
官方固定端点发送了一次相同的虚构资料，未自动重试或切换 Provider。

Run `ebddf9b5-e108-482f-bdc2-0b9086cdc223` 成功落为 `SUCCEEDED`，记录
742 输入、841 输出 Token，生成 3 条 `SUMMARY` Claim；每条 Claim 均有可回查
的输入 Element ID。只读复核确认 `AI_RUN_STARTED → AI_RUN_SUCCEEDED` 两条关联
Event。调用完成后的本地显示脚本误把字符串 `kind` 当作 Enum，因而退出码为 1；
这**不是 API 或持久化失败**，复核时没有重发请求。

合成项目的估算账本累计约 US$0.013484（含此前失败的 OpenAI 和 DeepSeek
尝试），只是预留估算，不代表厂商实际扣费；未核对 DeepSeek 账单。此次证明
DeepSeek 官方端点对合成输入的连通、结构化输出与引用落库可用，但账号条款/留存、
取消/超时、打包行为及真实资料外发仍未验收。生产 `live_enabled=False` 保持不变。

The owner explicitly requested a retry. After rechecking the [official model and price page](https://api-docs.deepseek.com/quick_start/pricing/),
`AIAnalysisService.plan` produced `COMPLETE_INPUT`, five elements, fingerprint
`acfc8dc0efbbb84ea4af72cf91b566366aab2a2584e4426263b0ac4774f81ecd`,
and the US$0.0056073 peak, uncached estimate for the same fixed Revision. Scope and cost
were shown again before transmission. Exactly one request sent the same fictional data to
DeepSeek's fixed official endpoint, without automatic retry or provider switching.

Run `ebddf9b5-e108-482f-bdc2-0b9086cdc223` persisted as `SUCCEEDED` with
742 input and 841 output tokens and three `SUMMARY` claims, each carrying verifiable input
Element IDs. Read-only verification found paired `AI_RUN_STARTED → AI_RUN_SUCCEEDED` events.
A local display script then treated a string `kind` as an Enum and exited with code 1;
this was **not an API or persistence failure**, and verification made no further request.

The synthetic project's estimated-spend ledger totals about US$0.013484, including the
earlier failed OpenAI and DeepSeek attempts. This is a reserved estimate, not a verified
provider charge. The call demonstrates synthetic connectivity, structured output, and cited
persistence at the official DeepSeek origin. Account terms/retention, cancellation/timeout,
packaged behavior, and real-data transmission remain unaccepted. Production
`live_enabled=False` is unchanged.

## 本机合成 DeepSeek 受限开关（2026-10-16） / Bounded local synthetic DeepSeek gate (2026-10-16)

负责人决定当前只收尾 DeepSeek；OpenAI 401 不处理，真实 API 的异常与桌面闭环验收
暂缓，并选择仅本机源码桌面发送合成资料的方案 A。具体范围与历史决定的取代关系见
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md)。

受限试运行启用时，源码桌面组合入口只配置 DeepSeek Adapter；仅当本机存在既有合成项目时，允许该项目
固定摘要计划的项目 ID、规范化数据库路径和 Fingerprint 全部匹配后发送。计划变化、
其他项目、OpenAI 或打包运行均由后端拒绝；UI 同步将其他计划的发送按钮置灰。
原有逐次完整输入预览、一次性确认令牌、US$0.50 单次与 US$5 合成预算、不自动
重试和引用验证继续有效。没有在这次代码变更中再次向 Provider 发请求。

假 Provider 合成服务回归 **16 通过**；更广的 UI 组合首轮因 Windows 沙盒临时目录
权限失败，允许环境中复跑为 23 通过、4 失败，其中 3 项为既有导入会话间歇问题，
1 项为旧错误文案断言，已修正后单独复跑 AI 服务 16 通过。源码组合的只读预检确认
已批准合成 DeepSeek 计划可执行、OpenAI 计划被拒；打包检测有自动化负例。
**尚未进行源码桌面的人工发送点击验收，也未验收打包版或真实业务资料外发。**

The owner narrowed current closure to DeepSeek, deferred OpenAI 401 and live failure/desktop-loop
acceptance, and chose option A: synthetic material from the local source desktop only. See
[ADR-032](../decisions/ADR-032-v2.4-local-synthetic-deepseek-gate.md) for its scope and
supersession of the earlier acceptance sequence.

When the bounded trial is enabled, source-desktop composition configures only the DeepSeek
adapter. It permits a send only
when the known synthetic Project exists locally and Project ID, resolved database path, and
fixed summary-plan fingerprint all match. Changed plans, other Projects, OpenAI, and packaged
runs are denied by the backend; the UI also disables Send for other plans. Exact per-request
preview, one-shot consent, US$0.50/request and US$5 synthetic estimates, no automatic retry,
and citation checks remain in place. This code change made no further live Provider request.

Fake-provider service regression: **16 passed**. A broader UI run first failed on Windows
sandbox temporary-path permissions; an allowed-environment rerun had 23 passed and 4 failed:
three existing intermittent import-session cases and one old error-text assertion. After
correcting the assertion behavior, a focused AI-service rerun passed all 16. A read-only
source-composition preflight allowed the approved synthetic DeepSeek plan and denied OpenAI;
an automated negative check covered packaged mode. **Manual source-desktop click-through,
packaged release, and real business-data egress remain unaccepted.**

## 待完成验收 / Remaining acceptance

2026-10-12 人工测试反馈：目录包的 `files/` 现直接列出文件名；同名按可读编号区分，
具体 Item/Revision 仍以 Manifest 为准。E01 的 Qt 任务选项已转为 `AnalysisAction`
后再交给后端；F01 的损坏 ZIP 保持无 Working 副本，但树中优先展示来源的
`CORRUPTED`，不再用 `VIRTUAL` 掩盖失败。针对性自动检查通过。其后用户确认
V2.4 收尾清单第 1 项复测以及第 2 项合成项目人工验收完成；真实 Provider 外发
Gate 未变化，详细签收状态以 CURRENT_SCOPE 为准。

Manual feedback on 2026-10-12: `files/` in new directory packs now lists readable filenames
directly, using numbered names for collisions; the manifest remains authoritative for
Item/Revision identity. E01 converts the Qt selection to `AnalysisAction` before calling the
backend. F01 keeps the corrupt ZIP without Working bytes but shows its source `CORRUPTED`
state in the tree instead of masking it with `VIRTUAL`. Focused automated checks passed.
The owner subsequently confirmed closure item 1 retest and item 2 synthetic-project manual
acceptance. The live-provider egress gate is unchanged; CURRENT_SCOPE owns the exact status.

1. 当前受限范围内：用源码桌面打开指定合成项目，人工检查预览、确认发送、草稿引用与重启后结果；此项尚未签收，且不会自动执行。
2. 未来若要扩大到真实资料或正式打包发布，另行审查 DeepSeek 账号条款/留存、真实 API 异常与打包行为，明确授权真实资料范围，并保留逐次精确输入确认。OpenAI 不再是当前收尾条件。

1. Within the current bounded scope, manually open the specified synthetic Project in the
   source desktop and check preview, confirmed send, cited draft, and reopening after restart.
   This remains unsigned and will not run automatically.
2. Any later real-data or packaged-release expansion requires separate review of DeepSeek
   account terms/retention, live failure behavior, and packaging, explicit authorization for
   the real-data scope, and exact per-request consent. OpenAI is no longer a current closure gate.
