# 第一版验证记录

本文件只记录实际执行结果，2026-10-12，Windows / Python 3.11.7 / Node 25.9 / Docker 29.7。

| 验证 | 实际结果 |
|---|---|
| `.venv-v1` 按 requirements 安装 | 成功；旧 `.venv` 保留 |
| `python -m pip check` | No broken requirements found |
| `python -m alembic upgrade head` | PostgreSQL 16 专用容器成功 |
| `python -m backend.seed` | 成功，已有账号不会重设密码 |
| 后端完整 pytest（含真实 PostgreSQL checkpoint） | 72 passed (23.76s)，含真实 PostgreSQL |
| 最终 Linux 非 root 镜像完整 pytest | 72 passed (27.43s)，含专用 PostgreSQL；镜像内 pip check 通过 |
| SQLite/PostgreSQL 断开重连与清空 checkpoint | 3 个相关测试通过（含 SSE 背压测试） |
| 前端 typecheck / Vitest / build | 通过；SSE 解析 3 测试 |
| Chromium 浏览器工作流 | 5 passed，37.5s：上传更新停用引用、周报持久化与隔离、停止后恢复历史、首次重复发送锁与周报编辑锁 |
| `docker compose config --quiet` | 成功 |
| 前后端 Linux 镜像构建 | 成功；基础镜像拉取超时后重试恢复，首次后端依赖下载约 36 分钟 |
| Compose 完整启动 | PostgreSQL / 单进程 API / Nginx 成功，数据库与 API healthy |
| 完整 Nginx 入口 API 验收 | prepare / 重启 backend / verify 全部通过：登录、CSRF、跨用户 404、周报保留/编辑、真实 PostgreSQL checkpoint 清空 |
| 完整 Nginx 入口 Chromium 验收 | 重启前、重启后新建浏览器会话均通过：登录、周报读取、第二账号隔离及角色入口 |
| GitHub Actions | 已配置；本地等效检查通过，未推送触发远程运行 |
| 真实 DeepSeek 连接验证 | 后续配置修复后通过：真实认证 API 问答 completed，约 1.97 秒，无工具调用，2 条历史消息持久化 |
| 真实 LLM 质量评测（独立 30 题） | 未执行，未实测 |
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

三张成功页面截图另复制到 `docs/screenshots/` 随项目保存，均来自确定性模型替身验收，不能用作真实模型回答质量证据。

当前依赖产生 LangGraph serializer 与 Chroma/Pydantic 的弃用警告；测试通过不意味着长期无需升级。对性能、模型质量或云端运行不作推断。

## 完整部署验收补充

使用独立 Compose project `codex-ai-fullstack-v1` 和命名卷，测试入口为 `http://127.0.0.1:18080`；README 的默认入口仍为 8080。首次部署验收用 `.env.example` 显式作为 Compose env-file，终端注入独立测试密码，模型 Key 为空。该阶段没有读取或改写用户真实凭证，也没有批量清理文件或卷。

```powershell
# 在独立测试实例中先设置 DEMO_PASSWORD 为该实例的初始化密码。
python tests/compose_smoke.py prepare --base-url http://127.0.0.1:18080
# 使用创建实例时相同的 env-file / project / override 重启 backend。
python tests/compose_smoke.py verify --base-url http://127.0.0.1:18080
```

API 验收脚本使用本机直连，避免环境 HTTP 代理把 loopback 请求转发为 502。Linux 容器启动前实际复现过非 root 用户导入 logger 时的目录权限错误；Dockerfile 已创建并授权 logs 目录，最终镜像的测试和实际启动均通过。生产入口浏览器截图为 `docs/screenshots/compose-reports.png`，展示真实部署的模拟业务数据，不涉及模型生成。

直接依赖由 requirements 固定版本；Windows 全量依赖快照只对应已验证 Windows 环境，传递依赖的 Linux 解析结果单独由实际镜像测试验证。

## 后续模型连接修复

用户报告实际问答失败后，容器日志确认缺少 DEEPSEEK_API_KEY。本机已有 `.env` 配置；在用户授权修复后，仅在进程内读取 Key 并注入重新创建的 backend，不输出或提交凭证，不改写 `.env`，沿用原数据库、账号密码、Origin 和命名卷。随后刷新 Nginx 的后端连接。

通过真实 Nginx/API 发送不含业务数据的连接测试，返回 completed、5 字符回答、无工具调用、约 1.97 秒；历史持久化 2 条消息。此结果只证明当前凭证和基础问答链路可用，不代表知识检索质量、业务工具的真实模型效果或完整 30 题评测。自动审批拒绝了可能发送业务记录的报销查询验证，已采用普通连接测试完成修复验收。
