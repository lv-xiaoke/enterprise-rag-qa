import type {ChatEvent} from '../types/api';

export async function* parseSSE(stream: ReadableStream<Uint8Array>): AsyncGenerator<ChatEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const {done, value} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      // Normalize only after receiving a full CRLF, including a split CR/LF pair.
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let type = '';
        const data: string[] = [];
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) type = line.slice(6).trim();
          if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
        }
        if (type && data.length) yield {...JSON.parse(data.join('\n')), type} as ChatEvent;
      }
      if (done) break;
    }
    if (buffer.trim() && !buffer.trim().startsWith(':')) throw new Error('响应流不完整，请查看历史后重试');
  } finally { reader.releaseLock(); }
}
