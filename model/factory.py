"""模型工厂：按配置装配对话模型与向量模型。

设计目标是把「用哪个厂商的模型」收敛成一个配置项，业务代码不感知具体 SDK。
新增厂商只需要在下面的注册表里加一个 builder 函数。

关于惰性加载
------------
模型客户端在**首次访问时**才构建，而不是在 import 时构建。原因有两个：

1. 缺少某个厂商的 API Key 时，不应该让整个包 import 失败。
2. 评测脚本需要在不配置 DEEPSEEK_API_KEY 的情况下跑纯检索指标。

向后兼容
--------
历史上其他模块直接 `from model.factory import chat_model`。为了不改动这些调用点，
模块级 `__getattr__` 保留了 `chat_model` / `embed_model` 两个名字，行为等价于
对应的 build_* 函数，并且带缓存。
"""

from __future__ import annotations

import os
from typing import Callable

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from utils.config_handler import rag_conf
from utils.logger_handler import logger


class ProviderError(RuntimeError):
    """模型供应商装配失败，通常是缺少 API Key 或配置了未知 provider。"""


def _require_env(key: str, provider: str) -> str:
    """读取必需的环境变量，缺失时给出可直接照做的修复提示。"""
    value = os.getenv(key)
    if not value:
        raise ProviderError(
            f"{provider} 需要环境变量 {key}，当前未设置。\n"
            f'修复方式：$env:{key}="your-api-key"（PowerShell）'
        )
    return value


# ---------------------------------------------------------------------------
# 对话模型
# ---------------------------------------------------------------------------

def _build_deepseek(
    model: str | None = None, temperature: float | None = None
) -> BaseChatModel:
    from langchain_deepseek import ChatDeepSeek

    _require_env("DEEPSEEK_API_KEY", "DeepSeek")
    return ChatDeepSeek(
        model=model or rag_conf.get("chat_model_name", "deepseek-chat"),
        temperature=(
            rag_conf.get("chat_temperature", 0.3) if temperature is None else temperature
        ),
    )


def _build_dashscope_chat(
    model: str | None = None, temperature: float | None = None
) -> BaseChatModel:
    from langchain_community.chat_models.tongyi import ChatTongyi

    _require_env("DASHSCOPE_API_KEY", "DashScope")
    return ChatTongyi(
        model=model or rag_conf.get("chat_model_name", "qwen-plus"),
        temperature=(
            rag_conf.get("chat_temperature", 0.3) if temperature is None else temperature
        ),
    )


CHAT_PROVIDERS: dict[str, Callable[..., BaseChatModel]] = {
    "deepseek": _build_deepseek,
    "dashscope": _build_dashscope_chat,
}


# 各 provider 下常用的模型，供界面下拉框使用。
# 放在工厂里而不是界面里：界面不该知道「deepseek 家有哪些模型」这种厂商细节，
# 否则换 provider 时要在两个地方同时改。
_CHAT_MODEL_CHOICES: dict[str, list[str]] = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "dashscope": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long"],
}


def chat_model_choices() -> list[str]:
    """当前 provider 下的候选模型。配置里指定的那个永远排第一，作为默认选中项。"""
    provider = rag_conf.get("chat_provider", "deepseek")
    configured = rag_conf.get("chat_model_name", "")
    return list(
        dict.fromkeys([configured, *_CHAT_MODEL_CHOICES.get(provider, [])])
    ) or [configured]


# ---------------------------------------------------------------------------
# 向量模型
# ---------------------------------------------------------------------------

def _build_dashscope_embedding() -> Embeddings:
    from langchain_community.embeddings import DashScopeEmbeddings

    _require_env("DASHSCOPE_API_KEY", "DashScope")
    return DashScopeEmbeddings(
        model=rag_conf.get("embedding_model_name", "text-embedding-v4")
    )


def _build_local_embedding() -> Embeddings:
    """本地 ONNX 向量模型（fastembed）。

    选它的理由：不依赖 PyTorch、不需要任何 API Key、可离线运行。
    这意味着任何人 clone 本仓库后都能直接跑通检索，而不用先去申请厂商额度。
    首次调用会自动下载模型（约 100MB）。
    """
    from langchain_community.embeddings import FastEmbedEmbeddings

    return FastEmbedEmbeddings(
        model_name=rag_conf.get("embedding_model_name", "BAAI/bge-small-zh-v1.5")
    )


EMBEDDING_PROVIDERS: dict[str, Callable[[], Embeddings]] = {
    "local": _build_local_embedding,
    "dashscope": _build_dashscope_embedding,
}


# ---------------------------------------------------------------------------
# 装配入口
# ---------------------------------------------------------------------------

_cache: dict[str, object] = {}


def _resolve(registry: dict[str, Callable], provider: str, kind: str):
    if provider not in registry:
        raise ProviderError(
            f"未知的 {kind} provider：{provider!r}，可选值为 {sorted(registry)}"
        )
    return registry[provider]


def build_chat_model(
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """构建对话模型。显式传 model/temperature 时绕过缓存，用于界面上的临时切换。

    注意这里是把 model/temperature **传进** builder 构造，而不是构造完再改实例属性。
    各厂商 SDK 的字段名并不统一（model / model_name / model_id），事后赋值会静默失效；
    走构造参数则由各家 SDK 自己负责映射。
    """
    provider = provider or rag_conf.get("chat_provider", "deepseek")

    if model is not None or temperature is not None:
        return _resolve(CHAT_PROVIDERS, provider, "chat")(model, temperature)

    key = f"chat:{provider}"
    if key not in _cache:
        _cache[key] = _resolve(CHAT_PROVIDERS, provider, "chat")()
        logger.info(f"[模型工厂]已装配对话模型 provider={provider}")
    return _cache[key]  # type: ignore[return-value]


def build_embedding_model(provider: str | None = None) -> Embeddings:
    """构建向量模型。"""
    provider = provider or rag_conf.get("embedding_provider", "dashscope")

    key = f"embed:{provider}"
    if key not in _cache:
        _cache[key] = _resolve(EMBEDDING_PROVIDERS, provider, "embedding")()
        logger.info(f"[模型工厂]已装配向量模型 provider={provider}")
    return _cache[key]  # type: ignore[return-value]


def build_judge_model() -> BaseChatModel:
    """构建评测用裁判模型。

    裁判必须输出稳定的 JSON，因此 temperature 强制为 0，且不复用业务模型实例，
    避免界面上调整 temperature 时污染评测结果。
    """
    key = "judge"
    if key not in _cache:
        from langchain_deepseek import ChatDeepSeek

        _require_env("DEEPSEEK_API_KEY", "DeepSeek")
        _cache[key] = ChatDeepSeek(
            model=rag_conf.get("judge_model_name", "deepseek-chat"),
            temperature=0,
        )
        logger.info("[模型工厂]已装配评测裁判模型")
    return _cache[key]  # type: ignore[return-value]


def clear_model_cache() -> None:
    """清空缓存，强制下次访问重新构建（切换模型或测试时使用）。"""
    _cache.clear()


# ---------------------------------------------------------------------------
# 向后兼容：让 `from model.factory import chat_model` 继续可用
# ---------------------------------------------------------------------------

_LAZY_NAMES = {
    "chat_model": build_chat_model,
    "embed_model": build_embedding_model,
}


def __getattr__(name: str):
    """PEP 562 模块级惰性属性。

    如果外部代码给 `model.factory.chat_model` 赋值，赋值会直接写进模块 __dict__，
    后续读取不再走这里，语义与过去一致。
    """
    if name in _LAZY_NAMES:
        return _LAZY_NAMES[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
