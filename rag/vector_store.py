from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.config_handler import chroma_conf

from model.factory import embed_model

from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.path_tool import get_abs_path
from utils.file_handler import pdf_loader, txt_loader, listdir_with_allowed_type, get_file_md5_hex
from utils.logger_handler import logger

import os


def build_retriever(vector_store, k: int, kind: str):
    """检索器的**唯一**装配点。

    评测、调参实验、界面、入库自检全都走这里，为的是杜绝一类很难发现的
    问题：某处代码自己 new 一个检索器、漏掉某个参数，于是**实验跑的根本
    不是生产在用的配置**，数字再漂亮也是无效的。

    本项目真踩过：`eval/run_eval.py` 里写的是 `HybridRetriever(k=k)`，
    漏传 `fetch_k`，于是评测用构造函数的兜底值 `max(k*4, 10) = 12`，
    而生产用配置里的 `hybrid_fetch_k = 10`。每路候选差 2 个，融合后的
    排序会不一样——评测结论对不上线上行为，而且不会有任何报错。

    两者都只需要 `.invoke(query) -> list[Document]`，调用方无需区分。

    :param vector_store: 指向哪个向量库。调参实验会传临时库进来。
    :param k: top-k。
    :param kind: "hybrid"（BM25 + 向量 + RRF）/ "vector"（纯向量）。
    """
    if kind == "hybrid":
        # 惰性导入：纯向量模式下没必要加载 rank_bm25、也没必要建 BM25 索引
        from rag.hybrid_retriever import HybridRetriever

        return HybridRetriever(
            k=k,
            fetch_k=chroma_conf.get("hybrid_fetch_k"),
            rrf_k=chroma_conf.get("rrf_k", 60),
            vector_store=vector_store,
        )

    return vector_store.as_retriever(search_kwargs={"k": k})


