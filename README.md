# 项目一 · LangGraph 智能体业务助手

当前升级重点是 **Streamlit + LangGraph 的 Agent 可靠性**：可信登录、缺参追问、多步骤工具任务、本人数据权限、会话恢复、工具轨迹和执行预算。已有 React 工作台与部署能力保留。

先读 [项目一讲解与演示](docs/interview/project-one-explainer.md)、[专项评测](docs/project-one-agent-evaluation.md) 和 [升级记录](docs/project-one-progress.md)。

项目一启动：沿用下方 Python 环境、数据库迁移和 seed 步骤，后端执行 `python -m backend.serve`；另一终端激活同一环境后执行 `python -m streamlit run app.py`，访问 `http://localhost:8501`。`API_BASE_URL` 默认 `http://127.0.0.1:8000`；Streamlit 服务端发送的 `APP_ORIGIN` 必须与后端配置一致（默认 `http://127.0.0.1:5173`），无需为 Streamlit 浏览器端关闭 CSRF。

从旧版升级先执行 `python -m alembic upgrade head`，新增工具轨迹字段；迁移已用独立 SQLite 验证保留旧会话和消息，不自动改动已有 runtime。管理员在 Streamlit 上传制度文档，员工账号查询本人数据；周报草稿经编辑和确认后保存。

## 保留的全栈能力

React/TypeScript + FastAPI + LangGraph 的个人全栈项目，支持登录、流式问答、文档版本管理、本人模拟业务查询和周报编辑保存。由 AI 辅助开发，学习与面试材料见 [代码导读](docs/interview/code-walkthrough.md)。

所有企业文档和个人业务记录均为模拟数据。真实模型效果未实测，实际检查结果见 [验证记录](docs/verification-v1.md)。

## 第一版功能

- 服务端会话登录、HttpOnly Cookie、Origin/CSRF 校验，员工和管理员角色。
- 自己的会话、消息和周报；SSE 流式回答、工具状态、取消、失败与重启中断状态。
- PostgreSQL 业务数据和 LangGraph checkpoint；本地开发支持 SQLite。
- 管理员上传 TXT/PDF，异步处理、失败重试、更新成功再激活版本、停用过滤；历史引用保留。
- Chroma 向量 + BM25/RRF 混合检索，两路只使用同一有效版本集合。
- 周报草稿由用户编辑确认后保存；个人查询权限由工具代码校验。

第一版按单进程部署；没有多副本控制、OCR、部门知识 ACL 或真实企业系统对接。Streamlit `app.py` 现已复用同一认证 API 与持久化业务 Agent 图；旧版静态 Python Agent 仅保留实验兼容用途。

## 本地运行（Python 3.11 / Node 22.12+）

首次从仓库根目录执行。保留你已有的 `.env`；需要时参考 `.env.example` 自行配置，切勿把真实 Key 和密码提交到 Git。

```powershell
python -m venv .venv-v1
.\.venv-v1\Scripts\Activate.ps1
$env:PYTHONUTF8='1'
python -m pip install -r requirements.txt
python -m pip check
# 默认使用 SQLite；使用 PostgreSQL 时设置自己的 DATABASE_URL。
$env:DEMO_PASSWORD='替换成至少12位的演示密码'
$env:APP_ORIGIN='http://127.0.0.1:5173'
python -m alembic upgrade head
python -m backend.seed
python -m backend.serve
```

另一个终端：

```powershell
cd frontend
npm ci
npm run dev
```

访问 `http://127.0.0.1:5173`。账号 `admin` 管理公共知识文档，员工账号 `E1001`、`E1002`、`E1003` 查询本人模拟记录；密码为初始化时设置的值。幂等 seed 不覆盖现有账号密码。不要交替使用 localhost 与 127.0.0.1，写请求 Origin 必须与 APP_ORIGIN 完全一致。

问答前由管理员上传 `data/enterprise/` 中的 TXT 文档。默认 `DEEPSEEK_API_KEY` 供对话与总结使用；模型选择见 `config/rag.yml`。本地 BGE embedding 首次需联网下载模型，其后可使用缓存。API 启动、登录和周报 CRUD 不需要模型 Key，缺 Key 的问答会显示生成失败。

Windows PostgreSQL 异步连接需 SelectorEventLoop，`backend.serve` 已配置。不要用多个 Uvicorn worker 运行本版本。真实文件、向量与本地数据库默认保存在 runtime，不能随意清理。

## Docker Compose

先在当前终端设置你自己的 `POSTGRES_PASSWORD`（建议随机字母数字）和 `DEMO_PASSWORD`；不要在版本控制内保存真实值。密码含 URL 特殊字符时 DATABASE_URL 需要编码。

```powershell
$env:POSTGRES_PASSWORD='替换为随机数据库密码'
$env:DEMO_PASSWORD='替换成至少12位的演示密码'
$env:APP_ORIGIN='http://localhost:8080'
docker compose config --quiet
docker compose up --build -d
```

默认同源入口 `http://localhost:8080`，PostgreSQL 不对外映射端口。启动顺序是数据库健康 → Alembic → seed → 单进程 API → Nginx。业务数据与 runtime 使用命名 volume，SSE 代理关闭缓冲。远程生产部署应使用 HTTPS、设置 `COOKIE_SECURE=true` 与实际 APP_ORIGIN，并自行配置入口端口；默认仅绑定本机。

本机已完成前后端 Linux 镜像构建、Compose 启动和重启后的 API/新浏览器会话验收，记录见 [验证记录](docs/verification-v1.md)。尚未部署云端。禁止批量删除文件或卷来解决启动问题。

## 验证与评测

```powershell
python -m pytest tests -q
cd frontend
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

浏览器验收启动独立测试服务和临时数据，使用模型与 embedding 替身，真实执行 HTTP、业务数据库与 Chroma；不调用真实付费模型。每次输出保存在新的 `frontend/playwright-output/<时间戳>`，不自动批量清理。可选设置 `TEST_POSTGRES_URL` 对专用测试库运行真实 PostgreSQL checkpoint 重启和清空测试；CI 也运行该测试。

[评测口径](docs/evaluation-v1.md) 解释独立 30 题测试集、实际证据收集与正确性评分。保留 [原版 RAG 调参实验](docs/legacy-rag-experiments.md)，其中来源文件命中率不等于分块正确率或回答准确率，也不代表新版动态知识库的端到端效果。原版实验工具可能自动清理其临时目录，遵守本仓库禁止批量删除约束时不要直接运行该清理流程。

## 阅读顺序

1. [架构与一分钟介绍](docs/interview/architecture.md)
2. [请求链路、代码入口与三个练习](docs/interview/code-walkthrough.md)
3. [演示脚本](docs/interview/demo-script.md)
4. [面试追问](docs/interview/questions.md)
5. [简历描述与能力边界](docs/interview/resume-evidence.md)
6. [执行计划](docs/superpowers/plans/2026-10-12-ai-fullstack-v1.md) / [执行进度](docs/execution-progress.md)
