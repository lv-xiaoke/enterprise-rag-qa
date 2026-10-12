# 第一版环境基线

目标解释器 Python 3.11。2026-10-12 在 Windows 本机使用 `.venv-v1` 完成独立安装，现有 `.venv` 和全局 Anaconda 环境保留。

原声明 `langchain/community 0.3.7` 与 `core 0.3.86` 的 langsmith 依赖约束没有交集；升级前两者到 0.3.27。`pip check` 实测通过。LangGraph 保留 0.2.50，checkpoint-postgres 锁定 2.0.9；2.0.25 明确警告不兼容旧 LangGraph。SQLite 扩展使用 2.0.11，aiosqlite 锁定 0.21.0；0.22.1 移除了扩展调用的 `Connection.is_alive()`，重启测试曾实际失败。

业务迁移已在 PostgreSQL 16 容器执行；SQLite 与 PostgreSQL 均通过“关闭连接、重新创建 Agent、读取上一轮消息”的 checkpoint 测试。前端使用 React 19、TypeScript 5.9、Vite 7，准确版本见 `frontend/package-lock.json`。

`requirements.txt` 锁定直接依赖；`requirements-lock.windows.txt` 保存本次 Windows 全量环境快照。Linux 镜像按直接依赖安装并实测构建，不把 Windows 专属包当作跨平台锁文件。原环境中的回归结果与新环境结果分开记录。

测试不下载 embedding，不调用真实 LLM。首次真实知识问答会加载 BGE，本地 embedding 首次需要下载模型，随后可使用缓存；启动 API、登录和数据库查询接口本身无需模型 Key。真实问答和总结需要配置 provider 的 Key。

注意：Windows 使用 PostgreSQL 异步 checkpoint 时需 SelectorEventLoop。使用 `python -m backend.serve` 启动；Linux 容器可直接使用 Uvicorn。测试目录与 Playwright 输出保留，不自动批量清理。
