"""入库台账与向量库失配时的自愈行为。

为什么这个用例值得单独存在
--------------------------
`VectorStoreService.load_document` 里有一段「台账非空但集合为空 -> 清空台账
重新入库」的自愈逻辑，对应本项目真实踩过的一次事故：向量库重建后忘了删
md5 台账，检索指标从 Hit@1=1.000 直接掉成 0.000，而日志里只有一行
「内容已经存在知识库内，跳过」。

这段逻辑的可怕之处在于**失败时不报错**。台账和向量库是两个独立文件，
可以各自被删、被替换、被回滚；一旦失配，每个文件都被判定成「已入库」跳过，
知识库永远是空的，应用照常启动、照常回答，只是回答没有任何检索依据。
没有测试盯着的话，将来重构 `load_document` 时很容易把它顺手删掉——
删掉之后全量测试仍然全绿。

关于假向量模型
--------------
这里注入确定性的假 Embeddings，而不是加载真实的 fastembed BGE。本用例要
检验的是**台账与向量库的状态机**，向量的语义质量与之无关；换成真模型只会
让用例慢上十几秒并多一个「首次运行要下载模型」的外部依赖。向量库本身仍是
真实的 Chroma（真实持久化、真实 `get(limit=1)`、真实集合为空），
自愈逻辑依赖的每一步都没有被替身短路。
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import Embeddings

import rag.vector_store as vector_store_module
from rag.vector_store import VectorStoreService
from utils.file_handler import get_file_md5_hex

HANDBOOK = """一、考勤制度
上班时间为上午九点至下午六点，午休一小时。

二、请假制度
年假按工龄计算，入职满一年可享五天。

三、报销制度
差旅费需在返回后十个工作日内提交审批。
"""


class FakeEmbeddings(Embeddings):
    """按文本内容散列出确定性的定长向量。

    确定性很重要：同一个块每次入库必须得到同一个向量，否则「重新入库后
    能否检索到」这个断言就会随机成败。
    """

    def __init__(self, dim: int = 32) -> None:
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        repeated = (digest * (self.dim // len(digest) + 1))[: self.dim]
        return [byte / 255.0 for byte in repeated]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture
def env(tmp_path, monkeypatch) -> SimpleNamespace:
    """把入库所需的一切都指向临时目录。

    配置里的路径本来是相对项目根的，由 `get_abs_path` 拼成绝对路径。
    这里直接把 `get_abs_path` 换成直通函数，让配置里写的绝对路径原样生效——
    比依赖 `os.path.join` 遇到绝对路径会丢弃前一段的行为更好读。
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    doc_path = data_dir / "handbook.txt"
    doc_path.write_text(HANDBOOK, encoding="utf-8")

    ledger = tmp_path / "md5.txt"

    conf = {
        "collection_name": "test_ingest_ledger",
        "persist_directory": str(tmp_path / "chroma"),
        "k": 3,
        "data_path": str(data_dir),
        "md5_hex_store": str(ledger),
        "allow_knowledge_file_type": ["txt", "pdf"],
        "retriever_type": "vector",
        # 与生产一致，避免用例里的切分行为和线上不是一回事
        "chunk_size": 100,
        "chunk_overlap": 20,
        "separators": ["\n\n", "。", ".", "？", "?", "；", ";", "！", "!", " ", ""],
    }

    monkeypatch.setattr(vector_store_module, "chroma_conf", conf)
    monkeypatch.setattr(vector_store_module, "embed_model", FakeEmbeddings())
    monkeypatch.setattr(vector_store_module, "get_abs_path", lambda p: p)

    return SimpleNamespace(
        conf=conf,
        ledger=ledger,
        doc_path=doc_path,
        md5=get_file_md5_hex(str(doc_path)),
    )


def _ingest() -> VectorStoreService:
    """建一个指向临时库的服务并跑一次入库，返回该服务。"""
    service = VectorStoreService()
    service.load_document()
    return service


def _count(service: VectorStoreService) -> int:
    return len(service.vector_store.get()["ids"])


def _ledger_lines(env: SimpleNamespace) -> list[str]:
    if not env.ledger.exists():
        return []
    return [line for line in env.ledger.read_text(encoding="utf-8").split() if line]


# ---------------------------------------------------------------------------
# 基线：正常入库与增量跳过
# ---------------------------------------------------------------------------


