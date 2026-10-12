from langchain_core.documents import Document
from eval.run_eval import run_generation


def test_agent_eval_uses_fresh_threads_and_actual_tool_evidence(monkeypatch):
    from agent import react_agent
    from rag.rag_service import retrieval_evidence
    threads = []
    class Agent:
        def execute_stream(self, question, thread_id=None):
            threads.append(thread_id)
            retrieval_evidence.get().append(Document(page_content='actual', metadata={'source': 'actual.txt'}))
            yield 'answer'
    class Retriever:
        def invoke(self, question):
            raise AssertionError('Agent evidence must come from its tool invocation')
    class Judge:
        def invoke(self, prompt):
            return '{"score": 1, "reason": "ok"}'
    monkeypatch.setattr(react_agent, 'ReactAgent', Agent)
    items = [{'id': str(i), 'category': 'test', 'question': 'query', 'reference_answer': 'answer'} for i in range(2)]
    result = run_generation(items, Retriever(), 3, Judge(), 'agent')
    assert len(set(threads)) == 2 and all(threads)
    assert all(row['retrieved'] == ['actual.txt'] for row in result['per_item'])
    assert result['answer_correctness'] == 1

