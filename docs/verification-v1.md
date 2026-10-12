# 第一版验证记录

本文件只记录实际执行结果，2026-10-12，Windows / Python 3.11.7 / Node 25.9 / Docker 29.7。

| 验证 | 实际结果 |
|---|---|
| `.venv-v1` 按 requirements 安装 | 成功；旧 `.venv` 保留 |
| `python -m pip check` | No broken requirements found |
| `python -m alembic upgrade head` | PostgreSQL 16 专用容器成功 |
| `python -m backend.seed` | 成功，已有账号不会重设密码 |
| 后端完整 pytest（含真实 PostgreSQL checkpoint） | 66 passed (21.23s)，含真实 PostgreSQL |
| SQLite/PostgreSQL 断开重连与清空 checkpoint | 3 个相关测试通过（含 SSE 背压测试） |
| 前端 typecheck / Vitest / build | 通过；SSE 解析 3 测试 |
| Chromium 浏览器工作流 | 3 passed，39.4s：上传更新停用引用、周报持久化与隔离、停止后恢复历史 |
| `docker compose config --quiet` | 成功 |
| Compose 完整构建与启动 | 首次构建因 Docker Hub Node 基础镜像连接超时失败；没有宣称完整容器验收通过 |
| 真实 LLM 生成评测 | 未执行，未实测 |
| 云端部署 | 未执行 |

本机测试命令：

```powershell
$env:PYTHONUTF8='1'
$env:ANONYMIZED_TELEMETRY='False'
python -m pytest tests -q
# 可选专用测试库，不要连接已有生产库：
$env:TEST_POSTGRES_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/TEST_DB'
python -m pytest tests/test_checkpoint_restart.py -q
cd frontend
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Playwright 输出保存在 `frontend/playwright-output/<时间戳>/`，每次新目录避免批量清理。成功截图包括 chat.png、documents.png、reports.png。失败时保存截图与 trace；这些文件不提交 Git。模型替身仅在 `tests/browser_server.py`，生产入口不引用它。

当前依赖产生 LangGraph serializer 与 Chroma/Pydantic 的弃用警告；测试通过不意味着长期无需升级。对性能、模型质量或云端运行不作推断。
