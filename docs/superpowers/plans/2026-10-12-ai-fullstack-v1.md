# AI 全栈实习项目第一版完成计划

> **For agentic workers:** 实施时按任务使用 `executing-plans` 技能；只有用户明确选择多 Agent 执行时，才使用 `subagent-driven-development` 技能。使用下方复选框记录进度。本文件只记录计划，不表示功能已经实现或测试已经通过。

**Goal:** 将现有企业知识库 Agent 升级成可以完整演示、稳定复现、便于理解和面试讲解的 AI 全栈应用，支持登录、知识问答、文档管理、个人数据查询和周报保存。

**Architecture:** 保留现有 LangGraph Agent、混合检索和模型工厂，增加独立 React 前端、可信登录和 PostgreSQL 业务持久化。FastAPI 统一承接权限校验、业务接口和 SSE 输出；PostgreSQL 保存业务数据与 Agent checkpoint，Chroma 保存文档向量。第一版以单后端进程部署为目标，文件保存在持久化挂载目录。

**Tech Stack:** React、TypeScript、Vite、FastAPI、SQLAlchemy、Alembic、PostgreSQL、LangGraph、Chroma、pytest、Playwright、Docker Compose。

**Spec:** 依据本聊天中已经提出的第一版方案；范围、流程、数据契约和验收要求在本文件第 1—7 节中完整记录，无需依赖聊天历史阅读。本轮仅写计划，实施代码需另行开展。

## 1. 目标、边界与全局约束

- 首要目标是近期实习投递所需的完整项目证据，以及用户对代码、架构与实现的理解。
- 采用增量改造，保留现有 AI 核心和有价值的测试；只进行本次功能所必需的重构。
- 禁止批量删除文件或目录。禁止 `del /s`、`rd /s`、`rmdir /s`、`Remove-Item -Recurse`、`rm -rf`；需要删除文件时，一次只操作一个明确路径的文件。禁止通过脚本、测试清理或工具封装绕过该限制。涉及批量清理时由用户手动处理。
- 不修改全局 Python 环境。首先核查已有 `.venv`；不覆盖或删除用户的现有环境、配置、数据和未提交修改。
- 不读取、打印或提交 `.env` 中的密钥。仓库只提交环境变量示例，真实模型调用从运行环境读取 Key。
- 前后端生产部署使用同源入口，第一版后端为单进程；不宣称支持多副本、高可用或大规模并发。
- 业务个人记录继续使用模拟数据，并在界面、README 和面试材料中说明。
- 第一版不增加多 Agent 产品功能、MCP、微调、Kubernetes、复杂消息队列或多租户平台。
- Python 以 3.11 作为第一版复现目标。现有依赖能否在该版本安装与运行，由任务 1 实测确认；不能直接把当前全局解释器的结果作为项目结论。
- 模型 SDK、LangGraph 与 checkpoint 扩展必须经过兼容性验证后统一锁定。前端保存 npm lockfile，不使用未经验证的版本组合。
- 新增接口使用 `/api` 前缀。第一版界面全部调用这些接口，Streamlit 保留为辅助演示入口。
- 默认执行方式为当前 Agent 按依赖顺序实施，不默认启动子 Agent。

## 2. 第一版必须完成的业务流程

### 2.1 登录与历史会话

1. 使用初始化的员工账号或管理员账号登录。
2. 创建会话、提问、查看历史、切换会话、清空指定会话。
3. 刷新浏览器、退出后重新登录、重启服务后，可以读取自己的已保存历史。
4. 用户不能通过修改员工 ID、会话 ID、消息 ID 或周报 ID 访问别人的数据。

### 2.2 知识问答与文档管理

1. 管理员上传 TXT/PDF，查看文档处理状态和失败原因。
2. 文档处理完成后，员工提问并收到流式回答、工具状态和可查看的引用。
3. 管理员更新同一文档；新版本处理成功后才替换当前有效版本。
4. 停用的文档和旧版本不再参与后续检索。已经保存的历史引用仍标明原版本；查看内容时重新检查访问权限。

### 2.3 个人查询与周报

1. 员工询问本人的年假、报销或项目情况，Agent 调用受权限约束的数据库工具。
2. 员工生成周报，在编辑页面修改后保存。
3. 员工可以分页查看、编辑和删除自己的周报，不能访问其他员工周报。

## 3. 第一版验收标准

