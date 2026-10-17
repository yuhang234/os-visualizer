import { useCallback, useEffect, useMemo, useState } from 'react';
import { ClipboardPaste, Download, RotateCcw, Save, Search, Trash2, Zap } from 'lucide-react';
import { checkBankerSafety, deleteScenario, listScenarios, requestBankerResource, saveScenario } from '../services/algorithmApi';
import type { ScenarioRecord } from '../services/algorithmApi';
import { errorMessage } from '../services/client';
import { useAuth } from '../hooks/useAuth';
import { usePlayback } from '../hooks/usePlayback';
import { Badge } from '../components/common/Badge';
import { Modal } from '../components/common/Modal';
import { LogConsole } from '../components/visualizer/LogConsole';
import type {
  BankerRequestSnapshot,
  BankerSafetySnapshot,
  BankerState,
  SafetyRow,
} from '../types/algorithm';

const RESOURCE_NAMES = ['A', 'B', 'C', 'D', 'E', 'F'];

const PRESETS = [
  {
    label: '教材标准 5 进程 3 资源',
    available: [3, 3, 2],
    maxMatrix: [
      [7, 5, 3],
      [3, 2, 2],
      [9, 0, 2],
      [2, 2, 2],
      [4, 3, 3],
    ],
    allocationMatrix: [
      [0, 1, 0],
      [2, 0, 0],
      [3, 0, 2],
      [2, 1, 1],
      [0, 0, 2],
    ],
  },
  {
    label: '三进程安全序列演示',
    available: [3, 3, 2],
    maxMatrix: [
      [7, 5, 3],
      [3, 2, 2],
      [9, 0, 2],
    ],
    allocationMatrix: [
      [0, 1, 0],
      [2, 0, 0],
      [3, 0, 2],
    ],
  },
];

function clone(matrix: number[][]): number[][] {
  return matrix.map((row) => [...row]);
}

function resize(matrix: number[][], rows: number, cols: number): number[][] {
  const result: number[][] = [];
  for (let i = 0; i < rows; i += 1) {
    const row: number[] = [];
    for (let j = 0; j < cols; j += 1) {
      row.push(matrix[i]?.[j] ?? 0);
    }
    result.push(row);
  }
  return result;
}

function isSafetySnapshot(snapshot: BankerSafetySnapshot | BankerRequestSnapshot): snapshot is BankerSafetySnapshot {
  return ['INIT', 'COMPLETE', 'SKIP', 'FINAL'].includes((snapshot as BankerSafetySnapshot).phase);
}

type CasePayload = {
  available?: number[];
  maxMatrix?: number[][];
  allocationMatrix?: number[][];
};

function VectorChips({ values, changed, danger }: { values: number[]; changed?: boolean[]; danger?: boolean[] }) {
  return (
    <span className="vector-view">
      {values.map((value, index) => (
        <span
          className={`vector-chip${danger?.[index] ? ' danger' : changed?.[index] ? ' changed' : ''}`}
          key={index}
        >
          {value}
        </span>
      ))}
    </span>
  );
}

