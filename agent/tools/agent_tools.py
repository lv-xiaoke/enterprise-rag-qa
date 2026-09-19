"""Agent 可调用的工具集合。

两个关键设计
------------
**身份来自会话，不是随机数**
    早期实现里 `get_employee_id` 返回 `random.choice(employee_ids)`，于是
    「我的年假还剩几天」的答案取决于一次随机抽样。这既是正确性缺陷
    （同一个问题两次回答不同、无法复现），也是安全问题（可能返回他人数据）。
    现在身份由入口通过 `set_current_employee()` 注入，工具只读当前请求的身份。

**越权访问由代码拦截，不是靠提示词劝阻**
    提示词约束是「建议」，模型可以选择不听——把安全边界建立在提示词上，
    等于没有边界。这里 `fetch_employee_records` / `get_employee_department`
    会校验请求的 employee_id 是否等于当前登录身份，不等直接拒绝并记安全日志。
    于是「帮我查同事 E1002 的年假」这类请求是被代码挡住的，而不是被劝住的。
"""

from __future__ import annotations

import csv
from contextvars import ContextVar
from functools import lru_cache
from typing import Literal

from langchain_core.tools import tool

from utils.config_handler import agent_conf
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

# ---------------------------------------------------------------------------
# 当前请求的员工身份
# ---------------------------------------------------------------------------

# 用 ContextVar 而不是模块级全局变量：全局变量在并发请求下会被互相覆盖
# （A 的请求把身份写成 E1001，B 的请求读到 E1001 却以为是自己的），
# ContextVar 天然按执行上下文隔离，Streamlit 与将来的 FastAPI 都适用。
_current_employee: ContextVar[str | None] = ContextVar("current_employee", default=None)


def set_current_employee(employee_id: str | None) -> None:
    """由入口在每次请求开始时调用，绑定本次请求的员工身份。"""
    _current_employee.set(employee_id)


def get_current_employee() -> str | None:
    """读取当前请求绑定的员工身份，未绑定时返回 None。"""
    return _current_employee.get()


# ---------------------------------------------------------------------------
# 员工数据加载
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_employee_records() -> dict[str, dict[str, str]]:
    """加载员工模拟业务数据。

    用 lru_cache 而不是「模块级字典 + if 判空」：后者在并发首次调用时
    会重复读文件，而且缓存状态散落在模块变量里，不好测也不好清。
    """
    external_data_path = get_abs_path(agent_conf["external_data_path"])
    records: dict[str, dict[str, str]] = {}

    try:
        # utf-8-sig：CSV 常带 BOM，用 utf-8 读会让首个列名变成 "﻿employee_id"
        with open(external_data_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                records[row["employee_id"].strip().upper()] = row
    except FileNotFoundError:
        logger.error(f"[员工数据]文件不存在：{external_data_path}")
        raise
    except Exception as e:
        logger.error(f"[员工数据]读取失败：{e}", exc_info=True)
        raise

    logger.info(f"[员工数据]已加载 {len(records)} 条记录")
    return records


def list_employees() -> list[dict[str, str]]:
    """列出可选登录身份，供入口渲染「当前登录员工」选择器。

    只回 id / 姓名 / 部门三个字段，不回年假余额、报销状态等业务字段——
    登录选择器不需要这些，而每多回一个字段就多一处泄露面。
    """
    return [
        {
            "employee_id": employee_id,
            "employee_name": record.get("employee_name", ""),
            "department": record.get("department", ""),
        }
        for employee_id, record in sorted(_load_employee_records().items())
    ]


def _deny_if_not_self(employee_id: str) -> str | None:
    """越权校验：允许访问返回 None，拒绝则返回给模型看的拒绝文案。"""
    current = get_current_employee()

    if current is None:
        return "当前会话未绑定员工身份，无法查询个人数据，请先登录。"

    if employee_id.strip().upper() != current.strip().upper():
        # 记 warning 而不是 info：这是一次被拦截的越权尝试，属于安全事件，
        # 需要能在日志里被单独检索出来。
        logger.warning(
            f"[越权拦截]当前身份 {current} 尝试查询 {employee_id} 的个人数据"
        )
        return (
            f"拒绝访问：当前登录员工无权查询 {employee_id} 的个人数据。"
            "如需查询他人信息，请通过 HR 或直属负责人发起正式申请。"
        )

    return None


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


@tool
def rag_summarize(query: str) -> str:
    """从企业知识库中检索制度、流程、IT 支持、项目规范等参考资料并总结回答。"""
    return rag.rag_summarize(query)


@tool
def get_employee_id() -> str:
    """获取当前登录员工的 ID。无入参，用于需要员工 ID 的后续查询。"""
    current = get_current_employee()
    if current is None:
        return "当前会话未绑定员工身份。"
    return current


@tool
def get_employee_department(employee_id: str) -> str:
    """根据员工 ID 查询所属部门。只能查询当前登录员工本人的部门。

    :param employee_id: 员工 ID，例如 E1001
    """
    denied = _deny_if_not_self(employee_id)
    if denied:
        return denied

    record = _load_employee_records().get(employee_id.strip().upper())
    if not record:
        return "未查询到该员工的部门信息。"
    return record["department"]


@tool
def fetch_employee_records(
    employee_id: str,
    query_type: Literal[
        "leave_balance",
        "reimbursement",
        "projects",
        "onboarding",
        "weekly_report",
        "all",
    ],
) -> str:
    """查询当前登录员工的个人业务数据。只能查询本人数据。

    :param employee_id: 员工 ID，例如 E1001
    :param query_type: 查询类型——leave_balance 年假余额；reimbursement 报销状态；
        projects 参与项目；onboarding 入职待办；weekly_report 周报素材；all 全部
    """
    denied = _deny_if_not_self(employee_id)
    if denied:
        return denied

    record = _load_employee_records().get(employee_id.strip().upper())
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

    return query_map[query_type]


@tool
def generate_weekly_report_context() -> str:
    """进入员工周报生成场景。无入参，用于获取周报的写作要求。"""
    return (
        "已进入员工周报生成场景。请结合员工项目记录输出："
        "本周工作概览、关键产出、问题风险、下周计划。"
    )


# ---------------------------------------------------------------------------
# RAG 服务的惰性单例
# ---------------------------------------------------------------------------

_rag_singleton = None


def _get_rag():
    """惰性构建 RagSummarizeService。

    放在函数里而不是模块顶层：模块顶层构造会连带加载向量模型、打开向量库，
    使 `import agent.tools.agent_tools` 变慢，也让纯工具测试被迫依赖向量库。
    """
    global _rag_singleton
    if _rag_singleton is None:
        from rag.rag_service import RagSummarizeService

        _rag_singleton = RagSummarizeService()
    return _rag_singleton


def __getattr__(name: str):
    """PEP 562 模块级惰性属性。

    保留 `rag` 这个名字是为了不动 `app.py` 的 `from ... import rag`。
    返回的是**缓存的同一个实例**，所以 app.py 里
    `rag_service.model = ...` 这类赋值能正确作用在单例上。
    """
    if name == "rag":
        return _get_rag()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