| 维度 | 必须满足的结果 |
|---|---|
| 功能闭环 | 三个业务流程都能通过浏览器完成，不依赖手动修改数据库 |
| 身份安全 | 登录身份由服务端会话确定；业务请求不能自行指定当前员工 |
| 用户隔离 | 两个账号之间的会话、消息、业务记录和周报访问受服务端限制 |
| 持久化 | 刷新页面和正常重启服务后历史数据仍可读取，Agent 可以恢复已提交对话状态 |
| 生成状态 | 成功、失败、已取消和服务重启中断有明确记录，不能把错误当作成功答案 |
| 文档一致性 | 新文档可检索，更新成功后使用新版本，停用后不再召回 |
| 工程交付 | 干净环境能够按 README 完成安装、迁移、初始化、启动和核心测试 |
| 演示证据 | 提供操作脚本、截图或录屏，以及真实测试和评测结果 |
| 面试理解 | 用户能沿一次请求定位前端、接口、鉴权、Agent、工具、数据库和引用代码 |

## 4. 现状与实施前核查

现有代码已经包含 `agent/react_agent.py`、`agent/tools/agent_tools.py`、`rag/`、`model/factory.py`、`api/server.py`、`app.py`、`eval/` 和 `tests/`。

已观察到的缺口：

- API 接受客户端提供的 `employee_id`，缺少真实认证；会话操作缺少所属用户校验。
- Agent 使用内存 checkpoint；员工业务数据来自 CSV。
- Streamlit 直接调用 Python 业务代码，尚无独立 TypeScript 前端。
- 文档入库缺少完整的版本切换流程；混合检索使用创建时的内存索引快照。
- 模型与检索配置存在全局可变对象，需要明确配置作用域。
- 检索评测按来源文件名命中计分，不能等价解释为分块正确率或回答准确率。

此前在默认全局解释器中检查时，工具层 15 个测试通过，首个 Agent 流式测试因 LangGraph 参数不兼容失败；API 测试因缺少 `langchain-chroma` 无法收集。当时全局 LangGraph 是 1.2.0，项目声明的是 0.2.50。该结果只说明当时环境与项目声明不一致，不表示已有 `.venv` 或正确依赖环境的结果。

## 5. 文件职责与目录规划

以下为计划中的文件，不表示这些文件目前全部存在。路径相对仓库根目录。

```text
frontend/
  package.json、package-lock.json、vite.config.ts
  src/
    api/client.ts                 HTTP 请求、Cookie、错误与 CSRF 处理
    api/chat-stream.ts            POST SSE 读取与解析
    types/api.ts                  前后端契约类型
    features/auth/                登录页面与当前用户状态
    features/chat/                会话列表、消息、工具状态与引用
    features/documents/           管理员文档操作与处理状态
    features/reports/             周报列表与编辑
  tests/chat-stream.test.ts       SSE 分片解析测试
  e2e/core-flows.spec.ts          浏览器核心流程
api/
  server.py                       应用创建、生命周期、路由装配
  dependencies.py                 当前用户、角色、数据库依赖
  routes/auth.py                  登录、退出、当前用户、CSRF
  routes/conversations.py         会话、消息、生成运行接口
  routes/documents.py             文档与引用访问接口
  routes/reports.py               周报接口
  schemas.py                     请求、响应与事件结构
backend/
  settings.py                     从环境变量读取服务配置
  db.py                           数据库连接与事务边界
  models.py                       第一版业务表
  auth.py                         密码哈希、登录会话与 CSRF
  conversations.py                会话与生成运行管理
  documents.py                    文件保存、版本状态与入库编排
  reports.py                      周报所属用户校验与 CRUD
  seed.py                         幂等初始化账号和模拟记录
agent/
  react_agent.py                  Agent 运行与持久化 checkpoint
  runtime.py                      单次运行身份、配置、来源与预算
  tools/agent_tools.py            数据库业务工具
rag/
  vector_store.py                 稳定分块 ID、版本化入库
  hybrid_retriever.py             有效版本过滤、索引刷新
  rag_service.py                  检索、生成、结构化引用
alembic.ini、migrations/           数据库迁移
tests/                            原有回归测试与新增集成测试
deploy/nginx.conf                 同源入口与 SSE 代理设置
Dockerfile、frontend/Dockerfile
compose.yaml
.github/workflows/ci.yml
docs/interview/                   架构、代码导读、演示与问答材料
```