class VectorStoreService:
    def __init__(self):
        # 这里一度加过 client_settings=Settings(anonymized_telemetry=False)，
        # 想关掉 chromadb 的遥测报错。结果它不但没关掉（原因见
        # utils/logger_handler.py 的说明），还引入了一个更严重的 bug：
        # langchain_chroma 在收到 client_settings 时会原样透传给
        # chromadb.Client()，而 Settings 的 is_persistent 默认是 False——
        # 于是客户端变成**纯内存**实现，persist_directory 被忽略，
        # 入库的向量只存在于进程内存里，进程一退全部消失。
        # 而它照样打印「内容加载成功」、照样写 md5 台账，
        # 表现是知识库永远为空且毫无报错。
        # 结论：不要传 client_settings，让 langchain_chroma 走它自己的
        # 默认分支（Settings(is_persistent=True) + persist_directory）。
        self.vector_store = Chroma(
            collection_name=chroma_conf["collection_name"],
            embedding_function=embed_model,
            persist_directory=chroma_conf["persist_directory"],
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf["chunk_size"],
            chunk_overlap=chroma_conf["chunk_overlap"],
            separators=chroma_conf["separators"],
            length_function=len,
        )

    def get_retriever(self, k: int | None = None, kind: str | None = None):
        """按 `retriever_type` 配置装配检索器。实现见模块级 `build_retriever`。

        :param k: 覆盖配置里的 top-k。UI 上可调，所以要能按次传入；
                  调用方不该为了改 k 而绕过本方法自己拼检索器——
                  那样会连检索策略一起丢掉。
        :param kind: 覆盖配置里的检索策略，供评测脚本逐个策略对比。
        """
        return build_retriever(
            self.vector_store,
            chroma_conf["k"] if k is None else k,
            kind or chroma_conf.get("retriever_type", "vector"),
        )

    def load_document(self):
        """
        从数据文件夹内读取数据文件，转为向量存入向量库
        要计算文件的MD5做去重
        :return: None
        """

        def check_md5_hex(md5_for_check: str):
            if not os.path.exists(get_abs_path(chroma_conf["md5_hex_store"])):
                # 创建文件
                open(get_abs_path(chroma_conf["md5_hex_store"]), "w", encoding="utf-8").close()
                return False            # md5 没处理过

            with open(get_abs_path(chroma_conf["md5_hex_store"]), "r", encoding="utf-8") as f:
                for line in f.readlines():
                    line = line.strip()
                    if line == md5_for_check:
                        return True     # md5 处理过

                return False            # md5 没处理过

        def save_md5_hex(md5_for_check: str):
            with open(get_abs_path(chroma_conf["md5_hex_store"]), "a", encoding="utf-8") as f:
                f.write(md5_for_check + "\n")

        ledger_path = get_abs_path(chroma_conf["md5_hex_store"])

        # 自愈：台账说「都入库了」，向量库却是空的。
        #
        # md5 台账和向量库是两个独立的文件，可以各自被删、被替换、被回滚。
        # 一旦台账留下了而向量库丢了（换 embedding 模型、重建库、从 git 恢复了
        # chroma_db 却忘了恢复台账……），每个文件都会被判定成「已入库」跳过，
        # 于是知识库永远是空的。
        #
        # 这种失配不报任何错：应用照常启动、照常回答，只是回答没有任何检索
        # 依据——表现为「模型开始编」或「总说资料不足」，是最难定位的一类问题。
        # 本项目就踩过一次：向量库重建后忘了删台账，检索指标从 Hit@1=1.000
        # 直接掉成 0.000，而日志里只有一行「内容已经存在知识库内，跳过」。
        #
        # 判据取「集合为空」：台账非空而集合为空，只可能是向量库丢了，
        # 此时台账没有任何可信度，清掉重来。
        # 用 get(limit=1) 而不是 _collection.count()：前者是公开 API，
        # 只取一条，不会把整个库读进内存。
        if os.path.exists(ledger_path) and os.path.getsize(ledger_path) > 0:
            if not self.vector_store.get(limit=1)["ids"]:
                logger.warning(
                    "[加载知识库]向量库为空但 md5 台账非空，判定台账已失效，"
                    "清空台账后全量重新入库"
                )
                open(ledger_path, "w", encoding="utf-8").close()

        def get_file_documents(read_path: str):
            if read_path.endswith("txt"):
                return txt_loader(read_path)

            if read_path.endswith("pdf"):
                return pdf_loader(read_path)

            return []

        allowed_files_path: list[str] = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allow_knowledge_file_type"]),
        )

        for path in allowed_files_path:
            # 获取文件的MD5
            md5_hex = get_file_md5_hex(path)

            if check_md5_hex(md5_hex):
                logger.info(f"[加载知识库]{path}内容已经存在知识库内，跳过")
                continue

            try:
                documents: list[Document] = get_file_documents(path)

                if not documents:
                    logger.warning(f"[加载知识库]{path}内没有有效文本内容，跳过")
                    continue

                split_document: list[Document] = self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库]{path}分片后没有有效文本内容，跳过")
                    continue

                # 将内容存入向量库
                self.vector_store.add_documents(split_document)

                # 记录这个已经处理好的文件的md5，避免下次重复加载
                save_md5_hex(md5_hex)

                logger.info(f"[加载知识库]{path} 内容加载成功")
            except Exception as e:
                # exc_info为True会记录详细的报错堆栈，如果为False仅记录报错信息本身
                logger.error(f"[加载知识库]{path}加载失败：{str(e)}", exc_info=True)
                continue


if __name__ == '__main__':
    # 知识库入库入口：python -m rag.vector_store
    # 增量：已入库且内容未变的文件会被 md5 台账跳过，可重复执行。
    service = VectorStoreService()
    service.load_document()

    # 用配置里的检索策略跑一次真实提问，确认入库结果可检索。
    # （这里原本查的是「迷路」，一句与知识库无关的教程遗留文本。）
    demo = "年假有几天？"
    print(f"\n自检提问：{demo}")
    for doc in service.get_retriever().invoke(demo):
        print("-" * 40)
        print(doc.page_content.strip()[:120])


