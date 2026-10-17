import { useEffect, useMemo, useRef } from 'react';
import type { TraceStep } from '../../types/algorithm';

/** 控制台运行日志：只累积到当前步骤，追加时平滑置底（设计文档 §4.3）。 */
export function LogConsole({
  steps,
  currentIndex,
  title = '控制台运行日志 (Console Execution Log)',
  tall = false,
  onClear,
}: {
  steps: TraceStep[];
  currentIndex: number;
  title?: string;
  tall?: boolean;
  onClear?: () => void;
}) {
  const bodyRef = useRef<HTMLDivElement | null>(null);

  const entries = useMemo(() => {
    const list: { key: string; timestamp: string; level: string; message: string }[] = [];
    for (let index = 0; index <= currentIndex && index < steps.length; index += 1) {
      const step = steps[index];
      for (const log of step.logs) {
        list.push({
          key: `${index}-${list.length}`,
          timestamp: log.timestamp,
          level: log.level,
          message: log.message,
        });
      }
    }
    return list;
  }, [steps, currentIndex]);

  const lastCountRef = useRef(0);
  useEffect(() => {
    if (entries.length !== lastCountRef.current && bodyRef.current) {
      bodyRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
    lastCountRef.current = entries.length;
  }, [entries.length]);

  return (
    <div className="terminal">
      <div className="terminal-head">
        <span className="terminal-dot" style={{ background: 'var(--color-danger)' }} />
        <span className="terminal-dot" style={{ background: 'var(--color-warning)' }} />
        <span className="terminal-dot" style={{ background: 'var(--color-success)' }} />
        <span className="terminal-title">{title}</span>
        <span className="spacer" />
        {onClear ? (
          <button className="btn btn-ghost btn-sm" onClick={onClear} type="button">
            清空日志
          </button>
        ) : null}
      </div>
      <div className={`terminal-body${tall ? ' tall' : ''}`} ref={bodyRef}>
        {entries.length === 0 ? (
          <div className="log-line">
            <span className="log-msg">（等待执行轨迹……）</span>
          </div>
        ) : (
          entries.map((entry) => (
            <div className="log-line" key={entry.key}>
              <span className="log-time">[{entry.timestamp}]</span>
              <span className={`log-level log-level-${entry.level}`}>{entry.level}</span>
              <span className="log-msg">{entry.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
