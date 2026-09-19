# =============================================================================
# LangChain 标准库：提供 AgentExecutor（代理执行器）和 create_react_agent
# （创建 ReAct 模式的代理）
# =============================================================================
from langchain.agents import AgentExecutor, create_react_agent
# LangChain 核心库：PromptTemplate 用于从字符串模板构建 prompt
from langchain_core.prompts import PromptTemplate

# =============================================================================
# 自定义工具函数（Agent 可调用的"技能"）：
#   fetch_employee_records   — 根据员工 ID 和查询类型拉取员工数据
#   generate_weekly_report_context — 生成本周工作上下文供撰写周报
#   get_employee_department  — 根据员工 ID 查询所属部门
#   get_employee_id          — 根据员工姓名查询员工 ID
#   rag_summarize            — 基于 RAG 对文档进行总结
# =============================================================================
from agent.tools.agent_tools import (
    fetch_employee_records,
    generate_weekly_report_context,
    get_employee_department,
    get_employee_id,
    rag_summarize,
)
# 获取 LLM 聊天模型实例（工厂模式）
from model.factory import chat_model
# 从 YAML 文件中加载系统级 prompt 模板
from utils.prompt_loader import load_system_prompts


class ReactAgent:
    """
    ReAct（Reasoning + Acting）模式的企业知识助手代理。

    核心流程：
    1. LLM 根据用户问题生成"思考 → 行动 → 观察"循环
    2. 行动步骤调用工具函数获取真实数据
    3. 观察步骤将工具结果返回给 LLM 继续推理
    4. 最终由 LLM 输出 Final Answer
    """

    def __init__(self):
        # ---- 1. 注册 Agent 可用工具列表 ----
        # LangChain 会将每个函数包装为 Tool 对象，供 LLM 选择调用
        tools = [
            rag_summarize,
            get_employee_id,
            get_employee_department,
            fetch_employee_records,
            generate_weekly_report_context,
        ]

        # ---- 2. 构建 ReAct Prompt 模板 ----
        # base_system_prompt：从 YAML 加载的角色定义、行为约束等基础系统提示
        base_system_prompt = load_system_prompts()
        # react_template：在基础系统提示上拼接 ReAct 格式说明和业务工作流
        #   {tools}         — 工具名称与描述列表
        #   {tool_names}    — 工具名称列表
        #   {input}         — 用户输入的问题
        #   {agent_scratchpad} — 思考/行动/观察的中间过程（由框架自动填充）
        react_template = (
            base_system_prompt
            + """

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

### Weekly report workflow ###
If the user asks to generate a personal weekly report or summarize weekly work:
1. Call get_employee_id first.
2. Call get_employee_department with the employee id.
3. Call generate_weekly_report_context.
4. Call fetch_employee_records with "employee_id,weekly_report".
5. Use Final Answer to write the weekly report in Chinese.

### Employee data workflow ###
If the user asks about personal leave balance, reimbursement status, assigned projects,
or onboarding tasks:
1. Call get_employee_id first unless the user explicitly provides an employee id.
2. Call fetch_employee_records with "employee_id,query_type".
3. Answer only from the returned structured data.

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
        )

        # 从字符串模板创建 PromptTemplate 对象
        prompt = PromptTemplate.from_template(react_template)

        # ---- 3. 创建 ReAct Agent ----
        # create_react_agent 将 LLM + 工具 + prompt 绑定为一个可调用的 agent
        agent = create_react_agent(
            llm=chat_model,
            tools=tools,
            prompt=prompt,
        )

        # ---- 4. 创建 Agent 执行器 ----
        # AgentExecutor 是 agent 的运行外壳，负责：
        #   实际调用 LLM → 解析输出 → 执行工具 → 将结果反馈给 LLM 的循环
        # verbose=True 打印完整的思考链（调试用）
        # handle_parsing_errors 在 LLM 输出格式不符合 ReAct 规范时给出中文提示
        self.agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=(
                "请检查输出格式：必须包含 Action 和 Action Input，"
                "或者使用 Final Answer 给出最终答案。"
            ),
        )

    def execute_stream(self, query: str):
        """
        流式执行 Agent 推理过程。

        使用 generator 逐块返回输出，适合 SSE 或 WebSocket 推送场景。
        """
        input_dict = {"input": query}
        # metadata 标记业务场景，用于日志追踪和监控
        config = {"metadata": {"business_scene": "enterprise_knowledge_assistant"}}

        try:
            # 流式遍历 agent 执行器的输出
            for chunk in self.agent_executor.stream(input_dict, config=config):
                # 只返回包含 "output" 键的 chunk（过滤掉中间步骤的冗余信息）
                if "output" in chunk:
                    yield chunk["output"] + "\n"
        except RuntimeError:
            # RuntimeError：通常是 LLM 输出格式多次解析失败导致的
            yield (
                "\n\n[系统提示：模型输出格式不符合 ReAct 要求，"
                "请换一种更明确的问法后重试。]\n"
            )
        except Exception as e:
            # 兜底异常处理，防止未预期的错误导致服务中断
            yield f"\n\n[系统提示：发生未知错误：{str(e)}]\n"


# =============================================================================
# 直接运行本文件时的测试入口
# =============================================================================
if __name__ == "__main__":
    agent = ReactAgent()
    # 测试：用中文提问"根据我的本周项目记录生成周报"
    for chunk in agent.execute_stream("根据我的本周项目记录生成周报"):
        print(chunk, end="", flush=True)
