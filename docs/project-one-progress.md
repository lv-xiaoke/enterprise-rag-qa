# Execution ledger — plan: docs/superpowers/plans/2026-10-13-project-one-agent-upgrade.md

- 用户授权：按计划直接实现，并提供演示及讲解材料；明确选择在当前 codex/ai-fullstack-v1 分支实施。
- Pre-flight 2→3：HTTP 客户端复用现有服务端会话身份；内部 thread_id 不进入客户端契约。
- Pre-flight 4→5→6：工具结果状态、流程完成条件和执行轨迹共用 ToolOutcome，避免用中文字符串推测成功。
- Pre-flight 6→7：评测读取真实 API 轨迹，脚本模型仅检验执行器，真实选择能力单独评测。
- Ruling: 用户明确选择当前功能分支，原地实现；不创建 worktree — 保留已有环境与未提交需求文档 — 成本：同一分支包含此前全栈能力。
- Ruling: 用户禁止批量删除，保留执行记录及测试产物，不运行技能的目录清理步骤 — 成本：本地保留少量产物。
- Task 1: baseline complete — 36 passed, 1 skipped (专用 PostgreSQL URL 未设置), 1 依赖弃用告警。Windows 沙箱内 asyncio socketpair 阻塞，沙箱外运行同一命令 3.75 秒通过；非业务代码失败。
- Task 2: 可信入口实现；17 项客户端/认证/配置测试通过。后续 AppTest 已验证实际页面操作。
- Task 3: 9 passed、1 skipped；交错并发、跨用户聊天/取消和已有恢复测试通过。
- Task 4/5: 新增追问、参数契约、证据前置与拒绝路径；先见缺失实现失败，再验证通过。
- Task 6: 工具预算、公开错误分类与持久化轨迹；19 项相关回归通过。新增模型 SDK 隐藏重试限制与迁移兼容测试通过。
- Task 7: 40 场景/46 轮实际认证 API 确定性评测全部达成预期；全量 Python 101 passed、1 skipped；前端类型检查/3 项单测/build 通过。
- Ruling: 预构建图无法在最终输出前强制检查业务证据，认证入口改用 BusinessAgent 显式 StateGraph；ReactAgent 同步适配器保留静态实验兼容 — 成本：保留两种用途不同的适配器，正式界面统一使用新图。
- Ruling: 制度工具直接返回结构化检索证据，最终 respond 节点统一总结，省去工具内部第二次模型总结 — 成本：需在真实模型评测中验证引用与总结质量。
- Ruling: 证据满足后进入无工具绑定的 respond 节点并增量输出；失败前不输出虚构成果 — 成本：第一次正文需等待前置工具完成。
- 已发现并修复：页面模型配置绕过测试替身导致一次意外真实请求；API fixture 现禁用真实凭证，页面测试注入所有模型构造路径。该请求不计入质量结论。
- 当前任务：整体验证及独立代码审查；未执行系统性真实模型评测、未改动既有 runtime 数据、未推送远程。