`backend/` 保存普通业务能力，`agent/` 与 `rag/` 保存 AI 能力，`api/` 负责对外契约和入口。第一版不为每张表建立多层抽象，也不引入通用插件系统。

## 6. 数据模型与关键契约

### 6.1 数据表

| 表 | 核心字段与关系 |
|---|---|
| `users` | UUID、登录名、密码哈希、角色、员工 ID；登录名和员工 ID 唯一 |
| `auth_sessions` | 随机会话凭证的哈希、用户 ID、过期时间、撤销时间；数据库不保存原始凭证 |
| `conversations` | UUID、所属用户 ID、标题、创建时间、更新时间 |
| `messages` | UUID、会话 ID、角色、正文、生成状态、引用 JSON、创建时间 |
| `chat_runs` | UUID、会话 ID、状态、取消标志、错误码、耗时、用量、开始及结束时间 |
| `documents` | UUID、展示名称、当前有效版本 ID、是否启用、上传用户 ID |
| `document_versions` | UUID、文档 ID、版本序号、内容哈希、存储路径、处理状态、错误码 |
| `employee_records` | 员工 ID、部门、年假余额、报销、项目及周报素材；由现有 CSV 初始化 |
| `weekly_reports` | UUID、所属用户 ID、标题、正文、创建时间、更新时间 |

为所属用户和列表排序字段建立组合索引。分页使用 `limit` 和 `offset`，默认 20 条，最大 100 条。业务表与 LangGraph checkpoint 表各司其职，页面展示不直接读取 checkpoint 内部结构。

### 6.2 登录与权限

- 登录凭证使用服务端随机会话，通过 HttpOnly Cookie 传输；生产 HTTPS 开启 Secure，SameSite=Lax。
- `GET /api/auth/csrf` 发放与 Cookie 绑定的 CSRF token；包括登录在内的写请求携带 `X-CSRF-Token`，服务端同时验证来源与 token。
- `GET /api/auth/me` 返回当前用户；`POST /api/auth/login` 建立会话，`POST /api/auth/logout` 撤销会话。
- 未登录返回 401，已登录但无管理员权限返回 403；他人拥有的资源统一返回 404，避免泄露资源是否存在。
- 普通员工只能访问自己的业务数据。管理员可以管理公共知识文档，不因此获得其他员工的聊天或个人记录权限。
- 新版 `/api` 接口不保留绕过认证的旧 `/chat` 和 `/employees` 入口；旧路由停用，README 更新调用示例。

### 6.3 核心接口

| 接口 | 作用 |
|---|---|
| `GET /api/health` | 存活检查，不暴露密钥或内部地址 |
| `GET /api/ready` | 数据库与必要存储就绪检查，不调用付费模型 |
| `POST /api/conversations` | 创建当前用户会话 |
| `GET /api/conversations` | 分页列出当前用户会话 |
| `GET /api/conversations/{id}/messages` | 分页读取所属会话消息 |
| `POST /api/conversations/{id}/chat` | 提交问题并返回 SSE；请求体只包含 `message` 和 `client_request_id` |
| `POST /api/chat-runs/{id}/cancel` | 取消当前用户的生成任务 |
| `DELETE /api/conversations/{id}/messages` | 清空所属会话消息与 checkpoint；生成中返回 409 |
| `POST /api/documents` | 管理员首次上传文档 |
| `GET /api/documents` | 管理员分页查看文档、版本与状态 |
| `POST /api/documents/{id}/versions` | 管理员上传新版本 |
| `POST /api/documents/{id}/retry` | 管理员重试失败版本 |
| `PATCH /api/documents/{id}` | 管理员启用或停用文档 |
| `GET /api/sources/{version_id}/{chunk_id}` | 验证权限后返回引用原文，不暴露本机路径 |
| `POST /api/weekly-reports` | 保存当前用户周报 |
| `GET /api/weekly-reports` | 分页列出当前用户周报 |
| `GET /api/weekly-reports/{id}` | 读取所属周报 |
| `PATCH /api/weekly-reports/{id}` | 编辑所属周报 |
| `DELETE /api/weekly-reports/{id}` | 删除一条所属周报 |

普通接口错误统一为 `{"error":{"code":"...","message":"...","request_id":"..."}}`。客户端看到可理解的提示，详细异常留在服务日志，不把原始堆栈和密钥发给客户端。

### 6.4 聊天状态与 SSE

