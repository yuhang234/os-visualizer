import { useCallback, useEffect, useMemo, useState } from 'react';
import { Play, RefreshCw } from 'lucide-react';
import { simulateThreads } from '../services/algorithmApi';
import { errorMessage } from '../services/client';
import { usePlayback } from '../hooks/usePlayback';
import { Badge, type BadgeTone } from '../components/common/Badge';
import { LogConsole } from '../components/visualizer/LogConsole';
import type { ThreadInfo, ThreadLifecycle, ThreadsMetrics, ThreadsSnapshot, ThreadsTrace } from '../types/algorithm';

const PRESETS = [
  { label: '2 生产者 / 2 消费者 / 缓冲 5', bufferCapacity: 5, producerCount: 2, consumerCount: 2, totalOperations: 20 },
  { label: '1 生产者 / 1 消费者 / 缓冲 3', bufferCapacity: 3, producerCount: 1, consumerCount: 1, totalOperations: 12 },
  { label: '3 生产者 / 2 消费者 / 缓冲 4（高争抢）', bufferCapacity: 4, producerCount: 3, consumerCount: 2, totalOperations: 24 },
];

const STATE_LABEL: Record<ThreadLifecycle, { text: string; tone: BadgeTone; cls: string }> = {
  NEW: { text: 'NEW 新建', tone: 'muted', cls: 'thread-state-new' },
  RUNNING: { text: '🟢 RUNNING 正在运行', tone: 'success', cls: 'thread-state-running' },
  BLOCKED: { text: '🟡 BLOCKED 阻塞等待', tone: 'warning', cls: 'thread-state-blocked' },
  SLEEP: { text: '🔵 SLEEP 休眠就绪', tone: 'info', cls: 'thread-state-sleep' },
  DONE: { text: '⚪ DONE 已完成', tone: 'muted', cls: 'thread-state-done' },
};

const INSERT_ACTIONS = new Set(['P_EMPTY', 'BLOCK_EMPTY', 'P_MUTEX', 'BLOCK_MUTEX', 'INSERT', 'V_MUTEX', 'V_FULL']);
const REMOVE_ACTIONS = new Set(['P_FULL', 'BLOCK_FULL', 'REMOVE', 'V_EMPTY', 'CONSUME']);

