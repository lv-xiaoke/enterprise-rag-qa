# 项目一专项验证与评测口径

## 本次已验证

- 2026-10-13 全量 Python 测试：101 passed、1 skipped。PostgreSQL 专用测试库未配置，因此本次未重验 PostgreSQL 集成；存在 LangGraph/Chroma 的依赖弃用告警。
- Streamlit AppTest 实际执行登录、查询、历史轨迹回看、草稿确认保存和退出；HTTP 边界使用本地 transport，保留真实 API、SQLAlchemy 数据库和 LangGraph，模型使用替身。
- SQLite 迁移测试从 0001 升到 0002，保留已有消息与运行记录。
- React 前端 typecheck、3 项单元测试和 build 通过；本轮不扩展 React 产品功能。
- 确定性专项评测：40 个固定场景，46 轮交互，预期行为全部达成。结果保存在 `runtime/agent-eval/20261013-141140-107d84/results.json`。

## 这些结果代表什么

评测通过认证 API 运行真实业务图、工具、业务数据库和 Chroma，读取实际运行轨迹评分。脚本模型控制语义输出；玩具 embedding 控制本地检索输入。因此结果表示执行器正确处理这些固定输入，不表示真实模型工具选择准确率、语义检索质量或完整回答事实准确率。

task_completed 字段表示“该场景预期行为达成”，包含正确追问、正确拒绝和正确失败，不能改名为“所有业务请求成功率”。权限分数检查另一员工的金丝雀数据不出现在返回中；它与工具读取前的授权断言、资源所有权测试共同构成证据，单靠模型说“拒绝”不足以证明安全。

本次未完成系统性的真实模型专项评测。页面测试曾因配置切换绕过替身而意外调用已配置模型；该请求不计作效果评测。已修正测试模型注入，并在 API 测试 fixture 禁用真实凭证，避免遗漏替身导致外部调用。

## 场景分布与指标

制度 6、本人数据 6、缺参/非法参数 6、多步骤 8、权限 6、上下文/恢复 4、故障 4。开发与留出标签用于隔离后续调参；已根据完整脚本集调试执行器，不能把本次脚本结果称为独立的真实模型留出成绩。

工具选择比较实际尝试的工具集合；参数比较实际轨迹中已标注的约束；完成同时检查 HTTP、运行终态、业务状态、必要成功工具结果与标注答案片段。失败和超时保留在分母。该规则评分只覆盖已标注行为，不替代人工事实审查。

## 复现

```powershell
python -m pytest tests -q
python -m eval.run_agent_eval --dataset eval/agent_cases.jsonl --mode deterministic
```

每次创建新的 `runtime/agent-eval/<时间戳与随机后缀>`，保留数据库、向量库及 results.json，不删除已有数据。评测仅使用模拟制度和员工数据，不向用户既有知识库上传内容。

以下命令会调用配置的真实模型并产生费用，当前尚未系统运行：

```powershell
python -m eval.run_agent_eval --dataset eval/agent_cases.jsonl --mode live --split heldout
```

live 模式排除 execution_only 的非法模型输出夹具，使用同一隔离模拟业务环境；玩具 embedding 的结果不能衡量生产语义检索质量。评测指标应结合逐题轨迹人工审查，工具的等价安全拒绝路径需要单独核对。
