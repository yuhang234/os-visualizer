/**
 * AI 教学助教对话页（设计文档 §8.2）。
 * - 顶部模型切换器：已保存配置 / 12 厂商模板 / 内置演示后端（免密钥）
 * - 预设提示词 chips、附带当前算法快照、Markdown 流式渲染 + 打字机光标
 * - 停止生成（AbortController 打断上游 SSE）与失败重试
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, Eraser, RefreshCw, Send, Settings2, Square, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAiStream } from '../hooks/useAiStream';
import { usePlayback } from '../hooks/usePlayback';
import { fetchEngineCatalog } from '../services/engineApi';
import { errorMessage } from '../services/client';
import { MarkdownBody } from '../components/common/MarkdownBody';
import { Badge } from '../components/common/Badge';
import type { EngineCatalog } from '../types/ai_engine';
import type { ChatContextSnapshot } from '../types/ai_engine';
import type {
  BankerRequestSnapshot,
  BankerSafetySnapshot,
  BankerSafetyTrace,
  PageRepInitialState,
  PageRepSnapshot,
  ThreadsMetrics,
  ThreadsSnapshot,
} from '../types/algorithm';

const PROMPT_CHIPS = [
  '什么是 Belady 异常？为什么 LRU 不会出现？',
  '银行家算法如何判断系统是否处于安全状态？',
  '生产者-消费者问题为什么需要两个信号量？',
  'CLOCK 置换算法的二次机会机制是怎样实现的？',
];

const ATTACH_KEY = 'osvis_chat_attach';

const PAGE_REP_IDS = ['fifo', 'lru', 'opt', 'clock'];

function readAttachPreference(): boolean {
  try {
    return localStorage.getItem(ATTACH_KEY) !== '0';
  } catch {
    return true;
  }
}

/** 把当前回放步骤拼装为后端 `build_system_prompt` 期望的快照结构。 */
function buildContextSnapshot(
  trace: ReturnType<typeof usePlayback>['trace'],
  step: ReturnType<typeof usePlayback>['currentStep'],
): ChatContextSnapshot | undefined {
  if (!trace || !step) return undefined;
  if (PAGE_REP_IDS.includes(trace.algorithmId)) {
    const snapshot = step.snapshot as PageRepSnapshot;
    const initial = trace.initialState as PageRepInitialState;
    return {
      pageReplacement: {
        algorithm: snapshot.algorithm,
        frameCount: snapshot.frameCount,
        frames: snapshot.frames,
        hits: snapshot.hits,
        misses: snapshot.misses,
        missRate: snapshot.missRate,
        referenceString: initial.referenceString,
        currentPage: snapshot.page,
        status: snapshot.status,
        accessedCount: snapshot.accessedCount,
        stepIndex: step.stepIndex + 1,
        totalSteps: trace.totalSteps,
      },
    };
  }
  if (trace.algorithmId === 'banker-safety' || trace.algorithmId === 'banker-request') {
    const state = (trace as BankerSafetyTrace).state;
    const snapshot = step.snapshot as BankerSafetySnapshot | BankerRequestSnapshot;
    const isSafety = 'finish' in snapshot;
    return {
      banker: {
        available: isSafety ? (snapshot as BankerSafetySnapshot).work : (snapshot as BankerRequestSnapshot).available,
        maxMatrix: state.maxMatrix,
        allocationMatrix: state.allocationMatrix,
        needMatrix: state.needMatrix,
        isSafe: isSafety ? (snapshot as BankerSafetySnapshot).isSafe : (snapshot.isSafeAfterTentative ?? null),
        safeSequence: snapshot.safeSequence ?? [],
        phase: snapshot.phase,
        process: snapshot.process,
        stepIndex: step.stepIndex + 1,
        totalSteps: trace.totalSteps,
      },
    };
  }
  const snapshot = step.snapshot as ThreadsSnapshot;
  const metrics = trace.metrics as ThreadsMetrics | undefined;
  return {
    threads: {
      bufferCapacity: metrics?.bufferCapacity,
      bufferCount: snapshot.bufferCount,
      produced: metrics?.produced,
      consumed: metrics?.consumed,
      semaphores: snapshot.semaphores,
      bufferState: snapshot.bufferState,
      waitQueues: snapshot.waitQueues,
      mutexOwner: snapshot.mutexOwner,
      stepIndex: step.stepIndex + 1,
      totalSteps: trace.totalSteps,
    },
  };
}

