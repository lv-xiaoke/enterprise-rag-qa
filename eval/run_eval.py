"""RAG / Agent 评测入口。

用法
----
纯检索指标（零成本、秒级，改完切分或检索策略就重跑一次）：

    python -m eval.run_eval --retriever vector --mode retrieval --tag baseline
    python -m eval.run_eval --retriever hybrid --mode retrieval --tag hybrid

生成指标（需要 DEEPSEEK_API_KEY，会调用裁判模型）：

    python -m eval.run_eval --retriever hybrid --mode all --tag hybrid

产物
----
    eval/report_<tag>.md     人看的报告，可直接贴进 README
    eval/results_<tag>.json  逐题明细，用于回归对比和排查

设计取舍
--------
生成模式默认走纯 RAG 链路而不是完整 Agent：RAG 指标要度量的是
「检索 + 生成」，把 Agent 的多步工具调用混进来会让归因变模糊。
需要评估 Agent 的拒答策略时用 --pipeline agent。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from eval import metrics

GOLDEN_SET_PATH = Path("eval/golden_set.jsonl")


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"评测集不存在：{path}")
    items: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno} 不是合法 JSON：{exc}") from exc
    return items


def build_retriever(kind: str, k: int):
    """按名称装配检索器。

    刻意委托给 `rag.vector_store.build_retriever`——**评测必须和线上跑同一套
    装配逻辑**。这里曾经自己 new 了 `HybridRetriever(k=k)`，漏传 `fetch_k`，
    于是评测用兜底值 12 而生产用配置里的 10，测的根本不是线上配置。
    """
    from rag.vector_store import VectorStoreService, build_retriever as _build

    svc = VectorStoreService()
    return _build(svc.vector_store, k, kind)


def retrieve(retriever, query: str, k: int) -> list[Any]:
    """统一取回文档列表。

    hybrid 与 langchain retriever 都返回 List[Document]，但为了兼容将来可能
    返回 (doc, score) 的实现，这里做一次归一化。
    """
    docs = retriever.invoke(query)
    normalized = []
    for item in docs[:k]:
        normalized.append(item[0] if isinstance(item, tuple) else item)
    return normalized


# ---------------------------------------------------------------------------
# 检索层评测
# ---------------------------------------------------------------------------


def run_retrieval(items: Sequence[dict], retriever, k: int) -> dict:
    per_item: list[dict] = []
    cases = [it for it in items if it.get("expected_sources")]

    for it in cases:
        docs = retrieve(retriever, it["question"], k)
        sources = metrics.extract_sources(docs)

        per_item.append(
            {
                "id": it["id"],
                "category": it["category"],
                "question": it["question"],
                "expected": it["expected_sources"],
                "retrieved": sources,
                "hit": metrics.hit_at_k(sources, it["expected_sources"], k),
                "hit_at_1": metrics.hit_at_k(sources, it["expected_sources"], 1),
                "rr": metrics.reciprocal_rank(sources, it["expected_sources"]),
                "recall": metrics.context_recall(sources, it["expected_sources"], k),
                "precision": metrics.precision_at_k(sources, it["expected_sources"], k),
            }
        )

    return {
        "k": k,
        "n_cases": len(cases),
        "hit_at_1": metrics.mean([r["hit_at_1"] for r in per_item]),
        "hit_at_k": metrics.mean([r["hit"] for r in per_item]),
        "mrr": metrics.mean([r["rr"] for r in per_item]),
        "context_recall": metrics.mean([r["recall"] for r in per_item]),
        "precision_at_k": metrics.mean([r["precision"] for r in per_item]),
        "per_item": per_item,
    }


# ---------------------------------------------------------------------------
# 生成层评测
# ---------------------------------------------------------------------------


def run_generation(items: Sequence[dict], retriever, k: int, judge, pipeline: str) -> dict:
    if pipeline == "agent":
        from agent.react_agent import ReactAgent

        agent = ReactAgent()
        rag_svc = None
    else:
        from rag.rag_service import RagSummarizeService

        rag_svc = RagSummarizeService()
        agent = None

    per_item: list[dict] = []

    for it in items:
        question = it["question"]
        docs = retrieve(retriever, question, k)
        contexts = [d.page_content for d in docs]
        sources = metrics.extract_sources(docs)

        try:
            if pipeline == "agent":
                answer = "".join(agent.execute_stream(question))
            else:
                context_text = "\n".join(
                    f"【参考资料{i}】{c}" for i, c in enumerate(contexts, start=1)
                )
                answer = rag_svc.chain.invoke({"input": question, "context": context_text})
        except Exception as exc:
            per_item.append(
                {
                    "id": it["id"],
                    "category": it["category"],
                    "question": question,
                    "error": str(exc),
                    "faithfulness": None,
                    "relevancy": None,
                    "refusal": None,
                }
            )
            continue

        faith = metrics.judge_faithfulness(judge, answer, contexts)
        relev = metrics.judge_relevancy(judge, question, answer)

        row = {
            "id": it["id"],
            "category": it["category"],
            "question": question,
            "answer": answer,
            "retrieved": sources,
            "faithfulness": faith["score"],
            "faithfulness_reason": faith["reason"],
            "relevancy": relev["score"],
            "relevancy_reason": relev["reason"],
        }

        if it.get("should_refuse"):
            refusal = metrics.judge_refusal(judge, question, answer, it.get("note", ""))
            row["refusal"] = refusal["score"]
            row["refusal_reason"] = refusal["reason"]

        per_item.append(row)

    refusal_cases = [r for r in per_item if r.get("refusal") is not None]

    return {
        "k": k,
        "pipeline": pipeline,
        "n_cases": len(per_item),
        "faithfulness": metrics.mean([r["faithfulness"] for r in per_item]),
        "relevancy": metrics.mean([r["relevancy"] for r in per_item]),
        "refusal_accuracy": metrics.mean([r["refusal"] for r in refusal_cases]),
        "n_refusal_cases": len(refusal_cases),
        "per_item": per_item,
    }


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def build_report(tag: str, retrieval: dict | None, generation: dict | None, k: int) -> str:
    lines = [f"# 评测报告 · `{tag}`", ""]
    lines.append(f"- 检索深度 top-k：**{k}**")

    if retrieval:
        lines += [
            f"- 检索题数：**{retrieval['n_cases']}**",
            "",
            "## 检索层指标（本地计算，不调用模型）",
            "",
            "| 指标 | 数值 | 含义 |",
            "|---|---|---|",
            f"| **Hit@1** | **{metrics.format_metric(retrieval['hit_at_1'])}** | 正确文档是否排在**第 1 位**，判别力最强 |",
            f"| Hit@{k} | {metrics.format_metric(retrieval['hit_at_k'])} | 正确文档是否进入 top-{k}（k 大时会饱和，容易掩盖问题）|",
            f"| MRR | {metrics.format_metric(retrieval['mrr'])} | 命中项排名的倒数均值，反映排序质量 |",
            f"| Context Recall | {metrics.format_metric(retrieval['context_recall'])} | 期望来源被召回的比例 |",
            f"| Precision@{k} | {metrics.format_metric(retrieval['precision_at_k'])} | top-{k} 中有效内容的占比，低值说明上下文被无关内容稀释 |",
            "",
        ]

        # 来源分布诊断：对比「被召回次数」与「被期望次数」。
        # 某篇文档被召回的次数远高于它真正该出现的次数，说明它是个「万金油文档」——
        # 主题泛、与谁都沾边，会持续挤占 top-k 席位，把正确答案往下压。
        # 这类问题在 Hit@k 上完全看不出来（命中率依然 100%），必须靠这个分布暴露。
        retrieved_count: dict[str, int] = {}
        expected_count: dict[str, int] = {}
        total_slots = 0
        for r in retrieval["per_item"]:
            for s in r["retrieved"]:
                retrieved_count[s] = retrieved_count.get(s, 0) + 1
                total_slots += 1
            for s in r["expected"]:
                expected_count[s] = expected_count.get(s, 0) + 1

        if retrieved_count:
            lines += ["### 来源召回分布（诊断过度召回）", ""]
            lines.append("| 文档 | 被召回 | 占 top-k 席位 | 被期望 | 偏离 |")
            lines.append("|---|---|---|---|---|")
            for source, count in sorted(
                retrieved_count.items(), key=lambda kv: kv[1], reverse=True
            ):
                expected_n = expected_count.get(source, 0)
                share = count / total_slots if total_slots else 0.0
                # 召回次数是被期望次数的 2 倍以上，且绝对次数不少，就标出来
                flag = " ⚠️ 过度召回" if expected_n and count >= 2 * expected_n else ""
                lines.append(
                    f"| `{source}` | {count} | {share:.0%} | {expected_n} | "
                    f"{count - expected_n:+d}{flag} |"
                )
            lines.append("")

        misses = [r for r in retrieval["per_item"] if r["hit"] == 0.0]
        if misses:
            lines += [f"### 未命中题目（{len(misses)} 条）", ""]
            for m in misses:
                lines.append(
                    f"- `{m['id']}` {m['question']}\n"
                    f"  - 期望：`{', '.join(m['expected'])}`\n"
                    f"  - 实际：`{', '.join(m['retrieved']) or '(空)'}`"
                )
            lines.append("")

        ranked = sorted(retrieval["per_item"], key=lambda r: r["rr"])
        lines += ["### 排序质量最差的题目", ""]
        for r in ranked[:5]:
            lines.append(f"- `{r['id']}` RR={r['rr']:.3f} · {r['question']}")
        lines.append("")

    if generation:
        lines += [
            f"- 生成题数：**{generation['n_cases']}**（链路 `{generation['pipeline']}`）",
            "",
            "## 生成层指标（LLM-as-judge）",
            "",
            "| 指标 | 数值 | 含义 |",
            "|---|---|---|",
            f"| Faithfulness | **{metrics.format_metric(generation['faithfulness'])}** | 答案是否只依据检索到的资料，衡量幻觉 |",
            f"| Answer Relevancy | {metrics.format_metric(generation['relevancy'])} | 答案是否真正回答了问题 |",
            f"| Refusal Accuracy | {metrics.format_metric(generation['refusal_accuracy'])}"
            f" | 越权/超范围问题是否正确拒绝（{generation['n_refusal_cases']} 条）|",
            "",
        ]

        bad = [r for r in generation["per_item"] if (r.get("faithfulness") or 0) < 0.8]
        if bad:
            lines += ["### 忠实度低于 0.8 的题目", ""]
            for r in bad:
                lines.append(
                    f"- `{r['id']}` faithfulness={metrics.format_metric(r.get('faithfulness'))} "
                    f"· {r['question']}\n  - 裁判理由：{r.get('faithfulness_reason', '')}"
                )
            lines.append("")

        failed_refusal = [r for r in generation["per_item"] if r.get("refusal") == 0.0]
        if failed_refusal:
            lines += ["### 未能正确拒绝的题目（安全性问题）", ""]
            for r in failed_refusal:
                lines.append(
                    f"- `{r['id']}` {r['question']}\n  - 裁判理由：{r.get('refusal_reason', '')}"
                )
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _build_judge():
    """惰性构建裁判模型，缺 Key 时给出明确指引而不是抛堆栈。"""
    from model.factory import ProviderError, build_judge_model

    try:
        return build_judge_model()
    except ProviderError as exc:
        raise SystemExit(
            f"\n无法启动生成层评测：{exc}\n"
            "提示：检索层指标不需要任何 API Key，可用 --mode retrieval 单独运行。"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG / Agent 评测")
    parser.add_argument(
        "--retriever", default="vector", choices=["vector", "hybrid"], help="检索策略"
    )
    parser.add_argument(
        "--mode", default="retrieval", choices=["retrieval", "generation", "all"]
    )
    parser.add_argument(
        "--pipeline", default="rag", choices=["rag", "agent"], help="生成阶段走哪条链路"
    )
    parser.add_argument("--k", type=int, default=3, help="检索深度")
    parser.add_argument("--tag", default=None, help="结果文件后缀，默认由策略名推导")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 题（调试用）")
    args = parser.parse_args()

    tag = args.tag or args.retriever
    items = load_golden_set()
    if args.limit:
        items = items[: args.limit]

    retriever = build_retriever(args.retriever, args.k)

    retrieval_result = None
    generation_result = None

    if args.mode in ("retrieval", "all"):
        retrieval_result = run_retrieval(items, retriever, args.k)
        print(
            f"[检索层] Hit@1={metrics.format_metric(retrieval_result['hit_at_1'])} "
            f"Hit@{args.k}={metrics.format_metric(retrieval_result['hit_at_k'])} "
            f"MRR={metrics.format_metric(retrieval_result['mrr'])} "
            f"P@{args.k}={metrics.format_metric(retrieval_result['precision_at_k'])}"
        )

    if args.mode in ("generation", "all"):
        judge = _build_judge()
        generation_result = run_generation(items, retriever, args.k, judge, args.pipeline)
        print(
            f"[生成层] Faithfulness={metrics.format_metric(generation_result['faithfulness'])} "
            f"Relevancy={metrics.format_metric(generation_result['relevancy'])} "
            f"Refusal={metrics.format_metric(generation_result['refusal_accuracy'])}"
        )

    report = build_report(tag, retrieval_result, generation_result, args.k)
    report_path = Path(f"eval/report_{tag}.md")
    report_path.write_text(report, encoding="utf-8")

    payload = {
        "tag": tag,
        "retriever": args.retriever,
        "k": args.k,
        "retrieval": retrieval_result,
        "generation": generation_result,
    }
    results_path = Path(f"eval/results_{tag}.json")
    results_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n报告已写入：{report_path}")
    print(f"明细已写入：{results_path}")


if __name__ == "__main__":
    main()