```typescript
type RunStatus = "running" | "completed" | "failed" | "cancelled" | "interrupted";
type Source = {
  document_id: string;
  version_id: string;
  chunk_id: string;
  title: string;
  page: number | null;
  excerpt: string;
};
type ChatEvent =
  | { type: "start"; run_id: string; conversation_id: string }
  | { type: "token"; content: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; content: string }
  | { type: "sources"; sources: Source[] }
  | { type: "error"; code: string; message: string }
  | { type: "done"; run_id: string; status: RunStatus };
```

- SSE 保留具名 `event:` 和 JSON `data:`，前端解析后转换为上述联合类型。
- 使用 `fetch` 读取 POST 响应流，解析器必须处理跨网络分片的事件、UTF-8 字符和多事件合并。
- 后端先校验身份与会话归属，再开始流式响应。未开始流时使用 HTTP 错误；已经开始流时发送 `error` 和带状态的 `done`。
- 同一会话只允许一个进行中的生成任务，并发提交返回 409。`client_request_id` 在用户与会话范围内去重，重复请求不再次调用模型。
- 用户主动取消先发送取消请求，再关闭浏览器响应流；后端停止后续模型/工具步骤并保存状态。上游无法立即中断时，不承诺已经撤销其费用。
- 网络断开时尽力取消运行并保存已生成内容。服务启动时将遗留 `running` 运行标记为 `interrupted`。
- Agent 运行包含显式用户、会话、模型配置和来源集合。跨线程/任务传递必须有测试，不依赖子任务修改 ContextVar 自动回传给父任务。
- 初始总超时 120 秒，图执行 `recursion_limit=20`，前端问题最多 2000 字；历史上下文按配置的 token 预算裁剪，保留系统消息与完整的工具调用/结果配对。用量缺失时记录为未知，不能记为零。

### 6.5 文档处理与版本一致性

- 单文件最大 10 MiB，仅允许 TXT/PDF；TXT 使用 UTF-8，无法解码时明确失败。PDF 无可提取文本时明确提示暂不支持 OCR。
- 服务端生成存储文件名，用户原始文件名只用于展示。同内容重传通过内容哈希识别，不重复建立相同版本。
- 状态为 `queued → processing → ready/failed`；文档停用属于文档层状态，不通过删除文件实现。
- 第一版使用数据库记录任务，加单进程串行文档处理器。启动时恢复 `queued`，将遗留 `processing` 标记为失败并允许显式重试；解析与 embedding 不阻塞 HTTP 事件循环。
- 分块 ID 由版本 ID 与块序号确定，向量写入使用幂等 ID；分块元数据包含文档 ID、版本 ID、块 ID、页码和可见范围。
- 新版本先完整写入并验证，再更新 PostgreSQL 的有效版本指针；失败时旧版本继续生效。
- 检索读取一份有效版本快照，向量召回与 BM25 都限制在相同快照，避免过期内容挤占 top-k。每次版本激活或文档停用后刷新索引；刷新失败记录错误，禁止静默继续使用错误快照。
- 第一版只支持内部员工共享知识文档及管理员维护，不承诺部门级或多租户 ACL；引用接口仍检查登录与可见范围。旧版本只用于已授权历史引用，不参加新检索。
- 旧版本文件与向量保留，物理回收不属于第一版，避免批量删除和更新失败后的不可恢复状态。

## 7. Review Focus：重点失败场景

| 场景 | 预期行为 | 测试归属 |
|---|---|---|
| 修改会话、消息、周报或运行 ID | 其他账号不能读取、清空、取消或修改 | 任务 2、3、6 |
| 重复点击发送、生成中切会话或刷新 | 不重复调用模型；消息和状态有明确归属 | 任务 3、4 |
| SSE 在汉字中间或事件中间分片 | 正确恢复文本和事件，不乱码、不丢事件 | 任务 4 |
| 新版本入库失败或服务处理中重启 | 旧版本仍有效，处理任务可识别并重试 | 任务 5 |
| 没有 Key、模型超时、工具异常、资料无答案 | 各自明确失败或拒答；错误不伪装成正常答案 | 任务 1、3、7 |

## 8. 实施任务与检查点

每个功能任务按“先写关键行为测试 → 确认失败原因 → 最小实现 → 定向测试与相关回归 → 检查差异”的顺序执行。文档、样式等低影响可逆修改不机械套用 TDD。每项完成后记录实际命令与结果；只有通过验收的成果才可进入简历。提交 Git 时仅暂存该任务的明确文件，不混入用户已有修改。