function snapshotSummary(snapshot: ChatContextSnapshot | undefined): string {
  if (!snapshot) return '当前没有可附带的算法轨迹（请先到算法页生成轨迹）';
  if (snapshot.pageReplacement) {
    const data = snapshot.pageReplacement;
    return `页面置换：${String(data.algorithm)} / ${String(data.frameCount)} 页框 / 命中 ${String(data.hits)} 次 / 缺页 ${String(data.misses)} 次`;
  }
  if (snapshot.banker) {
    const data = snapshot.banker;
    return `银行家算法：Available = [${(data.available as number[] | undefined)?.join(', ') ?? '—'}] / ${String(data.phase)}`;
  }
  return `生产者-消费者：缓冲区 ${String(snapshot.threads?.bufferCount ?? 0)} / ${String(snapshot.threads?.bufferCapacity ?? '?')}，信号量 mutex=${String(snapshot.threads?.semaphores ? (snapshot.threads.semaphores as { mutex: number }).mutex : '?')}`;
}

export function AiChatView() {
  const navigate = useNavigate();
  const { trace, currentStep } = usePlayback();
  const { messages, streaming, error, send, stop, retry, clear } = useAiStream();

  const [catalog, setCatalog] = useState<EngineCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [targetKey, setTargetKey] = useState('auto');
  const [modelOverride, setModelOverride] = useState('');
  const [attach, setAttach] = useState(readAttachPreference);
  const [draft, setDraft] = useState('');
  const [sendError, setSendError] = useState<string | null>(null);
  const messagesRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    fetchEngineCatalog()
      .then((result) => {
        if (!disposed) {
          setCatalog(result);
          setCatalogError(null);
        }
      })
      .catch((thrown) => {
        if (!disposed) setCatalogError(errorMessage(thrown));
      });
    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(ATTACH_KEY, attach ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, [attach]);

  useEffect(() => {
    const element = messagesRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  const contextSnapshot = useMemo(() => (attach ? buildContextSnapshot(trace, currentStep) : undefined), [attach, trace, currentStep]);
  const contextNote = useMemo(() => snapshotSummary(contextSnapshot), [contextSnapshot]);

  const handleSend = useCallback(async () => {
    const text = draft.trim();
    if (!text || streaming) return;
    setSendError(null);
    setDraft('');
    const options =
      targetKey === 'mock'
        ? { providerKey: 'builtin-mock', contextSnapshot, model: modelOverride.trim() || undefined }
        : targetKey.startsWith('saved:')
          ? { providerId: Number(targetKey.slice('saved:'.length)), contextSnapshot }
          : targetKey.startsWith('template:')
            ? { providerKey: targetKey.slice('template:'.length), contextSnapshot, model: modelOverride.trim() || undefined }
            : { contextSnapshot };
    try {
      await send(text, options);
    } catch (thrown) {
      setSendError(errorMessage(thrown));
    }
  }, [contextSnapshot, draft, modelOverride, send, streaming, targetKey]);

  const handleRetry = useCallback(() => {
    setSendError(null);
    void retry().catch((thrown) => setSendError(errorMessage(thrown)));
  }, [retry]);

  const savedConfigs = catalog?.saved ?? [];
  const templates = catalog?.providers ?? [];
  const currentTargetLabel = useMemo(() => {
    if (targetKey === 'mock') return '内置演示后端 (builtin-mock，免密钥)';
    if (targetKey.startsWith('saved:')) {
      const id = Number(targetKey.slice('saved:'.length));
      const found = savedConfigs.find((item) => item.id === id);
      return found ? `${found.displayName || found.providerName} · ${found.model}` : '已保存配置';
    }
    if (targetKey.startsWith('template:')) {
      const key = targetKey.slice('template:'.length);
      const found = templates.find((item) => item.key === key);
      return found ? `${found.name} · ${modelOverride.trim() || found.defaultModel}` : '厂商模板';
    }
    if (!catalog) return '自动选择（加载中…）';
    if (catalog.serverDefaults.hasServerKey) {
      return `自动选择：服务器默认 (${catalog.serverDefaults.provider} / ${catalog.serverDefaults.model})`;
    }
    const active = savedConfigs.find((item) => item.isActive);
    if (active) return `自动选择：默认配置 (${active.providerName} / ${active.model})`;
    return '自动选择：内置演示后端 (builtin-mock)';
  }, [catalog, modelOverride, savedConfigs, targetKey, templates]);

  const isTemplateTarget = targetKey.startsWith('template:');
  const guestLimit = catalog?.guest.dailyChatLimit ?? 20;

  return (
    <div className="chat-layout">
      <aside className="chat-side">
        <div className="card compact">
          <div className="card-title">对话引擎</div>
          <div className="engine-current">
            <div className="name">{currentTargetLabel}</div>
            <div className="mt-8">请求统一经后端代理转发，密钥不会出现在浏览器侧；切换引擎后立即对下一条提问生效。</div>
          </div>
          <select className="input-field full-width mt-12" value={targetKey} onChange={(event) => setTargetKey(event.target.value)}>
            <option value="auto">自动选择（默认配置 / 服务器密钥 / 内置演示）</option>
            <option value="mock">内置演示后端 builtin-mock（免密钥，可离线）</option>
            {savedConfigs.length > 0 ? (
              <optgroup label="已保存的厂商配置">
                {savedConfigs.map((item) => (
                  <option key={item.id} value={`saved:${item.id}`}>
                    {item.displayName || item.providerName} · {item.model}
                    {item.isActive ? '（默认）' : ''}
                  </option>
                ))}
              </optgroup>
            ) : null}
            <optgroup label="厂商模板（需先保存密钥）">
              {templates.map((item) => (
                <option key={item.key} value={`template:${item.key}`}>
                  {item.name} · {item.defaultModel}
                </option>
              ))}
            </optgroup>
          </select>
          {isTemplateTarget ? (
            <label className="field mt-8">
              <span className="field-label">模型标识覆盖（可选）</span>
              <input
                className="input-field input-mono"
                value={modelOverride}
                placeholder="留空则使用模板默认模型"
                onChange={(event) => setModelOverride(event.target.value)}
              />
            </label>
          ) : null}
          <button className="btn btn-secondary btn-sm btn-block mt-12" onClick={() => navigate('/settings/engine')} type="button">
            <Settings2 size={15} /> 打开模型引擎设置
          </button>
        </div>

        <div className="card compact">
          <div className="card-title">算法快照附带</div>
          <label className="row-inline" style={{ cursor: 'pointer', fontSize: 'var(--font-size-sm)' }}>
            <input type="checkbox" checked={attach} onChange={(event) => setAttach(event.target.checked)} />
            附带当前算法快照作为上下文
          </label>
          <div className="help-text mt-8">{contextNote}</div>
        </div>

        <div className="card compact">
          <div className="card-title">额度与隐私</div>
          {catalog?.guest.isGuest ? (
            <>
              <div className="alert alert-info" style={{ fontSize: 'var(--font-size-xs)' }}>
                游客模式：使用「服务器默认密钥」时每日限额 {guestLimit} 次提问。配置自己的厂商密钥或连接本地 Ollama / 内置小模型后不限次数。
              </div>
              <button className="btn btn-primary btn-sm btn-block mt-12" onClick={() => navigate('/login')} type="button">
                登录账号解除限额
              </button>
            </>
          ) : (
            <div className="help-text">已登录账号：使用服务器默认密钥不受游客限额限制；配置自己的密钥时全部请求仅经本地后端代理。</div>
          )}
          <div className="help-text mt-8">API Key 仅保存在后端 SQLite（AES 加密），前端只显示掩码。</div>
        </div>
        {catalogError ? <div className="alert alert-warning">引擎目录加载失败：{catalogError}</div> : null}
      </aside>

      <div className="chat-main">
        <div className="chat-head">
          <Bot size={18} style={{ color: 'var(--color-accent-primary)' }} />
          <strong style={{ fontSize: 'var(--font-size-sm)' }}>OS 教学助教</strong>
          {streaming ? <Badge tone="accent">流式生成中…</Badge> : <Badge tone="muted">就绪</Badge>}
          <span className="spacer" />
          <button className="btn btn-secondary btn-sm" onClick={clear} disabled={messages.length === 0 || streaming} type="button">
            <Eraser size={15} /> 清空对话
          </button>
        </div>

        <div className="chat-messages" ref={messagesRef}>
          {messages.length === 0 ? (
            <div className="msg assistant">
              <div className="msg-avatar">AI</div>
              <div className="msg-bubble">
                <div className="msg-meta">OS 教学助教 · 内置欢迎语</div>
                <p>
                  你好！我是操作系统可视化教学助教。可以问我关于虚拟内存、页面置换、银行家死锁判定或线程同步互斥的核心原理。
                  勾选左侧「附带当前算法快照」，我会结合你界面上的实验数据逐步讲解。
                </p>
              </div>
            </div>
          ) : (
            messages.map((message) => {
              const isAssistant = message.role === 'assistant';
              return (
                <div key={message.id} className={`msg ${isAssistant ? 'assistant' : 'user'}`}>
                  <div className="msg-avatar">{isAssistant ? 'AI' : <User size={15} />}</div>
                  <div className="msg-bubble">
                    {isAssistant ? (
                      <>
                        <div className="msg-meta">
                          {message.providerName ?? message.provider ?? 'OS 教学助教'}
                          {message.model ? ` · ${message.model}` : ''}
                          {message.source ? ` · ${message.source}` : ''}
                        </div>
                        {message.content ? <MarkdownBody content={message.content} /> : null}
                        {streaming && message.id === messages[messages.length - 1]?.id ? <span className="typing-cursor" /> : null}
                        {message.errorText ? (
                          <div className="alert alert-error mt-8" style={{ fontSize: 'var(--font-size-xs)' }}>
                            {message.errorCode ? `[${message.errorCode}] ` : ''}
                            {message.errorText}
                          </div>
                        ) : null}
                      </>
                    ) : (
                      <div style={{ whiteSpace: 'pre-wrap' }}>{message.content}</div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="chat-input-row">
          <div className="chat-hints">
            {PROMPT_CHIPS.map((chip) => (
              <button
                key={chip}
                className="prompt-chip"
                onClick={() => setDraft(chip)}
                disabled={streaming}
                type="button"
              >
                💡 {chip}
              </button>
            ))}
          </div>
          <div className="chat-input-area mt-12">
            <textarea
              className="input-field"
              value={draft}
              placeholder="输入你想探讨的操作系统内核概念，Enter 发送，Shift+Enter 换行……"
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
            />
            {streaming ? (
              <button className="btn btn-secondary" onClick={stop} type="button">
                <Square size={15} /> 停止生成
              </button>
            ) : (
              <>
                <button className="btn btn-secondary" onClick={handleRetry} disabled={messages.length === 0} type="button">
                  <RefreshCw size={15} /> 重试
                </button>
                <button className="btn btn-primary" onClick={() => void handleSend()} disabled={!draft.trim()} type="button">
                  <Send size={15} /> 发送提问
                </button>
              </>
            )}
          </div>
          {error || sendError ? <div className="alert alert-error mt-8">{sendError ?? error}</div> : null}
        </div>
      </div>
    </div>
  );
}
