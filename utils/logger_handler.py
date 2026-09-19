import logging
from utils.path_tool import get_abs_path

import os
from datetime import time, datetime

# 日志保存的根目录
LOG_ROOT=get_abs_path("logs")

# 确保日志的目录所在
os.makedirs(LOG_ROOT,exist_ok=True)

# 日志的格式配置 error info debug
DEFAULT_LOG_FORMAT= logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

def get_logger(
        name: str= "agent",
        console_level:int =logging.INFO,        # 只输出info级别以上的日志信息，避免debug垃圾信息
        file_level: int=logging.DEBUG,
        log_file =None,
) -> logging.Logger:
    logger =logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 避免重复添加Handler,如果存在,不重复打印日志
    if logger.handlers:
        return logger
    # 控制台Handler
    console_handler= logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(console_handler)

    # 文件Handler
    if not log_file:            # 日志文件的存放路径
        log_file= os.path.join(LOG_ROOT,f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    file_handler=logging.FileHandler(log_file,encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)

    logger.addHandler(file_handler)

    return logger

# 快捷获取日志器
logger=get_logger()


# chromadb 0.5.15 的遥测客户端与当前 posthog 版本不兼容：每次创建集合、
# 查询向量库都会 ERROR 一行
#   Failed to send telemetry event ClientCreateCollectionEvent:
#   capture() takes 1 positional argument but 3 were given
# 关不掉——它读的是 chromadb 自己的全局 Settings，既不认构造参数
# Chroma(client_settings=Settings(anonymized_telemetry=False))，
# 也不认 ANONYMIZED_TELEMETRY / CHROMA_ANONYMIZED_TELEMETRY 环境变量。
# 正解是升级 chromadb，但本项目为了保证评测结果可复现锁死了版本，
# 所以只能把这一支 logger 抬到 CRITICAL：遥测发不出去本来就是无害的，
# 不该占着 ERROR 级别刷屏、盖住真正的错误日志。
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
if __name__== '__main__':
    logger.info("信息日志")
    logger.error("错误日志")
    logger.warning("警告日志")
    logger.debug("调试日志")