### 任务 1：复现现有环境与建立基线

**文件：**核查 `.venv`、`requirements.txt`、`.env.example`、`README.md`；新增 `docs/environment-baseline.md`，修改 `.gitignore` 忽略专用环境 `.venv-v1/`。

**输入：**现有仓库与依赖声明。**输出：**可重复创建的隔离环境、经过验证的依赖版本、现有测试真实结果。

- [ ] 检查 Git 状态、Python 解释器、已有虚拟环境，以及 Node/npm/Docker 可用性；记录结果，不覆盖已有环境。
- [ ] 确认 `.venv-v1` 路径未被占用后，使用 Python 3.11 创建本次专用虚拟环境；路径已占用时先核查用途和兼容性，不直接覆盖或删除。
- [ ] 验证现有锁定依赖能否安装，特别检查 LangChain、LangGraph、Chroma 与数据库 checkpoint 扩展的兼容性。
- [ ] 为纯业务与接口测试提供假模型；测试收集不得要求真实 Key 或下载 embedding。将外部模型与重型存储的初始化移入可替换的装配边界。
- [ ] 在目标隔离环境运行原有 `tests/`，逐项区分依赖问题和代码问题，修复影响第一版的基线失败。
- [ ] 记录实际测试数量、通过/失败项和启动结果。后续再生成完整锁定文件，不能用手写“已通过”替代执行证据。

**验证命令：**Windows PowerShell 中执行 `& .\.venv-v1\Scripts\python.exe -m pip check`、`& .\.venv-v1\Scripts\python.exe -m pytest tests/ -q`。后续任务中的 `python` 均指该专用环境解释器；运行前审查测试及清理钩子，确保符合禁止批量删除要求。

**验收：**可从安装说明得到一致的依赖环境；没有 Key 时仍能收集并执行假模型测试；真实调用失败有清晰说明。

### 任务 2：数据库、账号和服务端权限

**文件：**新增 `backend/settings.py`、`backend/db.py`、`backend/models.py`、`backend/auth.py`、`backend/seed.py`、`api/dependencies.py`、`api/routes/auth.py`、`api/schemas.py`、`alembic.ini`、`migrations/`、`tests/test_auth.py`、`tests/test_resource_ownership.py`；修改 `api/server.py`、`.env.example`、依赖清单。

**输入：**任务 1 的依赖基线及第 6 节数据/登录契约。**输出：**可迁移业务表、当前用户依赖、员工/管理员种子账号。

- [ ] 编写登录成功、错误密码、过期/撤销会话、CSRF 缺失、非管理员访问和跨用户资源访问测试，先确认其失败。
- [ ] 建立数据库表与索引，使用 Alembic 迁移；种子导入幂等，多次执行不重复创建数据。
- [ ] 实现密码哈希、随机服务端登录会话、Cookie、CSRF 与角色校验。
- [ ] 将 CSV 内容导入员工业务表，员工 ID 从当前登录用户映射取得。
- [ ] 停用旧的匿名聊天和员工列表入口；`/api/health` 与 `/api/ready` 无需 Key。
- [ ] 运行 `python -m pytest tests/test_auth.py tests/test_resource_ownership.py -q`，确认没有越权或凭证泄露；记录迁移与种子命令。

**接口检查示例：**

```python
def test_employee_cannot_manage_documents(employee_client):
    response = employee_client.get('/api/documents')
    assert response.status_code == 403
```

`employee_client` 是测试中建立真实登录会话的 httpx 客户端 fixture，不能通过直接注入管理员身份绕过鉴权链路。

**验收：**两个员工与一个管理员可登录；错误身份、无权限和跨用户资源返回符合契约的错误；凭证和密码不出现在日志中。

### 任务 3：持久化聊天与可取消生成

**文件：**新增 `backend/conversations.py`、`agent/runtime.py`、`api/routes/conversations.py`、`tests/test_chat_persistence.py`、`tests/test_chat_lifecycle.py`；修改 `agent/react_agent.py`、`agent/tools/agent_tools.py`、`model/factory.py`、`rag/rag_service.py`、原有 Agent/API 测试。

**输入：**当前用户、会话表、消息表、运行表和第 6.4 节事件契约。**输出：**鉴权后的 POST SSE、历史读取、取消和持久化 checkpoint。