function threadCard(thread: ThreadInfo, activeId: string | null) {
  const label = STATE_LABEL[thread.state];
  const isActive = activeId === thread.id;
  return (
    <div className={`thread-card ${thread.state.toLowerCase()}${isActive ? ' running' : ''}`} key={thread.id}>
      <div className="thread-head">
        <span className="thread-id">{thread.id}</span>
        <span className={`thread-state-badge ${label.cls}`}>{label.text}</span>
        <span className="spacer" />
        <span className="mono-xs muted">
          {thread.opsDone}/{thread.opsQuota} 次
        </span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${Math.round(thread.progress * 100)}%` }} />
      </div>
      <div className="thread-meta">
        <span>进度 {(thread.progress * 100).toFixed(0)}%</span>
        {thread.type === 'PRODUCER' ? <span>已生产 {thread.produced}</span> : <span>已消费 {thread.consumed}</span>}
        <span>阻塞 {thread.waitEvents} 次</span>
        <span>唤醒 {thread.wakeEvents} 次</span>
        {thread.blockedOn ? <span style={{ color: 'var(--color-warning)' }}>blockedOn: {thread.blockedOn}</span> : null}
      </div>
      <div className="thread-action">执行代码: {thread.lastAction}</div>
    </div>
  );
}

export function ThreadsView() {
  const { trace, currentStep, index, totalSteps, loadTrace } = usePlayback();

  const [bufferCapacity, setBufferCapacity] = useState(5);
  const [producerCount, setProducerCount] = useState(2);
  const [consumerCount, setConsumerCount] = useState(2);
  const [totalOperations, setTotalOperations] = useState(20);
  const [productionTime, setProductionTime] = useState(1.5);
  const [consumptionTime, setConsumptionTime] = useState(2.0);
  const [criticalTime, setCriticalTime] = useState(0.35);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isThreadsTrace = trace?.algorithmId === 'threads-pc';

  const snapshot = useMemo<ThreadsSnapshot | null>(() => {
    if (!trace || !currentStep || !isThreadsTrace) return null;
    return currentStep.snapshot as ThreadsSnapshot;
  }, [trace, currentStep, isThreadsTrace]);

  const metrics = useMemo<ThreadsMetrics | undefined>(
    () => (isThreadsTrace ? (trace.metrics as ThreadsMetrics | undefined) : undefined),
    [trace, isThreadsTrace],
  );
  const invariants = useMemo(() => (isThreadsTrace ? (trace as ThreadsTrace).invariants : undefined), [trace, isThreadsTrace]);

  const run = useCallback(
    async (params: {
      bufferCapacity: number;
      producerCount: number;
      consumerCount: number;
      totalOperations: number;
      productionTime: number;
      consumptionTime: number;
      criticalTime: number;
    }) => {
      setBusy(true);
      setError(null);
      try {
        const result = await simulateThreads({ ...params, seed: 20261017 });
        loadTrace(result);
      } catch (thrown) {
        setError(errorMessage(thrown));
      } finally {
        setBusy(false);
      }
    },
    [loadTrace],
  );

  useEffect(() => {
    if (isThreadsTrace) return;
    void run({
      bufferCapacity: 5,
      producerCount: 2,
      consumerCount: 2,
      totalOperations: 20,
      productionTime: 1.5,
      consumptionTime: 2.0,
      criticalTime: 0.35,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const producers = snapshot?.threads.filter((thread) => thread.type === 'PRODUCER') ?? [];
  const consumers = snapshot?.threads.filter((thread) => thread.type === 'CONSUMER') ?? [];
  const capacity = snapshot ? Math.max(snapshot.bufferState.length, 1) : bufferCapacity;

  const highlightedSlot = (() => {
    if (!snapshot) return -1;
    if (INSERT_ACTIONS.has(snapshot.action)) {
      return snapshot.action === 'INSERT' ? (snapshot.inPointer - 1 + capacity) % capacity : snapshot.inPointer;
    }
    if (REMOVE_ACTIONS.has(snapshot.action)) {
      return snapshot.action === 'REMOVE' ? (snapshot.outPointer - 1 + capacity) % capacity : snapshot.outPointer;
    }
    return -1;
  })();

  const activeProducer = snapshot?.activeThreadType === 'PRODUCER';
  const activeLine = snapshot?.activeLine ?? null;
  const producerCode = producers[0]?.code ?? [];
  const consumerCode = consumers[0]?.code ?? [];

  const renderCode = (code: string[], active: boolean, title: string, threadId: string | null) => (
    <div className="code-block">
      <div className="code-block-title">
        {title}
        {active && threadId ? ` · 当前执行线程 ${threadId}` : ''}
      </div>
      {code.map((line, lineIndex) => (
        <div className={`code-line${active && activeLine === lineIndex + 1 ? ' active' : ''}`} key={lineIndex}>
          <span className="line-no">{lineIndex + 1}</span>
          <span>{line}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div>
      <div className="page-head">
        <span className="page-title">多线程同步互斥演示 —— 生产者/消费者模型</span>
        <div className="page-actions">
          <select
            className="input-field input-inline"
            defaultValue=""
            onChange={(event) => {
              const preset = PRESETS.find((item) => item.label === event.target.value);
              if (!preset) return;
              setBufferCapacity(preset.bufferCapacity);
              setProducerCount(preset.producerCount);
              setConsumerCount(preset.consumerCount);
              setTotalOperations(preset.totalOperations);
              void run({ ...preset, productionTime, consumptionTime, criticalTime });
            }}
            title="预设配置"
          >
            <option value="">预设: 2生产 2消费 缓冲=5 ▼</option>
            {PRESETS.map((preset) => (
              <option key={preset.label} value={preset.label}>
                {preset.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="config-card">
        <div className="config-row">
          <span className="config-label">缓冲区容量:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={1}
            max={10}
            value={bufferCapacity}
            style={{ width: 70 }}
            onChange={(event) => setBufferCapacity(Math.max(1, Math.min(10, Number(event.target.value) || 1)))}
          />
          <span className="config-label">生产速率 (s/个):</span>
          <input
            className="input-field input-inline"
            type="number"
            min={0.1}
            max={30}
            step={0.1}
            value={productionTime}
            style={{ width: 84 }}
            onChange={(event) => setProductionTime(Math.max(0.1, Number(event.target.value) || 1.5))}
          />
          <span className="config-label">消费速率 (s/个):</span>
          <input
            className="input-field input-inline"
            type="number"
            min={0.1}
            max={30}
            step={0.1}
            value={consumptionTime}
            style={{ width: 84 }}
            onChange={(event) => setConsumptionTime(Math.max(0.1, Number(event.target.value) || 2))}
          />
        </div>
        <div className="config-row">
          <span className="config-label">生产者数:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={1}
            max={4}
            value={producerCount}
            style={{ width: 70 }}
            onChange={(event) => setProducerCount(Math.max(1, Math.min(4, Number(event.target.value) || 1)))}
          />
          <span className="config-label">消费者数:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={1}
            max={4}
            value={consumerCount}
            style={{ width: 70 }}
            onChange={(event) => setConsumerCount(Math.max(1, Math.min(4, Number(event.target.value) || 1)))}
          />
          <span className="config-label">总产品数:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={1}
            max={60}
            value={totalOperations}
            style={{ width: 70 }}
            onChange={(event) => setTotalOperations(Math.max(1, Math.min(60, Number(event.target.value) || 1)))}
          />
          <span className="config-label" title="临界区写/取之后的持锁时间：>0 时其他线程可在该窗口内观察到 P(mutex) 阻塞">
            临界区时长 (s):
          </span>
          <input
            className="input-field input-inline"
            type="number"
            min={0}
            max={10}
            step={0.05}
            value={criticalTime}
            style={{ width: 84 }}
            onChange={(event) => setCriticalTime(Math.max(0, Math.min(10, Number(event.target.value) || 0)))}
          />
          <span className="spacer" />
          <button
            className="btn btn-primary btn-sm"
            disabled={busy}
            onClick={() =>
              void run({
                bufferCapacity,
                producerCount,
                consumerCount,
                totalOperations,
                productionTime,
                consumptionTime,
                criticalTime,
              })
            }
            type="button"
          >
            {busy ? <span className="spinner" /> : <Play size={15} />} 开始模拟
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() =>
              void run({
                bufferCapacity: 5,
                producerCount: 2,
                consumerCount: 2,
                totalOperations: 20,
                productionTime: 1.5,
                consumptionTime: 2.0,
                criticalTime: 0.35,
              })
            }
            type="button"
          >
            <RefreshCw size={15} /> 重置为默认案例
          </button>
        </div>
        {error ? <div className="alert alert-error mt-8">{error}</div> : null}
      </div>

      <div className="viz-grid">
        <div className="viz-main card">
          <div className="flex-between mb-12">
            <div className="card-title mb-0">共享缓冲区 (Bounded Buffer) 实时状态</div>
            <span className="mono-sm secondary-text">
              步骤 {totalSteps === 0 ? 0 : index + 1} / {totalSteps} · 虚拟时间 {(snapshot?.time ?? 0).toFixed(2)}s
            </span>
          </div>

          <div className="buffer-meta mb-12">
            <span>
              容量: <strong className="mono-sm">{capacity}</strong>
            </span>
            <span>
              当前产品数: <strong className="mono-sm">{snapshot?.bufferCount ?? 0}</strong> / {capacity}
            </span>
            <span>
              状态:{' '}
              {snapshot == null
                ? '等待模拟'
                : snapshot.bufferCount === 0
                  ? '缓冲区为空'
                  : snapshot.bufferCount >= capacity
                    ? '缓冲区已满'
                    : '正常流转'}
            </span>
            <span>
              当前动作: <strong className="mono-sm" style={{ color: 'var(--color-accent-primary)' }}>{snapshot?.action ?? '—'}</strong>
            </span>
          </div>

          <div className="buffer-row">
            {(snapshot?.bufferState ?? Array.from({ length: bufferCapacity }, () => null)).map((item, slotIndex) => {
              const active = slotIndex === highlightedSlot;
              return (
                <div className={`buffer-slot${item == null ? '' : ' filled'}${active ? ' active' : ''}`} key={slotIndex}>
                  {snapshot && snapshot.inPointer === slotIndex ? <span className="slot-tag">▼ 下一写入位</span> : null}
                  {snapshot && snapshot.outPointer === slotIndex ? <span className="slot-tag bottom">▲ 下一读出位</span> : null}
                  <span className="muted">槽位 {slotIndex}</span>
                  <span className="slot-item">{item == null ? '(空)' : `#${item}`}</span>
                </div>
              );
            })}
          </div>

          <div className="mt-16">
            <div className="card-title" style={{ fontSize: 'var(--font-size-sm)' }}>
              伪代码执行高亮联动面板 (Pseudo-code Context)
            </div>
            <div className="code-panel">
              {renderCode(
                producerCode,
                activeProducer,
                '生产者 Producer 代码',
                activeProducer ? (snapshot?.activeThreadId ?? null) : null,
              )}
              {renderCode(
                consumerCode,
                activeProducer === false && snapshot?.activeThreadType === 'CONSUMER',
                '消费者 Consumer 代码',
                snapshot?.activeThreadType === 'CONSUMER' ? (snapshot?.activeThreadId ?? null) : null,
              )}
            </div>
          </div>
        </div>

        <div className="viz-side">
          <div className="card">
            <div className="card-title">同步原语与锁状态 (Primitives)</div>
            <div className="sem-cards">
              <div className="sem-card">
                <div className="sem-head">
                  <span className="sem-name">互斥锁 Mutex</span>
                  {snapshot && snapshot.semaphores.mutex === 1 ? (
                    <Badge tone="success">🟢 自由空闲</Badge>
                  ) : (
                    <Badge tone="warning">🔴 已被占用</Badge>
                  )}
                </div>
                <div className="sem-value">
                  Value: {snapshot?.semaphores.mutex ?? 1}
                  {snapshot?.mutexOwner ? <span className="muted" style={{ fontSize: 'var(--font-size-xs)' }}> · owner {snapshot.mutexOwner}</span> : null}
                </div>
                <div className="sem-waiters">
                  {snapshot && snapshot.waitQueues.mutex.length > 0
                    ? `争抢等待队列: ${snapshot.waitQueues.mutex.join(', ')}`
                    : '无等待者'}
                </div>
              </div>

              <div className="sem-card">
                <div className="sem-head">
                  <span className="sem-name">空位信号量 Empty</span>
                  <span className="sem-value" style={{ color: 'var(--color-accent-primary)' }}>
                    {snapshot?.semaphores.empty ?? bufferCapacity}
                  </span>
                </div>
                <div className="sem-track">
                  <div
                    className="sem-fill"
                    style={{
                      width: `${((snapshot?.semaphores.empty ?? bufferCapacity) / capacity) * 100}%`,
                      background: 'var(--color-accent-primary)',
                    }}
                  />
                </div>
                <div className="sem-waiters">
                  {snapshot && snapshot.waitQueues.empty.length > 0
                    ? `阻塞等待唤醒: ${snapshot.waitQueues.empty.join(', ')}`
                    : '剩余空槽位充足'}
                </div>
              </div>

              <div className="sem-card">
                <div className="sem-head">
                  <span className="sem-name">产品信号量 Full</span>
                  <span className="sem-value" style={{ color: 'var(--color-success)' }}>
                    {snapshot?.semaphores.full ?? 0}
                  </span>
                </div>
                <div className="sem-track">
                  <div
                    className="sem-fill"
                    style={{
                      width: `${((snapshot?.semaphores.full ?? 0) / capacity) * 100}%`,
                      background: 'var(--color-success)',
                    }}
                  />
                </div>
                <div className="sem-waiters">
                  {snapshot && snapshot.waitQueues.full.length > 0
                    ? `阻塞等待唤醒: ${snapshot.waitQueues.full.join(', ')}`
                    : '暂无等待产品的消费者'}
                </div>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title">运行统计</div>
            <div className="metrics-strip" style={{ marginTop: 0 }}>
              <div className="metric-chip">
                <div className="label">累计生产</div>
                <div className="value">{snapshot?.counters.produced ?? 0}</div>
              </div>
              <div className="metric-chip">
                <div className="label">累计消费</div>
                <div className="value">{snapshot?.counters.consumed ?? 0}</div>
              </div>
              <div className="metric-chip">
                <div className="label">阻塞事件</div>
                <div className="value">{snapshot?.counters.blockEvents ?? 0}</div>
              </div>
              <div className="metric-chip">
                <div className="label">互斥锁争抢</div>
                <div className="value" style={{ color: 'var(--color-warning)' }}>
                  {snapshot?.counters.mutexBlockEvents ?? 0}
                </div>
              </div>
              <div className="metric-chip">
                <div className="label">唤醒事件</div>
                <div className="value">{snapshot?.counters.wakeEvents ?? 0}</div>
              </div>
              <div className="metric-chip">
                <div className="label">上下文切换</div>
                <div className="value">{snapshot?.counters.contextSwitches ?? 0}</div>
              </div>
            </div>
            {metrics ? (
              <div className="help-text mt-12">
                模拟结束统计：生产 {metrics.produced} / 消费 {metrics.consumed}，缓冲区残留 {metrics.bufferRemaining}，
                虚拟时长 {(metrics.virtualDuration ?? 0).toFixed(2)}s
                {metrics.truncated ? '（已达最大步数，轨迹截断）' : ''}
              </div>
            ) : null}
            {invariants ? (
              <div className="mt-12">
                <span className="config-label">不变量校验:</span>
                <div className="row-inline mt-8">
                  {Object.entries(invariants).map(([key, value]) => (
                    <Badge key={key} tone={value ? 'success' : 'danger'}>
                      {value ? '✅' : '❌'} {key}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="card mt-16">
        <div className="card-title">线程工作台与运行状态监控 (Thread Lifecycle &amp; Callstack)</div>
        <div className="config-label mb-12">生产者线程池 (Producers)</div>
        <div className="thread-pool">
          {producers.length === 0 ? <div className="empty-state">等待模拟生成线程……</div> : producers.map((thread) => threadCard(thread, snapshot?.activeThreadId ?? null))}
        </div>
        <div className="config-label mb-12 mt-16">消费者线程池 (Consumers)</div>
        <div className="thread-pool">
          {consumers.length === 0 ? <div className="empty-state">等待模拟生成线程……</div> : consumers.map((thread) => threadCard(thread, snapshot?.activeThreadId ?? null))}
        </div>
      </div>

      <LogConsole steps={trace?.steps ?? []} currentIndex={index} />
    </div>
  );
}
