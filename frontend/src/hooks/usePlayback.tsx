/**
 * 时间旅行回放引擎（设计文档 §1.2 / §4.2 / §4.3）。
 * - Trace 一次性装载进内存，步进/回退全部 O(1) 取快照，零网络请求、零重算
 * - 自动播放使用 requestAnimationFrame + Delta Time 累加器，避免 setInterval 丢帧
 * - 播放推进时按步骤 eventTone 触发 Web Audio 音效（§12.2）
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { STORAGE_KEYS } from '../services/client';
import { useAudioSynth, toneForEventTone } from './useAudioSynth';
import {
  PLAYBACK_SPEEDS,
  SPEED_INTERVAL_MS,
  type ExecutionTrace,
  type PlaybackSpeed,
  type PlaybackStatus,
  type TraceStep,
} from '../types/algorithm';

interface PlaybackContextValue {
  trace: ExecutionTrace | null;
  index: number;
  totalSteps: number;
  status: PlaybackStatus;
  speed: PlaybackSpeed;
  currentStep: TraceStep | null;
  loadTrace: (trace: ExecutionTrace | null) => void;
  clearTrace: () => void;
  setSpeed: (speed: PlaybackSpeed) => void;
  goto: (index: number) => void;
  next: () => void;
  prev: () => void;
  first: () => void;
  last: () => void;
  play: () => void;
  pause: () => void;
  toggle: () => void;
}

const PlaybackContext = createContext<PlaybackContextValue | null>(null);

function readSpeed(): PlaybackSpeed {
  try {
    const raw = Number(localStorage.getItem(STORAGE_KEYS.speed));
    if ((PLAYBACK_SPEEDS as readonly number[]).includes(raw)) {
      return raw as PlaybackSpeed;
    }
  } catch {
    /* ignore */
  }
  return 1;
}

