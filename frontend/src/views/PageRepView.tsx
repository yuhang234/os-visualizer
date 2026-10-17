import { useCallback, useEffect, useMemo, useState } from 'react';
import { Dices, RefreshCw, Zap } from 'lucide-react';
import { simulatePageReplacement } from '../services/algorithmApi';
import { errorMessage } from '../services/client';
import { usePlayback } from '../hooks/usePlayback';
import { AccessBanner } from '../components/visualizer/AccessBanner';
import { ClockDial } from '../components/visualizer/ClockDial';
import { FrameSlots } from '../components/visualizer/FrameSlots';
import { LogConsole } from '../components/visualizer/LogConsole';
import { MetricRing } from '../components/visualizer/MetricRing';
import { Badge } from '../components/common/Badge';
import type { PageAlgorithm, PageRepInitialState, PageRepSnapshot, PageRepTrace } from '../types/algorithm';

const ALGORITHMS: { value: PageAlgorithm; label: string; hint: string }[] = [
  { value: 'FIFO', label: 'FIFO', hint: '先进先出：淘汰最早进入内存的页面' },
  { value: 'LRU', label: 'LRU', hint: '最近最久未使用：淘汰最长时间未被访问的页面' },
  { value: 'OPT', label: 'OPT', hint: '最佳置换：淘汰未来最长时间不再被访问的页面' },
  { value: 'CLOCK', label: 'CLOCK', hint: '时钟算法：环形扫描访问位，给予二次机会' },
];

const PRESETS: { label: string; algorithm: PageAlgorithm; frameCount: number; referenceString: number[] }[] = [
  {
    label: '教材标准串',
    algorithm: 'FIFO',
    frameCount: 3,
    referenceString: [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1],
  },
  {
    label: '经典 Belady 异常例题',
    algorithm: 'FIFO',
    frameCount: 3,
    referenceString: [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5],
  },
  {
    label: '高频局部性访问',
    algorithm: 'LRU',
    frameCount: 4,
    referenceString: [0, 1, 2, 0, 1, 3, 0, 1, 2, 0, 1, 2, 3, 0, 1, 2],
  },
];

const PAGE_REP_IDS = ['fifo', 'lru', 'opt', 'clock'];

