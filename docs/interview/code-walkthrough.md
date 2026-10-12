# 从界面追踪到代码

| 操作 | 入口代码 | 关键逻辑 | 验证 |
|---|---|---|---|
| 登录 | `frontend/src/features/auth/Login.tsx` | `api/routes/auth.py` 校验密码、签发随机会话，`backend/auth.py` 验证 Cookie/CSRF | `tests/test_auth.py` |
| 提问 | `frontend/src/features/chat/Chat.tsx` 的 `send` | `api/routes/conversations.py` 的 `chat`、`backend/conversations.py` 的 `reserve_run` | `tests/test_chat_lifecycle.py` |
| SSE | `frontend/src/api/chat-stream.ts` 的 `parseSSE` | UTF-8 解码、跨分片缓存、具名事件；服务端生产者队列与取消 | 前端 SSE 测试、`tests/test_stream_backpressure.py` |
| 工具与身份 | `agent/react_agent.py` 的 `astream_events` | `agent/runtime.py` 请求上下文；`agent/tools/agent_tools.py` 的 `_deny_if_not_self` 与 `_lookup_employee` | `tests/test_agent_tools.py`、`tests/test_api.py` |
| 记忆 | `backend/checkpoints.py` 的 `Checkpoints` | 创建 saver、setup、持久化恢复与按 thread 清空 | `tests/test_checkpoint_restart.py` |
| 上传 | `frontend/src/features/documents/Documents.tsx` | `backend/documents.py` 的 `upload` / `_process` | `tests/test_document_versions.py` |
| 检索/引用 | `KnowledgeService.retrieve` / `source` | 查询有效版本，向量过滤与 BM25 使用同一快照，稳定 chunk ID | `tests/test_retriever_refresh.py`、`tests/test_hybrid_identity.py` |
| 周报保存 | `frontend/src/features/reports/Reports.tsx` | `api/routes/reports.py` CRUD，`backend/reports.py` 归属校验 | `tests/test_reports.py` |
| 启动 | `backend/serve.py`、`compose.yaml` | Alembic → 幂等 seed → 单进程 API；Nginx 不缓冲 SSE | `docs/verification-v1.md` |

先阅读 `api/schemas.py` 的输入契约，再阅读路由，最后阅读工具。特别注意请求体没有当前员工 ID；身份来自服务端会话。即使模型被诱导调用其他员工 ID，工具仍拒绝。

文档版本切换过程：存储新文件 → queued → processing → 切块与写入稳定 ID → 验证 BM25 可构建 → 事务更新 ready 与 active_version_id。失败不动旧指针。查询在同一个锁内取得 active 集合并构建 BM25，Chroma 使用同一 version filter。历史引用保留原版本，登录后可以查看并显示历史标志。

停止过程：浏览器先 POST cancel，再 AbortController 断开流；服务端事件使消费者退出，取消生产者，保存部分正文和 cancelled。同步线程里的外部调用可能继续完成，不能声称撤销了上游费用。异常对用户返回稳定错误码，日志用于定位。

## 三个动手练习

1. 增加一个本人查询字段：从 CSV 初始化模型数据入手，在 `fetch_employee_records` 的 Literal 和 query_map 增加字段；写本人成功、他人拒绝断言。完成后解释为什么仅修改提示词不够。
2. 增加“管理员只能维护自己上传的文档”的规则：从 `KnowledgeService.owned_document` 和路由的 AdminUser 入手，先写两管理员互改失败测试，再把上传者传入服务校验。注意这是产品权限变更，当前版本的管理员共享公共知识管理权。
3. 修改引用展示：从 `Source` 类型、Chat 的引用按钮、`GET /sources` 返回结构入手，显示版本号和页码；保留历史标志、键盘关闭和不可信 Markdown 的安全处理。

验收学习成果：独立讲清一条请求；定位一个错误码的来源；不让 Agent 代写，自己完成上面一个小改动并解释测试。
