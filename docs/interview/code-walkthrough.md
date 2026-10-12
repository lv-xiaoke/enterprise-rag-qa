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

审查修复导读：`ReactAgent._recover_incomplete_tools` 回退未配对的中断工具轮；`ToolNode(handle_tool_errors=False)` 让基础设施异常进入脱敏失败路径；启动恢复补建 interrupted 消息。对照 `tests/test_review_regressions.py` 阅读修复前后的失败行为。

## 可以讲清楚的失败案例

一次工具调用由带 tool_calls 的 AIMessage 和匹配 tool_call_id 的 ToolMessage 配对。如果进程在两条消息之间退出，checkpoint 中只剩工具调用；直接追加新问题会产生无效工具历史，下一轮也无法回答。修复是在新一轮开始前检查配对，回退未完成工具轮，保留用户问题和已完成历史。测试先构造这个持久化中断点，再关闭并重新创建 saver，确认下一轮成功且原问题仍在。

这里没有自动重新执行工具，也没有补一条假的成功结果：未来若接入写操作，重复执行可能产生副作用。业务历史仍显示 interrupted，让用户知道上一次没有完成。面试时同时解释 checkpoint 和展示消息表的职责，不能把“页面保留文字”等同于“Agent 恢复了有效状态”。