function parseReference(text: string): { pages?: number[]; error?: string } {
  const parts = text
    .split(/[,，\s]+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (parts.length === 0) {
    return { error: '参考串不能为空' };
  }
  const pages: number[] = [];
  for (const part of parts) {
    if (!/^\d+$/.test(part)) {
      return { error: `参考串中存在非法元素: ${part}` };
    }
    const value = Number(part);
    if (value < 0 || value > 99) {
      return { error: `页面号必须在 0~99 之间，收到 ${value}` };
    }
    pages.push(value);
  }
  if (pages.length > 200) {
    return { error: '参考串长度不能超过 200' };
  }
  return { pages };
}

export function PageRepView() {
  const { trace, currentStep, totalSteps, index, loadTrace, status } = usePlayback();
  const [algorithm, setAlgorithm] = useState<PageAlgorithm>('FIFO');
  const [frameCount, setFrameCount] = useState(3);
  const [referenceText, setReferenceText] = useState(PRESETS[0].referenceString.join(', '));
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const snapshot = useMemo<PageRepSnapshot | null>(() => {
    if (!trace || !currentStep || !PAGE_REP_IDS.includes(trace.algorithmId)) return null;
    return currentStep.snapshot as PageRepSnapshot;
  }, [trace, currentStep]);

  const initialState = useMemo<PageRepInitialState | null>(() => {
    if (!trace || !PAGE_REP_IDS.includes(trace.algorithmId)) return null;
    return trace.initialState as PageRepInitialState;
  }, [trace]);

  const generate = useCallback(
    async (params: { algorithm: PageAlgorithm; frameCount: number; referenceString: number[] }) => {
      setLoading(true);
      setError(null);
      try {
        const result: PageRepTrace = await simulatePageReplacement(params);
        loadTrace(result);
      } catch (thrown) {
        setError(errorMessage(thrown));
      } finally {
        setLoading(false);
      }
    },
    [loadTrace],
  );

  // 首次进入：若有同族轨迹则回填表单，否则用默认案例自动生成
  useEffect(() => {
    if (initialState) {
      setAlgorithm(initialState.algorithm);
      setFrameCount(initialState.frameCount);
      setReferenceText(initialState.referenceString.join(', '));
      return;
    }
    void generate({
      algorithm: PRESETS[0].algorithm,
      frameCount: PRESETS[0].frameCount,
      referenceString: PRESETS[0].referenceString,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const applyPreset = (label: string) => {
    const preset = PRESETS.find((item) => item.label === label);
    if (!preset) return;
    setAlgorithm(preset.algorithm);
    setFrameCount(preset.frameCount);
    setReferenceText(preset.referenceString.join(', '));
    void generate(preset);
  };

  const randomize = () => {
    const length = 12 + Math.floor(Math.random() * 9);
    const pages = Array.from({ length }, () => Math.floor(Math.random() * 8));
    setReferenceText(pages.join(', '));
    setError(null);
  };

  const handleExecute = () => {
    const parsed = parseReference(referenceText);
    if (parsed.error) {
      setError(parsed.error);
      return;
    }
    void generate({ algorithm, frameCount, referenceString: parsed.pages ?? [] });
  };

  const handleReset = () => {
    const preset = PRESETS[0];
    setAlgorithm(preset.algorithm);
    setFrameCount(preset.frameCount);
    setReferenceText(preset.referenceString.join(', '));
    setError(null);
    void generate(preset);
  };

  const currentAlgorithm = snapshot?.algorithm ?? algorithm;
  const principle = currentStep && snapshot ? currentStep.description : '点击「生成轨迹并播放」，即可查看逐步置换过程。';
  const missRatePercent = snapshot ? snapshot.missRate * 100 : 0;
  const riskText =
    snapshot == null
      ? '等待数据'
      : snapshot.totalAccess === 0
        ? '尚未访问'
        : missRatePercent >= 60
          ? '缺页风险较高'
          : missRatePercent >= 30
            ? '缺页率中等'
            : '缺页率健康';

  return (
    <div>
      <div className="page-head">
        <span className="page-title">页面置换算法可视化</span>
        <div className="page-actions">
          <select
            className="input-field input-inline"
            defaultValue=""
            onChange={(event) => {
              if (event.target.value) applyPreset(event.target.value);
            }}
            title="预设案例"
          >
            <option value="">预设案例：经典Belady异常 ▼</option>
            {PRESETS.map((preset) => (
              <option key={preset.label} value={preset.label}>
                {preset.label}
              </option>
            ))}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={randomize} type="button">
            <Dices size={15} /> 随机生成参考串
          </button>
        </div>
      </div>

      <div className="config-card">
        <div className="config-row">
          <span className="config-label">算法选择:</span>
          <div className="radio-group">
            {ALGORITHMS.map((item) => (
              <label key={item.value} className={`radio-pill${algorithm === item.value ? ' selected' : ''}`} title={item.hint}>
                <input
                  type="radio"
                  name="page-algorithm"
                  checked={algorithm === item.value}
                  onChange={() => setAlgorithm(item.value)}
                />
                {item.label}
              </label>
            ))}
          </div>
        </div>
        <div className="config-row">
          <span className="config-label">页面参考串:</span>
          <input
            className="input-field input-mono"
            style={{ flex: 1, minWidth: 260 }}
            value={referenceText}
            onChange={(event) => setReferenceText(event.target.value)}
            placeholder="例如：7, 0, 1, 2, 0, 3"
          />
        </div>
        <div className="config-row">
          <span className="config-label">物理页框数:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={2}
            max={7}
            value={frameCount}
            style={{ width: 76 }}
            onChange={(event) => {
              const value = Number(event.target.value);
              setFrameCount(Math.max(2, Math.min(7, Number.isFinite(value) ? value : 3)));
            }}
          />
          <span className="help-text">范围 2~7</span>
          <span className="spacer" />
          <button className="btn btn-primary btn-sm" onClick={handleExecute} disabled={loading} type="button">
            {loading ? <span className="spinner" /> : <Zap size={15} />}
            {loading ? '计算中…' : '生成轨迹并播放'}
          </button>
          <button className="btn btn-secondary btn-sm" onClick={handleReset} type="button">
            <RefreshCw size={15} /> 重置数据
          </button>
        </div>
        {error ? <div className="alert alert-error mt-8">{error}</div> : null}
      </div>

      <div className="viz-grid">
        <div className="viz-main card">
          <div className="flex-between mb-12">
            <div className="row-inline">
              <span className="mono-sm secondary-text">
                步骤 {totalSteps === 0 ? 0 : index + 1} / {totalSteps}
              </span>
              <span className="muted">|</span>
              <span className="secondary-text">
                当前访问: 页面 <strong className="mono-sm" style={{ color: 'var(--color-accent-primary)' }}>{snapshot?.page ?? '—'}</strong>
              </span>
            </div>
            {snapshot ? (
              snapshot.status === 'HIT' ? (
                <Badge tone="success">✅ 命中 (Page Hit)</Badge>
              ) : snapshot.status === 'MISS' ? (
                <Badge tone="danger">❌ 发生缺页 (Page Fault)</Badge>
              ) : (
                <Badge tone="muted">待机</Badge>
              )
            ) : (
              <Badge tone="muted">{status === 'LOADING' || loading ? '计算中…' : '未生成轨迹'}</Badge>
            )}
          </div>

          <div className="card-title mb-0" style={{ fontSize: 'var(--font-size-sm)' }}>
            时序参考串
          </div>
          {initialState ? (
            <AccessBanner
              referenceString={initialState.referenceString}
              accessedCount={snapshot?.accessedCount ?? 0}
            />
          ) : (
            <div className="empty-state">暂无参考串</div>
          )}

          <div className="card-title mb-0 mt-16" style={{ fontSize: 'var(--font-size-sm)' }}>
            物理页框状态
            {currentAlgorithm === 'CLOCK' ? <span className="muted">（环形表盘 + 指针）</span> : null}
          </div>
          {snapshot ? (
            <>
              {currentAlgorithm === 'CLOCK' ? <ClockDial snapshot={snapshot} /> : null}
              <FrameSlots snapshot={snapshot} />
            </>
          ) : (
            <div className="empty-state">等待生成执行轨迹……</div>
          )}
        </div>

        <div className="viz-side">
          <div className="card">
            <div className="card-title">实时统计与指标看板</div>
            <div className="stats-grid">
              <div className="stat-cell">
                <div className="stat-label">访问总数</div>
                <div className="stat-value accent">{snapshot?.totalAccess ?? 0}</div>
              </div>
              <div className="stat-cell">
                <div className="stat-label">缺页次数</div>
                <div className="stat-value miss">{snapshot?.misses ?? 0}</div>
              </div>
              <div className="stat-cell">
                <div className="stat-label">命中次数</div>
                <div className="stat-value hit">{snapshot?.hits ?? 0}</div>
              </div>
              <div className="stat-cell">
                <div className="stat-label">缺页率</div>
                <div className="stat-value miss">{missRatePercent.toFixed(1)}%</div>
              </div>
            </div>
            <div className="ring-wrap mt-12">
              <MetricRing percent={missRatePercent} label="缺页率" subLabel={riskText} tone={missRatePercent >= 60 ? 'danger' : 'success'} />
            </div>
          </div>

          <div className="card">
            <div className="card-title">置换原理解释</div>
            <div className="principle-card">
              <strong>{currentAlgorithm} 策略：</strong>
              <div className="mt-8">{principle}</div>
            </div>
          </div>
        </div>
      </div>

      <LogConsole steps={trace?.steps ?? []} currentIndex={index} />
    </div>
  );
}
