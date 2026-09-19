"""混合检索：BM25 稀疏检索 + 向量稠密检索，用 RRF 融合。

为什么需要混合
--------------
纯向量检索有两个已知短板：

1. **精确词面匹配弱**。向量检索对「3000 元」「6 个月」「2 个工作日」这类
   数字和专有名词不敏感，而 BM25 恰好擅长这个。
2. **对切分边界敏感**。块切得不巧时（把小节从中间切断、或把相邻两节合成
   一块），正确块被稀释，排名往下掉。

把 `chunk_size` 从 80 扫到 500（见 eval/tune_chunking.py），真正兑现的是第 2 条：
**混合检索在 Hit@1 / MRR 上一次都没输给纯向量**（7 个配置里 5 胜 2 平），
而纯向量在 `chunk_size=80`、`150` 处掉到 0.960。切分边界不巧时，BM25 的词面
匹配把正确文档重新拽回第 1 位。

代价是 `P@3`：混合检索在 7 个配置里 5 次低于纯向量。BM25 只认词面，
问「年假」时它会把所有出现「年假」二字的块都往上抬，其中一些并不是答案所在。
实测 `finance_reimbursement_policy.txt` 的 top-k 席位占比被从纯向量的 24%
抬到 31%，而它只是 6 道题的期望来源。

反过来 BM25 也有短板：不会处理同义改写（「年假」vs「带薪休假」）。
两者互补，融合后能同时覆盖「词面精确」和「语义相近」两类需求。

关于中文分词
------------
BM25 依赖分词，而中文没有空格。这里用**字符二元组（bigram）**而不是引入 jieba：

- 不增加依赖，不走 IO，初始化快
- 对中文的召回效果稳定，是信息检索里的经典做法
- 代价是没有词边界概念，但对「BM25 负责兜底词面匹配」这个定位来说足够了

关于 RRF
--------
Reciprocal Rank Fusion 只使用**排名**而不使用**分数**：

    score(d) = Σ 1 / (rrf_k + rank_r(d))

这样做的好处是绕开了「BM25 分数和余弦相似度量纲不同、无法直接加权」的问题。
两种检索器的分数分布完全不可比，但排名是可比的。rrf_k 默认 60（原论文取值），
作用是压低头部排名的绝对优势，让两个列表的中段结果也能参与竞争。
"""

from __future__ import annotations

import re
from typing import Sequence

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from utils.logger_handler import logger


def tokenize_zh(text: str) -> list[str]:
    """中文友好的轻量分词：去空白后取字符二元组。"""
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) < 2:
        return list(compact)
    return [compact[i : i + 2] for i in range(len(compact) - 1)]


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], rrf_k: int = 60
) -> dict[str, float]:
    """对多组排名做 RRF 融合，返回 key -> 融合分。

    入参是若干「按相关性从高到低排列的 key 列表」。
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
    return scores


class HybridRetriever:
    """BM25 + 向量 + RRF 的混合检索器。

    对外只需要 `.invoke(query)`，和 LangChain retriever 的用法一致，
    这样评测脚本和业务代码都能无差别替换。
    """

    def __init__(
        self,
        k: int = 3,
        fetch_k: int | None = None,
        rrf_k: int = 60,
        bm25_weight: float = 1.0,
        vector_weight: float = 1.0,
        vector_store=None,
    ) -> None:
        self.k = k
        # 每路先各取 fetch_k 个候选再融合。取太小时融合没有意义，
        # 默认取 k 的 4 倍并至少 10 个。
        self.fetch_k = fetch_k or max(k * 4, 10)
        self.rrf_k = rrf_k
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight

        if vector_store is None:
            from rag.vector_store import VectorStoreService

            vector_store = VectorStoreService().vector_store
        # 允许注入向量库：调参实验（如比较不同分块粒度）需要指向临时的库，
        # 但又必须复用这里同一套融合逻辑，否则实验结论对不上生产行为。
        self._vector_store = vector_store

        raw = self._vector_store.get(include=["documents", "metadatas"])
        contents: list[str] = raw.get("documents") or []
        metadatas: list[dict] = raw.get("metadatas") or [{} for _ in contents]

        self._docs: list[Document] = [
            Document(page_content=c, metadata=m or {})
            for c, m in zip(contents, metadatas)
        ]
        # 用 chunk 内容本身作为融合时的 key：同一份文档会被切成多块，
        # 用 source 当 key 会把不同块合并掉，丢掉块级区分度。
        self._key_to_doc: dict[str, Document] = {d.page_content: d for d in self._docs}

        corpus = [tokenize_zh(d.page_content) for d in self._docs]
        self._bm25 = BM25Okapi(corpus) if corpus else None

        logger.info(
            f"[混合检索]已建立 BM25 索引，语料 {len(self._docs)} 块，"
            f"k={k} fetch_k={self.fetch_k} rrf_k={rrf_k}"
        )

    # -- 内部：两路召回各自的排名 ------------------------------------------

    def _bm25_ranking(self, query: str) -> list[str]:
        if self._bm25 is None:
            return []
        tokens = tokenize_zh(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._docs[i].page_content for i in order[: self.fetch_k]]

    def _vector_ranking(self, query: str) -> list[str]:
        try:
            pairs = self._vector_store.similarity_search_with_score(query, k=self.fetch_k)
        except Exception as exc:  # 向量库不可用时退化为纯 BM25，而不是整体失败
            logger.error(f"[混合检索]向量召回失败，本次退化为 BM25：{exc}")
            return []
        # Chroma 返回的是距离，越小越相关
        pairs.sort(key=lambda p: p[1])
        return [doc.page_content for doc, _ in pairs]

    # -- 对外 ---------------------------------------------------------------

    def invoke(self, query: str) -> list[Document]:
        rankings: list[list[str]] = []
        if self.bm25_weight:
            rankings.append(self._bm25_ranking(query))
        if self.vector_weight:
            rankings.append(self._vector_ranking(query))

        if not rankings:
            return []

        fused = reciprocal_rank_fusion(rankings, rrf_k=self.rrf_k)
        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

        results: list[Document] = []
        for key, _score in ordered:
            doc = self._key_to_doc.get(key)
            if doc is not None:
                results.append(doc)
            if len(results) >= self.k:
                break
        return results

    def __call__(self, query: str) -> list[Document]:
        return self.invoke(query)


if __name__ == "__main__":
    # 手动对比一下同一问题在两种检索器下的排序差异
    from rag.vector_store import VectorStoreService

    query = "离职或岗位调整时需要完成哪些 IT 相关事项？"
    vector = VectorStoreService().vector_store.as_retriever(search_kwargs={"k": 3})
    hybrid = HybridRetriever(k=3)

    print(f"问题：{query}\n")
    print("--- 纯向量 ---")
    for i, d in enumerate(vector.invoke(query), 1):
        print(f"  {i}. {d.metadata.get('source')}")
    print("--- 混合检索 ---")
    for i, d in enumerate(hybrid.invoke(query), 1):
        print(f"  {i}. {d.metadata.get('source')}")
