/**
 * 双主题 Hook（设计文档 §3.4）。
 * - 三态：system / light / dark，显式选择写入 localStorage('os_theme')
 * - 仅切换 <html> 上的 `light-theme` class，零组件级重渲染（§1.1）
 * - 与 index.html 的 FOUC 预防脚本共用同一存储键
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { STORAGE_KEYS } from '../services/client';

export type ThemeMode = 'dark' | 'light' | 'system';

interface ThemeContextValue {
  mode: ThemeMode;
  resolved: 'dark' | 'light';
  setMode: (mode: ThemeMode) => void;
  /** 顶栏快捷开关：在深色 / 浅色之间显式切换 */
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEYS.theme);
    if (saved === 'light' || saved === 'dark' || saved === 'system') return saved;
  } catch {
    /* ignore */
  }
  return 'dark';
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function resolve(mode: ThemeMode): 'dark' | 'light' {
  if (mode === 'system') return systemPrefersDark() ? 'dark' : 'light';
  return mode;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(readStoredMode);
  const [resolved, setResolved] = useState<'dark' | 'light'>(() => resolve(readStoredMode()));

  useEffect(() => {
    const next = resolve(mode);
    setResolved(next);
    const root = document.documentElement;
    if (next === 'light') {
      root.classList.add('light-theme');
    } else {
      root.classList.remove('light-theme');
    }
    try {
      localStorage.setItem(STORAGE_KEYS.theme, mode);
    } catch {
      /* ignore */
    }
  }, [mode]);

  useEffect(() => {
    if (mode !== 'system') return;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const listener = () => {
      const next = systemPrefersDark() ? 'dark' : 'light';
      setResolved(next);
      document.documentElement.classList.toggle('light-theme', next === 'light');
    };
    query.addEventListener('change', listener);
    return () => query.removeEventListener('change', listener);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => setModeState(next), []);

  const toggle = useCallback(() => {
    setModeState((current) => (resolve(current) === 'light' ? 'dark' : 'light'));
  }, []);

  /** 全局快捷键：T 在深色 / 浅色之间切换（输入框聚焦时不拦截）。 */
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key !== 't' && event.key !== 'T') return;
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return;
      if (document.querySelector('.modal-overlay')) return;
      toggle();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggle]);

  const value = useMemo<ThemeContextValue>(
    () => ({ mode, resolved, setMode, toggle }),
    [mode, resolved, setMode, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme 必须在 <ThemeProvider> 内使用');
  }
  return context;
}
