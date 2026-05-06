from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from agent.tools.agent_tools import (
    fetch_employee_records,
    generate_weekly_report_context,
    get_employee_department,
    get_employee_id,
    rag_summarize,
)
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts


class ReactAgent:
    def __init__(self):
        tools = [
            rag_summarize,
            get_employee_id,
            get_employee_department,
            fetch_employee_records,
            generate_weekly_report_context,
        ]

        base_system_prompt = load_system_prompts()
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

        prompt = PromptTemplate.from_template(react_template)

        agent = create_react_agent(
            llm=chat_model,
            tools=tools,
            prompt=prompt,
        )

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
        input_dict = {"input": query}
        config = {"metadata": {"business_scene": "enterprise_knowledge_assistant"}}

        try:
            for chunk in self.agent_executor.stream(input_dict, config=config):
                if "output" in chunk:
                    yield chunk["output"] + "\n"
        except RuntimeError:
            yield (
                "\n\n[系统提示：模型输出格式不符合 ReAct 要求，"
                "请换一种更明确的问法后重试。]\n"
            )
        except Exception as e:
            yield f"\n\n[系统提示：发生未知错误：{str(e)}]\n"


if __name__ == "__main__":
    agent = ReactAgent()
    for chunk in agent.execute_stream("根据我的本周项目记录生成周报"):
        print(chunk, end="", flush=True)