- [ ] 写会话归属、服务重建恢复、重复请求去重、同会话并发 409、取消、超时和重启中断测试。
- [ ] 实现会话与消息 CRUD；消息、运行和 checkpoint 的生命周期必须明确，不在整个模型调用期间持有业务数据库事务。
- [ ] 使用已验证兼容的 PostgreSQL checkpointer；只在服务端生成并绑定 checkpoint 的 thread 标识，不能让客户端任意指定。
- [ ] 将用户身份、配置、调用预算、检索来源放入单次运行上下文；工具读取当前身份后访问数据库，不接受模型替换身份。
- [ ] 实现 SSE 状态、可取消运行、幂等请求、异常回滚与清空会话处理；重启后将遗留运行标记为中断。
- [ ] 执行 `python -m pytest tests/test_chat_persistence.py tests/test_chat_lifecycle.py tests/test_agent_tools.py tests/test_agent_stream.py -q`，补跑现有相关 API 回归。

**接口检查示例：**

```python
def test_other_user_cannot_read_messages(user_b_client, user_a_conversation):
    response = user_b_client.get(
        f'/api/conversations/{user_a_conversation.id}/messages'
    )
    assert response.status_code == 404
```

**验收：**真实模型可用时能连续问答；假模型下能完整验证恢复、错误与取消；A 用户不能读取或取消 B 用户的运行。

### 任务 4：独立 React 前端与聊天工作台

**文件：**新增 `frontend/` 中的 Vite 配置、API 客户端、类型、登录与聊天模块、SSE 解析测试；新增 `frontend/e2e/auth-chat.spec.ts`。

**输入：**任务 2、3 的接口和统一错误/SSE 契约。**输出：**可登录、查看历史、流式提问和取消的浏览器工作台。

- [ ] 建立 Vite/React/TypeScript 工程，提供登录页、受保护路由、会话列表和聊天页，保存依赖 lockfile。
- [ ] API 客户端统一携带 Cookie 与 CSRF；401 引导重新登录，403/404/409 显示对应提示。
- [ ] 先测试 SSE 的跨分片事件、UTF-8、结束时残留缓冲和错误事件，再实现解析器。
- [ ] 展示 Markdown、工具执行状态、引用和消息状态；Markdown 禁止直接执行模型返回的 HTML。
- [ ] 实现停止生成、切换会话、刷新恢复、网络失败和空数据状态；切会话后旧流不得写进新会话。
- [ ] 提供 `typecheck`、`test`、`build` 和 `test:e2e` npm 脚本；执行 `npm run typecheck`、`npm run test`、`npm run build`，运行登录与问答浏览器测试。

**验收：**通过页面完成登录、连续问答、切会话、取消与历史查看；前端不直接调用 Python 内部函数。

### 任务 5：文档管理与版本化检索

**文件：**新增 `backend/documents.py`、`api/routes/documents.py`、`tests/test_documents.py`、`tests/test_document_versions.py`、`tests/test_retriever_refresh.py`、前端文档模块；修改 `rag/vector_store.py`、`rag/hybrid_retriever.py`、`rag/rag_service.py`、相关迁移。

**输入：**管理员身份、文档/版本表、持久化文件目录。**输出：**上传、状态、重试、有效版本切换和授权引用接口。

- [ ] 写文件限制、同名不同内容、同内容重传、更新失败保留旧版、停用过滤、索引刷新及处理重启测试。
- [ ] 实现受限上传与数据库任务状态，文件名服务端生成；解析与 embedding 放在不阻塞事件循环的执行路径。
- [ ] 使用稳定 chunk ID 幂等写入；新版本验证成功后激活，旧版本保留且不参加新检索。
- [ ] 向量与 BM25 使用同一有效版本快照；刷新与激活过程保证并发查询不会混入旧版本。
- [ ] 前端实现文档列表、上传、版本状态、错误查看、重试与启停；引用接口不向客户端暴露磁盘路径。
- [ ] 执行 `python -m pytest tests/test_documents.py tests/test_document_versions.py tests/test_retriever_refresh.py tests/test_ingest_ledger.py -q`，通过浏览器验证上传到回答的完整流程。

**验收：**上传内容可被引用；更新成功后使用新内容；失败时旧版可用；停用后不召回；无权限用户无法管理文档。

### 任务 6：个人业务工具与周报编辑保存

**文件：**新增 `backend/reports.py`、`api/routes/reports.py`、`tests/test_reports.py`、前端周报模块；修改 `agent/tools/agent_tools.py` 和个人数据测试。

