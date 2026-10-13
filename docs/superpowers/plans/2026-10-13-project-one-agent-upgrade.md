# 项目一：LangGraph 智能体业务助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本文是根据现有仓库整理的升级评审稿；本次仅制定计划，尚未开始实现。默认由当前执行者按顺序实施，不自动启动子智能体。

**Goal:** 保留 Streamlit，让智能体在可信身份和会话范围内，正确选择工具、追问缺失信息、完成多步骤业务任务，并提供可复现的可靠性证据。

**Architecture:** Streamlit 作为项目一的界面，通过会话独立的 HTTP 客户端复用本仓库已有 FastAPI 登录、会话、异步 Agent 和 checkpoint 能力。工具权限由后端代码强制校验；针对缺参、流程前置条件和执行预算补充确定性约束，模型负责理解需求和组织回答。现有 React 和部署材料保留，本轮不扩展其产品功能，也不移动或合并另一个项目。

**Tech Stack:** 现有 Python、Streamlit、FastAPI、LangGraph、SQLAlchemy、SQLite/PostgreSQL、Chroma、pytest、httpx；沿用 requirements.txt 的锁定版本，升级目标是业务能力，不默认升级依赖。

**Spec:** [双项目升级取舍与智能体约束](../../双项目升级取舍与智能体约束.md)，仅落实“项目一”和“两项目的取舍”。

## Global Constraints

- 已有能力保留，只补实际缺口。
- 项目一保留 Streamlit，重点做 Agent 可靠性；项目二保留 React，重点做产品与工程交付。
- 暂不合并项目，不在项目二重复建设 Agent，也不为堆技术引入多智能体、微服务等额外架构。
- 禁止批量删除文件或目录；测试使用独立数据目录，保留测试产物，不清理既有 runtime、数据库或向量库。
- 个人数据仅允许本人访问；员工 ID、用户 ID、内部 checkpoint thread ID 不能由模型或前端声明为可信身份。
- 不自动保存模型生成的周报；先生成草稿，保存继续复用已有用户确认和周报权限逻辑。
- 固定回归使用模拟企业数据和模型替身；真实模型评测单独执行，明确记录费用、失败和未实测项。

## Review Focus

1. 登录失效、切换账号、Streamlit rerun 和两浏览器并发：不能复用他人 Cookie、模型可变配置、历史或工具结果。归属任务 2、3。
2. 篡改 conversation_id、employee_id、thread_id，或通过资料指令索取他人记录：在读取目标数据前拒绝，工具结果和日志均不能泄露目标数据。归属任务 3。
3. 用户需求含糊、参数非法、追问中切换话题：澄清后恢复正确任务，不猜测查询类型、不执行过期的待办。归属任务 4。
4. 并行工具调用乱序、重复工具调用、前置步骤失败：使用 call_id 关联结果，不把拒绝、空结果或异常视作流程成功。归属任务 5、6。
5. 工具阻塞、模型循环、流中断和服务重启：有执行上限和明确终态，后续会话可继续，不重放有副作用的操作。归属任务 6、7。

## 现状与实际缺口

以下来自代码和已有测试文件的静态检查；不是本次重新执行测试得出的通过结论。

| 要求 | 已有基础 | 本轮补齐 |
|---|---|---|
| 理解需求并调用工具 | agent/react_agent.py 已用 LangGraph tool calling；工具参数有类型和枚举 | 建立缺参追问、参数错误处理和多步骤依赖规则 |
| 本人数据权限 | agent/tools/agent_tools.py 有 ContextVar 身份及本人校验；API 有服务端登录 | Streamlit 从员工选择器改为可信登录入口，复用服务端授权 |
| 连续追问、恢复、隔离 | 后端有业务会话、服务端 thread_id、SQLite/PostgreSQL saver 和重启测试 | Streamlit 接入历史列表和恢复链路，不再独立依赖 MemorySaver |
| 执行过程与异常 | Agent 有 tool_call/tool_result/error；API 有整体超时、取消和运行状态 | 增加可关联的工具状态、工具预算、明确错误分类和轨迹回看 |
| 固定案例验证 | tests 已覆盖身份、工具 schema、Agent 流、资源隔离、重启；eval 有 RAG 评测 | 增加 Agent 场景集、真实调用轨迹评分和多轮任务完成率 |

