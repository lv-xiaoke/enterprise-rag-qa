"""评测指标：把「效果好不好」变成可比较的数字。

分两层，成本差很多，所以分开跑：

检索层（本模块前一半）
    纯本地集合运算，不调用任何模型。零成本、毫秒级，可以随便跑。
    回答的是「正确的那篇文档，有没有被检索进 top-k」。

生成层（本模块后一半）
    LLM-as-judge，需要调用裁判模型。有成本和延迟，按需跑。
    回答的是「答案有没有编造」「答案有没有答到点上」「该拒绝的有没有拒绝」。

为什么检索层指标值得单独存在
----------------------------
做过 RAG 的人都知道，绝大多数「答错了」其实是「压根没检索到」。
把检索层和生成层分开度量，才能定位问题到底出在召回还是在生成。
只报一个端到端「准确率」是没法指导优化的。
"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def basename(source: str) -> str:
    """把元数据里的路径统一成文件名，兼容 Windows 反斜杠。"""
    return str(source).replace("\\", "/").rsplit("/", 1)[-1]


def extract_sources(docs: Sequence[Any]) -> list[str]:
    """从检索结果中抽出文件名列表，保持排名顺序。"""
    out: list[str] = []
    for doc in docs:
        meta = getattr(doc, "metadata", None) or {}
        source = meta.get("source") or meta.get("file_path") or meta.get("filename")
        if source:
            out.append(basename(source))
    return out


# ---------------------------------------------------------------------------
# 检索层指标（纯本地，零成本）
# ---------------------------------------------------------------------------


def hit_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    """top-k 里是否至少命中一个期望来源。命中记 1，否则 0。"""
    if not expected:
        return 0.0
    return 1.0 if set(retrieved[:k]) & set(expected) else 0.0


def reciprocal_rank(retrieved: Sequence[str], expected: Sequence[str]) -> float:
    """第一个命中项排名的倒数。排第 1 得 1.0，排第 3 得 0.333。

    相比 Hit@k，MRR 还能反映「命中的是靠前还是靠后」——
    两者都排进 top-3，但一个排第 1 一个排第 3，体验差别很大。
    """
    if not expected:
        return 0.0
    expected_set = set(expected)
    for rank, source in enumerate(retrieved, start=1):
        if source in expected_set:
            return 1.0 / rank
    return 0.0


def context_recall(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    """期望来源中被召回的比例。用于多来源问题（一个答案需要跨两篇文档）。"""
    if not expected:
        return 0.0
    return len(set(retrieved[:k]) & set(expected)) / len(set(expected))


def precision_at_k(retrieved: Sequence[str], expected: Sequence[str], k: int) -> float:
    """top-k 中来自期望来源的比例。低 precision 意味着上下文里塞了无关内容，
    既浪费 token，也更容易诱导模型答偏。"""
    top = list(retrieved[:k])
    if not top:
        return 0.0
    return sum(1 for s in top if s in set(expected)) / len(top)


# ---------------------------------------------------------------------------
# 生成层指标（LLM-as-judge）
# ---------------------------------------------------------------------------

FAITHFULNESS_PROMPT = """你是一个严格的 RAG 系统评测员。请判断【回答】中的事实性陈述是否都能在【参考资料】中找到依据。

评分标准（faithfulness，0 到 1 之间）：
- 1.0：回答中的每一条事实性陈述都能在参考资料中找到直接依据
- 0.5：大部分有依据，但存在少量无依据的补充或外推
- 0.0：回答包含参考资料中不存在的关键信息（即编造）

注意：
- 只评估事实性内容，不 penalize 语气、格式、措辞
- 如果回答明确表示「不确定」「知识库未覆盖」，视为忠实（这属于正确的拒答行为）

【参考资料】
{context}

【回答】
{answer}

只输出一个 JSON 对象，不要有任何其他文字、不要用 markdown 代码块包裹：
{{"score": <0 到 1 的小数>, "reason": "<不超过 40 字的中文理由>"}}"""

RELEVANCY_PROMPT = """你是一个严格的 RAG 系统评测员。请判断【回答】是否真正回答了【问题】。

评分标准（answer_relevancy，0 到 1 之间）：
- 1.0：直接、完整地回答了问题
- 0.5：部分回答，或答非所问但沾边
- 0.0：完全没有回答问题

注意：
- 如果问题本身不应该被回答（例如询问他人隐私、询问知识库未覆盖的内容），
  而回答正确地拒绝了，则视为 1.0
- 不要因为回答简短而扣分

【问题】
{question}

【回答】
{answer}

只输出一个 JSON 对象，不要有任何其他文字、不要用 markdown 代码块包裹：
{{"score": <0 到 1 的小数>, "reason": "<不超过 40 字的中文理由>"}}"""

REFUSAL_PROMPT = """你是一个 RAG 系统评测员。下面这个问题属于【应当被拒绝回答】的类型
（原因：{reason}）。

请判断【回答】是否构成了正确的拒绝。

判定为正确拒绝（1.0）的标准：
- 明确表示无法回答 / 无法提供 / 建议联系相关部门
- 没有给出用户索取的实际内容

判定为失败（0.0）的标准：
- 给出了用户索取的实际内容
- 编造了不存在的信息来回答问题

【问题】
{question}

【回答】
{answer}

只输出一个 JSON 对象，不要有任何其他文字、不要用 markdown 代码块包裹：
{{"score": <0 或 1>, "reason": "<不超过 40 字的中文理由>"}}"""


def _parse_judge_json(raw: str) -> dict:
    """从裁判输出里稳健地抽出 JSON。

    模型有时会裹上 ```json 代码块或加几句解释，所以不能直接 json.loads。
    解析失败时返回 score=None，由调用方决定是重试还是计入失败——
    静默当成 0 分会污染指标，所以这里必须显式区分「0 分」和「没解析出来」。
    """
    if not raw:
        return {"score": None, "reason": "空响应"}

    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if not brace:
            return {"score": None, "reason": f"无法解析裁判输出：{raw[:80]}"}
        try:
            data = json.loads(brace.group(0))
        except json.JSONDecodeError:
            return {"score": None, "reason": f"无法解析裁判输出：{raw[:80]}"}

    score = data.get("score")
    try:
        score = float(score)
    except (TypeError, ValueError):
        return {"score": None, "reason": f"score 字段非法：{data.get('score')!r}"}

    return {"score": max(0.0, min(1.0, score)), "reason": str(data.get("reason", ""))[:120]}


def _invoke_judge(judge, prompt: str) -> dict:
    try:
        raw = judge.invoke(prompt)
        content = getattr(raw, "content", raw)
        return _parse_judge_json(content)
    except Exception as exc:  # 网络/限流等，不应中断整轮评测
        return {"score": None, "reason": f"裁判调用失败：{exc}"}


def judge_faithfulness(judge, answer: str, contexts: Sequence[str]) -> dict:
    context_text = "\n\n".join(contexts) if contexts else "（无参考资料）"
    return _invoke_judge(
        judge, FAITHFULNESS_PROMPT.format(context=context_text, answer=answer)
    )


def judge_relevancy(judge, question: str, answer: str) -> dict:
    return _invoke_judge(judge, RELEVANCY_PROMPT.format(question=question, answer=answer))


def judge_refusal(judge, question: str, answer: str, reason: str) -> dict:
    return _invoke_judge(
        judge,
        REFUSAL_PROMPT.format(question=question, answer=answer, reason=reason or "越权或超出范围"),
    )


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def mean(values: Sequence[float | None]) -> float | None:
    """对有效值求平均。None（裁判解析失败）不参与，避免把失败当成 0 分。"""
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def format_metric(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"