**输入：**已认证用户、员工模拟记录、Agent 生成结果。**输出：**本人数据查询及周报创建、列表、读取、编辑和单条删除。

- [ ] 写本人可查询、他人被拒绝、周报分页与 CRUD 所属用户检查测试。
- [ ] 工具查询 PostgreSQL 记录，保留现有查询类型约束；查询与权限判断都不依赖提示词。
- [ ] 实现周报接口，所属用户取自登录会话，不能通过请求体覆盖。
- [ ] 聊天结果提供“编辑并保存为周报”入口，打开编辑页后由用户明确保存，避免将任意模型输出自动写为正式周报。
- [ ] 执行 `python -m pytest tests/test_reports.py tests/test_agent_tools.py tests/test_resource_ownership.py -q`；浏览器验证生成、编辑、保存、重登读取及跨账号拒绝。

**验收：**模拟业务记录可被正确查询；周报可编辑保存；两个账号的数据彼此隔离。

### 任务 7：AI 可靠性与真实评测

**文件：**修改 `eval/run_eval.py`、`eval/metrics.py`、`eval/golden_set.jsonl`、Agent 预算与模型配置；新增 `eval/test_set.jsonl`、`tests/test_eval_isolation.py`、`docs/evaluation-v1.md`。

**输入：**已完成的真实业务链路与原有检索实验。**输出：**无会话污染、基于实际证据的评测结果及边界说明。

- [ ] 为独立题创建独立会话、设置测试身份，并验证题目之间不会共享上下文。
- [ ] 忠实度判断使用该次 Agent 实际读取的来源，不另行检索一批资料充当证据；同时加入参考答案正确性检查。
- [ ] 保留既有分块实验。新增独立的 30 题测试集：同义改写 8 题、数字细节 6 题、跨文档 6 题、无答案 5 题、权限拒绝 5 题；不得根据该测试集反复调参。
- [ ] 检索题标注有效文档版本和证据片段；权限题通过业务授权测试验证，不能仅凭模型说“拒绝”认定安全。
- [ ] 记录回答正确性、引用支持、拒答、TTFT、总耗时和可获得的 token 用量；区分冷启动、热启动及本地硬件条件。
- [ ] 运行 `python -m pytest tests/test_eval_isolation.py -q`；有可用 Key 后再执行真实生成评测，记录样本、模型、配置、时间和失败项。未执行的指标明确写“未实测”。

**验收：**能展示至少一个失败案例及修复证据；不将来源文档命中率包装为回答准确率，不虚构成本、并发或质量提升。

### 任务 8：容器、CI 与浏览器验收

**文件：**新增 `Dockerfile`、`frontend/Dockerfile`、`compose.yaml`、`deploy/nginx.conf`、`.github/workflows/ci.yml`、`frontend/e2e/core-flows.spec.ts`；更新 README 与环境变量示例。

**输入：**已验证的前后端构建、迁移、初始化和核心测试命令。**输出：**统一同源入口、一键启动方式和自动检查。

- [ ] Compose 包含 PostgreSQL、单进程 API、前端/Nginx；挂载数据库、文件和 Chroma 持久化目录。
- [ ] 明确迁移、幂等种子与服务启动顺序，数据库就绪后再启动 API；演示密码从环境读取，不写入代码。
- [ ] 配置 SSE 代理不缓冲、适当超时与健康检查；生产 Cookie 使用 HTTPS 安全设置。
- [ ] CI 运行隔离的假模型后端测试、前端类型检查、前端测试和构建，不依赖真实 Key。
- [ ] Playwright 覆盖两账号登录、连续问答、跨账号隔离、上传及更新文档、周报保存；截图和 trace 保留在独立输出目录，不使用批量删除清理步骤。
- [ ] 执行 `docker compose config`、构建与启动，在新浏览器会话验证重启恢复；记录真实命令与结果。

**验收：**另一台满足运行条件的机器可按 README 启动。可用服务器及部署权限确定后发布演示环境；未部署时只交付本地可运行版与录屏，不把线上地址写成已完成。

### 任务 9：代码导读、演示与面试材料

**文件：**新增 `docs/interview/architecture.md`、`docs/interview/code-walkthrough.md`、`docs/interview/demo-script.md`、`docs/interview/questions.md`、`docs/interview/resume-evidence.md`；按最终实现更新现有面试讲解文档。

