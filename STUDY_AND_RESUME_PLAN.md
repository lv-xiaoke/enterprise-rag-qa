# LangChain ReAct + RAG 项目学习与简历沉淀

## 1. 项目主链路

本项目的真实调用链路是：

```text
Streamlit(app.py)
  -> ReactAgent(agent/react_agent.py)
  -> AgentExecutor.stream()
  -> Tools(agent/tools/agent_tools.py)
  -> RAG(rag/rag_service.py)
  -> Chroma(rag/vector_store.py)
  -> DashScope(model/factory.py)
  -> Prompt(prompts/*.txt)
```

用户在 `app.py` 的 `st.chat_input()` 输入问题后，页面会调用 `ReactAgent.execute_stream()`。`ReactAgent` 内部通过 `create_react_agent()` 创建 ReAct Agent，再用 `AgentExecutor` 包装执行。最终结果通过 `AgentExecutor.stream()` 逐步返回给 Streamlit 页面。

## 2. RAG 学习重点

RAG 链路集中在 `rag/vector_store.py` 和 `rag/rag_service.py`。

核心流程：

```text
文档加载 -> 文本切分 -> Embedding -> Chroma 存储 -> Retriever 检索 -> Prompt 总结回答
```

重点配置在 `config/chroma.yml`：

- `chunk_size: 200`：每个文本块的最大长度，越大上下文越完整，但可能引入噪声。
- `chunk_overlap: 20`：相邻文本块的重叠长度，用来减少切分断句造成的信息丢失。
- `k: 3`：每次检索返回的 top-k 文档数量，越大召回越多，但回答更容易混入无关内容。

一句话区分：普通 RAG 是“先检索，再回答”；Agent 是“模型自己判断是否检索、调用哪个工具、调用几次”。

## 3. Agent 学习重点

Agent 核心在 `agent/react_agent.py`：

- `create_react_agent()`：把模型、工具、Prompt 组合成 ReAct Agent。
- `AgentExecutor`：负责执行 ReAct 循环、调用工具、处理解析错误。
- `tools` 列表：决定 Agent 能使用哪些能力。

ReAct 的标准循环：

```text
Thought -> Action -> Action Input -> Observation -> Final Answer
```

新增工具时需要做三件事：

1. 在 `agent/tools/agent_tools.py` 中用 `@tool` 定义工具函数。
2. 在 `agent/react_agent.py` 中导入工具，并加入 `tools` 列表。
3. 在 Prompt 中说明工具的调用场景、入参格式和边界。

## 4. 本次简历亮点改造

本次新增了 `generate_consumable_reminder(params_str: str)` 工具，用于根据用户 ID 和月份生成耗材更换提醒与维护建议。

工具调用格式：

```text
用户ID,月份
```

示例：

```text
1001,2025-03
```

适用场景：

- 用户询问耗材状态。
- 用户询问滤网、边刷、主刷、胶刷、尘盒、水箱等维护问题。
- 用户想知道是否需要更换配件或如何保养设备。

该改造体现了三个能力：

- 理解 LangChain 工具注册方式。
- 能把结构化业务数据接入 Agent。
- 能通过 Prompt 约束 Agent 在正确场景调用正确工具。

## 5. 简历写法

可以写成：

> 基于 LangChain + ReAct Agent + Chroma 实现智能客服问答系统，支持扫地机器人知识库问答、工具调用、个性化使用报告和耗材维护提醒生成。项目使用 DashScope 模型完成对话与 Embedding，基于 Chroma 构建本地向量知识库，通过 ReAct Agent 动态选择 RAG 检索、用户数据查询、报告生成和耗材提醒等工具，并使用 Streamlit 实现流式对话界面。

可量化亮点：

- 设计并实现 RAG 检索问答链路，支持 PDF/TXT 文档入库、文本切分、向量化存储和 top-k 检索。
- 基于 LangChain ReAct Agent 注册多个工具，实现知识库问答、用户数据查询、报告生成和耗材维护提醒等多任务调度。
- 使用 YAML 管理模型、Prompt、Chroma 和 Agent 配置，降低系统扩展成本。
- 构建 Streamlit 聊天界面，支持用户连续对话和流式输出。

## 6. 验收问题

学习验收：

- RAG 为什么需要把文档切成 chunk？
- `chunk_size`、`chunk_overlap`、`k` 分别影响什么？
- `rag_summarize` 什么时候会被 Agent 调用？
- `AgentExecutor` 和普通 LLM 调用有什么区别？
- 如果要新增一个工具，需要改哪些地方？

实践验收：

- 新增一份知识库文档并重新入库。
- 修改 `k` 或 `chunk_size`，观察回答变化。
- 询问知识库问题，观察 Agent 是否调用 `rag_summarize`。
- 询问完整使用报告，观察 Agent 是否调用报告工具链。
- 询问耗材维护问题，观察 Agent 是否调用 `generate_consumable_reminder`。