需要特别处理的现有入口差异：

- app.py 使用可选员工身份、模块级模型/RAG 可变设置和同步 stream_events，不能直接承诺可靠多用户隔离。
- 持久化 checkpoint 和中断工具回合恢复位于异步 API 链路；单独给 Streamlit 换 saver 会继续维护两套执行逻辑。
- generate_weekly_report_context 只返回写作要求，不负责查数据或保存周报；流程成功需要有数据读取和草稿完成的证据。
- 现有 eval/run_eval.py 的静态 Agent 分支不能代表新版认证 API 的会话、权限和恢复行为。

## 方案取舍

| 方案 | 收益 | 代价 | 结论 |
|---|---|---|---|
| Streamlit 复用现有 API | 直接复用登录、权限、异步执行、持久化和取消 | 多一个本地 API 启动进程，需要会话独立 Cookie 客户端 | 推荐；同一项目内部复用，不增加微服务拆分 |
| Streamlit 直接调用应用服务 | 可以只启动一个界面进程 | 需抽离 HTTP 依赖并解决异步 saver 生命周期和两入口一致性 | 仅在“必须单进程”成为明确要求时重新评估 |
| 继续扩展 React 产品 | 延续现有 Web 界面 | 偏离项目一保留 Streamlit 的定位 | 本轮不采用 |

推荐顺序：**基线 → Streamlit 接入 → 权限与恢复 → 追问 → 多步骤执行 → 异常与轨迹 → Agent 评测与交付**。

## Task 1：建立升级基线与验收矩阵

**Files:** 阅读 README.md、app.py、agent/react_agent.py、agent/runtime.py、agent/tools/agent_tools.py、api/routes/conversations.py、backend/checkpoints.py 和现有 tests；新增 docs/project-one-acceptance.md。

**Interfaces:** 沿用 ReactAgent.astream_events(query, thread_id)、RunContext、已存在的 /api/auth 与 /api/conversations 接口。本任务不修改业务接口。

- [ ] 将源要求逐条映射到本计划任务和测试；明确制度查询、本人数据、多工具周报三类主场景。
- [ ] 使用现有 .venv-v1 运行下方基线测试，记录实际通过、失败、跳过及环境信息；不读取或输出密钥。
- [ ] 把现有行为分别标为“已实现且本次验证”“仅发现实现”“本轮缺口”；PostgreSQL 测试跳过时不能写成已经验证。
- [ ] 将源要求之外的建议默认值单独标识；不把实现建议写成用户原始要求。
- [ ] 单独提交验收矩阵及基线记录。

**Validation:**

```powershell
.\.venv-v1\Scripts\python.exe -m pytest tests/test_agent_tools.py tests/test_agent_stream.py tests/test_db_tools.py tests/test_resource_ownership.py tests/test_checkpoint_restart.py tests/test_review_regressions.py -q
```

**完成标准：** 五项项目一要求均有对应任务、既有能力证据和待补测试。

## Task 2：Streamlit 使用可信登录与统一执行入口

**Files:** 修改 app.py；新增 ui/__init__.py、ui/api_client.py、ui/session_state.py、tests/test_streamlit_api_client.py、tests/test_streamlit_session_state.py；读取 api/routes/auth.py、api/schemas.py。

**Interfaces（新增）:**

```python
class AgentApiClient:
    def login(self, username: str, password: str) -> dict: ...
    def me(self) -> dict: ...
    def logout(self) -> None: ...
    def list_conversations(self) -> list[dict]: ...
    def create_conversation(self, title: str = "新对话") -> dict: ...
    def list_messages(self, conversation_id: str) -> list[dict]: ...
    def stream_chat(self, conversation_id: str, message: str,
                    client_request_id: str): ...
    def cancel(self, run_id: str) -> None: ...
```

上述为计划中的接口签名；实现时 stream_chat 返回逐条规范化事件，列表接口处理现有 API 分页。客户端每个 Streamlit 会话独立创建，不使用全局缓存或跨用户共享 Cookie jar。

