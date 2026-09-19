"""RAG 总结服务：检索参考资料 -> 拼进提示词 -> 交给模型总结。

关于「引用来源」的回传
----------------------
业务上需要把命中哪些文档展示给用户。直觉做法是界面层再检索一次
（`retriever_docs(query)`），但那样有两个问题：

1. **浪费一次检索**。embedding + BM25 是这条链路上最贵的两步，每次提问都跑两遍。
2. **展示的来源可能是错的**。Agent 会改写查询再调 `rag_summarize`（原始提问
   「年假怎么算」可能被改写成「年假 计算规则 工龄」），界面层用原始提问再检索一次，
   拿到的往往不是模型实际读到的那些块——用户看到的「依据」和答案的真实依据对不上。

所以改成由业务路径自己把检索结果登记下来，界面层直接读。用 ContextVar 而不是
实例属性：实例是全局单例，并发请求会互相覆盖来源。
"""

from __future__ import annotations

from contextvars import ContextVar

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts


def _current_chat_model():
    """取对话模型，但**不在 import 阶段**构建客户端。

    原先这里是顶层的 `from model.factory import chat_model`。那会让
    `import rag.rag_service` 直接触发模型构建——没有 API Key 时 import 就抛
    `ProviderError`，于是 api/server.py 连同服务进程一起起不来，
    测试也收集不了。`agent/react_agent.py` 早就为此做了惰性处理，
    这里保持一致。
    """
    from model.factory import chat_model

    return chat_model

# 本次请求实际检索到的文档块。
# 只存「最后一次」检索：一次 rag_summarize 调用对应一次检索，
# 多轮工具调用时展示的自然是最后一轮（即生成最终答案所依据的那一批）。
_last_docs: ContextVar[list[Document]] = ContextVar("last_retrieved_docs", default=[])


def last_retrieved_docs() -> list[Document]:
    """读取当前请求最近一次检索到的文档块，供界面展示引用来源。"""
    return _last_docs.get()


def normalize_sources(raw_docs: list) -> list[dict[str, str]]:
    """把检索到的 Document 转成「引用来源」的对外结构。

    放在这一层而不是界面层：引用来源是**接口契约**，Streamlit 和 FastAPI
    要给出一模一样的东西。原先它定义在 app.py 里，服务端想复用就得 import
    streamlit——为了一个纯数据转换把整个 UI 框架拖进服务进程，明显不合适。
    """
    sources = []
    for index, doc in enumerate(raw_docs, start=1):
        metadata = getattr(doc, "metadata", {}) or {}
        source = (
            metadata.get("source")
            or metadata.get("file_path")
            or metadata.get("filename")
            or "企业知识库"
        )
        page = metadata.get("page")
        if page is not None:
            source = f"{source} · p.{page}"

        content = " ".join(getattr(doc, "page_content", "").split())
        sources.append(
            {
                "title": f"文本块 {index}",
                "source": str(source),
                "content": content[:520],
            }
        )
    return sources


class RagSummarizeService(object):
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.retriever = self.vector_store.get_retriever()
        self.prompt_text = load_rag_prompts()
        self.prompt_template = PromptTemplate.from_template(self.prompt_text)
        self.model = _current_chat_model()
        self.chain = self._init_chain()

    def _init_chain(self):
        # 这里曾经挂着一个 print_prompt 节点，把拼好的提示词打到 stdout。
        # 调试完就该摘掉：它会在每次问答时把整段知识库原文写进日志，
        # 既污染输出，也让日志里混进大量业务数据。
        return self.prompt_template | self.model | StrOutputParser()

    def retriever_docs(self, query: str) -> list[Document]:
        docs = self.retriever.invoke(query)
        _last_docs.set(docs)
        return docs

    def rag_summarize(self, query: str) -> str:
        context_docs = self.retriever_docs(query)

        context = ""
        for counter, doc in enumerate(context_docs, start=1):
            context += (
                f"【参考资料{counter}】: 参考资料：{doc.page_content} "
                f"| 参考元数据：{doc.metadata}\n"
            )

        return self.chain.invoke(
            {
                "input": query,
                "context": context,
            }
        )


if __name__ == "__main__":
    rag = RagSummarizeService()

    print(rag.rag_summarize("小户型适合哪些扫地机器人"))
