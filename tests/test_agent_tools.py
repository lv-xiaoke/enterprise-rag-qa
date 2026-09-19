"""工具层测试：身份的绑定/隔离，以及越权访问的拦截。

为什么先测这一层
----------------
工具层里唯一「写错了会真的泄露数据」的逻辑，就是 `_deny_if_not_self`。
它没有模型参与、输入输出确定，是整套系统里最值得用测试钉死的部分。
反过来，答案好不好、措辞顺不顺，那些交给 eval/ 下的评测集去量化，
不写成断言——把会抖动的输出写进测试，只会得到一堆没人看的红灯。

这些用例全部不依赖向量库、不依赖模型 API Key。
"""

from __future__ import annotations

import contextvars
import csv
import logging

import pytest

from agent.tools import agent_tools
from agent.tools.agent_tools import (
    fetch_employee_records,
    get_current_employee,
    get_employee_department,
    get_employee_id,
    list_employees,
    set_current_employee,
)
from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path


# 独立读一遍 CSV，拿到「真实值」用于断言「没泄露」。
# 刻意不复用被测模块的 _load_employee_records：用被测代码去构造期望值，
# 一旦它的解析逻辑出错，测试会跟着一起错，等于没测。
def _real_records() -> dict[str, dict[str, str]]:
    path = get_abs_path(agent_conf["external_data_path"])
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return {row["employee_id"]: row for row in csv.DictReader(f)}


REAL = _real_records()
SELF = "E1001"
OTHER = "E1002"


@pytest.fixture(autouse=True)
def _clean_identity():
    """每个用例前后都清空身份，避免 ContextVar 在用例之间串味。"""
    set_current_employee(None)
    yield
    set_current_employee(None)


class TestIdentityBinding:
    """身份来自会话绑定，不是一个随机数。"""

    def test_bound_identity_is_returned(self):
        set_current_employee(SELF)
        assert get_employee_id.invoke({}) == SELF

    def test_unbound_session_reports_clearly(self):
        """没绑身份时要明说，不能默默返回一个别人的 ID。"""
        result = get_employee_id.invoke({})
        assert "未绑定" in result

    def test_identity_does_not_leak_across_contexts(self):
        """ContextVar 的核心价值：一个上下文改身份，不影响另一个。

        这条断言是「并发请求不串身份」这个设计承诺的直接证据——
        如果当初用模块级全局变量存身份，这里就会失败。
        """
        set_current_employee(SELF)
        other_context = contextvars.copy_context()

        other_context.run(set_current_employee, OTHER)

        assert get_current_employee() == SELF


class TestAccessControl:
    """越权访问由代码拦截，不靠提示词劝阻。"""

    def test_own_leave_balance_is_allowed(self):
        set_current_employee(SELF)
        result = fetch_employee_records.invoke(
            {"employee_id": SELF, "query_type": "leave_balance"}
        )
        assert REAL[SELF]["leave_balance_days"] in result

    def test_other_employee_leave_balance_is_denied(self):
        set_current_employee(SELF)
        result = fetch_employee_records.invoke(
            {"employee_id": OTHER, "query_type": "leave_balance"}
        )
        assert "拒绝访问" in result

    def test_other_employee_department_is_denied(self):
        set_current_employee(SELF)
        result = get_employee_department.invoke({"employee_id": OTHER})

        assert "拒绝访问" in result
        assert REAL[OTHER]["department"] not in result

    def test_denial_never_surfaces_the_target_record(self, monkeypatch):
        """用「金丝雀」记录验证拒绝路径不透出目标记录的任何字段。

        为什么不直接拿真实数据比对：这份模拟数据里
        `leave_balance_days='3'`、`missing_reimbursement_docs='无'` 都是单字值，
        用子串匹配无论实现对错都会通过——`'3' not in 拒绝文案` 恒真，
        测试会退化成一句空话。（这不是假设，初版就是这么写的，跑出来才发现。）

        换成多字符金丝雀后，「拒绝路径有没有读过目标记录」才真的被验证。
        后半段是对照组：同一份金丝雀数据查自己时必须原样返回，
        否则工具压根没接上数据源时，前一句断言也会通过。
        """
        canary = {key: f"CANARY-{key}-9f3a" for key in REAL[OTHER]}
        canary["employee_id"] = OTHER
        monkeypatch.setattr(
            agent_tools, "_load_employee_records", lambda: {OTHER: canary}
        )

        set_current_employee(SELF)
        denied = fetch_employee_records.invoke(
            {"employee_id": OTHER, "query_type": "all"}
        )
        assert "CANARY" not in denied

        set_current_employee(OTHER)
        allowed = fetch_employee_records.invoke(
            {"employee_id": OTHER, "query_type": "all"}
        )
        assert "CANARY" in allowed

    def test_unbound_session_cannot_read_personal_data(self):
        """未登录时连自己的数据也读不到——不能默认放行。"""
        result = fetch_employee_records.invoke(
            {"employee_id": SELF, "query_type": "leave_balance"}
        )
        assert "未绑定" in result
        assert REAL[SELF]["leave_balance_days"] not in result

    def test_identity_comparison_ignores_case_and_space(self):
        """`e1001` / ` E1001 ` 是同一个身份，不该被误判成越权。"""
        set_current_employee(SELF)
        result = fetch_employee_records.invoke(
            {"employee_id": f"  {SELF.lower()}  ", "query_type": "leave_balance"}
        )
        assert "拒绝访问" not in result
        assert REAL[SELF]["leave_balance_days"] in result

    def test_denial_is_recorded_as_a_security_event(self, caplog):
        """越权尝试要能在日志里被单独检索出来。

        这是「事后能不能发现有人试过越权」的唯一依据，所以要求是 warning，
        不能降级成 info——info 级别的日志在实际运维里等于不存在。
        """
        set_current_employee(SELF)

        with caplog.at_level(logging.WARNING, logger="agent"):
            fetch_employee_records.invoke(
                {"employee_id": OTHER, "query_type": "leave_balance"}
            )

        assert any("越权拦截" in record.message for record in caplog.records)


class TestDirectoryExposure:
    """登录选择器只需要通讯录字段。"""

    def test_list_employees_exposes_only_directory_fields(self):
        fields = set().union(*(item.keys() for item in list_employees()))
        assert fields == {"employee_id", "employee_name", "department"}

    def test_list_employees_returns_every_record(self):
        assert {item["employee_id"] for item in list_employees()} == set(REAL)

    def test_business_values_absent_from_directory(self):
        """年假、报销状态、项目风险这些不该出现在通讯录里。"""
        payload = str(list_employees())
        for key in ("leave_balance_days", "reimbursement_status", "risks"):
            assert REAL[SELF][key] not in payload


class TestToolSchemas:
    """工具签名是强类型的，枚举值由 schema 兜住，不靠手工切字符串。"""

    def test_query_type_is_a_closed_enum(self):
        schema = fetch_employee_records.args_schema.model_json_schema()
        assert set(schema["properties"]["query_type"]["enum"]) == {
            "leave_balance",
            "reimbursement",
            "projects",
            "onboarding",
            "weekly_report",
            "all",
        }

    def test_invalid_query_type_is_rejected_before_execution(self):
        """非法枚举值应该在 schema 校验阶段就被拒，而不是进函数体后 KeyError。"""
        set_current_employee(SELF)
        with pytest.raises(Exception):
            fetch_employee_records.invoke(
                {"employee_id": SELF, "query_type": "annual_leave"}
            )