- [ ] 先添加 httpx MockTransport 测试：两个客户端登录后 Cookie 不互传；写请求正确携带服务端 CSRF token 和配置的 Origin；401 触发本地身份与历史清空。
- [ ] 实现“获取 CSRF → 登录 → /me → 会话列表 → SSE 聊天”；退出登录撤销服务端会话并关闭当前客户端。
- [ ] 将 app.py 员工选择器替换为登录表单，聊天改用 API；session_state 仅保存界面状态和当前客户端，不自行注入 employee_id/thread_id。
- [ ] 新建、切换、恢复会话时从 API 读取消息；聊天请求体只提交 message 和 client_request_id。同一请求重发遇到 409 时刷新历史，不重复发起工具操作。
- [ ] 保留界面和导出功能；已有模型、Top-K、温度功能通过后端白名单配置实现等价隔离，扩展 api/schemas.py 与后端装配时同步测试，不能再修改模块级模型和 retriever。静态上传入口转接已有文档 API，避免另维护一份检索数据。
- [ ] 运行新增测试及现有 API 测试，单独提交。

**Validation:** `python -m pytest tests/test_streamlit_api_client.py tests/test_streamlit_session_state.py tests/test_auth.py tests/test_api.py -q`

**完成标准：** Streamlit 登录后能完成一次真实 HTTP 工具调用链路；注销或换账号看不到上一账号历史。测试阶段模型使用替身。

## Task 3：补齐用户、会话与 checkpoint 的隔离验收

**Files:** 主要扩展 tests/test_resource_ownership.py、tests/test_checkpoint_restart.py、tests/test_db_tools.py；新增 tests/test_agent_concurrency.py；仅在回归发现缺陷时修改 backend/conversations.py、agent/runtime.py、agent/tools/agent_tools.py 或 api/routes/conversations.py。

**Interfaces:** 身份只从现有服务端 AuthSession/User 建立；owned_conversation(db, conversation_id, user_id) 在 checkpoint 访问之前完成；内部 thread_id 不新增到 ChatRequest。

- [ ] 两个用户各建两个会话，在工具返回中设置独立金丝雀数据，交错执行并断言身份、记录、历史、来源不交叉。
- [ ] 扩展越权用例：访问他人消息、发送聊天、取消他人 run、清空他人历史；均拒绝且不触发目标工具或 checkpoint 读取。
- [ ] 对伪造 employee_id/user_id/thread_id 的请求断言 422；对工具参数篡改断言读取目标记录之前拒绝，管理员也不自动获得他人个人数据权限。
- [ ] 分别重启 API 和 Streamlit：重新认证后可恢复自己的已完成会话；仅换进程内对象不足以替代进程重启验收。
- [ ] 验证清空会话后追问不带旧上下文；未完成工具回合恢复保留完整历史且不伪造工具成功。
- [ ] 回归通过后单独提交；复用已经正确的授权逻辑，不重写整套认证。

**Validation:** `python -m pytest tests/test_resource_ownership.py tests/test_checkpoint_restart.py tests/test_db_tools.py tests/test_agent_concurrency.py tests/test_review_regressions.py -q`

**完成标准：** 未授权数据读取为零；并发、恢复和清空后的上下文隔离全部有断言证据。

## Task 4：明确工具契约与缺参追问

**Files:** 新增 agent/contracts.py、agent/policy.py、tests/test_agent_clarification.py、tests/test_agent_policy.py；修改 agent/react_agent.py、agent/tools/agent_tools.py、prompts/main_prompt.txt。

**Interfaces（新增）:** ToolOutcome 表达 status（ok/denied/not_found/invalid/error）、data、message、retryable；PendingRequest 表达 task、missing_fields、已有确认参数。业务结果与工具运行状态分开，拒绝访问不等于工具成功。

- [ ] 为“帮我查一下状态”建立期望追问案例：先问报销、项目还是入职待办，不自行选择 query_type；“年假还剩多少”可从身份得到 employee_id，不要求用户重复提供可信身份。
- [ ] 为“查报销 → 缺参追问 → 用户补充”建立多轮案例；切换到新问题时取消旧 PendingRequest，新会话不继承待补参数。
- [ ] 将工具输入错误、没有记录、越权拒绝改为可区分结果；保留权限代码在数据读取前执行，不能仅修改提示词。
- [ ] 将语义识别交给模型结构化输出，将字段完整性、枚举合法性、身份授权交给确定性 policy；需要澄清时结束当前轮并保存待补信息，不运行相关业务工具。
- [ ] 更新提示词的澄清示例；不假设现有周报 CSV 有历史日期查询能力，不新增没有数据支持的日期筛选。
- [ ] 先使新增失败测试通过，再回归工具和流事件测试，单独提交。

