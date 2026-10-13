import asyncio
from typing import Any
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langgraph.checkpoint.memory import MemorySaver
from test_agent_stream import RecordingModel
from test_agent_clarification import decision


def test_validated_final_answer_streams_before_generation_finishes():
    from agent.business_agent import BusinessAgent
    class StreamingReplyModel(RecordingModel):
        finished: bool = False
        release: Any = None
        async def _astream(self,messages,stop=None,run_manager=None,**kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content='第一段'))
            await self.release.wait()
            self.finished = True
            yield ChatGenerationChunk(message=AIMessageChunk(content='第二段'))
    model = StreamingReplyModel(script=[decision('chat')])
    async def run():
        model.release = asyncio.Event()
        observed = []
        async with asyncio.timeout(2):
            async for event in BusinessAgent(model=model,checkpointer=MemorySaver()).astream_events('你好','stream'):
                if event['type']=='token':
                    observed.append(event['content'])
                    if len(observed)==1:
                        assert not model.finished
                        model.release.set()
        return observed
    assert asyncio.run(run())==['第一段','第二段']
