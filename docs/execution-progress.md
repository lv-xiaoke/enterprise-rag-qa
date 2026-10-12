# SDD ledger — plan: docs/superpowers/plans/2026-10-12-ai-fullstack-v1.md

## 执行约束与裁决

- Ruling: 在当前目录的 `codex/ai-fullstack-v1` 功能分支实施，不新建 worktree — 保留用户已确认的未提交计划、已有环境与本地数据，避免复制秘密配置；代价是本目录会直接显示开发改动。
- Ruling: 进度使用本文件保存，不运行依赖 Bash 的技能脚本，也不删除技能临时目录 — Windows 环境及用户禁止批量删除优先；代价是手动记录任务与验证。
- Pre-flight: 任务 2 的身份是任务 3、5、6 的共同入口；统一通过服务端登录会话取得。
- Pre-flight: 任务 3 的 SSE 与任务 4 的联合类型逐字段保持一致；任务 5 引用使用版本 ID 和块 ID。
- Pre-flight: 任务 7 使用任务 3 的独立会话和实际来源，不能再独立检索代替实际证据。
- Pre-flight: 任务 8 单进程部署匹配任务 3 的运行控制和任务 5 的串行处理器。

## 任务 1：complete

- 已核查现有 `.venv`：Python 3.11.7、LangGraph 0.2.50，与全局解释器区分。
- 基线 `pip check` 失败：langchain/community 0.3.7 要求 langsmith <0.2，core 0.3.86 要求 langsmith >=0.3.45；原声明依赖不存在共同解。
- 原测试收集触发 embedding 下载，网络受限时失败；新增 import 边界测试先复现，再移除导入阶段模型构建。
- 已创建专用 `.venv-v1`，现有 `.venv` 保留。
- Docker 经授权检查可访问，服务版本 29.7.2。

## 后续任务

- [x] 任务 1 环境基线
- [x] 任务 2 数据库与鉴权
- [x] 任务 3 持久化聊天
- [x] 任务 4 React 工作台
- [x] 任务 5 文档管理
- [x] 任务 6 个人业务与周报
- [x] 任务 7 可靠性与评测
- [ ] 任务 8 交付与验收
- [x] 任务 9 面试材料

## 集成记录（2026-10-12）

- Task 1: complete — 独立环境安装、pip check、import 边界测试通过。
- Task 2: complete — PostgreSQL Alembic/seed 实跑；鉴权、CSRF、角色、跨用户拒绝测试通过。
- Task 3: complete — 真实图 SSE、并发身份、失败/超时/中断、背压取消、SQLite/PostgreSQL checkpoint 重连与清空通过。
- Task 4: complete — React 独立工程；typecheck、3 个 SSE 测试、build 和浏览器聊天/取消通过。
- Task 5: complete — 真实 Chroma 版本更新、失败保留旧版、重复上传、停用和引用测试通过；浏览器流程通过。
- Task 6: complete — 数据库个人工具与周报 CRUD/归属验证通过；浏览器保存、刷新和第二账号隔离通过。
- Task 7: complete — 评测隔离/实际证据回归通过；独立 30 题按 8/6/6/5/5 编写，真实模型未实测已标明。
- Task 8: partial — Compose config 通过，CI 配置完成；Chromium 3 passed (39.4s)。完整构建 Docker Hub Node 拉取超时；后端独立 Linux 构建进行中。
- Task 9: complete — docs/interview 五份材料、README、原版文档版本说明已完成。
- 集成验证：后端 66 passed (21.23s，含专用 PostgreSQL)；前端 typecheck、3 passed、生产 build 通过。

## 补充裁决

- Ruling: 本地开发默认 SQLite、Compose 默认 PostgreSQL — 降低首次学习运行成本，生产持久化与 PostgreSQL checkpoint 已实测；代价是开发需额外运行 PostgreSQL 集成测试。
- Ruling: 第一版每次检索在锁内重建有效版本 BM25 快照，统一使用 build_retriever — 保证小语料下两路一致性；代价是语料扩大后需要代次缓存优化。
- Ruling: 历史预算用 UTF-8 字节数加消息开销作为保守上界，保持完整工具配对 — 无需额外 tokenizer/下载且限制上下文；代价是可用上下文小于模型真实 token 容量。
- Ruling: 本次先提交集成实现，再提交最终审查修复 — 多个模块共享身份/SSE/版本接口，集成通过后形成可审查基线；代价是提交粒度较原计划大。
- Ruling: 静态 eval CLI 保留用于既有 RAG/Agent 比较，动态知识库由 API/浏览器验证 — 避免将不同数据链路混称端到端模型效果；代价是后续真实动态知识质量仍需专门评测。
