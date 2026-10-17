/**
 * Web Audio 程序化音效合成器（设计文档 §12）。
 * - 零静态资源：全部用 OscillatorNode / GainNode 实时合成
 * - 音效事件映射严格按 §12.2：HIT / MISS / STEP / SAFE / DEADLOCK / SWITCH
 * - 每个音符起止都施加 5ms 指数缓动，8x 高倍速下也不爆音（§15.2 风险二）
 */

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { STORAGE_KEYS } from '../services/client';

export type ToneEvent =
  | 'TONE_HIT'
  | 'TONE_MISS'
  | 'TONE_STEP'
  | 'TONE_SAFE'
  | 'TONE_DEADLOCK'
  | 'TONE_SWITCH_BLOCK'
  | 'TONE_SWITCH_WAKE';

const ATTACK = 0.005;

class SynthEngine {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;

  private ensure(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    if (!this.ctx) {
      this.ctx = new Ctor();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.7;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') {
      void this.ctx.resume();
    }
    return this.ctx;
  }

  setVolume(volume: number): void {
    if (this.master) {
      this.master.gain.value = Math.max(0, Math.min(1, volume));
    }
    this.pendingVolume = volume;
  }

  private pendingVolume: number | null = null;

  /** 用户手势后预热 AudioContext（浏览器自动播放策略）。 */
  unlock(): void {
    const ctx = this.ensure();
    if (ctx && this.pendingVolume != null && this.master) {
      this.master.gain.value = Math.max(0, Math.min(1, this.pendingVolume));
    }
  }

  private note(
    ctx: AudioContext,
    options: {
      type: OscillatorType;
      from: number;
      to?: number;
      duration: number;
      gain: number;
      delay?: number;
      filter?: number;
    },
  ): void {
    const start = ctx.currentTime + (options.delay ?? 0);
    const end = start + options.duration;
    const osc = ctx.createOscillator();
    osc.type = options.type;
    osc.frequency.setValueAtTime(options.from, start);
    if (options.to != null && options.to !== options.from) {
      osc.frequency.exponentialRampToValueAtTime(Math.max(20, options.to), end);
    }
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, options.gain), start + ATTACK);
    gain.gain.exponentialRampToValueAtTime(0.0001, end);
    let tail: AudioNode = gain;
    if (options.filter) {
      const lowpass = ctx.createBiquadFilter();
      lowpass.type = 'lowpass';
      lowpass.frequency.value = options.filter;
      gain.connect(lowpass);
      tail = lowpass;
    }
    osc.connect(gain);
    tail.connect(this.master ?? ctx.destination);
    osc.start(start);
    osc.stop(end + 0.02);
  }

  play(event: ToneEvent): void {
    const ctx = this.ensure();
    if (!ctx) return;
    switch (event) {
      case 'TONE_HIT':
        this.note(ctx, { type: 'sine', from: 587.33, to: 880, duration: 0.12, gain: 0.22 });
        break;
      case 'TONE_MISS':
        this.note(ctx, { type: 'triangle', from: 220, to: 110, duration: 0.2, gain: 0.26, filter: 900 });
        break;
      case 'TONE_STEP':
        this.note(ctx, { type: 'sine', from: 1200, duration: 0.03, gain: 0.1 });
        break;
      case 'TONE_SAFE':
        this.note(ctx, { type: 'sine', from: 523.25, duration: 0.35, gain: 0.16 });
        this.note(ctx, { type: 'sine', from: 659.25, duration: 0.35, gain: 0.14 });
        break;
      case 'TONE_DEADLOCK':
        // 锯齿波 180 → 150 Hz 震颤蜂鸣
        this.note(ctx, { type: 'sawtooth', from: 180, to: 150, duration: 0.4, gain: 0.2, filter: 1400 });
        this.note(ctx, { type: 'sawtooth', from: 182, to: 152, duration: 0.4, gain: 0.12, delay: 0.05 });
        break;
      case 'TONE_SWITCH_BLOCK':
        this.note(ctx, { type: 'sine', from: 600, to: 400, duration: 0.08, gain: 0.16 });
        break;
      case 'TONE_SWITCH_WAKE':
        this.note(ctx, { type: 'sine', from: 400, to: 600, duration: 0.08, gain: 0.16 });
        break;
    }
  }
}

const engine = new SynthEngine();

interface AudioContextValue {
  muted: boolean;
  volume: number;
  setMuted: (muted: boolean) => void;
  setVolume: (volume: number) => void;
  playTone: (event: ToneEvent) => void;
  testTone: () => void;
  /** 用户手势后预热 AudioContext（浏览器自动播放策略） */
  unlock: () => void;
}

const AudioReactContext = createContext<AudioContextValue | null>(null);

function readNumber(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function readBool(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return fallback;
    return raw === '1' || raw === 'true';
  } catch {
    return fallback;
  }
}

export function AudioProvider({ children }: { children: ReactNode }) {
  const [muted, setMutedState] = useState<boolean>(() => readBool(STORAGE_KEYS.muted, false));
  const [volume, setVolumeState] = useState<number>(() => {
    const stored = readNumber(STORAGE_KEYS.volume, 0.7);
    return Math.max(0, Math.min(1, stored));
  });
  const mutedRef = useRef(muted);
  mutedRef.current = muted;

  const setMuted = useCallback((next: boolean) => {
    setMutedState(next);
    try {
      localStorage.setItem(STORAGE_KEYS.muted, next ? '1' : '0');
    } catch {
      /* ignore */
    }
  }, []);

  const setVolume = useCallback((next: number) => {
    const clamped = Math.max(0, Math.min(1, next));
    setVolumeState(clamped);
    engine.setVolume(clamped);
    try {
      localStorage.setItem(STORAGE_KEYS.volume, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  const playTone = useCallback(
    (event: ToneEvent) => {
      if (mutedRef.current) return;
      engine.setVolume(volume);
      engine.play(event);
    },
    [volume],
  );

  const testTone = useCallback(() => {
    engine.unlock();
    engine.setVolume(volume);
    engine.play('TONE_HIT');
  }, [volume]);

  const unlock = useCallback(() => {
    engine.unlock();
    engine.setVolume(volume);
  }, [volume]);

  const value = useMemo<AudioContextValue>(
    () => ({ muted, volume, setMuted, setVolume, playTone, testTone, unlock }),
    [muted, volume, setMuted, setVolume, playTone, testTone, unlock],
  );

  return <AudioReactContext.Provider value={value}>{children}</AudioReactContext.Provider>;
}

export function useAudioSynth(): AudioContextValue {
  const context = useContext(AudioReactContext);
  if (!context) {
    throw new Error('useAudioSynth 必须在 <AudioProvider> 内使用');
  }
  return context;
}

/** 步骤事件音调 → 音效事件（设计文档 §12.2 映射表）。 */
export function toneForEventTone(tone: string): ToneEvent | null {
  switch (tone) {
    case 'HIT':
      return 'TONE_HIT';
    case 'MISS':
      return 'TONE_MISS';
    case 'STEP':
      return 'TONE_STEP';
    case 'SUCCESS':
      return 'TONE_SAFE';
    case 'DANGER':
      return 'TONE_DEADLOCK';
    case 'BLOCK':
      return 'TONE_SWITCH_BLOCK';
    case 'WAKEUP':
      return 'TONE_SWITCH_WAKE';
    default:
      return null;
  }
}
