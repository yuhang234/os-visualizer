/**
 * AI 对话流式状态 Hook（设计文档 §8.2）。
 * - 打字机增量写入最后一条 assistant 消息
 * - 停止生成 = AbortController 打断上游 SSE
 * - 出错保留原文并给出重试入口
 */

import { useCallback, useRef, useState } from 'react';
import { streamChat, ChatStreamError } from '../services/chatApi';
import type { ChatContextSnapshot } from '../types/ai_engine';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: number;
  provider?: string;
  providerName?: string;
  model?: string;
  source?: string;
  errorCode?: string;
  errorText?: string;
}

export interface SendOptions {
  contextSnapshot?: ChatContextSnapshot;
  providerId?: number;
  providerKey?: string;
  model?: string;
}

let messageSeq = 0;
function nextId(prefix: string): string {
  messageSeq += 1;
  return `${prefix}-${Date.now()}-${messageSeq}`;
}

export function useAiStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastRequestRef = useRef<{ text: string; options: SendOptions } | null>(null);

  const patchMessage = useCallback((id: string, patch: Partial<ChatMessage> | ((current: ChatMessage) => Partial<ChatMessage>)) => {
    setMessages((current) =>
      current.map((message) => (message.id === id ? { ...message, ...(typeof patch === 'function' ? patch(message) : patch) } : message)),
    );
  }, []);

  const run = useCallback(
    async (text: string, options: SendOptions, history: ChatMessage[]) => {
      const userMessage: ChatMessage = { id: nextId('u'), role: 'user', content: text, createdAt: Date.now() };
      const assistantMessage: ChatMessage = { id: nextId('a'), role: 'assistant', content: '', createdAt: Date.now() };
      setMessages([...history, userMessage, assistantMessage]);
      setStreaming(true);
      setError(null);

      const controller = new AbortController();
      abortRef.current = controller;
      const payloadMessages = [...history, userMessage].map((message) => ({
        role: message.role,
        content: message.content,
      }));

      try {
        await streamChat(
          {
            messages: payloadMessages,
            contextSnapshot: options.contextSnapshot,
            providerId: options.providerId,
            providerKey: options.providerKey,
            model: options.model,
          },
          {
            onMeta: (frame) => {
              patchMessage(assistantMessage.id, {
                provider: frame.provider,
                providerName: frame.providerName,
                model: frame.model,
                source: frame.source,
              });
            },
            onDelta: (content) => {
              patchMessage(assistantMessage.id, (current) => ({ content: current.content + content }));
            },
            onError: (code, message) => {
              patchMessage(assistantMessage.id, { errorCode: code, errorText: message });
              setError(message);
            },
          },
          controller.signal,
        );
      } catch (thrown) {
        const friendly =
          thrown instanceof ChatStreamError
            ? thrown.message
            : thrown instanceof Error
              ? thrown.message
              : String(thrown);
        const aborted = thrown instanceof ChatStreamError && thrown.code === 'ABORTED';
        if (!aborted) {
          setError(friendly);
          patchMessage(assistantMessage.id, { errorText: friendly, errorCode: 'CLIENT_ERROR' });
        }
        patchMessage(assistantMessage.id, (current) => {
          if (current.content) return { errorText: current.errorText, errorCode: current.errorCode };
          return { content: aborted ? '（已停止生成）' : '（未收到任何回复内容）', errorText: current.errorText };
        });
      } finally {
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [patchMessage],
  );

  const send = useCallback(
    async (text: string, options: SendOptions = {}) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;
      lastRequestRef.current = { text: trimmed, options };
      await run(trimmed, options, messages);
    },
    [messages, run, streaming],
  );

  /** 重试：重新发送最后一条用户消息（去掉此前的失败回复）。 */
  const retry = useCallback(async () => {
    if (streaming) return;
    const last = lastRequestRef.current;
    if (!last) return;
    let history = messages;
    while (history.length > 0 && history[history.length - 1].role === 'assistant') {
      history = history.slice(0, -1);
    }
    if (history.length > 0) {
      history = history.slice(0, -1);
    }
    await run(last.text, last.options, history);
  }, [messages, run, streaming]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const clear = useCallback(() => {
    abortRef.current?.abort();
    lastRequestRef.current = null;
    setMessages([]);
    setError(null);
  }, []);

  return { messages, streaming, error, send, stop, retry, clear, setError };
}
