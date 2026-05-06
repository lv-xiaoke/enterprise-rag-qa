# LangChain ReAct Agent 项目帮助文档

本文档用于帮助你在本地安装、配置、运行和扩展这个项目。项目主体是一个基于 Streamlit 的智能客服演示应用，后端使用 LangChain ReAct Agent 调度工具，结合 Chroma 向量库完成知识库问答，并可基于外部用户数据生成使用报告。

## 1. 项目能做什么

当前项目以“扫地机器人智能客服”为示例场景，主要支持三类能力：

- 知识库问答：从 `data/` 目录中的 txt/pdf 文档检索相关内容，再交给大模型生成回答。
- 工具辅助问答：ReAct Agent 可根据问题自动调用天气、用户位置、用户 ID、当前月份等工具。
- 使用报告生成：Agent 按固定流程获取用户 ID、月份和外部数据，然后生成个性化使用分析报告。

前端入口是 `app.py`，启动后会打开一个 Streamlit 聊天界面。

## 2. 目录结构

```text
.
├── app.py                         # Streamlit 应用入口
├── requirements.txt               # Python 依赖
├── config/                        # YAML 配置文件
│   ├── agent.yml                  # Agent 外部数据路径配置
│   ├── chroma.yml                 # Chroma 向量库与知识库切分配置
│   ├── prompts.yml                # Prompt 文件路径配置
│   └── rag.yml                    # 模型名称配置
├── agent/
│   ├── react_agent.py             # ReAct Agent 创建与流式执行逻辑
│   └── tools/
│       ├── agent_tools.py         # Agent 可调用工具集合
│       └── middleware.py          # 中间件示例代码
├── rag/
│   ├── rag_service.py             # RAG 检索与总结链
│   └── vector_store.py            # 知识库入库与检索器创建
├── model/
│   └── factory.py                 # 聊天模型与 Embedding 模型工厂
├── prompts/                       # Agent、RAG、报告生成 Prompt
├── data/                          # 知识库文档与外部数据
│   └── external/records.csv       # 报告生成使用的用户记录
├── utils/                         # 配置、路径、文件、日志等通用工具
├── chroma_db/                     # Chroma 持久化目录
└── logs/                          # 运行日志目录
```

## 3. 环境要求

- Python 3.10 或更高版本，当前项目已有 `.venv`，也可以自行新建虚拟环境。
- 可用的阿里云 DashScope API Key。
- Windows PowerShell、CMD、macOS 或 Linux Shell 均可运行，下面命令以 PowerShell 为主。

## 4. 安装依赖

在项目根目录执行：

```powershell
pip install -r requirements.txt
```

如果下载较慢，可以使用清华源：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

项目主要依赖包括：

- `streamlit`：前端聊天界面。
- `langchain`、`langchain-core`、`langchain-community`：Agent、模型、工具与链式调用。
- `langgraph`：Agent 工作流相关能力。
- `chromadb`、`langchain-chroma`：本地向量库。
- `dashscope`：调用通义千问聊天模型和 Embedding 模型。
- `pypdf`：读取 PDF 知识库文件。
- `pyyaml`：读取 YAML 配置。

## 5. 配置 API Key

项目通过 DashScope 调用模型，所以运行前需要配置 `DASHSCOPE_API_KEY`。

PowerShell 临时配置：

```powershell
$env:DASHSCOPE_API_KEY="your-api-key"
```

CMD 临时配置：

```cmd
set DASHSCOPE_API_KEY=your-api-key
```

macOS/Linux 临时配置：

```bash
export DASHSCOPE_API_KEY="your-api-key"
```

临时配置只对当前终端窗口有效。关闭终端后，需要重新配置。

## 6. 核心配置说明

### 6.1 模型配置

文件：`config/rag.yml`

```yaml
chat_model_name: qwen3-max
embedding_model_name: text-embedding-v4
```

- `chat_model_name`：聊天模型名称，当前使用 `qwen3-max`。
- `embedding_model_name`：向量化模型名称，当前使用 `text-embedding-v4`。

这两个模型会在 `model/factory.py` 中被读取并初始化。

### 6.2 向量库配置

文件：`config/chroma.yml`

```yaml
collection_name : agent
persist_directory : chroma_db
k :  3
data_path : data
md5_hex_store : md5.txt
allow_knowledge_file_type : ["txt","pdf"]
chunk_size : 200
chunk_overlap : 20
separators : ["\n\n","。",".","?","？","!"," ",""]
```

常用字段说明：