**输入：**最终实现、实际测试结果、真实评测与演示记录。**输出：**用户能够学习、复述并定位代码的材料。

- [ ] 按最终代码绘制请求链路和数据模型；所有代码位置使用实际存在的文件和符号。
- [ ] 每个模块解释解决的问题、入口代码、数据流、取舍、失败场景和测试证据。
- [ ] 准备一分钟介绍、五分钟架构讲解，以及鉴权、SSE、Agent、RAG、数据库和部署追问。
- [ ] 编写演示脚本：登录 → 上传 → 问答与引用 → 个人查询 → 周报保存 → 换账号验证隔离。
- [ ] 准备三个小改动练习：增加一个个人查询字段、调整一个权限规则、修改一个引用展示组件，并提供代码定位线索。
- [ ] 简历描述只写已完成且可验证的能力；注明个人项目、模拟数据、AI 辅助开发方式和评测范围。

**验收：**用户能从浏览器操作追踪到后端、Agent、工具和数据库，并完成一项小修改；材料不包含不存在的功能或未经验证的指标。

## 9. 执行依赖与阶段成果

```text
任务 1 环境基线
  → 任务 2 数据库与鉴权
  → 任务 3 持久化聊天
  → 任务 4 React 工作台
  → 任务 5 文档管理
  → 任务 6 个人业务与周报
  → 任务 7 可靠性与评测
  → 任务 8 交付与验收
  → 任务 9 面试材料
```

- **阶段 A：**任务 1—4 完成，得到可登录、可持久化、前后端独立的 AI 聊天应用。
- **阶段 B：**任务 5—6 完成，三个业务流程全部闭环。
- **阶段 C：**任务 7—9 完成，形成具备运行、验证与讲解证据的第一版。

近期投递可先基于已完成阶段准备材料，同时继续推进；不能把阶段 A 的成果描述成阶段 C 已全部交付。不承诺未经验证的固定工期，每个阶段结束记录剩余阻碍和真实进度。

## 10. 实际执行记录（2026-10-12）

| 任务 | 状态 | 实际修改文件 | 实际验证与结果 | 剩余限制 |
|---|---|---|---|---|
| 1 环境基线 | 完成 | requirements、独立环境、import 边界 | pip check 通过 | Windows 全量快照非跨平台锁文件 |
| 2 数据库与鉴权 | 完成 | backend、migrations、auth 路由 | PostgreSQL 迁移/seed、鉴权与 CSRF 测试通过 | 演示账户，非用户注册平台 |
| 3 持久化聊天 | 完成 | conversations、runtime、checkpoints | SQLite/PostgreSQL 重连/清空、并发隔离、失败/超时/中断/背压测试通过 | 单进程运行控制 |
| 4 React 前端 | 完成 | frontend/src 与 SSE 测试 | typecheck、3 个单测、build、浏览器流程通过 | 真实模型流效果未实测 |
| 5 文档管理 | 完成 | backend/documents、文档路由/界面 | Chroma 版本/重复/失败/停用测试及浏览器流程通过 | 每次检索重建小语料 BM25，无 OCR |
| 6 个人业务与周报 | 完成 | 数据库工具、周报路由/界面 | 工具授权、CRUD/隔离及浏览器持久化通过 | 业务记录为模拟数据 |
| 7 评测可靠性 | 完成 | eval、独立 30 题、隔离回归 | 实际工具证据、独立线程、来源 ID 回归通过 | 真实模型指标未实测 |
| 8 容器与 CI | 完成 | Dockerfile、Compose、Nginx、CI、Playwright | 前后端 Linux 构建与 Compose 启动通过；重启前后 API/新 Chromium 会话通过；Linux 72 passed | CI 已配置，未远程触发；没有云端部署 |
| 9 面试材料 | 完成 | docs/interview、README | 依据实际代码编写五份材料与练习 | 用户仍需亲自学习与练习 |

完整记录见 `docs/execution-progress.md` 和 `docs/verification-v1.md`；最终后端 Windows/Linux 各 72 passed、前端 3 passed、Chromium 5 passed，typecheck/build 与完整 Compose 重启验收通过。独立审查的五项 Important 及入库线程退出问题均已修复并回归，无延期 Minor。原计划中的逐步复选框保留为实施检查清单，完成状态以本表和最终验证记录为准；真实模型评测、云端发布及用户学习验收分别保留明确边界。
