import csv
import random

from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService
from utils.config_handler import agent_conf
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

rag = RagSummarizeService()

employee_ids = ["E1001", "E1002", "E1003", "E1004", "E1005"]
employee_records: dict[str, dict[str, str]] = {}


@tool
def rag_summarize(query: str) -> str:
    """从企业知识库中检索制度、流程、IT 支持、项目规范等参考资料。"""
    return rag.rag_summarize(query)


@tool
def get_employee_id(dummy: str = "") -> str:
    """获取当前员工 ID。无入参，Action Input 请传入空字符串。"""
    return random.choice(employee_ids)


@tool
def get_employee_department(employee_id: str) -> str:
    """根据员工 ID 获取员工所属部门。入参示例：E1001。"""
    load_employee_records()
    employee_id = employee_id.strip().replace('"', "").replace("'", "")
    record = employee_records.get(employee_id)
    if not record:
        return "未查询到该员工的部门信息。"
    return record["department"]


def load_employee_records() -> None:
    if employee_records:
        return

    external_data_path = get_abs_path(agent_conf["external_data_path"])
    try:
        with open(external_data_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                employee_records[row["employee_id"]] = row
    except FileNotFoundError:
        logger.error(f"[load_employee_records] 外部员工数据不存在：{external_data_path}")
        raise
    except Exception as e:
        logger.error(f"[load_employee_records] 读取员工数据失败：{e}", exc_info=True)
        raise


@tool
def fetch_employee_records(params_str: str) -> str:
    """
    查询员工模拟业务数据。Action Input 必须是 "员工ID,查询类型"。
    查询类型可用：leave_balance、reimbursement、projects、onboarding、weekly_report、all。
    """
    load_employee_records()

    clean_str = (
        params_str.replace('"', "")
        .replace("'", "")
        .replace("{", "")
        .replace("}", "")
        .strip()
    )
    if "," not in clean_str:
        return "数据查询失败：参数格式应为 '员工ID,查询类型'。"

    employee_id, query_type = [item.strip() for item in clean_str.split(",", 1)]
    record = employee_records.get(employee_id)
    if not record:
        return "未查询到该员工的模拟业务数据。"

    query_map = {
        "leave_balance": f"剩余年假：{record['leave_balance_days']} 天。",
        "reimbursement": (
            f"最近报销状态：{record['reimbursement_status']}；"
            f"待补充材料：{record['missing_reimbursement_docs']}。"
        ),
        "projects": (
            f"参与项目：{record['project_name']}；"
            f"本周重点：{record['weekly_highlights']}；"
            f"风险与阻塞：{record['risks']}。"
        ),
        "onboarding": f"入职待办：{record['onboarding_tasks']}。",
        "weekly_report": (
            f"员工：{record['employee_name']}；部门：{record['department']}；"
            f"项目：{record['project_name']}；本周重点：{record['weekly_highlights']}；"
            f"产出：{record['deliverables']}；下周计划：{record['next_week_plan']}；"
            f"风险与阻塞：{record['risks']}。"
        ),
        "all": str(record),
    }

    return query_map.get(query_type, query_map["all"])


@tool
def generate_weekly_report_context(dummy: str = "") -> str:
    """进入员工周报生成场景。无入参，Action Input 请传入空字符串。"""
    return (
        "已进入员工周报生成场景。请结合员工项目记录输出："
        "本周工作概览、关键产出、问题风险、下周计划。"
    )