- `collection_name`：Chroma 集合名称。
- `persist_directory`：向量库持久化目录。
- `k`：每次检索返回的文档片段数量。
- `data_path`：知识库文档所在目录。
- `md5_hex_store`：记录已入库文件 MD5 的文件，避免重复入库。
- `allow_knowledge_file_type`：允许入库的文件类型。
- `chunk_size`：知识库文档切分长度。
- `chunk_overlap`：相邻切片重叠长度。
- `separators`：文本切分使用的分隔符。

### 6.3 Prompt 配置

文件：`config/prompts.yml`

```yaml
main_prompt_path : prompts/main_prompt.txt
rag_summarize_prompt_path : prompts/rag_summarize.txt
report_prompt_path : prompts/report_prompt.txt
```

- `main_prompt.txt`：Agent 主提示词。
- `rag_summarize.txt`：RAG 检索后总结使用的提示词。
- `report_prompt.txt`：报告生成场景提示词。

### 6.4 外部数据配置

文件：`config/agent.yml`

```yaml
external_data_path: data/external/records.csv
```

`records.csv` 用于模拟外部业务系统里的用户使用记录。报告生成工具会读取该文件，并按 `用户ID,月份` 查询对应记录。

## 7. 构建或更新知识库

如果 `chroma_db/` 中已经有可用向量库，可以直接运行应用。

如果你新增、修改了 `data/` 目录中的知识库文档，需要重新执行入库逻辑：

```powershell
python -m rag.vector_store
```

入库逻辑位于 `rag/vector_store.py`，主要流程是：

1. 扫描 `config/chroma.yml` 中 `data_path` 指向的目录。
2. 只读取 `allow_knowledge_file_type` 允许的 txt/pdf 文件。
3. 计算文件 MD5，跳过已经处理过的文件。
4. 使用 `RecursiveCharacterTextSplitter` 切分文档。
5. 将切分后的片段写入 Chroma。
6. 将已处理文件的 MD5 写入 `md5.txt`。

注意：如果你想完全重建向量库，需要先手动确认并处理旧的 `chroma_db/` 和 `md5.txt`。不要在脚本中批量删除目录。

## 8. 启动应用

在项目根目录执行：

```powershell
streamlit run app.py
```

启动成功后，终端会显示本地访问地址，通常类似：

```text
Local URL: http://localhost:8501
```

打开浏览器访问该地址即可使用聊天界面。

## 9. 推荐测试问题

启动应用后，可以先用下面的问题验证功能。

知识库问答：

```text
扫地机器人有哪些主要功能？
```

故障排查：

```text
机器人无法正常回充，应该怎么处理？
```

选购建议：

```text
小户型适合选择什么类型的扫地机器人？
```

报告生成：

```text
请给我生成一份本月扫地机器人使用报告
```

天气工具：

```text
帮我看看深圳今天的天气
```

## 10. 工作流程说明

### 10.1 普通知识库问答

```text
用户输入问题
  ↓
Streamlit 将问题传给 ReactAgent
  ↓
Agent 判断需要调用 rag_summarize 工具
  ↓
RagSummarizeService 从 Chroma 检索相关文档
  ↓
模型根据问题和参考资料生成回答
  ↓
Streamlit 流式展示结果
```

### 10.2 使用报告生成

报告生成依赖 `agent/react_agent.py` 中写入 ReAct Prompt 的固定工具调用顺序：

1. 调用 `get_user_id` 获取用户 ID。
2. 调用 `get_current_month` 获取月份。
3. 调用 `fill_context_for_report` 注入报告场景上下文。
4. 调用 `fetch_external_data` 读取外部数据。
5. 根据外部数据生成最终报告。

当前 `get_user_id` 和 `get_current_month` 是随机返回示例数据，所以每次生成的用户和月份可能不同。

## 11. 主要代码入口

### 11.1 `app.py`

负责 Streamlit 页面：

- 初始化 `ReactAgent`。
- 保存聊天历史到 `st.session_state`。
- 接收用户输入。
- 调用 `execute_stream()` 获取流式响应。
- 将回答展示在聊天窗口中。

### 11.2 `agent/react_agent.py`

负责构建 ReAct Agent：

- 加载主 Prompt。
- 注册工具列表。
- 使用 `create_react_agent()` 创建 Agent。
- 使用 `AgentExecutor` 包装 Agent。
- 通过 `execute_stream()` 提供流式输出。

### 11.3 `agent/tools/agent_tools.py`

定义 Agent 可调用工具：

- `rag_summarize`：知识库检索问答。
- `get_weather`：返回模拟天气。
- `get_user_location`：随机返回用户城市。
- `get_user_id`：随机返回用户 ID。
- `get_current_month`：随机返回月份。
- `fetch_external_data`：读取 `records.csv` 中的外部记录。
- `fill_context_for_report`：报告场景占位工具。