**Validation:** `python -m pytest tests/test_agent_clarification.py tests/test_agent_policy.py tests/test_agent_tools.py tests/test_agent_stream.py -q`

**完成标准：** 缺少业务必要信息时不猜参数；有效追问能继续原任务；权限失败不触发改参绕过。

## Task 5：让多步骤业务任务具备明确的完成条件

**Files:** 新增 agent/workflows.py、tests/test_agent_workflows.py；修改 agent/react_agent.py、agent/policy.py、prompts/main_prompt.txt；复用已有 reports API。

**Interfaces（新增）:** WorkflowProgress 按任务记录已获得的有效数据与失败状态；完成条件按数据依赖检查，不依赖固定中文措辞。若现有预构建图无法承载检查点，再局部改为显式 StateGraph；不为展示技术预先重写图。

- [ ] 为三条流程添加模型脚本测试：制度查询；本人业务查询；“查报销状态并告诉我下一步怎么处理”的制度与个人数据组合查询。
- [ ] 为周报测试四项前置证据：可信员工身份、本人部门、写作要求、query_type=weekly_report 的本人记录。独立步骤可交换顺序，但依赖缺失时不允许生成完整周报。
- [ ] 验证草稿包含本周概览、关键产出、风险问题、下周计划，事实可回溯到工具数据；记录缺失时明确说明缺项。
- [ ] 制度无资料、本人记录为空或权限拒绝时，不生成假条款、假数据或“已经完成”的结论；组合任务可返回明确标注的部分结果。
- [ ] 周报“生成”和“保存”分别验收：只有用户确认后调用现有本人周报保存接口；生成草稿不声称已经落库。
- [ ] 运行流程、周报 CRUD 和现有 Agent 测试，单独提交。

**Validation:** `python -m pytest tests/test_agent_workflows.py tests/test_reports.py tests/test_agent_stream.py -q`

**完成标准：** 对每次多步骤任务，能从有效工具结果证明其完成、部分完成或失败。

## Task 6：执行预算、失败终态与工具轨迹

**Files:** 新增 agent/execution.py、tests/test_agent_execution.py、tests/test_agent_trace.py；修改 agent/react_agent.py、agent/runtime.py、agent/tools/agent_tools.py、model/factory.py、backend/settings.py、backend/models.py、backend/conversations.py、api/routes/conversations.py、app.py；新增 migrations/versions/0002_agent_trace.py。

**Interfaces（新增）:** ToolEvent 包含 run_id、tool_call_id、tool_name、phase、status、attempt、duration_ms、error_code、经过过滤的参数与结果摘要；后端产出并保存轨迹，Streamlit 只渲染可公开字段。沿用已存在的 token/tool_call/tool_result/error/done，并保持 React 消费方兼容。

**建议默认预算（实施时集中配置并用测试固定）：** 整轮 120 秒（沿用当前默认）；单工具 30 秒；每轮最多 8 次工具尝试；相同工具和规范化参数至多 2 次尝试；可重试只读工具最多重试 1 次；写入工具自动重试 0 次；保留 recursion_limit=20 作为兜底。

- [ ] 添加超时、连接失败、非法参数、空结果、权限拒绝、未知工具、重复调用和无限模型循环案例，断言终态、次数与截止时间。
- [ ] 清点 SDK 默认重试，统一纳入预算，避免 SDK 重试与工具重试叠加；参数错误最多一次修正，权限拒绝立即终止该访问路径。
- [ ] 用异步模型调用及明确的网络超时实现可取消执行；阻塞同步调用不能仅套 asyncio 超时就视为已经停止。检索/数据库使用必要的连接或查询边界，后台工作不得在取消后污染下一轮状态。
- [ ] 工具调用阶段分别显示“执行中、成功、拒绝、无数据、超时、失败”；使用 tool_call_id 关联并行结果，不以“模型想调用工具”冒充“工具开始执行”。
- [ ] ChatRun 增加 tool_events JSON 字段并迁移；新增按本人会话读取运行轨迹的 API，消息恢复后可回看轨迹。异常详情仅进受控日志，前端不显示堆栈、密钥或数据库连接串。
- [ ] 中途失败或取消时保留部分正文但明确标记失败/未完成；无成功结果不产生 completed；取消、断线、重启后验证下一轮仍可继续。
- [ ] 运行异常、流回压、重启与 API 回归，单独提交。