export function BankerView() {
  const { trace, currentStep, index, totalSteps, loadTrace, status } = usePlayback();
  const { isGuest } = useAuth();

  const [processCount, setProcessCount] = useState(5);
  const [resourceCount, setResourceCount] = useState(3);
  const [available, setAvailable] = useState<number[]>(PRESETS[0].available);
  const [maxMatrix, setMaxMatrix] = useState<number[][]>(PRESETS[0].maxMatrix);
  const [allocationMatrix, setAllocationMatrix] = useState<number[][]>(PRESETS[0].allocationMatrix);
  const [requestProcess, setRequestProcess] = useState(1);
  const [requestVector, setRequestVector] = useState<number[]>([1, 0, 2]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState('');
  const [importError, setImportError] = useState<string | null>(null);
  const [cases, setCases] = useState<ScenarioRecord[]>([]);
  const [caseHint, setCaseHint] = useState<string | null>(null);
  const [activeCaseId, setActiveCaseId] = useState<number | null>(null);

  const needMatrix = useMemo(
    () => maxMatrix.map((row, i) => row.map((value, j) => Math.max(0, value - (allocationMatrix[i]?.[j] ?? 0)))),
    [maxMatrix, allocationMatrix],
  );

  const snapshot = useMemo<BankerSafetySnapshot | BankerRequestSnapshot | null>(() => {
    if (!trace || !currentStep) return null;
    if (trace.algorithmId !== 'banker-safety' && trace.algorithmId !== 'banker-request') return null;
    return currentStep.snapshot as BankerSafetySnapshot | BankerRequestSnapshot;
  }, [trace, currentStep]);

  const safetyView = useMemo(() => {
    if (snapshot && isSafetySnapshot(snapshot)) return snapshot;
    return null;
  }, [snapshot]);

  const requestView = useMemo(() => {
    if (snapshot && !isSafetySnapshot(snapshot)) return snapshot as BankerRequestSnapshot;
    return null;
  }, [snapshot]);

  const traceState = useMemo<BankerState | null>(() => {
    if (!trace) return null;
    if (trace.algorithmId !== 'banker-safety' && trace.algorithmId !== 'banker-request') return null;
    return (trace as { state?: BankerState }).state ?? null;
  }, [trace]);

  /* ---------------------------- 输入辅助 ---------------------------- */

  const applyCounts = (nextProcessCount: number, nextResourceCount: number) => {
    setProcessCount(nextProcessCount);
    setResourceCount(nextResourceCount);
    setMaxMatrix((current) => resize(current, nextProcessCount, nextResourceCount));
    setAllocationMatrix((current) => resize(current, nextProcessCount, nextResourceCount));
    setAvailable((current) => {
      const next = [...current];
      while (next.length < nextResourceCount) next.push(0);
      return next.slice(0, nextResourceCount);
    });
    setRequestVector((current) => {
      const next = [...current];
      while (next.length < nextResourceCount) next.push(0);
      return next.slice(0, nextResourceCount);
    });
    setRequestProcess((current) => Math.min(current, nextProcessCount - 1));
  };

  const applyPreset = (label: string) => {
    const preset = PRESETS.find((item) => item.label === label);
    if (!preset) return;
    setProcessCount(preset.maxMatrix.length);
    setResourceCount(preset.available.length);
    setAvailable([...preset.available]);
    setMaxMatrix(clone(preset.maxMatrix));
    setAllocationMatrix(clone(preset.allocationMatrix));
    setRequestVector(preset.available.map(() => 0));
    setRequestProcess(1);
    setError(null);
  };

  const updateMatrix = (
    setter: (updater: (current: number[][]) => number[][]) => void,
    row: number,
    column: number,
    value: number,
  ) => {
    const clamped = Math.max(0, Math.min(99, Number.isFinite(value) ? value : 0));
    setter((current) => current.map((items, i) => (i === row ? items.map((item, j) => (j === column ? clamped : item)) : items)));
  };

  /* ---------------------- 云端矩阵案例（登录用户） ---------------------- */

  const refreshCases = useCallback(async () => {
    if (isGuest) {
      setCases([]);
      return;
    }
    try {
      setCases(await listScenarios('banker'));
    } catch {
      setCases([]); // 案例列表属于增强能力，拉取失败不打断算法演示
    }
  }, [isGuest]);

  useEffect(() => {
    void refreshCases();
  }, [refreshCases]);

  const saveCurrentCase = async () => {
    if (isGuest) {
      setCaseHint('游客模式下算法全开放；登录后可将自定义矩阵保存为云端案例并跨设备同步。');
      return;
    }
    const input = window.prompt('案例名称（1 ~ 64 字）', `自定义矩阵 ${cases.length + 1}`);
    const name = (input ?? '').trim().slice(0, 64);
    if (!name) return;
    try {
      await saveScenario('banker', name, {
        processCount,
        resourceCount,
        available: [...available],
        maxMatrix: clone(maxMatrix),
        allocationMatrix: clone(allocationMatrix),
      });
      setCaseHint(`案例「${name}」已保存到云端`);
      const updated = await listScenarios('banker').catch(() => null);
      if (updated) {
        setCases(updated);
        const saved = updated.find((item) => item.name === name);
        setActiveCaseId(saved?.id ?? null);
      }
    } catch (thrown) {
      setCaseHint(errorMessage(thrown));
    }
  };

  const loadCase = (record: ScenarioRecord) => {
    const payload = record.payload as CasePayload;
    const rows = payload.maxMatrix?.length ?? 0;
    const columns = payload.available?.length ?? 0;
    if (!rows || !columns || !payload.allocationMatrix) {
      setCaseHint('该案例数据不完整，无法载入');
      return;
    }
    setProcessCount(rows);
    setResourceCount(columns);
    setAvailable(payload.available ? [...payload.available] : available.map(() => 0));
    setMaxMatrix(clone(resize(payload.maxMatrix ?? [], rows, columns)));
    setAllocationMatrix(clone(resize(payload.allocationMatrix, rows, columns)));
    setRequestVector(Array.from({ length: columns }, () => 0));
    setRequestProcess((current) => Math.min(current, rows - 1));
    setActiveCaseId(record.id);
    setError(null);
    setCaseHint(`已载入案例「${record.name}」，点击「运行安全性检查」开始推导`);
  };

  const removeCase = async (record: ScenarioRecord) => {
    try {
      await deleteScenario(record.id);
      setCaseHint(`案例「${record.name}」已删除`);
      setActiveCaseId(null);
      await refreshCases();
    } catch (thrown) {
      setCaseHint(errorMessage(thrown));
    }
  };

  /* ---------------------------- 动作 ---------------------------- */

  const runSafety = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await checkBankerSafety({ available, maxMatrix, allocationMatrix });
      loadTrace(result.trace);
    } catch (thrown) {
      setError(errorMessage(thrown));
    } finally {
      setBusy(false);
    }
  }, [available, maxMatrix, allocationMatrix, loadTrace]);

  const submitRequest = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await requestBankerResource({
        processIndex: requestProcess,
        requestVector,
        currentState: { available, maxMatrix, allocationMatrix },
      });
      loadTrace(result.trace);
    } catch (thrown) {
      setError(errorMessage(thrown));
    } finally {
      setBusy(false);
    }
  };

  // 首次进入：若已有银行家轨迹则沿用，否则用教材标准案例自动做一次安全性检查
  useEffect(() => {
    if (trace && (trace.algorithmId === 'banker-safety' || trace.algorithmId === 'banker-request')) {
      return;
    }
    void runSafety();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const exportConfig = async () => {
    const payload = JSON.stringify({ available, maxMatrix, allocationMatrix }, null, 2);
    try {
      await navigator.clipboard.writeText(payload);
      setImportText(payload);
      setShowImport(true);
      setImportError('配置已复制到剪贴板，可直接粘贴分享。');
    } catch {
      setImportText(payload);
      setShowImport(true);
    }
  };

  const importConfig = () => {
    try {
      const parsed = JSON.parse(importText) as {
        available?: number[];
        maxMatrix?: number[][];
        allocationMatrix?: number[][];
      };
      if (!Array.isArray(parsed.available) || !Array.isArray(parsed.maxMatrix) || !Array.isArray(parsed.allocationMatrix)) {
        setImportError('JSON 必须包含 available / maxMatrix / allocationMatrix 三个字段');
        return;
      }
      const rows = parsed.maxMatrix.length;
      const cols = parsed.available.length;
      if (rows < 1 || rows > 10 || cols < 1 || cols > 6) {
        setImportError('进程数需在 1~10、资源种类需在 1~6 之间');
        return;
      }
      setProcessCount(rows);
      setResourceCount(cols);
      setAvailable(parsed.available.map((value) => Math.max(0, Math.min(99, Number(value) || 0))));
      setMaxMatrix(resize(parsed.maxMatrix, rows, cols));
      setAllocationMatrix(resize(parsed.allocationMatrix, rows, cols));
      setRequestProcess(0);
      setRequestVector(new Array(cols).fill(0));
      setImportError(null);
      setShowImport(false);
    } catch (thrown) {
      setImportError(errorMessage(thrown));
    }
  };

  /* ---------------------------- 渲染数据 ---------------------------- */

  const processNames = traceState?.processNames ?? Array.from({ length: processCount }, (_, i) => `P${i}`);
  const resourceNames = traceState?.resourceNames ?? RESOURCE_NAMES.slice(0, resourceCount);

  const rows: SafetyRow[] = safetyView?.rows ?? [];
  const activeProcess = snapshot?.processIndex ?? null;
  const activeName = snapshot?.process ?? null;
  const needCurrent = safetyView?.need ?? null;
  const workBefore = safetyView?.workBefore ?? null;

  const conditionState = (() => {
    if (safetyView == null) return null;
    if (safetyView.satisfied == null) return null;
    return safetyView.satisfied;
  })();

  const finalVerdict = (() => {
    if (safetyView) {
      // 后端只在 FINAL 步骤给出 isSafe，推导过程中应显示“判定中”而不是“未运行判定”
      if (safetyView.isSafe == null) {
        return { safe: null as boolean | null, label: '判定中…', detail: currentStep?.description ?? '' };
      }
      return { safe: safetyView.isSafe, label: safetyView.isSafe ? '状态: 安全 (SAFE)' : '状态: 不安全 (UNSAFE)', detail: currentStep?.description ?? '' };
    }
    if (requestView) {
      const granted = requestView.granted;
      if (granted == null) {
        return { safe: null, label: '判定中…', detail: currentStep?.description ?? '' };
      }
      return {
        safe: granted,
        label: granted ? '允许立即分配 (GRANTED)' : requestView.rolledBack ? '拒绝并回滚 / 等待 (ROLLBACK)' : '判定中…',
        detail: currentStep?.description ?? '',
      };
    }
    return { safe: null as boolean | null, label: '未运行判定', detail: '点击「运行安全性检查」开始逐步推导。' };
  })();

  const safeSequence = safetyView?.safeSequence ?? requestView?.safeSequence ?? [];

  return (
    <div>
      <div className="page-head">
        <span className="page-title">银行家算法 (Banker's Algorithm)</span>
        <div className="page-actions">
          <select
            className="input-field input-inline"
            defaultValue=""
            onChange={(event) => {
              if (event.target.value) applyPreset(event.target.value);
            }}
            title="预设案例"
          >
            <option value="">预设案例：教材标准5进程3资源 ▼</option>
            {PRESETS.map((preset) => (
              <option key={preset.label} value={preset.label}>
                {preset.label}
              </option>
            ))}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={() => void saveCurrentCase()} type="button">
            <Save size={15} /> 保存案例
          </button>
          {cases.length > 0 ? (
            <>
              <select
                className="input-field input-inline"
                value=""
                onChange={(event) => {
                  const record = cases.find((item) => String(item.id) === event.target.value);
                  if (record) loadCase(record);
                }}
                title="我的云端案例"
              >
                <option value="">我的案例（{cases.length}）▼</option>
                {cases.map((record) => (
                  <option key={record.id} value={record.id}>
                    {record.name}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-secondary btn-sm btn-danger"
                disabled={activeCaseId == null}
                onClick={() => {
                  const target = cases.find((item) => item.id === activeCaseId);
                  if (target) void removeCase(target);
                }}
                title={activeCaseId == null ? '先载入一个案例，再删除它' : '删除当前载入的案例'}
                type="button"
              >
                <Trash2 size={15} /> 删除该案例
              </button>
            </>
          ) : null}
          {caseHint ? <span className="help-text">{caseHint}</span> : null}
        </div>
      </div>

      <div className="config-card">
        <div className="config-row">
          <span className="config-label">进程总数:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={1}
            max={10}
            value={processCount}
            style={{ width: 76 }}
            onChange={(event) => applyCounts(Math.max(1, Math.min(10, Number(event.target.value) || 1)), resourceCount)}
          />
          <span className="config-label">资源种类:</span>
          <input
            className="input-field input-inline"
            type="number"
            min={1}
            max={6}
            value={resourceCount}
            style={{ width: 76 }}
            onChange={(event) => applyCounts(processCount, Math.max(1, Math.min(6, Number(event.target.value) || 1)))}
          />
          <span className="config-label">初始 Available:</span>
          {available.map((value, j) => (
            <span key={j} className="row-inline" style={{ gap: 4 }}>
              <span className="mono-xs muted">{resourceNames[j]}:</span>
              <input
                className="cell-input"
                value={value}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setAvailable((current) => current.map((item, k) => (k === j ? Math.max(0, Math.min(99, Number.isFinite(next) ? next : 0)) : item)));
                }}
              />
            </span>
          ))}
        </div>

        <div className="matrix-grid mt-12">
          <div className="matrix-card">
            <div className="matrix-card-title">
              <span>Max 矩阵 (最大需求)</span>
              <span className="muted">可编辑</span>
            </div>
            <table className="matrix-table">
              <thead>
                <tr>
                  <th>进程</th>
                  {resourceNames.map((name) => (
                    <th key={name}>{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {maxMatrix.map((row, i) => (
                  <tr key={i}>
                    <td className="row-label">{processNames[i]}</td>
                    {row.map((value, j) => (
                      <td key={j}>
                        <input
                          className="cell-input"
                          value={value}
                          onChange={(event) => updateMatrix(setMaxMatrix, i, j, Number(event.target.value))}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="matrix-card">
            <div className="matrix-card-title">
              <span>Allocation (已分配)</span>
              <span className="muted">可编辑</span>
            </div>
            <table className="matrix-table">
              <thead>
                <tr>
                  <th>进程</th>
                  {resourceNames.map((name) => (
                    <th key={name}>{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {allocationMatrix.map((row, i) => (
                  <tr key={i}>
                    <td className="row-label">{processNames[i]}</td>
                    {row.map((value, j) => (
                      <td key={j}>
                        <input
                          className="cell-input"
                          value={value}
                          onChange={(event) => updateMatrix(setAllocationMatrix, i, j, Number(event.target.value))}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="matrix-card">
            <div className="matrix-card-title">
              <span>Need (需求 = Max - Alloc)</span>
              <span className="muted">自动计算</span>
            </div>
            <table className="matrix-table">
              <thead>
                <tr>
                  <th>进程</th>
                  {resourceNames.map((name) => (
                    <th key={name}>{name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {needMatrix.map((row, i) => (
                  <tr key={i} className={activeProcess === i && safetyView ? 'row-active' : ''}>
                    <td className="row-label">{processNames[i]}</td>
                    {row.map((value, j) => (
                      <td key={j}>{value}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="config-row mt-16">
          <button className="btn btn-secondary btn-sm" onClick={() => setShowImport(true)} type="button">
            <ClipboardPaste size={15} /> 文本 / JSON 一键导入
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => void exportConfig()} type="button">
            <Download size={15} /> 导出配置
          </button>
          <button className="btn btn-primary btn-sm" onClick={() => void runSafety()} disabled={busy} type="button">
            {busy ? <span className="spinner" /> : <Search size={15} />} 运行安全性检查
          </button>
        </div>
        {error ? <div className="alert alert-error mt-8">{error}</div> : null}
      </div>

      <div className="viz-grid">
        <div className="viz-main card">
          <div className="flex-between mb-12">
            <div className="card-title mb-0">安全性检查推导动态大屏 (Work &amp; Finish)</div>
            <span className="mono-sm secondary-text">
              步骤 {totalSteps === 0 ? 0 : index + 1} / {totalSteps}
            </span>
          </div>

          <div className="row-inline mb-12">
            <span className="secondary-text">
              当前检查进程:{' '}
              <strong className="mono-sm" style={{ color: 'var(--color-accent-primary)' }}>
                {activeName ?? '—'}
              </strong>
            </span>
            <span className="muted">|</span>
            {needCurrent && workBefore ? (
              <span className="row-inline" style={{ gap: 6 }}>
                <span className="secondary-text">判定条件: Need[{activeName}] ({needCurrent.join(',')}) ≤ Work ({workBefore.join(',')})</span>
                <span>➔</span>
                {conditionState == null ? (
                  <Badge tone="muted">待判定</Badge>
                ) : conditionState ? (
                  <Badge tone="success">✅ 满足</Badge>
                ) : (
                  <Badge tone="warning">⏳ 不满足，本轮跳过</Badge>
                )}
              </span>
            ) : (
              <span className="secondary-text">
                {snapshot ? <span className="phase-badge">{snapshot.phase}</span> : '等待运行安全性检查'}
              </span>
            )}
          </div>

          <table className="mini-table">
            <thead>
              <tr>
                <th>进程</th>
                <th>Work (可用)</th>
                <th>Need (需求)</th>
                <th>Allocation</th>
                <th>Work+Alloc</th>
                <th>Finish状态</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    尚未有完成的进程，检查从 Work = Available 开始。
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.process} className="row-finish">
                    <td>{row.process}</td>
                    <td>{row.workBefore.join('  ')}</td>
                    <td>{row.need.join('  ')}</td>
                    <td>{row.allocation.join('  ')}</td>
                    <td>{row.workAfter.join('  ')}</td>
                    <td>
                      <Badge tone="success">[✅ TRUE]</Badge>
                    </td>
                  </tr>
                ))
              )}
              {safetyView && safetyView.process && safetyView.satisfied == null ? (
                <tr className="row-active">
                  <td>{safetyView.process}</td>
                  <td>{safetyView.workBefore.join('  ')}</td>
                  <td>{safetyView.need?.join('  ') ?? '—'}</td>
                  <td>{safetyView.allocation?.join('  ') ?? '—'}</td>
                  <td>{safetyView.workAfter.join('  ')}</td>
                  <td>[等待检查]</td>
                </tr>
              ) : null}
            </tbody>
          </table>

          {safetyView ? (
            <div className="mt-12">
              <span className="config-label">各进程 Finish 状态:</span>
              <div className="row-inline mt-8">
                {safetyView.finish.map((value, i) => (
                  <Badge key={i} tone={value ? 'success' : 'muted'}>
                    {processNames[i]} {value ? '✅' : '⏳'}
                  </Badge>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-16">
            <span className="config-label">当前找到的安全序列:</span>
            <div className="safe-seq">
              {safeSequence.length === 0 ? (
                <>
                  {processNames.map((name) => (
                    <span className="seq-node pending" key={name}>
                      {name}
                    </span>
                  ))}
                </>
              ) : (
                safeSequence.map((name, position) => (
                  <span key={`${name}-${position}`} className="row-inline" style={{ gap: 8 }}>
                    {position > 0 ? <span className="seq-arrow">──➔</span> : null}
                    <span className="seq-node">{name}</span>
                  </span>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="viz-side">
          <div className="card">
            <div className="card-title">最终判定结果看板</div>
            <div className={`verdict${finalVerdict.safe == null ? ' pending' : finalVerdict.safe ? ' safe' : ' unsafe'}`}>
              <h3>{finalVerdict.label}</h3>
              <div className="help-text" style={{ color: 'inherit' }}>
                {finalVerdict.detail}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title">动态资源请求交互模态区</div>
            <div className="config-row">
              <span className="config-label">发起请求进程:</span>
              <select
                className="input-field input-inline"
                value={requestProcess}
                onChange={(event) => setRequestProcess(Number(event.target.value))}
              >
                {processNames.map((name, i) => (
                  <option key={name} value={i}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div className="config-row">
              <span className="config-label">请求量:</span>
              {requestVector.map((value, j) => (
                <span key={j} className="row-inline" style={{ gap: 4 }}>
                  <span className="mono-xs muted">{resourceNames[j]}:</span>
                  <input
                    className="cell-input"
                    value={value}
                    onChange={(event) => {
                      const next = Number(event.target.value);
                      setRequestVector((current) =>
                        current.map((item, k) => (k === j ? Math.max(0, Math.min(99, Number.isFinite(next) ? next : 0)) : item)),
                      );
                    }}
                  />
                </span>
              ))}
            </div>
            <button className="btn btn-primary btn-sm btn-block mt-8" onClick={() => void submitRequest()} disabled={busy} type="button">
              {busy ? <span className="spinner" /> : <Zap size={15} />} 提交分配申请并判定
            </button>

            {requestView ? (
              <div className="mt-16 flex-col">
                <span className="phase-badge">阶段: {requestView.phase}</span>
                <div className="row-inline">
                  <span className="config-label">Request:</span>
                  <VectorChips values={requestView.request} />
                </div>
                <div className="row-inline">
                  <span className="config-label">Need[{requestView.process}]:</span>
                  <VectorChips
                    values={requestView.need}
                    danger={requestView.request.map((value, i) => value > requestView.need[i])}
                  />
                </div>
                <div className="row-inline">
                  <span className="config-label">Available:</span>
                  <VectorChips
                    values={requestView.availableBefore ?? requestView.available}
                    changed={requestView.availableBefore ? requestView.available.map((value, i) => value !== requestView.availableBefore?.[i]) : undefined}
                  />
                </div>
                <div className="row-inline">
                  <span className="config-label">条件一 (Request ≤ Need):</span>
                  {requestView.checkNeed == null ? (
                    <Badge tone="muted">待检查</Badge>
                  ) : requestView.checkNeed ? (
                    <Badge tone="success">✅ 成立</Badge>
                  ) : (
                    <Badge tone="danger">❌ 不成立</Badge>
                  )}
                </div>
                <div className="row-inline">
                  <span className="config-label">条件二 (Request ≤ Available):</span>
                  {requestView.checkAvailable == null ? (
                    <Badge tone="muted">待检查</Badge>
                  ) : requestView.checkAvailable ? (
                    <Badge tone="success">✅ 成立</Badge>
                  ) : (
                    <Badge tone="warning">⏳ 不成立</Badge>
                  )}
                </div>
                {requestView.reason ? (
                  <div className={`alert ${requestView.granted ? 'alert-success' : 'alert-warning'} mb-0`}>{requestView.reason}</div>
                ) : null}
              </div>
            ) : (
              <div className="help-text mt-12">提交一次分配申请，逐步观看三步判定与试探分配的安全性检查。</div>
            )}
          </div>

          <div className="card">
            <div className="flex-between">
              <div className="card-title mb-0">当前轨迹</div>
              <span className="badge badge-muted">
                {trace?.algorithmId === 'banker-safety'
                  ? '安全性检查'
                  : trace?.algorithmId === 'banker-request'
                    ? '资源请求判定'
                    : '无'}
              </span>
            </div>
            <div className="help-text mt-8">{status === 'PLAYING' ? '播放中' : '已就绪'} · 共 {totalSteps} 步</div>
            <button className="btn btn-secondary btn-sm btn-block mt-12" onClick={() => void runSafety()} disabled={busy} type="button">
              <RotateCcw size={15} /> 重新运行安全性检查
            </button>
          </div>
        </div>
      </div>

      <LogConsole steps={trace?.steps ?? []} currentIndex={index} />

      {showImport ? (
        <Modal
          title="文本 / JSON 一键导入 · 导出"
          onClose={() => {
            setShowImport(false);
            setImportError(null);
          }}
        >
          <div className="field">
            <span className="field-label">配置内容（JSON）</span>
            <textarea
              className="input-field input-mono"
              style={{ minHeight: 180 }}
              value={importText}
              onChange={(event) => setImportText(event.target.value)}
              placeholder='{"available":[3,3,2],"maxMatrix":[[7,5,3],...],"allocationMatrix":[[0,1,0],...]}'
            />
          </div>
          {importError ? <div className="alert alert-info">{importError}</div> : null}
          <div className="row-inline">
            <button className="btn btn-primary btn-sm" onClick={importConfig} type="button">
              导入并应用
            </button>
            <button
              className="btn btn-secondary btn-sm"
              type="button"
              onClick={() => {
                setImportText(JSON.stringify({ available, maxMatrix, allocationMatrix }, null, 2));
                setImportError(null);
              }}
            >
              从当前表单刷新
            </button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}