### 11.4 `rag/vector_store.py`

负责知识库入库和检索器创建：

- 初始化 Chroma。
- 扫描知识库目录。
- 加载 txt/pdf 文件。
- 切分文档。
- 写入向量库。
- 返回 retriever。

### 11.5 `rag/rag_service.py`

负责 RAG 问答链：

- 调用 retriever 检索相关文档。
- 拼接参考资料上下文。
- 使用 `rag_summarize.txt` 生成回答。

### 11.6 `model/factory.py`

负责模型初始化：

- `ChatTongyi`：聊天模型。
- `DashScopeEmbeddings`：Embedding 模型。

## 12. 如何新增知识库文档

1. 将 `.txt` 或 `.pdf` 文件放入 `data/` 目录。
2. 确认 `config/chroma.yml` 中允许该文件类型。
3. 执行：

```powershell
python -m rag.vector_store
```

4. 启动应用并提问验证。

建议：

- txt 文件尽量使用 UTF-8 编码。
- 文档内容最好按主题分段，能提升切分和检索效果。
- 如果问题经常检索不到，可以适当调大 `k` 或优化知识库文本表达。

## 13. 如何新增 Agent 工具

新增工具通常修改 `agent/tools/agent_tools.py` 和 `agent/react_agent.py`。

示例：

```python
from langchain_core.tools import tool

@tool
def get_order_status(order_id: str) -> str:
    """根据订单号查询订单状态。"""
    return "订单已完成"
```

然后在 `agent/react_agent.py` 中导入并加入工具列表：

```python
tools = [
    rag_summarize,
    get_weather,
    get_user_location,
    get_user_id,
    get_current_month,
    fetch_external_data,
    fill_context_for_report,
    get_order_status,
]
```

工具说明文档字符串很重要，ReAct Agent 会根据描述判断什么时候调用该工具。

## 14. 常见问题

### 14.1 启动时报 DashScope API Key 错误

检查是否设置了环境变量：

```powershell
$env:DASHSCOPE_API_KEY
```

如果没有输出，重新设置：

```powershell
$env:DASHSCOPE_API_KEY="your-api-key"
```

### 14.2 问答结果和知识库内容无关

可检查：

- `chroma_db/` 是否已经生成。
- 是否执行过 `python -m rag.vector_store`。
- `data/` 中是否有相关知识文档。
- `config/chroma.yml` 中 `k` 是否太小。
- 文档编码是否为 UTF-8。

### 14.3 新增文档后没有被检索到

项目会用 MD5 记录已处理文件。如果你只是轻微修改文件但没有重新入库成功，先确认 `python -m rag.vector_store` 是否执行完成，并查看 `logs/` 中的日志。

### 14.4 Agent 输出格式错误或中断

ReAct Agent 对输出格式要求较严格，模型需要生成 `Thought / Action / Action Input / Observation / Final Answer` 结构。项目已经在 `AgentExecutor` 中配置了 `handle_parsing_errors`，但如果仍然失败，可以尝试：

- 换一种更明确的问题问法。
- 检查 `prompts/main_prompt.txt` 是否被改坏。
- 换用更稳定的聊天模型。

### 14.5 README 显示乱码

当前仓库中的部分中文文件在终端输出时可能出现编码显示问题。运行代码时，项目多数文件仍按 UTF-8 读取。阅读项目说明时，建议优先参考本 `HELP.md`。

## 15. 开发建议

- 优先从 `app.py`、`agent/react_agent.py`、`agent/tools/agent_tools.py`、`rag/rag_service.py` 这几处开始理解项目。
- 修改 Prompt 时，先小步调整并立即在 Streamlit 页面验证。
- 新增工具时，先写清楚工具函数的 docstring，再把它加入 Agent 工具列表。
- 调整知识库效果时，优先尝试修改 `chunk_size`、`chunk_overlap`、`k` 和知识库文档组织方式。
- 查看问题原因时，优先阅读 `logs/` 下当天生成的日志文件。

## 16. 一键运行参考流程

首次运行可以按下面顺序执行：

```powershell
cd D:\my_develop\A_work_program\LangChain-ReAct-Agent-main
pip install -r requirements.txt
$env:DASHSCOPE_API_KEY="your-api-key"
python -m rag.vector_store
streamlit run app.py
```

如果依赖已经安装、知识库已经构建，下次只需要：

```powershell
cd D:\my_develop\A_work_program\LangChain-ReAct-Agent-main
$env:DASHSCOPE_API_KEY="your-api-key"
streamlit run app.py
```
