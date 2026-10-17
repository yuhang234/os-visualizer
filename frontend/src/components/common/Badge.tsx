import type { ReactNode } from 'react';

export type BadgeTone = 'success' | 'danger' | 'warning' | 'info' | 'accent' | 'muted';

const TONE_CLASS: Record<BadgeTone, string> = {
  success: 'badge badge-success',
  danger: 'badge badge-danger',
  warning: 'badge badge-warning',
  info: 'badge badge-info',
  accent: 'badge badge-accent',
  muted: 'badge badge-muted',
};

export function Badge({ tone = 'muted', children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={TONE_CLASS[tone]}>{children}</span>;
}