**Validation:** `python -m pytest tests/test_agent_execution.py tests/test_agent_trace.py tests/test_stream_backpressure.py tests/test_chat_lifecycle.py tests/test_review_regressions.py tests/test_api_restart.py -q`

**完成标准：** 失败有原因、运行有上限、结果不虚构；历史轨迹能对应实际执行；迁移后既有会话与周报可读。

## Task 7：Agent 专项评测与演示交付

**Files:** 新增 eval/agent_cases.jsonl、eval/agent_metrics.py、eval/run_agent_eval.py、tests/test_agent_eval.py、docs/project-one-agent-evaluation.md；修改 README.md、docs/interview/demo-script.md、docs/interview/architecture.md。保留现有 RAG 评测数据与报告。

**Interfaces（新增）:** 场景记录 case_id、category、user、turns、expected_tools、参数约束、前置依赖、expected_status、forbidden_access、事实断言。评测通过认证 API 驱动完整会话，直接读取实际轨迹；不把工具的预期调用写回评分输入作为“实际结果”。

- [ ] 建立 40 个固定场景：制度查询 6、本人数据 6、缺参/非法参数 6、多步骤组合与周报 8、越权与资料指令攻击 6、多轮恢复与隔离 4、超时/失败/重复调用 4。多轮场景分别记录各轮期望。
- [ ] 分开维护开发集和留出集；固定语料版本、模拟业务记录、模型版本、执行预算与随机配置；不得根据留出集反复调提示词后仍称其独立评测。
- [ ] 用确定性模型和故障注入验证执行器；用真实模型验证需求理解、工具选择和任务完成。二者分开报告，脚本模型测试不能证明真实模型选择能力。
- [ ] 实现工具选择、参数正确、依赖满足、任务完成、澄清正确、权限拦截、上下文保持、异常处理指标；同时报告分母、失败数、超时数与逐题轨迹。
- [ ] 输出总耗时、工具次数、重试次数和可取得的 token usage；未知 token 不计为零。工具路径允许等价顺序，不按固定自然语言全文匹配评分。
- [ ] 建议验收门槛：确定性权限/隔离/预算/恢复测试全部通过；真实模型留出集任务完成率至少 90%，工具选择与参数正确率分别至少 95%；任何越权泄露或失败伪报成功都阻断验收。真实模型未运行时这部分明确标“未实测”，不填估计值。
- [ ] 完成 Streamlit 人工演示：本人年假、报销与制度组合查询、缺参追问、周报草稿与确认保存、越权拒绝、重启恢复、超时/失败七类场景。
- [ ] 运行全量 Python 回归；若修改共享 API 事件或 schema，再执行现有前端 typecheck/test/build。更新项目定位和启动命令，单独提交交付材料。

**Validation（新增评测 CLI 的计划命令，实现后才能执行）:**

```powershell
python -m pytest tests -q
python -m eval.run_agent_eval --dataset eval/agent_cases.jsonl --mode deterministic
python -m eval.run_agent_eval --dataset eval/agent_cases.jsonl --mode live
```

**完成标准：** 可从 Streamlit 演示三条主流程和四类边界情况；评测报告能逐题证明实际工具行为与权限、上下文、异常处理结果。

## 执行节奏与停止条件

- 每个任务按“先补可失败的测试 → 最小实现 → 相关回归 → 独立提交”推进；新增文档本身无需编写模拟业务测试。
- 任务 2、3 完成后先验收可信入口和会话；任务 4、5 完成后验收 Agent 任务链；任务 6、7 完成后进行整体验收。
- 每次交付记录改动、验证命令、实际输出和剩余限制。已发现回归必须先修复，再进入依赖任务。
- 如果范围扩大到注册、私有知识库产品、云端 HTTPS、备份体系或 React 新功能，单独列入项目二计划，不混入本轮关键路径。
- 不为拆分项目删除或搬移现有 React、FastAPI、Docker、历史文档与运行数据。
- 本计划基于 2026-10-13 仓库静态检查，尚未执行基线测试、实现新模块或运行真实模型专项评测。
