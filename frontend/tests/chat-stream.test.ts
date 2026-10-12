import { describe, expect, it } from 'vitest';
import { parseSSE } from '../src/api/chat-stream';

async function collect(bytes: Uint8Array[]) {
  const stream = new ReadableStream<Uint8Array>({start(controller) {
    for (const chunk of bytes) controller.enqueue(chunk);
    controller.close();
  }});
  const output = [];
  for await (const event of parseSSE(stream)) output.push(event);
  return output;
}

describe('POST SSE parser', () => {
  it('preserves Chinese characters and events across arbitrary byte boundaries', async () => {
    const bytes = new TextEncoder().encode('event: token\r\ndata: {"content":"你好"}\r\n\r\nevent: done\ndata: {"run_id":"r","status":"completed"}\n\n');
    const parts = Array.from(bytes, byte => new Uint8Array([byte]));
    expect(await collect(parts)).toEqual([
      {type: 'token', content: '你好'}, {type: 'done', run_id: 'r', status: 'completed'},
    ]);
  });
  it('rejects truncated final events rather than reporting success', async () => {
    await expect(collect([new TextEncoder().encode('event: token\ndata: {"content":')])).rejects.toThrow();
  });
  it('ignores heartbeat comments and accepts multi-line JSON data', async () => {
    expect(await collect([new TextEncoder().encode(': ping\n\nevent: token\ndata: {\ndata: "content":"ok"}\n\n')])).toEqual([{type: 'token', content: 'ok'}]);
  });
});