class TestHealthyIngest:
    def test_first_run_fills_store_and_ledger(self, env):
        service = _ingest()

        assert _count(service) > 0, "首次入库应当写入向量"
        assert _ledger_lines(env) == [env.md5], "台账应当记下这个文件的 md5"

    def test_second_run_skips_unchanged_file(self, env):
        """内容没变时不该重复入库。

        这条同时是自愈逻辑的**反向**保障：如果那个「清空台账」的判断写得太宽
        （比如漏判了集合非空），每次启动都会全量重灌，台账形同虚设。
        """
        service = _ingest()
        first = _count(service)

        service.load_document()

        assert _count(service) == first, "内容未变时不该产生重复向量"
        assert _ledger_lines(env) == [env.md5], "台账不该被重复追加"


# ---------------------------------------------------------------------------
# 失配自愈：这才是本文件的重点
# ---------------------------------------------------------------------------


class TestStaleLedgerRecovery:
    def test_empty_store_with_stale_ledger_triggers_reingest(self, env):
        """台账说「入过了」、向量库却是空的 —— 必须重新入库。

        这是事故的最小复现：直接把文件的 md5 手写进台账（模拟「台账留下了」），
        而向量库从未写入（模拟「向量库丢了」）。修好之前，这里会因为
        `check_md5_hex` 命中而跳过，集合永远为空。
        """
        env.ledger.write_text(env.md5 + "\n", encoding="utf-8")

        service = _ingest()

        assert _count(service) > 0, (
            "台账非空但向量库为空时应当判定台账失效并重新入库，"
            "否则知识库会永久为空且不报任何错"
        )

    def test_recovery_clears_the_stale_entry_instead_of_duplicating(self, env):
        """清空台账要清干净，不能让旧条目和新条目共存。

        否则下次启动时同一个 md5 在台账里有两行——虽然结果仍然是跳过，
        但台账会随着每一次「失配->恢复」不断膨胀，且再也无法反推出
        「哪些文件真的入库过」。
        """
        env.ledger.write_text(env.md5 + "\n" + "f" * 32 + "\n", encoding="utf-8")

        _ingest()

        assert _ledger_lines(env) == [env.md5], (
            "失效台账里那条伪造的 md5 应当被一并清掉，只留下本次真正入库的记录"
        )

    def test_healthy_store_does_not_wipe_the_ledger(self, env):
        """集合非空时，台账里的其他条目必须原样保留。

        自愈逻辑的判断是「集合为空」，不是「台账有内容」。写反了的话，
        每次启动都会把所有历史记录清掉，增量入库彻底失效——而且同样不报错，
        只是每次都要全量重灌，文件多了以后启动慢得莫名其妙。
        """
        other = "a" * 32
        service = _ingest()
        env.ledger.write_text(other + "\n" + env.md5 + "\n", encoding="utf-8")

        service.load_document()

        assert other in _ledger_lines(env), "向量库非空时不该动台账"

    def test_recovery_is_logged_as_a_warning(self, env, caplog):
        """自愈必须留痕。

        这个分支平时不走，一旦走了就说明数据出过问题（有人删了向量库、
        或换了 embedding 模型重建）。静默恢复的话，运维永远不知道发生过什么。
        """
        env.ledger.write_text(env.md5 + "\n", encoding="utf-8")

        with caplog.at_level("WARNING"):
            _ingest()

        assert any("台账已失效" in r.message for r in caplog.records), (
            f"应当留下一条 warning，实际记录：{[r.message for r in caplog.records]}"
        )


class TestWipedCollectionRecovery:
    def test_reingest_after_collection_is_wiped(self, env):
        """完整复现事故：入库 -> 向量库被清空（台账还在）-> 再次启动。

        与上面手写台账的区别是这里走完了真实链路：第一次入库是真的写入，
        然后用 `reset_collection()` 把集合清掉——对应「换了 embedding 模型
        重建向量库，却忘了删台账」。
        """
        service = _ingest()
        assert _count(service) > 0
        assert _ledger_lines(env) == [env.md5]

        service.vector_store.reset_collection()
        assert _count(service) == 0, "前置条件：集合应当已被清空"

        recovered = _ingest()

        assert _count(recovered) > 0, "重启后应当发现失配并重新入库"
        assert _ledger_lines(env) == [env.md5]

    def test_recovered_store_is_actually_retrievable(self, env):
        """重新入库不能只是「写进去了」，还要真的检索得到。

        只断言集合非空的话，一个写坏了元数据、或用了不一致 embedding 的
        「恢复」也能骗过测试——而检索不到才是这个 bug 的最终表现。
        """
        _ingest()
        service = VectorStoreService()
        service.vector_store.reset_collection()

        recovered = _ingest()

        hits = recovered.get_retriever().invoke("年假有几天")
        assert hits, "恢复后应当能检索到内容"
        assert any("年假" in doc.page_content for doc in hits)
