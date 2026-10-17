/** 缺页率 / 安全度动态进度环（SVG Donut），设计文档 §5.3 GaugeProgressRing。 */
export function MetricRing({
  percent,
  label,
  subLabel,
  tone = 'danger',
  size = 132,
}: {
  percent: number;
  label: string;
  subLabel?: string;
  tone?: 'danger' | 'success' | 'accent';
  size?: number;
}) {
  const stroke = 11;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, percent));
  const dash = (clamped / 100) * circumference;
  const color =
    tone === 'danger' ? 'var(--color-danger)' : tone === 'success' ? 'var(--color-success)' : 'var(--color-accent-primary)';

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label} ${clamped.toFixed(1)}%`}>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="var(--color-bg-active)"
        strokeWidth={stroke}
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circumference - dash}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dasharray 0.3s ease' }}
      />
      <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" className="ring-center-text">
        {`${clamped.toFixed(clamped >= 100 || clamped === 0 ? 0 : 1)}%`}
      </text>
      <text x="50%" y="63%" textAnchor="middle" dominantBaseline="middle" className="ring-sub-text">
        {label}
      </text>
      {subLabel ? (
        <text x="50%" y="75%" textAnchor="middle" dominantBaseline="middle" className="ring-sub-text">
          {subLabel}
        </text>
      ) : null}
    </svg>
  );
}
