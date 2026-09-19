"""分块粒度实验：验证「块边界是否与文档语义边界对齐」对检索的影响。

背景
----
知识库里的 6 篇制度文档结构一致：标题 + 五个小节，每节 50~90 字，节与节之间
用空行分隔。这些小节是语义上不可再分的单元——一节只讲一件事。

但 chunk_size=200 会让切分器把两节合进同一个块。实测 `it_support_policy.txt`
的「三、故障处理」(VPN/邮箱无法登录) 和「四、数据安全」(禁止拷贝到个人网盘)
就被合进了同一块。后果是这一个块同时对两类毫不相干的问题都有较高的向量相似度，
变成「万金油块」，持续挤占 top-k 席位，把真正相关的块往下压。

这类问题的隐蔽之处在于：Hit@k 完全看不出来（正确文档照样在 top-k 里），
但 Precision@k 会很低——上下文里塞满了无关内容，白白烧 token 还容易诱导模型答偏。

扫描而不是拍脑袋
----------------
把 chunk_size 从 80 扫到 500，每个取值重建一次临时向量库并跑同一套评测集。
用数据回答「切多大合适」，而不是凭感觉调参。

复用生产的融合逻辑
------------------
实验直接复用 HybridRetriever，只把向量库换成临时的那个。如果实验里另写一套
融合代码，结论就对不上生产行为了。

用法
----
    python -m eval.tune_chunking                    # 纯向量 + 混合，各扫一遍
    python -m eval.tune_chunking --strategy vector  # 只扫一种，省一半时间
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from eval import metrics
from eval.run_eval import load_golden_set
from model.factory import embed_model
from utils.config_handler import chroma_conf
from utils.file_handler import listdir_with_allowed_type, txt_loader

# 围绕「单节长度（50~90 字）」上下取点，并覆盖到「整篇一个块」
CHUNK_SIZES = [80, 100, 120, 150, 200, 300, 500]
K = 3
TUNE_ROOT = Path("chroma_db.tune")


def load_chunks(chunk_size: int, chunk_overlap: int) -> list:
    """按给定粒度切分知识库全部文档。"""
    spliter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=chroma_conf["separators"],
        length_function=len,
    )
    paths = listdir_with_allowed_type(
        chroma_conf["data_path"], tuple(chroma_conf["allow_knowledge_file_type"])
    )

    chunks: list = []
    for path in paths:
        if path.endswith("txt"):
            chunks.extend(spliter.split_documents(txt_loader(path)))
    return chunks


def build_retriever(store, strategy: str):
    """按策略装配检索器，都指向传入的临时向量库。

    复用生产的装配函数，只把向量库换成临时的那个——这样 `fetch_k`、`rrf_k`
    等参数与线上完全一致。实验里另写一套装配代码，结论就对不上生产行为了。
    """
    from rag.vector_store import build_retriever as _build

    return _build(store, K, strategy)


def evaluate(chunk_size: int, chunk_overlap: int, items: list[dict], strategy: str) -> dict:
    """在指定粒度下重建向量库并跑一遍检索指标。"""
    persist = TUNE_ROOT / f"{strategy}_{chunk_size}"
    shutil.rmtree(persist, ignore_errors=True)

    chunks = load_chunks(chunk_size, chunk_overlap)
    store = Chroma(
        collection_name=f"tune_{strategy}_{chunk_size}",
        embedding_function=embed_model,
        persist_directory=str(persist),
    )
    store.add_documents(chunks)

    retriever = build_retriever(store, strategy)

    hits1: list[float] = []
    hitsk: list[float] = []
    rrs: list[float] = []
    precs: list[float] = []

    for it in items:
        expected = it.get("expected_sources")
        if not expected:
            continue
        docs = retriever.invoke(it["question"])[:K]
        sources = metrics.extract_sources(docs)
        hits1.append(metrics.hit_at_k(sources, expected, 1))
        hitsk.append(metrics.hit_at_k(sources, expected, K))
        rrs.append(metrics.reciprocal_rank(sources, expected))
        precs.append(metrics.precision_at_k(sources, expected, K))

    avg_len = sum(len(c.page_content) for c in chunks) / len(chunks) if chunks else 0.0

    return {
        "chunk_size": chunk_size,
        "strategy": strategy,
        "n_chunks": len(chunks),
        "avg_len": avg_len,
        "hit_at_1": metrics.mean(hits1),
        "hit_at_k": metrics.mean(hitsk),
        "mrr": metrics.mean(rrs),
        "precision_at_k": metrics.mean(precs),
    }


def sweep(strategy: str, items: list[dict], overlap: int) -> list[dict]:
    """扫描全部 chunk_size，打印一张表，返回各行结果。"""
    print(f"\n=== 检索策略：{strategy} ===")
    print(
        f"{'chunk_size':>10} {'块数':>6} {'平均块长':>8} "
        f"{'Hit@1':>7} {'Hit@3':>7} {'MRR':>7} {'P@3':>7}"
    )
    print("-" * 62)

    rows: list[dict] = []
    for size in CHUNK_SIZES:
        row = evaluate(size, overlap, items, strategy)
        rows.append(row)
        print(
            f"{size:>10} {row['n_chunks']:>6} {row['avg_len']:>8.0f} "
            f"{metrics.format_metric(row['hit_at_1']):>7} "
            f"{metrics.format_metric(row['hit_at_k']):>7} "
            f"{metrics.format_metric(row['mrr']):>7} "
            f"{metrics.format_metric(row['precision_at_k']):>7}"
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="分块粒度扫描")
    parser.add_argument(
        "--strategy",
        choices=["vector", "hybrid", "both"],
        default="both",
        help="只跑某一种检索策略，默认两种都跑",
    )
    args = parser.parse_args()

    items = load_golden_set()
    overlap = chroma_conf["chunk_overlap"]
    n_docs = len(
        listdir_with_allowed_type(
            chroma_conf["data_path"], tuple(chroma_conf["allow_knowledge_file_type"])
        )
    )
    strategies = ["vector", "hybrid"] if args.strategy == "both" else [args.strategy]

    print(f"知识库文档数：{n_docs}")
    print(f"评测题数：{sum(1 for it in items if it.get('expected_sources'))}（仅检索类）")
    print(f"chunk_overlap 固定为 {overlap}")

    results = {s: sweep(s, items, overlap) for s in strategies}

    # 排序键：Hit@1 优先（判别力最强），并列时看 P@3（上下文纯度）
    print(f"\n当前配置 chunk_size={chroma_conf['chunk_size']}")
    for strategy, rows in results.items():
        best = max(rows, key=lambda r: (r["hit_at_1"] or 0.0, r["precision_at_k"] or 0.0))
        print(
            f"[{strategy}] 按「Hit@1 优先、P@{K} 次之」排序，"
            f"最佳 chunk_size={best['chunk_size']}"
            f"（Hit@1={metrics.format_metric(best['hit_at_1'])}，"
            f"P@{K}={metrics.format_metric(best['precision_at_k'])}）"
        )

    shutil.rmtree(TUNE_ROOT, ignore_errors=True)
    print(f"\n临时向量库已清理：{TUNE_ROOT}")


if __name__ == "__main__":
    main()