export function PlaybackProvider({ children }: { children: ReactNode }) {
  const { playTone } = useAudioSynth();
  const [trace, setTrace] = useState<ExecutionTrace | null>(null);
  const [index, setIndex] = useState(0);
  const [status, setStatus] = useState<PlaybackStatus>('IDLE');
  const [speed, setSpeedState] = useState<PlaybackSpeed>(readSpeed);

  const indexRef = useRef(index);
  indexRef.current = index;
  const totalRef = useRef(trace?.totalSteps ?? 0);
  totalRef.current = trace?.totalSteps ?? 0;
  const statusRef = useRef(status);
  statusRef.current = status;
  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef(0);
  const accRef = useRef(0);

  /** 播放推进到某一步：取事件音效并更新游标 */
  const advanceTo = useCallback(
    (target: number) => {
      const total = totalRef.current;
      if (total <= 0) return;
      const clamped = Math.max(0, Math.min(total - 1, target));
      setIndex(clamped);
      const step = trace?.steps[clamped];
      if (step) {
        const tone = toneForEventTone(step.eventTone);
        if (tone) playTone(tone);
      }
    },
    [trace, playTone],
  );

  const stopLoop = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const loop = useCallback(
    (timestamp: number) => {
      if (statusRef.current !== 'PLAYING') return;
      const interval = SPEED_INTERVAL_MS[speed];
      if (!lastTsRef.current) lastTsRef.current = timestamp;
      const delta = timestamp - lastTsRef.current;
      lastTsRef.current = timestamp;
      accRef.current += delta;
      let guard = 0;
      while (accRef.current >= interval && statusRef.current === 'PLAYING' && guard < 64) {
        accRef.current -= interval;
        guard += 1;
        const nextIndex = indexRef.current + 1;
        if (nextIndex >= totalRef.current) {
          setStatus('FINISHED');
          advanceTo(totalRef.current - 1);
          stopLoop();
          return;
        }
        advanceTo(nextIndex);
      }
      rafRef.current = requestAnimationFrame(loop);
    },
    [speed, advanceTo, stopLoop],
  );

  useEffect(() => {
    if (status === 'PLAYING') {
      lastTsRef.current = 0;
      accRef.current = 0;
      stopLoop();
      rafRef.current = requestAnimationFrame(loop);
      return () => stopLoop();
    }
    stopLoop();
    return undefined;
  }, [status, loop, stopLoop]);

  const pause = useCallback(() => {
    setStatus((current) => (current === 'PLAYING' ? 'READY' : current));
  }, []);

  const play = useCallback(() => {
    const total = totalRef.current;
    if (total <= 1) return;
    accRef.current = 0;
    lastTsRef.current = 0;
    if (indexRef.current >= total - 1) {
      setIndex(0);
    }
    setStatus('PLAYING');
  }, []);

  const toggle = useCallback(() => {
    setStatus((current) => {
      if (current === 'PLAYING') return 'READY';
      if ((totalRef.current ?? 0) <= 1) return current;
      accRef.current = 0;
      lastTsRef.current = 0;
      if (indexRef.current >= totalRef.current - 1) {
        setIndex(0);
      }
      return 'PLAYING';
    });
  }, []);

  const loadTrace = useCallback((next: ExecutionTrace | null) => {
    setTrace(next);
    setIndex(0);
    setStatus(next && next.totalSteps > 0 ? 'READY' : 'IDLE');
  }, []);

  const clearTrace = useCallback(() => {
    setTrace(null);
    setIndex(0);
    setStatus('IDLE');
  }, []);

  const setSpeed = useCallback((next: PlaybackSpeed) => {
    setSpeedState(next);
    try {
      localStorage.setItem(STORAGE_KEYS.speed, String(next));
    } catch {
      /* ignore */
    }
  }, []);

  const goto = useCallback(
    (target: number) => {
      pause();
      advanceTo(target);
    },
    [advanceTo, pause],
  );

  const next = useCallback(() => {
    pause();
    if (totalRef.current <= 0) return;
    if (indexRef.current >= totalRef.current - 1) {
      setStatus('FINISHED');
      return;
    }
    advanceTo(indexRef.current + 1);
  }, [advanceTo, pause]);

  const prev = useCallback(() => {
    pause();
    advanceTo(indexRef.current - 1);
  }, [advanceTo, pause]);

  const first = useCallback(() => {
    pause();
    advanceTo(0);
  }, [advanceTo, pause]);

  const last = useCallback(() => {
    pause();
    advanceTo(totalRef.current - 1);
  }, [advanceTo, pause]);

  /**
   * 全局键盘快捷键（设计文档 §15.1 Phase 4「键盘快捷键支持」）。
   * 文档只提出要支持快捷键、未定义键位，此处选取与播放条按钮一一对应的常规键位：
   *   Space / K 播放-暂停，← / → 单步后退-前进，Home / End 跳至首-末，
   *   - / = 降速 / 升速（0.5x → 8x），T 切换深色 / 浅色（在 useTheme 中注册）。
   * 输入框、下拉框、可编辑区域获得焦点时一律让路，模态框打开时也不响应。
   */
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return;
      if (document.querySelector('.modal-overlay')) return;
      if (totalRef.current <= 1) return;
      switch (event.key) {
        case ' ':
        case 'Spacebar':
        case 'k':
        case 'K':
          event.preventDefault();
          toggle();
          break;
        case 'ArrowRight':
          event.preventDefault();
          next();
          break;
        case 'ArrowLeft':
          event.preventDefault();
          prev();
          break;
        case 'Home':
          event.preventDefault();
          first();
          break;
        case 'End':
          event.preventDefault();
          last();
          break;
        case '-':
        case '_':
        case '=':
        case '+': {
          event.preventDefault();
          const position = PLAYBACK_SPEEDS.indexOf(speed);
          const step = event.key === '-' || event.key === '_' ? -1 : 1;
          const nextSpeed = PLAYBACK_SPEEDS[Math.max(0, Math.min(PLAYBACK_SPEEDS.length - 1, position + step))];
          setSpeed(nextSpeed);
          break;
        }
        default:
          break;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [toggle, next, prev, first, last, speed, setSpeed]);

  const currentStep = trace && trace.steps.length > 0 ? trace.steps[Math.min(index, trace.steps.length - 1)] : null;

  const value = useMemo<PlaybackContextValue>(
    () => ({
      trace,
      index,
      totalSteps: trace?.totalSteps ?? 0,
      status,
      speed,
      currentStep,
      loadTrace,
      clearTrace,
      setSpeed,
      goto,
      next,
      prev,
      first,
      last,
      play,
      pause,
      toggle,
    }),
    [
      trace,
      index,
      status,
      speed,
      currentStep,
      loadTrace,
      clearTrace,
      setSpeed,
      goto,
      next,
      prev,
      first,
      last,
      play,
      pause,
      toggle,
    ],
  );

  return <PlaybackContext.Provider value={value}>{children}</PlaybackContext.Provider>;
}

export function usePlayback(): PlaybackContextValue {
  const context = useContext(PlaybackContext);
  if (!context) {
    throw new Error('usePlayback 必须在 <PlaybackProvider> 内使用');
  }
  return context;
}
