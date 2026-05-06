from langchain.agents import create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate

from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize, get_weather, get_user_location, get_user_id,
                                     get_current_month, fetch_external_data, fill_context_for_report,
                                     generate_consumable_reminder)

# 注意：原生的 Agent 不直接支持中间件，下面注释掉了 middleware 的导入
# 如果需要监控，LangChain 中需要通过 Callbacks (回调机制) 来实现
# from agent.tools.middleware import monitor_tool, log_before_model, report_prompt_switch


class ReactAgent:
    def __init__(self):
        # 1. 准备工具列表
        tools = [rag_summarize, get_weather, get_user_location, get_user_id,
                 get_current_month, fetch_external_data, fill_context_for_report,
                 generate_consumable_reminder]

        # 2. 原生 ReAct 需要一个非常严格的 Prompt 模板
        # 这里将你加载的 system_prompt 和 ReAct 的思维链模板拼接在一起
        base_system_prompt = load_system_prompts()
        react_template = base_system_prompt + """

Answer the following questions as best you can. You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action (MUST NOT BE EMPTY, use "" if no input is needed)
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

### 核心工作流指令 (CRITICAL WORKFLOW) ###
如果你需要生成“使用报告”，你必须严格按照以下顺序思考和调用工具：
1. 首先调用 get_user_id 获取用户标识。
2. 然后调用 get_current_month 获取当前月份。
3. 接着调用 fill_context_for_report 注入上下文。
4. 最后调用 fetch_external_data (传入刚才获取的 id 和 month) 获取数据。
5. 根据获取的数据，用 Final Answer 输出最终的报告。

### 工具选择边界 (TOOL SELECTION RULES) ###
1. 如果用户询问知识库问题、故障排查、选购建议、使用方法，优先调用 rag_summarize。
2. 如果用户要求完整的个人使用报告，必须按上面的“使用报告”固定流程执行。
3. 如果用户询问耗材、维护、保养、滤网、边刷、主刷、胶刷、尘盒、水箱或更换提醒，调用 generate_consumable_reminder。
4. 调用 generate_consumable_reminder 前，如用户没有明确给出用户ID或月份，先分别调用 get_user_id 和 get_current_month，再以 "用户ID,月份" 格式传入。

Begin!

Question: {input}
Thought:{agent_scratchpad}"""

        prompt = PromptTemplate.from_template(react_template)

        # 3. 创建标准的原生 ReAct Agent
        agent = create_react_agent(
            llm=chat_model,
            tools=tools,
            prompt=prompt
        )

        # 4. 使用 AgentExecutor 包装（这是必须的步骤）
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            # 【修复点】：将 handle_parsing_errors 设为具体的指导提示词，
            # 让大模型在格式化失败时知道如何纠正自己，而不是单纯的抛错
            handle_parsing_errors="请检查你的输出格式！必须严格包含 'Action:' 和 'Action Input:'，或者用 'Final Answer:' 给出最终答案。"
        )

    def execute_stream(self, query: str):
        # 5. 原生的输入格式直接是一个字典
        input_dict = {"input": query}

        # 6. config 代替了原先的 context 参数，用于传递上下文
        config = {"metadata": {"report": False}}

        # 7. 【修复点】：修改流式解析逻辑，增加 try-except 防止前端崩溃
        try:
            for chunk in self.agent_executor.stream(input_dict, config=config):
                # 捕获并 yield 最终结果
                if "output" in chunk:
                    yield chunk["output"] + "\n"
                
                # 如果你想在终端看到中间思考过程 (Thought/Action)，可以解除下面代码的注释
                # elif "actions" in chunk or "steps" in chunk:
                #    yield f"[思考中...] {chunk}\n"

        except RuntimeError as e:
            # 捕获到底层抛出的 StopIteration / RuntimeError
            yield "\n\n[⚠️ 系统提示：大模型思考过程意外中断。这通常是因为模型输出的格式不符合要求。请尝试重新提问，或换一种问法。]\n"
        except Exception as e:
            # 捕获其他可能的异常，防止 Streamlit 页面白屏报错
            yield f"\n\n[⚠️ 系统提示：发生未知错误 {str(e)}]\n"


if __name__ == '__main__':
    agent = ReactAgent()

    for chunk in agent.execute_stream("给我生成我的使用报告"):
        print(chunk, end="", flush=True)
