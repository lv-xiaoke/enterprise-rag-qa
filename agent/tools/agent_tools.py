import os
from utils.logger_handler import logger
from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService
import random
from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path

rag = RagSummarizeService()

user_ids = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010",]
month_arr = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
             "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12", ]

external_data = {}


@tool
def rag_summarize(query: str) -> str:
    """从向量存储中检索参考资料"""
    return rag.rag_summarize(query)


@tool
def get_weather(city: str) -> str:
    """获取指定城市的天气，以消息字符串的形式返回"""
    return f"城市{city}天气为晴天，气温26摄氏度，空气湿度50%，南风1级，AQI21，最近6小时降雨概率极低"


@tool
def get_user_location(dummy: str = "") -> str:
    """获取用户所在城市的名称，以纯字符串形式返回。调用时 Action Input 请传入空字符串 "" """
    return random.choice(["深圳", "合肥", "杭州"])


@tool
def get_user_id(dummy: str = "") -> str:
    """获取用户的ID，以纯字符串形式返回。调用时 Action Input 请传入空字符串 "" """
    return random.choice(user_ids)


@tool
def get_current_month(dummy: str = "") -> str:
    """获取当前月份，以纯字符串形式返回。调用时 Action Input 请传入空字符串 "" """
    return random.choice(month_arr)


def generate_external_data():
    """
    {
        "user_id": {
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            ...
        },
        "user_id": {
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            "month" : {"特征": xxx, "效率": xxx, ...}
            ...
        },
        ...
    }
    :return:
    """
    if not external_data:
        external_data_path = get_abs_path(agent_conf["external_data_path"])

        if not os.path.exists(external_data_path):
            raise FileNotFoundError(f"外部数据文件{external_data_path}不存在")

        with open(external_data_path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                arr: list[str] = line.strip().split(",")

                user_id: str = arr[0].replace('"', "")
                feature: str = arr[1].replace('"', "")
                efficiency: str = arr[2].replace('"', "")
                consumables: str = arr[3].replace('"', "")
                comparison: str = arr[4].replace('"', "")
                time: str = arr[5].replace('"', "")

                if user_id not in external_data:
                    external_data[user_id] = {}

                external_data[user_id][time] = {
                    "特征": feature,
                    "效率": efficiency,
                    "耗材": consumables,
                    "对比": comparison,
                }


@tool
def fetch_external_data(params_str: str) -> str:
    """从外部系统中获取指定用户在指定月份的使用记录。调用时 Action Input 请严格按照 '用户ID,月份' 的格式传入英文逗号分隔，例如 '1001,2025-03' """
    generate_external_data()

    try:
        # 1. 过滤掉大模型可能手欠加的引号，并按逗号切分
        clean_str = params_str.replace('"', '').replace("'", "").replace("}", "").replace("{", "")
        
        # 2. 解析出两个参数
        if "," in clean_str:
            user_id, month = clean_str.split(",", 1)
        else:
             # 兼容某些极端格式
             return "数据获取失败：参数格式错误，请严格按照 '用户ID,月份' 格式重试。"

        user_id = user_id.strip()
        month = month.strip()

        # 3. 返回数据
        return external_data[user_id][month]

    except KeyError:
        logger.warning(f"[fetch_external_data]未能检索到用户：{user_id}在{month}的使用记录数据")
        return ""
    except Exception as e:
        logger.error(f"解析参数失败: {e}")
        return "数据获取失败：参数解析异常。"


@tool
def fill_context_for_report(dummy: str = "") -> str:
    """无入参，无返回值，调用后触发中间件自动为报告生成的场景动态注入上下文信息，为后续提示词切换提供上下文信息。调用时 Action Input 请传入空字符串 "" """
    return "fill_context_for_report已调用"