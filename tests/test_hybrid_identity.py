from langchain_core.documents import Document
from rag.hybrid_retriever import HybridRetriever


def test_identical_text_from_different_chunks_preserves_both_sources():
    docs = [Document(page_content='共同制度内容', metadata={'chunk_id': key}) for key in ['a', 'b']]
    class Store:
        def get(self, **kwargs):
            return {'documents': [d.page_content for d in docs], 'metadatas': [d.metadata for d in docs]}
        def similarity_search_with_score(self, query, k):
            return [(d, i) for i, d in enumerate(docs)]
    results = HybridRetriever(k=2, vector_store=Store()).invoke('制度')
    assert {d.metadata['chunk_id'] for d in results} == {'a', 'b'}
