import type { PageRepSnapshot } from '../../types/algorithm';

/** CLOCK 环形表盘与指针（设计文档 §5.3 ClockPointerWidget，SVG 指针动画）。 */
export function ClockDial({ snapshot }: { snapshot: PageRepSnapshot }) {
  const size = 240;
  const center = size / 2;
  const radius = 84;
  const count = snapshot.frameCount || 1;
  const pointer = snapshot.clockPointer ?? 0;
  const angleStep = 360 / count;
  const needleAngle = pointer * angleStep - 90;

  return (
    <div className="clock-widget">
      <div className="clock-ring">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="CLOCK 环形缓冲区指针">
          <circle cx={center} cy={center} r={radius} fill="none" stroke="var(--color-border-default)" strokeWidth={2} />
          {snapshot.frames.map((page, index) => {
            const angle = (index * angleStep - 90) * (Math.PI / 180);
            const x = center + radius * Math.cos(angle);
            const y = center + radius * Math.sin(angle);
            const bit = snapshot.clockRefBits?.[index] ? 1 : 0;
            const isPointer = index === pointer;
            const inSweep = snapshot.clockSweep?.includes(index);
            return (
              <g key={index}>
                <circle
                  cx={x}
                  cy={y}
                  r={26}
                  fill={page == null ? 'var(--color-bg-subtle)' : bit ? 'var(--color-success-bg)' : 'var(--color-bg-panel)'}
                  stroke={
                    isPointer
                      ? 'var(--color-accent-primary)'
                      : inSweep
                        ? 'var(--color-warning)'
                        : page == null
                          ? 'var(--color-border-strong)'
                          : 'var(--color-border-default)'
                  }
                  strokeWidth={isPointer || inSweep ? 3 : 1.5}
                />
                <text x={x} y={y - 3} textAnchor="middle" dominantBaseline="middle" fontSize="15" fontFamily="var(--font-mono)" fill="var(--color-text-primary)">
                  {page == null ? '—' : page}
                </text>
                <text x={x} y={y + 13} textAnchor="middle" dominantBaseline="middle" fontSize="10" fontFamily="var(--font-mono)" fill={bit ? 'var(--color-success)' : 'var(--color-text-muted)'}>
                  bit {bit}
                </text>
              </g>
            );
          })}
          <g className="clock-needle" style={{ transform: `rotate(${needleAngle + 90}deg)`, transformOrigin: `${center}px ${center}px` }}>
            <line
              x1={center}
              y1={center}
              x2={center}
              y2={center - radius + 30}
              stroke="var(--color-accent-primary)"
              strokeWidth={3}
              strokeLinecap="round"
            />
            <circle cx={center} cy={center} r={5} fill="var(--color-accent-primary)" />
          </g>
        </svg>
      </div>
      <div className="help-text">
        指针当前位于 <strong className="mono-sm" style={{ color: 'var(--color-accent-primary)' }}>页框 {pointer}</strong>
        <br />
        扫描规则：访问位 = 1 则清零并给第二次机会；访问位 = 0 则淘汰该页并载入新页。
        <br />
        {snapshot.clockSweep && snapshot.clockSweep.length > 0 ? (
          <span style={{ color: 'var(--color-warning)' }}>
            本轮二次机会：页框 {snapshot.clockSweep.join('、')}
          </span>
        ) : (
          <span>本轮无二次机会</span>
        )}
      </div>
    </div>
  );
}
