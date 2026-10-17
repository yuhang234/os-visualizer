/**
 * AI 对话 SSE 流式客户端（设计文档 §1.3 / §8.2 / §13.2 第 5 项）。
 *
 * 帧协议（与后端 ai_proxy.py 的 `_sse` 严格对应）：
 *     data: {"type":"meta", ...}
 *     data: {"type":"delta","content":"..."}
 *     data: {"type":"error","code":"...","message":"..."}
 *     data: {"type":"done"}
 *     data: [DONE]
 *
 * 断流保护（§15.2 风险一）：连接/首帧 8 秒看门狗；首帧之后转为 30 秒空闲看门狗，
 * 超时即 AbortController 打断并给出可重试的友好错误。
 */

import { API_PREFIX, buildAuthHeaders } from './client';
import type { ChatStreamPayload, SseFrame } from '../types/ai_engine';

export const CONNECT_WATCHDOG_MS = 8000;
export const IDLE_WATCHDOG_MS = 30000;

export interface ChatStreamHandlers {
  onMeta?: (frame: Extract<SseFrame, { type: 'meta' }>) => void;
  onDelta?: (content: string) => void;
  onError?: (code: string, message: string) => void;
  onDone?: () => void;
}

export class ChatStreamError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'ChatStreamError';
    this.code = code;
  }
}

function parseFrame(block: string): SseFrame | 'DONE' | null {
  const dataLines = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart());
  if (dataLines.length === 0) return null;
  const data = dataLines.join('\n');
  if (data === '[DONE]') return 'DONE';
  try {
    const parsed = JSON.parse(data) as SseFrame;
    if (parsed && typeof parsed === 'object' && 'type' in parsed) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

/** 发起一次流式对话；提供 AbortSignal 以便「停止生成」。 */
export async function streamChat(
  payload: ChatStreamPayload,
  handlers: ChatStreamHandlers,
  externalSignal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController();
  const onExternalAbort = () => controller.abort();
  externalSignal?.addEventListener('abort', onExternalAbort);

  let sawFirstFrame = false;
  let watchdog: ReturnType<typeof setTimeout> | null = null;
  let watchdogFired = false;
  const armWatchdog = () => {
    if (watchdog) clearTimeout(watchdog);
    watchdog = setTimeout(
      () => {
        watchdogFired = true;
        controller.abort();
      },
      sawFirstFrame ? IDLE_WATCHDOG_MS : CONNECT_WATCHDOG_MS,
    );
  };

  try {
    armWatchdog();
    const response = await fetch(`${API_PREFIX}/ai/chat/stream`, {
      method: 'POST',
      headers: buildAuthHeaders(true),
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      let message = `对话请求失败（HTTP ${response.status}）`;
      try {
        const body = (await response.json()) as { detail?: unknown; message?: unknown };
        if (typeof body.detail === 'string') message = body.detail;
        else if (typeof body.message === 'string') message = body.message;
      } catch {
        /* 保留默认信息 */
      }
      throw new ChatStreamError(`HTTP_${response.status}`, message);
    }
    if (!response.body) {
      throw new ChatStreamError('NO_BODY', '服务端未返回流式响应体');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finished = false;

    while (!finished) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let separator = buffer.indexOf('\n\n');
      while (separator >= 0) {
        const block = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        separator = buffer.indexOf('\n\n');
        const frame = parseFrame(block);
        if (!frame) continue;
        if (!sawFirstFrame) {
          sawFirstFrame = true;
        }
        armWatchdog();
        if (frame === 'DONE') {
          finished = true;
          break;
        }
        if (frame.type === 'meta') {
          handlers.onMeta?.(frame);
        } else if (frame.type === 'delta') {
          handlers.onDelta?.(frame.content);
        } else if (frame.type === 'error') {
          handlers.onError?.(frame.code, frame.message);
        } else if (frame.type === 'done') {
          handlers.onDone?.();
        }
      }
    }
    handlers.onDone?.();
  } catch (error) {
    if (controller.signal.aborted && !externalSignal?.aborted) {
      if (watchdogFired) {
        throw new ChatStreamError(
          'TIMEOUT',
          sawFirstFrame ? '生成中断：30 秒未收到新内容，已自动打断。可点击重试。' : '连接超时（8 秒）：上游模型未响应，请检查引擎配置或重试。',
        );
      }
      throw new ChatStreamError('ABORTED', '已停止生成。');
    }
    if (error instanceof ChatStreamError) throw error;
    if (externalSignal?.aborted) {
      throw new ChatStreamError('ABORTED', '已停止生成。');
    }
    throw new ChatStreamError('NETWORK_ERROR', `请求失败：${error instanceof Error ? error.message : String(error)}`);
  } finally {
    if (watchdog) clearTimeout(watchdog);
    externalSignal?.removeEventListener('abort', onExternalAbort);
  }
}
