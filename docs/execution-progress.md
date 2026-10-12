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
- [x] 任务 8 交付与验收
- [x] 任务 9 面试材料

## 集成记录（2026-10-12）

- Task 1: complete — 独立环境安装、pip check、import 边界测试通过。
- Task 2: complete — PostgreSQL Alembic/seed 实跑；鉴权、CSRF、角色、跨用户拒绝测试通过。
- Task 3: complete — 真实图 SSE、并发身份、失败/超时/中断、背压取消、SQLite/PostgreSQL checkpoint 重连与清空通过。
- Task 4: complete — React 独立工程；typecheck、3 个 SSE 测试、build 和浏览器聊天/取消通过。
- Task 5: complete — 真实 Chroma 版本更新、失败保留旧版、重复上传、停用和引用测试通过；浏览器流程通过。
- Task 6: complete — 数据库个人工具与周报 CRUD/归属验证通过；浏览器保存、刷新和第二账号隔离通过。
- Task 7: complete — 评测隔离/实际证据回归通过；独立 30 题按 8/6/6/5/5 编写，真实模型未实测已标明。
- Task 8: complete — 前后端 Linux 镜像、完整 Compose 启动、重启前后 API 与新 Chromium 会话验收通过；Linux 非 root 镜像 72 passed (27.43s)。CI 已配置，未远程触发。
- Task 9: complete — docs/interview 五份材料、README、原版文档版本说明已完成。
- 集成验证：后端 66 passed (21.23s，含专用 PostgreSQL)；前端 typecheck、3 passed、生产 build 通过。

## 补充裁决

- Ruling: 本地开发默认 SQLite、Compose 默认 PostgreSQL — 降低首次学习运行成本，生产持久化与 PostgreSQL checkpoint 已实测；代价是开发需额外运行 PostgreSQL 集成测试。
- Ruling: 第一版每次检索在锁内重建有效版本 BM25 快照，统一使用 build_retriever — 保证小语料下两路一致性；代价是语料扩大后需要代次缓存优化。
- Ruling: 历史预算用 UTF-8 字节数加消息开销作为保守上界，保持完整工具配对 — 无需额外 tokenizer/下载且限制上下文；代价是可用上下文小于模型真实 token 容量。
- Ruling: 本次先提交集成实现，再提交最终审查修复 — 多个模块共享身份/SSE/版本接口，集成通过后形成可审查基线；代价是提交粒度较原计划大。
- Ruling: 静态 eval CLI 保留用于既有 RAG/Agent 比较，动态知识库由 API/浏览器验证 — 避免将不同数据链路混称端到端模型效果；代价是后续真实动态知识质量仍需专门评测。

## Final review 与一次修复

独立只读审查基线 11c90d8..56a1285；审查认为无 Critical，有五项 Important，无 Minor。按实际用户影响保留五项等级，均进入一次修复；未进行第二次重复审查。

- Final: fixed 未完成工具 checkpoint 阻塞新提问 — test_restart_with_pending_tool_accepts_next_turn_and_preserves_history RED→GREEN；回退未完成工具轮，保留用户输入与已完成历史，不伪造工具成功、不自动重放副作用。
- Final: fixed 工具异常泄露且运行被当作成功 — test_tool_infrastructure_exception_is_masked_and_run_failed RED→GREEN；ToolNode 不吞基础设施异常，由统一 API 返回脱敏 failed。
- Final: fixed 服务重启历史看不到 interrupted — test_startup_marks_stale_runs_and_processing_documents RED→GREEN；同一恢复事务补建可展示消息。
- Final: fixed 首次发送重复创建/运行 — Chromium first send locks before conversation creation completes RED→GREEN；await 前锁定，创建失败/取消释放。
- Final: fixed 周报修改响应错绑当前编辑对象 — Chromium report mutation locks editor selection until response finishes RED→GREEN；保存/删除期间锁住对象切换。
- Final: Ruling: 线程退出问题由审查暂未定级升级为 Important — 显式屏障测试证明 close 提前返回会允许底层写入越过关闭点，因此修复并等待线程完成；代价是慢 embedding 调用会延长正常关机。
- Final: fixed 入库线程退出 — test_knowledge_close_waits_for_active_ingestion_thread RED→GREEN。
- Final: Ruling: 真实模型质量、费用保持未实测 — 不自动使用未知用户 Key 产生费用；代价是需后续真实质量评测。
- Final: Ruling: 第一版交付本地运行，云端目标未提供 — 不推送或发布到未知目标；代价是当前没有公网演示地址。
- Final: Ruling: 多进程控制、部门 ACL、OCR 与物理回收维持已确认排除范围 — 与第一版单进程和保留历史文件一致；代价是不能宣称这些扩展能力。
- 审查暂不定级的串行查询等待沿用前述 BM25 快照裁决，无新隐藏例外。
- Final suite: 后端 71/71 passed (22.80s，含 PostgreSQL)；Chromium 5/5 passed (37.5s)。无 deferred minors。

- Final suite（追加真实 API 重启路径）：72/72 passed (23.76s)，真实 PostgreSQL；前端 3/3、build 通过；Chromium 5/5。
- 容器进展：官方 Node/Nginx 拉取重试成功，最终前端 Linux 镜像构建成功；后端首次依赖下载进行中。
- 容器修复：Linux 普通用户导入 logger 实测 RED（/app/logs PermissionError）；镜像创建并授权日志目录，隔离容器导入 GREEN。构建上下文排除本机 logs，避免继承属主与旧日志。
- 最终交付：前后端镜像构建成功，完整 Compose 三服务运行；API prepare/verify 与新 Chromium 会话 prepare/verify 均通过，后端容器实际重启。容器测试 72/72 passed，pip check 通过。启动与周报验收不使用模型 Key。
- 验收脚本修复：实际运行暴露本机代理 502 和重复打开 httpx Client；改为显式直连与上下文管理器后 prepare/verify 通过；SPA fallback 改为严格断言 200/HTML/root。
- Final: Ruling: 保留当前功能分支、本地提交与工作目录，不触发合并/推送菜单或清理 — 用户授权本地实现并要求禁止批量删除；代价是远程发布及合并仍需后续安排。
- Final: minor (deferred): 部署截图中，带长串无空格验收标记的周报标题会在侧栏略微越界；不影响保存、读取与隔离，后续补强文本换行。
- 保留已有环境、运行数据、独立验收容器及日志，没有批量删除。
